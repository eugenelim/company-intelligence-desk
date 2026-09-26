"""Run-path guard: refuse any provider-bound model call that lacks a reasoning disable.

AC-0276. Installed as a capability at the ``'innermost'`` ordering tier so that
``before_model_request`` sees the model and settings **after** all per-step
model substitution and capability layering.

**The guard covers both provider-reaching methods of ``BedrockConverseModel``
on the pin (``request`` and ``count_tokens``) through one interception point.**
``before_model_request`` runs before both calls: if the guard refuses it raises
and neither method is reached; if it admits, both are allowed to proceed.
A guard placed inside ``wrap_model_request`` would miss ``count_tokens``, which
runs outside that chain — the reason this placement is chosen and recorded.

**Placement at ``'innermost'`` is the key property.** An outer capability's
``before_model_request`` can replace the model or settings in the context, and
the guard sees the replacement because it runs last in the chain. A guard at a
non-innermost tier is bypassed by any innermost capability that replaces the
model after the guard's hook returns.

**The observable is the seam's answer, not ``ModelRequestParameters.thinking``.**
``ModelRequestParameters.thinking`` is assigned at one site gated on the unified
key surviving the merge and is ``False`` while an adaptive profile renders
nothing — reading it would go green while the provider reasons, the defect this
guard inherits from AC-0275 and may not repeat.

**Residual, stated because it is not closed.** A capability's
``wrap_model_request`` that replaces the model *after* ``before_model_request``
has run is not seen by this guard. The framework's bundled durable-execution
capabilities use ``before_model_request`` for model replacement on this pin, so
this residual does not apply to Phase 1's deployment. A guard sitting inside
``wrap_model_request`` at the innermost tier would close this residual but would
miss ``count_tokens``, trading one gap for another; closing both simultaneously
requires an interception point that the framework does not expose on this pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, CapabilityOrdering
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.settings import ModelSettings

from ced.adapters.reasoning_disable import ReasoningDisable, reasoning_disable_of

__all__ = ["ReasoningDisableGuard", "ReasoningReachesTheProvider"]


class ReasoningReachesTheProvider(Exception):
    """Raised when a model call would reach a provider that has not disabled reasoning.

    The message names the model class and the seam's answer so an operator's
    log identifies the cause rather than seeing a generic refusal.
    """


@dataclass(init=False)
class ReasoningDisableGuard(AbstractCapability[Any]):
    """Refuse any provider-reaching model call whose request would not disable reasoning.

    Placed at the ``'innermost'`` ordering tier so ``before_model_request``
    sees the final model and settings — after per-step substitution and all
    other capability layering — before either ``request()`` or ``count_tokens()``
    is called.

    The guard calls the same ``adapters/`` seam as the compile-time check
    (AC-0275) and does not re-derive the answer itself. A seam guard with its
    own rendering logic would be the restatement AC-0275's criterion forbids,
    running in production.

    Fails closed: an unrecognised model or a probe that raises is refused.
    In-process doubles (``FunctionModel``, ``TestModel``) are admitted because
    the seam positively identifies them as reaching no provider, on the same
    recorded residual as AC-0275 (a delegating subclass inherits the admit).
    """

    def get_ordering(self) -> CapabilityOrdering:
        """Place at the innermost tier so per-step substitution is already applied."""
        return CapabilityOrdering(position="innermost")

    async def before_model_request(
        self,
        ctx: RunContext[Any],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        """Refuse any call that would not send a provider-level reasoning disable.

        Called with the model and settings as the invoked model actually receives
        them, after all capability layering and per-step model substitution.
        The seam is asked with ``request_context.model_settings``, not with the
        compile-time probe value, so the answer is about this specific call.

        Raises ``ReasoningReachesTheProvider`` if the seam answers ``NOT_CARRIED``
        or raises an internal error.  Returns the context unchanged for ``CARRIED``
        and ``NOT_PROVIDER_BACKED``.
        """
        model = request_context.model
        settings = request_context.model_settings or ModelSettings()

        result = reasoning_disable_of(model, settings)

        if result is ReasoningDisable.CARRIED:
            return request_context

        if result is ReasoningDisable.NOT_PROVIDER_BACKED:
            # Positive identification as an in-process double: no provider to
            # send anything to, so there is nothing for a disable to be carried
            # in.  Admitted on the same recorded residual as AC-0275: a subclass
            # of a double that delegates to a provider inherits the admit.
            return request_context

        # NOT_CARRIED: the model would not disable reasoning, or the probe
        # failed internally (reasoning_disable_of logs the failure and returns
        # NOT_CARRIED so the guard sees a consistent refusal).
        raise ReasoningReachesTheProvider(
            f"model {type(model).__name__!r} would not send a provider-level "
            f"reasoning disable (seam answered {result.value!r}); "
            f"call refused before reaching the provider"
        )
