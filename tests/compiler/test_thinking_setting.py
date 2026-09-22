"""AC-0204 — `thinking` is `False` where the model reads it, and nowhere else.

**The observation is at the model boundary, not on the carrier.** A compiler
that computes the value and constructs the `Agent` without it would be green
against `CompiledRole` while the provider reasons, so what is asserted below
is what a stub model was handed during a real run.

**Where 2.45.0 puts that value is not where the criterion's wording expects.**
`Model.prepare_request` resolves `ModelSettings['thinking']` into
`ModelRequestParameters.thinking` and **strips the key from the settings the
model's `request` receives** — and it carries the value across when the
profile declares `supports_thinking` **or** `thinking_always_enabled`, except
that an explicit `False` is dropped on an always-thinking profile, because a
model that cannot stop reasoning gets no instruction to. So the settings a model
receives never carry the key on this version, and the model-boundary fact is
`model_request_parameters.thinking`. The stub below declares a profile that
supports thinking, which is what makes the resolved value observable at all.
A profile declaring neither thinking flag would not leave the assertion true
for the wrong reason — it would fail it, because `prepare_request` never
assigns the value and the resolved field stays at its `None` default. That is
its own hole rather than a test artefact: the compiler's `False` reaches
nothing on such a profile, and the spec carries it as a Follow-on with a
register entry.

**Omitting the key is not sufficient either.** `ModelSettings.thinking` is
`bool | Literal['minimal', 'low', 'medium', 'high', 'xhigh']` on a `total=False`
TypedDict, so an omitted key leaves the provider's own default in force. The
compiler therefore *sets* the value on every compiled role and refuses a role
declaring any other — which is why the two checks below differ only in whether
the record mentions `thinking`, and expect the same answer.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles import ModelProfile

from ced.agents.compiler import RoleCompileError, compile_role

from .role_records import a_pool, a_quarantined_role, returns_an_empty_selection


def thinking_the_model_received(role: dict[str, Any]) -> Any:
    """Run one compiled role against a stub model and return its resolved value."""
    seen: list[Any] = []

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info.model_request_parameters.thinking)
        return returns_an_empty_selection(info)

    model = FunctionModel(reply, profile=ModelProfile(supports_thinking=True))
    compiled = compile_role(role=role, integrations=(), pool=a_pool(model=model))
    asyncio.run(compiled.agent.run("go", usage_limits=compiled.limits))

    assert len(seen) == 1, "the stub model was not asked for exactly one request"
    return seen[0]


def test_the_stub_model_receives_thinking_as_false_when_the_role_declares_it() -> None:
    """The declared-and-admitted case, read where the provider would read it."""
    assert (
        thinking_the_model_received(a_quarantined_role(settings={"thinking": False})) is False
    )


def test_the_stub_model_receives_thinking_as_false_when_the_role_omits_it() -> None:
    """The compiler sets the key; it does not merely admit a role that set it.

    This is the case an omission would leave to the provider's default, and
    the one a settings-forwarding compiler fails.
    """
    assert thinking_the_model_received(a_quarantined_role()) is False


@pytest.mark.parametrize("declared", [True, "low", "minimal", 1, None])
def test_a_role_declaring_any_other_thinking_value_fails_to_compile(declared: Any) -> None:
    """Every other value the framework's `ThinkingLevel` admits, refused."""
    role = a_quarantined_role(settings={"thinking": declared})

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(), pool=a_pool())

    assert "thinking" in str(caught.value)
