"""Worker liveness probe: a file-based mark the poll loop refreshes.

AC-0331 requires the probe to report:

  * **healthy** for an idle worker (nothing to claim)
  * **healthy** for a busy one (executing a step)
  * **unhealthy** for a stalled poll loop that has not killed the process

The mark is a monotonic timestamp written by the poll loop — both between
claims (idle path) and while a step is in flight (busy path). An out-of-process
probe reads the mark and checks its age against twice the lease TTL.

The probe is a worker-side command the container healthcheck runs, **not an
HTTP route** (DR4). This module is importable independently of psycopg and the
framework, so the healthcheck command is a pure subprocess that checks one file.

**Why both paths must write.** A mark written only between claims marks a busy
worker unhealthy — ``run_forever`` is blocked inside ``_execute`` and makes no
passes while a step runs. A mark written only in the heartbeat marks an idle
worker unhealthy — ``renew`` is only called inside ``_execute`` under a live
lease, so a worker with nothing to claim attempts no heartbeat at all. Either
half alone is wrong (AC-0331); both together span the two states the probe must
not confuse.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ced.worker.pool import LEASE_TTL_SECONDS

__all__ = [
    "LivenessState",
    "MARK_PATH_VAR",
    "default_mark_path",
    "liveness_state",
    "probe",
    "refresh_mark",
    "run",
]

#: Environment variable that lets the healthcheck command and the poll loop
#: agree on the mark file path without hardcoding it.
MARK_PATH_VAR = "CED_LIVENESS_MARK_PATH"

#: Default path when the variable is unset. ``/tmp`` is acceptable here: the
#: mark is ephemeral and must not survive a process restart — a stale mark left
#: over from a previous process would make the new one appear healthy before its
#: first poll. ``/tmp`` is typically cleared on container restart, which is the
#: right scope for this.
_DEFAULT_MARK_PATH = Path("/tmp/ced-liveness-mark")


@dataclass(frozen=True)
class LivenessState:
    """The verdict the probe returns."""

    healthy: bool


def default_mark_path() -> Path:
    """Return the liveness mark path from the environment or the built-in default."""
    raw = os.environ.get(MARK_PATH_VAR)
    return Path(raw) if raw else _DEFAULT_MARK_PATH


def liveness_state(*, seconds_since_poll: float, lease_ttl_seconds: int) -> LivenessState:
    """Compute the liveness verdict from elapsed time and the configured TTL.

    The threshold is twice the lease TTL. An idle worker polls at most every
    ``POLL_SECONDS`` (30 s by default), which is well inside 120 s (2 × 60 s).
    A stalled loop — one that has not refreshed the mark for two full TTLs — is
    reportable within the window a scheduler would normally act on anyway.

    AC-0331: "a worker whose loop is stalled without killing the process reports
    unhealthy within twice the lease TTL".
    """
    return LivenessState(healthy=seconds_since_poll < 2 * lease_ttl_seconds)


def refresh_mark(path: Path | None = None) -> None:
    """Write the current monotonic time to the mark file.

    Called by the poll loop: between claims (idle path) and at each heartbeat
    renewal (busy path). The mark file is created or overwritten; the directory
    must already exist.
    """
    mark = path or default_mark_path()
    mark.write_text(str(time.monotonic()), encoding="utf-8")


def probe(
    path: Path | None = None, lease_ttl_seconds: int = LEASE_TTL_SECONDS
) -> LivenessState:
    """Read the mark file and return the liveness verdict.

    An absent or unreadable mark file is unhealthy: either the poll loop has
    not started yet, or it has been stalled long enough for the file to
    disappear — either way the healthcheck should fire.
    """
    mark = path or default_mark_path()
    try:
        text = mark.read_text(encoding="utf-8").strip()
        mark_time = float(text)
    except (OSError, ValueError):
        return LivenessState(healthy=False)
    elapsed = time.monotonic() - mark_time
    return liveness_state(seconds_since_poll=elapsed, lease_ttl_seconds=lease_ttl_seconds)


def run(
    path: Path | None = None,
    lease_ttl_seconds: int = LEASE_TTL_SECONDS,
) -> None:
    """Exit 0 when healthy, 1 when not. The container healthcheck runs this.

    An exit code is the lingua franca between the probe and the scheduler:
    no HTTP, no psycopg, no framework import is required. The command can be
    invoked by any process with filesystem access.
    """
    state = probe(path, lease_ttl_seconds)
    sys.exit(0 if state.healthy else 1)
