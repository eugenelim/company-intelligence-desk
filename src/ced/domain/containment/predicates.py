"""The decidable fragment: the predicates a ceiling may be written in.

`worker-runtime.md` r5 § 4 closes the fragment over "closed enumerations,
string prefixes, numeric ranges and set membership, combined as a conjunction
of independent per-argument predicates", and gives the per-type table this
module implements:

  `url`              `scheme_in{…}` · `host_eq(h)` · `host_in_domain(d)` ·
                     `path_within(p)` on the normalized path
  `fs-path`          `within(root)` after full normalization
  `content-locator`  membership in the runtime-minted set for this step
  `opaque-string`    `prefix(p)`, the one type it is sound on

`enum`, `number` and `date` take the fragment's other three constructors.

Two operations over a predicate, and they answer different questions.
`admits` asks whether a canonical value falls inside one; `contains` asks
whether one predicate's admitted set is a subset of another's, which is the
per-field `⊆` r5 computes containment with. `contains` refuses a pair drawn
from different fields rather than answering `False`, because two predicates
over different components stand in no containment relation and a `False` there
would read as "not contained" to a caller that cannot tell the difference.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from ced.domain.containment.canonicaliser import CanonicalUrl
from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.errors import ContainmentUndecidable

__all__ = [
    "EXPRESSIBLE_PREDICATES",
    "DateRange",
    "HostEq",
    "HostInDomain",
    "InMintedSet",
    "NumberRange",
    "OneOf",
    "PathWithin",
    "Predicate",
    "Prefix",
    "SchemeIn",
    "Within",
    "admits",
    "constrains_host",
    "contains",
]


@dataclass(frozen=True)
class Prefix:
    """A string prefix. Sound only where the callee does not parse the value."""

    value: str


@dataclass(frozen=True)
class SchemeIn:
    """Membership of a URL's scheme in a closed set."""

    schemes: frozenset[str]


@dataclass(frozen=True)
class HostEq:
    """Exact match on a URL's parsed host."""

    host: str


@dataclass(frozen=True)
class HostInDomain:
    """A host equal to `domain` or a subdomain of it.

    r5 absorbs this disjunction into one primitive deliberately: "`sec.gov` or
    any subdomain of it" is what an allowlist needs, and expressing it as a
    disjunction would break structural containment.
    """

    domain: str


@dataclass(frozen=True)
class PathWithin:
    """A URL path at or below `prefix`, on the normalized path only."""

    prefix: str


@dataclass(frozen=True)
class Within:
    """A filesystem path at or below `root`, after full normalization."""

    root: str


@dataclass(frozen=True)
class InMintedSet:
    """Membership in the reference set the runtime minted for this step."""

    members: frozenset[str]


@dataclass(frozen=True)
class OneOf:
    """Membership in a closed enumeration."""

    members: frozenset[str]


@dataclass(frozen=True)
class NumberRange:
    """An inclusive numeric range."""

    low: Decimal
    high: Decimal


@dataclass(frozen=True)
class DateRange:
    """An inclusive date range."""

    low: date
    high: date


type Predicate = (
    Prefix
    | SchemeIn
    | HostEq
    | HostInDomain
    | PathWithin
    | Within
    | InMintedSet
    | OneOf
    | NumberRange
    | DateRange
)

#: Which constructors each domain type admits. A declaration naming a
#: predicate outside its type's row is refused at authoring time: the type
#: decides which predicates are expressible, which is r5's first rule.
EXPRESSIBLE_PREDICATES: Final[dict[DomainType, frozenset[type]]] = {
    DomainType.OPAQUE_STRING: frozenset({Prefix, OneOf}),
    DomainType.URL: frozenset({SchemeIn, HostEq, HostInDomain, PathWithin}),
    DomainType.FS_PATH: frozenset({Within}),
    DomainType.CONTENT_LOCATOR: frozenset({InMintedSet}),
    DomainType.ENUM: frozenset({OneOf}),
    DomainType.NUMBER: frozenset({NumberRange}),
    DomainType.DATE: frozenset({DateRange}),
}

#: The constructors that constrain which host a `url` argument may name.
#: AC-0240 requires one of these to be present on every `url` argument; it
#: does not constrain which host the predicate then admits.
_HOST_CONSTRAINING: Final[frozenset[type]] = frozenset({HostEq, HostInDomain})


def constrains_host(predicate: Predicate) -> bool:
    """Return whether `predicate` restricts which host a URL may name."""
    return type(predicate) in _HOST_CONSTRAINING


def _in_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _within_path(path: str, prefix: str) -> bool:
    bounded = prefix.rstrip("/")
    return path == bounded or path.startswith(f"{bounded}/")


def _undecidable(predicate: Predicate, value: object) -> ContainmentUndecidable:
    return ContainmentUndecidable(
        f"{type(predicate).__name__} cannot be evaluated against a "
        f"{type(value).__name__}, so whether the value is inside is undecided"
    )


def admits(predicate: Predicate, value: object) -> bool:
    """Return whether the canonical `value` falls inside `predicate`.

    Raises `ContainmentUndecidable` when the predicate does not range over a
    value of that shape — AC-0315's third case. Returning `False` there would
    be a denial, which reads as a decision the fragment did not make.
    """
    match predicate:
        case Prefix(value=prefix):
            if not isinstance(value, str):
                raise _undecidable(predicate, value)
            return value.startswith(prefix)
        case SchemeIn(schemes=schemes):
            if not isinstance(value, CanonicalUrl):
                raise _undecidable(predicate, value)
            return value.scheme in schemes
        case HostEq(host=host):
            if not isinstance(value, CanonicalUrl):
                raise _undecidable(predicate, value)
            return value.host == host
        case HostInDomain(domain=domain):
            if not isinstance(value, CanonicalUrl):
                raise _undecidable(predicate, value)
            return _in_domain(value.host, domain)
        case PathWithin(prefix=prefix):
            if not isinstance(value, CanonicalUrl):
                raise _undecidable(predicate, value)
            return _within_path(value.path, prefix)
        case Within(root=root):
            if not isinstance(value, str):
                raise _undecidable(predicate, value)
            return value == root or value.startswith(root.rstrip(os.sep) + os.sep)
        case InMintedSet(members=members) | OneOf(members=members):
            if not isinstance(value, str):
                raise _undecidable(predicate, value)
            return value in members
        case NumberRange(low=low, high=high):
            if isinstance(value, bool) or not isinstance(value, int | Decimal):
                raise _undecidable(predicate, value)
            return low <= Decimal(value) <= high
        case DateRange(low=low, high=high):
            if not isinstance(value, date):
                raise _undecidable(predicate, value)
            return low <= value <= high


def contains(outer: Predicate, inner: Predicate) -> bool:
    """Return whether every value `inner` admits is one `outer` admits.

    Raises `ContainmentUndecidable` for a pair over different fields — a
    scheme constraint and a host constraint restrict different components and
    neither contains the other, so there is no answer to give.
    """
    if type(outer) is not type(inner):
        raise ContainmentUndecidable(
            f"{type(outer).__name__} and {type(inner).__name__} range over different "
            "components, so neither contains the other"
        )
    match outer, inner:
        case Prefix(value=wide), Prefix(value=narrow):
            return narrow.startswith(wide)
        case SchemeIn(schemes=wide_set), SchemeIn(schemes=narrow_set):
            return narrow_set <= wide_set
        case HostEq(host=wide_host), HostEq(host=narrow_host):
            return wide_host == narrow_host
        case HostInDomain(domain=wide_domain), HostInDomain(domain=narrow_domain):
            return _in_domain(narrow_domain, wide_domain)
        case PathWithin(prefix=wide_path), PathWithin(prefix=narrow_path):
            return _within_path(narrow_path.rstrip("/"), wide_path)
        case Within(root=wide_root), Within(root=narrow_root):
            bounded = wide_root.rstrip(os.sep)
            return narrow_root == bounded or narrow_root.startswith(bounded + os.sep)
        case InMintedSet(members=wide_set), InMintedSet(members=narrow_set):
            return narrow_set <= wide_set
        case OneOf(members=wide_set), OneOf(members=narrow_set):
            return narrow_set <= wide_set
        case NumberRange(low=wide_low, high=wide_high), NumberRange(low=low, high=high):
            return low > high or (wide_low <= low and high <= wide_high)
        case DateRange(low=wide_low, high=wide_high), DateRange(low=low, high=high):
            return low > high or (wide_low <= low and high <= wide_high)
        case _:  # pragma: no cover — the type check above makes this unreachable
            raise ContainmentUndecidable(f"no containment rule for {type(outer).__name__}")
