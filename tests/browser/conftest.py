"""Browser-test fixtures.

``api_server`` and ``clean_runs`` are defined in ``tests/api/conftest.py``
and re-exported here so that ``tests/browser/`` tests can consume them.
Importing them into this conftest registers them as fixtures for the
``tests/browser/`` directory without requiring the ``pytest_plugins``
mechanism (which is invalid in a non-rootdir conftest in pytest 9+).

Cut-before-adding rung 2: the functions already exist in
``tests/api/conftest.py``; a re-export adds no new code.
"""

from __future__ import annotations

from tests.api.conftest import api_server, clean_runs

__all__ = ["api_server", "clean_runs"]
