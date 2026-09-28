"""AC-0327: the projection driven over a committed run.

The plan's proof obligation (plan.md:240): "the projection is driven over a
committed run and the ledger records the mutation that reds it — dropping the
event append from any one committed transition must break the projection's
agreement with the snapshot."

This file is the substrate oracle. The pure-logic tests in
``tests/schema/test_ac_0327_run_state.py`` pin the projection function itself;
this file pins that the projection agrees with what the system actually commits.

Structure per committed transition:
1. Commit the event through the append path.
2. Read the event log from the database.
3. Project → assert the expected state.
4. Compare against ``GET /runs/{run_id}/snapshot`` — the two must agree.
5. Drop the transition's event from the read list, re-project, assert the
   projection disagrees with the snapshot (mutation proof: the snapshot still
   shows the committed state, but the projection without the event shows the
   prior state).

Dropping from the read list is not dropping from the database.  The mutation
targets the *input to the projection*, not the database itself, which is the
correct formulation: the projection is the oracle, and its sensitivity to each
committed event is what the proof establishes.  If the projection returned the
right state without that event, the test would still pass after deleting the
event from the log — a failure mode the projection oracle exists to prevent.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import read_events
from ced.domain.events import EventEnvelope
from ced.domain.run_state import project_run_state

from .conftest import E2EClient

pytestmark = pytest.mark.substrate


@pytest.fixture
def committed_run(require_substrate: None) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """A run in ``running`` state: run.requested + step.started committed."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    with psycopg.connect(database_url("migration")) as conn:
        with conn.transaction():
            # Start in requested; insert run.requested at seq=1.
            conn.execute(
                "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'requested', 0)",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
                "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
                "now() + interval '60 seconds')",
                (step_id, run_id),
            )
            conn.execute("UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s", (run_id,))
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 1, 'run.requested', NULL, 'fixture')",
                (run_id,),
            )
            # Commit step.started (moves run to running) at seq=2.
            conn.execute(
                "UPDATE runs SET next_seq = next_seq + 1, state = 'running' WHERE run_id = %s",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 2, 'step.started', %s, 'fixture')",
                (run_id, step_id),
            )
    try:
        yield run_id, step_id
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            with conn.transaction():
                conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
                conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
                conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def _read_log(run_id: uuid.UUID) -> list[EventEnvelope]:
    """Read all committed events for ``run_id`` in seq order."""
    with psycopg.connect(database_url("worker")) as conn:
        return read_events(conn, run_id=run_id)


def _snapshot_state(client: E2EClient, run_id: uuid.UUID) -> str:
    """Call ``GET /runs/{run_id}/snapshot`` and return the committed state."""
    resp = client.get(f"/runs/{run_id}/snapshot")
    assert resp.status == 200, f"snapshot returned {resp.status}: {resp.body}"
    return str(resp.body["state"])


# ── Edge 1: requested → running on step.started ─────────────────────────────


def test_projection_agrees_with_snapshot_after_step_started(
    e2e_server: E2EClient,
    committed_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0327 edge 1: projection from the committed log agrees with the snapshot.

    The ``committed_run`` fixture commits ``run.requested`` and ``step.started``.
    The projection over those events should yield ``running``, and
    ``GET /runs/{run_id}/snapshot`` must agree.
    """
    run_id, _ = committed_run
    events = _read_log(run_id)
    projected = project_run_state(events)
    assert projected[-1] == "running", (
        f"projection over committed log should be 'running', got {projected[-1]!r}; "
        f"full sequence: {projected!r}"
    )
    snapshot_state = _snapshot_state(e2e_server, run_id)
    assert snapshot_state == projected[-1], (
        f"snapshot state {snapshot_state!r} disagrees with projection {projected[-1]!r}"
    )


def test_dropping_step_started_event_disagrees_with_snapshot(
    e2e_server: E2EClient,
    committed_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0327 mutation proof for edge 1: drop step.started from the read list.

    The snapshot still shows 'running' (the event is committed in the DB).
    The projection over the truncated list shows 'requested'. The two disagree,
    proving the projection is sensitive to the step.started commit.

    If the projection returned 'running' without step.started in the input,
    this assertion would red — catching an implementation that ignores the event.
    """
    run_id, _ = committed_run
    all_events = _read_log(run_id)
    # Drop the step.started event from the input list.
    without_started = [e for e in all_events if e.type != "step.started"]
    projected_mutant = project_run_state(without_started)
    snapshot_state = _snapshot_state(e2e_server, run_id)

    # The snapshot still reports "running" (committed state).
    assert snapshot_state == "running", (
        f"snapshot should still be 'running' after mutation, got {snapshot_state!r}"
    )
    # The projection without step.started should disagree.
    assert projected_mutant[-1] != snapshot_state, (
        f"projection without step.started is {projected_mutant[-1]!r}, "
        f"same as snapshot {snapshot_state!r}; "
        "the projection is not sensitive to the step.started commit"
    )
    assert projected_mutant[-1] == "requested", (
        f"projection without step.started should be 'requested', got {projected_mutant[-1]!r}"
    )


# ── Edge 2: running → completed on run.completed ────────────────────────────


@pytest.fixture
def completed_run(
    require_substrate: None,
    committed_run: tuple[uuid.UUID, uuid.UUID],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Extend ``committed_run`` with a committed ``run.completed`` at seq=3."""
    run_id, step_id = committed_run
    with psycopg.connect(database_url("migration")) as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE runs SET next_seq = next_seq + 1, state = 'completed' "
                "WHERE run_id = %s",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 3, 'run.completed', NULL, 'fixture')",
                (run_id,),
            )
    return run_id, step_id


def test_projection_agrees_with_snapshot_after_run_completed(
    e2e_server: E2EClient,
    completed_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0327 edge 2: projection from the committed log agrees with the snapshot."""
    run_id, _ = completed_run
    events = _read_log(run_id)
    projected = project_run_state(events)
    assert projected[-1] == "completed", (
        f"projection should be 'completed', got {projected[-1]!r}; full sequence: {projected!r}"
    )
    snapshot_state = _snapshot_state(e2e_server, run_id)
    assert snapshot_state == projected[-1], (
        f"snapshot {snapshot_state!r} disagrees with projection {projected[-1]!r}"
    )


def test_dropping_run_completed_event_disagrees_with_snapshot(
    e2e_server: E2EClient,
    completed_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0327 mutation proof for edge 2: drop run.completed from the read list."""
    run_id, _ = completed_run
    all_events = _read_log(run_id)
    without_completed = [e for e in all_events if e.type != "run.completed"]
    projected_mutant = project_run_state(without_completed)
    snapshot_state = _snapshot_state(e2e_server, run_id)

    assert snapshot_state == "completed"
    assert projected_mutant[-1] != snapshot_state, (
        "projection without run.completed must disagree with the 'completed' snapshot"
    )
    assert projected_mutant[-1] == "running"


# ── Edge 3: running → failed on run.failed ──────────────────────────────────


@pytest.fixture
def failed_run(require_substrate: None) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """A run that went requested→running→failed: run.requested, step.started, run.failed."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    with psycopg.connect(database_url("migration")) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'requested', 0)",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
                "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
                "now() + interval '60 seconds')",
                (step_id, run_id),
            )
            # seq=1: run.requested
            conn.execute("UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s", (run_id,))
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 1, 'run.requested', NULL, 'fixture')",
                (run_id,),
            )
            # seq=2: step.started (requested→running)
            conn.execute(
                "UPDATE runs SET next_seq = next_seq + 1, state = 'running' WHERE run_id = %s",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 2, 'step.started', %s, 'fixture')",
                (run_id, step_id),
            )
            # seq=3: run.failed (running→failed)
            conn.execute(
                "UPDATE runs SET next_seq = next_seq + 1, state = 'failed' WHERE run_id = %s",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, 3, 'run.failed', NULL, 'fixture')",
                (run_id,),
            )
    try:
        yield run_id, step_id
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            with conn.transaction():
                conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
                conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
                conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def test_projection_agrees_with_snapshot_after_run_failed(
    e2e_server: E2EClient,
    failed_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0327 edge 3: projection from the committed log agrees with the snapshot."""
    run_id, _ = failed_run
    events = _read_log(run_id)
    projected = project_run_state(events)
    assert projected[-1] == "failed", (
        f"projection should be 'failed', got {projected[-1]!r}; full sequence: {projected!r}"
    )
    snapshot_state = _snapshot_state(e2e_server, run_id)
    assert snapshot_state == projected[-1], (
        f"snapshot {snapshot_state!r} disagrees with projection {projected[-1]!r}"
    )


def test_dropping_run_failed_event_disagrees_with_snapshot(
    e2e_server: E2EClient,
    failed_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0327 mutation proof for edge 3: drop run.failed from the read list."""
    run_id, _ = failed_run
    all_events = _read_log(run_id)
    without_failed = [e for e in all_events if e.type != "run.failed"]
    projected_mutant = project_run_state(without_failed)
    snapshot_state = _snapshot_state(e2e_server, run_id)

    assert snapshot_state == "failed"
    assert projected_mutant[-1] != snapshot_state, (
        "projection without run.failed must disagree with the 'failed' snapshot"
    )
    assert projected_mutant[-1] == "running"
