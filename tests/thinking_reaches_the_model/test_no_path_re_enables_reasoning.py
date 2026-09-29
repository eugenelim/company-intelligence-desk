"""AC-0276: no call reaching a provider is issued unless the model would disable reasoning.

The guard is ``ReasoningDisableGuard``, a capability at the ``'innermost'``
ordering tier whose ``before_model_request`` hook checks the model and settings
after all per-step model substitution and capability layering.

**Every route is driven twice against the same model** — once re-enabling
reasoning and refused, once without it and admitted — because a refusal-only
suite cannot distinguish a guard that observes the route from one that refuses
everything it fails to classify.

**The admitted case** raises ``_ModelReached`` from the sentinel model's
overridden ``request()``.  The test catches this to prove the guard admitted the
call and the model was actually invoked, without reaching the provider.

**Offline throughout.**  The sentinel is a ``BedrockConverseModel`` subclass
whose ``request()`` and ``count_tokens()`` raise ``_ModelReached`` before any
network I/O.  ``prepare_request`` and ``_build_additional_model_request_fields``
are inherited so the seam check runs against the real adapter logic.
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability, CapabilityOrdering
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelSettings
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from ced.adapters.reasoning_disable import ReasoningDisable, reasoning_disable_of
from ced.adapters.reasoning_disable_guard import (
    ReasoningDisableGuard,
    ReasoningReachesTheProvider,
)
from ced.agents.compiler import COMPILED_THINKING, compile_role

from ..compiler.role_records import a_quarantined_role
from .adapters import (
    ADAPTIVE_MODEL_ID,
    DISABLING_MODEL_ID,
    a_bedrock_model,
    a_pool_resolving_to,
    an_in_process_double,
)

# ── sentinel model ────────────────────────────────────────────────────────────


class _ModelReached(Exception):
    """The guard admitted the call and the model was invoked."""


class _GuardedSentinel(BedrockConverseModel):
    """A non-adaptive Bedrock model that raises a sentinel instead of calling the provider.

    ``prepare_request`` and ``_build_additional_model_request_fields`` are
    inherited from ``BedrockConverseModel`` so the seam check runs against the
    real adapter logic.  Only the actual provider calls are intercepted.
    """

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        raise _ModelReached("guard admitted; request() was called")

    async def count_tokens(self, *args: Any, **kwargs: Any) -> Any:
        raise _ModelReached("guard admitted; count_tokens() was called")


def _a_disabling_sentinel() -> _GuardedSentinel:
    """A sentinel on the non-adaptive family: its render carries a disable."""
    from pydantic_ai.providers.bedrock import BedrockProvider

    from .adapters import OFFLINE_KEY_ID, OFFLINE_SECRET, REGION

    provider = BedrockProvider(
        region_name=REGION,
        aws_access_key_id=OFFLINE_KEY_ID,
        aws_secret_access_key=OFFLINE_SECRET,
    )
    return _GuardedSentinel(DISABLING_MODEL_ID, provider=provider)


def _a_compiled_agent_with_sentinel() -> Any:
    """Compile a quarantined role against a sentinel model.

    The sentinel's ``prepare_request`` carries a disable, so AC-0275 passes at
    compile time.  At run time the guard sees the same model and admits it.
    """
    sentinel = _a_disabling_sentinel()
    pool = a_pool_resolving_to(sentinel, declared=())
    return compile_role(a_quarantined_role(), (), pool)


# ── innermost context-replacing capability (route 5) ─────────────────────────


@dataclass(init=False)
class _ModelReplacer(AbstractCapability[Any]):
    """A capability at the innermost tier that replaces the model in the context.

    This is the shape the bundled durable-execution capabilities use: the
    innermost tier wraps ``before_model_request`` to swap in an activity-level
    model that dispatches to a provider differently.  Used here to drive route 5.

    Listed **before** ``ReasoningDisableGuard`` in the capability sequence so
    it runs first: both are ``'innermost'``, and the combined-capability chain
    iterates in user-provided order within a tier.
    """

    replacement: Any  # Model
    _inner: list[Any] = field(default_factory=list)

    def __init__(self, replacement: Any) -> None:
        self.replacement = replacement
        self._inner = []

    def get_ordering(self) -> CapabilityOrdering:
        return CapabilityOrdering(position="innermost")

    async def before_model_request(
        self,
        ctx: Any,
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        """Replace the model with ``self.replacement`` before the guard sees it."""
        return dataclasses.replace(request_context, model=self.replacement)


# ── calibration ───────────────────────────────────────────────────────────────


def test_calibration_seam_answer_agrees_with_model_rendering() -> None:
    """The seam's answer agrees with the request the model itself builds.

    For one admitted and one refused model so a mis-probing seam cannot
    simultaneously pass both.  The guard calls the seam; this check verifies the
    seam is not internally inconsistent with the model's own behaviour.
    """
    from typing import cast

    settings = ModelSettings(thinking=COMPILED_THINKING)

    # Admitted: seam says CARRIED and the model renders {type: disabled}.
    disabling = a_bedrock_model(DISABLING_MODEL_ID)
    assert reasoning_disable_of(disabling, settings) is ReasoningDisable.CARRIED, (
        "admitted model must be CARRIED for the calibration to mean anything"
    )
    resolved, params = disabling.prepare_request(settings, ModelRequestParameters())
    rendered = disabling._build_additional_model_request_fields(
        cast(BedrockModelSettings, resolved or {}), params
    )
    assert isinstance(rendered, dict), (
        "seam reported CARRIED but _build_additional_model_request_fields returned non-dict"
    )
    assert rendered.get("thinking", {}).get("type") == "disabled", (
        "seam reported CARRIED but model's own rendering does not have {type: disabled}"
    )

    # Refused: seam says NOT_CARRIED and the model's rendering has no disable.
    adaptive = a_bedrock_model(ADAPTIVE_MODEL_ID)
    assert reasoning_disable_of(adaptive, settings) is ReasoningDisable.NOT_CARRIED, (
        "refused model must be NOT_CARRIED for the calibration to mean anything"
    )
    resolved2, params2 = adaptive.prepare_request(settings, ModelRequestParameters())
    rendered2 = adaptive._build_additional_model_request_fields(
        cast(BedrockModelSettings, resolved2 or {}), params2
    )
    assert rendered2 is None or rendered2.get("thinking", {}).get("type") != "disabled", (
        "seam reported NOT_CARRIED but model's own rendering has a disable"
    )


# ── route 1: per-run settings ─────────────────────────────────────────────────


def test_per_run_settings_that_enable_reasoning_are_refused() -> None:
    """Route 1 refused: model_settings override re-enables reasoning."""
    compiled = _a_compiled_agent_with_sentinel()

    with pytest.raises(ReasoningReachesTheProvider):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            model_settings={"thinking": True},  # overrides compiled thinking=False
            capabilities=[ReasoningDisableGuard()],
        )


def test_per_run_settings_that_do_not_enable_reasoning_are_admitted() -> None:
    """Route 1 admitted: compiled thinking=False reaches the guard unchanged."""
    compiled = _a_compiled_agent_with_sentinel()

    with pytest.raises(_ModelReached):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            # No model_settings override; compiled thinking=False is used.
            capabilities=[ReasoningDisableGuard()],
        )


# ── route 2: attached Thinking capability ─────────────────────────────────────


def test_thinking_capability_that_enables_reasoning_is_refused() -> None:
    """Route 2 refused: Thinking() capability re-enables reasoning via get_model_settings."""
    from pydantic_ai.capabilities import Thinking

    compiled = _a_compiled_agent_with_sentinel()

    # Thinking() is at default ordering (not innermost), placed before the guard.
    # Its get_model_settings() returns thinking=True, merged into the request
    # settings the guard sees.
    with pytest.raises(ReasoningReachesTheProvider):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            capabilities=[Thinking(True), ReasoningDisableGuard()],
        )


def test_no_thinking_capability_leaves_the_disable_in_place() -> None:
    """Route 2 admitted: without a Thinking() capability, the compiled disable stands."""
    compiled = _a_compiled_agent_with_sentinel()

    with pytest.raises(_ModelReached):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            capabilities=[ReasoningDisableGuard()],
        )


# ── route 3: adapter-native carrier ──────────────────────────────────────────


def test_adapter_native_carrier_that_enables_reasoning_is_refused() -> None:
    """Route 3 refused: bedrock_additional_model_requests_fields carries thinking: enabled.

    On the pin, a ``thinking`` key in the additional-fields blob suppresses the
    unified rendering (via the ``'thinking' not in existing`` guard), so an
    explicit ``{type: enabled}`` reaches the wire instead of the compiled disable.
    The seam's render detects this and returns NOT_CARRIED.
    """
    compiled = _a_compiled_agent_with_sentinel()

    # The additional-fields key suppresses the unified thinking=False rendering.
    adversarial_settings: dict[str, Any] = {
        "thinking": False,
        "bedrock_additional_model_requests_fields": {
            "thinking": {"type": "enabled", "budget_tokens": 1000}
        },
    }
    with pytest.raises(ReasoningReachesTheProvider):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            model_settings=adversarial_settings,
            capabilities=[ReasoningDisableGuard()],
        )


def test_no_adapter_native_carrier_leaves_the_disable_in_place() -> None:
    """Route 3 admitted: without an additional-fields override, the disable renders."""
    compiled = _a_compiled_agent_with_sentinel()

    with pytest.raises(_ModelReached):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            capabilities=[ReasoningDisableGuard()],
        )


# ── route 4: model substituted after compilation ──────────────────────────────


def test_model_substituted_to_adaptive_after_compilation_is_refused() -> None:
    """Route 4 refused: run_sync(model=...) substitutes a reasoning model per-step.

    The framework re-resolves the step's model from the ``model=`` argument and
    reassigns it before the capability chain runs.  A guard bound at construction
    time — or at the compiled-model level — would miss this substitution.  The
    guard at ``'innermost'`` sees the substituted model via ``request_context.model``.
    """
    compiled = _a_compiled_agent_with_sentinel()

    with pytest.raises(ReasoningReachesTheProvider):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            model=a_bedrock_model(ADAPTIVE_MODEL_ID),  # substituted after compilation
            capabilities=[ReasoningDisableGuard()],
        )


def test_model_substituted_to_disabling_after_compilation_is_admitted() -> None:
    """Route 4 admitted: substituted model still carries a disable."""
    compiled = _a_compiled_agent_with_sentinel()

    another_sentinel = _a_disabling_sentinel()
    with pytest.raises(_ModelReached):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            model=another_sentinel,  # different sentinel, same non-adaptive family
            capabilities=[ReasoningDisableGuard()],
        )


# ── route 5: capability at the innermost tier replaces context ────────────────


def test_innermost_capability_replacing_to_adaptive_model_is_refused() -> None:
    """Route 5 refused: innermost capability replaces model with adaptive.

    This is the shape the bundled durable-execution capabilities use: they sit at
    the innermost tier and swap ``request_context.model`` for a wrapper that
    dispatches through an activity or task.  A guard at a non-innermost position
    would run before this replacement and miss the substituted model.

    ``_ModelReplacer`` is listed before ``ReasoningDisableGuard`` in the
    capabilities sequence so it runs first within the innermost tier (the
    combined-capability chain iterates in user-provided order within a tier),
    placing the guard where it sees the result.
    """
    compiled = _a_compiled_agent_with_sentinel()

    with pytest.raises(ReasoningReachesTheProvider):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            capabilities=[
                _ModelReplacer(a_bedrock_model(ADAPTIVE_MODEL_ID)),  # innermost, runs first
                ReasoningDisableGuard(),  # innermost, runs second; sees replacement
            ],
        )


def test_innermost_capability_replacing_to_disabling_model_is_admitted() -> None:
    """Route 5 admitted: innermost capability replaces with a model that carries a disable."""
    compiled = _a_compiled_agent_with_sentinel()

    another_sentinel = _a_disabling_sentinel()
    with pytest.raises(_ModelReached):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            capabilities=[
                _ModelReplacer(another_sentinel),  # innermost, runs first
                ReasoningDisableGuard(),  # innermost, runs second; sees sentinel → admits
            ],
        )


# ── count_tokens is guarded by the same interception point ────────────────────


def test_count_tokens_refused_when_reasoning_is_enabled() -> None:
    """count_tokens is never called when the guard refuses.

    count_tokens runs after before_model_request but outside wrap_model_request
    (the "request-wrapping chain").  A guard in wrap_model_request would miss
    it; before_model_request precedes both.  This check proves the guard's
    interception point also covers count_tokens: it refuses before count_tokens
    runs, so the sentinel's count_tokens() override is not reached.
    """
    compiled = _a_compiled_agent_with_sentinel()

    # Guard refuses before count_tokens is called; _ModelReached is not raised.
    with pytest.raises(ReasoningReachesTheProvider):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            model_settings={"thinking": True},
            usage_limits=UsageLimits(count_tokens_before_request=True),
            capabilities=[ReasoningDisableGuard()],
        )


def test_count_tokens_admitted_when_reasoning_is_disabled() -> None:
    """count_tokens is called when the guard admits, proving the same point covers it.

    When the guard admits (CARRIED), count_tokens proceeds.  The sentinel's
    count_tokens() override raises _ModelReached, proving the call was made.
    Attribution: before_model_request at the innermost tier guards both
    request() and count_tokens() through a single refusal or admission.
    """
    compiled = _a_compiled_agent_with_sentinel()

    with pytest.raises(_ModelReached):
        compiled.agent.run_sync(
            "Return an empty list of references.",
            # count_tokens_before_request=True triggers model.count_tokens().
            usage_limits=UsageLimits(count_tokens_before_request=True),
            capabilities=[ReasoningDisableGuard()],
        )


# ── unwired-factory case ──────────────────────────────────────────────────────


def test_unwired_factory_call_is_refused() -> None:
    """A call with no resolved model (model=None) is refused by the guard.

    T6 admits a compile where the pool wired no factory (model_factory=None),
    because there is no model to interrogate at compile time.  If the agent were
    somehow invoked in that state, the guard refuses the call — reasoning_disable_of
    returns NOT_CARRIED for None, which is the safe direction.

    The test invokes the guard's before_model_request directly because the
    framework raises UserError before reaching the guard when model=None at
    run_sync level.  The guard's refusal is therefore the defence for the case
    where a model is supplied *after* compilation through a non-standard path.
    """

    async def _run() -> Any:
        guard = ReasoningDisableGuard()
        req_ctx = ModelRequestContext(
            model=None,  # type: ignore[arg-type]
            messages=[],
            model_settings=ModelSettings(thinking=COMPILED_THINKING),
            model_request_parameters=ModelRequestParameters(),
        )
        return await guard.before_model_request(None, req_ctx)  # type: ignore[arg-type]

    with pytest.raises(ReasoningReachesTheProvider):
        asyncio.run(_run())


# ── in-process double is admitted ─────────────────────────────────────────────


def test_in_process_double_is_admitted() -> None:
    """An in-process double (FunctionModel/TestModel) is admitted at run time.

    The seam positively identifies in-process doubles as reaching no provider
    (NOT_PROVIDER_BACKED).  The guard admits them without a declaration check
    at run time — unlike AC-0275, which needs the declaration because it cannot
    run the double's settings-to-request resolution, the guard has the seam's
    positive answer directly.  The same recorded residual as AC-0275 applies:
    a subclass of a double that delegates to a provider inherits the admit.
    """
    double = an_in_process_double()

    async def _run() -> Any:
        guard = ReasoningDisableGuard()
        req_ctx = ModelRequestContext(
            model=double,
            messages=[],
            model_settings=ModelSettings(thinking=COMPILED_THINKING),
            model_request_parameters=ModelRequestParameters(),
        )
        return await guard.before_model_request(None, req_ctx)  # type: ignore[arg-type]

    # No exception: the guard admits the in-process double.
    asyncio.run(_run())


# ── the wiring, as distinct from the mechanism ────────────────────────────────
#
# Every check above installs the guard itself, so all of them pass whether or
# not production installs it. Removing `capabilities=[ReasoningDisableGuard()]`
# from either real call site reds nothing among them — the mandatory security
# review of 2026-09-26 found exactly that, and it is the execution-path gap
# this delivery has now hit twice: a control the tests reach by a seam
# production does not use is a control nothing pins.
#
# These two drive the production functions themselves and install nothing.


def test_the_executors_call_site_installs_the_guard() -> None:
    """`executor._run_compiled_agent` must refuse by itself, installing nothing.

    The adversary is a compiled role whose agent carries an adaptive model —
    route 4's premise, applied at the call site. It cannot be injected through
    the function's arguments, because `_run_compiled_agent` deliberately takes
    no `model=` or `model_settings=`: T6 already guarantees the *compiled*
    model disables. So the substitution is made on the `CompiledRole` itself,
    which is what a per-step reassignment would produce.
    """
    from ced.worker.executor import _make_approval_toolset, _run_compiled_agent

    compiled = _a_compiled_agent_with_sentinel()
    substituted = dataclasses.replace(
        compiled,
        agent=Agent(
            a_bedrock_model(ADAPTIVE_MODEL_ID),
            output_type=compiled.agent.output_type,
            model_settings=ModelSettings(thinking=COMPILED_THINKING),
        ),
    )

    with pytest.raises(ReasoningReachesTheProvider):
        _run_compiled_agent(substituted, [_make_approval_toolset()])


def test_the_resume_paths_call_site_installs_the_guard() -> None:
    """`history.run_with_approval` must refuse by itself, installing nothing.

    The resumed path carries its own `run_sync`, so wiring the executor alone
    would leave a second entry to a provider call unguarded. The agent here is
    built directly rather than through `compile_role`, because T6's
    compile-time refusal would otherwise stop an adaptive model reaching this
    call site at all — and it is precisely the run path that must not rely on
    the compile path having been taken.
    """
    from pydantic_ai.toolsets import FunctionToolset

    from ced.adapters.objectstore.history import run_with_approval
    from ced.agents.tools.approval import request_approval

    agent = Agent(
        a_bedrock_model(ADAPTIVE_MODEL_ID),
        model_settings=ModelSettings(thinking=COMPILED_THINKING),
    )
    approval_toolset: FunctionToolset[Any] = FunctionToolset()
    approval_toolset.add_function(request_approval, requires_approval=True)

    # A resume needs a history to resume from; an empty one is refused by the
    # framework before the model is reached, which would make this check pass
    # for the wrong reason.
    history = [
        ModelRequest(parts=[UserPromptPart(content="resume me")]),
        ModelResponse(parts=[ToolCallPart("request_approval", {}, tool_call_id="pending-1")]),
    ]

    with pytest.raises(ReasoningReachesTheProvider):
        run_with_approval(
            agent,
            history=history,
            approval_map={"pending-1": True},
            usage_limits=UsageLimits(request_limit=2),
            output_type=[str],
            approval_toolset=approval_toolset,
        )
