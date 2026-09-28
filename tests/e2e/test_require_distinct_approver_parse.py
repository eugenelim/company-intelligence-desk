"""Offline tests for ``_parse_require_distinct_approver`` and ``_lifespan``.

These tests drive the parse function and the startup context manager directly,
using ``monkeypatch.setenv`` rather than a running server.  They run without
a substrate — no database, no MinIO, no uvicorn.

Coverage:
- Absent variable → ``False`` (off by default).
- Recognised truthy values → ``True``.
- Recognised falsy values → ``False``.
- Present but unrecognised value → ``ValueError`` naming the variable.
- ``_lifespan`` propagates the ``ValueError`` so the process refuses at startup
  rather than starting with a silently misread policy flag.

These tests are the only layer that exercises the env-var → parse →
``app.state`` seam.  The e2e substrate tests (``test_approval_decision_route``)
set ``app.state.require_distinct_approver`` directly; they prove the route reads
``app.state`` but cannot observe whether the parse function produced the right
value from the raw environment string.
"""

from __future__ import annotations

import asyncio

import pytest

from ced.api.main import (
    _REQUIRE_DISTINCT_APPROVER_VAR,
    _lifespan,
    _parse_require_distinct_approver,
)
from ced.api.main import app as _app

# ── Absent variable ───────────────────────────────────────────────────────────


def test_absent_variable_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent ``CED_REQUIRE_DISTINCT_APPROVER`` defaults to ``False``."""
    monkeypatch.delenv(_REQUIRE_DISTINCT_APPROVER_VAR, raising=False)
    assert _parse_require_distinct_approver() is False


# ── Truthy values ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "YES", "True"])
def test_truthy_values_return_true(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Recognised truthy strings enable the check."""
    monkeypatch.setenv(_REQUIRE_DISTINCT_APPROVER_VAR, value)
    assert _parse_require_distinct_approver() is True


# ── Recognised falsy values ───────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["0", "false", "no", "FALSE", "NO", "False"])
def test_falsy_values_return_false(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Recognised falsy strings disable the check explicitly."""
    monkeypatch.setenv(_REQUIRE_DISTINCT_APPROVER_VAR, value)
    assert _parse_require_distinct_approver() is False


# ── Malformed values must refuse ──────────────────────────────────────────────


@pytest.mark.parametrize("value", ["ture", "2", "enabled", "on", "off", "maybe", "yes!"])
def test_malformed_value_raises_value_error(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """A present but unrecognised value raises ``ValueError`` naming the variable.

    Mutation-proof: if the raise is removed and the function returns ``False``
    for unrecognised values, ``pytest.raises(ValueError)`` is not satisfied and
    the test reds.
    """
    monkeypatch.setenv(_REQUIRE_DISTINCT_APPROVER_VAR, value)
    with pytest.raises(ValueError, match=_REQUIRE_DISTINCT_APPROVER_VAR):
        _parse_require_distinct_approver()


# ── _lifespan propagates the error ────────────────────────────────────────────


def test_lifespan_refuses_malformed_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed env var causes ``_lifespan`` to raise before yielding.

    The process must refuse at startup — not start with a silently misread
    policy flag.  Mutation-proof: if ``_lifespan`` catches the error and
    defaults to ``False``, it yields without raising and ``pytest.raises``
    is not satisfied.
    """
    monkeypatch.setenv(_REQUIRE_DISTINCT_APPROVER_VAR, "ture")

    async def _run() -> None:
        async with _lifespan(_app):
            pass  # pragma: no cover — never reached

    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(_run())


def test_lifespan_sets_false_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent env var causes ``_lifespan`` to set ``app.state`` to ``False``."""
    monkeypatch.delenv(_REQUIRE_DISTINCT_APPROVER_VAR, raising=False)
    # Save and restore the original state so this test doesn't bleed.
    original = getattr(_app.state, "require_distinct_approver", None)
    try:
        asyncio.run(_drive_lifespan())
        assert _app.state.require_distinct_approver is False
    finally:
        if original is not None:
            _app.state.require_distinct_approver = original


async def _drive_lifespan() -> None:
    async with _lifespan(_app):
        pass


def test_lifespan_sets_true_when_truthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """A truthy env var causes ``_lifespan`` to set ``app.state`` to ``True``."""
    monkeypatch.setenv(_REQUIRE_DISTINCT_APPROVER_VAR, "1")
    original = getattr(_app.state, "require_distinct_approver", None)
    try:
        asyncio.run(_drive_lifespan())
        assert _app.state.require_distinct_approver is True
    finally:
        _app.state.require_distinct_approver = original if original is not None else False
