"""AC-0009 — the served routes match the committed contract.

Compared against the *generated* document rather than by inspection, so the
two cannot drift silently. What is compared is the route table: every path,
every method, every parameter with its location and required-ness, and every
declared response status. Not the whole document — FastAPI emits a schema
section whose exact shape is the framework's business, and asserting on it
would make every framework upgrade a contract failure while catching no real
drift.

`operationId` is included, because it is the name generated clients use: a
change to it is a breaking change to a consumer even when the path is
unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from .conftest import Client

# NOT module-wide: `test_the_contract_file_includes_the_stream_operation` reads
# only the committed YAML and is free in the offline gate. Only the checks that
# need a running server carry the mark.
CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "runs.yaml"

_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


def _route_table(document: dict[str, Any]) -> dict[str, Any]:
    """Reduce an OpenAPI document to the facts a consumer depends on."""
    table: dict[str, Any] = {}
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            if method not in _METHODS:
                continue
            parameters = {
                (parameter["name"], parameter["in"]): bool(parameter.get("required", False))
                for parameter in operation.get("parameters", [])
            }
            table[f"{method.upper()} {path}"] = {
                "operationId": operation.get("operationId"),
                "parameters": parameters,
                "requestBodyRequired": bool(
                    operation.get("requestBody", {}).get("required", False)
                ),
                "responses": sorted(operation.get("responses", {})),
            }
    return table


@pytest.fixture(scope="session")
def committed() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    return document


@pytest.fixture(scope="session")
def served(api_server: Client) -> dict[str, Any]:
    response = api_server.get("/openapi.json")
    assert response.status == 200
    document: dict[str, Any] = response.body
    return document


def test_the_contract_file_includes_the_stream_operation(
    committed: dict[str, Any],
) -> None:
    """Setup check, reported separately: it cannot fail on the application.

    It guards against the comparison below passing because both sides are
    empty, which is the way a contract test most often becomes decorative.
    The stream operation's presence is asserted positively; no route total is
    pinned here because pinning a count couples this check to unrelated route
    additions and T1's plan forbids it.

    Break: remove the stream operation from contracts/openapi/runs.yaml while
    leaving the route implemented.  The full generated-versus-committed
    comparison (test_the_served_routes_match_the_committed_contract) still reds
    because the served route is absent from the committed table.
    """
    table = _route_table(committed)
    assert "GET /runs/{run_id}/events/stream" in table


@pytest.mark.substrate
def test_the_served_routes_match_the_committed_contract(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """AC-0009."""
    assert _route_table(served) == _route_table(committed)


@pytest.mark.substrate
def test_the_documents_agree_on_title_and_version(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """A consumer pins the version; a silent bump is a silent breaking change."""
    assert served["info"]["title"] == committed["info"]["title"]
    assert served["info"]["version"] == committed["info"]["version"]


@pytest.mark.substrate
def test_the_documents_declare_the_same_openapi_major_version(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    served_major = served["openapi"].split(".")[0]
    committed_major = committed["openapi"].split(".")[0]
    assert served_major == committed_major


@pytest.mark.substrate
def test_the_comparison_notices_a_removed_route(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """The check, shown failing. A contract test never seen failing is not one.

    A deliberately mutated copy of the served document must not compare equal.
    The mutation is applied to the copy and never to the application, so no
    mutation switch ships in the served surface.
    """
    mutated = {**served, "paths": {**served["paths"]}}
    mutated["paths"].pop("/runs/{run_id}/snapshot")

    assert _route_table(mutated) != _route_table(committed)


@pytest.mark.substrate
def test_the_comparison_notices_a_renamed_query_parameter(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """A rename keeps the route and breaks every client. It must be caught."""
    import copy

    mutated = copy.deepcopy(served)
    for parameter in mutated["paths"]["/runs/{run_id}/events"]["get"]["parameters"]:
        if parameter["name"] == "after":
            parameter["name"] = "since"

    assert _route_table(mutated) != _route_table(committed)


@pytest.mark.substrate
def test_the_comparison_notices_a_renamed_operation_id(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """The name generated clients call by."""
    import copy

    mutated = copy.deepcopy(served)
    mutated["paths"]["/runs"]["post"]["operationId"] = "create_run"

    assert _route_table(mutated) != _route_table(committed)


@pytest.mark.substrate
def test_every_response_status_the_contract_declares_is_served(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """Stated separately from the table comparison because it is the half a
    reader most wants named: a 404 promised and not served is a lie a client
    finds at run time."""
    committed_table = _route_table(committed)
    served_table = _route_table(served)

    for route, expected in committed_table.items():
        assert expected["responses"] == served_table[route]["responses"], route


def test_the_contract_file_includes_the_analysis_operation(
    committed: dict[str, Any],
) -> None:
    """Setup check: the analysis operation is in the committed contract.

    Mirrors ``test_the_contract_file_includes_the_stream_operation``: guards
    against the full comparison passing vacuously because both sides are empty.

    Break: remove GET /runs/{run_id}/analysis from contracts/openapi/runs.yaml
    while leaving the route implemented.  The served table has the operation;
    the committed table does not — and the comparison fails in the other
    direction.  This offline check catches the committed-only removal.
    """
    table = _route_table(committed)
    assert "GET /runs/{run_id}/analysis" in table


def test_the_contract_file_includes_503_on_start_run(
    committed: dict[str, Any],
) -> None:
    """Setup check: POST /runs in the committed contract declares 503.

    Break: remove '503' from the POST /runs responses in runs.yaml.
    Red: this assertion fails immediately (offline gate).
    """
    responses = committed["paths"]["/runs"]["post"]["responses"]
    assert "503" in responses, (
        "committed contract must declare 503 for POST /runs; "
        "the analysis snapshot read can fail the object store"
    )


def test_the_analysis_operation_carries_an_x_spec_link(
    committed: dict[str, Any],
) -> None:
    """The x-spec link on the analysis endpoint is present and correct.

    Break: remove or change x-spec from GET /runs/{run_id}/analysis in runs.yaml.
    Red: the assertion fires immediately (offline gate).
    """
    path_item = committed["paths"].get("/runs/{run_id}/analysis", {})
    x_spec = path_item.get("get", {}).get("x-spec", "")
    assert "first-published-analysis" in x_spec, (
        "x-spec must reference first-published-analysis spec"
    )
    assert "publishing-through-the-existing-run-boundary" in x_spec, (
        "x-spec must link to the publishing-through-the-existing-run-boundary anchor"
    )


def test_the_start_run_schema_includes_the_analysis_field(
    committed: dict[str, Any],
) -> None:
    """analysis is documented as an optional property of StartRunRequest.

    Break: remove the analysis property from StartRunRequest in runs.yaml.
    Red: this assertion fires immediately (offline gate).
    """
    schema = committed["components"]["schemas"]["StartRunRequest"]
    props = schema.get("properties", {})
    assert "analysis" in props, (
        "StartRunRequest.properties must include the optional analysis field"
    )


def test_the_analysis_request_schema_is_documented(
    committed: dict[str, Any],
) -> None:
    """AnalysisRequest schema is present in the committed contract.

    Break: remove the AnalysisRequest schema from runs.yaml.
    Red: this assertion fires immediately (offline gate).
    """
    schemas = committed["components"]["schemas"]
    assert "AnalysisRequest" in schemas, "components.schemas must include AnalysisRequest"


@pytest.mark.substrate
def test_the_comparison_notices_a_removed_analysis_operation(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """Removing the analysis operation from the served document must fail comparison.

    Break: remove GET /runs/{run_id}/analysis from the FastAPI app.
    Red: the route is absent from the served table; the committed table still
    has it; the comparison fails.
    """
    import copy

    mutated = copy.deepcopy(served)
    del mutated["paths"]["/runs/{run_id}/analysis"]

    assert _route_table(mutated) != _route_table(committed)


@pytest.mark.substrate
def test_the_comparison_notices_a_removed_503_on_start_run(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """Removing 503 from POST /runs in the served document must fail the response check.

    Break: remove responses[503] from the POST /runs decorator in main.py.
    Red: the served route table has no 503 in responses; the committed table
    still does; the per-route response assertion fires.
    """
    import copy

    mutated = copy.deepcopy(served)
    mutated["paths"]["/runs"]["post"]["responses"].pop("503", None)

    committed_table = _route_table(committed)
    served_table = _route_table(mutated)
    assert committed_table["POST /runs"]["responses"] != served_table["POST /runs"]["responses"]


@pytest.mark.substrate
def test_the_comparison_notices_a_renamed_analysis_operation_id(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """Renaming the analysis operationId must fail the comparison.

    Break: change operation_id='read_analysis' to something else in main.py.
    Red: the served operationId does not match the committed operationId.
    """
    import copy

    mutated = copy.deepcopy(served)
    mutated["paths"]["/runs/{run_id}/analysis"]["get"]["operationId"] = "get_analysis"

    assert _route_table(mutated) != _route_table(committed)


# ---------------------------------------------------------------------------
# Schema-level agreement helpers (AC-0414, AC-0415)
#
# The existing ``_route_table`` comparison is deliberately narrow: it proves
# that the served and committed contracts agree on the route inventory a
# consumer depends on (operationId, parameters, requestBodyRequired, response
# status codes).  It excludes schema details by design, so a route with a
# correctly declared set of status codes but a wrong or empty response schema
# passes that check undetected.
#
# The helpers below extend the comparison to cover the analysis slice's schema
# contract: the typed 200 response body, the AnalysisRequest field set, the
# x-spec link, and the response set on the read_analysis operation.
#
# ``_deref`` resolves JSON Pointer-style ``$ref`` values locally within one
# document.  ``_normalize_schema`` strips auto-generated (``title``) and
# documentation-only (``description``, ``x-spec``) keys so that the YAML and
# Pydantic-generated schemas can be compared on their structural semantics
# without requiring every title or description to appear in both.
# ---------------------------------------------------------------------------


def _deref(document: dict[str, Any], schema: Any) -> Any:
    """Recursively resolve all ``$ref`` values within *schema* against *document*.

    Only local JSON Pointer references (``#/...``) are supported; the schemas
    in this project never use remote references.  The resolution is eager and
    recursive, so the result contains no ``$ref`` values.
    """
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = str(schema["$ref"])
            assert ref.startswith("#/"), f"only local JSON Pointer refs supported: {ref!r}"
            parts = ref[2:].split("/")
            target: Any = document
            for part in parts:
                target = target[part]
            return _deref(document, target)
        return {k: _deref(document, v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_deref(document, item) for item in schema]
    return schema


_SCHEMA_STRIP_KEYS: frozenset[str] = frozenset({"title", "description", "x-spec"})


def _normalize_schema(schema: Any) -> Any:
    """Strip documentation-only keys from *schema* for semantic comparison.

    Removed keys:
    - ``title``: auto-generated by Pydantic from class and field names; the
      YAML omits it.
    - ``description``: narrative documentation; not enforced by validators,
      so a mismatch is not a behavioural difference.
    - ``x-spec``: custom OpenAPI extension; compared separately via
      ``_analysis_schema_view``.
    """
    if isinstance(schema, dict):
        return {
            k: _normalize_schema(v) for k, v in schema.items() if k not in _SCHEMA_STRIP_KEYS
        }
    if isinstance(schema, list):
        return [_normalize_schema(item) for item in schema]
    return schema


def _analysis_schema_view(document: dict[str, Any]) -> dict[str, Any]:
    """Extract the analysis-slice facts from *document* for cross-document comparison.

    Returns a dict covering:
    - ``x-spec`` on the read_analysis operation
    - The sorted list of response status codes on read_analysis
    - The fully resolved and normalised 200 response schema (PublishedAnalysis)
    - The fully resolved and normalised AnalysisRequest schema

    Missing paths or schemas return empty / None so a mutated document that
    removes an element produces a distinct view rather than raising an error.
    """
    schemas = document.get("components", {}).get("schemas", {})
    paths = document.get("paths", {})
    read_op = paths.get("/runs/{run_id}/analysis", {}).get("get", {})

    read_200_raw: Any = (
        read_op.get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    ar_raw = schemas.get("AnalysisRequest", {})
    start_op = paths.get("/runs", {}).get("post", {})
    start_analysis_field = (
        schemas.get("StartRunRequest", {}).get("properties", {}).get("analysis", {})
    )
    start_503_x_spec = start_op.get("responses", {}).get("503", {}).get("x-spec")

    # Strip the x-spec value: YAML ``>`` block scalars add a trailing newline
    # that plain Python strings do not carry, so normalise both sides.
    x_spec_raw = read_op.get("x-spec")
    x_spec = x_spec_raw.strip() if isinstance(x_spec_raw, str) else x_spec_raw

    return {
        "read_analysis_x_spec": x_spec,
        "read_analysis_responses": sorted(read_op.get("responses", {}).keys()),
        "read_analysis_200_schema": _normalize_schema(_deref(document, read_200_raw)),
        "analysis_request_schema": _normalize_schema(_deref(document, ar_raw)),
        "start_run_analysis_field": _normalize_schema(_deref(document, start_analysis_field)),
        "start_run_responses": sorted(start_op.get("responses", {}).keys()),
        "start_run_503_x_spec": (
            start_503_x_spec.strip() if isinstance(start_503_x_spec, str) else start_503_x_spec
        ),
    }


# ---------------------------------------------------------------------------
# Main schema agreement test — requires a running server
# ---------------------------------------------------------------------------


@pytest.mark.substrate
def test_the_analysis_schema_view_matches_committed(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """The served and committed schemas agree on the analysis slice.

    Covers the 200 response schema (PublishedAnalysis, fully resolved),
    the AnalysisRequest schema, the x-spec link, and the response set.

    Break: change any nested property, remove x-spec, or alter any response
    code on the served side. Red: this assertion fails immediately.
    """
    assert _analysis_schema_view(served) == _analysis_schema_view(committed)


# ---------------------------------------------------------------------------
# Offline mutation tests (committed-side)
#
# Each test mutates a copy of the *committed* document and asserts that
# ``_analysis_schema_view`` produces a different result for the mutated copy
# versus the original.  This proves the view function is sensitive to that
# element, which in turn proves that the substrate agreement test above would
# fail if either side made the equivalent change.
# ---------------------------------------------------------------------------


def test_analysis_view_notices_removed_analysis_operation(
    committed: dict[str, Any],
) -> None:
    """Removing the analysis operation changes the view.

    Break: remove GET /runs/{run_id}/analysis from the committed contract.
    Red: this assertion fails (offline gate).
    """
    import copy

    mutated = copy.deepcopy(committed)
    del mutated["paths"]["/runs/{run_id}/analysis"]
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


def test_analysis_view_notices_removed_request_field(
    committed: dict[str, Any],
) -> None:
    """Removing snapshot_ref from AnalysisRequest changes the view.

    Break: remove snapshot_ref from AnalysisRequest in the committed contract.
    Red: this assertion fails (offline gate).
    """
    import copy

    mutated = copy.deepcopy(committed)
    ar = mutated["components"]["schemas"]["AnalysisRequest"]
    del ar["properties"]["snapshot_ref"]
    ar["required"] = [r for r in ar["required"] if r != "snapshot_ref"]
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


def test_analysis_view_notices_removed_artifact_property(
    committed: dict[str, Any],
) -> None:
    """Removing memo from PublishedAnalysis changes the view.

    The 200 schema is resolved through the $ref, so a missing nested property
    is visible after dereferencing even though the ref itself is unchanged.

    Break: remove the memo property from PublishedAnalysis in the committed contract.
    Red: this assertion fails (offline gate).
    """
    import copy

    mutated = copy.deepcopy(committed)
    pa = mutated["components"]["schemas"]["PublishedAnalysis"]
    del pa["properties"]["memo"]
    pa["required"] = [r for r in pa["required"] if r != "memo"]
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


def test_analysis_view_notices_removed_200_response(
    committed: dict[str, Any],
) -> None:
    """Removing the 200 response from read_analysis changes the view.

    Break: remove the 200 response from GET /runs/{run_id}/analysis in the
    committed contract.
    Red: this assertion fails (offline gate).
    """
    import copy

    mutated = copy.deepcopy(committed)
    mutated["paths"]["/runs/{run_id}/analysis"]["get"]["responses"].pop("200", None)
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


def test_analysis_view_notices_removed_409_response(
    committed: dict[str, Any],
) -> None:
    """Removing the 409 response from read_analysis changes the view.

    Break: remove the 409 response from GET /runs/{run_id}/analysis in the
    committed contract.
    Red: this assertion fails (offline gate).
    """
    import copy

    mutated = copy.deepcopy(committed)
    mutated["paths"]["/runs/{run_id}/analysis"]["get"]["responses"].pop("409", None)
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


def test_analysis_view_notices_removed_x_spec(
    committed: dict[str, Any],
) -> None:
    """Removing x-spec from the read_analysis operation changes the view.

    Break: remove x-spec from GET /runs/{run_id}/analysis in the committed
    contract.
    Red: this assertion fails (offline gate).
    """
    import copy

    mutated = copy.deepcopy(committed)
    mutated["paths"]["/runs/{run_id}/analysis"]["get"].pop("x-spec", None)
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda d: d["components"]["schemas"]["StartRunRequest"]["properties"].pop(
                "analysis"
            ),
            id="analysis-field-removed",
        ),
        pytest.param(
            lambda d: d["components"]["schemas"]["StartRunRequest"]["properties"][
                "analysis"
            ].update({"anyOf": [{"$ref": "#/components/schemas/AnalysisRequest"}]}),
            id="analysis-field-not-nullable",
        ),
        pytest.param(
            lambda d: d["paths"]["/runs"]["post"]["responses"].pop("503"),
            id="start-run-503-removed",
        ),
        pytest.param(
            lambda d: d["paths"]["/runs"]["post"]["responses"]["503"].pop("x-spec"),
            id="start-run-503-x-spec-removed",
        ),
    ],
)
def test_analysis_view_notices_start_run_changes(
    committed: dict[str, Any], mutate: Any
) -> None:
    """Each start-run part of this slice's contract is in the compared view.

    Break: apply the named change to the committed contract.
    Red: the view no longer equals the unchanged contract's (offline gate).
    """
    import copy

    mutated = copy.deepcopy(committed)
    mutate(mutated)
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


# ---------------------------------------------------------------------------
# Substrate mutation tests (served-side)
#
# Mutate the *served* document to prove the real agreement test catches
# changes on the served side.
# ---------------------------------------------------------------------------


@pytest.mark.substrate
def test_analysis_view_notices_dropped_served_property(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """Dropping memo from the served PublishedAnalysis schema fails the comparison.

    Break: remove the memo field from the PublishedAnalysis Pydantic model in
    src/ced/api/models.py.
    Red: the served schema no longer has memo; the comparison against committed
    fails.
    """
    import copy

    mutated = copy.deepcopy(served)
    pa = mutated["components"]["schemas"]["PublishedAnalysis"]
    del pa["properties"]["memo"]
    pa["required"] = [r for r in pa["required"] if r != "memo"]
    assert _analysis_schema_view(mutated) != _analysis_schema_view(committed)


def test_the_published_attribution_bound_matches_the_model() -> None:
    """The one check that holds the contract's number and the model's in step.

    AC-0009 compares a route table and excludes `components.schemas` by design,
    so nothing there notices if these two drift — and two comments used to
    claim otherwise. This is deliberately *not* an extension of AC-0009:
    widening that criterion's artifact would change what a ratified acceptance
    criterion asserts, which is not this delivery's call.

    **It lives here, and that is the point of the move.** It was written in
    `test_start_and_read_a_run.py`, whose module-wide `substrate` mark meant
    the one check guarding against this drift never ran in the offline gate — a
    contributor could raise the constant, run the documented offline subset
    green, and ship a contract publishing the old bound. This file already
    refuses a module-wide mark for exactly that reason.
    """
    from ced.api.models import ATTRIBUTION_MAX_LENGTH, StartRunRequest

    published = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"][
        "StartRunRequest"
    ]["properties"]

    # **Both bounds are compared to what the field enforces, never to the
    # constant.** The maximum was compared to `ATTRIBUTION_MAX_LENGTH` — the
    # YAML against a module constant, which is the two-literals comparison this
    # check rejects for the minimum three lines down. The model merely
    # *references* that constant today, so giving a field its own literal
    # maximum left the published value equal to the constant and this check
    # green while the API accepted more than the contract promised.
    for field in ("principal", "agent_role"):
        model_field = StartRunRequest.model_fields[field]
        bounds = {type(meta).__name__: meta for meta in model_field.metadata}
        for kind, attribute, published_key in (
            ("MinLen", "min_length", "minLength"),
            ("MaxLen", "max_length", "maxLength"),
        ):
            # A missing bound is itself drift in a direction this check exists
            # to catch — the contract publishing a limit the model no longer
            # enforces. Reported rather than left to raise `KeyError` from a
            # bare lookup, which named neither the field nor the value.
            assert kind in bounds, (
                f"the model no longer enforces a {published_key} on {field}, "
                f"while the contract still publishes "
                f"{published[field].get(published_key)!r}; the field's bounds "
                f"are {sorted(bounds)}"
            )
            enforced = getattr(bounds[kind], attribute)
            # Symmetric to the guard above: the contract dropping a bound the
            # model still enforces is drift in the other direction, and it was
            # raising the bare `KeyError` the same commit removed on the model
            # side.
            assert published_key in published[field], (
                f"the contract no longer publishes a {published_key} for "
                f"{field}, while the model enforces {enforced}; the published "
                f"keys are {sorted(published[field])}"
            )
            assert published[field][published_key] == enforced, (
                f"{field}'s published {published_key} is "
                f"{published[field][published_key]} but the model enforces "
                f"{enforced}; a client trusting the contract would be told the "
                "wrong limit"
            )

    # The constant is still worth asserting, but as its own fact: that the
    # published value and the model agree is the drift this check exists for;
    # that both equal `ATTRIBUTION_MAX_LENGTH` is what keeps the named constant
    # meaningful to a reader.
    assert published["principal"]["maxLength"] == ATTRIBUTION_MAX_LENGTH, (
        f"the published maximum is {published['principal']['maxLength']} while "
        f"ATTRIBUTION_MAX_LENGTH is {ATTRIBUTION_MAX_LENGTH}; the constant no "
        "longer names the shipped bound"
    )
