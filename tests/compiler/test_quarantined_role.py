"""AC-0219 and AC-0205 — the quarantined role is constructed, not declared.

`role-configuration-seams.md` § 4: a role is quarantined exactly when its
`ceiling` is empty. Everything below reads the **compiled agent**, because the
role record is the input and the agent is the fact — a compiler that recorded
the intent and built something else would pass every assertion made against
the record.

The derivation is guarded in both directions. Left unguarded one way, a
quarantined role could declare a planning contract; unguarded the other, one
ceiling entry would silently promote it and restore the retry budgets the zero
ones exist to hold over attacker-authored text.

**The retry budgets are read off the agent's own state.** On the pinned
2.45.0 the framework keeps them as `_max_tool_retries` and
`_max_output_retries` and exposes no public reader; ADR-0002 D1 pins the
version exactly and `tests/contract/test_version_pin.py` reds on drift, which
is what makes reading them tolerable. The request-count check below is the
behavioural half and does not depend on either name.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from ced.adapters.framework_contract import FunctionToolset
from ced.agents.compiler import (
    FindingSet,
    ReferenceSelection,
    RoleCompileError,
    compile_role,
)

from .role_records import (
    CountingModel,
    a_planning_role,
    a_pool,
    a_quarantined_role,
    an_integration,
    returns_a_malformed_output,
)


def _innermost_toolset(stack: Any) -> FunctionToolset[Any]:
    """Walk the compiled chain to the layer that holds the domain tools."""
    node = stack
    while not isinstance(node, FunctionToolset):
        node = node.wrapped
    return node


def test_an_empty_ceiling_compiles_a_quarantined_role() -> None:
    """AC-0219, first half: no domain tools and the closed-vocabulary type."""
    compiled = compile_role(role=a_quarantined_role(), integrations=(), pool=a_pool())

    assert compiled.quarantined
    stack = next(t for t in compiled.agent.toolsets if t is compiled.stack)
    assert _innermost_toolset(stack).tools == {}
    assert compiled.agent.output_type is ReferenceSelection


def test_a_non_empty_ceiling_compiles_a_role_that_is_not_quarantined() -> None:
    """The contrast that makes the assertion above contentful rather than vacuous."""
    compiled = compile_role(
        role=a_planning_role(), integrations=(an_integration(),), pool=a_pool()
    )

    assert not compiled.quarantined
    assert sorted(_innermost_toolset(compiled.stack).tools) == ["fetch_filing"]
    assert compiled.agent.output_type is FindingSet


def test_an_empty_ceiling_declaring_another_output_contract_fails_to_compile() -> None:
    """Refused, never overridden: the record and the agent may not disagree."""
    role = a_quarantined_role()
    role["output_schema_ref"] = "finding-set"

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(), pool=a_pool())
    assert "reference-selection" in str(caught.value)


def test_a_non_empty_ceiling_declaring_the_quarantined_contract_fails_to_compile() -> None:
    """The other direction: one ceiling entry must not promote the role silently."""
    role = a_planning_role()
    role["output_schema_ref"] = "reference-selection"

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(an_integration(),), pool=a_pool())
    assert "non-empty ceiling" in str(caught.value)


def test_a_compiled_quarantined_role_carries_both_retry_budgets_at_zero() -> None:
    """AC-0205, first half. The budgets are the compiler's, not the record's."""
    compiled = compile_role(role=a_quarantined_role(), integrations=(), pool=a_pool())

    assert compiled.agent._max_tool_retries == 0
    assert compiled.agent._max_output_retries == 0


def test_a_malformed_output_raises_after_exactly_one_model_turn() -> None:
    """AC-0205, second half. The re-prompt over untrusted text is what must not happen."""
    model = CountingModel(returns_a_malformed_output)
    compiled = compile_role(
        role=a_quarantined_role(), integrations=(), pool=a_pool(model=model.model)
    )

    with pytest.raises(UnexpectedModelBehavior) as caught:
        asyncio.run(compiled.agent.run("go", usage_limits=compiled.limits))
    assert "output retries (0)" in str(caught.value)
    assert model.turns == [1]


def test_a_role_that_is_not_quarantined_keeps_the_frameworks_retry_default() -> None:
    """Zero is a property of the derived class, not of every compiled role.

    The planning role re-prompts once over content this system minted, which
    is r5 § 7's stated reason for leaving its budget alone — and it is what
    makes the quarantined role's single turn above a measurement rather than
    the framework's own behaviour.
    """
    model = CountingModel(returns_a_malformed_output)
    compiled = compile_role(
        role=a_planning_role(), integrations=(an_integration(),), pool=a_pool(model=model.model)
    )

    assert compiled.agent._max_tool_retries == 1
    assert compiled.agent._max_output_retries == 1
    with pytest.raises(UnexpectedModelBehavior):
        asyncio.run(compiled.agent.run("go", usage_limits=compiled.limits))
    assert model.turns == [1, 2]
