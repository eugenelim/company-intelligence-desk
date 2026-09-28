"""End-to-end server fixture for the e2e test suite.

Starts a real uvicorn instance on a loopback port so the tests drive the
shipped ASGI app over the wire, not through a test client shim.  The same
pattern as ``tests/api/conftest.py``; reproduced here so each suite owns its
server and can set ``app.state`` independently.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import psycopg
import pytest
import uvicorn

from ced.adapters.postgres.dsn import database_url
from ced.api.main import app


@dataclass(frozen=True)
class Response:
    status: int
    body: Any


@dataclass
class E2EClient:
    """HTTP client for e2e tests; supports custom headers and JSON bodies."""

    base_url: str
    default_headers: dict[str, str] = field(default_factory=dict)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        all_headers: dict[str, str] = {}
        if data:
            all_headers["Content-Type"] = "application/json"
        all_headers.update(self.default_headers)
        if headers:
            all_headers.update(headers)
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=all_headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return Response(status=resp.status, body=json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return Response(status=exc.code, body=json.loads(raw) if raw else None)

    def get(self, path: str, **kw: Any) -> Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, payload: dict[str, Any], **kw: Any) -> Response:
        return self.request("POST", path, payload, **kw)

    @property
    def origin(self) -> str:
        """The Origin value this server expects for CSRF defence."""
        # base_url is http://127.0.0.1:<port> — that IS the origin.
        return self.base_url


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def e2e_server(require_substrate: None) -> Iterator[E2EClient]:
    """Start uvicorn in a thread for the e2e suite; tear it down after session."""
    # Reset to a known state before starting the server.
    app.state.require_distinct_approver = False

    port = _free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    client = E2EClient(base_url=f"http://127.0.0.1:{port}")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:  # pragma: no cover
        pytest.fail("e2e uvicorn did not start within 30 s")

    try:
        yield client
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.fixture
def clean_e2e_runs(require_substrate: None) -> Iterator[None]:
    """Remove runs the e2e test created, whichever way it ended."""
    with psycopg.connect(database_url("migration")) as conn:
        before = {row[0] for row in conn.execute("SELECT run_id FROM runs").fetchall()}
    try:
        yield
    finally:
        with psycopg.connect(database_url("migration")) as cleanup:
            with cleanup.transaction():
                rows = cleanup.execute("SELECT run_id FROM runs").fetchall()
                created = [r[0] for r in rows if r[0] not in before]
                for run_id in created:
                    cleanup.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
                    cleanup.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
                    cleanup.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@dataclass(frozen=True)
class SuspendedE2E:
    """A run+step in the suspended state, usable for decision-route tests."""

    run_id: uuid.UUID
    step_id: uuid.UUID
    suspension_seq: int
    initiating_principal: str


@pytest.fixture
def suspended_e2e(require_substrate: None, clean_e2e_runs: None) -> SuspendedE2E:
    """Insert a run + suspended step directly (no executor needed).

    Sets up exactly the state the approval decision route requires:
    a committed ``step.suspended`` event and ``awaiting_decision = true``.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    principal = "initiating-principal-e2e"
    with psycopg.connect(database_url("migration")) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'running', 0)",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO steps (step_id, run_id, state, awaiting_decision) "
                "VALUES (%s, %s, 'runnable', true)",
                (step_id, run_id),
            )
            # run.requested at seq=1
            conn.execute(
                "UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 1, 'run.requested', NULL, %s)",
                (run_id, principal),
            )
            # step.suspended at seq=2
            conn.execute(
                "UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 2, 'step.suspended', %s, %s)",
                (run_id, step_id, principal),
            )
    return SuspendedE2E(
        run_id=run_id,
        step_id=step_id,
        suspension_seq=2,
        initiating_principal=principal,
    )
