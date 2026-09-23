"""AC-0317 — evaluation denies an argument no predicate ranges over.

AC-0316 refuses the same shape at authoring time, and the two cannot share a
case: AC-0316 makes this input unreachable through the front door. So the
entry here is **constructed directly**, which is what an entry that arrived
by a migration, or a role authored before the refusal existed, looks like.

The hole underneath both is r5's per-argument conjunction: a conjunction over
a subset is vacuously true on every argument outside it, so an `fs-path` with
no root admits `/etc/passwd` while every other criterion stays green.
"""

from __future__ import annotations

from ced.domain.containment.ceiling import (
    CeilingArgument,
    CeilingEntry,
    Denied,
    evaluate,
)
from ced.domain.containment.predicates import HostInDomain, SchemeIn, Within

_CONSTRAINED = CeilingArgument(
    domain_type="url",
    predicates=(SchemeIn(frozenset({"https"})), HostInDomain("sec.gov")),
)


def test_an_argument_the_entry_names_with_no_predicate_denies() -> None:
    entry = CeilingEntry(
        name="fetch_filing",
        arguments={"url": _CONSTRAINED, "path": CeilingArgument("fs-path", ())},
    )
    decision = evaluate(entry, {"url": "https://www.sec.gov/x", "path": "/etc/passwd"})
    assert isinstance(decision, Denied)
    assert "path" in decision.reason
    assert "no predicate" in decision.reason


def test_an_argument_the_entry_does_not_name_at_all_denies() -> None:
    entry = CeilingEntry(name="fetch_filing", arguments={"url": _CONSTRAINED})
    decision = evaluate(entry, {"url": "https://www.sec.gov/x", "path": "/etc/passwd"})
    assert isinstance(decision, Denied)
    assert "path" in decision.reason


def test_the_constrained_argument_of_the_same_entry_still_decides_normally() -> None:
    """The deny is about the unconstrained argument, not about the entry."""
    entry = CeilingEntry(
        name="fetch_filing",
        arguments={"url": _CONSTRAINED, "path": CeilingArgument("fs-path", ())},
    )
    assert isinstance(
        evaluate(entry, {"url": "https://attacker.example/", "path": "/evidence/x"}),
        Denied,
    )


def test_an_argument_the_entry_constrains_and_the_call_omits_denies() -> None:
    """The mirror of AC-0317, and the same vacuous conjunction from the far side.

    AC-0317 closes a call argument no predicate ranges over. This is a
    predicate no call argument arrives for, and deciding only what the call
    happens to supply would make `evaluate(entry, {})` an admission against
    any ceiling however tightly written — after which whatever default the
    callee binds for the omitted parameter sits outside the ceiling
    entirely. Beyond AC-0316 and AC-0317 as worded; recorded in the
    verification ledger.
    """
    entry = CeilingEntry(name="fetch_filing", arguments={"url": _CONSTRAINED})
    assert isinstance(evaluate(entry, {}), Denied)

    two = CeilingEntry(
        name="fetch_filing",
        arguments={
            "url": _CONSTRAINED,
            "path": CeilingArgument("fs-path", (Within("/evidence"),)),
        },
    )
    decision = evaluate(two, {"url": "https://www.sec.gov/x"})
    assert isinstance(decision, Denied)
    assert "path" in decision.reason
