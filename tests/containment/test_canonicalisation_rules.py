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

from collections.abc import Mapping
from pathlib import Path

import pytest

from ced.domain.containment.canonicaliser import (
    FS_PATH_RULES,
    URL_RULES,
    canonicalise,
    rule_names,
)
from ced.domain.containment.ceiling import Admitted, CeilingEntry, declare, evaluate
from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.errors import ContainmentUndecidable
from ced.domain.containment.predicates import Within
from tests.containment.fixture import (
    canonicaliser_clauses,
    decode_and_dot_segments_transposed,
    rule_disabled,
    sec_ceiling,
)

#: One input per load-bearing URL rule: refused as things stand, admitted
#: once that rule is gone. Each was chosen so that no *other* rule's removal
#: changes its answer — the independence half of the criterion is what that
#: buys.
_URL_CASES: Mapping[str, str] = {
    # Two `@` in the authority: parsers disagree about which side is the host.
    "refuse-ambiguous-parse": "https://a@attacker.example@www.sec.gov/evidence/x",
    # A right-to-left override IDNA prohibits, sitting inside a host that ends
    # in `.sec.gov` as plain text.
    "idna-normalise-host": "https://www\u202e.sec.gov/evidence/x",
    # Double-encoded, so one decoding round leaves an encoded separator behind
    # and dot-segment removal never sees a traversal at all.
    "percent-decode-then-refuse-residual": (
        "https://www.sec.gov/evidence/%252e%252e/etc/passwd"
    ),
    # A literal traversal, which needs no decoding to escape the path root.
    "remove-dot-segments": "https://www.sec.gov/evidence/../etc/passwd",
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


def _case(rule: str, workspace: Path) -> tuple[CeilingEntry, dict[str, object]]:
    if rule == "resolve-symlinks":
        return _symlink_case(workspace)
    return sec_ceiling(), {"url": _URL_CASES[rule]}


def _refuses(entry: CeilingEntry, call: Mapping[str, object]) -> bool:
    """Return whether the fragment declines the call, by denial or by raise.

    Both are refusals. Which one a case gets is a property of the input, not
    of the rule being load-bearing, so AC-0216 reads them the same way.
    """
    try:
        return not isinstance(evaluate(entry, call), Admitted)
    except ContainmentUndecidable:
        return True


def test_every_rule_is_accounted_for(tmp_path: Path) -> None:
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
    entry, call = _case(rule, tmp_path)
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
        entry, call = _case(other, tmp_path / f"{disabled}-{other}")
        with rule_disabled(disabled):
            assert _refuses(entry, call), (
                f"removing {disabled!r} also admitted {other!r}'s case, so the two "
                "rules are entangled and neither mutation isolates a rule"
            )


def test_percent_decoding_runs_before_dot_segment_removal() -> None:
    """The pinned transposition case. AC-0216 cannot reach this one.

    Every rule is still present here; only the order of two of them changes.
    With decoding first the encoded traversal becomes a real one and is
    removed; with removal first there is nothing to remove, and the decode
    that follows produces the traversal after the last check has run.
    """
    entry = sec_ceiling()
    assert _refuses(entry, {"url": _TRANSPOSITION_CASE})
    with decode_and_dot_segments_transposed():
        assert not _refuses(entry, {"url": _TRANSPOSITION_CASE}), (
            "the transposed order still refuses the encoded traversal, so this "
            "case is not pinning the order it claims to"
        )


@pytest.mark.parametrize("rule", sorted(_FAIL_CLOSED_RULES))
def test_a_fail_closed_rule_admits_nothing_when_it_is_removed(
    rule: str, tmp_path: Path
) -> None:
    """The direction that is true for the two normalising clauses.

    AC-0216 asks for an input the removal admits. For these two there is
    none, and this is the assertion that says so rather than leaving the
    claim in prose: nothing the full pipeline refuses becomes admitted, over
    every case in this module and over the positive path as well.
    """
    for other in _mutated_rules():
        entry, call = _case(other, tmp_path / f"{rule}-{other}")
        with rule_disabled(rule):
            assert _refuses(entry, call), _FAIL_CLOSED_RULES[rule]
    with rule_disabled(rule):
        assert isinstance(
            evaluate(sec_ceiling(), {"url": "https://www.sec.gov/evidence/report.pdf"}),
            Admitted,
        )


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
    """The rule does its job. Removing it changes the value, not a decision."""
    assert str(canonicalise(DomainType.URL, "https://www.sec.gov:443/a")) == (
        "https://www.sec.gov/a"
    )
    assert str(canonicalise(DomainType.URL, "https://www.sec.gov:8443/a")) == (
        "https://www.sec.gov:8443/a"
    )
    with rule_disabled("drop-default-ports"):
        assert str(canonicalise(DomainType.URL, "https://www.sec.gov:443/a")) == (
            "https://www.sec.gov:443/a"
        )
