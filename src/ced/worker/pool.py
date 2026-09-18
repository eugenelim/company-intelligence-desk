"""The pool: claim under a lease, execute outside any transaction, renew fenced.

r7 § Step execution, and `worker-runtime.md` § The pool. The protocol is theirs;
what is here is the implementation and the timings they specify.

**Row locking and lease expiry are different mechanisms.** A row lock held
across a multi-minute step would pin an idle-in-transaction connection, hold
`xmin` back, and block vacuum on the event-log tables. So the claim commits
immediately and the step executes with no transaction open; what protects the
step is the lease, and what protects the lease is the epoch fence.

**One step in flight per worker.** The SEC rate limit is an aggregate
obligation enforced by a central token bucket and Bedrock's budget is
account-wide, so in-process concurrency buys no throughput — it moves
contention somewhere harder to observe. It also means a fenced worker has
exactly one thing to abandon, which is what makes "aborts without *additional*
side effects" a simple statement rather than a coordination problem.

**What this module does not do**, because no criterion in
`walking-skeleton-foundation` needs it and the sibling specs own it:

  * It runs an **injected step body**. `walking-skeleton-agent-runtime`
    supplies the real one; here the default sleeps, which is what keeps this
    spec's suite offline and free of spend.
  * There is no cancellation token and no `step_deadline`. Those are
    `worker-runtime.md` § The pool's, and the evidence spec measures them.
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
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType
from uuid import UUID

import psycopg

from ced.adapters.postgres.dsn import database_url

log = logging.getLogger("ced.worker.pool")

#: r7 § Step execution. TTL 60 s, heartbeat at TTL/3, poll 30 s — so a worker
#: that dies without notice loses at most one TTL plus one poll interval, which
#: is the 150 s AC-0010 measures against.
LEASE_TTL_SECONDS = 60
HEARTBEAT_SECONDS = LEASE_TTL_SECONDS // 3
POLL_SECONDS = 30
WORST_CASE_REACQUISITION_SECONDS = LEASE_TTL_SECONDS + POLL_SECONDS + HEARTBEAT_SECONDS

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

        The timings are overridable so a test can compress them, and the
        defaults are r7's. AC-0010 and AC-0011 are measured at the defaults:
        a compressed run would demonstrate the mechanism and not the number.
        """
        return cls(
            worker_id=os.environ.get("CED_WORKER_ID", f"worker-{os.getpid()}"),
            pool_class=os.environ.get("CED_POOL_CLASS", DEFAULT_POOL_CLASS),
            lease_ttl_seconds=int(os.environ.get("CED_LEASE_TTL_SECONDS", LEASE_TTL_SECONDS)),
            heartbeat_seconds=int(os.environ.get("CED_HEARTBEAT_SECONDS", HEARTBEAT_SECONDS)),
            poll_seconds=int(os.environ.get("CED_POLL_SECONDS", POLL_SECONDS)),
        )


class Fenced(Exception):
    """The lease moved on while this worker held it."""


def verify_boot(config: PoolConfig) -> None:
    """Open and verify both database connections before claiming anything.

    A worker that claims a step before it can finish one manufactures a lease
    expiry and a 150-second recovery for a problem a readiness check catches in
    milliseconds. The policy connection is checked here for that reason: a
    worker without it cannot authorize a tool call, so it must fail readiness
    rather than start and deny everything.

    Two roles, one OS process — `worker-runtime.md` § Changes this design asks
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

    def request_stop(self) -> None:
        self._stop.set()

    def install_signal_handlers(self) -> None:
        def handle(signum: int, frame: FrameType | None) -> None:
            log.info("received %s — draining", signal.Signals(signum).name)
            self.request_stop()

        signal.signal(signal.SIGTERM, handle)
        signal.signal(signal.SIGINT, handle)

    def run_forever(self) -> None:
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
        """Run the step body with the heartbeat renewing alongside it."""
        log.info("claimed step %s at epoch %s", lease.step_id, lease.epoch)
        body_stop = threading.Event()
        outcome: list[str] = []

        def body() -> None:
            try:
                self.step_body(lease, body_stop)
                outcome.append("completed")
            except Exception:
                log.exception("step %s failed", lease.step_id)
                outcome.append("failed")

        thread = threading.Thread(target=body, daemon=True)
        thread.start()

        # The heartbeat runs on this thread, and a separate connection, so the
        # renewal is not queued behind whatever the step body is doing.
        with psycopg.connect(database_url("worker")) as heartbeat_conn:
            while thread.is_alive():
                if self._stop.is_set():
                    # Graceful drain: expire the lease now and stop the body.
                    # The step goes back within one poll interval.
                    self._expire_now(heartbeat_conn, lease)
                    body_stop.set()
                    thread.join(timeout=self.config.lease_ttl_seconds)
                    return
                thread.join(timeout=self.config.heartbeat_seconds)
                if not thread.is_alive():
                    break
                try:
                    run_state = renew(heartbeat_conn, self.config, lease)
                except Fenced:
                    log.warning("fenced on step %s — abandoning", lease.step_id)
                    body_stop.set()
                    return
                if run_state in ("cancelled", "failed", "completed"):
                    log.info("run %s is %s — abandoning step", lease.run_id, run_state)
                    body_stop.set()
                    return

        release(conn, self.config, lease, outcome[0] if outcome else "failed")

    def _expire_now(self, conn: psycopg.Connection, lease: Lease) -> None:
        """`SIGTERM` sets `lease_expires_at = now()`, per r7 § Step execution."""
        conn.execute(
            "UPDATE steps SET lease_expires_at = now() WHERE step_id = %s AND owner = %s",
            (lease.step_id, self.config.worker_id),
        )
        conn.commit()
        log.info("drained step %s — expires now", lease.step_id)


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
