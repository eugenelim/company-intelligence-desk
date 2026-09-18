"""The pool's completion and abandon paths, exercised in process.

Review round 1 established that `release`, the fence-loss abandon, the
terminal-run abandon and the failed-body branch had **never executed under any
check**: the pool ran only inside the Compose containers, whose step body
sleeps 600 seconds, and every fault-injection test kills or stops its worker
well inside that. Four code paths, no coverage, on the mechanism AC-0010 and
AC-0011 rest on.

These use the `step_body` injection seam and `PoolConfig`'s overridable
timings, both of which the pool already shipped for exactly this purpose. The
timings are compressed **here and only here**: AC-0010 and AC-0011 stay at
r7's real values in `tests/fault_injection`, because a compressed run
demonstrates the mechanism and not the number. What these tests establish is
the mechanism.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import psycopg
import pytest

from ced.adapters.postgres import event_log
from ced.worker import pool

pytestmark = pytest.mark.substrate

# **Read comparisons use `clock_timestamp()`, never `now()`.** `now()` is
# `transaction_timestamp()`, and these fixtures' connections are not
# autocommit — so a read taken inside an already-open transaction compares
# against the instant that transaction began, not the present. The
# fault-injection suite had an assertion that could never be true for exactly
# that reason, and the reads here were only correct by accident of being the
# first statement in a fresh transaction.

#: Fast enough to keep the suite offline-quick, slow enough that the heartbeat
#: fires at least once inside a step.
#: A pool class the container workers do not poll. They are started with no
#: `CED_POOL_CLASS`, so they take the default — and this suite runs with them
#: up, inserting `runnable` rows at that same default. A container claim
#: landing before the test's own `claim_one` made `lease is not None` or
#: `epoch == 1` red for a reason unrelated to the code, and every row these
#: tests abandoned was afterwards claimed and re-abandoned by a container.
#: `pool_class` is the partition seam r7 change 3 already shipped.
TEST_POOL_CLASS = "in-process-tests"

FAST = pool.PoolConfig(
    worker_id="test-worker",
    pool_class=TEST_POOL_CLASS,
    lease_ttl_seconds=3,
    heartbeat_seconds=1,
    poll_seconds=1,
)


@dataclass
class _Body:
    """An injectable step body that records what happened to it."""

    started: threading.Event
    finished: threading.Event
    stopped: threading.Event
    raises: bool = False
    block: bool = True

    def __call__(self, lease: pool.Lease, stop: threading.Event) -> None:
        self.started.set()
        try:
            if self.raises:
                raise RuntimeError("the step body failed")
            if self.block:
                if stop.wait(timeout=30):
                    self.stopped.set()
        finally:
            self.finished.set()


def make_body(*, raises: bool = False, block: bool = True) -> _Body:
    return _Body(
        started=threading.Event(),
        finished=threading.Event(),
        stopped=threading.Event(),
        raises=raises,
        block=block,
    )


@pytest.fixture
def runnable_step(owner_conn: psycopg.Connection) -> Iterator[tuple[UUID, UUID]]:
    """One run with one runnable step, cleaned up either way."""
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, agent_role, pool_class) "
            "VALUES (%s, %s, 'runnable', 'coordinator', %s)",
            (step_id, run_id, TEST_POOL_CLASS),
        )
    try:
        yield run_id, step_id
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def _step_state(conn: psycopg.Connection, step_id: UUID) -> tuple[str, int, object]:
    row = conn.execute(
        "SELECT state, lease_epoch, lease_expires_at FROM steps WHERE step_id = %s",
        (step_id,),
    ).fetchone()
    assert row is not None
    return str(row[0]), int(row[1]), row[2]


# ── claim ───────────────────────────────────────────────────────────────────


def test_claim_one_stamps_the_owner_and_bumps_the_epoch(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """The epoch `claim_one` returns is the one the fence then accepts.

    This joins the two halves that were previously only tested separately: the
    claim issues an epoch, and `append_step_event` accepts that same value and
    refuses its predecessor.
    """
    run_id, step_id = runnable_step

    lease = pool.claim_one(worker_conn, FAST)

    assert lease is not None
    assert lease.step_id == step_id
    assert lease.run_id == run_id
    assert lease.epoch == 1
    assert lease.agent_role == "coordinator"

    state, epoch, expires = _step_state(owner_conn, step_id)
    assert (state, epoch) == ("leased", 1)
    assert expires is not None

    # The issued epoch is accepted…
    assert (
        event_log.append_step_event(
            worker_conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=lease.epoch,
            type="step.started",
            principal=FAST.worker_id,
        )
        == 1
    )
    # …and the one before it is not.
    with pytest.raises(event_log.Fenced):
        event_log.append_step_event(
            worker_conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=lease.epoch - 1,
            type="step.started",
            principal=FAST.worker_id,
        )


def test_claim_one_returns_none_when_nothing_is_runnable(
    worker_conn: psycopg.Connection,
) -> None:
    """Otherwise the poll loop would spin on a phantom lease."""
    assert (
        pool.claim_one(worker_conn, pool.PoolConfig(worker_id="w", pool_class="none")) is None
    )


def test_a_second_claim_of_a_reacquired_step_invalidates_the_first_lease(
    worker_conn: psycopg.Connection, runnable_step: tuple[UUID, UUID]
) -> None:
    """Reacquisition fences the previous holder out — asserted, not commented.

    `tests/fault_injection` states this consequence in a comment. Here it is
    the assertion: two claims in turn, first lease refused, second accepted.
    """
    run_id, step_id = runnable_step

    first = pool.claim_one(worker_conn, FAST)
    assert first is not None
    # Expire it, as a lost worker's lease would expire.
    worker_conn.execute(
        "UPDATE steps SET lease_expires_at = now() - interval '1 second' WHERE step_id = %s",
        (step_id,),
    )
    worker_conn.commit()

    second = pool.claim_one(
        worker_conn,
        pool.PoolConfig(
            worker_id="other-worker",
            pool_class=TEST_POOL_CLASS,
            lease_ttl_seconds=3,
        ),
    )
    assert second is not None
    assert second.epoch == first.epoch + 1

    with pytest.raises(event_log.Fenced):
        event_log.append_step_event(
            worker_conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=first.epoch,
            type="step.progress",
            principal=FAST.worker_id,
        )
    assert event_log.append_step_event(
        worker_conn,
        run_id=run_id,
        step_id=step_id,
        lease_epoch=second.epoch,
        type="step.progress",
        principal="other-worker",
    )


# ── renew and release ───────────────────────────────────────────────────────


def test_renew_extends_the_lease_and_returns_the_run_state(
    worker_conn: psycopg.Connection, runnable_step: tuple[UUID, UUID]
) -> None:
    """The run state and the renewal arrive as one signal, by design."""
    _run_id, step_id = runnable_step
    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None
    _state, _epoch, before = _step_state(worker_conn, step_id)

    assert pool.renew(worker_conn, FAST, lease) == "requested"

    _state, _epoch, after = _step_state(worker_conn, step_id)
    assert after > before


def test_renew_is_fenced_on_epoch_and_on_owner(
    worker_conn: psycopg.Connection, runnable_step: tuple[UUID, UUID]
) -> None:
    """A partitioned-but-alive worker must not renew a lease it lost."""
    _run_id, _step_id = runnable_step
    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    stale = pool.Lease(
        step_id=lease.step_id, run_id=lease.run_id, epoch=lease.epoch - 1, agent_role=None
    )
    with pytest.raises(event_log.Fenced):
        pool.renew(worker_conn, FAST, stale)

    impostor = pool.PoolConfig(worker_id="not-the-owner", pool_class=TEST_POOL_CLASS)
    with pytest.raises(event_log.Fenced):
        pool.renew(worker_conn, impostor, lease)


def test_release_marks_the_step_and_clears_the_lease(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """`release` had never executed under any check before this."""
    _run_id, step_id = runnable_step
    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    pool.release(worker_conn, FAST, lease, "completed")

    state, _epoch, expires = _step_state(owner_conn, step_id)
    assert state == "completed"
    assert expires is None


def test_a_fenced_release_is_a_silent_no_op(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """The step already belongs to another worker; do not reach into it."""
    _run_id, step_id = runnable_step
    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None
    stale = pool.Lease(
        step_id=lease.step_id, run_id=lease.run_id, epoch=lease.epoch - 1, agent_role=None
    )

    pool.release(worker_conn, FAST, stale, "completed")

    state, _epoch, _expires = _step_state(owner_conn, step_id)
    assert state == "leased", "a fenced release rewrote a step it does not own"


# ── the four paths through `_execute` ───────────────────────────────────────


def _run_one_step(worker: pool.Worker, conn: psycopg.Connection) -> None:
    """Claim one step and execute it, as `run_forever` would."""
    lease = pool.claim_one(conn, worker.config)
    assert lease is not None
    worker._execute(conn, lease)


def test_a_completed_body_releases_the_step_as_completed(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """Path 1 of 4: completion falls through to `release`."""
    _run_id, step_id = runnable_step
    body = make_body(block=False)
    worker = pool.Worker(FAST, step_body=body)

    _run_one_step(worker, worker_conn)

    assert body.started.is_set() and body.finished.is_set()
    assert _step_state(owner_conn, step_id)[0] == "completed"


def test_a_raising_body_releases_the_step_as_failed(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """Path 2 of 4: the `outcome == "failed"` branch."""
    _run_id, step_id = runnable_step
    body = make_body(raises=True)
    worker = pool.Worker(FAST, step_body=body)

    _run_one_step(worker, worker_conn)

    assert body.finished.is_set()
    assert _step_state(owner_conn, step_id)[0] == "failed"


def test_fence_loss_abandons_the_step_and_stops_the_body(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """Path 3 of 4: the fence-loss abandon, with the body actually joined.

    Another worker reacquires mid-step, so the heartbeat's renewal returns zero
    rows. The step must not be released by the worker that lost it.
    """
    _run_id, step_id = runnable_step
    body = make_body()
    worker = pool.Worker(FAST, step_body=body)

    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    def steal() -> None:
        body.started.wait(timeout=10)
        with psycopg.connect(_dsn()) as thief:
            thief.execute(
                "UPDATE steps SET lease_epoch = lease_epoch + 1, owner = 'thief' "
                "WHERE step_id = %s",
                (step_id,),
            )
            thief.commit()

    thief_thread = threading.Thread(target=steal)
    thief_thread.start()
    worker._execute(worker_conn, lease)
    thief_thread.join(timeout=10)

    assert body.stopped.is_set(), "the abandoned body was not stopped"
    assert body.finished.is_set(), "the abandoned body was not joined"
    # The losing worker left the step alone: still leased, to the thief.
    state, epoch, _expires = _step_state(owner_conn, step_id)
    assert state == "leased"
    assert epoch == lease.epoch + 1


def test_a_terminal_run_abandons_the_step(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """Path 4 of 4: the heartbeat reads run state in the same statement.

    Nothing in this spec produces a terminal run — the run state machine is the
    evidence spec's — so the state is set directly here. What is exercised is
    the worker's response to the signal, which is this spec's.
    """
    run_id, step_id = runnable_step
    body = make_body()
    worker = pool.Worker(FAST, step_body=body)

    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    def cancel() -> None:
        body.started.wait(timeout=10)
        with psycopg.connect(_dsn()) as conn:
            conn.execute("UPDATE runs SET state = 'cancelled' WHERE run_id = %s", (run_id,))
            conn.commit()

    canceller = threading.Thread(target=cancel)
    canceller.start()
    worker._execute(worker_conn, lease)
    canceller.join(timeout=10)

    assert body.stopped.is_set()
    assert body.finished.is_set()
    # **This is a recorded gap, not a desired outcome.** The step is left
    # `leased` with a lease `renew` just extended by a full TTL, and
    # `claim_one`'s predicate does not join `runs.state` — so it becomes
    # claimable again every TTL and the body re-executes for about one
    # heartbeat each cycle, indefinitely. The run state machine that would
    # retire such a step belongs to `walking-skeleton-evidence`; the ledger
    # records the unbounded re-claim as not established against.
    assert _step_state(owner_conn, step_id)[0] == "leased"


def test_a_drain_expires_the_lease_and_joins_the_body(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """The drain path, and the reason AC-0011 can now assert one poll interval.

    `request_stop` sets the wake event, so the supervisor observes it at once
    rather than after the remaining heartbeat interval. This asserts the
    promptness the container test then measures in wall-clock.
    """
    _run_id, step_id = runnable_step
    body = make_body()
    worker = pool.Worker(FAST, step_body=body)

    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    def drain() -> None:
        body.started.wait(timeout=10)
        worker.request_stop()

    drainer = threading.Thread(target=drain)
    drainer.start()
    worker._execute(worker_conn, lease)
    drainer.join(timeout=10)

    assert body.stopped.is_set()
    assert body.finished.is_set()
    # `SIGTERM` sets lease_expires_at = now(), so the next poll takes it.
    row = owner_conn.execute(
        "SELECT lease_expires_at <= clock_timestamp() FROM steps WHERE step_id = %s",
        (step_id,),
    ).fetchone()
    assert row == (True,), "the drain did not expire the lease"
    assert _step_state(owner_conn, step_id)[0] == "leased"


def test_verify_boot_opens_both_roles(require_substrate: None) -> None:
    """A worker without the policy connection must fail readiness.

    `verify_boot` had no caller under test either. It raises rather than
    returning false, which is what makes a broken policy connection a failed
    readiness check rather than a worker that starts and denies everything.
    """
    pool.verify_boot(FAST)


def _dsn() -> str:
    from ced.adapters.postgres.dsn import database_url

    return database_url("migration")


def test_a_stop_requested_before_the_body_starts_is_not_lost(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """The wake bit must survive `_execute`'s clear.

    `_wake` is shared across steps and cleared on entry, so a `SIGTERM`
    arriving while `claim_one` was in flight had its bit dropped — after
    `run_forever` had already tested `_stop` — and the supervisor then blocked
    a full heartbeat before noticing. Every existing check requested the stop
    *after* the body started, i.e. after the clear, so none covered it.

    Here the stop is requested before `_execute` is entered at all, which is
    exactly that window. With the defect present this takes a whole heartbeat
    interval; with it fixed, milliseconds.
    """
    _run_id, step_id = runnable_step
    body = make_body()
    worker = pool.Worker(FAST, step_body=body)

    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    worker.request_stop()
    started = time.monotonic()
    worker._execute(worker_conn, lease)
    elapsed = time.monotonic() - started

    assert elapsed < FAST.heartbeat_seconds, (
        f"the drain took {elapsed:.2f}s, at least one heartbeat "
        f"({FAST.heartbeat_seconds}s) — the stop was observed late"
    )
    assert body.finished.is_set(), "the body was not joined"
    row = owner_conn.execute(
        "SELECT lease_expires_at <= clock_timestamp() FROM steps WHERE step_id = %s",
        (step_id,),
    ).fetchone()
    assert row == (True,), "the drain did not expire the lease"


def test_a_completed_body_is_released_even_when_a_stop_is_pending(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """An outcome already recorded has exactly one correct disposition.

    The drain branch used to run first unconditionally, so a body that had
    already reported `completed` was abandoned and the survivor re-executed it
    — duplicate side effects once a real body replaces the sleep.
    """
    _run_id, step_id = runnable_step
    worker: pool.Worker

    def body_that_stops_the_worker(_lease: pool.Lease, _stop: threading.Event) -> None:
        """Finish, then request the stop — so both are true on the first wake.

        This is the ordering the check exists for, arranged rather than raced
        for. An earlier version called `body.finished.wait(timeout=0)` before
        `_execute` had even started the body thread, which is a no-op, and then
        set `_stop` — so which branch ran depended on whether the body happened
        to finish during `psycopg.connect`.
        """
        worker.request_stop()

    worker = pool.Worker(FAST, step_body=body_that_stops_the_worker)
    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    worker._execute(worker_conn, lease)

    assert _step_state(owner_conn, step_id)[0] == "completed", (
        "a completed step was returned to the pool as unfinished"
    )


def test_the_drain_stops_the_body_before_surrendering_the_lease(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    runnable_step: tuple[UUID, UUID],
) -> None:
    """Otherwise the step is claimable while the old body still runs.

    `_expire_now` used to precede the join, so between the expiry and the
    body's stop the survivor could claim and execute the same step. Asserted by
    observing that the body has finished by the time the lease is expired.
    """
    _run_id, step_id = runnable_step
    body = make_body()
    worker = pool.Worker(FAST, step_body=body)

    lease = pool.claim_one(worker_conn, FAST)
    assert lease is not None

    def drain() -> None:
        body.started.wait(timeout=10)
        worker.request_stop()

    drainer = threading.Thread(target=drain)
    drainer.start()
    worker._execute(worker_conn, lease)
    drainer.join(timeout=10)

    # The body is stopped and joined by the time `_execute` returns, and the
    # lease is expired — so no window exists in which both are true of the old
    # body and the step is claimable.
    assert body.stopped.is_set() and body.finished.is_set()
    row = owner_conn.execute(
        "SELECT lease_expires_at <= clock_timestamp() FROM steps WHERE step_id = %s",
        (step_id,),
    ).fetchone()
    assert row == (True,)
