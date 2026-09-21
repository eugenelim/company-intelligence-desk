"""The structural check over a constructed toolset chain.

`worker-runtime.md` r5 § 2 fixes the order and calls it a security property:
`PolicyDecisionPoint` outermost so nothing below observes an unauthorized
call, `TrustClassToolset` innermost of the three so no layer above observes an
unparsed result.

**This is a function over a chain, not a parameter on the compiler.** The
plan's design decision is explicit about why: making the compiler accept an
ordered layer list would widen a production contract to make a test possible,
and would put stack order in a caller's hands. So the compiler builds the
chain and calls this; this is unit-tested against hand-built wrong chains,
which is what lets the ordering be asserted without the compiler ever
accepting a layer list.

**What this does not establish.** It reads composition, not behaviour. A chain
in the right order still proves nothing about what each layer decides, and it
says nothing about a tool reachable *beside* the stack — that is AC-0201, a
different defect, asserted against the constructed `Agent` rather than here.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic_ai.toolsets import AbstractToolset

from ced.adapters.framework_contract import FunctionToolset, WrapperToolset
from ced.agents.toolsets.policy import PolicyDecisionPoint
from ced.agents.toolsets.step_events import StepEventToolset
from ced.agents.toolsets.trust_class import TrustClassToolset

__all__ = ["EXPECTED_STACK_ORDER", "StackOrderError", "check_stack_order"]

#: Outermost first, matching r5 § 2 read from the `Agent` inward. `FunctionToolset`
#: is the framework's; the three above it are this runtime's.
EXPECTED_STACK_ORDER: Final[tuple[type[AbstractToolset[Any]], ...]] = (
    PolicyDecisionPoint,
    StepEventToolset,
    TrustClassToolset,
    FunctionToolset,
)


class StackOrderError(Exception):
    """A constructed chain is not the ratified four layers in the ratified order."""


def check_stack_order(stack: AbstractToolset[Any]) -> None:
    """Raise unless `stack` is exactly `EXPECTED_STACK_ORDER`, outermost first.

    Types are compared exactly rather than with `isinstance`, so a subclass
    substituted for a layer is refused: the check is about which layer sits
    where, and a subclass is free to override the very method that makes the
    position mean something.
    """
    found = _layers(stack)
    if found != EXPECTED_STACK_ORDER:
        raise StackOrderError(
            "toolset chain is not the ratified order; expected "
            f"{[layer.__name__ for layer in EXPECTED_STACK_ORDER]}, "
            f"found {[layer.__name__ for layer in found]}"
        )


def _layers(stack: AbstractToolset[Any]) -> tuple[type[AbstractToolset[Any]], ...]:
    """Walk `WrapperToolset.wrapped` outermost to innermost, collecting types.

    The walk stops at the first layer that is not a `WrapperToolset`, so a
    non-wrapper carrying an unrelated `wrapped` attribute terminates the chain
    rather than extending it. It also stops one layer past the expected depth,
    so a chain that is too deep — or one a caller made cyclic by wrapping a
    layer in itself — is reported as wrong rather than hung on.
    """
    found: list[type[AbstractToolset[Any]]] = []
    node: AbstractToolset[Any] = stack
    while len(found) <= len(EXPECTED_STACK_ORDER):
        found.append(type(node))
        if not isinstance(node, WrapperToolset):
            break
        node = node.wrapped
    return tuple(found)
