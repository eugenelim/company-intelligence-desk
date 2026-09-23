"""The property test: `contains` agrees with set containment over real values.

The claim this spec makes about the fragment is set-theoretic — one
predicate's admitted set is a subset of another's — so behaviour at chosen
values is the wrong shape of evidence for it.

**The oracle is a different computation from the one under test, and for two
of the ten arms it is not independent of it.** `contains` answers
symbolically: it compares two predicates' *arguments* and never parses a URL.
The oracle answers extensionally: it runs a universe of concrete values
through the real canonicaliser and `admits`, and asks whether one admitted set
sits inside the other.

What that does not cover: `contains(HostInDomain, …)` and
`admits(HostInDomain, …)` both call `_in_domain`, and `contains(PathWithin, …)`
and `admits(PathWithin, …)` both call `_within_path`. A boundary deleted from
either helper moves both sides of the comparison together and every check in
this module stays green — measured, not supposed. Those two arms are covered
by `test_boundaries_are_load_bearing.py` instead, with direct fixtures on both
sides of a label break and a segment break. This module is not evidence about
them and does not claim to be.

**The universe carries a witness for every predicate generated**, because
every predicate is built from the same pools the universe is built from. That
is what lets a finite check stand in for containment over all strings: a pair
whose analytic answer is "not contained" has a value in the universe that
shows it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import product
from typing import Final

from hypothesis import given
from hypothesis import strategies as st

from ced.domain.containment.canonicaliser import CanonicalUrl, canonicalise
from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.predicates import (
    EXPRESSIBLE_PREDICATES,
    DateRange,
    HostEq,
    HostInDomain,
    InMintedSet,
    NumberRange,
    OneOf,
    PathWithin,
    Predicate,
    Prefix,
    SchemeIn,
    Within,
    admits,
    contains,
)

_SCHEMES: Final[tuple[str, ...]] = ("https", "http", "ftp")
_HOSTS: Final[tuple[str, ...]] = (
    "sec.gov",
    "www.sec.gov",
    "reports.www.sec.gov",
    "sec.gov.attacker.example",
    "attacker.example",
    "example.com",
    "www.example.com",
)
_PATHS: Final[tuple[str, ...]] = ("/", "/evidence/", "/evidence/2024/", "/other/")
_LABELS: Final[tuple[str, ...]] = ("revenue-recognition", "margin-expansion", "tax-rate-change")
_NUMBERS: Final[tuple[Decimal, ...]] = tuple(Decimal(n) for n in range(-2, 6))
_DATES: Final[tuple[date, ...]] = tuple(date(2024, month, 1) for month in range(1, 7))
_OPAQUE: Final[tuple[str, ...]] = ("report-a", "report-b", "draft-a", "a", "")
_ROOTS: Final[tuple[str, ...]] = ("/evidence", "/evidence/filings", "/other")
_FS_PATHS: Final[tuple[str, ...]] = (
    "/evidence",
    "/evidence/x",
    "/evidence/filings",
    "/evidence/filings/x",
    "/evidence-secret/x",
    "/other/x",
)
_LOCATORS: Final[tuple[str, ...]] = ("ref:a", "ref:b", "ref:c")

#: Every URL the oracle evaluates a URL predicate over.
_URL_UNIVERSE: Final[tuple[object, ...]] = tuple(
    canonicalise(DomainType.URL, f"{scheme}://{host}{path}")
    for scheme, host, path in product(_SCHEMES, _HOSTS, _PATHS)
)


@dataclass(frozen=True)
class _Kind:
    """One constructor's generator and the universe its pairs are judged over."""

    constructor: type
    strategy: st.SearchStrategy[Predicate]
    universe: tuple[object, ...]


#: Pairs are drawn same-kind: two predicates over different components stand
#: in no containment relation, and `contains` raises on such a pair rather
#: than answering.
_KINDS: Final[tuple[_Kind, ...]] = (
    _Kind(
        SchemeIn,
        st.sets(st.sampled_from(_SCHEMES), min_size=1).map(
            lambda members: SchemeIn(frozenset(members))
        ),
        _URL_UNIVERSE,
    ),
    _Kind(HostEq, st.sampled_from(_HOSTS).map(HostEq), _URL_UNIVERSE),
    _Kind(
        HostInDomain,
        st.sampled_from(("sec.gov", "www.sec.gov", "example.com")).map(HostInDomain),
        _URL_UNIVERSE,
    ),
    _Kind(PathWithin, st.sampled_from(_PATHS).map(PathWithin), _URL_UNIVERSE),
    _Kind(
        OneOf,
        st.sets(st.sampled_from(_LABELS)).map(lambda members: OneOf(frozenset(members))),
        _LABELS,
    ),
    _Kind(
        NumberRange,
        st.tuples(st.sampled_from(_NUMBERS), st.sampled_from(_NUMBERS)).map(
            lambda bounds: NumberRange(low=bounds[0], high=bounds[1])
        ),
        _NUMBERS,
    ),
    _Kind(Prefix, st.sampled_from(_OPAQUE).map(Prefix), _OPAQUE),
    _Kind(Within, st.sampled_from(_ROOTS).map(Within), _FS_PATHS),
    _Kind(
        InMintedSet,
        st.sets(st.sampled_from(_LOCATORS)).map(
            lambda members: InMintedSet(frozenset(members))
        ),
        _LOCATORS,
    ),
    _Kind(
        DateRange,
        st.tuples(st.sampled_from(_DATES), st.sampled_from(_DATES)).map(
            lambda bounds: DateRange(low=bounds[0], high=bounds[1])
        ),
        _DATES,
    ),
)


def _pairs() -> st.SearchStrategy[tuple[Predicate, Predicate, tuple[object, ...]]]:
    return st.one_of(
        *(st.tuples(kind.strategy, kind.strategy, st.just(kind.universe)) for kind in _KINDS)
    )


def _admitted(predicate: Predicate, universe: Sequence[object]) -> frozenset[int]:
    """Return the universe positions `predicate` admits, by evaluating each."""
    return frozenset(index for index, value in enumerate(universe) if admits(predicate, value))


def test_every_constructor_contains_answers_for_is_generated() -> None:
    """Setup check: an arm no pair reaches can be replaced by `return True`.

    `contains` is exported and is the `role.ceiling ⊆ parent_role.ceiling`
    primitive r5 computes per field, so an arm no pair reaches ships as
    untested authorization logic. The expected set is read from
    `EXPRESSIBLE_PREDICATES`, which is what the authoring surface admits, so
    a constructor added to the fragment reds here until it is generated.
    """
    expressible: set[type] = set()
    for row in EXPRESSIBLE_PREDICATES.values():
        expressible |= set(row)
    assert {kind.constructor for kind in _KINDS} == expressible


@given(_pairs())
def test_contains_agrees_with_set_containment(
    pair: tuple[Predicate, Predicate, tuple[object, ...]],
) -> None:
    outer, inner, universe = pair
    assert contains(outer, inner) == (_admitted(inner, universe) <= _admitted(outer, universe))


@given(_pairs())
def test_containment_is_reflexive(
    pair: tuple[Predicate, Predicate, tuple[object, ...]],
) -> None:
    outer, _, _ = pair
    assert contains(outer, outer)


@given(_pairs())
def test_a_contained_predicate_admits_nothing_its_container_refuses(
    pair: tuple[Predicate, Predicate, tuple[object, ...]],
) -> None:
    """The property in the form the authorization rule uses it.

    `may_run` reads `role.ceiling ⊆ parent_role.ceiling`, so what has to hold
    is that containment implies no value escapes upward.
    """
    outer, inner, universe = pair
    if not contains(outer, inner):
        return
    for value in universe:
        assert not admits(inner, value) or admits(outer, value)


def test_the_universe_has_a_witness_for_every_generated_predicate() -> None:
    """Setup check: a finite universe with no witness makes the property vacuous.

    Every pool member the strategies draw from appears in the universe, and
    each non-empty predicate kind admits at least one value there. Without
    this, `contains` could return `True` for a disjoint pair and the oracle
    would agree by having nothing to disagree with.
    """
    hosts = {url.host for url in _URL_UNIVERSE if isinstance(url, CanonicalUrl)}
    assert hosts == set(_HOSTS)
    for domain in ("sec.gov", "www.sec.gov", "example.com"):
        assert _admitted(HostInDomain(domain), _URL_UNIVERSE)
    for path in _PATHS:
        assert _admitted(PathWithin(path), _URL_UNIVERSE)
    for host in _HOSTS:
        assert _admitted(HostEq(host), _URL_UNIVERSE)
    for root in _ROOTS:
        assert _admitted(Within(root), _FS_PATHS)
    for locator in _LOCATORS:
        assert _admitted(InMintedSet(frozenset({locator})), _LOCATORS)
    for moment in _DATES:
        assert _admitted(DateRange(moment, moment), _DATES)
    assert _admitted(Prefix("report-"), _OPAQUE)


def test_the_oracle_can_tell_a_non_containing_pair_apart() -> None:
    """Mutation check on the oracle itself, not on the fragment.

    A universe that admitted everything, or an oracle that always returned
    the empty set, would make the property above pass for any implementation
    of `contains`. This is the pair that would red if either happened.
    """
    wide = HostInDomain("sec.gov")
    narrow = HostInDomain("www.sec.gov")
    assert not contains(narrow, wide)
    assert not _admitted(wide, _URL_UNIVERSE) <= _admitted(narrow, _URL_UNIVERSE)
