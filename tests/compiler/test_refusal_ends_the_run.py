"""AC-0259 — a refusal leaves the run, and the model is not asked again.

The decision point refuses every call in this interval. What this file adds
to AC-0234, which pins the raised *type* against a hand-built layer, is what
happens to a refusal raised inside a real `Agent.run`: it propagates out
rather than being handed back to the model as something to work around, and
no further turn is issued. Both halves matter — a framework that caught the
refusal and re-prompted would still raise eventually, and only the request
count tells the two apart.

The refusal is observed on a compiled role, because the position of the
decision point in the compiled stack is the thing that makes it unavoidable.
"""

from __future__ import annotations

import asyncio

import pytest

from ced.agents.compiler import compile_role
from ced.agents.toolsets import ToolCallDenied

from .role_records import CountingModel, a_planning_role, a_pool, calls_the_only_tool


def test_a_denied_tool_call_propagates_out_of_the_run() -> None:
    """The refusal is what the caller sees, unwrapped and unretried."""
    model = CountingModel(calls_the_only_tool)
    compiled = compile_role(
        role=a_planning_role(), integrations=(), pool=a_pool(model=model.model)
    )

    with pytest.raises(ToolCallDenied) as caught:
        asyncio.run(compiled.agent.run("go", usage_limits=compiled.limits))
    assert "fetch_filing" in str(caught.value)


def test_no_further_model_turn_is_issued_after_a_denial() -> None:
    """One turn asked for the call; nothing asked the model what to do instead."""
    model = CountingModel(calls_the_only_tool)
    compiled = compile_role(
        role=a_planning_role(), integrations=(), pool=a_pool(model=model.model)
    )

    with pytest.raises(ToolCallDenied):
        asyncio.run(compiled.agent.run("go", usage_limits=compiled.limits))
    assert model.turns == [1]
