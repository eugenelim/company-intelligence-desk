"""AC-0213 — every documented prefix bypass is refused over the parsed value.

The rows come out of `worker-runtime.md` § 4 rather than out of a list here.
AC-0213 says a row added to that table upstream is an amendment trigger for
the criterion, and a trigger nothing reads is a sentence: `_CEILING_FOR_ROW`
below has to name every row's ceiling, so a new row reds this module until
somebody decides what refuses it.

Each row states a ceiling written as a **prefix**. The fragment refuses that
ceiling outright — AC-0217 — so what this module checks is the other half:
the same intent written in the sound way, over parsed components, refuses the
value the prefix admits.
"""

from __future__ import annotations

import pytest

from ced.domain.containment.ceiling import Admitted, evaluate
from tests.containment.fixture import UnsafePrefixRow, sec_ceiling, unsafe_prefix_rows

#: The argument of `sec_ceiling()` that expresses each documented prefix
#: soundly. Keyed by the row's ceiling cell exactly as the document writes it.
_CEILING_FOR_ROW: dict[str, str] = {
    'startswith("https://www.sec.gov")': "url",
    'startswith("/evidence/")': "path",
}


def test_the_table_was_found_and_carries_the_documented_rows() -> None:
    """Setup check: the parse found a table rather than an empty set."""
    rows = unsafe_prefix_rows()
    assert len(rows) >= 3, f"expected the two original rows plus userinfo, got {rows}"
    assert any("@attacker.example" in row.value for row in rows), (
        "the userinfo row this spec files upstream is missing from the table"
    )


def test_every_row_names_a_ceiling_this_suite_can_refuse_against() -> None:
    """The amendment trigger: a new row has to be given an answer here."""
    unmapped = {row.ceiling for row in unsafe_prefix_rows()} - set(_CEILING_FOR_ROW)
    assert not unmapped, (
        f"worker-runtime.md § 4 gained prefix ceilings this suite does not refuse "
        f"against: {sorted(unmapped)}. AC-0213 is the amendment trigger."
    )


@pytest.mark.parametrize("row", unsafe_prefix_rows(), ids=lambda row: row.value)
def test_the_value_a_prefix_admits_is_refused_over_the_parsed_value(
    row: UnsafePrefixRow,
) -> None:
    argument = _CEILING_FOR_ROW[row.ceiling]
    decision = evaluate(sec_ceiling(), {argument: row.value})
    assert not isinstance(decision, Admitted), (
        f"{row.value!r} was admitted, and the callee sees {row.callee_sees}"
    )
