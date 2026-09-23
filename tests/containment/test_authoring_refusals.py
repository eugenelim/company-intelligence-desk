"""The authoring-time refusals: AC-0215, AC-0217, AC-0240 and AC-0316.

All four judge a *declaration* rather than a call, over the same surface, so
they sit together. The reason they are authoring-time at all is in the plan's
design decisions: a call-time refusal makes an undecidable predicate look like
a working one until the wrong argument arrives.
"""

from __future__ import annotations

import encodings.idna
import unicodedata
from datetime import date
from decimal import Decimal

import pytest

from ced.domain.containment.ceiling import (
    PUBLIC_SUFFIX_DATASET_AS_OF,
    Admitted,
    CeilingArgument,
    CeilingEntry,
    Denied,
    declare,
    evaluate,
    is_public_suffix,
)
from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.errors import CeilingDeclarationRefused
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
)

_HTTPS = SchemeIn(frozenset({"https"}))
_SEC = HostInDomain("sec.gov")


def _separator_characters() -> tuple[str, ...]:
    """Return every character the IDNA encoder turns into a label separator.

    **Derived from the encoder, not enumerated.** This defect was found three
    times and each earlier repair closed it by lengthening a hand-kept list,
    which is a snapshot of one codec version rather than the rule. Two
    sources, and both are read from the standard library: the characters the
    codec splits on directly, and the characters its own NFKC pass turns into
    a full stop inside a label.
    """
    direct = {character for character in encodings.idna.dots.pattern if character not in "[]"}
    folded = {
        chr(code) for code in range(0x110000) if unicodedata.normalize("NFKC", chr(code)) == "."
    }
    return tuple(sorted(direct | folded))


SEPARATORS: tuple[str, ...] = _separator_characters()


def test_the_separator_set_was_derived_and_is_not_empty() -> None:
    """Setup check: every parametrisation below rests on this set.

    An empty or ASCII-only result would make each of them pass vacuously,
    which is how a derived list quietly becomes no list at all.
    """
    assert "." in SEPARATORS
    assert [character for character in SEPARATORS if character != "."], (
        "no non-ASCII separator was derived; encodings.idna may have changed shape"
    )


# AC-0215 — a domain argument that is a public suffix.


@pytest.mark.parametrize(
    "suffix",
    ["gov", "com", "co.uk", "GOV", "github.io", *(f"gov{c}" for c in SEPARATORS)],
)
def test_a_public_suffix_domain_argument_is_refused(suffix: str) -> None:
    with pytest.raises(CeilingDeclarationRefused, match="public suffix"):
        declare("fetch", {"url": ("url", (_HTTPS, HostInDomain(suffix)))})


@pytest.mark.parametrize("domain", ["sec.gov", "example.co.uk", "www.sec.gov"])
def test_a_registrable_domain_argument_is_accepted(domain: str) -> None:
    """The refusing half alone is satisfied by refusing every domain."""
    entry = declare("fetch", {"url": ("url", (_HTTPS, HostInDomain(domain)))})
    assert entry.arguments["url"].predicates == (_HTTPS, HostInDomain(domain.lower()))


@pytest.mark.parametrize(
    "domain",
    [
        "",
        ".",
        "sec..gov",
        ".sec.gov",
        *(f"{c}sec.gov" for c in SEPARATORS),
        *(f"sec{c}{c}gov" for c in SEPARATORS),
    ],
)
def test_a_host_argument_with_an_empty_label_is_refused(domain: str) -> None:
    """A name with a hole in it ranges over every host or over none.

    `host_in_domain("")` would pass a public-suffix lookup, satisfy AC-0240's
    host-constraining requirement, and admit every host — a default-allow
    wearing the shape of a constraint.

    Two refusal paths reach the same answer and the test accepts either,
    because which one fires is a property of the spelling rather than of the
    rule. A separator the encoder splits on directly leaves it with an empty
    label to encode, and it refuses the host outright; one the encoder's own
    normalisation produces survives into the output, where the label check
    sees it. What must not happen is a third outcome, and that is what this
    asserts: no spelling of an empty label is authorable.
    """
    with pytest.raises(
        CeilingDeclarationRefused, match="label with nothing in it|not IDNA-encodable"
    ):
        declare("fetch", {"url": ("url", (_HTTPS, HostInDomain(domain)))})


def test_the_root_label_is_normalised_on_both_sides() -> None:
    """`sec.gov.` and `sec.gov` are one name, to the ceiling and to the value.

    A resolver reads the two identically, so a fragment that does not would
    hand an author a second spelling that the public-suffix refusal does not
    cover: `host_in_domain("gov.")` was authorable and admitted
    `https://attacker.gov./`. Two things follow and both are asserted here.
    The normalisation runs on **both sides**, because one that runs on only
    one of them is a differential rather than a canonical form. And it runs
    over every character the encoder reads as a separator, derived from the
    encoder rather than listed here, because each earlier repair that listed
    them left the same bypass reachable through a character the list had not
    reached yet.
    """
    for stop in SEPARATORS:
        entry = declare("fetch", {"url": ("url", (_HTTPS, HostInDomain(f"sec.gov{stop}")))})
        assert entry.arguments["url"].predicates[1] == HostInDomain("sec.gov")

        admitted = evaluate(entry, {"url": f"https://www.sec.gov{stop}/report.pdf"})
        assert isinstance(admitted, Admitted)
        assert str(admitted.canonical["url"]) == "https://www.sec.gov/report.pdf"
        assert isinstance(
            evaluate(entry, {"url": f"https://attacker.gov{stop}/report.pdf"}), Denied
        )


def test_the_suffix_answer_comes_from_the_dataset_not_a_local_list() -> None:
    """Setup check: the bundled dataset is loaded and separates the two cases.

    A hand-kept list is what AC-0215 refuses, so this asserts the dataset
    itself answers. `s3.amazonaws.com` and `github.io` are delegated suffixes
    that no plausible hand-kept list of registry suffixes carries, and they
    are exactly the ones that matter: `host_in_domain("github.io")` admits
    every user's pages site. `sec.gov` is not one and stays authorable.
    """
    assert is_public_suffix("s3.amazonaws.com")
    assert is_public_suffix("github.io")
    assert not is_public_suffix("sec.gov")


# AC-0217 — a prefix predicate on an argument the callee parses.


@pytest.mark.parametrize(
    "domain_type",
    [member for member in DomainType if member is not DomainType.OPAQUE_STRING],
    ids=lambda member: member.value,
)
def test_a_prefix_on_an_interpreted_type_is_refused(domain_type: DomainType) -> None:
    """AC-0217 names `url`, `fs-path` and `content-locator`; the rule is wider.

    The implementation states r5's rule — prefix is expressible only on
    `opaque-string` — so every other member refuses it, and a domain type
    added later inherits the refusal instead of needing this list reworded.
    """
    with pytest.raises(CeilingDeclarationRefused, match="prefix is not expressible"):
        declare("fetch", {"arg": (domain_type.value, (Prefix("https://www.sec.gov"),))})


def test_a_prefix_on_an_opaque_string_is_accepted() -> None:
    """The other direction. Refusing every prefix would satisfy the first half."""
    entry = declare("fetch", {"arg": ("opaque-string", (Prefix("report-"),))})
    assert entry.arguments["arg"].predicates == (Prefix("report-"),)


# AC-0240 — a `url` argument with no host-constraining predicate.


def test_a_url_argument_with_no_host_predicate_is_refused() -> None:
    with pytest.raises(CeilingDeclarationRefused, match="no host-constraining predicate"):
        declare("fetch", {"url": ("url", (_HTTPS, PathWithin("/evidence/")))})


@pytest.mark.parametrize("predicate", [HostInDomain("sec.gov"), HostEq("www.sec.gov")])
def test_a_url_argument_carrying_a_host_predicate_is_accepted(predicate: Predicate) -> None:
    assert declare("fetch", {"url": ("url", (_HTTPS, predicate))}).arguments


def test_the_criterion_does_not_constrain_which_host_the_predicate_admits() -> None:
    """Recorded, not asserted as a good outcome.

    AC-0240 requires a host-constraining predicate to be *present*. It does
    not constrain the host that predicate names, so the link-local
    instance-metadata address is authorable and this test says so out loud.
    The spec's § Follow-ons records both this gap and the address-level one as
    unowned; the egress proxy cannot own the second, because r8 § 4 specifies
    it as a hostname allowlist with no private-range or metadata block.
    """
    assert declare("fetch", {"url": ("url", (_HTTPS, HostEq("169.254.169.254")))}).arguments


# AC-0316 — an argument the entry names and attaches no predicate to.


def test_an_argument_with_no_predicate_is_refused_naming_entry_and_argument() -> None:
    with pytest.raises(CeilingDeclarationRefused) as refusal:
        declare(
            "fetch_filing",
            {"url": ("url", (_HTTPS, _SEC)), "since": ("date", ())},
        )
    message = str(refusal.value)
    assert "fetch_filing" in message, message
    assert "since" in message, message


def test_an_unknown_domain_type_is_refused_at_authoring_time() -> None:
    with pytest.raises(CeilingDeclarationRefused, match="not a declared domain type"):
        declare("fetch", {"query": ("graphql-query", (Prefix("{"),))})


@pytest.mark.parametrize(
    "predicate",
    [
        HostInDomain("a" * 64 + ".gov"),
        HostEq("a" * 64 + ".gov"),
        HostInDomain("\u202e.example"),
        HostEq("\u202e.example"),
        PathWithin("/evidence/%252e%252e/"),
    ],
    ids=lambda predicate: type(predicate).__name__ + repr(predicate)[:24],
)
def test_declare_never_leaks_the_undecidable_signal(predicate: Predicate) -> None:
    """Every refusal the authoring surface produces is an authoring refusal.

    `ContainmentUndecidable` is what the decision point reads as a *denied
    call*. A declaration whose argument has no canonical form must not
    produce it, or an unauthorable role would arrive one spec over looking
    like a call that was refused. The assertion is the property and not the
    exception's parentage, because parentage does not catch a leak: this test
    fails if `ContainmentUndecidable` escapes, since `pytest.raises` does not
    catch it.
    """
    predicates = (
        (_HTTPS, predicate)
        if not isinstance(predicate, PathWithin)
        else (
            _HTTPS,
            _SEC,
            predicate,
        )
    )
    with pytest.raises(CeilingDeclarationRefused, match="no canonical form"):
        declare("fetch", {"url": ("url", predicates)})


def test_a_predicate_outside_its_types_row_is_refused() -> None:
    with pytest.raises(CeilingDeclarationRefused, match="not expressible"):
        declare("fetch", {"url": ("url", (_HTTPS, _SEC, OneOf(frozenset({"a"}))))})


# Beyond AC-0240 and AC-0316, both fail-closed, both recorded in the
# verification ledger as strengthenings the owner has not ratified.


def test_a_url_argument_with_no_scheme_predicate_is_refused() -> None:
    """A host constraint constrains nothing under a scheme that ignores hosts.

    `file://sec.gov/etc/passwd` satisfies `host_eq("sec.gov")` and every
    resolver ignores that authority, so the one predicate AC-0240 forces to
    be present decides nothing about what the callee opens. The scheme
    allowlist is the control the host constraint presupposes, and AC-0240
    closes only the mirror case — a scheme constraint with no host one.
    """
    with pytest.raises(CeilingDeclarationRefused, match="no scheme-constraining predicate"):
        declare("fetch", {"url": ("url", (HostEq("sec.gov"),))})


@pytest.mark.parametrize("scheme", ["file", "gopher", "ftp"])
def test_the_scheme_refusal_is_what_keeps_those_urls_out(scheme: str) -> None:
    """Mutation proof for the test above: the refusal is what stops these.

    Declared through the front door the value is unreachable, so the entry
    is built directly — the same route AC-0317 uses, and for the same
    reason.
    """
    entry = CeilingEntry(
        name="fetch", arguments={"url": CeilingArgument("url", (HostEq("sec.gov"),))}
    )
    decision = evaluate(entry, {"url": f"{scheme}://sec.gov/etc/passwd"})
    assert isinstance(decision, Admitted), (
        "an entry with no scheme predicate admits this, which is why the "
        "authoring surface must refuse the entry"
    )


def test_a_filesystem_root_that_bounds_nothing_is_refused() -> None:
    """The filesystem twin of the public-suffix refusal, on the same grounds.

    `host_in_domain("gov")` is refused for admitting everything below a root
    that bounds nothing; `within("/")` is the same shape and was authorable,
    admitting `/etc/passwd` with AC-0316 satisfied because a predicate *was*
    attached.
    """
    with pytest.raises(CeilingDeclarationRefused, match="bounds nothing"):
        declare("fetch", {"path": ("fs-path", (Within("/"),))})

    assert declare("fetch", {"path": ("fs-path", (Within("/evidence"),))}).arguments


def test_the_suffix_dataset_records_the_day_it_was_published() -> None:
    """The dependency's limit, stated where a reader meets the answer.

    `publicsuffix2` has shipped no release since its bundled snapshot, so a
    suffix delegated after that date answers `False` and is authorable —
    `pages.dev` and `vercel.app` among them. An earlier comment justified
    the dependency on the grounds that a bundled dataset goes stale "at a
    version bump a reviewer can see"; no bump exists, so this constant and
    the ledger are what make the staleness visible instead.
    """
    assert PUBLIC_SUFFIX_DATASET_AS_OF == "2019-12-21"
    assert not is_public_suffix("pages.dev"), (
        "the snapshot now carries a suffix it did not; update the recorded "
        "as-of date and the ledger entry that reasons from it"
    )


@pytest.mark.parametrize("root", ["", "relative/dir", "evidence", "./evidence"])
def test_a_relative_filesystem_root_is_refused(root: str) -> None:
    """A root that is not absolute resolves against the worker's directory.

    The declaration's text then does not say what it admits, and two workers
    started in different directories enforce different ceilings from the
    same role record. Same grounds as the `within(/)` refusal, and beyond
    any criterion in the same way.
    """
    with pytest.raises(CeilingDeclarationRefused, match="no absolute root"):
        declare("fetch", {"path": ("fs-path", (Within(root),))})


#: r5 § 4's per-type expressibility table, restated as the suite's
#: expectation. Restated and not read from the implementation on purpose:
#: `EXPRESSIBLE_PREDICATES` is the thing under test, so a check that read it
#: would agree with whatever it said. Widening any single row is what this
#: catches — the union of the rows is not enough, because a constructor added
#: to one row usually appears in another already.
_EXPECTED_ROWS: dict[str, set[type]] = {
    "opaque-string": {Prefix, OneOf},
    "url": {SchemeIn, HostEq, HostInDomain, PathWithin},
    "fs-path": {Within},
    "content-locator": {InMintedSet},
    "enum": {OneOf},
    "number": {NumberRange},
    "date": {DateRange},
}


def test_each_domain_type_admits_exactly_the_predicates_r5_gives_it() -> None:
    """Per row, not per union.

    The union check this replaces could not see a row being widened, and the
    widening that bites is `one_of` on `content-locator`: r5 makes that type
    "membership in the runtime-minted set for this step", so a ceiling
    bounded by a set its author typed instead is the whole content of that
    row, gone, with every criterion green.
    """
    actual = {
        domain_type.value: set(row) for domain_type, row in EXPRESSIBLE_PREDICATES.items()
    }
    assert actual == _EXPECTED_ROWS


@pytest.mark.parametrize(
    ("domain_type", "predicate"),
    [
        ("content-locator", OneOf(frozenset({"ref:author-chose-this"}))),
        ("content-locator", Prefix("ref:")),
        ("enum", Prefix("a")),
        ("enum", InMintedSet(frozenset({"a"}))),
        ("url", Within("/evidence")),
        ("url", OneOf(frozenset({"https://sec.gov/"}))),
        ("fs-path", PathWithin("/evidence/")),
        ("fs-path", OneOf(frozenset({"/evidence/x"}))),
        ("number", DateRange(date(2024, 1, 1), date(2024, 12, 31))),
        ("date", NumberRange(Decimal(0), Decimal(1))),
        ("opaque-string", InMintedSet(frozenset({"a"}))),
        ("date", OneOf(frozenset({"a"}))),
    ],
    ids=lambda value: value if isinstance(value, str) else type(value).__name__,
)
def test_a_predicate_outside_its_row_is_refused(domain_type: str, predicate: Predicate) -> None:
    """One negative per row, so no single row can be widened unnoticed."""
    with pytest.raises(CeilingDeclarationRefused):
        declare("fetch", {"a": (domain_type, (predicate,))})
