"""Compiling a stored ceiling into the containment fragment's entries.

Revision 0003 fixed a ceiling entry's three binding fields and put the
`predicates` encoding out of scope, and `walking-skeleton-authority-containment`
shipped the fragment without it. So until this module existed there was no route
from a registry row to `evaluate`, and the decision point above had nothing to
look up. This is that route, and it is the only one.

**Every entry is built through `declare`.** `CeilingEntry` is a directly
constructible frozen dataclass and both `agent_role.ceiling` and
`entitlements.ceiling` are bare `jsonb` with no CHECK, written by operator
insert. A decoder that built the dataclass itself would admit a stored row
encoding `scheme_in{file}` beside a host prefix, or `within("")` — which reaches
`admits` un-canonicalised, compares with `startswith("/")` and admits every
absolute path — with every authorization criterion green. `evaluate` re-checks
only a missing argument, an argument no predicate ranges over, and an
unrecognised domain type; every other refusal `declare` holds is unrepeated, so
routing through `declare` is the control and not a preference.

**The decode is exact, because `declare` cannot refuse a conjunct it never
received.** `declare` takes already-constructed `Predicate` objects. A decoder
that skipped an unrecognised kind, an unrecognised key or a malformed element
would hand it a strictly *weaker* conjunction, `declare` would accept it because
every surviving predicate is well-formed, and the ceiling would silently widen.
Absent is as dangerous as unrecognised and quieter: `declare` accepts
`Prefix(value="")` and `evaluate` then admits every string, so a `prefix` element
with no payload would become an unconditional admit on an argument that reads as
constrained. Every required key must therefore be present and carried from the
row, and any element, key or kind this module does not recognise — or any
required key the row omits — refuses the whole entry. Nothing is dropped,
narrowed, defaulted or coerced. That is the rule
`ced.adapters.postgres.roles` already states for the role record, "Refuse, never
coerce, and name what failed", applied to elements.

**A ceiling row carrying no predicate encoding installs no entry**, and that is
what makes a call against it deny by lookup miss rather than by anything the
fragment does on its own. An argument with an empty predicate tuple is refused by
`declare`; an entry naming *no* arguments is accepted by `declare` and `evaluate`
returns `Admitted` for a call supplying none. So the empty encoding is handled
here, by installing nothing, and never by handing the fragment an empty entry.

**The public-suffix refusal is beyond every criterion and is ratified.** See
`compile_ceiling` and `spec.md` § Follow-ons for its grounds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final

import ced.domain.containment.ceiling as fragment
from ced.agents.models import RoleCompileError
from ced.domain.containment.ceiling import (
    Admitted,
    CeilingEntry,
    declare,
    evaluate,
)
from ced.domain.containment.errors import (
    CeilingDeclarationRefused,
    ContainmentUndecidable,
    for_the_record,
)
from ced.domain.containment.predicates import (
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
)

__all__ = [
    "ARGUMENT_KEYS",
    "PREDICATE_PAYLOADS",
    "STALE_PUBLIC_SUFFIX_SNAPSHOT",
    "URL_DOMAIN_TYPE",
    "CompiledCeiling",
    "compile_ceiling",
]

#: The snapshot the bundled `publicsuffix2` dataset carries, and the value
#: `PUBLIC_SUFFIX_DATASET_AS_OF` holds while there is no refresh path. Written
#: here rather than imported by name so the comparison below is against a
#: literal this module owns: reading the fragment's value through its module
#: (see `_dataset_is_stale`) is what lets a check move the dataset forward
#: without this module carrying a switch to disable the refusal.
STALE_PUBLIC_SUFFIX_SNAPSHOT: Final[str] = "2019-12-21"

#: The domain type the public-suffix refusal bounds. A `url` argument is the
#: only one whose predicates resolve a host, which is why the refusal is scoped
#: to it and why it does not reach a `host_in_domain` on any other type.
URL_DOMAIN_TYPE: Final[str] = "url"

#: The keys a stored argument object carries, exactly. `domain_type` is the
#: declared type and `predicates` the conjunction over the argument; an object
#: carrying more or fewer is refused rather than read for the two it has.
ARGUMENT_KEYS: Final[frozenset[str]] = frozenset({"domain_type", "predicates"})

#: The key naming which constructor an element encodes.
_KIND_KEY: Final[str] = "kind"


def _a_string(value: object) -> str:
    if not isinstance(value, str):
        raise _BadPayload(f"{for_the_record(type(value).__name__)} is not a string")
    return value


def _a_string_set(value: object) -> frozenset[str]:
    """Decode a JSON array of strings, refusing any other shape.

    A `list` and not any iterable: a stored string is iterable and would decode
    into a set of its characters, which is a silent widening of exactly the kind
    this module refuses everywhere else.
    """
    if not isinstance(value, list):
        raise _BadPayload(f"{for_the_record(type(value).__name__)} is not an array of strings")
    for member in value:
        if not isinstance(member, str):
            raise _BadPayload(
                f"the array carries {for_the_record(type(member).__name__)}, "
                "and every member must be a string"
            )
    return frozenset(value)


def _a_decimal(value: object) -> Decimal:
    """Decode a numeric bound as an exact `Decimal`.

    **A JSON float is refused rather than converted.** `Decimal(0.1)` is not
    one tenth, so a bound written as a float would compare against a value the
    operator did not write — a ceiling whose edge is somewhere other than where
    it reads. An integer is exact, and a string is the exact decimal text.
    """
    if isinstance(value, bool):
        raise _BadPayload("a boolean is not a numeric bound")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            bound = Decimal(value)
        except InvalidOperation as error:
            raise _BadPayload(f"{for_the_record(value)} is not a decimal number") from error
        if not bound.is_finite():
            raise _BadPayload(
                f"{for_the_record(value)} is not finite, so it orders against nothing"
            )
        return bound
    raise _BadPayload(
        f"{for_the_record(type(value).__name__)} is not a numeric bound; write an "
        "integer, or a string carrying the exact decimal text — a float has no "
        "exact decimal value"
    )


def _a_date(value: object) -> date:
    text = _a_string(value)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise _BadPayload(f"{for_the_record(text)} is not an ISO-8601 date") from error


class _BadPayload(Exception):
    """An element's payload does not decode. Internal; never leaves this module."""


#: Every predicate kind this module recognises, with the payload keys each one
#: requires and how each value decodes. **The mapping is the recognised set**:
#: a kind absent from it refuses the entry, so a constructor added to the
#: fragment is unreadable here until somebody adds its row — which is the safe
#: direction, and is why the refusal is keyed on this mapping rather than on a
#: `match` with a fall-through arm.
#:
#: The names are r5 § 4's own spelling of the fragment's constructors.
PREDICATE_PAYLOADS: Final[Mapping[str, tuple[type[Any], Mapping[str, Any]]]] = {
    "prefix": (Prefix, {"value": _a_string}),
    "scheme_in": (SchemeIn, {"schemes": _a_string_set}),
    "host_eq": (HostEq, {"host": _a_string}),
    "host_in_domain": (HostInDomain, {"domain": _a_string}),
    "path_within": (PathWithin, {"prefix": _a_string}),
    "within": (Within, {"root": _a_string}),
    "in_minted_set": (InMintedSet, {"members": _a_string_set}),
    "one_of": (OneOf, {"members": _a_string_set}),
    "number_range": (NumberRange, {"low": _a_decimal, "high": _a_decimal}),
    "date_range": (DateRange, {"low": _a_date, "high": _a_date}),
}


def _refuse(label: str, why: str) -> RoleCompileError:
    """Return the refusal an operator reads, naming what failed.

    `RoleCompileError` and not the fragment's own refusal type, because this is
    a stored record failing to become an agent and `append_role_refusal` maps
    this type to `role.compile.refused`. Letting `CeilingDeclarationRefused` out
    of here would produce a refusal that never becomes an event.
    """
    return RoleCompileError(f"{label}: {why}")


def _decode_predicate(label: str, element: object) -> Predicate:
    """Decode one stored element into a `Predicate`, or refuse the entry.

    Exact on both sides. The element's keys beside `kind` must be **exactly**
    the payload keys its kind requires: an unrecognised key means the row says
    something this module cannot carry, and a missing one means the row says
    less than the constructor needs, which the constructor's own default would
    then silently supply.
    """
    if not isinstance(element, Mapping):
        raise _refuse(
            label,
            f"a predicate element is a {for_the_record(type(element).__name__)}; "
            "every element is an object carrying a kind and that kind's payload",
        )

    if _KIND_KEY not in element:
        raise _refuse(
            label,
            f"a predicate element omits {for_the_record(_KIND_KEY)}; the kinds this "
            f"compiler recognises are {for_the_record(sorted(PREDICATE_PAYLOADS))}",
        )
    kind = element[_KIND_KEY]
    if kind not in PREDICATE_PAYLOADS:
        raise _refuse(
            label,
            f"predicate kind {for_the_record(kind)} is not one this compiler "
            f"recognises; the kinds are {for_the_record(sorted(PREDICATE_PAYLOADS))}. "
            "The whole entry is refused rather than the element dropped, because a "
            "dropped conjunct is a wider ceiling than the row declares",
        )

    constructor, payload_keys = PREDICATE_PAYLOADS[kind]
    supplied = set(element) - {_KIND_KEY}
    required = set(payload_keys)
    if supplied != required:
        faults = []
        if unrecognised := sorted(supplied - required):
            faults.append(f"does not recognise {for_the_record(unrecognised)}")
        if absent := sorted(required - supplied):
            faults.append(
                f"is not carrying {for_the_record(absent)}, and nothing may be "
                "supplied that the row does not"
            )
        raise _refuse(
            label,
            f"predicate kind {for_the_record(kind)} requires exactly "
            f"{for_the_record(sorted(required))} beside its kind, and " + " and ".join(faults),
        )

    decoded: dict[str, Any] = {}
    for key, decode in payload_keys.items():
        try:
            decoded[key] = decode(element[key])
        except _BadPayload as error:
            raise _refuse(
                label,
                f"predicate kind {for_the_record(kind)} carries {for_the_record(key)} "
                f"that does not decode: {error}",
            ) from error
    predicate: Predicate = constructor(**decoded)
    return predicate


def _decode_argument(
    label: str, argument: str, declaration: object
) -> tuple[str, tuple[Predicate, ...]]:
    """Decode one stored argument object into what `declare` takes."""
    if not isinstance(declaration, Mapping):
        raise _refuse(
            label,
            f"argument {for_the_record(argument)} is declared as a "
            f"{for_the_record(type(declaration).__name__)}; an object carrying "
            f"{for_the_record(sorted(ARGUMENT_KEYS))} is required",
        )
    if set(declaration) != ARGUMENT_KEYS:
        raise _refuse(
            label,
            f"argument {for_the_record(argument)} carries "
            f"{for_the_record(sorted(declaration))}; it requires exactly "
            f"{for_the_record(sorted(ARGUMENT_KEYS))}",
        )

    domain_type = declaration["domain_type"]
    if not isinstance(domain_type, str):
        raise _refuse(
            label,
            f"argument {for_the_record(argument)} declares a domain type of type "
            f"{for_the_record(type(domain_type).__name__)}; a string is required",
        )

    elements = declaration["predicates"]
    if not isinstance(elements, list):
        raise _refuse(
            label,
            f"argument {for_the_record(argument)} declares predicates of type "
            f"{for_the_record(type(elements).__name__)}; an array is required",
        )
    return domain_type, tuple(_decode_predicate(label, element) for element in elements)


def _dataset_is_stale() -> bool:
    """Whether the bundled public-suffix dataset is still the stale snapshot.

    Read through the fragment's module at call time rather than bound at import,
    which is what lets a check move the dataset forward in its own process to
    reach the four `declare` refusals that only a `url` argument can trigger.
    **That is not a disable switch**: nothing here takes a parameter, and the
    shipped decision point and predicate carry no flag. It is the same idiom
    `ced.domain.containment.canonicaliser` uses for its rule tuple, and for the
    same reason — the spec's first `Never do` refuses a bypass inside a shipped
    control, so fault evidence is produced by patching in the test process.
    """
    return fragment.PUBLIC_SUFFIX_DATASET_AS_OF == STALE_PUBLIC_SUFFIX_SNAPSHOT


def _check_public_suffix_dataset(label: str, argument: str, domain_type: str) -> None:
    """Refuse a `url` argument while the bundled suffix dataset is stale.

    **Beyond every criterion, and ratified by the owner on 2026-09-23** on the
    containment spec's own precedent for a fail-closed refusal. `publicsuffix2`
    bundles a snapshot published 2019-12-21 and has shipped no release since, so
    every suffix delegated after that date answers "not a public suffix" and is
    authorable against that spec's AC-0215. Integrations are data and registering
    one is an operator insert that opens no pull request, so this compile path is
    the only place enforcement can sit.

    **What it does not do**: it does not refuse a stale-suffix `host_in_domain`
    on a non-`url` argument, because no other domain type resolves a host, and it
    does not make the dataset fresh. Replacing the dataset remains owed —
    `workspace.toml` `[backlog].open` carries it as
    `public-suffix-dataset-has-no-refresh-path`.

    It fires where an operator sees it, at registration, rather than as an
    admitted call in production. Today nothing registers a URL-taking tool, so it
    fires nowhere.
    """
    if domain_type != URL_DOMAIN_TYPE or not _dataset_is_stale():
        return
    raise _refuse(
        label,
        f"argument {for_the_record(argument)} is declared "
        f"{for_the_record(URL_DOMAIN_TYPE)}, and the bundled public-suffix dataset "
        f"is still the snapshot published {STALE_PUBLIC_SUFFIX_SNAPSHOT}. Every "
        "suffix delegated after that date answers 'not a public suffix', so "
        "host_in_domain over one is authorable and silently admits everything "
        "registered under it. Refresh or replace the dataset before registering a "
        "url-taking tool",
    )


@dataclass(frozen=True)
class CompiledCeiling:
    """A `CeilingResolver` over the entries one stored ceiling declared.

    Keyed on tool name, so a call naming a tool with no entry finds nothing and
    the decision point above denies by lookup miss. **That miss is the whole of
    the fail-closed default**: there is no fall-through arm here and none may be
    added.

    `entries_admitting` lets `ContainmentUndecidable` propagate. The decision
    point catches it around the predicate call alone and records a denial, which
    is the receiving half of the fragment's AC-0315 seam; swallowing it here
    would turn an undecided call into a decided one.
    """

    entries: Mapping[str, CeilingEntry]

    def entries_admitting(
        self, tool_name: str, tool_args: dict[str, Any]
    ) -> Sequence[CeilingEntry]:
        """Return the entry admitting this call, empty if none does."""
        entry = self.entries.get(tool_name)
        if entry is None:
            return ()
        decision = evaluate(entry, tool_args)
        return (entry,) if isinstance(decision, Admitted) else ()


def compile_ceiling(label: str, ceiling: Sequence[Mapping[str, Any]]) -> CompiledCeiling:
    """Compile a stored ceiling into the resolver the decision point holds.

    `ceiling` is the decoded `jsonb` array — `agent_role.ceiling` or
    `entitlements.ceiling`, which are the same decidable fragment and are decoded
    by this one function. `label` names the record for the refusal message.

    Raises `RoleCompileError` on anything the fragment cannot carry, which
    `append_role_refusal` maps to `role.compile.refused`. An entry whose
    `predicates` encoding is absent or empty contributes **no** entry, so a call
    to that tool denies by lookup miss.
    """
    entries: dict[str, CeilingEntry] = {}
    for position, binding in enumerate(ceiling):
        where = f"{label} ceiling[{position}]"
        tool_name = binding.get("tool_name")
        if not isinstance(tool_name, str):
            raise _refuse(
                where,
                f"binds a tool name of type {for_the_record(type(tool_name).__name__)}; "
                "a string is required",
            )

        encoding = binding.get("predicates")
        if encoding is None or encoding == [] or encoding == {}:
            # No predicate encoding, so no entry — see this module's docstring.
            # Installing an empty `CeilingEntry` instead would be admitting a
            # no-argument call, which is what `evaluate` does with one.
            continue
        if not isinstance(encoding, Mapping):
            raise _refuse(
                where,
                f"declares predicates of type {for_the_record(type(encoding).__name__)}; "
                "an object mapping each constrained argument to its declaration is "
                "required",
            )

        arguments: dict[str, tuple[str, tuple[Predicate, ...]]] = {}
        for argument, declaration in encoding.items():
            domain_type, predicates = _decode_argument(where, argument, declaration)
            _check_public_suffix_dataset(where, argument, domain_type)
            arguments[argument] = (domain_type, predicates)

        try:
            entry = declare(tool_name, arguments)
        except CeilingDeclarationRefused as error:
            raise _refuse(where, f"is not authorable: {error}") from error
        except ContainmentUndecidable as error:  # pragma: no cover — declare converts these
            raise _refuse(where, f"cannot be decided: {error}") from error

        if tool_name in entries:
            raise _refuse(
                where,
                f"declares predicates for tool {for_the_record(tool_name)}, which an "
                "earlier entry already constrains; two entries for one tool make "
                "which ceiling applies depend on read order",
            )
        entries[tool_name] = entry

    return CompiledCeiling(entries=entries)
