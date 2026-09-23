"""The property test: `contains` agrees with set containment over real values.

The claim this spec makes about the fragment is set-theoretic — one
predicate's admitted set is a subset of another's — so behaviour at chosen
values is the wrong shape of evidence for it.

**The oracle does not share the implementation under test.** `contains`
answers symbolically: it compares two predicates' *arguments* and never parses
a URL. The oracle answers extensionally: it runs a universe of concrete values
through the real canonicaliser and `admits`, and asks whether one admitted set
sits inside the other. The two computations meet only at their answer, which
is what makes disagreement informative rather than circular.

**The universe carries a witness for every predicate generated**, because
every predicate is built from the same pools the universe is built from. That
is what lets a finite check stand in for containment over all strings: a pair
whose analytic answer is "not contained" has a value in the universe that
shows it.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from itertools import product
from typing import Final

from hypothesis import given
from hypothesis import strategies as st

from ced.domain.containment.canonicaliser import canonicalise
from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.predicates import (
    HostEq,
    HostInDomain,
    NumberRange,
    OneOf,
    PathWithin,
    Predicate,
    SchemeIn,
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

#: Every URL the oracle evaluates a URL predicate over.
_URL_UNIVERSE: Final[tuple[object, ...]] = tuple(
    canonicalise(DomainType.URL, f"{scheme}://{host}{path}")
    for scheme, host, path in product(_SCHEMES, _HOSTS, _PATHS)
)

_scheme_in = st.sets(st.sampled_from(_SCHEMES), min_size=1).map(
    lambda members: SchemeIn(frozenset(members))
)
_host_eq = st.sampled_from(_HOSTS).map(HostEq)
_host_in_domain = st.sampled_from(("sec.gov", "www.sec.gov", "example.com")).map(HostInDomain)
_path_within = st.sampled_from(_PATHS).map(PathWithin)
_one_of = st.sets(st.sampled_from(_LABELS)).map(lambda members: OneOf(frozenset(members)))
_number_range = st.tuples(st.sampled_from(_NUMBERS), st.sampled_from(_NUMBERS)).map(
    lambda bounds: NumberRange(low=bounds[0], high=bounds[1])
)

#: Pairs are drawn same-kind: two predicates over different components stand
#: in no containment relation, and `contains` raises on such a pair rather
#: than answering. Each entry carries the universe its kind is judged over.
_KINDS: Final[tuple[tuple[st.SearchStrategy[Predicate], tuple[object, ...]], ...]] = (
    (_scheme_in, _URL_UNIVERSE),
    (_host_eq, _URL_UNIVERSE),
    (_host_in_domain, _URL_UNIVERSE),
    (_path_within, _URL_UNIVERSE),
    (_one_of, _LABELS),
    (_number_range, _NUMBERS),
)


def _pairs() -> st.SearchStrategy[tuple[Predicate, Predicate, tuple[object, ...]]]:
    return st.one_of(*(st.tuples(kind, kind, st.just(universe)) for kind, universe in _KINDS))


def _admitted(predicate: Predicate, universe: Sequence[object]) -> frozenset[int]:
    """Return the universe positions `predicate` admits, by evaluating each."""
    return frozenset(index for index, value in enumerate(universe) if admits(predicate, value))


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
    hosts = {url.host for url in _URL_UNIVERSE if hasattr(url, "host")}
    assert hosts == set(_HOSTS)
    for domain in ("sec.gov", "www.sec.gov", "example.com"):
        assert _admitted(HostInDomain(domain), _URL_UNIVERSE)
    for path in _PATHS:
        assert _admitted(PathWithin(path), _URL_UNIVERSE)
    for host in _HOSTS:
        assert _admitted(HostEq(host), _URL_UNIVERSE)


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
