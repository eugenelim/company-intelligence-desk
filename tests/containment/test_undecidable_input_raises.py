"""AC-0315 — an input the fragment cannot decide raises, and raises what.

Three shapes, asserted separately. A single combined case would pass on a
fragment that raises for one and answers "inside" for the other two, which is
the fail-open the criterion exists to close.

**The type is the point as much as the raise.** The fragment is consumed
across a spec boundary:
`walking-skeleton-policy-decision-point`'s AC-0236 receives this raise and
its AC-0208 requires the denial handler to be narrow by type and to let a
programming error through. Neither spec names a type, so it is settled here,
in the package the far side imports, and the last test in this module is what
holds it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ced.domain.containment.ceiling import CeilingArgument, CeilingEntry, evaluate
from ced.domain.containment.errors import CeilingDeclarationRefused, ContainmentUndecidable
from ced.domain.containment.predicates import HostInDomain, NumberRange, SchemeIn


def test_an_unrecognised_declared_domain_type_raises() -> None:
    entry = CeilingEntry(
        name="run_query",
        arguments={"query": CeilingArgument("graphql-query", (SchemeIn(frozenset({"a"})),))},
    )
    with pytest.raises(ContainmentUndecidable, match="does not recognise"):
        evaluate(entry, {"query": "{ filings }"})


def test_an_ambiguous_parse_raises() -> None:
    entry = CeilingEntry(
        name="fetch_filing",
        arguments={
            "url": CeilingArgument(
                "url", (SchemeIn(frozenset({"https"})), HostInDomain("sec.gov"))
            )
        },
    )
    with pytest.raises(ContainmentUndecidable, match="more than one '@'"):
        evaluate(entry, {"url": "https://a@attacker.example@www.sec.gov/evidence/x"})


def test_a_predicate_that_cannot_be_evaluated_against_the_value_raises() -> None:
    entry = CeilingEntry(
        name="fetch_filing",
        arguments={"count": CeilingArgument("number", (NumberRange(Decimal(0), Decimal(10)),))},
    )
    with pytest.raises(ContainmentUndecidable, match="cannot be evaluated against"):
        evaluate(entry, {"count": "ten"})


def test_no_undecidable_input_returns_an_admitting_or_passthrough_result() -> None:
    """The raise is the whole answer: nothing falls through to a return."""
    entry = CeilingEntry(
        name="run_query",
        arguments={"query": CeilingArgument("graphql-query", (SchemeIn(frozenset({"a"})),))},
    )
    try:
        decision = evaluate(entry, {"query": "{ filings }"})
    except ContainmentUndecidable:
        return
    pytest.fail(f"evaluation returned {decision!r} instead of raising")


def test_the_seam_exception_is_not_one_a_programming_error_raises() -> None:
    """The decision point may treat this as a denial without swallowing bugs.

    `walking-skeleton-policy-decision-point`'s AC-0208 requires its denial
    handler to be narrow by type. A fragment raising `TypeError` would make
    that handler catch every mistyped call in the runtime as well, and the
    fail direction would be decided by accident. Both exception types here
    derive from `Exception` and from no builtin error class an ordinary bug
    produces.
    """
    for seam_error in (ContainmentUndecidable, CeilingDeclarationRefused):
        assert issubclass(seam_error, Exception)
        assert not issubclass(
            seam_error, TypeError | ValueError | AttributeError | KeyError | LookupError
        )
