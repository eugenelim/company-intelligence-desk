"""AC-0274 — the typed-scalar channel, in its three clauses.

Once AC-0221 closed references on provenance and AC-0268 closed labels on
membership, typed scalars were the one admitted class with no declared
membership: AC-0220's only refusal case is free prose, which every candidate
scalar encoding rejects anyway, so an opaque locator string or an unbounded
unit token would be admitted by a green suite. This is the widest remaining
channel out of the quarantined agent, and these are its three gates.

* **Clause (i)** — a typed scalar whose type is not one of the declared
  admitted scalar types is refused.
* **Clause (ii)** — where an admitted scalar type is itself an enumeration, a
  non-member is refused too.
* **Clause (iii)** — **Phase 1 mints no content-addressing value, so the
  parser refuses every one of them here**, categorically.

**The governing set is r8 § 4's** — decimals, dates, enumerated units,
content-addressed locators — which this spec's obligation table already names
as the owner of the quarantine guarantee, and which differs from r5 § 4's
narrower three. The suite reads `ADMITTED_SCALAR_TYPES`, `ADMITTED_UNITS` and
`UNMINTED_SCALAR_TYPES` rather than restating them, for the same reason
AC-0268's suite reads the label vocabulary.

**No case here is free prose.** AC-0220 covers that, and a scalar-shaped value
is the only thing that distinguishes this criterion from it.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from ced.domain.quarantine.mint import mint_candidate_set
from ced.domain.quarantine.parser import AdmittedTypeRefused, admit
from ced.domain.quarantine.vocabulary import (
    ADMITTED_SCALAR_TYPES,
    ADMITTED_UNITS,
    CONTENT_ADDRESSING_REFUSAL,
    CONTENT_KEY_PATTERN,
    UNMINTED_SCALAR_TYPES,
    ContentLocator,
    EnumeratedUnit,
)

from .fixture import FILING_CONTENT_HASH, STEP_A, recorded_filing


def test_every_declared_admitted_scalar_type_is_admitted() -> None:
    """Paired with the three refusals, so none of them is vacuous."""
    assert admit(Decimal("560.0")) == Decimal("560.0")
    assert admit(date(2026, 7, 31)) == date(2026, 7, 31)
    unit = EnumeratedUnit("usd")
    assert admit(unit) is unit
    assert {Decimal, date, EnumeratedUnit} == set(ADMITTED_SCALAR_TYPES)


# Clause (i) — a scalar whose type is not declared.


def test_a_float_is_a_scalar_whose_type_is_not_declared() -> None:
    """Read off the constant, so widening the set would fail this first."""
    assert float not in ADMITTED_SCALAR_TYPES


def test_a_scalar_of_an_undeclared_type_is_refused() -> None:
    """A float is scalar-shaped and carries a number; it is still not declared."""
    with pytest.raises(AdmittedTypeRefused):
        admit(560.0)


def test_a_datetime_is_refused_even_though_it_subclasses_an_admitted_type() -> None:
    """Exact-type matching, not `isinstance`: r8 § 4 declares a date."""
    assert datetime not in ADMITTED_SCALAR_TYPES
    with pytest.raises(AdmittedTypeRefused):
        admit(datetime(2026, 7, 31, 12, 0))


# Clause (ii) — an admitted type that is itself an enumeration.


def test_the_unit_enumeration_is_declared_beside_the_label_vocabulary() -> None:
    """Same module, same rule, or the membership test is an inline literal."""
    from ced.domain.quarantine import vocabulary

    assert vocabulary.ADMITTED_UNITS is ADMITTED_UNITS
    assert isinstance(ADMITTED_UNITS, frozenset) and ADMITTED_UNITS
    assert hasattr(vocabulary, "LABEL_VOCABULARY")


def test_a_non_member_of_the_unit_enumeration_is_refused() -> None:
    """Correct carrier type, undeclared member."""
    assert "eur" not in ADMITTED_UNITS
    with pytest.raises(AdmittedTypeRefused):
        admit(EnumeratedUnit("eur"))


def test_every_declared_unit_is_admitted() -> None:
    """A parser that raised on every unit would pass the case above."""
    for unit in sorted(ADMITTED_UNITS):
        assert admit(EnumeratedUnit(unit)) == EnumeratedUnit(unit)


# Clause (iii) — Phase 1 mints no content-addressing value.


def test_a_content_addressing_locator_is_declared_and_not_admitted() -> None:
    """r8 § 4 files it as a scalar; this phase admits none of them."""
    assert ContentLocator in UNMINTED_SCALAR_TYPES
    assert ContentLocator not in ADMITTED_SCALAR_TYPES


def test_the_refused_locator_is_well_formed() -> None:
    """Otherwise the refusal below would be of a malformed string, not a locator."""
    locator = ContentLocator("public", FILING_CONTENT_HASH)
    assert CONTENT_KEY_PATTERN.fullmatch(locator.key)


def test_a_well_formed_locator_is_refused_categorically() -> None:
    """**Categorically**, and the assertion says so.

    Refused identically with no candidate set and with a real, non-empty,
    freshly minted one — which is what shows provenance plays no part in the
    refusal. `walking-skeleton-step-lifecycle` opens the payload-object write
    path and must therefore **change** this test rather than inherit a green
    one that never checked provenance: once a locator can be minted, these two
    calls stop agreeing.
    """
    locator = ContentLocator("public", FILING_CONTENT_HASH)
    candidates = mint_candidate_set(STEP_A, recorded_filing())
    assert len(candidates) > 0

    with pytest.raises(AdmittedTypeRefused) as without_a_set:
        admit(locator)
    with pytest.raises(AdmittedTypeRefused) as with_a_set:
        admit(locator, candidates)

    assert str(without_a_set.value) == str(with_a_set.value)
    assert CONTENT_ADDRESSING_REFUSAL in str(without_a_set.value)


def test_the_categorical_refusal_is_not_the_unrecognised_type_fall_through() -> None:
    """The reason discriminates, or the categorical branch is dead code.

    A `ContentLocator` absent from `ADMITTED_SCALAR_TYPES` would be refused by
    the fall-through anyway, so a check that only observes "it raised" cannot
    tell the two apart — and would stay green for a later spec that admits the
    type and deletes the branch. Reading the declared reason is what makes the
    refusal observably the content-addressing one.
    """
    with pytest.raises(AdmittedTypeRefused) as unrecognised:
        admit(560.0)
    assert CONTENT_ADDRESSING_REFUSAL not in str(unrecognised.value)


def test_the_locator_refusal_does_not_depend_on_the_scope_or_the_hash() -> None:
    """Every one of them, not the one the fixture happens to name."""
    other = ContentLocator("run-0f1e2d3c", "0" * 63 + "1")
    assert CONTENT_KEY_PATTERN.fullmatch(other.key)
    with pytest.raises(AdmittedTypeRefused) as refused:
        admit(other, mint_candidate_set(UUID(str(STEP_A)), recorded_filing()))
    assert CONTENT_ADDRESSING_REFUSAL in str(refused.value)
