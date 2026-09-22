"""AC-0250 — mutating the candidate set in flight is refused, and changes nothing.

Separate from AC-0238 because a set nothing tries to mutate satisfies AC-0238
with no enforcement built at all. Both halves are asserted: the runtime's own
refusal type, and the set unchanged afterwards. Naming the observable is what
separates a built guard from an incidental `TypeError` — an unwired holder
that happened to raise `AttributeError` would pass a bare `pytest.raises`.

The set is per-step in-process state by the owner's ruling of 2026-09-20, so
the assertion is in process and not against a store.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ced.agents.compiler import compile_role
from ced.domain.quarantine.mint import CandidateSet, CandidateSetSealed, mint_candidate_set

from ..compiler.role_records import a_pool, a_quarantined_role, returns_an_empty_selection
from .fixture import STEP_A, recorded_filing

FORGED = "ref/5c1a0b7e-9d3f-4a62-8e10-2b4c6d8f0a1e/xbrl/us-gaap:Forged/c-1"


class MutatingModel:
    """Attempts to widen the candidate set from inside the run."""

    def __init__(self, candidates: CandidateSet) -> None:
        self.candidates = candidates
        self.refusals: list[Exception] = []
        self.before: list[frozenset[str]] = []
        self.after: list[frozenset[str]] = []
        self.model = FunctionModel(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.before.append(self.candidates.references)
        try:
            self.candidates.add(FORGED)
        except Exception as refusal:  # noqa: BLE001 - the type is the assertion
            self.refusals.append(refusal)
        self.after.append(self.candidates.references)
        return returns_an_empty_selection(info)


def _run() -> MutatingModel:
    candidates = mint_candidate_set(STEP_A, recorded_filing())
    model = MutatingModel(candidates)
    compiled = compile_role(
        role=a_quarantined_role(), integrations=(), pool=a_pool(model=model.model)
    )
    asyncio.run(compiled.agent.run("select", usage_limits=compiled.limits))
    return model


def test_an_in_flight_mutation_raises_the_runtimes_own_refusal() -> None:
    """Not an incidental `TypeError`: the declared refusal, named."""
    model = _run()
    assert model.refusals
    assert all(isinstance(refusal, CandidateSetSealed) for refusal in model.refusals)


def test_an_in_flight_mutation_leaves_the_set_unchanged() -> None:
    """The refusal is not the whole guarantee; the set not moving is."""
    model = _run()
    assert model.after == model.before
    assert FORGED not in model.after[0]


def test_resealing_cannot_reopen_a_sealed_set() -> None:
    """Rebinding the seal is refused too, so `add` cannot be unlocked."""
    candidates = mint_candidate_set(STEP_A, recorded_filing())
    with pytest.raises(CandidateSetSealed):
        candidates.sealed = False
