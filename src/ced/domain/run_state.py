"""Run-state projection: fold the committed event log into a state sequence.

AC-0327 commits three edges:

  * ``requested → running`` on ``step.started``
  * ``running → completed`` on ``run.completed``
  * ``running → failed`` on ``run.failed``

The projection is deterministic and pure — no database connection is opened
here. Tests drive it from any sequence of ``EventEnvelope`` objects, and the
mutation proof drops the event append from any one committed transition and
asserts that the projection then disagrees with the snapshot.

**Why only three edges.** ``requested → claimed`` would need ``run.claimed``,
and ``running → awaiting_approval`` would need ``approval.requested`` — neither
type exists anywhere in the repository, and inventing them is an event-vocabulary
decision above this spec's authority. AC-0329 records the gap.
"""

from __future__ import annotations

from ced.domain.events import EventEnvelope

__all__ = ["apply_event", "project_run_state"]

#: The three edges AC-0327 commits. Source-state × event-type → target state.
_TRANSITIONS: dict[tuple[str, str], str] = {
    ("requested", "step.started"): "running",
    ("running", "run.completed"): "completed",
    ("running", "run.failed"): "failed",
}


def apply_event(state: str, event_type: str) -> str | None:
    """Return the next state, or ``None`` if this event commits no move.

    Returns ``None`` rather than the input state so callers can distinguish
    a committed transition from a no-op — which most events are.
    """
    return _TRANSITIONS.get((state, event_type))


def project_run_state(events: list[EventEnvelope]) -> list[str]:
    """Fold the committed event log into the sequence of states a run entered.

    Starts at ``"requested"`` (the state every run is born into) and appends
    a new entry whenever ``apply_event`` names a transition. Callers that want
    only the final state take the last element; callers asserting the full path
    compare the whole list.
    """
    state = "requested"
    states: list[str] = [state]
    for event in events:
        next_state = apply_event(state, event.type)
        if next_state is not None:
            state = next_state
            states.append(state)
    return states
