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

**A numeric fact's identity is filer-authored too**, so the two attributes
this module does interpolate are admitted only against a declared alphabet
and length — `FACT_IDENTITY_PATTERN` in `vocabulary.py`, beside the closed
sets the parser admits by and under the same rule. A filing carrying an
identity outside it mints nothing and raises.

**No attribute this module reads may be declared more than once.**
`_INTERPRETED_ATTRIBUTES` is that set — the two identity attributes and
`xsi:nil` — and a second occurrence of any of them fails the mint rather
than resolving to one of the two.

The identity attributes carry a second rule the nil flag does not: they must
also be present and non-empty, because an element with no readable identity
mints nothing and a skipped element is a dropped fact. `xsi:nil` is optional
and its absent, empty and unrecognised spellings all mean *not nil*, by the
deliberate leniency recorded at `_NIL_TRUE_VALUES` — an inert extra candidate
is the safe direction there, where a dropped fact is not. The nil flag is
read first for the same reason: a fact reported as nil mints nothing whatever
its identity says, so there is no candidate to lose and no unreadable
identity acted on.

Two ways to get that wrong, and this module has had both. Skipping an
element the reader could not read dropped a fact the filer chose while the
candidate set still reported itself complete. Collapsing the attribute list
with `dict()` kept the final occurrence, so a repeated attribute resolved
last-wins — a document a conformant XBRL processor rejects outright,
resolved here, on input the filer controls. Both are the same steering
channel, and a lenient reader that resolves what a strict resolver refuses
disagrees with every successor built on the strict reading. Refusing keeps
the two from diverging; picking a precedence rule would settle by fiat, in
the most lenient place in the stack, a question no ratified document has
asked.

**The set is per-step in-process state**, by the owner's ruling of
2026-09-20, and it is sealed before it leaves this module. Sealing is the
enforcement AC-0250 reads: a mutation attempted while the agent runs raises
`CandidateSetSealed` and leaves the set unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from html.parser import HTMLParser
from typing import Any, Final
from uuid import UUID

from ced.domain.quarantine.vocabulary import FACT_IDENTITY_PATTERN, REFERENCE_PREFIX

__all__ = [
    "CandidateSet",
    "CandidateSetSealed",
    "UnmintableFactIdentity",
    "mint_candidate_set",
]

#: The inline-XBRL element carrying a numeric fact. Lower-cased because
#: `html.parser` normalises tag and attribute names.
_NUMERIC_FACT_TAG: Final = "ix:nonfraction"

#: The two attributes carrying a numeric fact's identity. Lower-cased for
#: the same reason the tag is: `html.parser` normalises attribute names, so
#: `contextRef` arrives here as `contextref`.
_CONCEPT_ATTRIBUTE: Final = "name"
_CONTEXT_ATTRIBUTE: Final = "contextref"

#: A fact reported as nil has no value, so it can never resolve. A candidate
#: that resolves to nothing is not a candidate.
_NIL_ATTRIBUTE: Final = "xsi:nil"

#: `xsi:nil` is an XML Schema boolean, whose true lexical space is exactly
#: these two spellings. **Value, not presence**: reading presence alone made a
#: perfectly legal `xsi:nil="false"` fact unmintable and therefore uncitable,
#: which hands the filer a say in which evidence can be referenced at all.
#:
#: The `whiteSpace` facet on that type is `collapse`, so the read strips
#: first. Any other spelling is *not* nil and the fact is minted: a candidate
#: that turns out not to resolve is inert, where a silently dropped fact is
#: the steering channel this guard exists to close.
_NIL_TRUE_VALUES: Final = frozenset({"true", "1"})

#: Every attribute this reader interprets, and therefore every attribute the
#: declare-at-most-once rule covers. Declared rather than implied because the
#: rule is only as wide as this set: an attribute read past it would resolve
#: last-wins again, which is the defect the rule exists to close.
#: `test_the_reader_interprets_no_attribute_outside_the_declared_set` is what
#: holds the reader to it.
_INTERPRETED_ATTRIBUTES: Final = (_CONCEPT_ATTRIBUTE, _CONTEXT_ATTRIBUTE, _NIL_ATTRIBUTE)


class UnmintableFactIdentity(Exception):
    """The mint cannot read a numeric fact element unambiguously.

    Raised for an identity the declared alphabet does not permit, and for
    any attribute the reader interprets that the element declares zero times,
    empty, or more than once — see the read-exactly-once rule in this
    module's docstring for why each of those refuses rather than skips.

    Refusing the mint fails the step, and § Boundaries forbids a live fetch,
    so in Phase 1 only the recorded corpus reaches here.
    """


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
        nil = _read_once(attrs, _NIL_ATTRIBUTE)
        if nil is not None and nil.strip() in _NIL_TRUE_VALUES:
            return
        self.identities.add(_identity(attrs))


def _read_once(attrs: Sequence[tuple[str, str | None]], attribute: str) -> str | None:
    """Return the one occurrence of `attribute`, or refuse the mint.

    Takes the attribute list rather than a mapping, and that is the whole
    point: collapsing to a mapping is what hides a second occurrence.
    `None` means the element did not declare it, which each caller judges
    for itself — absent is fatal for an identity attribute and ordinary for
    `xsi:nil`.

    The refusal names the attribute and the count and echoes neither value,
    because everything on this element is filer-authored. `_reference` holds
    the same rule for the same reason — one module, one answer to what a
    refusal may quote.
    """
    if attribute not in _INTERPRETED_ATTRIBUTES:
        raise ValueError(
            f"{attribute!r} is not in _INTERPRETED_ATTRIBUTES; add it there so "
            f"the declare-at-most-once rule covers it before reading it here"
        )
    declared = [value for name, value in attrs if name == attribute]
    if len(declared) > 1:
        raise UnmintableFactIdentity(
            f"a {_NUMERIC_FACT_TAG} element declares {attribute!r} "
            f"{len(declared)} times; nothing ranks the occurrences, so no "
            f"candidate set is minted for this filing"
        )
    return declared[0] if declared else None


def _identity(attrs: Sequence[tuple[str, str | None]]) -> tuple[str, str]:
    """Read one numeric fact element's single identity, or refuse the mint.

    Both attributes are required of `ix:nonFraction` and neither is
    repeatable, so an element missing one, declaring one empty, or declaring
    one twice is not a conforming fact element — and under this module's
    read-exactly-once rule that is a reason to refuse it rather than pass
    over it.
    """
    identity: list[str] = []
    for attribute in (_CONCEPT_ATTRIBUTE, _CONTEXT_ATTRIBUTE):
        value = _read_once(attrs, attribute)
        if not value:
            raise UnmintableFactIdentity(
                f"a {_NUMERIC_FACT_TAG} element declares no readable "
                f"{attribute!r}; it carries no identity to mint a reference "
                f"from, and no candidate set is minted for this filing"
            )
        identity.append(value)
    concept, context = identity
    return concept, context


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

    **Both components must conform to `FACT_IDENTITY_PATTERN`**, or no token
    is minted for this filing at all. Readable is only safe while the filer
    cannot choose what is read: interpolating an unconstrained attribute would
    carry its author's prose inside a value the parser admits on membership
    alone. Excluding the `/` separator from that alphabet is also what makes
    this function injective over `(concept, context)`.
    """
    for role, component in ((_CONCEPT_ATTRIBUTE, concept), (_CONTEXT_ATTRIBUTE, context)):
        if FACT_IDENTITY_PATTERN.fullmatch(component) is None:
            raise UnmintableFactIdentity(
                f"the {role!r} component of a fact identity is {len(component)} "
                f"characters and is not permitted by the declared pattern "
                f"{FACT_IDENTITY_PATTERN.pattern}; its content is filer-authored "
                f"and is not reproduced here. No reference is minted for step "
                f"{step_id}"
            )
    return f"{REFERENCE_PREFIX}{step_id}/xbrl/{concept}/{context}"


def mint_candidate_set(step_id: UUID, filing_html: str) -> CandidateSet:
    """Derive one step's candidate references from a recorded filing, sealed.

    Deterministic: the same filing and step id give the same set, and the set
    is complete and sealed before this returns, so no unsealed set escapes the
    pipeline and nothing can be minted lazily once the agent is running.

    **Not total.** A filing carrying a fact identity outside the declared
    alphabet, or a numeric fact element that carries no readable identity at
    all or more than one, raises `UnmintableFactIdentity` and yields no set,
    because the alternative — returning a set that silently omits it, or one
    built on an arbitrary pick — would report a complete candidate set that
    is not one.
    """
    reader = _NumericFactReader()
    reader.feed(filing_html)
    reader.close()

    candidates = CandidateSet(step_id)
    for concept, context in sorted(reader.identities):
        candidates.add(_reference(step_id, concept, context))
    candidates.seal()
    return candidates
