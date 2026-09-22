"""AC-0238 — the candidate set is complete before the first model turn.

Three claims, and the criterion needs all three. The set observed before the
quarantined agent's first turn is **non-empty**, **equal to a committed
baseline**, and **identical to the set observed after the last turn**. Drop
the first and a mint producing nothing satisfies the other two; drop the
second and a pipeline deriving the wrong set from the fixture passes.

**Both snapshots are taken by the stub model at its own request boundary**,
so the ordering is decided outside the implementation: an implementation that
minted lazily inside the first turn, or grew the set mid-run, is what the
snapshots can see and a post-run probe cannot.
"""

from __future__ import annotations

import asyncio

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ced.agents.compiler import compile_role
from ced.domain.quarantine.mint import CandidateSet, mint_candidate_set

from ..compiler.role_records import a_pool, a_quarantined_role, returns_an_empty_selection
from .fixture import STEP_A, expected_candidate_set, recorded_filing


class SnapshottingModel:
    """Records the candidate set on entry to and exit from every request.

    The timeline it appends to is the test's, not the runtime's: nothing in
    `ced/` knows this object exists, which is what keeps the ordering claim
    an observation rather than a restatement of the implementation.
    """

    def __init__(self, candidates: CandidateSet, timeline: list[str]) -> None:
        self.candidates = candidates
        self.timeline = timeline
        self.on_entry: list[frozenset[str]] = []
        self.on_exit: list[frozenset[str]] = []
        self.sealed_on_entry: list[bool] = []
        self.model = FunctionModel(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.timeline.append("model.request")
        self.on_entry.append(self.candidates.references)
        self.sealed_on_entry.append(self.candidates.sealed)
        response = returns_an_empty_selection(info)
        self.on_exit.append(self.candidates.references)
        return response


def _run_quarantined_agent() -> SnapshottingModel:
    """Mint, then run the compiled quarantined agent over the recorded filing."""
    timeline: list[str] = []
    candidates = mint_candidate_set(STEP_A, recorded_filing())
    timeline.append("mint.complete")
    model = SnapshottingModel(candidates, timeline)
    compiled = compile_role(
        role=a_quarantined_role(), integrations=(), pool=a_pool(model=model.model)
    )
    asyncio.run(compiled.agent.run("select", usage_limits=compiled.limits))
    assert timeline[0] == "mint.complete"
    assert timeline.count("model.request") >= 1
    return model


def test_the_set_before_the_first_turn_is_non_empty() -> None:
    """A mint that produced nothing would satisfy both snapshots otherwise."""
    model = _run_quarantined_agent()
    assert model.on_entry[0]


def test_the_set_before_the_first_turn_equals_the_committed_baseline() -> None:
    """Compared literally against a committed artifact, not a second mint."""
    model = _run_quarantined_agent()
    assert sorted(model.on_entry[0]) == expected_candidate_set()


def test_the_set_is_complete_before_the_first_turn() -> None:
    """Sealed at the request boundary, so nothing was minted lazily in-turn."""
    model = _run_quarantined_agent()
    assert model.sealed_on_entry[0] is True


def test_the_set_after_the_last_turn_is_identical() -> None:
    """No reference was added while the agent ran."""
    model = _run_quarantined_agent()
    assert model.on_exit[-1] == model.on_entry[0]
