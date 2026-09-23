"""The ceiling entry: what may be declared, and what a call is decided against.

Two surfaces, and the split is the point.

`declare` is the authoring surface. It refuses a declaration a reviewer
cannot decide — a prefix on an interpreted type, a domain argument that is a
public suffix, a `url` with nothing constraining its host, an argument with no
predicate at all. A call-time refusal would make an undecidable predicate look
like a working one until the wrong argument arrives.

`evaluate` decides a call. It repeats the "every named argument is
constrained" check rather than trusting the authoring surface, because an
entry can reach a database by a migration or predate the refusal, and r5's
conjunction of per-argument predicates is **vacuously true** on any argument
no predicate ranges over. That is AC-0317 to AC-0316's AC-0316.

`evaluate` has three outcomes and no fourth: `Admitted`, `Denied`, and a
`ContainmentUndecidable` raise. There is no "pass the value through".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import publicsuffix2

from ced.domain.containment.canonicaliser import canonicalise, canonicalise_fs_root
from ced.domain.containment.domain_types import DomainType, prefix_expressible
from ced.domain.containment.errors import CeilingDeclarationRefused, ContainmentUndecidable
from ced.domain.containment.predicates import (
    EXPRESSIBLE_PREDICATES,
    HostInDomain,
    Predicate,
    Prefix,
    Within,
    admits,
    constrains_host,
)

__all__ = [
    "Admitted",
    "CeilingArgument",
    "CeilingEntry",
    "Decision",
    "Denied",
    "declare",
    "evaluate",
    "is_public_suffix",
]

#: The bundled dataset AC-0215 resolves against. A hand-kept list of suffixes
#: goes stale silently; a newly delegated suffix in a dataset goes stale
#: loudly, at a version bump a reviewer can see.
_PUBLIC_SUFFIX_LIST: Final[publicsuffix2.PublicSuffixList] = publicsuffix2.PublicSuffixList()


def is_public_suffix(domain: str) -> bool:
    """Return whether `domain` is a public suffix under the bundled dataset.

    Resolved with the list's own default rule, under which a single-label
    domain whose TLD the dataset does not carry is still a public suffix. That
    is the dataset's behaviour, not a local addition: `host_in_domain` over a
    whole TLD admits the internet whether or not the registry is listed.
    """
    longest_suffix: object = _PUBLIC_SUFFIX_LIST.get_tld(domain)
    return longest_suffix == domain


@dataclass(frozen=True)
class CeilingArgument:
    """One argument a ceiling entry names, with the predicates over it.

    `domain_type` is a plain string rather than a `DomainType`, because an
    entry that reached storage by some route other than `declare` may name a
    type this fragment does not know. AC-0315 wants that decided at
    evaluation, and a field that cannot hold the value cannot reach it.
    """

    domain_type: str
    predicates: tuple[Predicate, ...]


@dataclass(frozen=True)
class CeilingEntry:
    """A conjunction of independent per-argument predicates, under one name."""

    name: str
    arguments: Mapping[str, CeilingArgument]


@dataclass(frozen=True)
class Admitted:
    """The call falls inside the ceiling, with the values the adapter receives.

    `canonical` is the whole point of the result type. r5's third rule is that
    the canonical form is what gets passed on; returning only a boolean would
    leave the adapter re-parsing the original and rebuild the differential
    inside our own process.
    """

    canonical: Mapping[str, object]


@dataclass(frozen=True)
class Denied:
    """The call falls outside the ceiling, with the reason it was decided so."""

    reason: str


type Decision = Admitted | Denied


def _refuse(entry_name: str, argument: str, why: str) -> CeilingDeclarationRefused:
    return CeilingDeclarationRefused(
        f"ceiling entry {entry_name!r}, argument {argument!r}: {why}"
    )


def _canonicalise_predicate(predicate: Predicate) -> Predicate:
    """Return `predicate` with its own argument canonicalised.

    A ceiling's host and root are compared against canonical values, so they
    have to be canonical themselves. Comparing a canonical value against a
    literal somebody typed is a string coincidence, not a containment check.
    """
    match predicate:
        case HostInDomain(domain=domain):
            return HostInDomain(domain=domain.lower())
        case Within(root=root):
            return Within(root=canonicalise_fs_root(root))
        case _:
            return predicate


def declare(
    name: str, arguments: Mapping[str, tuple[str, tuple[Predicate, ...]]]
) -> CeilingEntry:
    """Return the ceiling entry, or refuse the declaration.

    `arguments` maps an argument name to its declared domain type and the
    predicates over it. Every refusal names the entry and the argument.
    """
    declared: dict[str, CeilingArgument] = {}
    for argument, (domain_type_name, predicates) in arguments.items():
        try:
            domain_type = DomainType(domain_type_name)
        except ValueError as error:
            raise _refuse(
                name,
                argument,
                f"{domain_type_name!r} is not a declared domain type; the seven are "
                f"{sorted(member.value for member in DomainType)}",
            ) from error

        if not predicates:
            raise _refuse(
                name,
                argument,
                "no predicate is attached to it, and a conjunction over the "
                "arguments somebody remembered to name is vacuously true on the rest",
            )

        expressible = EXPRESSIBLE_PREDICATES[domain_type]
        for predicate in predicates:
            if isinstance(predicate, Prefix) and not prefix_expressible(domain_type):
                raise _refuse(
                    name,
                    argument,
                    f"a string prefix is not expressible on {domain_type.value!r}; the "
                    "callee parses it, and a prefix corresponds to no containment "
                    "relation in the parsed domain",
                )
            if type(predicate) not in expressible:
                raise _refuse(
                    name,
                    argument,
                    f"{type(predicate).__name__} is not expressible on {domain_type.value!r}",
                )
            if isinstance(predicate, HostInDomain) and is_public_suffix(
                predicate.domain.lower()
            ):
                raise _refuse(
                    name,
                    argument,
                    f"{predicate.domain!r} is a public suffix, so host_in_domain over "
                    "it silently admits the internet",
                )

        if domain_type is DomainType.URL and not any(map(constrains_host, predicates)):
            raise _refuse(
                name,
                argument,
                "a url argument carries no host-constraining predicate, so every "
                "host is admitted, including the link-local metadata address",
            )

        declared[argument] = CeilingArgument(
            domain_type=domain_type.value,
            predicates=tuple(_canonicalise_predicate(p) for p in predicates),
        )
    return CeilingEntry(name=name, arguments=declared)


def evaluate(entry: CeilingEntry, call: Mapping[str, object]) -> Decision:
    """Decide `call` against `entry`, or raise when it cannot be decided."""
    canonical: dict[str, object] = {}
    for argument, value in call.items():
        constraint = entry.arguments.get(argument)
        if constraint is None or not constraint.predicates:
            return Denied(
                f"ceiling entry {entry.name!r} attaches no predicate to argument "
                f"{argument!r}, so nothing bounds the value the call supplies"
            )
        try:
            domain_type = DomainType(constraint.domain_type)
        except ValueError as error:
            raise ContainmentUndecidable(
                f"ceiling entry {entry.name!r} declares argument {argument!r} as "
                f"{constraint.domain_type!r}, which this fragment does not recognise"
            ) from error

        canonical_value = canonicalise(domain_type, value)
        for predicate in constraint.predicates:
            if not admits(predicate, canonical_value):
                return Denied(
                    f"argument {argument!r} is outside {type(predicate).__name__} on "
                    f"ceiling entry {entry.name!r}"
                )
        canonical[argument] = canonical_value
    return Admitted(canonical=canonical)
