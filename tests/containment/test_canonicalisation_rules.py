"""AC-0216 — every canonicalisation rule carries weight, proved by removing it.

A rule nobody's case exercises is indistinguishable from an absent one, so
each rule in `URL_RULES` and `FS_PATH_RULES` has an input the fragment refuses
and that is admitted once that rule is gone. **Both halves matter.** A
mutation that reds every case shows the rule set is entangled, not that one
rule is load-bearing, so the independence direction is asserted too.

The mutations patch the module-level rule tuples in the test process. The
canonicaliser ships no disable switch — the spec's first `Never do` refuses
one inside a shipped security control — which is why they live here.

**Two of r5's clauses have no such input, and the reason is a property of
the clauses rather than of this suite.** Case-folding a host and dropping a
default port both *normalise*: each admits strictly more, and no predicate in
r5's `url` row ranges over a port at all, so removing either can only shrink
what the fragment admits. For those two the suite proves the direction that is
true — the rule does its job, and its removal admits nothing new — and says
so rather than substituting a miswrite for the removal AC-0216 asks for. The
spec's verification ledger records what that leaves open against the
criterion.

**AC-0216 cannot see a transposition**, because it removes rules and never
reorders them. The last test is the separate pinned case for the one ordering
the design rests on, and the spec's `Never do` states the same rule in prose.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from ced.domain.containment.canonicaliser import (
    FS_PATH_RULES,
    URL_RULES,
    CanonicalUrl,
    canonicalise,
    rule_names,
)
from ced.domain.containment.ceiling import Admitted, CeilingEntry, declare, evaluate
from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.errors import ContainmentUndecidable
from ced.domain.containment.predicates import (
    EXPRESSIBLE_PREDICATES,
    HostEq,
    HostInDomain,
    PathWithin,
    Predicate,
    SchemeIn,
    Within,
    admits,
)
from tests.containment.fixture import (
    canonicaliser_clauses,
    decode_and_dot_segments_transposed,
    rule_disabled,
    sec_ceiling,
    url_call,
)

#: The inputs per load-bearing URL rule: each refused as things stand, each
#: admitted once that rule is gone. A rule may have more than one, because a
#: guard with several branches needs a case per branch — a branch nobody's
#: case drives can be deleted with the suite green, which is the criterion's
#: own objection one level down.
_URL_CASES: Mapping[str, tuple[str, ...]] = {
    # A tab `urlsplit` strips and a stricter client does not, plus both
    # edges of the set the guard is defined by: the space below C0's top and
    # DEL above it. Without an edge case the range can be narrowed silently,
    # after which the character reaches the adapter inside the canonical path.
    "refuse-control-characters": (
        "https://www.sec.gov/evidence/\tx",
        "https://www.sec.gov/evidence/a b",
        "https://www.sec.gov/evidence/a\x7fb",
    ),
    # Two `@` in the authority: parsers disagree about which side is the host.
    "refuse-second-userinfo": ("https://a@attacker.example@www.sec.gov/evidence/x",),
    # A doubled separator, which survives as an empty label once the root
    # label is dropped.
    "refuse-empty-label": ("https://www.sec.gov../evidence/x",),
    # Three branches of the port check: text that is not digits at all,
    # digits above the range a port can hold, and zero, which is below it.
    "refuse-invalid-port": (
        "https://www.sec.gov:443.attacker.example/evidence/x",
        "https://www.sec.gov:70000/evidence/x",
        "https://www.sec.gov:0/evidence/x",
    ),
    # A right-to-left override IDNA prohibits, sitting inside a host that ends
    # in `.sec.gov` as plain text.
    "idna-normalise-host": ("https://www\u202e.sec.gov/evidence/x",),
    # Double-encoded, so one decoding round leaves an encoded separator behind
    # and dot-segment removal never sees a traversal at all. One per
    # alternative of the residual pattern: an encoded dot, an encoded slash,
    # an encoded backslash, and an encoded percent sign.
    "percent-decode-then-refuse-residual": (
        "https://www.sec.gov/evidence/%252e%252e/etc/passwd",
        "https://www.sec.gov/evidence/%252f..%252f..%252fetc/passwd",
        "https://www.sec.gov/evidence/%255c..%255cetc/passwd",
        "https://www.sec.gov/evidence/%2525/etc/passwd",
        # Percent-encoding is case-insensitive by RFC 3986, so each member
        # of the pattern's character classes needs a witness and not each
        # alternative: with only the lowercase spellings driven, narrowing
        # `[eEfF]` to `[ef]` leaves every gate green and `%252E%252E` walks
        # out of the path root.
        "https://www.sec.gov/evidence/%252E%252E/etc/passwd",
        "https://www.sec.gov/evidence/%252F..%252F..%252Fetc/passwd",
        "https://www.sec.gov/evidence/%255C..%255Cetc/passwd",
    ),
    # A literal traversal, which needs no decoding to escape the path root.
    "remove-dot-segments": ("https://www.sec.gov/evidence/../etc/passwd",),
}

#: The rules whose omission cannot admit anything, with the reason. These get
#: a normalisation check and a fail-closed check instead of a mutation case.
_FAIL_CLOSED_RULES: Mapping[str, str] = {
    "lowercase-host-not-path": (
        "a folded host matches strictly more ceilings and the rule never touches "
        "the path, so removing it can only shrink what is admitted"
    ),
    "drop-default-ports": (
        "no predicate in r5's `url` row ranges over a port, so port normalisation "
        "changes the value handed on and never changes a decision"
    ),
}

#: The universe the two fail-closed rules are judged over. Every member is a
#: value at least one of them acts on — hosts differing in case, a punycode
#: host, and authorities carrying a default port, a non-default port and
#: none — and the set spans both sides of the ceiling, so a rule that started
#: admitting something would have somewhere to show it.
_FAIL_CLOSED_UNIVERSE: tuple[str, ...] = (
    "https://www.sec.gov/evidence/report.pdf",
    "https://WWW.SEC.GOV/evidence/report.pdf",
    "https://Www.Sec.Gov/EVIDENCE/report.pdf",
    "https://www.sec.gov:443/evidence/report.pdf",
    "https://WWW.SEC.GOV:443/evidence/report.pdf",
    "https://www.sec.gov:8443/evidence/report.pdf",
    "https://www.sec.gov:80/evidence/report.pdf",
    "https://WWW.SEC.GOV.ATTACKER.EXAMPLE/evidence/report.pdf",
    "https://attacker.example:443/evidence/report.pdf",
    "https://xn--sec-vma.gov/evidence/report.pdf",
    "https://XN--SEC-VMA.GOV:443/evidence/report.pdf",
    "https://www.sec.gov:443/other/report.pdf",
)

#: The input that pins the order of the two rules AC-0216 cannot reorder.
#: Singly encoded: correct order decodes it into a traversal and removes it;
#: the transposed order removes nothing and then decodes into one.
_TRANSPOSITION_CASE = "https://www.sec.gov/evidence/%2e%2e/%2e%2e/etc/passwd"

#: The paragraph every rule implements a clause of, as r5 states it. Pinned so
#: that a rule added upstream reds here — AC-0216's amendment trigger.
_CANONICALISER_CLAUSES = (
    "What the canonicalizer must do, because each omission is a known bypass: "
    "IDNA-normalize the host to punycode, lowercase the host and not the path, "
    "percent-decode before dot-segment removal and refuse a value that still "
    "contains an encoded separator afterwards, drop default ports, and reject an "
    "ambiguous parse rather than guessing. For `fs-path`, normalization resolves "
    "symlinks, because a name-only normalization admits a link pointing outside "
    "the root."
)


def _symlink_case(workspace: Path) -> tuple[CeilingEntry, dict[str, object]]:
    """Build a root holding a symlink that leaves it, and a value through it.

    The paths are resolved first: a root the declaration canonicalises and a
    value the test builds from an unresolved temporary directory would differ
    for a reason that has nothing to do with the rule under test.
    """
    base = workspace.resolve()
    root = base / "evidence"
    outside = base / "outside"
    root.mkdir(parents=True)
    outside.mkdir(parents=True)
    (outside / "secret").write_text("not evidence", encoding="utf-8")
    (root / "link").symlink_to(outside, target_is_directory=True)
    entry = declare("fetch_filing", {"path": ("fs-path", (Within(str(root)),))})
    return entry, {"path": str(root / "link" / "secret")}


def _cases(rule: str, workspace: Path) -> tuple[tuple[CeilingEntry, dict[str, object]], ...]:
    """Return every (entry, call) pair that stands for `rule`."""
    if rule == "resolve-symlinks":
        return (_symlink_case(workspace),)
    return tuple((sec_ceiling(), url_call(value)) for value in _URL_CASES[rule])


def _case(rule: str, workspace: Path) -> tuple[CeilingEntry, dict[str, object]]:
    """Return one representative pair for `rule`."""
    return _cases(rule, workspace)[0]


def _refuses(entry: CeilingEntry, call: Mapping[str, object]) -> bool:
    """Return whether the fragment declines the call, by denial or by raise.

    Both are refusals. Which one a case gets is a property of the input, not
    of the rule being load-bearing, so AC-0216 reads them the same way.
    """
    try:
        return not isinstance(evaluate(entry, call), Admitted)
    except ContainmentUndecidable:
        return True


def test_every_rule_is_accounted_for() -> None:
    """Setup check: a rule added to the canonicaliser reds here until it is placed.

    Exactly one of three groups: a mutation case, the symlink case, or the
    fail-closed group with its stated reason. A rule in none of them would
    otherwise sit in the canonicaliser with no evidence at all, which is the
    state AC-0216 exists to prevent.
    """
    placed = set(_URL_CASES) | {"resolve-symlinks"} | set(_FAIL_CLOSED_RULES)
    assert set(rule_names()) == placed, (
        f"unaccounted rules: {sorted(set(rule_names()) - placed)}; "
        f"accounted rules that no longer exist: {sorted(placed - set(rule_names()))}"
    )


def test_the_clause_paragraph_upstream_is_unchanged() -> None:
    """AC-0216's amendment trigger: a rule added to r5's list reds here."""
    assert canonicaliser_clauses() == _CANONICALISER_CLAUSES


def test_every_rule_names_a_clause_of_that_paragraph() -> None:
    """The rule set is r5's list, not a list of its own."""
    for rule in (*URL_RULES, *FS_PATH_RULES):
        assert rule.clause in _CANONICALISER_CLAUSES, (
            f"rule {rule.name!r} claims a clause r5's paragraph does not state"
        )


def _mutated_rules() -> tuple[str, ...]:
    """Return the rules a removal case exists for."""
    return (*_URL_CASES, "resolve-symlinks")


@pytest.mark.parametrize("rule", _mutated_rules())
def test_the_rule_is_load_bearing(rule: str, tmp_path: Path) -> None:
    for entry, call in _cases(rule, tmp_path / rule):
        assert _refuses(entry, call), f"{call} is not refused even with {rule!r} in place"
        with rule_disabled(rule):
            assert not _refuses(entry, call), (
                f"{call} is still refused without {rule!r}, so the case does not "
                "show that rule carries the weight"
            )


@pytest.mark.parametrize("disabled", rule_names())
def test_disabling_one_rule_leaves_every_other_case_refused(
    disabled: str, tmp_path: Path
) -> None:
    """The entanglement half. A mutation that reds everything proves nothing.

    Every rule is removed in turn, the fail-closed two included, because a
    rule with no case of its own can still break somebody else's.
    """
    for other in _mutated_rules():
        if other == disabled:
            continue
        for entry, call in _cases(other, tmp_path / f"{disabled}-{other}"):
            with rule_disabled(disabled):
                assert _refuses(entry, call), (
                    f"removing {disabled!r} also admitted {other!r}'s case, so the "
                    "two rules are entangled and neither mutation isolates a rule"
                )


def test_percent_decoding_runs_before_dot_segment_removal() -> None:
    """The pinned transposition case. AC-0216 cannot reach this one.

    Every rule is still present here; only the order of two of them changes.
    With decoding first the encoded traversal becomes a real one and is
    removed; with removal first there is nothing to remove, and the decode
    that follows produces the traversal after the last check has run.
    """
    entry = sec_ceiling()
    assert _refuses(entry, url_call(_TRANSPOSITION_CASE))
    with decode_and_dot_segments_transposed():
        assert not _refuses(entry, url_call(_TRANSPOSITION_CASE)), (
            "the transposed order still refuses the encoded traversal, so this "
            "case is not pinning the order it claims to"
        )


@pytest.mark.parametrize("rule", sorted(_FAIL_CLOSED_RULES))
def test_a_fail_closed_rule_acts_on_the_universe_it_is_judged_over(rule: str) -> None:
    """Setup check: the fail-closed proof below is judged over live values.

    A universe the rule never touches would make that proof pass against any
    implementation, which is the vacuity a substitute for a missing mutation
    case most easily falls into. So this asserts the rule changes the
    canonical form of several members before the next test reads anything
    into their decisions.
    """
    changed = [
        value
        for value in _FAIL_CLOSED_UNIVERSE
        if _canonical_form(value, without=None) != _canonical_form(value, without=rule)
    ]
    assert len(changed) >= 2, (
        f"{rule!r} changes the canonical form of {len(changed)} of "
        f"{len(_FAIL_CLOSED_UNIVERSE)} universe members, so the fail-closed "
        "proof over that universe would hold whatever the rule did"
    )


@pytest.mark.parametrize("rule", sorted(_FAIL_CLOSED_RULES))
def test_a_fail_closed_rule_admits_nothing_when_it_is_removed(
    rule: str, tmp_path: Path
) -> None:
    """The direction that is true for the two normalising clauses.

    AC-0216 asks for an input the removal admits. For these two there is
    none, and this is the assertion that says so rather than leaving the
    claim in prose. It runs over a universe built for these rules — hosts
    that differ in case, punycode, and authorities carrying a default and a
    non-default port — plus every other rule's case, and asserts that nothing
    the full pipeline refuses becomes admitted.
    """
    for value in _FAIL_CLOSED_UNIVERSE:
        call = url_call(value)
        refused_with = _refuses(sec_ceiling(), call)
        with rule_disabled(rule):
            refused_without = _refuses(sec_ceiling(), call)
        assert not (refused_with and not refused_without), (
            f"removing {rule!r} admitted {value!r}, which the full pipeline "
            f"refuses: {_FAIL_CLOSED_RULES[rule]}"
        )
    for other in _mutated_rules():
        for entry, call in _cases(other, tmp_path / f"{rule}-{other}"):
            with rule_disabled(rule):
                assert _refuses(entry, call), _FAIL_CLOSED_RULES[rule]


def test_lowercase_host_not_path_folds_the_host_and_leaves_the_path() -> None:
    """The rule does its job, which its fail-closed proof does not show.

    Both halves in one value: an uppercase host that has to come back folded,
    and an uppercase path that has to come back exactly as it arrived. The
    standard library's IDNA codec does not fold case, so nothing else in the
    pipeline would do the first half if this rule stopped.
    """
    canonical = canonicalise(DomainType.URL, "https://WWW.SEC.GOV/EVIDENCE/x")
    assert str(canonical) == "https://www.sec.gov/EVIDENCE/x"
    with rule_disabled("lowercase-host-not-path"):
        assert str(canonicalise(DomainType.URL, "https://WWW.SEC.GOV/EVIDENCE/x")) == (
            "https://WWW.SEC.GOV/EVIDENCE/x"
        )


def test_drop_default_ports_drops_the_default_and_keeps_the_rest() -> None:
    """The rule does its job. Removing it changes the value, not a decision.

    The rule is also what reads the port at all — validating one is
    `refuse-invalid-port`'s judgment and converting one is this rule's — so
    without it no port reaches the canonical value, default or not. That is
    a loss in the value handed on and still not a decision, which is the
    distinction the fail-closed proof turns on.
    """
    assert str(canonicalise(DomainType.URL, "https://www.sec.gov:443/a")) == (
        "https://www.sec.gov/a"
    )
    assert str(canonicalise(DomainType.URL, "https://www.sec.gov:8443/a")) == (
        "https://www.sec.gov:8443/a"
    )
    with rule_disabled("drop-default-ports"):
        assert str(canonicalise(DomainType.URL, "https://www.sec.gov:8443/a")) == (
            "https://www.sec.gov/a"
        )


def _canonical_form(value: str, *, without: str | None) -> str:
    """Return the canonical rendering of `value`, optionally without one rule."""
    if without is None:
        return str(canonicalise(DomainType.URL, value))
    with rule_disabled(without):
        return str(canonicalise(DomainType.URL, value))


@pytest.mark.parametrize(
    "value",
    [
        "https://.sec.gov/evidence/x",
        "https://www.sec..gov/evidence/x",
        "https://www.sec.gov\u3002\u3002/evidence/x",
        "https:///evidence/x",
    ],
)
def test_refuse_ambiguous_parse_is_what_refuses_an_empty_label(value: str) -> None:
    """The empty-label guard is in the rule its docstring says it is in.

    The standard library's IDNA codec happens to reject most of these too, so
    asserting against the full pipeline would pass whether or not this
    package had a guard of its own — and the behaviour would then rest on a
    codec detail nothing here records a dependency on. Removing
    `idna-normalise-host` takes that incidental refusal away, so what is left
    refusing is `refuse-ambiguous-parse`.
    """
    entry = sec_ceiling()
    assert _refuses(entry, {"url": value})
    with rule_disabled("idna-normalise-host"):
        assert _refuses(entry, {"url": value}), (
            "with the IDNA rule gone nothing refused an empty-label host, so the "
            "guard `refuse-ambiguous-parse` documents does not exist"
        )


@pytest.mark.parametrize(
    "value",
    [
        "http://\uff05\uff10\uff10.example/evidence/x",
        "http://\uff05\uff12\uff45.sec.gov/evidence/x",
    ],
)
def test_a_canonical_host_may_not_carry_a_percent_escape(value: str) -> None:
    """The residual-separator refusal ranges over the path, not the host.

    The host reaches its canonical form by the encoder, whose NFKC pass can
    turn a fullwidth sequence into a literal `%` escape:
    `http://\uff05\uff10\uff10.example/` used to canonicalise to host
    `%00.example` and hand the adapter exactly that. A client that decodes
    the authority then resolves a name this check never compared, which is
    the differential the path's refusal exists to prevent, on the component
    it does not reach.
    """
    with pytest.raises(ContainmentUndecidable, match="percent escape"):
        canonicalise(DomainType.URL, value)


def test_the_default_port_of_each_scheme_is_dropped() -> None:
    """`_DEFAULT_PORTS` has two entries and needs two witnesses.

    Deleting the `http` entry used to leave the suite green, after which
    `http://h.example/x` and `http://h.example:80/x` canonicalise to
    different values and a ceiling comparison separates two spellings of one
    address.
    """
    for scheme, default, other in (("https", "443", "8443"), ("http", "80", "8080")):
        assert str(canonicalise(DomainType.URL, f"{scheme}://h.example:{default}/x")) == (
            f"{scheme}://h.example/x"
        )
        assert str(canonicalise(DomainType.URL, f"{scheme}://h.example:{other}/x")) == (
            f"{scheme}://h.example:{other}/x"
        )


# AC-0216's fail-closed limb is entered on a premise about the *predicate*
# table, and the criterion's amendment trigger names that table as well as
# r5's clause list. These two checks derive the premise from
# `EXPRESSIBLE_PREDICATES` rather than letting `_FAIL_CLOSED_RULES` assert
# it, so adding a constructor that ranges over a port, or one that reads a
# host case-sensitively, reds here and forces the rule back into the
# mutation limb where it belongs.


#: One predicate per `url` constructor, **read back from `declare`** rather
#: than written canonical here. That is the difference between deriving the
#: monotonicity ground and assuming half of it: the ground is that folding a
#: host cannot remove an admission, which holds only if the predicates are
#: insensitive to host case *and* the declaration surface folds a ceiling's
#: host argument. Probes written lowercase by hand assert the first and
#: assume the second, and a regression that stopped folding `host_eq`'s
#: argument was measured suite-green under exactly that shape.
#:
#: The arguments below are deliberately mixed-case so the readback is
#: evidence about `declare`.
_MIXED_CASE_ARGUMENTS: Mapping[type, tuple[Predicate, ...]] = {
    SchemeIn: (SchemeIn(frozenset({"https"})),),
    HostEq: (HostEq("WWW.SEC.GOV"), HostEq("Attacker.Example")),
    HostInDomain: (HostInDomain("SEC.GOV"), HostInDomain("Attacker.Example")),
    PathWithin: (PathWithin("/evidence/"), PathWithin("/other/")),
}


def _declared(predicate: Predicate) -> Predicate:
    """Return `predicate` as the authoring surface stores it."""
    entry = declare(
        "probe",
        {"u": ("url", (SchemeIn(frozenset({"https"})), HostInDomain("sec.gov"), predicate))},
    )
    stored = [p for p in entry.arguments["u"].predicates if type(p) is type(predicate)]
    return stored[-1]


_PROBES: Mapping[type, tuple[Predicate, ...]] = {
    constructor: tuple(_declared(p) for p in written)
    for constructor, written in _MIXED_CASE_ARGUMENTS.items()
}


#: Which derivation grounds each fail-closed rule, by test name. A rule
#: entering the weak limb without one is refused here rather than admitted
#: by whoever added its reason string.
_DERIVED_GROUNDS: Mapping[str, tuple[str, ...]] = {
    "drop-default-ports": ("test_no_url_predicate_ranges_over_a_port",),
    "lowercase-host-not-path": (
        "test_folding_a_host_never_removes_an_admission",
        "test_the_declaration_surface_folds_a_host_argument",
    ),
}


def test_every_fail_closed_rule_names_a_derivation_that_exists() -> None:
    """AC-0216's weak limb is entered by evidence, not by declaration.

    Adding a rule to `_FAIL_CLOSED_RULES` with only a reason string leaves
    both existing derivations passing — they are about the port and about
    host case — so without this the third rule's limb membership would be
    an author's assertion again.
    """
    assert set(_DERIVED_GROUNDS) == set(_FAIL_CLOSED_RULES)
    module = sys.modules[__name__]
    for rule, names in _DERIVED_GROUNDS.items():
        for name in names:
            assert callable(getattr(module, name, None)), (
                f"{rule!r} names the derivation {name!r}, which does not exist"
            )


def test_the_declaration_surface_folds_a_host_argument() -> None:
    """The half of the monotonicity ground that lives in `declare`.

    `lowercase-host-not-path` is fail-closed because folding a value's host
    cannot remove an admission — and that holds only against a ceiling
    argument already folded. This is what reds if `declare` stops folding
    one, instead of the failure showing up as a neighbouring criterion's
    suffix-lookup case or not at all.
    """
    for written in (*_MIXED_CASE_ARGUMENTS[HostEq], *_MIXED_CASE_ARGUMENTS[HostInDomain]):
        stored = _declared(written)
        rendered = stored.host if isinstance(stored, HostEq) else stored.domain
        assert rendered == rendered.lower(), (
            f"declare stored {stored!r} unfolded, so a host predicate is compared "
            "against an argument that is not canonical and folding a value's host "
            "can remove an admission"
        )


def test_every_url_constructor_has_a_probe() -> None:
    """Setup check: a premise asserted over a constructor nobody probes is no premise."""
    assert set(_PROBES) == set(EXPRESSIBLE_PREDICATES[DomainType.URL])


def _url(value: str) -> CanonicalUrl:
    canonical = canonicalise(DomainType.URL, value)
    assert isinstance(canonical, CanonicalUrl)
    return canonical


@pytest.mark.parametrize(
    "constructor", sorted(EXPRESSIBLE_PREDICATES[DomainType.URL], key=lambda t: t.__name__)
)
def test_no_url_predicate_ranges_over_a_port(constructor: type) -> None:
    """`drop-default-ports` is fail-closed only while this holds.

    The rule normalises a component nothing reads, so removing it cannot
    change a decision. That is a fact about the predicate table, not about
    the canonicaliser, and r5 closes the fragment over numeric ranges — so a
    later phase adding a port-ranging constructor makes the rule
    load-bearing while its fail-closed evidence stays green. This is what
    reds when that happens.
    """
    for predicate in _PROBES[constructor]:
        for base in ("https://www.sec.gov/evidence/x", "https://attacker.example/other/y"):
            without = _url(base)
            with_port = replace(without, port=8443)
            assert admits(predicate, without) == admits(predicate, with_port), (
                f"{constructor.__name__} reads the port, so drop-default-ports is "
                "load-bearing and cannot sit in AC-0216's fail-closed limb"
            )


@pytest.mark.parametrize(
    "constructor", sorted(EXPRESSIBLE_PREDICATES[DomainType.URL], key=lambda t: t.__name__)
)
def test_folding_a_host_never_removes_an_admission(constructor: type) -> None:
    """`lowercase-host-not-path` is fail-closed only while this holds.

    Its ground is not that nothing reads the host — `host_eq` and
    `host_in_domain` both do — but that folding is *monotone* against a
    ceiling argument that is already folded: every value admitted unfolded
    is admitted folded, so removing the rule can only shrink the admitted
    set. A constructor that read a host case-sensitively would break that,
    and this is what reds.
    """
    for predicate in _PROBES[constructor]:
        for base in ("https://WWW.SEC.GOV/evidence/x", "https://Www.Sec.Gov/EVIDENCE/y"):
            unfolded = replace(_url(base), host=urlsplit(base).netloc)
            folded = replace(unfolded, host=unfolded.host.lower())
            assert admits(predicate, folded) or not admits(predicate, unfolded), (
                f"{constructor.__name__} admits a value unfolded that it refuses "
                "folded, so lowercase-host-not-path can remove an admission and "
                "cannot sit in AC-0216's fail-closed limb"
            )
