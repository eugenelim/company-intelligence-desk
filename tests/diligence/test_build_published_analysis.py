"""Diligence domain tests — AC-0406 through AC-0410.

The stub function ``test_the_canonical_filing_builds_the_linked_net_sales_claim``
(marked ``# STUB: AC-0407``) matches the plan block byte-for-byte except that its
module-level imports are collected here at the top of the file as the project style
requires (ruff E402).  The function body is unchanged.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from decimal import Decimal

import pytest

from ced.domain.diligence import (
    Calculation,
    Claim,
    ClaimLink,
    DiligenceError,
    FilingFact,
    Memo,
    PublishedAnalysis,
    build_published_analysis,
    canonical_bytes,
    parse_published_analysis,
)
from tests.ingestion.fixture import FILING_CONTENT_HASH, recorded_filing

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm"
)
_AS_OF_DATE = "2026-07-31"

_APPROVED_SENTENCE = (
    "Quarterly net sales increased 16.36% year over year, "
    "from USD 94.036 billion to USD 109.417 billion."
)


# ---------------------------------------------------------------------------
# STUB: AC-0407
# ---------------------------------------------------------------------------


def test_the_canonical_filing_builds_the_linked_net_sales_claim() -> None:
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019326000020/aapl-20260627.htm"
        ),
        as_of_date="2026-07-31",
    )

    calculation = artifact.evidence_manifest.calculations[0]
    assert calculation.value == Decimal("16.36")
    assert artifact.memo.claims[0].evidence_refs == (calculation.evidence_id,)
    assert artifact.unresolved_claim_ids() == ()


# ---------------------------------------------------------------------------
# AC-0406 — XBRL extraction validation
# ---------------------------------------------------------------------------


def test_absent_concept_raises_diligence_error() -> None:
    """Mutation: rename the target concept — fact becomes absent."""
    modified = recorded_filing().replace(
        b"us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        b"us-gaap:DifferentConcept",
    )
    with pytest.raises(DiligenceError, match="absent"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_absent_current_context_raises_diligence_error() -> None:
    """Mutation: remove the c-18 context definition."""
    filing = recorded_filing()
    start = filing.index(b'<xbrli:context id="c-18">')
    end = filing.index(b"</xbrli:context>", start) + len(b"</xbrli:context>")
    modified = filing[:start] + filing[end:]
    with pytest.raises(DiligenceError, match="c-18"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_absent_prior_context_raises_diligence_error() -> None:
    """Mutation: remove the c-19 context definition."""
    filing = recorded_filing()
    start = filing.index(b'<xbrli:context id="c-19">')
    end = filing.index(b"</xbrli:context>", start) + len(b"</xbrli:context>")
    modified = filing[:start] + filing[end:]
    with pytest.raises(DiligenceError, match="c-19"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_period_mismatch_current_raises_diligence_error() -> None:
    """Mutation: change c-18's endDate — period mismatch."""
    modified = recorded_filing().replace(
        b"<xbrli:endDate>2026-06-27</xbrli:endDate>",
        b"<xbrli:endDate>2026-09-27</xbrli:endDate>",
        1,
    )
    with pytest.raises(DiligenceError, match="period end"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_period_mismatch_prior_raises_diligence_error() -> None:
    """Mutation: change c-19's endDate — period mismatch."""
    modified = recorded_filing().replace(
        b"<xbrli:endDate>2025-06-28</xbrli:endDate>",
        b"<xbrli:endDate>2025-09-27</xbrli:endDate>",
    )
    with pytest.raises(DiligenceError, match="period end"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_unit_mismatch_raises_diligence_error() -> None:
    """Mutation: change the unit measure to EUR — USD unit absent."""
    modified = recorded_filing().replace(
        b"<xbrli:measure>iso4217:USD</xbrli:measure>",
        b"<xbrli:measure>iso4217:EUR</xbrli:measure>",
    )
    with pytest.raises(DiligenceError, match="iso4217:USD"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_scale_mismatch_raises_diligence_error() -> None:
    """Mutation: change scale from 6 to 7 — scale mismatch."""
    modified = recorded_filing().replace(b'scale="6"', b'scale="7"')
    with pytest.raises(DiligenceError, match="scale"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_conflicting_duplicates_raises_diligence_error() -> None:
    """Mutation: change one copy of a fact to a different value — conflict."""
    modified = recorded_filing().replace(
        b'id="f-381">109,417</ix:nonFraction>',
        b'id="f-381">108,000</ix:nonFraction>',
    )
    with pytest.raises(DiligenceError, match="conflicting"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_memo_sentence_is_rendered_from_the_calculated_values() -> None:
    """Every number in the sentence follows the facts it claims (AC-0408).

    Mutation: render the sentence from a fixed string. The changed facts below
    still produce 16.36% and 109.417 there, so this check reds.
    """
    modified = (
        recorded_filing().replace(b">109,417<", b">112,850<").replace(b">94,036<", b">95,000<")
    )
    artifact = build_published_analysis(
        filing_html=modified,
        filing_sha256=hashlib.sha256(modified).hexdigest(),
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    assert artifact.evidence_manifest.calculations[0].value == Decimal("18.79")
    assert artifact.memo.claims[0].text == (
        "Quarterly net sales increased 18.79% year over year, "
        "from USD 95.000 billion to USD 112.850 billion."
    )


def test_a_non_increase_has_no_approved_sentence() -> None:
    """Only the approved increase wording exists, so a decline refuses (AC-0408)."""
    modified = recorded_filing().replace(b">109,417<", b">90,000<")
    with pytest.raises(DiligenceError, match="increase"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_identical_duplicates_collapse_to_two_facts() -> None:
    """The canonical fixture (three copies per fact) produces exactly two facts."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    assert len(artifact.evidence_manifest.facts) == 2


def test_cik_mismatch_raises_diligence_error() -> None:
    """Mutation: change the CIK in entity identifiers — CIK mismatch."""
    modified = recorded_filing().replace(
        b">0000320193<",
        b">0000000001<",
    )
    with pytest.raises(DiligenceError, match="CIK"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


# ---------------------------------------------------------------------------
# AC-0407 — Calculation lineage
# ---------------------------------------------------------------------------


def test_calculation_has_correct_operation() -> None:
    """Lineage field: operation name is recorded correctly."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    calc = artifact.evidence_manifest.calculations[0]
    assert calc.operation == "year_over_year_percent_change"


def test_calculation_lineage_records_both_fact_refs() -> None:
    """Lineage field: input_fact_refs names both facts."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    calc = artifact.evidence_manifest.calculations[0]
    fact_ids = {f.evidence_id for f in artifact.evidence_manifest.facts}
    assert set(calc.input_fact_refs) == fact_ids


def test_calculation_records_correct_numerator_and_denominator() -> None:
    """Lineage: numerator=15381, denominator=94036; values are Decimal, not float.

    Mutation — float conversion: isinstance(calc.numerator, Decimal) reds.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    calc = artifact.evidence_manifest.calculations[0]
    assert isinstance(calc.numerator, Decimal)
    assert isinstance(calc.denominator, Decimal)
    assert isinstance(calc.value, Decimal)
    assert calc.numerator == Decimal("15381")
    assert calc.denominator == Decimal("94036")


def test_calculation_rounding_rule_and_output_scale() -> None:
    """Lineage: rounding metadata is recorded correctly.

    Mutation — ROUND_DOWN: result would be 16.35, not 16.36;
    test_the_canonical_filing_builds_the_linked_net_sales_claim reds.
    Mutation — output_scale != 2: quantize target differs, value changes.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    calc = artifact.evidence_manifest.calculations[0]
    assert calc.rounding_rule == "ROUND_HALF_UP"
    assert calc.output_scale == 2
    assert calc.unit == "percent"


# ---------------------------------------------------------------------------
# AC-0408 — No model call; fixed memo sentence
# ---------------------------------------------------------------------------


def test_no_model_adapter_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    """BedrockConverseModel.__init__ wired to fail — build must not call it.

    Mutation: call BedrockConverseModel inside build_published_analysis →
    AssertionError fires and the test reds.  AC-0408.
    """

    def _fail_init(self: object, *args: object, **kwargs: object) -> None:
        raise AssertionError(
            "BedrockConverseModel constructor must not be called "
            "during build_published_analysis"
        )

    monkeypatch.setattr(
        "pydantic_ai.models.bedrock.BedrockConverseModel.__init__",
        _fail_init,
    )
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    assert artifact.memo.claims[0].text == _APPROVED_SENTENCE


def test_distinctive_non_fact_string_not_in_memo() -> None:
    """Inject a canary string into a non-fact section; it must not appear in memo.

    Mutation: derive memo text from filing HTML → canary appears in memo.
    AC-0408.
    """
    canary = "DILIGENCE_CANARY_XQZ987654"
    filing = recorded_filing()
    modified = filing.replace(
        b"Apple Inc. Form 10-Q",
        f"Apple Inc. Form 10-Q {canary}".encode(),
    )
    assert canary.encode() in modified

    artifact = build_published_analysis(
        filing_html=modified,
        filing_sha256=hashlib.sha256(modified).hexdigest(),
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    memo_text = artifact.memo.claims[0].text
    assert memo_text == _APPROVED_SENTENCE
    assert canary not in memo_text


def test_memo_has_exactly_one_factual_claim() -> None:
    """Exactly one claim; its text equals the approved sentence."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    assert len(artifact.memo.claims) == 1
    assert artifact.memo.claims[0].text == _APPROVED_SENTENCE


# ---------------------------------------------------------------------------
# AC-0409 — Exhaustive lineage validator refuses serialisation on any gap
# ---------------------------------------------------------------------------


def test_empty_evidence_refs_makes_claim_unresolved() -> None:
    """Delete edge: claim carries no evidence_refs → unresolved, serialisation refused.

    Mutation: skip the evidence_refs check in unresolved_claim_ids →
    the claim would not appear in the returned tuple; this assertion reds.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    old_claim = artifact.memo.claims[0]
    bad_claim = dataclasses.replace(old_claim, evidence_refs=())
    bad_memo = dataclasses.replace(artifact.memo, claims=(bad_claim,))
    bad = dataclasses.replace(artifact, memo=bad_memo)

    assert bad.unresolved_claim_ids() == (old_claim.claim_id,)
    with pytest.raises(DiligenceError):
        canonical_bytes(bad)

    # Confirm Claim and Memo are importable (suppresses unused-import warning).
    assert Claim is not None
    assert Memo is not None
    assert PublishedAnalysis is not None


def test_missing_claim_link_makes_claim_unresolved() -> None:
    """Delete edge: remove claim_link → claim has no link → unresolved."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    bad_manifest = dataclasses.replace(artifact.evidence_manifest, claim_links=())
    bad = dataclasses.replace(artifact, evidence_manifest=bad_manifest)

    assert bad.unresolved_claim_ids() != ()
    with pytest.raises(DiligenceError):
        canonical_bytes(bad)


def test_dangling_calculation_ref_makes_claim_unresolved() -> None:
    """Dangle edge: claim_link points to a nonexistent calculation.

    Mutation: remove the calculation_ref check in unresolved_claim_ids →
    the claim resolves despite the dangling ref; the assertion reds.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    old_link = artifact.evidence_manifest.claim_links[0]
    bad_link = dataclasses.replace(old_link, calculation_ref="nonexistent-calc")
    bad_manifest = dataclasses.replace(artifact.evidence_manifest, claim_links=(bad_link,))
    bad = dataclasses.replace(artifact, evidence_manifest=bad_manifest)

    assert bad.unresolved_claim_ids() != ()
    with pytest.raises(DiligenceError):
        canonical_bytes(bad)

    assert ClaimLink is not None


def test_dangling_input_fact_ref_makes_claim_unresolved() -> None:
    """Dangle edge: calculation references facts that do not exist.

    Mutation: skip the input_fact_refs check → dangling ref goes undetected;
    the assertion reds.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    old_calc = artifact.evidence_manifest.calculations[0]
    bad_calc = dataclasses.replace(
        old_calc, input_fact_refs=("nonexistent-fact", "nonexistent-fact-2")
    )
    bad_manifest = dataclasses.replace(artifact.evidence_manifest, calculations=(bad_calc,))
    bad = dataclasses.replace(artifact, evidence_manifest=bad_manifest)

    assert bad.unresolved_claim_ids() != ()
    with pytest.raises(DiligenceError):
        canonical_bytes(bad)

    assert Calculation is not None


def test_missing_source_makes_claim_unresolved() -> None:
    """Delete edge: remove source → fact's source_id cannot resolve."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    bad_manifest = dataclasses.replace(artifact.evidence_manifest, sources=())
    bad = dataclasses.replace(artifact, evidence_manifest=bad_manifest)

    assert bad.unresolved_claim_ids() != ()
    with pytest.raises(DiligenceError):
        canonical_bytes(bad)


def test_empty_source_fragment_makes_claim_unresolved() -> None:
    """Dangle edge: fact carries an empty source_fragment.

    Mutation: remove the source_fragment check → empty fragment goes undetected;
    the assertion reds.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    old_fact = artifact.evidence_manifest.facts[0]
    bad_fact = dataclasses.replace(old_fact, source_fragment="")
    bad_manifest = dataclasses.replace(
        artifact.evidence_manifest,
        facts=(bad_fact, artifact.evidence_manifest.facts[1]),
    )
    bad = dataclasses.replace(artifact, evidence_manifest=bad_manifest)

    assert bad.unresolved_claim_ids() != ()
    with pytest.raises(DiligenceError):
        canonical_bytes(bad)

    assert FilingFact is not None


# ---------------------------------------------------------------------------
# AC-0410 — Canonical byte stability and input sensitivity
# ---------------------------------------------------------------------------


def test_canonical_bytes_are_deterministic() -> None:
    """Two builds from identical inputs produce byte-identical canonical JSON.

    Mutation: include a timestamp or random nonce → bytes differ; assertion reds.
    """
    b1 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=FILING_CONTENT_HASH,
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )
    )
    b2 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=FILING_CONTENT_HASH,
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )
    )
    assert b1 == b2


def test_different_filing_sha256_produces_different_bytes() -> None:
    """Changing the filing digest changes the canonical output."""
    other_hash = "a" * 64
    b1 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=FILING_CONTENT_HASH,
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )
    )
    b2 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=other_hash,
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )
    )
    assert b1 != b2


def test_different_as_of_date_produces_different_bytes() -> None:
    """Changing the as-of date changes the canonical output."""
    b1 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=FILING_CONTENT_HASH,
            source_url=_SOURCE_URL,
            as_of_date="2026-07-31",
        )
    )
    b2 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=FILING_CONTENT_HASH,
            source_url=_SOURCE_URL,
            as_of_date="2026-08-31",
        )
    )
    assert b1 != b2


def test_different_source_url_produces_different_bytes() -> None:
    """Changing the source URL changes the canonical output."""
    b1 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=FILING_CONTENT_HASH,
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )
    )
    b2 = canonical_bytes(
        build_published_analysis(
            filing_html=recorded_filing(),
            filing_sha256=FILING_CONTENT_HASH,
            source_url="https://www.sec.gov/Archives/edgar/data/320193/other/filing.htm",
            as_of_date=_AS_OF_DATE,
        )
    )
    assert b1 != b2


def test_canonical_bytes_round_trip() -> None:
    """canonical_bytes → parse_published_analysis round-trips without loss."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    raw = canonical_bytes(artifact)
    restored = parse_published_analysis(raw)
    assert canonical_bytes(restored) == raw


def test_parse_published_analysis_rejects_wrong_schema_version() -> None:
    """parse_published_analysis fails closed on an unsupported schema_version."""
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    raw_bytes = canonical_bytes(artifact)
    raw_dict = json.loads(raw_bytes)
    raw_dict["schema_version"] = "unknown/99"
    corrupted = json.dumps(raw_dict).encode("utf-8")
    with pytest.raises(DiligenceError, match="schema_version"):
        parse_published_analysis(corrupted)


def test_parse_published_analysis_rejects_non_utf8() -> None:
    """parse_published_analysis fails closed on invalid bytes."""
    with pytest.raises(DiligenceError, match="UTF-8"):
        parse_published_analysis(b"\xff\xfe invalid")


def test_stable_fragment_selection_among_identical_duplicates() -> None:
    """The stable source fragment is the lexically smallest element id.

    Fixture c-18 ids: f-56, f-381, f-731 → lexically min is f-381.
    Fixture c-19 ids: f-57, f-382, f-760 → lexically min is f-382.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    facts_by_context = {f.context: f for f in artifact.evidence_manifest.facts}
    assert facts_by_context["c-18"].source_fragment == "#f-381"
    assert facts_by_context["c-19"].source_fragment == "#f-382"
