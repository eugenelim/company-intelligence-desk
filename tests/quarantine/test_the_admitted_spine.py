"""The plan's one quarantine integration test, walked as a single sequence.

`plan.md` § Construction tests names it: the deterministic pipeline mints a
reference set from the recorded filing, the quarantined agent selects among
them, the parser admits. Each leg is green alone elsewhere — the mint in
`test_mint_precedes_the_run.py`, the admission in `test_reference_provenance.py`
with no agent in the loop, an agent run in `test_label_vocabulary.py` only in
the refused direction — and the join was exercised nowhere.

**The selection happens inside the run.** The stub model is handed the minted
set and picks a member at its own request boundary, so what reaches `admit` is
a value that travelled the framework's output path rather than a constant the
test carried around it. That is what makes the check catch a mismatch between
the token the mint produces and the value the run yields: the reference the run
returns is admitted against a set minted **again, independently**, after the
run, from the same filing and the same step.

**It stops short of the planning-step leg.** The onward crossing into a
planning step is `walking-skeleton-step-lifecycle`'s, per the same plan entry.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ced.agents.compiler import compile_role
from ced.domain.quarantine.mint import CandidateSet, mint_candidate_set
from ced.domain.quarantine.parser import AdmittedTypeRefused, admit

from ..compiler.role_records import a_pool, a_quarantined_role
from .fixture import STEP_A, STEP_B, recorded_filing


class SelectsOneMintedReference:
    """A stub model that picks one member of the set it was minted for."""

    def __init__(self, candidates: CandidateSet) -> None:
        self.offered = sorted(candidates.references)
        self.selected: list[str] = []
        self.model = FunctionModel(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        choice = self.offered[0]
        self.selected.append(choice)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"references": [choice]})]
        )


def _mint_select_and_return() -> tuple[CandidateSet, SelectsOneMintedReference, list[str]]:
    """Mint for step A, run the compiled quarantined agent, hand back its output."""
    candidates = mint_candidate_set(STEP_A, recorded_filing())
    assert candidates.references, "the mint must offer something to select from"
    model = SelectsOneMintedReference(candidates)
    compiled = compile_role(
        role=a_quarantined_role(), integrations=(), pool=a_pool(model=model.model)
    )
    result = asyncio.run(compiled.agent.run("select", usage_limits=compiled.limits))
    references: list[str] = result.output.references
    return candidates, model, references


def test_the_run_yields_exactly_the_token_the_mint_produced() -> None:
    """A value altered anywhere between the mint and the output is caught here."""
    _, model, references = _mint_select_and_return()
    assert model.selected, "the stub model never ran, so nothing was selected"
    assert references == [model.selected[0]]


def test_the_parser_admits_the_selected_reference_against_that_steps_set() -> None:
    """The spine's admitted direction: mint, select in the run, admit."""
    candidates, _, references = _mint_select_and_return()
    selected = references[0]
    assert admit(selected, candidates) == selected


def test_the_selected_reference_is_admitted_against_an_independent_mint() -> None:
    """The set is minted again after the run, so the admission is not circular."""
    _, _, references = _mint_select_and_return()
    minted_again = mint_candidate_set(STEP_A, recorded_filing())
    assert admit(references[0], minted_again) == references[0]


def test_the_selected_reference_is_refused_against_another_steps_set() -> None:
    """Without this the admission above would pass for a provenance-free parser."""
    _, _, references = _mint_select_and_return()
    other_step = mint_candidate_set(STEP_B, recorded_filing())
    with pytest.raises(AdmittedTypeRefused):
        admit(references[0], other_step)
