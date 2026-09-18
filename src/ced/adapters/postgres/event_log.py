"""The two append paths, and the one transaction that starts a run.

Raw SQL through psycopg3, not an ORM. The claim query, the fenced append and
the lock ordering are the load-bearing mechanisms and were proven by Phase 0
spike P2 as specific statements; an ORM would put a query planner between the
plan and what was proven.

Every append is a function call, because no application role holds an insert on
`events` — revision 0002 revoked it. A caller that could bypass these functions
would be a caller that could forge a policy decision.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import psycopg

from ced.domain.events import (
    EventEnvelope,
    derived_idempotency_key,
)

__all__ = [
    "DEADLOCK_ATTEMPTS",
    "DEADLOCK_BACKOFF_SECONDS",
    "Fenced",
    "RunAlreadyTerminal",
    "append_policy_decision",
    "append_run_event",
    "append_step_event",
    "derived_idempotency_key",
    "read_events",
    "retry_on_deadlock",
    "start_run",
]

#: r7 § Event log: "Deadlock (40P01) is retried with backoff." Three attempts
#: over ~350 ms in total, which is well inside the 200 ms `deadlock_timeout`
#: the test container runs with and bounded enough not to hide a real ordering
#: defect behind patience.
DEADLOCK_ATTEMPTS = 3
DEADLOCK_BACKOFF_SECONDS = (0.05, 0.15, 0.30)


class Fenced(Exception):
    """The lease moved on: this worker no longer owns the step.

    Not a retryable condition. A fenced worker aborts without *additional*
    side effects; it may already have invoked a tool, and attribution is at the
    logical-invocation level with idempotency keys deduping re-execution.
    """


class RunAlreadyTerminal(Exception):
    """A run-lifecycle append arrived after the run reached a terminal state.

    A late cancel is a no-op by design. The guard exists because the stream
    closes on a terminal event, so an event committing after one would be
    invisible to every live client while present in the log.
    """


@dataclass(frozen=True)
class StartedRun:
    """What `start_run` committed, read back rather than assumed."""

    run_id: UUID
    step_id: UUID
    seq: int


def retry_on_deadlock[T](operation: Callable[[], T]) -> T:
    """Run `operation`, retrying only on 40P01.

    r7 § Event log: "Deadlock (40P01) is retried with backoff." Every append
    path below goes through this, so the retry is on the live path rather than
    being a helper nothing calls.

    A retry is safe because a deadlocked append rolled back whole: it consumed
    no sequence number, so the second attempt is the first append, not a
    duplicate.

    Scoped to deadlock deliberately. A serialization failure from the fence is
    *not* retried: it means the lease moved on, and retrying it would be a
    worker insisting on work it no longer owns.
    """
    last: psycopg.errors.DeadlockDetected | None = None
    for attempt in range(DEADLOCK_ATTEMPTS):
        try:
            return operation()
        except psycopg.errors.DeadlockDetected as exc:
            last = exc
            if attempt + 1 < DEADLOCK_ATTEMPTS:
                time.sleep(DEADLOCK_BACKOFF_SECONDS[attempt])
    assert last is not None
    raise last


def start_run(
    conn: psycopg.Connection,
    *,
    run_id: UUID,
    step_id: UUID,
    principal: str,
    agent_role: str,
) -> StartedRun:
    """Commit the run row, its coordinator step, and `run.requested` together.

    AC-0002. All three or none: a run row with no coordinator step is a run
    nothing will ever claim, and an event log that records a request for a run
    that does not exist is a log that cannot be reconstructed.

    There is no failure-injection parameter here. AC-0002's test forces the step
    insert to fail by passing a `step_id` that already exists, which is a real
    unique violation on the real statement — a switch in this signature would
    be a test-only disable path shipped inside the thing under test.
    """
    with conn.transaction():
        conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'requested')",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO steps (step_id, run_id, state, agent_role) "
            "VALUES (%s, %s, 'runnable', %s)",
            (step_id, run_id, agent_role),
        )
        row = conn.execute(
            "SELECT append_run_event(%s, 'run.requested', %s)",
            (run_id, principal),
        ).fetchone()
        assert row is not None
        return StartedRun(run_id=run_id, step_id=step_id, seq=row[0])


def append_step_event(
    conn: psycopg.Connection,
    *,
    run_id: UUID,
    step_id: UUID,
    lease_epoch: int,
    type: str,
    principal: str,
    agent_role: str | None = None,
    payload_ref: str | None = None,
    idempotency_key: str | None = None,
) -> int:
    """The worker path: fenced on `lease_epoch`. Returns the allocated `seq`."""

    def call() -> int:
        try:
            with conn.transaction():
                row = conn.execute(
                    "SELECT append_step_event(%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        run_id,
                        step_id,
                        lease_epoch,
                        type,
                        principal,
                        agent_role,
                        payload_ref,
                        idempotency_key,
                    ),
                ).fetchone()
                assert row is not None
                return int(row[0])
        except psycopg.errors.SerializationFailure as exc:
            raise Fenced(str(exc).splitlines()[0]) from exc

    return retry_on_deadlock(call)


def append_run_event(
    conn: psycopg.Connection,
    *,
    run_id: UUID,
    type: str,
    principal: str,
    payload_ref: str | None = None,
) -> int:
    """The run-lifecycle path: unfenced, `step_id` null, two types only."""

    def call() -> int:
        try:
            with conn.transaction():
                row = conn.execute(
                    "SELECT append_run_event(%s, %s, %s, %s)",
                    (run_id, type, principal, payload_ref),
                ).fetchone()
                assert row is not None
                return int(row[0])
        except psycopg.errors.SerializationFailure as exc:
            raise RunAlreadyTerminal(str(exc).splitlines()[0]) from exc

    return retry_on_deadlock(call)


def append_policy_decision(
    conn: psycopg.Connection,
    *,
    run_id: UUID,
    step_id: UUID,
    lease_epoch: int,
    principal: str,
    agent_role: str | None = None,
    payload_ref: str | None = None,
) -> int:
    """The policy path. `conn` must be the `policy` role, never the `worker`.

    The split separates **recording** authority, never **decision** authority:
    the worker still makes the call. It defends against a bug or partial
    compromise in any single write path forging a decision, and does not
    defend against full compromise of the worker process, which legitimately
    holds the credential that reaches the decision point.
    """

    def call() -> int:
        try:
            with conn.transaction():
                row = conn.execute(
                    "SELECT append_policy_decision(%s, %s, %s, %s, %s, %s)",
                    (run_id, step_id, lease_epoch, principal, agent_role, payload_ref),
                ).fetchone()
                assert row is not None
                return int(row[0])
        except psycopg.errors.SerializationFailure as exc:
            raise Fenced(str(exc).splitlines()[0]) from exc

    return retry_on_deadlock(call)


def read_events(
    conn: psycopg.Connection, *, run_id: UUID, after: int = 0, limit: int = 1000
) -> list[EventEnvelope]:
    """The cursor projection over committed events, in `seq` order."""
    rows = conn.execute(
        """
        SELECT schema_version, run_id, seq, type, principal, step_id,
               agent_role, payload_ref, idempotency_key
          FROM events
         WHERE run_id = %s AND seq > %s
         ORDER BY seq
         LIMIT %s
        """,
        (run_id, after, limit),
    ).fetchall()
    return [
        EventEnvelope(
            schema_version=row[0],
            run_id=row[1],
            seq=row[2],
            type=row[3],
            principal=row[4],
            step_id=row[5],
            agent_role=row[6],
            payload_ref=row[7],
            idempotency_key=row[8],
        )
        for row in rows
    ]
