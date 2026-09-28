"""Worker liveness probe: a file-based mark the poll loop refreshes.

AC-0331 requires the probe to report:

  * **healthy** for an idle worker (nothing to claim)
  * **healthy** for a busy one (executing a step)
  * **unhealthy** for a stalled poll loop that has not killed the process

The mark is updated by the poll loop — both between claims (idle path) and
while a step is in flight (busy path). An out-of-process probe reads the mark
and checks its age against twice the lease TTL.

The probe is a worker-side command the container healthcheck runs, **not an
HTTP route** (DR4). This module does not import ``pool`` or ``psycopg``, so the
healthcheck command is a pure subprocess that checks one file.

**Why both paths must write.** A mark written only between claims marks a busy
worker unhealthy — ``run_forever`` is blocked inside ``_execute`` and makes no
passes while a step runs. A mark written only in the heartbeat marks an idle
worker unhealthy — ``renew`` is only called inside ``_execute`` under a live
lease, so a worker with nothing to claim attempts no heartbeat at all. Either
half alone is wrong (AC-0331); both together span the two states the probe must
not confuse.

**Staleness measure.** The mark's ``mtime`` (file modification time set by the
OS) is the staleness measure. Writing ``time.monotonic()`` as text — the
previous approach — is undefined across process boundaries: Python documents
the reference point as unspecified, and only intra-process differences are
valid. ``mtime`` is a wall-clock value the OS sets consistently whether read
in the same process or a different one.

**Mark path.** The default path includes ``CED_WORKER_ID`` so two workers on
one host write different marks. A stalled worker cannot hide behind a healthy
sibling's mark. The contracted deployment is one container per worker, where
paths are already isolated, so the per-id default is a safety measure for
local development only.

**Startup unlink.** The mark is unlinked at worker startup. A stale mark from
a previous process (``docker restart`` reuses the container's writable layer,
so ``/tmp`` survives) would otherwise make the new process appear healthy
before its first poll. Unlinking at startup removes that hazard; an absent mark
is treated as unhealthy.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "LEASE_TTL_SECONDS",
    "LivenessState",
    "MARK_PATH_VAR",
    "default_mark_path",
    "liveness_state",
    "probe",
    "refresh_mark",
    "run",
    "unlink_mark",
]

#: The lease TTL the probe uses as its staleness threshold.
#:
#: **Canonical source.** ``pool.py`` imports this constant from here, so the
#: probe and the pool always agree. This breaks the former circular import:
#: ``liveness`` no longer imports ``pool``, so both lazy imports in ``pool``
#: become normal module-level imports.
#:
#: r7 § Step execution: TTL 60 s.
LEASE_TTL_SECONDS = 60

#: Environment variable that lets the healthcheck command and the poll loop
#: agree on the mark file path without hardcoding it.
MARK_PATH_VAR = "CED_LIVENESS_MARK_PATH"


def default_mark_path() -> Path:
    """Return the liveness mark path from the environment or a per-worker default.

    The default includes ``CED_WORKER_ID`` (if set) so two workers on one host
    write distinct marks. ``CED_LIVENESS_MARK_PATH`` overrides this entirely.
    """
    raw = os.environ.get(MARK_PATH_VAR)
    if raw:
        return Path(raw)
    worker_id = os.environ.get("CED_WORKER_ID", "")
    suffix = f"-{worker_id}" if worker_id else ""
    return Path(f"/tmp/ced-liveness-mark{suffix}")


@dataclass(frozen=True)
class LivenessState:
    """The verdict the probe returns."""

    healthy: bool


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
    """Touch the mark file to record the current wall-clock time as its mtime.

    Called by the poll loop: between claims (idle path) and at each heartbeat
    renewal (busy path). The directory must already exist.

    The mtime is set by the OS and is consistent across process boundaries,
    unlike ``time.monotonic()`` whose reference point is process-local.
    """
    mark = path or default_mark_path()
    # touch() updates mtime to now; create if absent.
    mark.touch()


def unlink_mark(path: Path | None = None) -> None:
    """Remove the mark file at worker startup, so a stale mark never hides a fresh start.

    ``docker restart`` reuses the container's writable layer, so ``/tmp``
    survives a restart. Without the unlink, a stale mark from the previous
    process would make the new process appear healthy before its first poll.
    Missing file is silently ignored (already clean or never written).
    """
    mark = path or default_mark_path()
    try:
        mark.unlink()
    except FileNotFoundError:
        pass


def probe(
    path: Path | None = None, lease_ttl_seconds: int = LEASE_TTL_SECONDS
) -> LivenessState:
    """Read the mark file's mtime and return the liveness verdict.

    An absent or unreadable mark file is unhealthy: either the poll loop has
    not started yet, or it has been stalled long enough for the file to
    disappear — either way the healthcheck should fire.

    ``mtime`` is the wall-clock time the OS recorded on the last write, which
    is consistent across processes. ``time.time()`` is the matching wall-clock
    read on the probe side.
    """
    mark = path or default_mark_path()
    try:
        stat = mark.stat()
        mark_mtime = stat.st_mtime
    except OSError:
        return LivenessState(healthy=False)
    elapsed = time.time() - mark_mtime
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


if __name__ == "__main__":
    # Allow ``python -m ced.worker.liveness [path]`` for testing.
    # An optional positional argument overrides the default mark path.
    _path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    run(_path)
