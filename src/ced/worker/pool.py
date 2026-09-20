"""The pool: claim under a lease, execute outside any transaction, renew fenced.

r8 § 3 Runtime Model, and `worker-runtime.md` § 6 Deployment and Operations.
The protocol is theirs;
what is here is the implementation and the timings they specify.

**Row locking and lease expiry are different mechanisms.** A row lock held
across a multi-minute step would pin an idle-in-transaction connection, hold
`xmin` back, and block vacuum on the event-log tables. So the claim commits
immediately and the step executes with no transaction open; what protects the
step is the lease, and what protects the lease is the epoch fence.

**One step in flight per worker**, and the condition is named rather than
implied. The SEC rate limit is an aggregate obligation enforced by a central
token bucket and Bedrock's budget is account-wide, so in-process concurrency
buys no throughput — it moves contention somewhere harder to observe. It also
means a fenced worker has exactly one thing to abandon, which is what makes
"aborts without *additional* side effects" a simple statement rather than a
coordination problem.

**Every exit path stops and joins the body before this worker touches the
row.** The five dispositions:

  * completion and failure — join, then `release`;
  * fence loss and a terminal run — join, then return without touching the
    row, because the step is already someone else's or the run is over. If the
    join times out on either path the row is left untouched for the same
    reason, and the worker additionally stops claiming rather than pick up
    another step beside a body still running — as in the drain case below;
  * drain where the body had already finished — join, then `release` with the
    recorded outcome, so a step that completed on its own is not handed back
    to a survivor to re-run;
  * drain — join, then `_expire_now`;
  * drain where the body could not be joined within a lease TTL — the lease is
    **left to expire on its own** and the worker stops claiming.

**This is not a no-overlap invariant, and it used to claim to be one.** The
join in the last two cases runs for a full lease TTL while the supervisor —
the only renewer — is inside it, so no heartbeat fires; the lease was last
renewed at most one heartbeat earlier and therefore has TTL minus heartbeat to
TTL of validity left. A body that takes longer than that to unwind loses its
lease *during the join*, and a survivor claims and starts a second body beside
it. Measured, with the timings compressed: at TTL 6 / heartbeat 2 against a
body needing 14 s to stop, the lease was dead 5.13 s after the drain signal
with the old body still running, and a second worker claimed the same step at
the next epoch.

At the shipped timings the threshold is a body that takes more than about 40 s
to stop — **derived, not measured**: it is `LEASE_TTL_SECONDS` minus
`HEARTBEAT_SECONDS`, the least validity a lease can have left when the join
starts. Nothing drives a stuck body at the shipped timings, and the 5.13 s
figure above came from a scratchpad probe rather than a committed check; both
limits are recorded in the verification ledger.

That overlap is **accepted, ratified behaviour, not a defect to close here**.
`worker-runtime.md` § 3 Runtime Model states that two workers can be
inside the same step's toolset stack at once and names the derived idempotency
key and the fenced `policy.decision` append as "exactly what make that overlap
benign — neither is optional". Shortening the join or renewing through it would
be designing around that acceptance. What the non-surrender above buys is
narrower and worth stating exactly: this worker does not *itself* hand the step
over while its body runs. Whether the lease outlives the body is a race it does
not control.

An earlier version surrendered the lease on the drain path regardless, which
made the step claimable immediately while the old body ran. The cost of the
current behaviour is that a stuck body delays recovery of its step to one full
lease TTL, which is the recovery path r7 already specifies for a worker that
dies.

**What this module does not do**, because no criterion in
`walking-skeleton-foundation` needs it and the sibling specs own it:

  * It runs an **injected step body**. `walking-skeleton-role-compilation`
    supplies the real one; here the default sleeps, which is what keeps this
    spec's suite offline and free of spend.
  * There is no cancellation token and no `step_deadline`. Those are
    `worker-runtime.md` § 6 Deployment and Operations', and the evidence spec
    measures them.
  * The boot sequence verifies both database connections and **not** the object
    store: nothing in this spec reads or writes an object, and an S3 client
    here would put the AWS SDK outside `adapters/`, which the
    dependency-direction gate forbids.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType
from uuid import UUID

import psycopg

from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import Fenced

log = logging.getLogger("ced.worker.pool")

#: r7 § Step execution: TTL 60 s, heartbeat at TTL/3, poll 30 s.
LEASE_TTL_SECONDS = 60
HEARTBEAT_SECONDS = LEASE_TTL_SECONDS // 3
POLL_SECONDS = 30

#: The bound this implementation can be derived to. A worker dying immediately
#: after a renewal leaves the lease valid for one full TTL, and the surviving
#: worker then needs at most one poll interval to find it claimable.
DERIVED_REACQUISITION_BOUND_SECONDS = LEASE_TTL_SECONDS + POLL_SECONDS

#: AC-0010's bound, and r7's own figure for the same timings.
#:
#: **These two numbers do not agree, and the difference is recorded rather than
#: reconciled here.** r8 § 3 Runtime Model and `worker-runtime.md` § 6
#: both state 150 s for TTL 60 / heartbeat 20 / poll 30; the terms above sum to
#: 90, and no arrangement of those three values reaches 150. The criterion is
#: the looser of the two, so nothing is at risk: this implementation is inside
#: both. Reconciling the architecture's arithmetic belongs to the outstanding
#: r8 consistency pass its own header names, not to this spec, which is
#: forbidden from designing around a ratified decision.
CRITERION_REACQUISITION_BOUND_SECONDS = 150

#: r7 change 3. One class in MVP, so the predicate narrows nothing yet.
DEFAULT_POOL_CLASS = "default"


@dataclass(frozen=True)
class Lease:
    """A claimed step. `epoch` is what every subsequent write is fenced on."""

    step_id: UUID
    run_id: UUID
    epoch: int
    agent_role: str | None


@dataclass(frozen=True)
class PoolConfig:
    worker_id: str
    pool_class: str = DEFAULT_POOL_CLASS
    lease_ttl_seconds: int = LEASE_TTL_SECONDS
    heartbeat_seconds: int = HEARTBEAT_SECONDS
    poll_seconds: int = POLL_SECONDS

    @classmethod
    def from_environment(cls) -> PoolConfig:
        """Read the deploy-time configuration.

        **The timings are not environment-overridable.** They were, on the
        stated ground that "a test can compress them", and no caller ever did:
        `tests/worker` constructs `PoolConfig` directly and Compose sets only
        the worker id and the step-body duration. Three unread variables were
        removed under `AGENTS.md` § Cut before adding rung 1. AC-0010 and
        AC-0011 are measured at r7's values, which is what makes them
        measurements of the numbers those criteria state.
        """
        return cls(
            worker_id=os.environ.get("CED_WORKER_ID", f"worker-{os.getpid()}"),
            pool_class=os.environ.get("CED_POOL_CLASS", DEFAULT_POOL_CLASS),
        )


def verify_boot(config: PoolConfig) -> None:
    """Open and verify both database connections before claiming anything.

    A worker that claims a step before it can finish one manufactures a lease
    expiry and a 150-second recovery for a problem a readiness check catches in
    milliseconds. The policy connection is checked here for that reason: a
    worker without it cannot authorize a tool call, so it must fail readiness
    rather than start and deny everything.

    Two roles, one OS process — `runtime-architecture.md` r8 § 4, Identity
    of r7 item 11. The strength of the split rests on the database grant rather
    than on credential separation, because the task role can obtain both.
    """
    for role in ("worker", "policy"):
        with psycopg.connect(database_url(role)) as conn:
            row = conn.execute("SELECT session_user").fetchone()
            assert row is not None
            log.info("boot: %s connection verified as %s", role, row[0])


def claim_one(conn: psycopg.Connection, config: PoolConfig) -> Lease | None:
    """Claim a runnable step, stamp it, bump the epoch, and commit at once.

    `FOR UPDATE SKIP LOCKED` so two workers polling together take different
    rows rather than queueing on one. The predicate admits a step that is
    runnable, or one whose lease has expired — which is the recovery path: no
    operator action, no scheduler, just the next poll finding it claimable.
    """
    with conn.transaction():
        row = conn.execute(
            """
            SELECT step_id, run_id, agent_role
              FROM steps
             WHERE pool_class = %s
               AND (state = 'runnable'
                    OR (state = 'leased' AND lease_expires_at < now()))
             ORDER BY created_at
               FOR UPDATE SKIP LOCKED
             LIMIT 1
            """,
            (config.pool_class,),
        ).fetchone()
        if row is None:
            return None
        step_id, run_id, agent_role = row

        epoch_row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = %s,
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + make_interval(secs => %s)
             WHERE step_id = %s
             RETURNING lease_epoch
            """,
            (config.worker_id, config.lease_ttl_seconds, step_id),
        ).fetchone()
        assert epoch_row is not None
        return Lease(
            step_id=step_id,
            run_id=run_id,
            epoch=int(epoch_row[0]),
            agent_role=agent_role,
        )


def renew(conn: psycopg.Connection, config: PoolConfig, lease: Lease) -> str:
    """Renew the lease, fenced on epoch and owner. Returns the run's state.

    Without the fence a partitioned-but-alive worker could renew a lease it no
    longer owns. Zero rows means fenced, and the caller aborts.

    The run's state is read in the **same statement** that renews, so a
    cancelled run and a lost fence arrive as one signal rather than as two
    reads that can disagree.
    """
    row = conn.execute(
        """
        UPDATE steps AS s
           SET lease_expires_at = now() + make_interval(secs => %s)
          FROM runs AS r
         WHERE s.step_id = %s
           AND s.lease_epoch = %s
           AND s.owner = %s
           AND r.run_id = s.run_id
         RETURNING r.state
        """,
        (config.lease_ttl_seconds, lease.step_id, lease.epoch, config.worker_id),
    ).fetchone()
    conn.commit()
    if row is None:
        raise Fenced(f"step {lease.step_id} epoch {lease.epoch}")
    return str(row[0])


def release(conn: psycopg.Connection, config: PoolConfig, lease: Lease, state: str) -> None:
    """Mark the step finished, fenced. A fenced release is a silent no-op.

    Silent because the step already belongs to another worker: rewriting its
    state from here would be this worker reaching into work it lost.
    """
    conn.execute(
        """
        UPDATE steps
           SET state = %s, lease_expires_at = NULL
         WHERE step_id = %s AND lease_epoch = %s AND owner = %s
        """,
        (state, lease.step_id, lease.epoch, config.worker_id),
    )
    conn.commit()


def sleep_step_body(lease: Lease, stop: threading.Event) -> None:
    """The injected default: sleep until told to stop, or for a fixed spell.

    A sleep, not a model call, which is what keeps this spec's fault-injection
    suite free of a credential and of spend.
    """
    seconds = float(os.environ.get("CED_STEP_BODY_SECONDS", "600"))
    stop.wait(timeout=seconds)


StepBody = Callable[[Lease, threading.Event], None]


class Worker:
    """One poll loop, one step in flight."""

    def __init__(self, config: PoolConfig, step_body: StepBody | None = None) -> None:
        self.config = config
        self.step_body = step_body or sleep_step_body
        self._stop = threading.Event()
        #: Set whenever something happened worth looking at — the step body
        #: finished, or a stop was requested. The supervisor parks on this
        #: rather than on `thread.join(heartbeat)`, which is what makes
        #: `SIGTERM` observable immediately instead of up to one heartbeat
        #: later. AC-0011 measures that difference.
        self._wake = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def install_signal_handlers(self) -> None:
        def handle(signum: int, frame: FrameType | None) -> None:
            log.info("received %s — draining", signal.Signals(signum).name)
            self.request_stop()

        signal.signal(signal.SIGTERM, handle)
        signal.signal(signal.SIGINT, handle)

    def run_forever(self) -> None:
        """Poll, claim, execute. Crash-only on a database failure.

        **There is no in-loop retry**, so a reset connection or a restarted
        backend propagates out and the process exits. That is a recorded
        posture rather than an oversight: in-loop retry is machinery for the
        deployment this spec puts out of scope, and `AGENTS.md` § Cut before
        adding rung 1 refuses an addition that is not genuinely needed. The
        local cost is real and named — `deploy/compose.yaml` sets
        `restart: "no"`, so capacity halves until an operator intervenes, and
        the fault-injection suite's ECS substitution covers container kill and
        not process exit.
        """
        verify_boot(self.config)
        log.info("ready: %s polling class %s", self.config.worker_id, self.config.pool_class)
        with psycopg.connect(database_url("worker")) as conn:
            while not self._stop.is_set():
                lease = claim_one(conn, self.config)
                if lease is None:
                    self._stop.wait(timeout=self.config.poll_seconds)
                    continue
                self._execute(conn, lease)

    def _execute(self, conn: psycopg.Connection, lease: Lease) -> None:
        """Run the step body with the heartbeat renewing alongside it.

        The supervisor waits on `self._wake`, not on the body thread, so a
        completed body is released at once and a `SIGTERM` reaches
        `_expire_now` without waiting out a heartbeat. AC-0011 states the
        second of those as one poll interval.

        Three orderings here are deliberate and each was got wrong once:

        * **A stop already requested survives the clear.** `_wake` is shared
          across steps and cleared on entry, so a `SIGTERM` arriving while
          `claim_one` was in flight used to have its bit dropped — after
          `run_forever` had already tested `_stop` — costing a full heartbeat.
          The clear is now followed by a re-assert when `_stop` is set.
        * **A completed body is released even when a stop is pending.** The
          drain branch used to run first unconditionally, so a body that had
          already recorded `completed` was abandoned and re-executed by the
          survivor.
        * **The body is stopped before the lease is surrendered.** `_expire_now`
          used to precede the join, so the step became claimable while the old
          body was still running.
        """
        log.info("claimed step %s at epoch %s", lease.step_id, lease.epoch)
        body_stop = threading.Event()
        body_done = threading.Event()
        outcome: list[str] = []

        self._wake.clear()
        if self._stop.is_set():
            # A stop requested before or during the claim. Re-assert the bit the
            # clear above just dropped, so the first wait returns immediately.
            self._wake.set()

        def body() -> None:
            try:
                self.step_body(lease, body_stop)
                outcome.append("completed")
            except Exception:
                log.exception("step %s failed", lease.step_id)
                outcome.append("failed")
            finally:
                body_done.set()
                self._wake.set()

        thread = threading.Thread(target=body, daemon=True)
        thread.start()

        def stop_body(reason: str) -> bool:
            """Stop the body and wait for it. True when it actually stopped.

            A body that will not stop is a defect in the body, and the caller
            must not claim again while it runs — so the return value is acted
            on rather than only logged.

            **The join bound and the container's stop grace are one
            relationship, not two independent numbers.** This joins for a lease
            TTL; a container SIGKILLed before that elapses never reaches
            `_expire_now` or the `if not stopped` branch, and AC-0011's
            surrender silently degrades to waiting out the TTL. So
            `deploy/compose.yaml` sets `stop_grace_period` on both worker
            services above this bound, and the two must move together. The
            fault-injection suite does not exercise the interaction — it uses
            `docker kill --signal=TERM`, which has no grace period and no
            follow-up SIGKILL — so the grace period is the only thing standing
            between a slow body and that degradation under `docker stop` or
            `docker-compose down`.
            """
            body_stop.set()
            thread.join(timeout=self.config.lease_ttl_seconds)
            if thread.is_alive():
                log.error(
                    "step %s body did not stop within %ss after %s; this worker "
                    "will stop claiming rather than run two bodies at once",
                    lease.step_id,
                    self.config.lease_ttl_seconds,
                    reason,
                )
                return False
            return True

        # The heartbeat runs on a separate connection, so the renewal is not
        # queued behind whatever the step body is doing.
        with psycopg.connect(database_url("worker")) as heartbeat_conn:
            # Computed once. A wake that is neither stop nor completion must
            # not push the renewal out by another full interval.
            renew_at = time.monotonic() + self.config.heartbeat_seconds
            while True:
                woken = self._wake.wait(timeout=max(renew_at - time.monotonic(), 0.0))
                self._wake.clear()

                # Completion first: an outcome already recorded has exactly one
                # correct disposition, stop pending or not.
                if body_done.is_set():
                    thread.join(timeout=self.config.lease_ttl_seconds)
                    release(conn, self.config, lease, outcome[0] if outcome else "failed")
                    return

                if self._stop.is_set():
                    # Graceful drain. Stop and join the body *before*
                    # surrendering the lease, so the step is not claimable
                    # while the old body still runs.
                    #
                    # `finished_first` is captured before `body_stop` is set,
                    # because the window between the `body_done` test above and
                    # this line is exactly where a body can complete on its
                    # own. It used to fall through to the surrender, discarding
                    # a recorded `completed` and letting the survivor
                    # re-execute a finished step — the round-2 defect narrowed
                    # rather than removed.
                    # Captured *before* `body_stop` is set, and nothing else
                    # will do: after `stop_body` returns, `body_done` is set on
                    # every cooperative body, because stopping it is what made
                    # it finish. Reading it afterwards cannot tell "completed
                    # on its own" from "completed because we asked", and an
                    # earlier version of this branch used that reading and
                    # released every drained step instead of surrendering it.
                    finished_first = body_done.is_set()
                    stopped = stop_body("drain")
                    if finished_first:
                        release(
                            conn,
                            self.config,
                            lease,
                            outcome[0] if outcome else "failed",
                        )
                        return
                    if not stopped:
                        # The body is still running, so the step must not
                        # become claimable: hold the lease and let it expire on
                        # its own rather than handing the step to a survivor
                        # that would run a second body beside this one.
                        log.error(
                            "step %s not surrendered: its body is still "
                            "running, so the lease is left to expire",
                            lease.step_id,
                        )
                        return
                    self._expire_now(heartbeat_conn, lease)
                    return

                if woken:
                    # Neither stop nor completion — a stale body's `finally`
                    # from a previous step is the only known setter. Do not
                    # reset `renew_at`.
                    continue

                try:
                    run_state = renew(heartbeat_conn, self.config, lease)
                except Fenced:
                    log.warning("fenced on step %s — abandoning", lease.step_id)
                    if not stop_body("fence loss"):
                        self.request_stop()
                    return
                if run_state in ("cancelled", "failed", "completed"):
                    log.info("run %s is %s — abandoning step", lease.run_id, run_state)
                    if not stop_body(f"run {run_state}"):
                        self.request_stop()
                    return
                renew_at = time.monotonic() + self.config.heartbeat_seconds

    def _expire_now(self, conn: psycopg.Connection, lease: Lease) -> None:
        """`SIGTERM` sets `lease_expires_at = now()`, per r7 § Step execution.

        The log line reports what the statement actually did. It was
        unconditional, so a drain whose row had been reowned or deleted
        announced a surrender having changed nothing — a log that misstates the
        one transition AC-0011 rests on.
        """
        cursor = conn.execute(
            "UPDATE steps SET lease_expires_at = now() WHERE step_id = %s AND owner = %s",
            (lease.step_id, self.config.worker_id),
        )
        conn.commit()
        if cursor.rowcount:
            log.info("drained step %s — expires now", lease.step_id)
        else:
            log.info(
                "drain on step %s changed nothing: the lease had already moved "
                "on or the row is gone",
                lease.step_id,
            )


def run() -> None:
    """The `ced-worker` entry point. The second deployable from one image."""
    logging.basicConfig(
        level=os.environ.get("CED_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = Worker(PoolConfig.from_environment())
    worker.install_signal_handlers()
    try:
        worker.run_forever()
    except KeyboardInterrupt:  # pragma: no cover — handled by the signal path
        pass
    log.info("exited")
