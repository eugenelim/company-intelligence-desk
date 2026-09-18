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

pytestmark = pytest.mark.substrate

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


def test_the_served_routes_match_the_committed_contract(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """AC-0009."""
    assert _route_table(served) == _route_table(committed)


def test_the_documents_agree_on_title_and_version(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """A consumer pins the version; a silent bump is a silent breaking change."""
    assert served["info"]["title"] == committed["info"]["title"]
    assert served["info"]["version"] == committed["info"]["version"]


def test_the_documents_declare_the_same_openapi_major_version(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    served_major = served["openapi"].split(".")[0]
    committed_major = committed["openapi"].split(".")[0]
    assert served_major == committed_major


def test_the_comparison_notices_a_removed_route(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """The check, shown failing. A contract test never seen failing is not one.

    A deliberately mutated copy of the served document must not compare equal.
    Mutating the copy rather than the application keeps the mutation out of the
    shipped code — the same reason AC-0216's mutation evidence is produced by
    patching in the test process.
    """
    mutated = {**served, "paths": {**served["paths"]}}
    mutated["paths"].pop("/runs/{run_id}/snapshot")

    assert _route_table(mutated) != _route_table(committed)


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


def test_the_comparison_notices_a_renamed_operation_id(
    committed: dict[str, Any], served: dict[str, Any]
) -> None:
    """The name generated clients call by."""
    import copy

    mutated = copy.deepcopy(served)
    mutated["paths"]["/runs"]["post"]["operationId"] = "create_run"

    assert _route_table(mutated) != _route_table(committed)


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
