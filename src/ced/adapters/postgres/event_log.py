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
    "MALFORMED_EVENT_TYPE_SQLSTATE",
    "MalformedEventType",
    "StepRunMismatch",
    "RunAlreadyTerminal",
    "append_policy_decision",
    "append_run_event",
    "append_step_event",
    "derived_idempotency_key",
    "read_events",
    "retry_on_deadlock",
    "start_run",
]

#: The private SQLSTATE `append_step_event` raises when a type fails the
#: canonical shape, matched by code rather than by a `psycopg` exception class
#: because the driver has no class for it.
#:
#: **Verified unoccupied, not reserved for us.** No PostgreSQL release
#: allocates class `CE` and psycopg's generated table carries none, so nothing
#: but that one `RAISE` produces this code — checked against PostgreSQL 17.11
#: and psycopg 3.3.6, and falsified by any future release claiming class `CE`.
#: An earlier version of this comment claimed the code sat "in Postgres's
#: user-defined range", which is wrong: the standard leaves classes beginning
#: `5`-`9` or `I`-`Z` implementation-defined, and `CE` is inside the `A`-`H`
#: band it reserves. That was the third ungrounded justification this one
#: refusal has carried, after `invalid_parameter_value` and
#: `invalid_text_representation` were each claimed exact and each found to
#: collide — so the ground stated here is a fact with a version attached and a
#: named way to be wrong, rather than a category.
MALFORMED_EVENT_TYPE_SQLSTATE = "CED01"

#: r7 § Event log: "Deadlock (40P01) is retried with backoff."
#:
#: **Three attempts sleep twice, for 200 ms in total.** `retry_on_deadlock`
#: sleeps only *between* attempts, so it reads indices 0 and 1 and never the
#: last element — the tuple is therefore exactly one element longer than the
#: attempt count, by construction rather than by accident. The comment here
#: used to claim "~350 ms in total, which is well inside the 200 ms
#: `deadlock_timeout`", which was false on every reading: the code's total is
#: 200 ms, the tuple's own sum is 500 ms, and neither is inside 200 ms.
#:
#: The bound that matters is not a comparison against `deadlock_timeout` — the
#: detector has already fired by the time a 40P01 reaches this code — but that
#: the total stays short enough not to hide a real ordering defect behind
#: patience. 200 ms does.
DEADLOCK_ATTEMPTS = 3
#: One sleep per gap between attempts, hence `DEADLOCK_ATTEMPTS - 1` values
#: read. Asserted rather than trusted, so a fourth attempt cannot silently
#: sleep off the end of the tuple nor a shortened tuple silently skip a sleep.
DEADLOCK_BACKOFF_SECONDS = (0.05, 0.15)
assert len(DEADLOCK_BACKOFF_SECONDS) == DEADLOCK_ATTEMPTS - 1


class Fenced(Exception):
    """The step does not hold a live lease at the epoch the caller named.

    **This covers more than a lease that moved on**, and the docstring used to
    name only that case. `fence_step` refuses four states through one
    `serialization_failure`: the epoch advanced, the step was never claimed
    (`lease_epoch` is `NOT NULL DEFAULT 0`, so epoch 0 matched a fresh row),
    the owner is null, and the lease has lapsed or been released. A worker
    losing its lease and an `app_policy` forging an append against a step no
    worker ever leased therefore arrive here identically, and the pool logs
    both as an ordinary abandon — so a forgery attempt is **not** observable at
    this boundary. Recorded rather than split: ADR-0005's confirmation signal
    is that the refusals occur, not that they are distinguishable, and giving
    each state its own type is a sibling spec's call once something reads them.

    Not a retryable condition. A fenced worker aborts without *additional*
    side effects; it may already have invoked a tool, and attribution is at the
    logical-invocation level with idempotency keys deduping re-execution.
    """


class StepRunMismatch(Exception):
    """The fenced step does not belong to the run being appended to.

    Distinct from `Fenced` on purpose. A fence loss means the lease moved on and
    the worker should abandon quietly; this means the *arguments* disagree, which
    is a caller defect or a forgery attempt, and it must not be retried or
    treated as an ordinary abandon.
    """


class MalformedEventType(Exception):
    """The event type is not a dotted run of lowercase ASCII alphanumerics.

    Refused by `append_step_event` rather than normalised away, because
    collapsing interior padding would manufacture a name the caller never
    sent. Covers an unenumerated invisible character, a homoglyph, interior
    padding, and the empty string a pure-padding argument trims down to.

    **Recognised by SQLSTATE `CED01`**, verified unoccupied by any PostgreSQL
    release or psycopg condition rather than drawn from a range reserved for
    private codes — see `MALFORMED_EVENT_TYPE_SQLSTATE`. It is the third code
    this refusal has had. `invalid_parameter_value` arrived as
    `StepRunMismatch`, because the adapter already mapped it. Its replacement
    `invalid_text_representation` was no better: 22P02 is what Postgres raises
    for any failed input cast on the same statement, so a non-UUID `run_id`
    surfaced to the caller as a complaint about the event type. A private code
    is the only spelling no other failure on that call can produce, which is
    what makes this mapping exact rather than merely distinct.
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
        except psycopg.errors.InvalidParameterValue as exc:
            raise StepRunMismatch(str(exc).splitlines()[0]) from exc
        except psycopg.errors.DatabaseError as exc:
            # **Last, and that ordering is load-bearing.** `psycopg` has no
            # class for a private SQLSTATE, so `CED01` arrives as a generic
            # `DatabaseError` and has to be matched by code. But every specific
            # handler above is a `DatabaseError` subclass, so putting this
            # clause before them would swallow their exceptions and re-raise
            # them past their own handlers — `StepRunMismatch` would stop being
            # raised at all. Anything that is not `CED01` re-raises untouched;
            # this must never become a catch-all for the family.
            if exc.sqlstate != MALFORMED_EVENT_TYPE_SQLSTATE:
                raise
            raise MalformedEventType(str(exc).splitlines()[0]) from exc

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
        except psycopg.errors.InvalidParameterValue as exc:
            raise StepRunMismatch(str(exc).splitlines()[0]) from exc

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
