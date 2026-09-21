"""The four-layer toolset stack, and the check that it is in the right order.

`worker-runtime.md` r5 § 2 *The toolset stack, innermost to outermost* fixes
the order and calls it a security property. Read outermost first:
`PolicyDecisionPoint` → `StepEventToolset` → `TrustClassToolset` →
`FunctionToolset`. The first three are this runtime's; the last is the
framework's, holding the resolved integration adapters.

The compiler is the only constructor of the stack and calls `check_stack_order`
on what it built. That checker is a function over a chain rather than a
parameter on the compiler, so stack order never reaches a caller's hands.

**What this package does not establish.** Nothing here executes a tool body.
The decision point refuses every call until
`walking-skeleton-authority-containment` supplies the containment predicate,
so the two inner layers' `call_tool` bodies are unreached by contract rather
than by omission, and this package's suite asserts composition and refusal
only.
"""

from __future__ import annotations

from ced.agents.toolsets.policy import (
    CeilingResolver,
    NoCeilingEntries,
    PolicyDecisionPoint,
    ToolCallDenied,
)
from ced.agents.toolsets.step_events import StepEventToolset
from ced.agents.toolsets.structure import (
    EXPECTED_STACK_ORDER,
    StackOrderError,
    check_stack_order,
)
from ced.agents.toolsets.trust_class import ResultParser, TrustClassToolset

__all__ = [
    "EXPECTED_STACK_ORDER",
    "CeilingResolver",
    "NoCeilingEntries",
    "PolicyDecisionPoint",
    "ResultParser",
    "StackOrderError",
    "StepEventToolset",
    "ToolCallDenied",
    "TrustClassToolset",
    "check_stack_order",
]
