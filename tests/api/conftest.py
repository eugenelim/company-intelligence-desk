"""A real uvicorn server, driven over real HTTP.

AC-0001 asks for "the real ASGI app rather than a mocked router". This goes one
better and runs the app under its production server on a loopback port, then
drives it with `urllib.request` from the standard library. Two reasons, and the
second is the one that decided it:

  * It is stronger evidence. An in-process test client short-circuits the
    server, so it cannot catch a route the server declines to mount, a
    serialisation the JSON encoder refuses, or a status code the framework
    rewrites on the way out.
  * FastAPI's `TestClient` needs `httpx`, which the plan's § Dependencies &
    integration does not list. `urllib.request` is in the standard library.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Client:
    base_url: str

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Response:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                return Response(
                    status=response.status,
                    body=json.loads(raw) if raw else None,
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            # An error response is a result, not an exception: the status code
            # is what several of these tests assert.
            return Response(status=exc.code, body=json.loads(raw) if raw else None)

    def get(self, path: str) -> Response:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Response:
        return self.request("POST", path, payload)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def api_server(require_substrate: None) -> Iterator[Client]:
    """Start uvicorn in a thread and tear it down after the session."""
    port = _free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    client = Client(base_url=f"http://127.0.0.1:{port}")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:  # pragma: no cover — a start failure is a broken environment
        pytest.fail("uvicorn did not start within 30 s")

    try:
        yield client
    finally:
        server.should_exit = True
        thread.join(timeout=15)


@pytest.fixture
def clean_runs(owner_conn: psycopg.Connection) -> Iterator[None]:
    """Remove whatever the test created, whichever way the test ended."""
    before = {row[0] for row in owner_conn.execute("SELECT run_id FROM runs").fetchall()}
    try:
        yield
    finally:
        with psycopg.connect(database_url("migration")) as cleanup:
            with cleanup.transaction():
                rows = cleanup.execute("SELECT run_id FROM runs").fetchall()
                created = [row[0] for row in rows if row[0] not in before]
                for run_id in created:
                    cleanup.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
                    cleanup.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
                    cleanup.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
