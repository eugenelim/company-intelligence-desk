"""§ Grounding probe rows 1, 3, 10 and 11 — the `Agent` surface.

Each row is asserted against behaviour or against an inspected signature, never
against `hasattr`: an attribute that exists proves nothing about the contract
the runtime depends on.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, get_type_hints

import pytest
from pydantic_ai import Agent, AgentRetries, CancellationToken, ModelRetry
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.exceptions import RunCancelled, UnexpectedModelBehavior
from pydantic_ai.models.test import TestModel
from pydantic_ai.result import StreamedRunResult
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import RunUsage


def test_agent_run_accepts_a_cancellation_token() -> None:
    """Row 1. The pool cancels a run it no longer owns, so the parameter is load-bearing.

    Signature presence alone would pass against a parameter the framework
    accepts and ignores, so the token is cancelled up front and the run is
    required to refuse.
    """
    parameter = inspect.signature(Agent.run).parameters["cancellation_token"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None

    token = CancellationToken()
    token.cancel()
    with pytest.raises(RunCancelled):
        asyncio.run(Agent(TestModel()).run("go", cancellation_token=token))


def test_the_retry_budget_type_carries_exactly_the_tool_and_output_budgets() -> None:
    """Row 3, first clause. DR9 zeroes two budgets; a third one would go unzeroed."""
    budgets = get_type_hints(AgentRetries)
    assert budgets == {"tools": int, "output": int}
    assert AgentRetries.__required_keys__ == frozenset()


def _run_with_retrying_tool(retries: AgentRetries) -> tuple[int, str]:
    """Run an agent whose only tool always asks to retry; report calls and error."""
    agent = Agent(TestModel(), retries=retries)
    calls: list[int] = []

    @agent.tool_plain
    def flaky(value: int) -> int:
        calls.append(value)
        raise ModelRetry("try again")

    with pytest.raises(UnexpectedModelBehavior) as caught:
        asyncio.run(agent.run("go"))
    return len(calls), str(caught.value)


def test_a_zero_tool_retry_budget_runs_the_tool_body_exactly_once() -> None:
    """Row 3, second clause. Zero means one attempt and no retry — counted, not configured."""
    calls, message = _run_with_retrying_tool({"tools": 0, "output": 0})
    assert calls == 1
    assert "0" in message

    retried_calls, _ = _run_with_retrying_tool({"tools": 1, "output": 0})
    assert retried_calls == 2


def test_the_two_retry_budgets_are_spent_separately() -> None:
    """Row 3, third clause. A generous output budget must not fund a tool retry."""
    calls, _ = _run_with_retrying_tool({"tools": 0, "output": 5})
    assert calls == 1


def test_a_zero_output_retry_budget_is_the_budget_in_force() -> None:
    """Row 3, fourth clause. The framework names the exhausted output budget."""
    agent = Agent(TestModel(), retries={"tools": 0, "output": 0})

    @agent.output_validator
    def reject(output: str) -> str:
        raise ModelRetry("bad output")

    with pytest.raises(UnexpectedModelBehavior) as caught:
        asyncio.run(agent.run("go"))
    assert "output retries (0)" in str(caught.value)


def test_result_usage_is_a_property_and_stream_text_debounces_by_default() -> None:
    """Row 10. Both were probe-established; no upstream document states either."""
    assert isinstance(inspect.getattr_static(AgentRunResult, "usage"), property)

    result = asyncio.run(Agent(TestModel()).run("go"))
    assert isinstance(result.usage, RunUsage)
    assert not callable(result.usage)

    debounce = inspect.signature(StreamedRunResult.stream_text).parameters["debounce_by"]
    assert isinstance(debounce.default, float)
    assert debounce.default > 0


def test_a_constructed_agent_carries_its_own_toolset_beside_the_passed_one() -> None:
    """Row 11. This is the observation AC-0202's chain walk must not root on.

    The framework adds `_AgentFunctionToolset` — the home of decorator-registered
    tools — alongside anything given through `toolsets=[...]`. A walk rooted at
    the `Agent` therefore sees a sibling that is not part of the compiled stack,
    which is why the walk roots at the compiler's own `.stack`.
    """
    passed = FunctionToolset[Any]()
    agent = Agent(TestModel(), toolsets=[passed])

    toolsets = list(agent.toolsets)
    assert any(t is passed for t in toolsets)
    siblings = [t for t in toolsets if t is not passed]
    assert siblings, "the framework no longer adds a toolset of its own"
    assert [type(t).__name__ for t in siblings] == ["_AgentFunctionToolset"]
    assert getattr(passed, "wrapped", None) is None
