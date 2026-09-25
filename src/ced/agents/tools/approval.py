"""The contentless approval gate, per DR1.

``request_approval`` is the agent's only suspension lever.  Its body never
runs: ``pydantic_ai`` intercepts any call to a ``requires_approval=True``
tool and returns a ``DeferredToolRequests`` instead of delegating.  The
function exists only to name the gate; it carries no payload so the agent
cannot choose what gets published.

The executor injects this function into a ``FunctionToolset`` at run time
(``toolsets=[...]`` on ``run_sync``), keeping it outside the compiled stack
and therefore outside the policy decision point's authority check.  That
placement is deliberate: approval is an interrupt delivered by the framework
layer, not a tool the ceiling bounds.
"""

from __future__ import annotations

__all__ = ["request_approval"]


def request_approval() -> None:
    """Signal that this step requires human approval before proceeding.

    The body never executes.  The executor injects this function into a
    ``FunctionToolset`` with ``requires_approval=True`` at run time; the
    framework intercepts the call and suspends the run with a
    ``DeferredToolRequests`` output.
    """
