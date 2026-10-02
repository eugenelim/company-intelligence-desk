"""Same-origin checks for state-changing API routes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from ced.api.main import app

from .conftest import Client

pytestmark = pytest.mark.substrate


def _request(
    api_server: Client,
    method: str,
    path: str,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> int:
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        api_server.base_url + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_foreign_origin_is_refused_on_every_state_change(api_server: Client) -> None:
    state_changing = sorted(
        f"{method} {route.path}"
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in {"POST", "PUT", "PATCH", "DELETE"}
    )
    assert state_changing == [
        "POST /runs",
        "POST /runs/{run_id}/steps/{step_id}/decision",
    ]

    payloads = {
        "POST /runs": ("/runs", {"principal": "operator", "agent_role": "coordinator"}),
        "POST /runs/{run_id}/steps/{step_id}/decision": (
            "/runs/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/steps/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/decision",
            {
                "suspension_seq": 1,
                "decisions": [{"call_id": "call-1", "granted": True}],
                "principal": "approver",
            },
        ),
    }
    for route in state_changing:
        path, payload = payloads[route]
        assert (
            _request(
                api_server,
                "POST",
                path,
                payload,
                headers={"Origin": "https://attacker.invalid"},
            )
            == 400
        ), route


def test_start_run_keeps_non_browser_absent_origin_policy(
    api_server: Client,
    clean_runs: None,
) -> None:
    assert (
        _request(
            api_server,
            "POST",
            "/runs",
            {"principal": "operator", "agent_role": "coordinator"},
        )
        == 201
    )
