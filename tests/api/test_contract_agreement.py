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

# NOT module-wide: `test_the_contract_file_describes_three_routes` reads only
# the committed YAML and is free in the offline gate. Only the checks that need
# a running server carry the mark.
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


def test_the_contract_file_describes_three_routes(
    committed: dict[str, Any],
) -> None:
    """Setup check, reported separately: it cannot fail on the application.

    It guards against the comparison below passing because both sides are
    empty, which is the way a contract test most often becomes decorative.
    """
    table = _route_table(committed)
    assert len(table) == 3, sorted(table)


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
