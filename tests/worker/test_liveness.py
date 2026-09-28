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
import time
from pathlib import Path

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
