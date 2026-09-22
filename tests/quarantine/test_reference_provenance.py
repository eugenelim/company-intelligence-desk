"""AC-0221 — a reference the runtime did not mint for *this* step is refused.

The criterion to write first and trust least. A parser that validates shape
without a minting authority admits an attacker-chosen value inside a
well-formed reference, and it looks identical in a green suite. So the case
that decides this is not a malformed reference — it is a **perfectly well
formed one that resolves in another step's set**.

Both steps mint from the **same recorded filing**, so the two sets differ in
nothing but the step they were minted for. That is the sharpest available
form of the criterion: the refused reference names a real fact in the real
corpus, is structurally indistinguishable from an admitted one, and resolves
— in the other step.
"""

from __future__ import annotations

import pytest

from ced.domain.quarantine.mint import mint_candidate_set
from ced.domain.quarantine.parser import AdmittedTypeRefused, admit
from ced.domain.quarantine.vocabulary import REFERENCE_PREFIX

from .fixture import STEP_A, STEP_B, recorded_filing


def _two_sets() -> tuple[object, object]:
    filing = recorded_filing()
    return mint_candidate_set(STEP_A, filing), mint_candidate_set(STEP_B, filing)


def test_a_minted_reference_is_admitted_against_its_own_set() -> None:
    """The admitted direction, without which every case below is vacuous."""
    set_a, _ = _two_sets()
    minted = sorted(set_a.references)[0]
    assert admit(minted, set_a) == minted


def test_a_reference_from_another_steps_set_is_well_formed_and_resolves_there() -> None:
    """Establishes the premise the refusal below is interesting because of."""
    set_a, set_b = _two_sets()
    from_b = sorted(set_b.references)[0]
    assert from_b.startswith(REFERENCE_PREFIX)
    assert admit(from_b, set_b) == from_b
    assert from_b not in set_a


def test_a_reference_from_another_steps_set_is_refused_here() -> None:
    """Shape validity is not provenance."""
    set_a, set_b = _two_sets()
    for from_b in sorted(set_b.references)[:5]:
        with pytest.raises(AdmittedTypeRefused):
            admit(from_b, set_a)


def test_a_forged_reference_naming_this_step_is_refused() -> None:
    """The attacker's best case: this step's scope, a concept never minted."""
    set_a, _ = _two_sets()
    forged = f"{REFERENCE_PREFIX}{STEP_A}/xbrl/us-gaap:Fabricated/c-1"
    assert forged not in set_a
    with pytest.raises(AdmittedTypeRefused):
        admit(forged, set_a)


def test_a_reference_with_no_candidate_set_is_refused() -> None:
    """Fail closed: with nothing to check provenance against, nothing crosses."""
    set_a, _ = _two_sets()
    minted = sorted(set_a.references)[0]
    with pytest.raises(AdmittedTypeRefused):
        admit(minted)


def test_the_two_sets_are_the_same_size_over_the_same_filing() -> None:
    """The sets differ only in provenance, not in what the corpus offers."""
    set_a, set_b = _two_sets()
    assert len(set_a) == len(set_b) > 0
    assert set_a.references.isdisjoint(set_b.references)
