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

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import publicsuffix2

from ced.domain.containment.canonicaliser import (
    canonicalise,
    canonicalise_fs_root,
    canonicalise_host,
    canonicalise_url_path,
)
from ced.domain.containment.domain_types import DomainType, prefix_expressible
from ced.domain.containment.errors import (
    CeilingDeclarationRefused,
    ContainmentUndecidable,
    for_the_record,
)
from ced.domain.containment.predicates import (
    EXPRESSIBLE_PREDICATES,
    HostEq,
    HostInDomain,
    InMintedSet,
    OneOf,
    PathWithin,
    Predicate,
    Prefix,
    SchemeIn,
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
    "PUBLIC_SUFFIX_DATASET_AS_OF",
    "declare",
    "evaluate",
    "is_public_suffix",
    "longest_public_suffix",
]

#: The bundled dataset AC-0215 resolves against, and the day its snapshot was
#: published. **There is no refresh path.** `publicsuffix2` has shipped no
#: release since this one, so the suffixes delegated after that date — the
#: platform suffixes under which anyone can register a name are the ones that
#: matter — answer `False` here and are authorable. An earlier comment claimed
#: a bundled dataset "goes stale at a version bump a reviewer can see"; no bump
#: exists, so the staleness is silent and the plan's § Risks entry is the only
#: thing naming it. Recorded in the verification ledger for the owner.
PUBLIC_SUFFIX_DATASET_AS_OF: Final[str] = "2019-12-21"

#: The suffix oracle, as a module-level name a test can substitute. A dataset
#: reached only through a singleton built at import is a dataset no test can
#: pin, and the risk this dependency carries is precisely that its answers
#: drift from the registry's.
_PUBLIC_SUFFIX_LIST: Final[publicsuffix2.PublicSuffixList] = publicsuffix2.PublicSuffixList()


def longest_public_suffix(domain: str) -> str | None:
    """Return the longest public suffix of `domain` under the bundled dataset.

    The seam `is_public_suffix` asks. Separate from it so a test can pin the
    answer for a suffix the snapshot predates, without reaching into the
    dependency.
    """
    suffix: object = _PUBLIC_SUFFIX_LIST.get_tld(domain)
    return suffix if isinstance(suffix, str) else None


def is_public_suffix(domain: str) -> bool:
    """Return whether `domain` is a public suffix under the bundled dataset.

    Resolved with the list's own default rule, under which a single-label
    domain whose TLD the dataset does not carry is still a public suffix. That
    is the dataset's behaviour, not a local addition: `host_in_domain` over a
    whole TLD admits the internet whether or not the registry is listed.

    **A suffix delegated after `PUBLIC_SUFFIX_DATASET_AS_OF` answers `False`**
    and is authorable. That is the dependency's limit, not this function's.
    """
    return longest_public_suffix(domain) == domain


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


#: How many members of a set-valued predicate a denial may name before it
#: reports a count instead. Small, because the text is recorded once per
#: refused call and a ceiling's author chooses the set's size.
_SET_LISTING_BUDGET: Final[int] = 8


def _describe(predicate: Predicate) -> str:
    """Return a denial-safe description of `predicate`.

    A set-valued predicate is summarised rather than enumerated. An
    `in_minted_set` denial would otherwise write every reference the runtime
    minted for that step into the event log, which is a disclosure the
    denial does not need to be legible.
    """
    match predicate:
        case InMintedSet(members=members):
            return f"in_minted_set over {len(members)} minted reference(s)"
        case OneOf(members=members):
            return f"one_of over {len(members)} member(s)"
        case SchemeIn(schemes=schemes):
            # Listed while a reader can take it in, because which schemes a
            # ceiling admits is the useful part of this denial; counted past
            # that, because the set is as large as its author made it and
            # this text is recorded.
            if len(schemes) > _SET_LISTING_BUDGET:
                return f"scheme_in over {len(schemes)} scheme(s)"
            return f"scheme_in{sorted(schemes)}"
        case _:
            # Bounded like the named arms. A `prefix` argument is
            # author-controlled rather than model-chosen, so nobody can grow
            # it on purpose — but the text is still recorded once per refused
            # call, and a constructor added later inherits the bound here
            # rather than needing somebody to remember this arm.
            return for_the_record(predicate)


def _refuse(entry_name: str, argument: str, why: str) -> CeilingDeclarationRefused:
    """Return the refusal, with the two fields this function owns bounded.

    `why` arrives already composed and is not bounded again here: bounding
    it a second time would cut the prose rather than the value, and
    `tests/containment/test_every_message_is_bounded_by_construction.py`
    is what holds that every interpolation inside a caller's `why` went
    through `for_the_record` first.
    """
    return CeilingDeclarationRefused(
        f"ceiling entry {for_the_record(entry_name)}, argument "
        f"{for_the_record(argument)}: {why}"
    )


def _canonicalise_predicate(predicate: Predicate) -> Predicate:
    """Return `predicate` with its own argument canonicalised.

    **Every predicate whose argument is compared against a canonical value is
    handled here**, and that is the whole list: the two host constructors, the
    URL path prefix, and the filesystem root. Comparing a canonical value
    against a literal somebody typed is a string coincidence, not a
    containment check — and it fails closed, so a ceiling written as
    `host_eq("WWW.SEC.GOV")` would be accepted at authoring time and then deny
    every call, silently, with no criterion reding.

    The remaining constructors range over values the canonicaliser passes
    through unchanged, so their arguments are already in the compared form.
    """
    match predicate:
        case HostEq(host=host):
            return HostEq(host=canonicalise_host(host))
        case HostInDomain(domain=domain):
            return HostInDomain(domain=canonicalise_host(domain))
        case PathWithin(prefix=prefix):
            return PathWithin(prefix=canonicalise_url_path(prefix))
        case Within(root=root):
            if not os.path.isabs(root):
                raise ContainmentUndecidable(
                    f"within({for_the_record(root)}) names no absolute root, so it "
                    "resolves "
                    "against whatever directory the worker started in: the "
                    "declaration's text does not say what it admits, and two "
                    "workers enforce different ceilings from it"
                )
            return Within(root=canonicalise_fs_root(root))
        case _:
            return predicate


def declare(
    name: str, arguments: Mapping[str, tuple[str, tuple[Predicate, ...]]]
) -> CeilingEntry:
    """Return the ceiling entry, or refuse the declaration.

    `arguments` maps an argument name to its declared domain type and the
    predicates over it. Every refusal names the entry and the argument.

    **Every refusal is a `CeilingDeclarationRefused`**, including one that
    began as a value the canonicaliser could not decide. Letting
    `ContainmentUndecidable` out of here would hand the decision point the
    signal it reads as a denied call, for a declaration that is simply not
    authorable — the confusion the two types exist to keep apart.
    """
    declared: dict[str, CeilingArgument] = {}
    for argument, (domain_type_name, predicates) in arguments.items():
        try:
            domain_type = DomainType(domain_type_name)
        except ValueError as error:
            raise _refuse(
                name,
                argument,
                f"{for_the_record(domain_type_name)} is not a declared domain type; the "
                "seven are "
                f"{for_the_record(sorted(member.value for member in DomainType))}",
            ) from error

        if not predicates:
            raise _refuse(
                name,
                argument,
                "no predicate is attached to it, and a conjunction over the "
                "arguments somebody remembered to name is vacuously true on the rest",
            )

        # Canonicalising first is what keeps every later check working on the
        # form it compares against — and it is what keeps `declare` from
        # leaking `ContainmentUndecidable`, which the decision point reads as
        # a call denial rather than as an unauthorable declaration.
        try:
            canonical = tuple(_canonicalise_predicate(p) for p in predicates)
        except ContainmentUndecidable as error:
            raise _refuse(
                name,
                argument,
                f"a predicate argument has no canonical form: {for_the_record(error)}",
            ) from error

        expressible = EXPRESSIBLE_PREDICATES[domain_type]
        for predicate in canonical:
            if isinstance(predicate, Prefix) and not prefix_expressible(domain_type):
                raise _refuse(
                    name,
                    argument,
                    "a string prefix is not expressible on "
                    f"{for_the_record(domain_type.value)}; the callee parses it, "
                    "and a prefix corresponds to no containment relation in the "
                    "parsed domain",
                )
            if type(predicate) not in expressible:
                raise _refuse(
                    name,
                    argument,
                    f"{for_the_record(type(predicate).__name__)} is not expressible on "
                    f"{for_the_record(domain_type.value)}",
                )
            if isinstance(predicate, HostInDomain) and is_public_suffix(predicate.domain):
                raise _refuse(
                    name,
                    argument,
                    f"{for_the_record(predicate.domain)} is a public suffix, so host_in_domain "
                    "over "
                    "it silently admits the internet",
                )
            # The filesystem twin of the line above, and refused on the same
            # grounds: a root that bounds nothing is a predicate that is
            # present and decides nothing. Beyond AC-0316, which requires a
            # predicate to exist and not to constrain anything in particular.
            if isinstance(predicate, Within) and predicate.root == os.sep:
                raise _refuse(
                    name,
                    argument,
                    "within(/) is the whole filesystem, so the predicate is present "
                    "and bounds nothing",
                )

        if domain_type is DomainType.URL and not any(map(constrains_host, canonical)):
            raise _refuse(
                name,
                argument,
                "a url argument carries no host-constraining predicate, so every "
                "host is admitted, including the link-local metadata address",
            )

        # Beyond AC-0240, and fail-closed on purpose. A host constraint only
        # constrains what the callee reaches if the scheme makes the host
        # mean something: `file://sec.gov/etc/passwd` satisfies
        # `host_eq("sec.gov")` and every resolver ignores that authority, so
        # the one predicate AC-0240 forces to be present decides nothing. The
        # scheme allowlist is the control the host constraint presupposes.
        # Recorded in the verification ledger as a strengthening the owner
        # has not ratified.
        if domain_type is DomainType.URL and not any(
            isinstance(predicate, SchemeIn) for predicate in canonical
        ):
            raise _refuse(
                name,
                argument,
                "a url argument carries no scheme-constraining predicate, so a "
                "scheme that ignores the authority — `file:` above all — turns "
                "its host predicate into a constraint on nothing",
            )

        declared[argument] = CeilingArgument(
            domain_type=domain_type.value, predicates=canonical
        )
    return CeilingEntry(name=name, arguments=declared)


def evaluate(entry: CeilingEntry, call: Mapping[str, object]) -> Decision:
    """Decide `call` against `entry`, or raise when it cannot be decided.

    **A call has to supply every argument the entry constrains.** Deciding
    only what the call happens to pass would make `evaluate(entry, {})` an
    admission against any ceiling however tightly written, and would leave
    whatever default the callee binds for an omitted parameter outside the
    ceiling entirely. That is the same vacuous conjunction AC-0316 and
    AC-0317 close from the other side — there, an argument no predicate
    ranges over; here, a predicate no argument arrives for. An entry whose
    tool has a genuinely optional argument declares the arguments it will
    always receive.

    Three outcomes and no fourth: `Admitted`, `Denied`, or a
    `ContainmentUndecidable` raise. Nothing is passed through undecided.
    """
    missing = sorted(set(entry.arguments) - set(call))
    if missing:
        return Denied(
            f"ceiling entry {for_the_record(entry.name)} constrains "
            f"{for_the_record(', '.join(missing))}, and the call supplies neither "
            "a value for them nor anything this fragment could decide in their "
            "place"
        )

    canonical: dict[str, object] = {}
    for argument, value in call.items():
        constraint = entry.arguments.get(argument)
        if constraint is None or not constraint.predicates:
            return Denied(
                f"ceiling entry {for_the_record(entry.name)} attaches no predicate to argument "
                f"{for_the_record(argument)}, so nothing bounds the value the "
                "call supplies"
            )
        try:
            domain_type = DomainType(constraint.domain_type)
        except ValueError as error:
            raise ContainmentUndecidable(
                f"ceiling entry {for_the_record(entry.name)} declares argument "
                f"{for_the_record(argument)} as "
                f"{for_the_record(constraint.domain_type)}, which this fragment "
                "does not recognise"
            ) from error

        canonical_value = canonicalise(domain_type, value)
        for predicate in constraint.predicates:
            if not admits(predicate, canonical_value):
                # The reason has to let a reader reconstruct the mismatch. A
                # denial naming only the predicate's type puts a
                # `policy.decision` in the event log that records a refusal
                # and not why the value did not match, which in a system
                # whose event log is its inspection surface is half a record.
                # Both halves are bounded: the value because the caller
                # chooses its length, the predicate because a set-valued one
                # would otherwise enumerate itself into the log.
                return Denied(
                    f"argument {for_the_record(argument)} is outside "
                    f"{_describe(predicate)} on "
                    f"ceiling entry {for_the_record(entry.name)}: the canonical value is "
                    f"{for_the_record(canonical_value)}"
                )
        canonical[argument] = canonical_value
    return Admitted(canonical=canonical)
