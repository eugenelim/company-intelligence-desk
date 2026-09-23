"""Nothing but this package's own two types leaves the fragment.

AC-0315 fixes the answer on an input the fragment cannot decide as a raise,
and the verification ledger fixes *which* raise, so that the decision point's
denial handler can be narrow by type and still let a programming error
through. That contract is only worth what the fragment's failure vocabulary
is: a builtin escaping `evaluate` turns an attacker-chosen tool argument into
an uncaught error in the worker step rather than a logged denial, and a
handler catching `ContainmentUndecidable` cannot see it coming.

A tool-call argument is model-chosen and therefore shaped by whatever the
documents under analysis contain, so every one of these is reachable from
untrusted input rather than only from a caller's mistake.

The first test names the shapes found; the property test is what holds the
claim against a shape nobody has thought of yet.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from urllib.parse import urlsplit

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ced.domain.containment.ceiling import (
    Admitted,
    CeilingArgument,
    CeilingEntry,
    Denied,
    declare,
    evaluate,
)
from ced.domain.containment.errors import CeilingDeclarationRefused, ContainmentUndecidable
from ced.domain.containment.predicates import (
    DateRange,
    HostInDomain,
    InMintedSet,
    NumberRange,
    OneOf,
    Predicate,
    SchemeIn,
    Within,
)

_URL = CeilingArgument("url", (SchemeIn(frozenset({"https"})), HostInDomain("sec.gov")))
_FS = CeilingArgument("fs-path", (Within("/srv"),))
_NUMBER = CeilingArgument("number", (NumberRange(Decimal(0), Decimal(9)),))
_DATE = CeilingArgument("date", (DateRange(date(2024, 1, 1), date(2024, 12, 31)),))

#: Values whose canonicalisation or whose comparison is itself ill-defined,
#: and which each used to leave `evaluate` as a builtin: `ValueError` out of
#: `realpath`, `decimal.InvalidOperation` out of an ordering against NaN, and
#: `TypeError` from comparing a `date` with a `datetime`, which passes an
#: `isinstance` test because `datetime` subclasses `date`.
_ILL_DEFINED: tuple[tuple[str, CeilingArgument, object], ...] = (
    ("a path with a NUL in it", _FS, "/srv/a\x00/../../etc/passwd"),
    ("a path that is not a string", _FS, 17),
    ("a number that is NaN", _NUMBER, Decimal("NaN")),
    ("a number that is infinite", _NUMBER, Decimal("Infinity")),
    ("a date that is a datetime", _DATE, datetime(2024, 6, 1, 12, 0)),
    ("a url that is not a string", _URL, 17),
    ("a url with no scheme", _URL, "www.sec.gov/evidence"),
)


@pytest.mark.parametrize(
    ("label", "constraint", "value"), _ILL_DEFINED, ids=[case[0] for case in _ILL_DEFINED]
)
def test_an_ill_defined_value_is_undecidable_and_not_a_crash(
    label: str, constraint: CeilingArgument, value: object
) -> None:
    entry = CeilingEntry(name="t", arguments={"a": constraint})
    with pytest.raises(ContainmentUndecidable):
        evaluate(entry, {"a": value})


def test_declare_refuses_a_root_the_filesystem_cannot_resolve() -> None:
    """The authoring surface has the same closed vocabulary, for the same value."""
    with pytest.raises(CeilingDeclarationRefused):
        declare("t", {"p": ("fs-path", (Within("/srv\x00"),))})


#: The alphabet a URL's structure is built from. Unstructured text never
#: reaches `urlsplit`'s raising branches — an unclosed IPv6 literal and an
#: authority carrying a character NFKC turns into a delimiter both need URL
#: shape — so a strategy that does not build one attests to a surface it
#: never enters.
_AUTHORITY_ALPHABET: Final[str] = (
    "abz.:[]@%-_0189\u2100\uff05\uff10\uff0e\u3002\u2024\u202e\x00\t"
)
_PATH_ALPHABET: Final[str] = "abz/.%25eEfF\\-_\u2024\x00\t"

_urls = st.builds(
    lambda scheme, authority, path: f"{scheme}://{authority}{path}",
    st.sampled_from(("https", "http", "file", "ftp", "")),
    st.text(alphabet=_AUTHORITY_ALPHABET, max_size=24),
    st.text(alphabet=_PATH_ALPHABET, max_size=24).map(lambda p: f"/{p}"),
)

_fs_paths = st.text(alphabet="abz/.\\%-_\x00\t\u2024", max_size=32).map(lambda p: f"/{p}")


def test_the_url_strategy_reaches_the_parse_it_claims_to_cover() -> None:
    """Setup check: the strategy must actually reach `urlsplit`'s refusals.

    An earlier version of the property below generated unstructured text,
    which never produces an unclosed IPv6 literal or an authority NFKC turns
    into a delimiter — so it held a claim about a branch it did not enter.
    These are the witnesses, run through the parse directly. The third is a
    superscript two as a port: `str.isdigit` is true of it and `int()` is
    not, which is how a guard written on `isdigit` crashed instead of
    refusing.
    """
    for value in ("http://[::1", "https://sec.gov\u2100/"):
        with pytest.raises(ValueError):
            urlsplit(value)
    for value in ("http://[::1", "https://sec.gov\u2100/", "https://h.example:\xb2/a"):
        entry = CeilingEntry(name="t", arguments={"u": _URL})
        with pytest.raises(ContainmentUndecidable):
            evaluate(entry, {"u": value})


@settings(max_examples=500, deadline=None)
@given(_urls, _fs_paths)
def test_no_generated_value_leaves_evaluation_as_anything_else(url: str, path: str) -> None:
    """The claim the named cases cannot make: it holds for a shape nobody listed.

    Generated in the shapes a model-chosen argument actually arrives in. The
    assertion is not about the answer — a denial and a raise are both correct
    — but about the vocabulary: three outcomes and no fourth.
    """
    entry = CeilingEntry(name="t", arguments={"u": _URL, "p": _FS})
    try:
        decision = evaluate(entry, {"u": url, "p": path})
    except ContainmentUndecidable:
        return
    assert isinstance(decision, Admitted | Denied)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=48))
def test_no_unstructured_string_leaves_evaluation_as_anything_else(value: str) -> None:
    """The same claim over text with no URL shape at all."""
    entry = CeilingEntry(name="t", arguments={"u": _URL, "p": _FS})
    for argument in ("u", "p"):
        other = "u" if argument == "p" else "p"
        call = {argument: value, other: "https://www.sec.gov/x" if other == "u" else "/srv/x"}
        try:
            decision = evaluate(entry, call)
        except ContainmentUndecidable:
            continue
        assert isinstance(decision, Admitted | Denied)


def test_a_denial_reason_is_bounded_and_does_not_enumerate_a_set() -> None:
    """A denial is what the consumer writes as `policy.decision`.

    An unbounded reason lets one refused call write an event row as large as
    the caller cares to make it, at no cost to the caller, and a set-valued
    predicate would write every minted reference for the step into the log.
    Both halves are bounded, and the reason still says which value was
    refused and what it failed.
    """
    entry = CeilingEntry(name="t", arguments={"u": _URL})
    reason = evaluate(entry, {"u": "https://attacker.example/" + "a" * 5000}).reason
    assert len(reason) < 400, reason
    assert "5025 characters" in reason
    assert "attacker.example" in reason

    minted = CeilingEntry(
        name="t",
        arguments={
            "r": CeilingArgument(
                "content-locator", (InMintedSet(frozenset(f"ref:{n}" for n in range(50))),)
            )
        },
    )
    minted_reason = evaluate(minted, {"r": "ref:not-minted"}).reason
    assert "50 minted reference(s)" in minted_reason
    assert "ref:7" not in minted_reason


@pytest.mark.parametrize(
    ("domain_type", "predicate", "value", "expected", "member"),
    [
        (
            "enum",
            OneOf(frozenset(f"label-{n}" for n in range(5000))),
            "not-a-member",
            "5000 member(s)",
            "label-4321",
        ),
        (
            "opaque-string",
            OneOf(frozenset(f"label-{n}" for n in range(5000))),
            "not-a-member",
            "5000 member(s)",
            "label-4321",
        ),
        (
            "url",
            SchemeIn(frozenset(f"scheme{n}" for n in range(500))),
            "https://sec.gov/x",
            "500 scheme(s)",
            "scheme499",
        ),
    ],
)
def test_every_set_valued_predicate_is_summarised_in_a_denial(
    domain_type: str, predicate: Predicate, value: str, expected: str, member: str
) -> None:
    """The bound on the predicate half holds for every constructor that has one.

    Only `in_minted_set` was driven before, and the other arms could each
    fall through to the `repr` fallback with the suite green — after which a
    denial against a 5,000-member `one_of` writes all 5,000 members into the
    `policy.decision` it becomes. `one_of` is expressible on two domain
    types, so both are driven.
    """
    arguments: dict[str, CeilingArgument] = {"a": CeilingArgument(domain_type, (predicate,))}
    if domain_type == "url":
        arguments["a"] = CeilingArgument("url", (predicate, HostInDomain("example.com")))
    reason = evaluate(CeilingEntry(name="t", arguments=arguments), {"a": value}).reason
    assert len(reason) <= _MESSAGE_CEILING, reason[:200]
    assert member not in reason
    assert expected in reason


@pytest.mark.parametrize("port", ["\xb2", "\xb3", "\xb9", "\u1369", "\u0664\u0664\u0663"])
def test_a_digit_like_port_is_refused_rather_than_read(port: str) -> None:
    """A port is ASCII digits, and `str.isdigit` is not that test.

    Two failures came out of one predicate. `str.isdigit` is true of 128
    characters `int()` refuses, so the guard crashed instead of refusing —
    a builtin out of `evaluate` for a value a model can choose. And it is
    true of the Arabic-Indic digits, which `int()` accepts, so
    `https://h.example:\u0664\u0664\u0663/a` was admitted and rewritten
    into `https://h.example/a`: an authority RFC 3986 does not admit,
    normalised into one that looks valid.
    """
    entry = CeilingEntry(name="t", arguments={"u": _URL})
    with pytest.raises(ContainmentUndecidable, match="is not a port"):
        evaluate(entry, {"u": f"https://sec.gov:{port}/x"})


#: Every message this fragment produces is recorded by the consumer — a
#: `Denied` reason as the `policy.decision`, and a `ContainmentUndecidable`
#: as the denial AC-0315 makes it. So the bound has to hold on all of them,
#: not on the one path it was first installed for.
_MESSAGE_CEILING: Final[int] = 800

#: A model-chosen fragment long enough that an unbounded path shows up as a
#: length rather than as a judgment call.
_OVERSIZE: Final[str] = "A" * 20000


def _texts_from_every_path(oversize: str) -> dict[str, str]:
    """Return one message per path that can carry a model-chosen fragment."""
    url = CeilingArgument("url", (SchemeIn(frozenset({"https"})), HostInDomain("sec.gov")))
    fs = CeilingArgument("fs-path", (Within("/srv"),))
    entry = CeilingEntry(name="t", arguments={"u": url})
    texts: dict[str, str] = {}

    texts["unknown argument name"] = str(
        evaluate(entry, {"u": "https://www.sec.gov/x", oversize: "y"}).reason
    )
    texts["denied value"] = str(
        evaluate(entry, {"u": f"https://attacker.example/{oversize}"}).reason
    )
    texts["missing arguments"] = str(
        evaluate(CeilingEntry(name="t", arguments={oversize: url}), {}).reason
    )

    for label, call_entry, value in (
        ("control character", entry, f"https://a.example/\t{oversize}"),
        ("unparseable url", entry, f"http://[::1{oversize}"),
        ("no scheme", entry, oversize),
        ("bad port", entry, f"https://sec.gov:\xb2{oversize}/x"),
        ("nul in path", CeilingEntry(name="t", arguments={"p": fs}), f"/srv/\x00{oversize}"),
    ):
        argument = next(iter(call_entry.arguments))
        try:
            evaluate(call_entry, {argument: value})
        except ContainmentUndecidable as refusal:
            texts[label] = str(refusal)

    try:
        declare("t", {"p": ("fs-path", (Within(oversize),))})
    except CeilingDeclarationRefused as refusal:
        texts["declare relative root"] = str(refusal)
    try:
        declare("t", {"u": ("url", (SchemeIn(frozenset({"https"})), HostInDomain(oversize)))})
    except CeilingDeclarationRefused as refusal:
        texts["declare bad domain"] = str(refusal)

    return texts


def test_the_message_paths_this_bound_covers_were_all_reached() -> None:
    """Setup check: a bound asserted over paths nothing entered is no bound."""
    texts = _texts_from_every_path(_OVERSIZE)
    assert len(texts) == 10, sorted(texts)


@pytest.mark.parametrize("path", sorted(_texts_from_every_path(_OVERSIZE)))
def test_every_message_a_consumer_records_is_bounded(path: str) -> None:
    """The bound belongs on every text this fragment hands a consumer.

    A `Denied` reason becomes a `policy.decision` and AC-0315 makes a
    `ContainmentUndecidable` the signal the decision point records as a
    denial, so both land in the event log. Bounding one path and leaving its
    siblings open is a control that looks installed and is not: before this,
    an argument *name* — model-chosen exactly as a value is — went into a
    reason whole, and an undecidable message carried the value whole.
    """
    text = _texts_from_every_path(_OVERSIZE)[path]
    assert len(text) <= _MESSAGE_CEILING, f"{path}: {len(text)} characters"
    assert _OVERSIZE not in text
    assert re.search(r"\(\d{4,} characters\)", text), (
        f"{path} cut the value without saying how much there was: {text}"
    )
