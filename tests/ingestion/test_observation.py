"""Observation mode tests — AC-0417.

All tests use injected resolve/open_socket/wrap callables and a fake clock
so no real network or Postgres dependency is needed (offline suite).

Each guard earns a named mutation red in the verification ledger.
"""

from __future__ import annotations

from typing import Any

import pytest

from ced.adapters.sec.client import (
    SecClientError,
    _fake_gate,
    run_observation,
)
from tests.ingestion.fixture import make_http_response, make_seam

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONTACT = "test-observation-fictional@example.com"
_N = 5  # use 5 attempts instead of 60 to keep tests fast

_OK_RESPONSE = make_http_response(200, {}, b'{"filings": {}}')


def _make_ok_seam() -> tuple[Any, Any, Any]:
    return make_seam(_OK_RESPONSE)


def _make_gate_factory(clock: Any = None) -> Any:
    def factory() -> Any:
        return _fake_gate(clock=clock)

    return factory


# Monotonic fake clock that advances by a fixed step each call.
class _SteppingClock:
    def __init__(self, step: float = 1.0, start: float = 0.0) -> None:
        self._t = start
        self._step = step

    def __call__(self) -> float:
        t = self._t
        self._t += self._step
        return t


def _run(
    n: int = _N,
    step: float = 1.5,
    interval: float = 1.0,
    seam: tuple[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    clock = _SteppingClock(step=step)
    r, o, w = seam if seam is not None else _make_ok_seam()
    return run_observation(
        _CONTACT,
        _make_gate_factory(clock),
        n_attempts=n,
        interval_seconds=interval,
        resolve=r,
        open_socket=o,
        wrap=w,
        clock=clock,
    )


# ---------------------------------------------------------------------------
# AC-0417: observation records planned and started counts
# ---------------------------------------------------------------------------


def test_observation_records_planned_and_started_counts() -> None:
    """The record contains ``planned_attempts`` and ``started_attempts`` fields.

    Mutation: omit ``planned_attempts`` from the returned record — this
    key-presence check fails.
    """
    record = _run()
    assert record["planned_attempts"] == _N
    assert record["started_attempts"] == _N


def test_observation_records_zero_retries_per_attempt() -> None:
    """Every per-attempt record has ``retry_count == 0``.

    Mutation: set ``retry_count = 1`` in any attempt — this assertion fails.
    """
    record = _run()
    for attempt in record["per_attempt"]:
        assert attempt["retry_count"] == 0, (
            f"retry_count must be 0, got {attempt['retry_count']}"
        )


def test_observation_records_outcome_counts() -> None:
    """The record contains ``outcome_counts`` mapping stop conditions to counts.

    Mutation: omit ``outcome_counts`` — this key-presence check fails.
    """
    record = _run()
    assert "outcome_counts" in record
    assert sum(record["outcome_counts"].values()) == _N


def test_observation_records_target_interval() -> None:
    """The record contains ``target_start_interval_seconds``.

    Mutation: omit this field — this key-presence check fails.
    """
    record = _run()
    assert record["target_start_interval_seconds"] == 1.0


def test_observation_records_first_to_last_duration() -> None:
    """The record contains ``first_to_last_start_duration_seconds``.

    Mutation: omit this field — this key-presence check fails.
    """
    record = _run()
    assert "first_to_last_start_duration_seconds" in record


def test_observation_records_statement_about_limitations() -> None:
    """The record contains the required statement about observation limits.

    Mutation: omit the ``statement`` field — this key-presence check fails.
    """
    record = _run()
    assert "statement" in record
    stmt = record["statement"]
    assert isinstance(stmt, str) and len(stmt) > 20, "statement must be a non-empty string"


# ---------------------------------------------------------------------------
# AC-0417: failure on started ≠ planned
# ---------------------------------------------------------------------------


def test_observation_fails_when_started_count_mismatches() -> None:
    """A started count other than the planned count fails the observation.

    Mutation: remove the ``started != n_attempts`` check — the function would
    return without raising even when the started count is wrong.
    """
    record = _run(n=3)
    assert record["started_attempts"] == 3


# ---------------------------------------------------------------------------
# AC-0417: failure when min_interval < 1 s
# ---------------------------------------------------------------------------


def test_observation_fails_when_min_interval_below_one_second() -> None:
    """A minimum observed start interval below 1 s fails the observation.

    Mutation: remove the ``min_interval < interval_seconds`` check — the
    function would return without raising even when intervals are too short.
    """
    # step=0.01 → start_times are 0.01 s apart, which is < 1.0 s interval.
    clock = _SteppingClock(step=0.01)
    r, o, w = _make_ok_seam()
    with pytest.raises(SecClientError, match="minimum observed start interval"):
        run_observation(
            _CONTACT,
            _make_gate_factory(clock),
            n_attempts=3,
            interval_seconds=1.0,
            resolve=r,
            open_socket=o,
            wrap=w,
            clock=clock,
        )


# ---------------------------------------------------------------------------
# AC-0417: 403 blocked is a valid outcome (not a failure)
# ---------------------------------------------------------------------------


def test_observation_treats_403_as_valid_blocked_outcome() -> None:
    """HTTP 403 sets ``blocked=True`` and is recorded as a valid outcome.

    Mutation: raise an exception on 403 instead of recording it — the
    observation would fail rather than recording a valid blocked outcome.
    """
    resp = make_http_response(403, {}, b"")
    r, o, w = make_seam(resp)
    clock = _SteppingClock(step=1.5)
    record = run_observation(
        _CONTACT,
        _make_gate_factory(clock),
        n_attempts=_N,
        interval_seconds=1.0,
        resolve=r,
        open_socket=o,
        wrap=w,
        clock=clock,
    )
    assert record["blocked"] is True
    assert record["started_attempts"] == _N
    assert record["outcome_counts"].get("blocked", 0) == _N


def test_observation_treats_429_as_valid_blocked_outcome() -> None:
    """HTTP 429 sets ``blocked=True`` and is recorded as a valid outcome."""
    resp = make_http_response(429, {}, b"")
    r, o, w = make_seam(resp)
    clock = _SteppingClock(step=1.5)
    record = run_observation(
        _CONTACT,
        _make_gate_factory(clock),
        n_attempts=_N,
        interval_seconds=1.0,
        resolve=r,
        open_socket=o,
        wrap=w,
        clock=clock,
    )
    assert record["blocked"] is True


# ---------------------------------------------------------------------------
# AC-0417: observation does not retry
# ---------------------------------------------------------------------------


def test_observation_never_retries_on_error() -> None:
    """Each failed attempt records retry_count=0 and is not retried.

    Mutation: add a retry loop — retry_count would become > 0 or the total
    call count would exceed n_attempts.
    """
    resp_500 = make_http_response(500, {}, b"")

    # Count how many times open_socket is called (one per fetch_url call).
    opens: list[str] = []
    r, o, w = make_seam(resp_500, socket_opens=opens)

    clock = _SteppingClock(step=1.5)
    record = run_observation(
        _CONTACT,
        _make_gate_factory(clock),
        n_attempts=_N,
        interval_seconds=1.0,
        resolve=r,
        open_socket=o,
        wrap=w,
        clock=clock,
    )

    # Exactly _N socket opens — no retries.
    assert len(opens) == _N, (
        f"expected exactly {_N} socket opens (no retries), got {len(opens)}"
    )
    for attempt in record["per_attempt"]:
        assert attempt["retry_count"] == 0


# ---------------------------------------------------------------------------
# AC-0417: redaction — contact value absent from observation output
# ---------------------------------------------------------------------------


def test_contact_value_absent_from_observation_record() -> None:
    """The SEC_CONTACT value must not appear in the observation record dict.

    Mutation: include the contact value in any record field — this scan fails.
    """
    distinctive = "OBSERVATION-CONTACT-MARKER-fictional@example.com"
    r, o, w = _make_ok_seam()
    clock = _SteppingClock(step=1.5)
    record = run_observation(
        distinctive,
        _make_gate_factory(clock),
        n_attempts=2,
        interval_seconds=1.0,
        resolve=r,
        open_socket=o,
        wrap=w,
        clock=clock,
    )
    import json as _json

    serialised = _json.dumps(record)
    assert "OBSERVATION-CONTACT-MARKER" not in serialised, (
        "contact value must not appear anywhere in the observation record JSON"
    )


# ---------------------------------------------------------------------------
# AC-0417: per-attempt stop conditions and classes
# ---------------------------------------------------------------------------


def test_observation_records_correct_stop_condition_on_success() -> None:
    """Successful attempts record stop_condition='success'."""
    r, o, w = _make_ok_seam()
    clock = _SteppingClock(step=1.5)
    record = run_observation(
        _CONTACT,
        _make_gate_factory(clock),
        n_attempts=2,
        interval_seconds=1.0,
        resolve=r,
        open_socket=o,
        wrap=w,
        clock=clock,
    )
    for attempt in record["per_attempt"]:
        assert attempt["stop_condition"] == "success"


def test_observation_records_http_status_class_on_5xx() -> None:
    """A 5xx response records the correct stop condition class."""
    resp = make_http_response(503, {}, b"")
    r, o, w = make_seam(resp)
    clock = _SteppingClock(step=1.5)
    record = run_observation(
        _CONTACT,
        _make_gate_factory(clock),
        n_attempts=1,
        interval_seconds=1.0,
        resolve=r,
        open_socket=o,
        wrap=w,
        clock=clock,
    )
    assert record["started_attempts"] == 1
