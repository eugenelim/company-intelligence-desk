"""Hand-built toolset chains, for the structural checker's unit tests.

The checker is a function over a chain precisely so the wrong orders can be
composed by hand; these builders are that hand. They are a test helper and
never a production seam — the compiler builds the real chain and nothing here
is reachable from `src/`.

**Every layer built here is inert.** The step-event layer is handed a `None`
where its connection goes and the trust-class layer a parser that raises if
called, because no chain in this file is ever invoked: the checker reads
composition, and no tool body executes anywhere in this spec. A placeholder
that would appear to work is the failure mode these two deliberately avoid.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from ced.adapters.framework_contract import FunctionToolset
from ced.agents.toolsets import (
    PolicyDecisionPoint,
    StepContext,
    StepEventToolset,
    TrustClassToolset,
)

#: What the step path will inject once `walking-skeleton-step-lifecycle` exists.
#: Fixed values, so a chain built twice compares equal. The hex below is
#: letter-bearing on purpose: an all-digit twelve-character tail is what
#: `tools/lint-no-identifiers.py` reads as an account id, and `AGENTS.md`
#: § Security considerations asks for letter placeholders for that reason.
STEP_CONTEXT = StepContext(
    connection=cast(Any, None),
    policy_connection=cast(Any, None),
    run_id=UUID("aaaaaaaa-0000-4000-8000-00000000000a"),
    step_id=UUID("bbbbbbbb-0000-4000-8000-00000000000b"),
    lease_epoch=1,
    principal="app_worker",
    agent_role="analysis",
)


def never_parses(tool_name: str, result: Any) -> Any:
    """Stands where T3's parser will be wired. Raises, because it must not run."""
    raise AssertionError(f"no tool body executes in this spec; {tool_name!r} returned a result")


def a_function_toolset() -> FunctionToolset[Any]:
    """The framework's innermost layer, empty — composition needs no tools."""
    return FunctionToolset[Any]()


def a_step_event_layer(wrapped: Any) -> StepEventToolset:
    """The observability layer, with the step context the step path will inject."""
    return StepEventToolset(wrapped, STEP_CONTEXT)


def a_trust_class_layer(wrapped: Any) -> TrustClassToolset:
    """The innermost wrapped layer, with the parser seam T3 fills."""
    return TrustClassToolset(wrapped, never_parses)


def the_ratified_chain() -> PolicyDecisionPoint:
    """r5 § 2's four layers in r5 § 2's order."""
    return PolicyDecisionPoint(a_step_event_layer(a_trust_class_layer(a_function_toolset())))
