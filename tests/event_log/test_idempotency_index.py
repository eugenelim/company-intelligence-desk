"""AC-0006 — a duplicate derived idempotency key is refused by the index.

The SQL-level half only. The *behavioural* half — a duplicate terminating the
step — is `walking-skeleton-policy-decision-point`'s AC-0212, which gives the
step-event toolset its append behaviour. r7 change 2's disposition routes it to
the spec that owns that toolset, and this suite stops at the index.

**The raw `psycopg.errors.UniqueViolation` asserted below is load-bearing for
both.** The adapter deliberately does not remap it, so this criterion observes
the index and the toolset one layer up catches the same exception to decide the
duplicate. Remapping it would move this observation rather than add one.
"""

from __future__ import annotations

import psycopg
import pytest

from ced.adapters.postgres import event_log
from ced.domain.events import TOOL_INVOKED, derived_idempotency_key

from .conftest import LeasedStep, next_seq_of, sequence_of

pytestmark = pytest.mark.substrate


def test_a_second_tool_invoked_with_the_same_key_is_refused(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """AC-0006 — the second append raises a unique violation."""
    key = derived_idempotency_key(leased_step.run_id, leased_step.step_id, "toolu_01example")

    first = event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type=TOOL_INVOKED,
        principal="worker-1",
        idempotency_key=key,
    )
    assert first == 1

    with pytest.raises(psycopg.errors.UniqueViolation):
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=TOOL_INVOKED,
            principal="worker-1",
            idempotency_key=key,
        )

    # The refused append consumed no sequence number either: the unique
    # violation aborts the same transaction that bumped `next_seq`.
    assert sequence_of(owner_conn, leased_step.run_id) == [1]
    assert next_seq_of(owner_conn, leased_step.run_id) == 1


def test_the_index_is_partial_so_other_types_are_unconstrained(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """A full unique index would refuse two step events carrying no key.

    Every other type leaves the column null. Postgres treats nulls as distinct,
    so a non-partial index would still admit them — but it would also refuse a
    second event of a *different* type that happened to carry the same key,
    which is not what r7 change 2 asks for.
    """
    key = derived_idempotency_key(leased_step.run_id, leased_step.step_id, "toolu_01example")

    event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type=TOOL_INVOKED,
        principal="worker-1",
        idempotency_key=key,
    )
    # Same key, different type: outside the index's predicate, so admitted.
    seq = event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type="tool.returned",
        principal="worker-1",
        idempotency_key=key,
    )
    assert seq == 2


def test_several_keyless_events_are_admitted(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """The common case must not be caught by the index.

    Asserts the allocated sequence numbers, not merely the absence of an
    exception. It asserted nothing, so a path that admitted the events while
    allocating no number — the hole `runs.next_seq` exists to prevent — would
    have stayed green.
    """
    allocated = [
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type="step.progress",
            principal="worker-1",
        )
        for _ in range(3)
    ]

    assert allocated == [1, 2, 3]


def test_the_same_key_in_a_different_run_is_admitted(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The index is scoped to `(run_id, idempotency_key)`, not to the key."""
    import uuid

    other_run, other_step = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (other_run,))
        # A *live, owned* lease. The fence requires both since ADR-0005: a
        # `leased` row with no owner and no expiry is no longer appendable,
        # which is the point of that decision.
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() + interval '60 seconds')",
            (other_step, other_run),
        )
    try:
        # A literal, shared across both runs, rather than a derived key —
        # which by construction differs per run. The index's scoping is the
        # claim, so the key has to be held constant to test it.
        shared = "0" * 64

        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=TOOL_INVOKED,
            principal="worker-1",
            idempotency_key=shared,
        )
        assert (
            event_log.append_step_event(
                worker_conn,
                run_id=other_run,
                step_id=other_step,
                lease_epoch=1,
                type=TOOL_INVOKED,
                principal="worker-1",
                idempotency_key=shared,
            )
            == 1
        )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (other_run,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (other_run,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (other_run,))


def test_the_derived_key_is_stable_and_call_scoped() -> None:
    """A pure-function check on the derivation, with its limit asserted."""
    import uuid

    run, step = uuid.uuid4(), uuid.uuid4()

    # Stable across a resume from the same history: same inputs, same key.
    assert derived_idempotency_key(run, step, "toolu_1") == derived_idempotency_key(
        run, step, "toolu_1"
    )
    # And NOT stable across a re-planned retry: a new model turn mints a new
    # tool_call_id, so the second invocation is a different logical call. This
    # is the recorded limit, asserted rather than left as prose.
    assert derived_idempotency_key(run, step, "toolu_1") != derived_idempotency_key(
        run, step, "toolu_2"
    )
    assert derived_idempotency_key(run, step, "toolu_1") != derived_idempotency_key(
        run, uuid.uuid4(), "toolu_1"
    )
