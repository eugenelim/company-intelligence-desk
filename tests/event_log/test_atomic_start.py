"""AC-0002 — the run row, the coordinator step and `run.requested` are atomic.

The failure is injected as a *real* unique violation on the real statement: the
test passes a `step_id` that already exists. No production code holds a
failure-injection switch, and no statement is patched out, so what is asserted
is the transaction rather than the mock.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from uuid import UUID

import psycopg
import pytest

from ced.adapters.postgres import event_log

pytestmark = pytest.mark.substrate


@pytest.fixture
def occupied_step_id(owner_conn: psycopg.Connection) -> Iterator[UUID]:
    """A `step_id` that is already taken, on a decoy run."""
    decoy_run, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (decoy_run,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id) VALUES (%s, %s)",
            (step_id, decoy_run),
        )
    try:
        yield step_id
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (decoy_run,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (decoy_run,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (decoy_run,))


def _counts(conn: psycopg.Connection, run_id: UUID) -> tuple[int, int, int]:
    """Return `(runs, steps, events)` row counts for one run."""
    row = conn.execute(
        """
        SELECT (SELECT count(*) FROM runs   WHERE run_id = %s),
               (SELECT count(*) FROM steps  WHERE run_id = %s),
               (SELECT count(*) FROM events WHERE run_id = %s)
        """,
        (run_id, run_id, run_id),
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def test_all_three_rows_commit_together(
    api_conn: psycopg.Connection, owner_conn: psycopg.Connection
) -> None:
    """The happy path, so the negative case below is not vacuously green."""
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    try:
        started = event_log.start_run(
            api_conn,
            run_id=run_id,
            step_id=step_id,
            principal="operator",
            agent_role="coordinator",
        )

        assert started.seq == 1
        assert _counts(owner_conn, run_id) == (1, 1, 1)

        events = event_log.read_events(owner_conn, run_id=run_id)
        assert [e.type for e in events] == ["run.requested"]
        # The run-lifecycle path leaves both null, per the r7 envelope.
        assert events[0].step_id is None
        assert events[0].agent_role is None
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def test_a_failed_step_insert_leaves_no_run_no_step_and_no_event(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    occupied_step_id: UUID,
) -> None:
    """AC-0002 — with the step insert forced to fail, all three are absent."""
    run_id = uuid.uuid4()

    with pytest.raises(psycopg.errors.UniqueViolation):
        event_log.start_run(
            api_conn,
            run_id=run_id,
            step_id=occupied_step_id,
            principal="operator",
            agent_role="coordinator",
        )

    assert _counts(owner_conn, run_id) == (0, 0, 0)


def test_the_connection_is_usable_after_the_rolled_back_start(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    occupied_step_id: UUID,
) -> None:
    """A rollback that poisons the connection would hide the next failure."""
    with pytest.raises(psycopg.errors.UniqueViolation):
        event_log.start_run(
            api_conn,
            run_id=uuid.uuid4(),
            step_id=occupied_step_id,
            principal="operator",
            agent_role="coordinator",
        )

    assert api_conn.execute("SELECT 1").fetchone() == (1,)
