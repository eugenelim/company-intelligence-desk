"""AC-0218 — the fragment admits, against the ceiling AC-0213 refuses against.

Every other criterion in this spec is a refusal, and a canonicaliser that
refuses everything satisfies all of them. This is the one case standing
against that, which is why it runs against the *same* ceiling rather than a
permissive one written for the occasion.

**It stops at the fragment's answer.** No tool body runs in this package and
nothing here can run one, so the other half of the positive path — an
admitted call reaching an approved tool body — is
`walking-skeleton-policy-decision-point`'s AC-0318.
"""

from __future__ import annotations

from pathlib import Path

from ced.domain.containment.canonicaliser import CanonicalUrl
from ced.domain.containment.ceiling import Admitted, evaluate
from tests.containment.fixture import EVIDENCE_ROOT, path_call, sec_ceiling, url_call


def test_the_evidence_root_is_not_on_this_host() -> None:
    """Setup check: canonicalising an `fs-path` reads the host filesystem.

    `within("/evidence")` and the values below are resolved with
    `os.path.realpath`, so a machine that carried `/evidence` — as a symlink
    above all — would change what every `fs-path` case in this suite means.
    Reding here is better than those cases quietly testing something else.
    """
    assert not Path(EVIDENCE_ROOT).exists(), (
        f"{EVIDENCE_ROOT} exists on this machine, so the fs-path cases resolve "
        "against it instead of lexically"
    )


def test_a_canonical_in_ceiling_url_is_admitted() -> None:
    decision = evaluate(sec_ceiling(), url_call("https://www.sec.gov/evidence/report.pdf"))
    assert isinstance(decision, Admitted)
    assert str(decision.canonical["url"]) == "https://www.sec.gov/evidence/report.pdf"


def test_an_in_root_fs_path_is_admitted() -> None:
    decision = evaluate(sec_ceiling(), path_call("/evidence/filings/2024/report.txt"))
    assert isinstance(decision, Admitted)
    assert decision.canonical["path"] == "/evidence/filings/2024/report.txt"


def test_both_arguments_are_admitted_in_one_call() -> None:
    decision = evaluate(
        sec_ceiling(),
        {"url": "https://www.sec.gov/evidence/report.pdf", "path": "/evidence/report.txt"},
    )
    assert isinstance(decision, Admitted)
    assert isinstance(decision.canonical["url"], CanonicalUrl)


def test_the_canonical_value_carries_the_query_it_was_given() -> None:
    """The query is part of the value AC-0214 says the adapter observes.

    No predicate ranges over it — § Follow-ons records that as an
    unconstrained component, and it is r5's fragment that leaves it so — but
    the rendering that carries it to the adapter still has to be right.
    Without this case `CanonicalUrl.__str__` can drop the query entirely and
    every other check stays green, which would hand the adapter a different
    request from the one that was decided.
    """
    decision = evaluate(
        sec_ceiling(), url_call("https://www.sec.gov/evidence/report.pdf?cik=320193&type=10-K")
    )
    assert isinstance(decision, Admitted)
    assert str(decision.canonical["url"]) == (
        "https://www.sec.gov/evidence/report.pdf?cik=320193&type=10-K"
    )


def test_a_traversal_above_the_root_still_yields_an_absolute_path() -> None:
    """Dot-segment removal may not walk off the front of the path.

    `/../x` has nothing above it to remove, and a removal that pops the
    leading empty segment yields `x` — a *relative* path handed to an
    adapter, which resolves it against whatever base the adapter has. The
    `remove-dot-segments` mutation case drives the escape; this one drives
    the guard that keeps the result absolute.
    """
    decision = evaluate(sec_ceiling(), url_call("https://www.sec.gov/../evidence/x"))
    assert isinstance(decision, Admitted)
    assert str(decision.canonical["url"]) == "https://www.sec.gov/evidence/x"


def test_a_path_ending_in_a_dot_segment_keeps_its_trailing_separator() -> None:
    """`/evidence/.` names the directory, and so must its canonical form."""
    decision = evaluate(sec_ceiling(), url_call("https://www.sec.gov/evidence/2024/."))
    assert isinstance(decision, Admitted)
    assert str(decision.canonical["url"]) == "https://www.sec.gov/evidence/2024/"
