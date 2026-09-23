"""Fixtures for the authorization suite, defined in `harness.py` and bound here.

Split so the harness stays importable as a module — several checks call its
helpers directly — while pytest still collects the fixtures. Re-exporting is the
whole of this file; the definitions and their reasoning live next door.
"""

from __future__ import annotations

from tests.authorization.harness import claimed, step

__all__ = ["claimed", "step"]
