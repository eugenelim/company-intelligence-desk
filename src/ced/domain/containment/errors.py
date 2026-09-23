"""The two refusals this package can produce, as named types a caller can catch.

**The spec left the exception type unsettled on purpose.** AC-0315 fixes the
fragment's answer on an input it cannot decide as *a raise* and names no type;
[`walking-skeleton-policy-decision-point`](../../../../docs/specs/walking-skeleton-policy-decision-point/spec.md)'s
AC-0236 receives that raise and names no type either, while its AC-0208
requires the denial handler to be narrow by type and to let a programming
error through. A bare `TypeError` would satisfy the letter of both and make
the fail direction an accident of which builtin happened to escape first.

So the type is settled here, in the package the far side imports:

  `ContainmentUndecidable`  the fragment could not decide — the decision point
                            treats this as a denial, not as a defect
  `CeilingDeclarationRefused`  the declaration is not authorable at all

Neither derives from a builtin error class that ordinary bugs raise, which is
what lets `except ContainmentUndecidable` be narrow in the sense AC-0208 asks
for. The decision is recorded in
`docs/specs/walking-skeleton-authority-containment/notes/verification-ledger.md`.
"""

from __future__ import annotations

__all__ = ["CeilingDeclarationRefused", "ContainmentUndecidable"]


class CeilingDeclarationRefused(Exception):
    """A ceiling entry is not authorable, and no role version may carry it.

    Raised by the authoring surface only. Every refusal message names the
    entry and the argument it is about, because a refusal an author cannot
    locate is a refusal they will work around.
    """


class ContainmentUndecidable(Exception):
    """The fragment cannot decide whether this value falls inside the ceiling.

    Raised at evaluation, never returned. Returning "inside" or handing the
    value through would put a fail-open default at the authorization boundary,
    which is the hole AC-0315 exists to close. The three shapes that reach it
    are an unrecognised declared domain type, a value whose parse is
    ambiguous, and a predicate that cannot be evaluated against the value
    supplied.
    """
