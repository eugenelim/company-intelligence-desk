"""The authoring-time refusals: AC-0215, AC-0217, AC-0240 and AC-0316.

All four judge a *declaration* rather than a call, over the same surface, so
they sit together. The reason they are authoring-time at all is in the plan's
design decisions: a call-time refusal makes an undecidable predicate look like
a working one until the wrong argument arrives.
"""

from __future__ import annotations

import pytest

from ced.domain.containment.ceiling import Admitted, Denied, declare, evaluate, is_public_suffix
from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.errors import CeilingDeclarationRefused
from ced.domain.containment.predicates import (
    HostEq,
    HostInDomain,
    OneOf,
    PathWithin,
    Predicate,
    Prefix,
    SchemeIn,
)

_HTTPS = SchemeIn(frozenset({"https"}))
_SEC = HostInDomain("sec.gov")


# AC-0215 — a domain argument that is a public suffix.


@pytest.mark.parametrize(
    "suffix",
    ["gov", "com", "co.uk", "GOV", "github.io", "gov.", "GOV.", "s3.amazonaws.com."],
)
def test_a_public_suffix_domain_argument_is_refused(suffix: str) -> None:
    with pytest.raises(CeilingDeclarationRefused, match="public suffix"):
        declare("fetch", {"url": ("url", (_HTTPS, HostInDomain(suffix)))})


@pytest.mark.parametrize("domain", ["sec.gov", "example.co.uk", "www.sec.gov"])
def test_a_registrable_domain_argument_is_accepted(domain: str) -> None:
    """The refusing half alone is satisfied by refusing every domain."""
    entry = declare("fetch", {"url": ("url", (_HTTPS, HostInDomain(domain)))})
    assert entry.arguments["url"].predicates == (_HTTPS, HostInDomain(domain.lower()))


@pytest.mark.parametrize("domain", ["", ".", "sec..gov", ".sec.gov"])
def test_a_host_argument_with_an_empty_label_is_refused(domain: str) -> None:
    """A name with a hole in it ranges over every host or over none.

    `host_in_domain("")` would pass a public-suffix lookup, satisfy AC-0240's
    host-constraining requirement, and admit every host — a default-allow
    wearing the shape of a constraint.
    """
    with pytest.raises(CeilingDeclarationRefused, match="label with nothing in it"):
        declare("fetch", {"url": ("url", (_HTTPS, HostInDomain(domain)))})


def test_the_root_label_is_normalised_on_both_sides() -> None:
    """`sec.gov.` and `sec.gov` are one name, to the ceiling and to the value.

    A resolver reads the two identically, so a fragment that does not would
    hand an author a second spelling that the public-suffix refusal does not
    cover: `host_in_domain("gov.")` was authorable and admitted
    `https://attacker.gov./`. The normalisation has to run on both sides —
    one that runs on only one of them is a differential, not a canonical
    form.
    """
    entry = declare("fetch", {"url": ("url", (_HTTPS, HostInDomain("sec.gov.")))})
    assert entry.arguments["url"].predicates[1] == HostInDomain("sec.gov")

    admitted = evaluate(entry, {"url": "https://www.sec.gov./report.pdf"})
    assert isinstance(admitted, Admitted)
    assert str(admitted.canonical["url"]) == "https://www.sec.gov/report.pdf"

    assert isinstance(evaluate(entry, {"url": "https://attacker.gov./report.pdf"}), Denied)


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


@pytest.mark.parametrize("predicate", [_SEC, HostInDomain("sec.gov")])
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
