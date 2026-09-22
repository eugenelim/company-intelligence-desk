"""The closed sets the parser admits by, in one place a reviewer can see change.

`runtime-architecture.md` r8 § 4 Contracts and Invariants owns the quarantine
guarantee and names what may cross from a quarantined agent to a planning
agent: **references, closed-vocabulary labels, and typed scalars — decimals,
dates, enumerated units, content-addressed locators.** That is the governing
set; `worker-runtime.md` r5 § 4 gives the narrower "decimals, dates,
enumerated units", and this spec's obligation table names r8 § 4 as the owner.

**Every closed set lives here and nowhere else**, as module-level constants a
suite reads rather than restates. That is the rule AC-0268 states for the
label vocabulary and AC-0274 extends to the scalar types and to the unit
enumeration: a membership test written as an inline literal at a call site is
not reviewable, and widening it would not show up as a diff over a declared
set. None of these sets is derived from a role record, a registry row or model
output — nothing here reads any of the three, and `frozenset` leaves no
runtime widening affordance either.

**r5 § 4 admits labels because for a label the shape *is* membership** in a
finite fixed alphabet. A parser whose label test is a token-shape regex
satisfies AC-0220 while letting the filer steer hyphenated tokens drawn from
the filing across into a planning agent, which is the channel
`LABEL_VOCABULARY` closes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

__all__ = [
    "ADMITTED_SCALAR_TYPES",
    "ADMITTED_UNITS",
    "CONTENT_ADDRESSING_REFUSAL",
    "CONTENT_KEY_PATTERN",
    "LABEL_VOCABULARY",
    "REFERENCE_PREFIX",
    "UNMINTED_SCALAR_TYPES",
    "ContentLocator",
    "EnumeratedUnit",
]

#: The closed vocabulary a quarantined agent may label a selection with.
#:
#: Three members, each grounded in a document rather than invented here:
#: `revenue-recognition` is the plan's approved AC-0220 stub, and
#: `margin-expansion` and `tax-rate-change` are the two labels
#: `spikes/README.md` § Spike 4 recorded the quarantined agent using against
#: this same corpus. Spike 4 spelled the latter two with underscores; the
#: pinned stub spells its own with hyphens, and the stub is contract, so one
#: spelling is carried here and it is the stub's.
#:
#: Spike 4 also falsified the hypothesis that a closed vocabulary carries a
#: diligence judgement: causality cannot cross a fixed alphabet, and no
#: enlargement of this set fixes that. Widening it is a reviewable diff for
#: that reason as much as for the steering channel.
LABEL_VOCABULARY: Final = frozenset(
    {
        "revenue-recognition",
        "margin-expansion",
        "tax-rate-change",
    }
)

#: The unit enumeration, declared here and under the same rule as the labels
#: because AC-0274's second clause requires exactly that: an admitted scalar
#: type that is itself an enumeration needs its members somewhere a reviewer
#: sees change, or the membership test is an inline literal at the call site.
#:
#: The six members are the `unitRef` values the recorded corpus actually uses,
#: read off the committed filing rather than guessed.
ADMITTED_UNITS: Final = frozenset(
    {
        "usd",
        "usdPerShare",
        "shares",
        "number",
        "customer",
        "vendor",
    }
)

#: What a minted reference starts with. The parser never parses past it: the
#: prefix routes a string to the provenance test, and membership in the step's
#: candidate set is the whole of that test. Shape validity is not provenance.
REFERENCE_PREFIX: Final = "ref/"

#: r8 § 4's `key = <owner_scope>/<content_hash>`, with `public` as an explicit
#: named scope. Declared so a suite can establish that the locator it refuses
#: is **well formed**, which is what makes the refusal categorical rather than
#: a rejection of a malformed string.
CONTENT_KEY_PATTERN: Final = re.compile(r"\A[a-z][a-z0-9-]*/[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class EnumeratedUnit:
    """One of r8 § 4's enumerated units, as a value the parser can type-test.

    A typed carrier and not a bare `str`, because a unit crossing as a string
    would be indistinguishable from a closed-vocabulary label — which would
    merge two closed sets into one namespace and leave AC-0274's second clause
    with nothing to decide that AC-0268 does not already decide.

    Not an `enum.Enum`: a non-member of an `Enum` cannot be constructed, so the
    refusal this type exists to demonstrate would be unreachable and the
    membership test vacuous.
    """

    unit: str


@dataclass(frozen=True)
class ContentLocator:
    """An address for stored content — `<owner_scope>/<content_hash>`.

    r8 § 4 files this as a typed scalar. **Phase 1 admits none of them.** This
    spec writes no payload object and the key format belongs to
    `walking-skeleton-step-lifecycle`, so there is no minted locator for a
    provenance test to admit, and the parser refuses every one categorically —
    see `UNMINTED_SCALAR_TYPES`.
    """

    owner_scope: str
    content_hash: str

    @property
    def key(self) -> str:
        """The r8 § 4 object key this locator addresses."""
        return f"{self.owner_scope}/{self.content_hash}"


#: The typed-scalar types admitted in Phase 1, matched on the value's exact
#: type rather than by `isinstance`. Exact matching is the fail-closed reading
#: and it closes one real hole: `datetime.datetime` is a subclass of
#: `datetime.date`, so an `isinstance` test would admit a timestamp where r8
#: § 4 declares a date.
ADMITTED_SCALAR_TYPES: Final[tuple[type, ...]] = (Decimal, date, EnumeratedUnit)

#: The reason a content-addressing value is refused, named so a suite can
#: tell the **categorical** refusal from the fall-through one a value of an
#: unrecognised type gets. Without it the branch below is dead code: a
#: `ContentLocator` absent from `ADMITTED_SCALAR_TYPES` is refused either way,
#: and a suite that only observes "it raised" cannot see which happened — nor
#: fail for a later spec that admits the type and deletes the branch.
CONTENT_ADDRESSING_REFUSAL: Final = "Phase 1 mints no content-addressing value"

#: r8 § 4's fourth scalar class, declared and **refused**. Kept as its own
#: constant rather than merely omitted from the set above, so that the Phase 1
#: posture is a statement a reviewer and a suite can both read.
#:
#: The durable rule is the general one AC-0274 states: **any admitted value
#: that addresses stored content carries AC-0221's minting-and-provenance
#: test**, whichever class a ratified document files it under. The spec that
#: opens the payload-object write path adds that criterion and moves this
#: member, which is a diff across two named constants rather than a green test
#: inherited without provenance ever having been checked.
UNMINTED_SCALAR_TYPES: Final[tuple[type, ...]] = (ContentLocator,)
