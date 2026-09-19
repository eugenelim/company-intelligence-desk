"""AC-0003 and AC-0004 — density under concurrency, and rollback leaving no hole.

Both are stated as properties rather than examples, because density under
concurrency is a property of interleavings no fixed case covers. The shape is
Phase 0 spike P2's, carried forward — eight concurrent writers, 25 appends each
— and run against the schema this delivery ships rather than the spike's own.

**What these results do not establish.** The container runs with
`deadlock_timeout` at 200 ms, well below the 1 s default, so deadlocks surface
faster here than in production; and it is a local container, not RDS or Aurora,
so connection pooling and failover behaviour are untested. That qualification
travels with every number below, exactly as `spikes/README.md` records it for
Phase 0.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import UUID

import psycopg
import pytest

from ced.adapters.postgres import event_log
from ced.adapters.postgres.dsn import database_url

from .conftest import next_seq_of, sequence_of

pytestmark = pytest.mark.substrate

#: Spike P2's shape exactly: 8 x 25 = 200 events.
WRITERS = 8
APPENDS_PER_WRITER = 25


@dataclass
class _WriterOutcome:
    deadlocks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@pytest.fixture
def run_with_one_step_per_writer(
    owner_conn: psycopg.Connection,
) -> Iterator[tuple[UUID, list[UUID]]]:
    """One run, and one step leased at epoch 1 for each concurrent writer."""
    run_id = uuid.uuid4()
    step_ids = [uuid.uuid4() for _ in range(WRITERS)]
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        for step_id in step_ids:
            owner_conn.execute(
                "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
                "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
                "now() + interval '60 seconds')",
                (step_id, run_id),
            )
    try:
        yield run_id, step_ids
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def _append_many(run_id: UUID, step_id: UUID, label: str) -> _WriterOutcome:
    """Append `APPENDS_PER_WRITER` step events, and also claim a step.

    The claim half is spike P2's too, and it is what makes this a lock-ordering
    test rather than an append test: the claim takes a `steps` row lock and the
    append takes `steps` then `runs`, so both paths contend on the same rows in
    the designed order.
    """
    outcome = _WriterOutcome()
    with psycopg.connect(database_url("worker")) as conn:
        for _ in range(APPENDS_PER_WRITER):
            try:
                event_log.append_step_event(
                    conn,
                    run_id=run_id,
                    step_id=step_id,
                    lease_epoch=1,
                    type="step.progress",
                    principal=label,
                )
                with conn.transaction():
                    conn.execute(
                        "SELECT step_id FROM steps WHERE state = 'leased' "
                        "AND run_id = %s ORDER BY step_id "
                        "FOR UPDATE SKIP LOCKED LIMIT 1",
                        (run_id,),
                    ).fetchone()
            except psycopg.errors.DeadlockDetected as exc:
                outcome.deadlocks.append(str(exc).splitlines()[0][:100])
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                outcome.errors.append(f"{type(exc).__name__}: {exc!s:.100}")
    return outcome


def test_the_sequence_is_dense_from_one_under_eight_concurrent_writers(
    owner_conn: psycopg.Connection,
    run_with_one_step_per_writer: tuple[UUID, list[UUID]],
) -> None:
    """AC-0003 — every `seq` dense from 1, no duplicates, no gaps."""
    run_id, step_ids = run_with_one_step_per_writer
    outcomes: list[_WriterOutcome] = []

    threads = [
        threading.Thread(
            target=lambda i=i: outcomes.append(_append_many(run_id, step_ids[i], f"w{i}"))
        )
        for i in range(WRITERS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    errors = [e for o in outcomes for e in o.errors]
    deadlocks = [d for o in outcomes for d in o.deadlocks]
    assert errors == [], f"unexpected errors: {errors[:3]}"
    # **What this assertion now shows: no deadlock survived the retry** under
    # the designed order. `retry_on_deadlock` sits inside `append_step_event`,
    # so a 40P01 reaches this list only after three attempts all deadlock. That
    # is weaker than "the designed order does not deadlock", and the comment
    # used to claim the stronger thing. The ordering claim itself is carried by
    # `test_lock_ordering.py`, whose contenders take raw row locks below the
    # retry — including the mixed-order case, which is shown deadlocking.
    assert deadlocks == [], f"deadlocks survived the retry: {deadlocks[:3]}"

    seqs = sequence_of(owner_conn, run_id)
    expected = WRITERS * APPENDS_PER_WRITER
    assert len(seqs) == expected
    assert seqs == list(range(1, expected + 1)), "sequence is not dense from 1"
    assert len(set(seqs)) == len(seqs), "duplicate seq values"
    assert next_seq_of(owner_conn, run_id) == expected


def test_a_stale_epoch_rolls_back_and_consumes_no_sequence_number(
    owner_conn: psycopg.Connection, worker_conn: psycopg.Connection
) -> None:
    """AC-0004 — the rolled-back attempt leaves the sequence dense.

    This is the whole reason `next_seq` is a row UPDATE rather than a
    `bigserial`: rollback undoes the increment, where a `bigserial` allocation
    would survive it and leave a hole a reader skips forever.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 7, "
            "now() + interval '60 seconds')",
            (step_id, run_id),
        )
    try:
        for _ in range(3):
            event_log.append_step_event(
                worker_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=7,
                type="step.progress",
                principal="worker-1",
            )
        assert sequence_of(owner_conn, run_id) == [1, 2, 3]

        # Epoch 6 is one behind: this worker's lease was reclaimed.
        with pytest.raises(event_log.Fenced):
            event_log.append_step_event(
                worker_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=6,
                type="step.progress",
                principal="worker-1",
            )

        assert sequence_of(owner_conn, run_id) == [1, 2, 3]
        assert next_seq_of(owner_conn, run_id) == 3, (
            "the fenced attempt consumed a sequence number"
        )

        # And the next legitimate append gets 4, not 5.
        seq = event_log.append_step_event(
            worker_conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=7,
            type="step.progress",
            principal="worker-1",
        )
        assert seq == 4
        assert sequence_of(owner_conn, run_id) == [1, 2, 3, 4]
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def test_a_fence_loss_is_not_retried_as_a_deadlock(
    worker_conn: psycopg.Connection, run_with_one_step_per_writer: tuple[UUID, list[UUID]]
) -> None:
    """The retry wrapper is scoped to 40P01 and must not swallow a fence.

    Retrying a fenced append would be a worker insisting on work it no longer
    owns, and it would do so while another worker holds the lease.
    """
    run_id, step_ids = run_with_one_step_per_writer

    # Called directly: `append_step_event` already carries the wrapper, so
    # wrapping it again here tested two layers and named one.
    with pytest.raises(event_log.Fenced):
        event_log.append_step_event(
            worker_conn,
            run_id=run_id,
            step_id=step_ids[0],
            lease_epoch=999,
            type="step.progress",
            principal="worker-1",
        )
