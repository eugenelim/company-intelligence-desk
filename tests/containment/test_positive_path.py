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

from ced.domain.containment.canonicaliser import CanonicalUrl
from ced.domain.containment.ceiling import Admitted, evaluate
from tests.containment.fixture import sec_ceiling


def test_a_canonical_in_ceiling_url_is_admitted() -> None:
    decision = evaluate(sec_ceiling(), {"url": "https://www.sec.gov/evidence/report.pdf"})
    assert isinstance(decision, Admitted)
    assert str(decision.canonical["url"]) == "https://www.sec.gov/evidence/report.pdf"


def test_an_in_root_fs_path_is_admitted() -> None:
    decision = evaluate(sec_ceiling(), {"path": "/evidence/filings/2024/report.txt"})
    assert isinstance(decision, Admitted)
    assert decision.canonical["path"] == "/evidence/filings/2024/report.txt"


def test_both_arguments_are_admitted_in_one_call() -> None:
    decision = evaluate(
        sec_ceiling(),
        {"url": "https://www.sec.gov/evidence/report.pdf", "path": "/evidence/report.txt"},
    )
    assert isinstance(decision, Admitted)
    assert isinstance(decision.canonical["url"], CanonicalUrl)
