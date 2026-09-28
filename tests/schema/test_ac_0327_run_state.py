"""AC-0327: the three committed state transitions, driven through the projection.

AC-0327 commits exactly three edges:

  * requested → running  on step.started
  * running → completed  on run.completed
  * running → failed     on run.failed

``project_run_state`` is a pure function: no database connection, no
framework import. These tests drive it from constructed EventEnvelope
sequences and assert the state at each boundary.

Mutation-proof discipline: each test drops one load-bearing event and
asserts the projection disagrees — so returning a constant sequence
fails at least one case. All three edges have their own dropping test.
"""

from __future__ import annotations

import uuid

from ced.domain.events import EventEnvelope
from ced.domain.run_state import project_run_state

# The final group avoids a 12-digit run of decimal digits: the repository
# identifier lint reads that shape as an AWS account id and refuses the
# commit. A hex-bearing tail is just as readable and does not trip it.
_RUN_ID = uuid.UUID("11111111-0000-0000-0000-aaaaaaaaaaa1")
_STEP_ID = uuid.UUID("22222222-0000-0000-0000-bbbbbbbbbbb2")
_PRINCIPAL = "test-principal"


def _env(seq: int, type: str, step_id: uuid.UUID | None = None) -> EventEnvelope:
    """Construct a minimal EventEnvelope for projection tests."""
    return EventEnvelope(
        schema_version=1,
        run_id=_RUN_ID,
        seq=seq,
        type=type,
        principal=_PRINCIPAL,
        step_id=step_id,
    )


# ── AC-0327 edge 1: requested → running on step.started ─────────────────────


def test_requested_transitions_to_running_on_step_started() -> None:
    """step.started moves the run from requested to running (AC-0327 edge 1)."""
    events = [_env(1, "run.requested"), _env(2, "step.started", _STEP_ID)]
    states = project_run_state(events)
    # Initial state is requested; after step.started it becomes running.
    assert states[-1] == "running", (
        f"after step.started, expected state 'running', got {states[-1]!r}; "
        f"full sequence: {states!r}"
    )


def test_dropping_step_started_leaves_run_at_requested() -> None:
    """Mutation-proof: without step.started the run stays at requested."""
    events = [_env(1, "run.requested")]  # step.started dropped
    states = project_run_state(events)
    assert states[-1] == "requested", (
        f"without step.started, expected state 'requested', got {states[-1]!r}"
    )


# ── AC-0327 edge 2: running → completed on run.completed ────────────────────


def test_running_transitions_to_completed_on_run_completed() -> None:
    """run.completed moves the run from running to completed (AC-0327 edge 2)."""
    events = [
        _env(1, "run.requested"),
        _env(2, "step.started", _STEP_ID),
        _env(3, "run.completed"),
    ]
    states = project_run_state(events)
    assert states[-1] == "completed", (
        f"after run.completed, expected state 'completed', got {states[-1]!r}; "
        f"full sequence: {states!r}"
    )


def test_dropping_run_completed_leaves_run_running() -> None:
    """Mutation-proof: without run.completed the run stays at running."""
    events = [
        _env(1, "run.requested"),
        _env(2, "step.started", _STEP_ID),
        # run.completed dropped
    ]
    states = project_run_state(events)
    assert states[-1] == "running", (
        f"without run.completed, expected state 'running', got {states[-1]!r}"
    )


# ── AC-0327 edge 3: running → failed on run.failed ──────────────────────────


def test_running_transitions_to_failed_on_run_failed() -> None:
    """run.failed moves the run from running to failed (AC-0327 edge 3)."""
    events = [
        _env(1, "run.requested"),
        _env(2, "step.started", _STEP_ID),
        _env(3, "run.failed"),
    ]
    states = project_run_state(events)
    assert states[-1] == "failed", (
        f"after run.failed, expected state 'failed', got {states[-1]!r}; "
        f"full sequence: {states!r}"
    )


def test_dropping_run_failed_leaves_run_running() -> None:
    """Mutation-proof: without run.failed the run stays at running."""
    events = [
        _env(1, "run.requested"),
        _env(2, "step.started", _STEP_ID),
        # run.failed dropped
    ]
    states = project_run_state(events)
    assert states[-1] == "running", (
        f"without run.failed, expected state 'running', got {states[-1]!r}"
    )


# ── Three-edge completeness ──────────────────────────────────────────────────


def test_completed_and_failed_are_distinct_terminal_states() -> None:
    """completed and failed are different states, not interchangeable.

    A projection that collapses both to the same value fails one of these,
    without needing a full two-run fixture.
    """
    completed_events = [
        _env(1, "run.requested"),
        _env(2, "step.started", _STEP_ID),
        _env(3, "run.completed"),
    ]
    failed_events = [
        _env(1, "run.requested"),
        _env(2, "step.started", _STEP_ID),
        _env(3, "run.failed"),
    ]
    assert project_run_state(completed_events)[-1] != project_run_state(failed_events)[-1], (
        "completed and failed must map to distinct terminal states"
    )
