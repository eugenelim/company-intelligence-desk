"""The four-layer toolset stack, and the check that it is in the right order.

`worker-runtime.md` r5 § 2 *The toolset stack, innermost to outermost* fixes
the order and calls it a security property. Read outermost first:
`PolicyDecisionPoint` → `StepEventToolset` → `TrustClassToolset` →
`FunctionToolset`. The first three are this runtime's; the last is the
framework's, holding the resolved integration adapters.

The compiler is the only constructor of the stack and calls `check_stack_order`
on what it built. That checker is a function over a chain rather than a
parameter on the compiler, so stack order never reaches a caller's hands.

**A tool body does execute, and the two inner layers are reached.**
`walking-skeleton-authority-containment` ships the decidable fragment and
`walking-skeleton-policy-decision-point` decodes a stored ceiling into it,
installs the result on the decision point and supplies the step-event layer's
append behaviour. Composition and refusal are still asserted here; what an
admitted call does is asserted in `tests/authorization/`.
"""

from __future__ import annotations

from ced.agents.toolsets.policy import (
    CeilingResolver,
    NoCeilingEntries,
    PolicyDecisionNotRecorded,
    PolicyDecisionPoint,
    ToolCallDenied,
)
from ced.agents.toolsets.step_events import (
    DuplicateInvocation,
    StepContext,
    StepEventToolset,
)
from ced.agents.toolsets.structure import (
    EXPECTED_STACK_ORDER,
    StackOrderError,
    check_stack_order,
)
from ced.agents.toolsets.trust_class import ResultParser, TrustClassToolset

__all__ = [
    "EXPECTED_STACK_ORDER",
    "CeilingResolver",
    "DuplicateInvocation",
    "NoCeilingEntries",
    "PolicyDecisionNotRecorded",
    "PolicyDecisionPoint",
    "ResultParser",
    "StackOrderError",
    "StepContext",
    "StepEventToolset",
    "ToolCallDenied",
    "TrustClassToolset",
    "check_stack_order",
]
