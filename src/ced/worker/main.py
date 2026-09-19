"""The `ced-worker` console-script target. The pool is in `pool.py`."""

from __future__ import annotations

from ced.worker.pool import run

__all__ = ["run"]
