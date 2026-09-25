"""Real and stand-in models for the reasoning-disable checks.

**The Bedrock adapter here is the real one, and it is constructed with
explicit placeholder credentials so that building it emits no network I/O.**
A region name alone is not enough: boto3 walks the AWS credential chain when
the client is built, which on this machine attempts outbound connections to
the EC2 instance-metadata address `169.254.169.254`. On a cloud runner that
silently pulls instance-role credentials into a suite that needs none, and on
a network that blackholes the address it hangs the offline gate for seconds
per construct. Supplying the keys below short-circuits the chain: measured
2026-09-24, construction goes from two metadata connects and 2.2 s to **zero
connects and 0.5 s**. The seam still issues no provider call.

**The model ids are provider-prefixed, and that is load-bearing.** A bare
family name such as `claude-sonnet-4-5` is not a constructor argument but the
prefix a Bedrock id resolves *to*: given the bare name the id split yields no
provider, the profile lookup misses, and the rendered request carries no
thinking key at all — byte-identical to what an adaptive family renders for a
disable. A pair built from bare names would therefore decide its admitted half
through the no-profile refusal rather than through the rendering it exists to
calibrate.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers.bedrock import BedrockModelProfile, BedrockProvider

from ..compiler.role_records import a_pool

#: Any region. The adapter reads it to build a client it never calls.
REGION = "us-east-1"

#: Placeholder credentials, present only to stop boto3 walking the credential
#: chain while the client is built. They authenticate nothing: no request is
#: ever issued with them, and the seam reaches no provider.
OFFLINE_KEY_ID = "offline-probe-not-a-secret"
OFFLINE_SECRET = "offline-probe-not-a-secret"


def _offline_provider() -> BedrockProvider:
    """A provider whose client construction touches no network."""
    return BedrockProvider(
        region_name=REGION,
        aws_access_key_id=OFFLINE_KEY_ID,
        aws_secret_access_key=OFFLINE_SECRET,
    )


#: Non-adaptive on the pin: its request carries `{'thinking': {'type':
#: 'disabled'}}` for the compiled setting, so it is the admitted half.
DISABLING_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

#: Adaptive on the pin: the adaptive branch has no `else`, so a disable
#: renders nothing and this is the refused half.
ADAPTIVE_MODEL_ID = "us.anthropic.claude-sonnet-5"

#: A bare family name, which resolves to no profile. Refused, never read as a
#: fixture: an unrecognised real model id resolves to no profile too.
NO_PROFILE_MODEL_ID = "claude-sonnet-4-5"


def a_bedrock_model(model_id: str) -> BedrockConverseModel:
    """The real adapter for `model_id`, built from a region name alone."""
    return BedrockConverseModel(model_id, provider=_offline_provider())


class _ResolutionRaises(BedrockConverseModel):
    """A model the seam does interrogate, whose own resolution then fails."""

    def prepare_request(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the framework moved under the pin")


def a_model_whose_resolution_raises() -> BedrockConverseModel:
    """The error path, on a class the seam has provider knowledge of."""
    return _ResolutionRaises(DISABLING_MODEL_ID, provider=_offline_provider())


def an_in_process_double() -> FunctionModel:
    """A model the seam positively identifies as reaching no provider.

    The ordinary shape of a test double, and the only shape the deployment's
    non-provider declaration admits. Named for what the seam proves about it
    rather than for what it fails to recognise: an earlier build classified by
    *absence* of provider knowledge, which is what let a wrapped live adapter
    read as a fixture.
    """

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise AssertionError("no check here runs the model")

    return FunctionModel(respond)


def a_pool_resolving_to(model: Any, *, declared: tuple[str, ...]) -> dict[str, Any]:
    """A pool whose factory does resolve the role's model id to `model`.

    `declared` is the deployment's `non_provider_model_ids`, passed explicitly
    at every call site here because which ids it holds is what several of
    these checks turn on.
    """
    return a_pool(model=model, non_provider_model_ids=declared)


class _AlwaysThinking(BedrockConverseModel):
    """A Bedrock adapter on an always-thinking profile.

    **This is the fixture that separates the seam from a restatement of the
    rendering rule.** On an always-thinking profile `Model.prepare_request`
    *discards* an explicit `thinking=False` — a model that cannot stop
    reasoning gets no instruction to — so the parameters it returns carry no
    thinking value and the adapter renders nothing. A check that skipped
    `prepare_request` and handed the renderer a value it built itself would
    see `False`, render `{'thinking': {'type': 'disabled'}}`, and admit a
    model that will reason.

    No Bedrock Anthropic profile sets `thinking_always_enabled` on the pin,
    which the plan records as a property of the pin rather than of the guard.
    Declaring one here is what makes the divergence observable now instead of
    at whichever version introduces it.
    """

    @property
    def profile(self) -> Any:
        return BedrockModelProfile(
            bedrock_thinking_variant="anthropic",
            bedrock_supports_adaptive_thinking=False,
            supports_thinking=True,
            thinking_always_enabled=True,
        )


def a_model_that_cannot_stop_thinking() -> BedrockConverseModel:
    """A provider-backed model whose profile discards an explicit disable."""
    return _AlwaysThinking(DISABLING_MODEL_ID, provider=_offline_provider())


def a_wrapper_around(model: Model) -> WrapperModel:
    """A `WrapperModel` over `model`, the shape instrumentation ships in.

    `InstrumentedModel` is this shape, and it is the one instrumentation
    ships. **`FallbackModel` is not** — measured on the pin,
    `issubclass(FallbackModel, WrapperModel)` is `False`; it holds a `models`
    list rather than a `wrapped` attribute, so the unwrap never descends into
    a fallback chain and such a model is classified by the fallback object
    itself. That direction is safe — it falls through to refusal — but it is a
    stated residual, not coverage: a legitimate fallback configuration cannot
    compile until the seam learns to read one.

    The seam must classify by what a wrapper wraps: a wrapper is a different
    class from the adapter inside it, so a test against the adapter class
    alone reads a live provider model as a local double.
    """
    return WrapperModel(model)


class _AnotherProvidersAdapter(Model):
    """A provider adapter this seam has no rendering knowledge of.

    Stands in for an OpenAI, Anthropic-direct or Google adapter — none of
    which is installed, since only the `[bedrock]` extra is pinned. What makes
    it useful is exactly that the seam cannot render it: it must still be
    refused rather than read as a fixture.
    """

    @property
    def model_name(self) -> str:
        return "some-other-provider-model"

    @property
    def system(self) -> str:
        return "some-other-provider"

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no check here runs the model")


def another_providers_adapter() -> Model:
    """A model that reaches a provider the seam cannot interrogate."""
    return _AnotherProvidersAdapter()
