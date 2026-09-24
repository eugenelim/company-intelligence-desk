"""Whether the request a resolved model would send carries a reasoning disable.

AC-0275 and AC-0276 ask one question of a model: would the request it sends
carry a **provider-level** disable? On the pinned `pydantic-ai` 2.45.0 the
compiled `thinking=False` is dropped before the wire by several independent
layers, so nothing above this module can answer it by reading a setting.

**The answer is produced by running the model's own settings-to-request
resolution**, never by restating the rule that resolution applies. The probe is
`Model.prepare_request` followed by the adapter's own additional-fields build,
which is the pair of steps that decides the rendering: `prepare_request` is
where an explicit `False` is discarded on an always-thinking profile and where
a profile declaring neither thinking flag never carries the value across at
all, and the fields build is where the surviving value becomes provider JSON.
A check that reads the renderer alone skips the first step and drifts at the
next version pin.

**This is the only module that names a provider's rendering**, which is what
keeps `agents/` free of provider knowledge: r5 § 2 R3 and
`ced.agents.models`'s "nothing here knows what a Bedrock model is" both forbid
the compiler resolving this question itself.

**It fails closed, and the direction of that is the whole control.** Any error
inside the model's own resolution, and any rendering that is not an
affirmative disable, answer `NOT_CARRIED`. `NOT_PROVIDER_BACKED` is reported
only for a model this module **positively identifies** as one of the
framework's in-process doubles, because that is the single answer the
deployment's non-provider declaration may admit.

**An earlier build classified by the absence of provider knowledge** — "not
the one adapter class I know, therefore nothing to disable, therefore
admissible" — which is the fail-open AC-0275 exists to refuse. It admitted a
`WrapperModel` around a live Bedrock adapter, the shape instrumentation
ships, and any second provider's adapter. Wrappers are now unwrapped first
and anything neither rendered nor proved local is refused.

**Residual, stated because it is not closed:** identification is by class, so
a *subclass* of an in-process double that delegates to a provider inherits the
admit. Reaching it takes deliberate code inside the deployment's own
`model_factory` plus a matching declaration, and an exact-type test would
refuse the legitimate local subclasses this repository already uses.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import cast

from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelSettings
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

__all__ = ["MAX_WRAPPER_DEPTH", "ReasoningDisable", "reasoning_disable_of"]

log = logging.getLogger(__name__)

#: The key the Bedrock Anthropic branch renders the unified setting into, and
#: the value that branch emits for an affirmative disable. Named here and
#: nowhere else in the package.
_THINKING_FIELD = "thinking"
_DISABLED_TYPE = "disabled"

#: How far the seam will descend a `WrapperModel` chain before giving up and
#: refusing. Shipped wrappers nest one or two deep; the bound exists so a
#: cycle cannot hang compilation rather than to express a real limit.
MAX_WRAPPER_DEPTH = 16


class ReasoningDisable(Enum):
    """What the request a model would send says about reasoning.

    Three answers rather than two, because "the seam has no provider knowledge
    of this class" is not the same claim as "this model would reason" and the
    deployment's non-provider declaration is applied to exactly one of them.
    """

    #: The rendered request carries an affirmative provider-level disable.
    CARRIED = "carried"
    #: The rendered request carries reasoning enabled or adaptive, or carries
    #: nothing at all. Also the answer for any error inside the resolution.
    NOT_CARRIED = "not-carried"
    #: The model is one of the framework's in-process doubles, so it reaches
    #: no provider and there is nothing for a disable to be carried in. This
    #: is the **only** answer the deployment's non-provider declaration may
    #: admit, and it is deliberately a positive identification rather than
    #: "not a class this module knows": a model this module cannot render but
    #: cannot prove local answers `NOT_CARRIED` and is refused.
    NOT_PROVIDER_BACKED = "not-provider-backed"


def reasoning_disable_of(model: Model, settings: ModelSettings) -> ReasoningDisable:
    """Run `model`'s own resolution of `settings` and classify what it renders.

    `settings` is the settings the request would actually carry — the compiled
    role's at compile time, the call's resolved settings at run time — so the
    answer is about the request in hand and not about what the model could be
    asked to do.

    Issues no provider call and needs no credential: both steps are local to
    the adapter instance.
    """
    # **Unwrap first.** A `WrapperModel` is a different class from the adapter
    # it wraps, so a test against the adapter class alone answers "not this
    # class" for a model that does reach a provider. Classifying by identity
    # with one concrete class is what let a wrapped Bedrock adapter read as a
    # local fixture. `InstrumentedModel` is this shape; **`FallbackModel` is
    # not** — measured on the pin it holds a `models` list rather than a
    # `wrapped` attribute, so the loop never descends a fallback chain and
    # such a model is classified by the fallback object itself. That falls
    # through to refusal, which is the safe direction, but it means a
    # legitimate fallback configuration cannot compile: a stated residual,
    # not coverage.
    # Bounded: a wrapper chain is a handful deep in practice, and a cyclic one
    # would otherwise hang role compilation with no timeout and no log line.
    # Exhausting the bound falls through to the refusal below rather than
    # returning, so an unreadable chain is never admitted.
    for _ in range(MAX_WRAPPER_DEPTH):
        if not isinstance(model, WrapperModel):
            break
        model = model.wrapped

    # The positive test, and the direction of the remaining `else` is the
    # whole control: only a model identified as an in-process double may be
    # admitted by the declaration. Anything this module cannot render and
    # cannot prove local — another provider's adapter, or a double the
    # framework adds later — falls through to `NOT_CARRIED` and is refused.
    if isinstance(model, FunctionModel | TestModel):
        return ReasoningDisable.NOT_PROVIDER_BACKED
    if not isinstance(model, BedrockConverseModel):
        return ReasoningDisable.NOT_CARRIED

    try:
        resolved, parameters = model.prepare_request(settings, ModelRequestParameters())
        # The adapter's own build, reached on its own settings type. Private on
        # the pin, which is the whole reason this module exists: no layer above
        # `adapters/` may name it.
        rendered = model._build_additional_model_request_fields(
            cast(BedrockModelSettings, resolved or {}), parameters
        )
    except Exception:
        # Fail closed: a probe that cannot be answered is not a disable. The
        # exception is recorded rather than dropped, because the refusal the
        # caller raises reads as a statement about the model, and a signature
        # drift on the private build above is a statement about the pin.
        log.warning(
            "reasoning-disable probe failed for %s; refusing as though no disable were carried",
            type(model).__name__,
            exc_info=True,
        )
        return ReasoningDisable.NOT_CARRIED

    if not isinstance(rendered, dict):
        return ReasoningDisable.NOT_CARRIED
    entry = rendered.get(_THINKING_FIELD)
    if isinstance(entry, dict) and entry.get("type") == _DISABLED_TYPE:
        return ReasoningDisable.CARRIED
    return ReasoningDisable.NOT_CARRIED
