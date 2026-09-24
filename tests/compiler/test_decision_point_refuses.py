"""AC-0234 — the interval's refusal is terminal, and is not `ModelRetry`.

This spec ships the decision point's position and not its predicate, so every
call is refused. AC-0234 pins the raised type in both directions: positively,
that it is the interval's own declared refusal type, because a bare exclusion
is satisfied by an `AttributeError` from a decision point nobody wired; and
negatively, that it is neither `ModelRetry` nor a subclass, because a denial
delivered as advice the model may retry turns the authorization boundary into
a negotiation.

`ModelRetry`'s identity is taken from `ced.adapters.framework_contract`, the
one place this runtime resolves framework names, so the exclusion is measured
against the same object the production code would see.

**What these checks do not establish.** They are decided against a
hand-built decision point, not against a compiled role. AC-0233 — that the
refusal holds for every role in `agent_role` and every tool in
`integration_registry`, enumerated by reading both tables — is a substrate
criterion and is not here. Neither is the permanent guard that a lookup miss
denies once a real predicate exists; that is
`walking-skeleton-authority-containment`'s AC-0235, and it cannot be decided
here because there is no lookup to miss yet.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from ced.adapters.framework_contract import FunctionToolset, ModelRetry
from ced.agents.toolsets import (
    NoCeilingEntries,
    PolicyDecisionPoint,
    ToolCallDenied,
)


def _a_stack_over_a_spy() -> tuple[PolicyDecisionPoint, list[str]]:
    """A decision point over one real tool whose body records that it ran.

    The spy is what makes "did not execute" observable rather than inferred.
    The two inner layers are left out on purpose: they are not what AC-0234
    decides, and including them would put an inert placeholder connection on
    a path this test actually drives.
    """
    executed: list[str] = []
    inner = FunctionToolset[Any]()

    def ping(value: int) -> int:
        executed.append("ping")
        return value

    inner.add_function(ping)
    return PolicyDecisionPoint(inner), executed


def test_the_declared_refusal_type_is_not_the_frameworks_retry_type() -> None:
    """The negative half of AC-0234, asserted on the class rather than an instance.

    Read on the class, a later edit that re-bases the refusal on `ModelRetry`
    reds here even if no call is ever made.
    """
    assert not issubclass(ToolCallDenied, ModelRetry)
    assert ToolCallDenied is not ModelRetry


def test_a_call_through_the_decision_point_raises_the_declared_type() -> None:
    """The positive half. Driven through a real `Agent`, so the framework's own
    dispatch is what reaches the layer, as it will in production."""
    stack, executed = _a_stack_over_a_spy()
    agent = Agent(TestModel(), toolsets=[stack])

    with pytest.raises(ToolCallDenied) as raised:
        asyncio.run(agent.run("go"))

    assert not isinstance(raised.value, ModelRetry)
    assert executed == [], "the tool body ran despite the refusal"


def test_the_refusal_names_the_tool_it_refused() -> None:
    """An operator reading the failure has to be able to tell which call died."""
    stack, _ = _a_stack_over_a_spy()
    agent = Agent(TestModel(), toolsets=[stack])

    with pytest.raises(ToolCallDenied) as raised:
        asyncio.run(agent.run("go"))

    assert "ping" in str(raised.value)


def test_a_decision_point_built_without_a_resolver_holds_the_empty_one() -> None:
    """The default is what makes the interval refuse by construction.

    A caller that forgets to pass a resolver must fail closed, so the default
    is asserted rather than left to whoever writes the compiler.
    """
    stack = PolicyDecisionPoint(FunctionToolset[Any]())
    assert isinstance(stack.resolver, NoCeilingEntries)
    assert stack.resolver.entries_admitting("anything", {}) == ()
