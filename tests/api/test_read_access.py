"""Phase 1 direct-read posture for run evidence."""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from ced.api.main import run

from .conftest import Client

pytestmark = pytest.mark.substrate


def test_existing_runs_are_readable_without_run_owner(
    api_server: Client, clean_runs: None
) -> None:
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    assert api_server.get(f"/runs/{run_id}/events").status == 200
    request = urllib.request.Request(api_server.base_url + f"/runs/{run_id}/events/stream")
    with urllib.request.urlopen(request, timeout=2) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "text/event-stream"
        response.close()


def test_unknown_run_is_refused_for_page_and_stream(api_server: Client) -> None:
    """An unknown run is ``404`` on the page and the stream (AC-0338).

    The page's ``404`` carries the browser client, so the page can show the
    Unavailable outcome; ``tests/browser/test_run_page.py::
    test_missing_run_shows_unavailable`` observes that. The stream opens
    nothing.
    """
    missing = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    # A malformed id names no run either, so its page is the same 404.
    for run_id in (missing, "not-a-run-id"):
        page = urllib.request.Request(api_server.base_url + f"/runs/{run_id}")
        try:
            urllib.request.urlopen(page, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404, run_id
            assert exc.headers.get_content_type() == "text/html", run_id
        else:  # pragma: no cover
            pytest.fail(f"unknown run page answered 200 for {run_id!r}")
    request = urllib.request.Request(api_server.base_url + f"/runs/{missing}/events/stream")
    try:
        urllib.request.urlopen(request, timeout=2)
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    else:  # pragma: no cover
        pytest.fail("unknown run stream opened")


def test_api_default_bind_remains_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.delenv("CED_API_HOST", raising=False)
    monkeypatch.setattr("uvicorn.run", fake_run)

    run()

    assert captured["host"] == "127.0.0.1"
