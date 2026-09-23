"""AC-0201 — no tool is reachable outside the wrapped stack.

Asserted against the **constructed `Agent`**, which is where the defect can
hide: `tests/contract/test_agent_surface.py` pins that the framework adds its
own `_AgentFunctionToolset` beside anything passed, and a tool registered
there has no ceiling entry to violate. AC-0202's walk roots at
`CompiledRole.stack` and never reaches the `Agent`, so it cannot absorb this.

The two cases the criterion names are hand-built agents rather than compiled
ones, for the same reason the stack-order checker is unit-tested against
hand-built chains: `compile_role` is the only constructor of the agent, so it
offers no way to ask for a decorator tool or a second toolset. The two checks
at the end are what stop that being a gap — they hold the delegation, so a
compiler that stopped calling either structural check reds here rather than
shipping unguarded.
"""

from __future__ import annotations

from typing import Any

import pytest

from ced.adapters.framework_contract import Agent, FunctionToolset
from ced.agents import compiler
from ced.agents.compiler import SoleToolsetError, check_sole_toolset, compile_role
from ced.agents.toolsets import PolicyDecisionPoint, TrustClassToolset
from ced.domain.quarantine.parser import parse_integration_result

from .role_records import a_planning_role, a_pool, an_integration


def a_compiled_agent() -> Any:
    """One compiled planning role, which binds a single domain tool."""
    return compile_role(role=a_planning_role(), integrations=(an_integration(),), pool=a_pool())


def test_a_compiled_agent_reaches_no_tool_outside_the_stack() -> None:
    """The agent carries the stack and one empty framework toolset, nothing else."""
    compiled = a_compiled_agent()

    toolsets = list(compiled.agent.toolsets)
    assert sum(1 for toolset in toolsets if toolset is compiled.stack) == 1
    siblings = [toolset for toolset in toolsets if toolset is not compiled.stack]
    assert [type(toolset).__name__ for toolset in siblings] == ["_AgentFunctionToolset"]
    assert not siblings[0].tools, "the framework toolset holds a tool the ceiling cannot govern"


def test_the_roles_tool_is_reachable_only_inside_the_stack() -> None:
    """The bound tool lives on the innermost layer, under the decision point."""
    compiled = a_compiled_agent()

    node = compiled.stack
    while not isinstance(node, FunctionToolset):
        node = node.wrapped
    assert sorted(node.tools) == ["fetch_filing"]


def test_the_trust_class_layer_holds_the_real_parser() -> None:
    """The compiler wires the quarantine boundary itself into `parse_result`.

    An identity assertion, not a behavioural one. `TrustClassToolset.call_tool`
    is unentered by contract in this spec, so nothing else here would notice
    the compiler passing a pass-through in place of the boundary. The seam is
    driven in `walking-skeleton-policy-decision-point`'s AC-0247, which is the
    first criterion anywhere to run a tool body and read what the layer does
    with its return.
    """
    compiled = a_compiled_agent()

    node = compiled.stack
    while not isinstance(node, TrustClassToolset):
        node = node.wrapped
    assert node.parse_result is parse_integration_result


def test_a_decorator_registered_tool_fails_the_build() -> None:
    """A tool on the agent itself is outside every ceiling, so the build refuses."""
    compiled = a_compiled_agent()
    agent: Agent[None, Any] = Agent(toolsets=[compiled.stack])

    @agent.tool_plain
    def sideband(cik: str) -> str:
        raise AssertionError("no tool body executes in this spec")

    with pytest.raises(SoleToolsetError) as caught:
        check_sole_toolset(agent, compiled.stack)
    assert "sideband" in str(caught.value)


def test_a_second_toolset_entry_fails_the_build() -> None:
    """A toolset passed beside the stack is reachable and ungoverned."""
    compiled = a_compiled_agent()
    beside = FunctionToolset[Any]()
    agent: Agent[None, Any] = Agent(toolsets=[compiled.stack, beside])

    with pytest.raises(SoleToolsetError):
        check_sole_toolset(agent, compiled.stack)


def test_a_stack_that_is_not_the_decision_point_fails_the_build() -> None:
    """R5's first invariant is that the one toolset *is* the decision point."""
    agent: Agent[None, Any] = Agent()
    with pytest.raises(SoleToolsetError):
        check_sole_toolset(agent, FunctionToolset[Any]())


def test_the_compiler_checks_the_agent_it_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reachability check runs on the build, not only in this file."""
    seen: list[tuple[Any, Any]] = []
    monkeypatch.setattr(
        compiler, "check_sole_toolset", lambda agent, stack: seen.append((agent, stack))
    )

    compiled = compile_role(
        role=a_planning_role(), integrations=(an_integration(),), pool=a_pool()
    )

    assert len(seen) == 1
    assert seen[0][0] is compiled.agent
    assert seen[0][1] is compiled.stack


def test_the_compiler_checks_the_order_of_the_chain_it_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compiler calls the structural checker; it does not assume its own output."""
    seen: list[Any] = []
    monkeypatch.setattr(compiler, "check_stack_order", seen.append)

    compiled = compile_role(
        role=a_planning_role(), integrations=(an_integration(),), pool=a_pool()
    )

    assert seen == [compiled.stack]
    assert isinstance(compiled.stack, PolicyDecisionPoint)
