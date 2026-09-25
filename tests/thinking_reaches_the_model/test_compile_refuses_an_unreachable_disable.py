"""AC-0275: compiling refuses a model that would not disable reasoning.

Every check here compiles a real role through `compile_role`, which resolves
the model itself and asks `ced.adapters.reasoning_disable` about the instance
the compiled agent carries. Nothing restates the adapter's rendering rule: the
answers below come from the model's own settings-to-request resolution, which
is what keeps the suite honest across a version pin.

The suite is not refusal-only. A guard that refused everything it failed to
classify would pass a refusal-only suite while blocking every deployment, so
each refusal here has an admitted counterpart differing in one thing.

Offline throughout: the Bedrock adapter is built from a region name and no
call is issued.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings

from ced.adapters.reasoning_disable import (
    MAX_WRAPPER_DEPTH,
    ReasoningDisable,
    reasoning_disable_of,
)
from ced.agents.compiler import COMPILED_THINKING, ThinkingDisableUnreachable, compile_role

from ..compiler.role_records import STUB_MODEL_ID, a_pool, a_quarantined_role
from .adapters import (
    ADAPTIVE_MODEL_ID,
    DISABLING_MODEL_ID,
    NO_PROFILE_MODEL_ID,
    a_bedrock_model,
    a_model_that_cannot_stop_thinking,
    a_model_whose_resolution_raises,
    a_pool_resolving_to,
    a_wrapper_around,
    an_in_process_double,
    another_providers_adapter,
)

#: The declaration the deployment makes, and the one it does not.
DECLARED = (STUB_MODEL_ID,)
NOTHING_DECLARED: tuple[str, ...] = ()


# ── the real adapter, admitted and refused ──────────────────────────────────


def test_a_model_whose_request_carries_a_disable_compiles() -> None:
    """The admitted half of the pair decided against a real provider adapter.

    A seam that answered "carries a disable" for every model would pass an
    all-double suite; this is what it cannot fake, because the answer comes
    from the adapter's own rendering of the compiled setting.
    """
    pool = a_pool_resolving_to(a_bedrock_model(DISABLING_MODEL_ID), declared=NOTHING_DECLARED)

    compiled = compile_role(a_quarantined_role(), (), pool)

    assert compiled.agent.model_settings is not None
    assert compiled.agent.model_settings["thinking"] is COMPILED_THINKING


def test_a_model_whose_request_carries_no_disable_is_refused_naming_the_id() -> None:
    """The refused half, on an adaptive family whose branch emits nothing."""
    pool = a_pool_resolving_to(a_bedrock_model(ADAPTIVE_MODEL_ID), declared=NOTHING_DECLARED)

    with pytest.raises(ThinkingDisableUnreachable, match=STUB_MODEL_ID):
        compile_role(a_quarantined_role(), (), pool)


#: Deeper than any bound this seam should carry. A literal on purpose: see the
#: exhaustion check below, which cannot observe the bound if it derives its
#: chain length from it.
_CHAIN = 64


def test_a_model_id_resolving_to_no_profile_is_refused() -> None:
    """Refused, and never read as a fixture.

    An unrecognised real model id resolves to no profile too, so reading "no
    profile" as "no provider" would admit every typo in a role record.
    """
    pool = a_pool_resolving_to(a_bedrock_model(NO_PROFILE_MODEL_ID), declared=NOTHING_DECLARED)

    with pytest.raises(ThinkingDisableUnreachable, match=STUB_MODEL_ID):
        compile_role(a_quarantined_role(), (), pool)


def test_reasoning_enabled_is_not_read_as_a_disable() -> None:
    """A thinking key in the request is not a disable, and is refused.

    Decided at the seam rather than through a compile, because the compiler
    fixes `thinking=False` and no role may declare otherwise — so an enabled
    rendering is unreachable from `compile_role` and would go unchecked. It
    is the case that separates the seam from a presence-of-a-thinking-key
    predicate, which the adaptive and no-profile checks above cannot: both of
    those render no key at all, so such a predicate passes the rest of this
    suite.
    """
    model = a_bedrock_model(DISABLING_MODEL_ID)

    assert reasoning_disable_of(model, ModelSettings(thinking=True)) is (
        ReasoningDisable.NOT_CARRIED
    )
    assert reasoning_disable_of(model, ModelSettings(thinking="high")) is (
        ReasoningDisable.NOT_CARRIED
    )
    assert (
        reasoning_disable_of(model, ModelSettings(thinking=False)) is ReasoningDisable.CARRIED
    )


def test_a_resolution_that_raises_answers_no_disable() -> None:
    """Fail closed: a probe that cannot be answered is not a disable.

    The class is one the seam does interrogate, so this is not the
    uninterrogable case — it is the framework moving under the pin, and the
    answer has to be the refusing one rather than an escaping exception the
    compiler has no branch for.
    """

    assert reasoning_disable_of(
        a_model_whose_resolution_raises(), ModelSettings(thinking=False)
    ) is (ReasoningDisable.NOT_CARRIED)


# ── the class the seam cannot interrogate, and the declaration ──────────────


def test_an_in_process_double_is_refused_when_nothing_declares_it() -> None:
    """ "No provider knowledge, therefore nothing to disable" is the fail-open.

    It is the same shape the carve-out replaced, so a class the seam cannot
    interrogate is refused unless the deployment has said it reaches no
    provider.
    """
    pool = a_pool_resolving_to(an_in_process_double(), declared=NOTHING_DECLARED)

    with pytest.raises(ThinkingDisableUnreachable, match=STUB_MODEL_ID):
        compile_role(a_quarantined_role(), (), pool)


def test_the_declaration_is_what_admits_a_non_provider_model() -> None:
    """The carve-out, and the check that it discriminates.

    The pool's factory **does** resolve the id, to a model the seam would
    otherwise refuse, so the declaration is the only thing admitting this
    compile and removing it alone reds it. The allowed set is untouched, so
    the refusal cannot be AC-0251's. Run against the deployment's own
    unwired-factory pool instead, this check would pass with the carve-out
    deleted: that compile is admitted because no model resolves at all.
    """
    model = an_in_process_double()

    compiled = compile_role(
        a_quarantined_role(), (), a_pool_resolving_to(model, declared=DECLARED)
    )
    assert compiled.agent.model is model

    with pytest.raises(ThinkingDisableUnreachable, match=STUB_MODEL_ID):
        compile_role(
            a_quarantined_role(), (), a_pool_resolving_to(model, declared=NOTHING_DECLARED)
        )


def test_a_declared_id_resolving_to_a_provider_backed_model_is_refused() -> None:
    """The declaration is not an operator-supplied bypass of the guard.

    The model here is the one the admitted pair uses, so its rendering carries
    a disable and nothing about the request is wrong. It is refused anyway:
    the deployment declared that this id reaches no provider and it does, so
    the declaration is false and the clause that would admit it no longer
    holds.
    """
    pool = a_pool_resolving_to(a_bedrock_model(DISABLING_MODEL_ID), declared=DECLARED)

    with pytest.raises(ThinkingDisableUnreachable, match=STUB_MODEL_ID):
        compile_role(a_quarantined_role(), (), pool)


# ── the case this task admits and hands on ──────────────────────────────────


def test_a_pool_that_wired_no_adapter_compiles() -> None:
    """No model resolves, so there is no request to interrogate.

    Admitted here and guarded at the call by T7, which is where a model the
    compile never saw is reached.
    """
    compiled = compile_role(a_quarantined_role(), (), a_pool())

    assert compiled.agent.model is None


def test_a_declared_id_on_an_unknown_providers_adapter_is_refused() -> None:
    """Only a model proved local is admitted, never one merely unrecognised.

    The seam has rendering knowledge of one provider. A second provider's
    adapter is a model it cannot interrogate *and* cannot prove reaches no
    provider — and "no provider knowledge, therefore nothing to disable,
    therefore admit" is the fail-open shape AC-0275 exists to refuse. It must
    fall to the refusal, not to the fixture carve-out.
    """
    other = another_providers_adapter()

    assert reasoning_disable_of(other, ModelSettings(thinking=COMPILED_THINKING)) is (
        ReasoningDisable.NOT_CARRIED
    ), "an adapter the seam cannot render must not read as non-provider-backed"

    with pytest.raises(ThinkingDisableUnreachable, match=STUB_MODEL_ID):
        compile_role(
            a_quarantined_role(), (), a_pool_resolving_to(other, declared=(STUB_MODEL_ID,))
        )


def test_the_answer_comes_from_the_models_own_resolution_not_the_rendering_rule() -> None:
    """AC-0275's "never by restating the rendering rule", pinned.

    On an always-thinking profile `prepare_request` discards an explicit
    `thinking=False`, so the parameters it returns carry no thinking value and
    the adapter renders nothing: the honest answer is that no disable is
    carried. A seam that skipped that step and handed the renderer a value it
    built from the settings itself would see `False` and render a disable —
    admitting a model that cannot stop reasoning.

    Without this check the two implementations are indistinguishable: every
    other fixture here sits on a profile where they agree, and a mutant that
    restates the rule leaves the whole suite green.
    """
    model = a_model_that_cannot_stop_thinking()

    assert reasoning_disable_of(model, ModelSettings(thinking=COMPILED_THINKING)) is (
        ReasoningDisable.NOT_CARRIED
    ), "an always-thinking profile discards the disable; the seam must report that"

    with pytest.raises(ThinkingDisableUnreachable, match=STUB_MODEL_ID):
        compile_role(a_quarantined_role(), (), a_pool_resolving_to(model, declared=()))


def test_a_wrapped_model_is_classified_by_what_it_wraps() -> None:
    """The unwrapping itself, pinned on the side where it is observable.

    The refusal check above cannot pin it: an un-unwrapped `WrapperModel`
    matches neither the in-process doubles nor the adapter class, so it falls
    to `NOT_CARRIED` and is refused either way — the check passes whether or
    not the seam unwraps, which is a check that cannot fail for its own
    reason. Removing the unwrap left the whole suite green.

    It is observable only where unwrapping *admits*: a wrapper around a model
    whose request does carry a disable must compile, and without the unwrap it
    is refused for a property of the wrapper rather than of the model that
    renders the request.
    """
    wrapped = a_wrapper_around(a_bedrock_model(DISABLING_MODEL_ID))

    assert reasoning_disable_of(wrapped, ModelSettings(thinking=COMPILED_THINKING)) is (
        ReasoningDisable.CARRIED
    ), "the disable the wrapped adapter renders must be the seam's answer"

    compiled = compile_role(a_quarantined_role(), (), a_pool_resolving_to(wrapped, declared=()))
    assert compiled.agent.model is wrapped


def test_each_in_process_double_is_admitted_by_the_declaration() -> None:
    """Both members of the admitted set, pinned separately.

    The declaration may admit exactly one answer, so every class that can
    produce it is load-bearing. Checked one at a time because a single check
    over `FunctionModel` leaves `TestModel`'s membership free to be deleted
    with the suite green — which it was.
    """
    for double in (an_in_process_double(), TestModel()):
        assert reasoning_disable_of(double, ModelSettings(thinking=COMPILED_THINKING)) is (
            ReasoningDisable.NOT_PROVIDER_BACKED
        ), f"{type(double).__name__} must be identified as reaching no provider"

        compiled = compile_role(
            a_quarantined_role(), (), a_pool_resolving_to(double, declared=(STUB_MODEL_ID,))
        )
        assert compiled.agent.model is double


def test_an_undeclared_double_is_refused_for_the_missing_declaration() -> None:
    """The refusal names the missing declaration, not a rendering.

    Deleting the branch that says so leaves the generic fall-through message,
    which carries the model id too — so a check matching only on the id stays
    green while the operator is told the model would reason when the real fix
    is to declare the id. The advice is what this check observes.
    """
    with pytest.raises(ThinkingDisableUnreachable, match="declared") as refusal:
        compile_role(
            a_quarantined_role(),
            (),
            a_pool_resolving_to(an_in_process_double(), declared=NOTHING_DECLARED),
        )

    assert "in-process double" in str(refusal.value)
    assert "would carry no provider-level" not in str(refusal.value), (
        "a missing declaration must not be reported as a model that would reason"
    )


def test_a_failed_probe_is_recorded_for_the_operator(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The probe's failure reaches a log, with its exception context.

    This is the half of the round-1 diagnostic finding that was done, and the
    deferral of the other half rests on it: without this line an operator
    facing a pin that moved under the seam sees only a refusal blaming the
    model. Deleting the log left the suite green, so it is pinned here.
    """
    with caplog.at_level(logging.WARNING, logger="ced.adapters.reasoning_disable"):
        answer = reasoning_disable_of(
            a_model_whose_resolution_raises(), ModelSettings(thinking=COMPILED_THINKING)
        )

    assert answer is ReasoningDisable.NOT_CARRIED
    assert caplog.records, "a swallowed probe failure must not be silent"
    assert caplog.records[0].exc_info is not None, (
        "the recorded warning must carry the exception that was swallowed"
    )


def test_a_wrapper_chain_deeper_than_the_bound_is_refused() -> None:
    """The bound's exhaustion branch, which otherwise rots unexercised.

    **The chain length is a literal, not `MAX_WRAPPER_DEPTH + 1`.** Derived
    from the constant, the chain grows with it and the check passes at any
    bound — widening the bound to ten thousand reds nothing, which a mutation
    sweep found. Written against a fixed depth, raising the bound past it
    lets the seam read the chain to the end, answer `CARRIED` for the
    disabling model inside, and red this check. The guard above states the
    relationship so the failure is legible rather than mysterious.

    The descent is bounded so a cyclic chain cannot hang role compilation.
    Nothing this repository wires can build one, so the branch is reached here
    deliberately: a chain past the bound must fall through to the refusal
    rather than be admitted, which is what makes the bound fail-closed rather
    than merely finite.
    """
    assert MAX_WRAPPER_DEPTH < _CHAIN, (
        "the bound must stay below the chain this check builds, or the check "
        "stops observing the exhaustion branch at all"
    )

    model: Any = a_bedrock_model(DISABLING_MODEL_ID)
    for _ in range(_CHAIN):
        model = a_wrapper_around(model)

    assert reasoning_disable_of(model, ModelSettings(thinking=COMPILED_THINKING)) is (
        ReasoningDisable.NOT_CARRIED
    ), "a chain the seam cannot read to the end must not be admitted"
