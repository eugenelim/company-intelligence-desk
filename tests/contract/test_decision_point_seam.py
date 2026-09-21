"""§ Grounding probe row 5 — `WrapperToolset.call_tool` as the decision point.

ADR-0001 D3 puts the authorization boundary on this method. A change to its
signature or to whether the framework routes wrapped calls through it is a
change to that boundary, and the vendor need not class it as breaking, so it
is asserted here by signature *and* by interception.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset


class _Denied(Exception):
    """Stands in for the terminal refusal the decision point will raise."""


def test_call_tool_is_declared_on_the_wrapper_with_the_expected_signature() -> None:
    """Row 5, first clause. The seam must be the wrapper's own, not an inherited one.

    An inherited `call_tool` would still be overridable, but the parameters an
    override receives are the boundary's inputs — a renamed or dropped one is a
    silent change to what the decision point can decide on.
    """
    assert "call_tool" in vars(WrapperToolset)
    signature = inspect.signature(WrapperToolset.call_tool)
    assert list(signature.parameters) == ["self", "name", "tool_args", "ctx", "tool"]
    assert inspect.iscoroutinefunction(WrapperToolset.call_tool)


def test_every_wrapped_tool_call_is_routed_through_the_override() -> None:
    """Row 5, second clause. Position is the security property, so it is exercised.

    A wrapper whose override refuses must stop the wrapped tool body running.
    If the framework ever reached the inner toolset directly, the body would
    run and the spy would move.
    """
    executed: list[str] = []
    intercepted: list[str] = []

    inner = FunctionToolset[Any]()

    def ping(value: int) -> int:
        executed.append("ping")
        return value

    inner.add_function(ping)

    class Refusing(WrapperToolset[Any]):
        async def call_tool(
            self,
            name: str,
            tool_args: dict[str, Any],
            ctx: Any,
            tool: Any,
        ) -> Any:
            intercepted.append(name)
            raise _Denied(name)

    agent = Agent(TestModel(), toolsets=[Refusing(inner)])
    with pytest.raises(_Denied):
        asyncio.run(agent.run("go"))

    assert intercepted == ["ping"]
    assert executed == [], "the wrapped tool body ran despite the refusal"
