"""Rate gate tests — AC-0403.

Two independently spawned OS processes each open their own Postgres session
and race to acquire the shared advisory lock. The tests verify:

1. The gate serialises request starts by at least ``_GATE_INTERVAL`` seconds
   while both sessions are live.
2. Terminating the holder process releases the contender without deadlock.
3. A psycopg.Error raised during lock release (unlock) is swallowed so the
   original outcome reaches the caller (Concern 5).

The process-isolation tests are substrate tests; the swallowing test is offline.
"""

from __future__ import annotations

import multiprocessing
import time
from typing import Any

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url
from ced.adapters.sec.client import _GATE_INTERVAL, SecClientError, open_postgres_gate

# ---------------------------------------------------------------------------
# Worker functions (run in child processes via spawn)
# ---------------------------------------------------------------------------


def _gate_worker(
    queue: multiprocessing.Queue[str],
    dsn: str,
    hold_seconds: float = 0.5,
) -> None:
    """Acquire the gate, send the admission marker, hold for hold_seconds, then release."""
    import time as _time

    with open_postgres_gate(dsn) as admission:
        queue.put(f"admitted:{admission:.6f}")
        queue.join_thread()  # ensure message is flushed before any sleep
        _time.sleep(hold_seconds)


def _gate_worker_long(
    queue: multiprocessing.Queue[str],
    dsn: str,
) -> None:
    """Acquire the gate, signal admission, then hold indefinitely (until killed)."""
    import time as _time

    with open_postgres_gate(dsn) as admission:
        queue.put(f"admitted:{admission:.6f}")
        queue.join_thread()  # ensure message is flushed
        # Hold until the process is terminated externally.
        while True:
            _time.sleep(0.1)


# ---------------------------------------------------------------------------
# AC-0403: two processes are serialised by at least _GATE_INTERVAL
# ---------------------------------------------------------------------------


@pytest.mark.substrate
def test_two_processes_gate_admission_separated(require_substrate: None) -> None:
    """Two spawned processes have their gate-admission times separated by at
    least ``_GATE_INTERVAL`` seconds.

    Mutation 1 — replace Postgres advisory lock with a threading.Lock: the
    two separate processes would each acquire the thread-local lock instantly
    and the separation would be near zero, making this assertion fail.

    Mutation 2 — delete the ``_GATE_INTERVAL`` hold: the lock is released
    immediately after the admission and the second process is admitted before
    the interval elapses.
    """
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue[str] = ctx.Queue()
    dsn = database_url("worker")

    p1 = ctx.Process(target=_gate_worker, args=(queue, dsn, 0.5))
    p2 = ctx.Process(target=_gate_worker, args=(queue, dsn, 0.0))

    p1.start()
    # Small delay so p1 has time to acquire the lock first.
    time.sleep(0.05)
    p2.start()

    # Collect both markers (each is "admitted:<monotonic>").
    markers: list[float] = []
    deadline = time.monotonic() + 15.0
    while len(markers) < 2 and time.monotonic() < deadline:
        try:
            msg = queue.get(timeout=0.2)
            if msg.startswith("admitted:"):
                markers.append(float(msg.split(":")[1]))
        except Exception:
            pass

    p1.join(timeout=5)
    p2.join(timeout=5)

    assert len(markers) == 2, f"expected 2 admission markers, got {len(markers)}"

    separation = abs(markers[1] - markers[0])
    assert separation >= _GATE_INTERVAL, (
        f"gate separation {separation:.4f}s < _GATE_INTERVAL {_GATE_INTERVAL}s; "
        f"the gate must serialise request starts by at least the interval"
    )


# ---------------------------------------------------------------------------
# AC-0403: connection loss releases the lock without deadlock
# ---------------------------------------------------------------------------


@pytest.mark.substrate
def test_holder_termination_releases_contender(require_substrate: None) -> None:
    """Terminating the holder process releases the contender without deadlock.

    The test parent receives the holder's admission marker, then sends SIGTERM
    to the holder.  That kills the process — closing its Postgres connection
    and releasing the session-level advisory lock — so the contender can
    proceed.  No interval assertion is made across the crash boundary.

    Mutation: use a lock that is not released on connection loss (e.g., a
    file lock without LOCK_NB) — the contender would hang indefinitely and
    the ``queue.get(timeout=15)`` call would time out.
    """
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue[str] = ctx.Queue()
    dsn = database_url("worker")

    # Holder: acquires lock, signals, then holds indefinitely until killed.
    holder = ctx.Process(target=_gate_worker_long, args=(queue, dsn))
    # Contender: started after holder is terminated; should acquire the freed lock.
    contender = ctx.Process(target=_gate_worker, args=(queue, dsn, 0.0))

    holder.start()

    # Wait for holder to acquire and signal.
    holder_admitted = False
    deadline = time.monotonic() + 10.0
    while not holder_admitted and time.monotonic() < deadline:
        try:
            msg = queue.get(timeout=0.2)
            if msg.startswith("admitted:"):
                holder_admitted = True
        except Exception:
            pass

    assert holder_admitted, "holder must acquire gate before being terminated"

    # Terminate the holder — this closes its DB connection, releasing the lock.
    holder.terminate()
    holder.join(timeout=5)

    # Now start contender; it should acquire the released lock.
    contender.start()

    contender_admitted = False
    deadline = time.monotonic() + 15.0
    while not contender_admitted and time.monotonic() < deadline:
        try:
            msg = queue.get(timeout=0.2)
            if msg.startswith("admitted:"):
                contender_admitted = True
        except Exception:
            pass

    contender.join(timeout=5)

    assert contender_admitted, (
        "contender must be admitted after holder process is terminated; "
        "the Postgres session-level advisory lock must be released on connection close"
    )


# ---------------------------------------------------------------------------
# Concern 5 (AC-0403): release-failure swallowing — offline, no substrate
# ---------------------------------------------------------------------------


def test_open_postgres_gate_swallows_release_error_and_propagates_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """open_postgres_gate swallows psycopg.Error on release and lets the original
    outcome reach the caller.

    A fake connection acquires the lock successfully (first execute) and raises
    ``psycopg.OperationalError`` on the unlock call (second execute).  The
    original ``SecClientError`` raised inside the gate body must propagate, not
    the release error.

    Mutation: re-raise the psycopg.Error from release instead of swallowing it
    → the original ``SecClientError`` is replaced by the ``psycopg.OperationalError``
    and ``pytest.raises(SecClientError)`` fails.
    """
    monkeypatch.setattr("time.sleep", lambda s: None)

    execute_count: list[int] = [0]

    class _FakeConn:
        def execute(self, query: str, params: Any = None) -> None:
            execute_count[0] += 1
            if execute_count[0] >= 2:
                # Second execute is the pg_advisory_unlock call; simulate failure.
                raise psycopg.OperationalError("simulated release failure")

        def commit(self) -> None:
            pass

        def close(self) -> None:
            pass

        def __enter__(self) -> _FakeConn:
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

    monkeypatch.setattr("psycopg.connect", lambda dsn, **kw: _FakeConn())

    original_exc = SecClientError("original error from body")

    with pytest.raises(SecClientError) as exc_info:
        with open_postgres_gate("fake-dsn"):
            raise original_exc

    assert exc_info.value is original_exc, (
        "the original SecClientError must reach the caller; "
        "psycopg.Error from release must not replace it"
    )
