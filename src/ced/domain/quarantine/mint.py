"""Minting the candidate reference set, before any model sees the filing.

`runtime-architecture.md` r8 § 4 Contracts and Invariants: *"The model never
produces a reference, and that is the difference between detecting forgery and
making it unrepresentable."* A deterministic pipeline runs **before** the
quarantined agent and produces the candidates; the agent's job shrinks to
selecting and labelling among values that already resolve.

**This is not the construction Phase 0 tested.** Spike 4 ran the weaker one —
the agent emitted anchors and a parser rejected those that failed to resolve —
and 1 in 8 were fabricated with no adversary present. The same run found that a
verbatim-substring anchor cannot resolve a fact assembled from table cells, so
a prose-quote reference type systematically drops the figures this product
exists to analyse. Quantitative claims therefore cross as XBRL fact
references, which is what this module mints.

**What this mints, and what it does not.** It mints one candidate per distinct
inline-XBRL numeric fact identity — concept name plus context — read from the
recorded filing with the standard library's HTML parser. It does **not** mint
parsed table cells with their coordinates, nor section boundaries, both of
which r8 § 4 names as part of the eventual pipeline; those arrive with the
evidence-acquisition path, which no task in this spec builds. It deliberately
mints nothing from `ix:nonNumeric` elements: those carry filer-authored text,
which is the thing the boundary exists to keep out.

**The set is per-step in-process state**, by the owner's ruling of
2026-09-20, and it is sealed before it leaves this module. Sealing is the
enforcement AC-0250 reads: a mutation attempted while the agent runs raises
`CandidateSetSealed` and leaves the set unchanged.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Final
from uuid import UUID

from ced.domain.quarantine.vocabulary import REFERENCE_PREFIX

__all__ = ["CandidateSet", "CandidateSetSealed", "mint_candidate_set"]

#: The inline-XBRL element carrying a numeric fact. Lower-cased because
#: `html.parser` normalises tag and attribute names.
_NUMERIC_FACT_TAG: Final = "ix:nonfraction"

#: A fact reported as nil has no value, so it can never resolve. A candidate
#: that resolves to nothing is not a candidate.
_NIL_ATTRIBUTE: Final = "xsi:nil"


class CandidateSetSealed(Exception):
    """The candidate set was mutated after the mint completed.

    The runtime's own refusal, named so that AC-0250 observes a built guard
    rather than an incidental `TypeError` from a frozen container.
    """


class CandidateSet:
    """The references the runtime minted for one step, and nothing else.

    Sealed once the pipeline finishes, after which `add` refuses and the
    `sealed` flag cannot be rebound to reopen it. `references` hands out a
    `frozenset`, so no caller ever holds the mutable interior.
    """

    def __init__(self, step_id: UUID) -> None:
        self.step_id = step_id
        self._references: set[str] = set()
        self.sealed = False

    def __setattr__(self, name: str, value: Any) -> None:
        """Refuse every rebinding once sealed, `sealed` itself included."""
        if getattr(self, "sealed", False):
            raise CandidateSetSealed(
                f"the candidate set for step {self.step_id} is sealed; "
                f"{name!r} cannot be rebound after the mint"
            )
        object.__setattr__(self, name, value)

    def add(self, reference: str) -> None:
        """Record one minted reference, or refuse because the mint is over."""
        if self.sealed:
            raise CandidateSetSealed(
                f"the candidate set for step {self.step_id} is sealed; "
                f"{reference!r} was not minted for it and cannot be added"
            )
        self._references.add(reference)

    def seal(self) -> None:
        """Close the set. Idempotent, so sealing twice is not a refusal."""
        object.__setattr__(self, "sealed", True)

    @property
    def references(self) -> frozenset[str]:
        """An immutable read of everything the pipeline minted for this step."""
        return frozenset(self._references)

    def __contains__(self, reference: object) -> bool:
        """Whether this step's mint produced `reference`. The provenance test."""
        return reference in self._references

    def __len__(self) -> int:
        return len(self._references)

    def __repr__(self) -> str:
        return (
            f"CandidateSet(step_id={self.step_id!s}, "
            f"references={len(self)}, sealed={self.sealed})"
        )


class _NumericFactReader(HTMLParser):
    """Collects the identity of every non-nil inline-XBRL numeric fact.

    The standard library's parser rather than a new dependency: the filing is
    inline XBRL embedded in HTML, the elements wanted are identified by tag
    and attributes alone, and nothing here needs a document tree.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.identities: set[tuple[str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record `(concept, context)` for one numeric fact element."""
        if tag != _NUMERIC_FACT_TAG:
            return
        attributes = dict(attrs)
        if attributes.get(_NIL_ATTRIBUTE) is not None:
            return
        concept = attributes.get("name")
        context = attributes.get("contextref")
        if concept and context:
            self.identities.add((concept, context))


def _reference(step_id: UUID, concept: str, context: str) -> str:
    """The minted token for one fact, scoped to the step it was minted for.

    The step scope is inside the token because r5 § 4 states the invariant as
    a reference resolving against the set *the runtime minted for this step*.
    Without it, two steps over the same evidence mint interchangeable tokens
    and "did not mint for the current candidate set" has nothing to decide.

    Readable rather than hashed, on purpose. Unpredictability buys nothing —
    the quarantined agent is handed the candidate set, so it already knows
    every token — and a readable token makes the committed baseline a
    reviewable diff.
    """
    return f"{REFERENCE_PREFIX}{step_id}/xbrl/{concept}/{context}"


def mint_candidate_set(step_id: UUID, filing_html: str) -> CandidateSet:
    """Derive one step's candidate references from a recorded filing, sealed.

    Deterministic and total over the input: the same filing and step id give
    the same set, and the set is complete and sealed before this returns, so
    no unsealed set escapes the pipeline and nothing can be minted lazily
    once the agent is running.
    """
    reader = _NumericFactReader()
    reader.feed(filing_html)
    reader.close()

    candidates = CandidateSet(step_id)
    for concept, context in sorted(reader.identities):
        candidates.add(_reference(step_id, concept, context))
    candidates.seal()
    return candidates
