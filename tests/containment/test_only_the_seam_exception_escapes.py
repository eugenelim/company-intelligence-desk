"""Nothing but this package's own two types leaves the fragment.

AC-0315 fixes the answer on an input the fragment cannot decide as a raise,
and the verification ledger fixes *which* raise, so that the decision point's
denial handler can be narrow by type and still let a programming error
through. That contract is only worth what the fragment's failure vocabulary
is: a builtin escaping `evaluate` turns an attacker-chosen tool argument into
an uncaught error in the worker step rather than a logged denial, and a
handler catching `ContainmentUndecidable` cannot see it coming.

A tool-call argument is model-chosen and therefore shaped by whatever the
documents under analysis contain, so every one of these is reachable from
untrusted input rather than only from a caller's mistake.

The first test names the shapes found; the property test is what holds the
claim against a shape nobody has thought of yet.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ced.domain.containment.ceiling import (
    Admitted,
    CeilingArgument,
    CeilingEntry,
    Denied,
    declare,
    evaluate,
)
from ced.domain.containment.errors import CeilingDeclarationRefused, ContainmentUndecidable
from ced.domain.containment.predicates import (
    DateRange,
    HostInDomain,
    NumberRange,
    SchemeIn,
    Within,
)

_URL = CeilingArgument("url", (SchemeIn(frozenset({"https"})), HostInDomain("sec.gov")))
_FS = CeilingArgument("fs-path", (Within("/srv"),))
_NUMBER = CeilingArgument("number", (NumberRange(Decimal(0), Decimal(9)),))
_DATE = CeilingArgument("date", (DateRange(date(2024, 1, 1), date(2024, 12, 31)),))

#: Values whose canonicalisation or whose comparison is itself ill-defined,
#: and which each used to leave `evaluate` as a builtin: `ValueError` out of
#: `realpath`, `decimal.InvalidOperation` out of an ordering against NaN, and
#: `TypeError` from comparing a `date` with a `datetime`, which passes an
#: `isinstance` test because `datetime` subclasses `date`.
_ILL_DEFINED: tuple[tuple[str, CeilingArgument, object], ...] = (
    ("a path with a NUL in it", _FS, "/srv/a\x00/../../etc/passwd"),
    ("a path that is not a string", _FS, 17),
    ("a number that is NaN", _NUMBER, Decimal("NaN")),
    ("a number that is infinite", _NUMBER, Decimal("Infinity")),
    ("a date that is a datetime", _DATE, datetime(2024, 6, 1, 12, 0)),
    ("a url that is not a string", _URL, 17),
    ("a url with no scheme", _URL, "www.sec.gov/evidence"),
)


@pytest.mark.parametrize(
    ("label", "constraint", "value"), _ILL_DEFINED, ids=[case[0] for case in _ILL_DEFINED]
)
def test_an_ill_defined_value_is_undecidable_and_not_a_crash(
    label: str, constraint: CeilingArgument, value: object
) -> None:
    entry = CeilingEntry(name="t", arguments={"a": constraint})
    with pytest.raises(ContainmentUndecidable):
        evaluate(entry, {"a": value})


def test_declare_refuses_a_root_the_filesystem_cannot_resolve() -> None:
    """The authoring surface has the same closed vocabulary, for the same value."""
    with pytest.raises(CeilingDeclarationRefused):
        declare("t", {"p": ("fs-path", (Within("/srv\x00"),))})


@settings(max_examples=400, deadline=None)
@given(st.text(max_size=48))
def test_no_string_leaves_evaluation_as_anything_else(value: str) -> None:
    """The claim the named cases cannot make: it holds for a shape nobody listed.

    Generated over strings because that is the shape a model-chosen argument
    arrives in. The assertion is not about the answer — a denial and a raise
    are both correct — but about the vocabulary: three outcomes and no
    fourth.
    """
    entry = CeilingEntry(name="t", arguments={"u": _URL, "p": _FS})
    for argument in ("u", "p"):
        other = "u" if argument == "p" else "p"
        call = {argument: value, other: "https://www.sec.gov/x" if other == "u" else "/srv/x"}
        try:
            decision = evaluate(entry, call)
        except ContainmentUndecidable:
            continue
        assert isinstance(decision, Admitted | Denied)
