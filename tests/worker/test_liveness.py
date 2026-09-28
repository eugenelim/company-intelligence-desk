"""AC-0331: three liveness verdicts and the probe command.

AC-0331 requires the probe to report healthy for an idle worker (nothing to
claim), healthy for a busy one (executing a step), and unhealthy for a stalled
poll loop that has not killed the process.

Mutation-proof note: the staleness threshold is 2 * lease_ttl_seconds. A
mutant that always returns healthy fails test_a_stalled_worker_reports_unhealthy.
A mutant that always returns unhealthy fails test_an_idle_worker_reports_healthy
and test_a_busy_worker_mid_step_reports_healthy. A mutant that drops the factor-of-2
(threshold = lease_ttl_seconds) fails test_a_busy_worker_mid_step_reports_healthy
(which supplies seconds_since_poll = lease_ttl_seconds * 1.1, inside 2× but
outside 1×).
"""

import subprocess
import sys
import threading
import time
import unittest.mock as mock
from pathlib import Path

import pytest

from ced.worker.liveness import (
    LEASE_TTL_SECONDS,
    liveness_state,
    probe,
    refresh_mark,
    unlink_mark,
)


def test_an_idle_worker_reports_healthy() -> None:
    """An idle worker that polled recently is healthy (AC-0331 verdict 1)."""
    assert liveness_state(seconds_since_poll=1.0, lease_ttl_seconds=60).healthy is True


def test_a_busy_worker_mid_step_reports_healthy() -> None:
    """A worker executing a long step is still healthy (AC-0331 verdict 2).

    The heartbeat writes the mark during a step, so elapsed time stays below
    the threshold even while the poll loop is blocked inside _execute. The
    threshold is twice the lease TTL; a step running for 1.1× the TTL is
    within that window and must be healthy.
    """
    ttl = 60
    # 1.1 × TTL is inside 2 × TTL — a running step, not a stalled loop.
    assert liveness_state(seconds_since_poll=ttl * 1.1, lease_ttl_seconds=ttl).healthy is True


def test_a_stalled_worker_reports_unhealthy() -> None:
    """A loop that has not refreshed the mark for 2 × TTL is unhealthy (AC-0331 verdict 3)."""
    ttl = 60
    # 2.1 × TTL — past the threshold; the loop is stalled.
    assert liveness_state(seconds_since_poll=ttl * 2.1, lease_ttl_seconds=ttl).healthy is False


def test_probe_reads_mark_mtime(tmp_path: Path) -> None:
    """probe() returns healthy for a fresh mark file, unhealthy for a stale one."""
    mark = tmp_path / "mark"

    # No mark → unhealthy.
    assert probe(mark).healthy is False

    # Fresh mark → healthy.
    refresh_mark(mark)
    assert probe(mark).healthy is True

    # Simulate a stale mark by back-dating its mtime by 3 × TTL.
    stale_mtime = time.time() - (3 * LEASE_TTL_SECONDS)
    import os

    os.utime(mark, (stale_mtime, stale_mtime))
    assert probe(mark).healthy is False


def test_unlink_mark_removes_existing(tmp_path: Path) -> None:
    """unlink_mark() removes the mark; a missing mark is silently ignored."""
    mark = tmp_path / "mark"
    mark.touch()
    assert mark.exists()
    unlink_mark(mark)
    assert not mark.exists()
    # Second call is a no-op (missing is silently ignored).
    unlink_mark(mark)


def test_probe_as_command_exits_0_when_healthy(tmp_path: Path) -> None:
    """The ced-liveness entry point exits 0 for a healthy mark (AC-0331 probe-as-command)."""
    mark = tmp_path / "mark"
    refresh_mark(mark)
    result = subprocess.run(
        [sys.executable, "-m", "ced.worker.liveness", str(mark)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_probe_as_command_exits_1_when_absent(tmp_path: Path) -> None:
    """The ced-liveness entry point exits 1 for a missing mark (AC-0331 probe-as-command)."""
    mark = tmp_path / "absent_mark"
    result = subprocess.run(
        [sys.executable, "-m", "ced.worker.liveness", str(mark)],
        capture_output=True,
    )
    assert result.returncode == 1, result.stderr.decode()


# ── AC-0331: real process assertions (Entry 6) ───────────────────────────────

_LIVENESS_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}


@pytest.mark.substrate
def test_idle_worker_writes_mark_and_probe_reports_healthy(
    require_substrate: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Idle Worker writes the liveness mark; probe reports healthy then unhealthy when stalled.

    Stalls the poll loop by back-dating the mark mtime after the Worker has
    written it (simulating a process-alive stall without killing the Worker).
    Probes the real mark path — not a mock — at each stage.

    Mutation that must red (idle-path): remove ``refresh_mark()`` from pool.py's
    between-claims site. The mark is never written; the initial healthy assertion
    reds because the mark does not exist.
    """
    import os

    from ced.worker.pool import PoolConfig, Worker

    mark = tmp_path / "ced-t2-liveness-idle-mark"
    monkeypatch.setenv("CED_LIVENESS_MARK_PATH", str(mark))

    pool_class = "t2-liveness-idle-probe"
    config = PoolConfig(
        worker_id="t2-liveness-idle-probe-worker",
        default_limits=_LIVENESS_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        pool_class=pool_class,
        poll_seconds=1,
    )

    worker = Worker(config)
    thread = threading.Thread(target=worker.run_forever, daemon=True)
    thread.start()

    # Wait up to 10 s for the Worker to poll and write the mark.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if mark.exists():
            break
        time.sleep(0.05)

    try:
        assert mark.exists(), (
            "idle Worker must write the liveness mark between claims; "
            "mutation: remove refresh_mark() → mark absent → this assertion reds"
        )
        assert probe(mark).healthy, "mark written by idle Worker must be fresh (healthy)"

        # Stall the loop inside claim_one so no refresh_mark() can intervene
        # between the back-date and the probe.  The Worker polls every second;
        # without the stall the loop can overwrite the back-dated mtime before
        # probe() reads it, making the assertion a race rather than a proof.
        import ced.worker.pool as pool_module

        loop_held = threading.Event()
        loop_resume = threading.Event()
        _real_claim_one = pool_module.claim_one

        def _hold_then_claim(conn: object, cfg: object) -> object:
            loop_held.set()  # signal: loop is parked inside claim_one
            loop_resume.wait()  # wait for the test to release us
            return _real_claim_one(conn, cfg)  # type: ignore[arg-type]

        with mock.patch("ced.worker.pool.claim_one", _hold_then_claim):
            assert loop_held.wait(timeout=5), "poll loop did not enter claim_one within 5 s"
            # Loop is blocked; back-date the mark safely.
            stale = time.time() - 3 * LEASE_TTL_SECONDS
            os.utime(mark, (stale, stale))
            assert not probe(mark).healthy, (
                "back-dated mark must be unhealthy; "
                "the loop is stalled inside claim_one so no refresh can intervene; "
                "mutation: remove idle-path refresh_mark() → the assertion the idle "
                "path never writes a fresh mark, but this assertion targets staleness "
                "of an already-written mark, which the mtime back-date establishes; "
                "mutation: make probe ignore mtime → always reports healthy → this reds"
            )
            loop_resume.set()  # release the loop
    finally:
        worker.request_stop()
        thread.join(timeout=5)


@pytest.mark.substrate
def test_busy_worker_heartbeat_keeps_mark_fresh(
    require_substrate: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Busy Worker: heartbeat keeps the mark fresh past 2 × TTL (AC-0331 verdict 2).

    A step that runs for longer than 2 × lease_ttl_seconds stays healthy
    because the in-step heartbeat refreshes the mark at each renewal.

    Uses compressed timings (TTL=3 s, heartbeat=1 s) so the test completes
    in ~9 s.

    Mutation that must red (busy-path): remove the ``refresh_mark()`` call from
    pool.py's heartbeat-renewal site (line
    ``refresh_mark()  # AC-0331: busy-path mark``). The mark ages out past
    2 × TTL while the step runs; the healthy assertion reds.
    """
    import uuid

    import psycopg

    from ced.adapters.postgres.dsn import database_url
    from ced.worker.pool import PoolConfig, Worker

    mark = tmp_path / "ced-t2-liveness-busy-mark"
    monkeypatch.setenv("CED_LIVENESS_MARK_PATH", str(mark))

    pool_class = f"t2-liveness-busy-{uuid.uuid4().hex[:8]}"
    TTL = 3  # seconds — compressed for the test

    config = PoolConfig(
        worker_id="t2-liveness-busy-worker",
        default_limits=_LIVENESS_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        pool_class=pool_class,
        lease_ttl_seconds=TTL,
        heartbeat_seconds=1,
        poll_seconds=1,
    )

    # Insert a step whose body blocks until told to stop.
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    body_started = threading.Event()

    def blocking_body(lease: object, stop: threading.Event) -> None:
        body_started.set()
        # Block until the test signals completion or stop fires.
        stop.wait(timeout=30)

    with psycopg.connect(database_url("migration")) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'running', 0)",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO steps (step_id, run_id, state, pool_class, agent_role)"
                " VALUES (%s, %s, 'runnable', %s, 'coordinator')",
                (step_id, run_id, pool_class),
            )

    try:
        worker = Worker(config, step_body=blocking_body)
        thread = threading.Thread(target=worker.run_forever, daemon=True)
        thread.start()

        # Wait for the body to start (Worker claimed the step and is executing).
        assert body_started.wait(timeout=15), "Worker did not start the step body within 15 s"

        # Let the step run past 2 × TTL so the idle-only mark would go stale.
        time.sleep(2 * TTL + 1)

        # The mark must still be healthy — the heartbeat kept it fresh.
        # Pass the compressed TTL so the threshold is 2 × TTL = 6 s, not the
        # default 120 s: with the mutation (heartbeat refresh_mark removed), the
        # mark was last written before the step started (~7 s ago) and ages past
        # the 6 s threshold, reding this assertion.
        assert mark.exists(), "mark must exist while step is executing"
        assert probe(mark, lease_ttl_seconds=TTL).healthy, (
            "mark must be fresh (healthy) while the Worker is executing a step; "
            "the in-step heartbeat must refresh it at each renewal; "
            "mutation: remove refresh_mark() from pool.py heartbeat-renewal site → "
            "mark ages past 2 × TTL (6 s) → this assertion reds"
        )
    finally:
        worker.request_stop()
        thread.join(timeout=TTL + 5)
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()
