"""AC-0202, second predicate — the structural check rejects a wrong chain.

AC-0202 is two predicates under one checkbox, and the spec's § Open questions
records that split. The first predicate walks a real `CompiledRole.stack`;
that one belongs to the compiler and is not decided here. This file decides
the second: the checker, exercised against hand-built chains, is what lets the
ordering be asserted without the compiler ever accepting an ordered layer
list. The plan's § Design decisions rules that parameter out because it would
widen a production contract to make a test possible.

**What these checks do not establish.** They read composition, not behaviour.
None of these chains is invoked, and none could be — no tool body executes
anywhere in this spec. That no tool is reachable *beside* the stack is
AC-0201, a different defect asserted against the constructed `Agent`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from ced.adapters.framework_contract import FunctionToolset
from ced.agents.toolsets import (
    EXPECTED_STACK_ORDER,
    PolicyDecisionPoint,
    StackOrderError,
    StepEventToolset,
    TrustClassToolset,
    check_stack_order,
)

from .toolset_chains import (
    STEP_CONTEXT,
    a_function_toolset,
    a_step_event_layer,
    a_trust_class_layer,
    never_parses,
    the_ratified_chain,
)


def test_the_expected_order_is_the_one_r5_ratified() -> None:
    """r5 § 2, read outermost first. Pinned so a reordering is a visible diff.

    The layers are compared as class objects, not as name strings, so renaming
    one reds on behaviour rather than on spelling.
    """
    assert EXPECTED_STACK_ORDER == (
        PolicyDecisionPoint,
        StepEventToolset,
        TrustClassToolset,
        FunctionToolset,
    )


def test_the_ratified_order_is_accepted() -> None:
    """The control.

    Without it, every rejection below is also satisfied by a checker that
    refuses everything.
    """
    check_stack_order(the_ratified_chain())


@pytest.mark.parametrize(
    "build_chain",
    [
        pytest.param(
            lambda: PolicyDecisionPoint(
                TrustClassToolset(a_step_event_layer(a_function_toolset()), never_parses)
            ),
            id="trust-class-above-step-events",
        ),
        pytest.param(
            lambda: StepEventToolset(
                PolicyDecisionPoint(a_trust_class_layer(a_function_toolset())),
                **STEP_CONTEXT,
            ),
            id="decision-point-not-outermost",
        ),
        pytest.param(
            lambda: a_step_event_layer(a_trust_class_layer(a_function_toolset())),
            id="decision-point-absent",
        ),
        pytest.param(
            lambda: PolicyDecisionPoint(a_step_event_layer(a_function_toolset())),
            id="trust-class-absent",
        ),
        pytest.param(
            lambda: PolicyDecisionPoint(a_trust_class_layer(a_function_toolset())),
            id="step-events-absent",
        ),
        pytest.param(
            lambda: PolicyDecisionPoint(
                a_step_event_layer(
                    a_trust_class_layer(a_step_event_layer(a_function_toolset()))
                )
            ),
            id="one-layer-too-deep",
        ),
        pytest.param(a_function_toolset, id="no-wrapping-at-all"),
    ],
)
def test_a_chain_in_any_other_composition_is_rejected(
    build_chain: Callable[[], Any],
) -> None:
    """Each case is a composition the compiler must never produce.

    `decision-point-not-outermost` is the one the security property is about:
    every ratified layer is present, and the decision point still cannot see a
    call the step-event layer has already recorded.
    """
    with pytest.raises(StackOrderError):
        check_stack_order(build_chain())


def test_the_refusal_names_both_the_expected_and_the_found_order() -> None:
    """An operator reading the failure has to be able to see which layer moved."""
    with pytest.raises(StackOrderError) as raised:
        check_stack_order(a_step_event_layer(a_function_toolset()))
    message = str(raised.value)
    assert "PolicyDecisionPoint" in message
    assert "StepEventToolset" in message


def test_a_subclass_substituted_for_a_layer_is_refused() -> None:
    """Exact types, not `isinstance`.

    A subclass is free to override the very method that makes a position mean
    something, so a chain that merely *derives from* the decision point is not
    the ratified chain.
    """

    class WiderDecisionPoint(PolicyDecisionPoint):
        pass

    chain = WiderDecisionPoint(a_step_event_layer(a_trust_class_layer(a_function_toolset())))
    with pytest.raises(StackOrderError):
        check_stack_order(chain)
