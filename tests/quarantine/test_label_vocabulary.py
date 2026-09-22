"""AC-0268 — a well-formed label the declared vocabulary does not contain fails.

r5 § 4 admits closed-vocabulary labels because for a label the shape **is**
membership in a finite fixed alphabet. A parser whose label test is a
token-shape regex satisfies AC-0220 — free prose still fails — while letting
the filer steer hyphenated tokens drawn from the filing across into a planning
agent. This file is the criterion that closes that.

**The suite reads `LABEL_VOCABULARY` rather than restating its members**, so
widening the vocabulary is a reviewable diff and cannot be done silently by
the implementation these checks exist to catch. A test carrying its own copy
of the alphabet would pass unchanged against a runtime that had doubled it.

The refused token is `tariff-refund-tailwind`: hyphenated, lower-case, the
exact shape of an admitted label, and drawn from `spikes/README.md` § Spike 4,
where "tariff refunds — a non-recurring tailwind" is filing-derived language
the quarantined agent had in front of it.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from ced.agents.compiler import compile_role
from ced.domain.quarantine.parser import AdmittedTypeRefused, admit
from ced.domain.quarantine.vocabulary import LABEL_VOCABULARY

from ..compiler.role_records import (
    CountingModel,
    a_pool,
    a_quarantined_role,
    an_integration,
)

STEERED_LABEL = "tariff-refund-tailwind"


def test_the_refused_token_is_well_formed_and_simply_not_a_member() -> None:
    """Otherwise the case below would be decided by shape, not by membership."""
    assert STEERED_LABEL not in LABEL_VOCABULARY
    admitted = sorted(LABEL_VOCABULARY)
    assert admitted, "the vocabulary must be non-empty for this to mean anything"
    assert all(label.islower() and " " not in label for label in admitted)
    assert STEERED_LABEL.islower() and " " not in STEERED_LABEL
    assert "-" in STEERED_LABEL and all("-" in label for label in admitted)


def test_a_well_formed_non_member_label_is_refused() -> None:
    """The membership test, which is the whole of the label guarantee."""
    with pytest.raises(AdmittedTypeRefused):
        admit(STEERED_LABEL)


def test_every_declared_member_is_admitted() -> None:
    """Paired with the refusal: a parser that raises on everything is not this."""
    for label in sorted(LABEL_VOCABULARY):
        assert admit(label) == label


def test_the_parser_has_no_parameter_a_role_or_a_registry_row_could_arrive_through() -> None:
    """The vocabulary cannot be derived from a record that cannot reach it."""
    assert list(inspect.signature(admit).parameters) == ["value", "candidates"]
    assert isinstance(LABEL_VOCABULARY, frozenset)


def test_compiling_a_quarantined_role_beside_a_row_naming_the_token_does_not_widen_it() -> None:
    """A registry row may carry the token, and a compile beside it changes nothing.

    Read what this does *not* decide. A quarantined role's `ceiling` is empty,
    so `_bound_integrations` iterates nothing and the compiler never reads the
    row — the check passes identically with `integrations=()`. What it pins is
    that the token survives as a `tools` entry without the vocabulary moving,
    which is the layer the registry sits at. Binding the row through a ceiling
    entry, so a guard reads it, is a second check; `workspace.toml`
    `[backlog].open` carries it.
    """
    row = an_integration(tools=(STEERED_LABEL,))
    compile_role(role=a_quarantined_role(), integrations=(row,), pool=a_pool())
    assert STEERED_LABEL in row["tools"]
    with pytest.raises(AdmittedTypeRefused):
        admit(STEERED_LABEL)


def test_model_output_carrying_the_token_does_not_widen_it() -> None:
    """Structured output is a layer; the boundary is still the parser."""
    model = CountingModel(
        lambda info: ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"references": [STEERED_LABEL]})]
        )
    )
    compiled = compile_role(
        role=a_quarantined_role(), integrations=(), pool=a_pool(model=model.model)
    )
    result = asyncio.run(compiled.agent.run("select", usage_limits=compiled.limits))
    assert result.output.references == [STEERED_LABEL]
    with pytest.raises(AdmittedTypeRefused):
        admit(result.output.references[0])
