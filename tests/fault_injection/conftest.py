"""Helpers for driving real worker containers.

Nothing here is compressed. AC-0010 and AC-0011 are measured at r7's timings —
TTL 60 s, heartbeat 20 s, poll 30 s — because a compressed run would
demonstrate the mechanism and not the number, and the number is the criterion.
That makes this the slow suite; it is marked `substrate` and skips cleanly when
the stack is not up.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from ced.worker.pool import CRITERION_REACQUISITION_BOUND_SECONDS, POLL_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "deploy" / "compose.yaml"

WORKER_CONTAINERS = ("deploy-worker-a-1", "deploy-worker-b-1")

#: AC-0010's bound, imported so the number has one home rather than two.
WORST_CASE_SECONDS = CRITERION_REACQUISITION_BOUND_SECONDS

#: AC-0011's bound: "within one poll interval".
DRAIN_BOUND_SECONDS = POLL_SECONDS

#: Headroom for container scheduling, applied to the *helper's* timeout and
#: never to an assertion. Review round 1 found AC-0011 asserting
#: `elapsed <= POLL_SECONDS + OBSERVATION_MARGIN_SECONDS` while the helper
#: failed at exactly that value — so the assertion was satisfied by every
#: value the helper could return, and the criterion's own 30 s was asserted
#: nowhere. Every wait below now uses a timeout strictly greater than the bound
#: it asserts, so the assertion is the thing that reds.
OBSERVATION_MARGIN_SECONDS = 20


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=False)


def container_is_running(name: str) -> bool:
    result = docker("inspect", "-f", "{{.State.Running}}", name)
    return result.returncode == 0 and result.stdout.strip() == "true"


@pytest.fixture
def running_workers(require_substrate: None) -> list[str]:
    """Skip with an actionable message when the worker containers are absent.

    Per test, not per module. It was module-scoped, so a worker that failed to
    restart after an earlier test left every later one waiting out its full
    timeout for an owner change that one worker cannot produce — reported as a
    reacquisition failure two tests away from its cause.
    """
    missing = [name for name in WORKER_CONTAINERS if not container_is_running(name)]
    if missing:
        pytest.skip(
            f"worker containers not running: {missing}. Run "
            f"`docker-compose -f {COMPOSE_FILE.relative_to(REPO_ROOT)} up -d --build`"
        )
    return list(WORKER_CONTAINERS)


@dataclass
class StepObservation:
    owner: str | None
    epoch: int
    state: str
    lease_expires_at: object


def observe(conn: psycopg.Connection, step_id: UUID) -> StepObservation:
    row = conn.execute(
        "SELECT owner, lease_epoch, state, lease_expires_at FROM steps WHERE step_id = %s",
        (step_id,),
    ).fetchone()
    assert row is not None, f"step {step_id} vanished"
    return StepObservation(
        owner=row[0], epoch=int(row[1]), state=row[2], lease_expires_at=row[3]
    )


def wait_until_claimed(
    conn: psycopg.Connection, step_id: UUID, timeout: float
) -> StepObservation:
    """Poll until some worker owns the step, or fail with what was seen."""
    deadline = time.monotonic() + timeout
    last = observe(conn, step_id)
    while time.monotonic() < deadline:
        last = observe(conn, step_id)
        if last.owner is not None and last.state == "leased":
            return last
        time.sleep(0.5)
    pytest.fail(f"step {step_id} was not claimed within {timeout} s; last saw {last}")


def wait_for_reacquisition(
    conn: psycopg.Connection,
    step_id: UUID,
    previous_owner: str,
    timeout: float,
    started: float | None = None,
) -> tuple[StepObservation, float]:
    """Poll until a *different* worker owns the step. Returns it and the wait.

    Wall clock read from this side, and the ownership change read from the
    database — not from a log line. A log line records what a worker believed;
    the `steps` row records what actually happened.

    `started` lets the caller begin the interval **before** the fault is
    injected. AC-0011 needs that: `docker stop` is synchronous with container
    exit — measured at 0.16 s with the container already gone — so a clock
    started on entry here begins *after* the worker has detected `SIGTERM`,
    expired its lease and exited, and `elapsed` would contain only the
    survivor's poll phase. The drain would then be unmeasured, and the
    assertion insensitive to it.
    """
    started = time.monotonic() if started is None else started
    deadline = started + timeout
    last = observe(conn, step_id)
    while time.monotonic() < deadline:
        last = observe(conn, step_id)
        if last.owner is not None and last.owner != previous_owner:
            return last, time.monotonic() - started
        time.sleep(0.5)
    pytest.fail(
        f"step {step_id} was not reacquired within {timeout} s "
        f"(still owned by {last.owner!r}); last saw {last}"
    )


@pytest.fixture
def pending_step(owner_conn: psycopg.Connection) -> Iterator[tuple[UUID, UUID]]:
    """A run with one runnable step, cleaned up whichever way the test ends."""
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, agent_role) "
            "VALUES (%s, %s, 'runnable', 'coordinator')",
            (step_id, run_id),
        )
    try:
        yield run_id, step_id
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
