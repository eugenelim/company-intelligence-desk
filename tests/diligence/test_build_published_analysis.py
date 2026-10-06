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


# ---------------------------------------------------------------------------
# Sustained finding guards — filing-derived value validation
#
# Each test feeds a modified fixture and asserts DiligenceError.
# Mutation→red: removing the guard causes build_published_analysis to
# succeed, so the pytest.raises block raises Failed instead.
# ---------------------------------------------------------------------------


def test_fact_id_missing_raises_diligence_error() -> None:
    """Guard: ix:nonFraction id is required.

    Mutation — remove the id-required check: fact id becomes empty string,
    source_fragment becomes '#', build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(b' id="f-56"', b"", 1)
    with pytest.raises(DiligenceError, match="id"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_fact_id_invalid_pattern_raises_diligence_error() -> None:
    """Guard: ix:nonFraction id must match [A-Za-z_][A-Za-z0-9_.-]{0,127}.

    Mutation — remove the pattern check: id '0invalid' is accepted,
    source_fragment '#0invalid' still fails _SOURCE_FRAGMENT_PATTERN in
    the lineage validator, but build_published_analysis itself succeeds.
    """
    modified = recorded_filing().replace(b'id="f-56"', b'id="0invalid"', 1)
    with pytest.raises(DiligenceError, match="pattern"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_fact_id_duplicate_raises_diligence_error() -> None:
    """Guard: ix:nonFraction ids must be unique in the filing.

    Mutation — remove the duplicate check: two facts share id 'f-56',
    _extract_fact still selects the lexically-minimum id for each context,
    build_published_analysis succeeds with valid source fragments.
    """
    # Change c-19's first fact id from f-57 to f-56 (already used by c-18).
    modified = recorded_filing().replace(b'id="f-57"', b'id="f-56"', 1)
    with pytest.raises(DiligenceError, match="duplicate"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_fact_sign_attribute_raises_diligence_error() -> None:
    """Guard: ix:nonFraction must not carry a sign attribute.

    Mutation — remove the sign check: sign='-' is silently ignored, the
    parser does not negate the value, build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(
        b'format="ixt:num-dot-decimal" scale="6" id="f-56"',
        b'format="ixt:num-dot-decimal" scale="6" id="f-56" sign="-"',
        1,
    )
    with pytest.raises(DiligenceError, match="sign"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_fact_wrong_format_raises_diligence_error() -> None:
    """Guard: ix:nonFraction format must be exactly 'ixt:num-dot-decimal'.

    Mutation — remove the format check: a fact with format='ixt:num-comma-decimal'
    is accepted and build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(
        b'format="ixt:num-dot-decimal"',
        b'format="ixt:num-comma-decimal"',
        1,
    )
    with pytest.raises(DiligenceError, match="format"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_fact_missing_format_raises_diligence_error() -> None:
    """Guard: ix:nonFraction format is required (None != 'ixt:num-dot-decimal').

    Mutation — remove the format check: a fact with no format attribute
    is accepted and build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(b' format="ixt:num-dot-decimal"', b"", 1)
    with pytest.raises(DiligenceError, match="format"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_context_start_date_not_iso_raises_diligence_error() -> None:
    """Guard: xbrli:startDate must match YYYY-MM-DD before fromisoformat.

    Mutation — skip _parse_iso_date for start date: '26-03-29' is copied
    raw into Period.start_date and build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(
        b"<xbrli:startDate>2026-03-29</xbrli:startDate>",
        b"<xbrli:startDate>26-03-29</xbrli:startDate>",
        1,
    )
    with pytest.raises(DiligenceError, match="YYYY-MM-DD"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_context_start_date_wrong_value_raises_diligence_error() -> None:
    """Guard: startDate must equal the canonical expected start for each context.

    Mutation — remove the value check: '2026-03-30' parses as a valid ISO
    date and build_published_analysis succeeds, silently accepting a wrong
    period that could misidentify the quarter.
    """
    modified = recorded_filing().replace(
        b"<xbrli:startDate>2026-03-29</xbrli:startDate>",
        b"<xbrli:startDate>2026-03-30</xbrli:startDate>",
        1,
    )
    with pytest.raises(DiligenceError, match="period start"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_context_with_segment_raises_diligence_error() -> None:
    """Guard: xbrli:segment inside a context entity marks non-consolidated — refused.

    Mutation — remove the segment check: a segmented (non-consolidated)
    context is accepted and build_published_analysis succeeds.
    """
    # Insert <xbrli:segment/> inside c-18's entity before </xbrli:entity>.
    modified = recorded_filing().replace(
        b"0000320193</xbrli:identifier>\n      </xbrli:entity>",
        b"0000320193</xbrli:identifier>\n        <xbrli:segment/>\n      </xbrli:entity>",
        1,
    )
    with pytest.raises(DiligenceError, match="segment"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_fact_value_with_non_numeric_characters_raises_diligence_error() -> None:
    """Guard: display value must contain only digits and commas.

    Mutation — remove the _DISPLAY_VALUE_RE.fullmatch check: '109e3' passes
    Decimal() as 109000, which is still a positive increase, and
    build_published_analysis succeeds with the wrong computed value.
    Replace all three identical copies to avoid the conflicting-duplicate
    guard firing first.
    """
    # '109e3' contains 'e' — fails ^[0-9,]+$ but parses as Decimal(109000).
    modified = recorded_filing().replace(b">109,417<", b">109e3<")
    with pytest.raises(DiligenceError, match="display value"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_fragment_only_hash_makes_claim_unresolved() -> None:
    """Guard: source_fragment must match '#' + valid id pattern in lineage validator.

    '#' alone is non-empty but does not match _SOURCE_FRAGMENT_PATTERN.
    Mutation — revert to 'if not fact.source_fragment': '#' is truthy and
    the claim would not be flagged, so unresolved_claim_ids() returns ().
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    old_fact = artifact.evidence_manifest.facts[0]
    bad_fact = dataclasses.replace(old_fact, source_fragment="#")
    bad_manifest = dataclasses.replace(
        artifact.evidence_manifest,
        facts=(bad_fact, artifact.evidence_manifest.facts[1]),
    )
    bad = dataclasses.replace(artifact, evidence_manifest=bad_manifest)

    assert bad.unresolved_claim_ids() != ()
    with pytest.raises(DiligenceError):
        canonical_bytes(bad)


def test_canonical_bytes_digest_matches_pinned_value() -> None:
    """All guards remain open for canonical inputs: artifact digest is stable.

    Verifies that the filing-derived validation changes do not alter the
    canonical artifact bytes.  A changed digest here means a guard altered
    output for valid input, which would break AC-0410 replay equivalence.
    """
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    raw = canonical_bytes(artifact)
    assert (
        hashlib.sha256(raw).hexdigest()
        == "9aaf1714a11e183c5cc4b8534872779f9e6a895fe2b494aeb4669b09ced3896f"
    )


# ---------------------------------------------------------------------------
# Blocker 1 — non-target segment/sign/format facts do not refuse the build
# ---------------------------------------------------------------------------


def test_non_target_segment_sign_format_facts_do_not_refuse_build() -> None:
    """Non-target contexts and facts with segment, sign="-", or wrong format succeed.

    The real filing has segmented contexts (e.g. c-2), ~54 facts with
    sign="-", and facts with format="ixt:fixed-zero" or absent format.
    Those guards must not fire on non-target elements.

    Mutation — keep the guard filing-wide: the first signed non-target fact
    raises DiligenceError before the target facts are reached, so this
    assertion fails (the build raises rather than returning 16.36).
    """
    filing = recorded_filing()

    # Insert a segmented non-target context (id c-2) before the unit definition.
    # The segment marks c-2 as non-consolidated; only c-18/c-19 are checked.
    extra_ctx = (
        b'    <xbrli:context id="c-2">\n'
        b"      <xbrli:entity>\n"
        b'        <xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193</xbrli:identifier>\n'
        b"        <xbrli:segment/>\n"
        b"      </xbrli:entity>\n"
        b"      <xbrli:period><xbrli:startDate>2026-03-29</xbrli:startDate>"
        b"<xbrli:endDate>2026-06-27</xbrli:endDate></xbrli:period>\n"
        b"    </xbrli:context>\n"
    )
    # Insert a non-target fact with sign="-", one with format="ixt:fixed-zero",
    # and one with no format attribute.  All use concept names that are not
    # the target concept so _extract_fact never validates them.
    extra_facts = (
        b'<ix:nonFraction name="us-gaap:OtherExpenses" contextRef="c-18"'
        b' unitRef="usd" decimals="-6" scale="6"'
        b' format="ixt:num-dot-decimal" id="f-signed-nt-1" sign="-">1,000</ix:nonFraction>\n'
        b'<ix:nonFraction name="us-gaap:FixedZeroItem" contextRef="c-18"'
        b' unitRef="usd" decimals="-6" scale="6"'
        b' format="ixt:fixed-zero" id="f-fmtz-nt-2">0</ix:nonFraction>\n'
        b'<ix:nonFraction name="us-gaap:NoFormatItem" contextRef="c-18"'
        b' unitRef="usd" decimals="-6" scale="6"'
        b' id="f-nofmt-nt-3">5,000</ix:nonFraction>\n'
    )

    modified = filing.replace(
        b'    <xbrli:unit id="usd">', extra_ctx + b'    <xbrli:unit id="usd">', 1
    )
    modified = modified.replace(b"</body>", extra_facts + b"</body>", 1)

    artifact = build_published_analysis(
        filing_html=modified,
        filing_sha256=hashlib.sha256(modified).hexdigest(),
        source_url=_SOURCE_URL,
        as_of_date=_AS_OF_DATE,
    )
    assert artifact.evidence_manifest.calculations[0].value == Decimal("16.36")


def test_segmented_target_context_still_raises_diligence_error() -> None:
    """Guard: segment inside c-18 (a target context) is still refused.

    Mutation — remove the has_segment check in _require_context: a segmented
    c-18 is accepted and build_published_analysis succeeds.
    """
    # The existing test already covers this via a direct byte-replace; this
    # confirms the guard survives Blocker 1's refactoring.
    modified = recorded_filing().replace(
        b"0000320193</xbrli:identifier>\n      </xbrli:entity>",
        b"0000320193</xbrli:identifier>\n        <xbrli:segment/>\n      </xbrli:entity>",
        1,
    )
    with pytest.raises(DiligenceError, match="segment"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_target_fact_with_sign_still_raises_diligence_error() -> None:
    """Guard: sign="-" on a target-concept fact in c-18 is still refused.

    Mutation — remove the sign check in _extract_fact: the signed target fact
    is accepted and build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(
        b'format="ixt:num-dot-decimal" scale="6" id="f-56"',
        b'format="ixt:num-dot-decimal" scale="6" id="f-56" sign="-"',
        1,
    )
    with pytest.raises(DiligenceError, match="sign"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_target_fact_with_wrong_format_still_raises_diligence_error() -> None:
    """Guard: format="ixt:num-comma-decimal" on a target-concept fact is still refused.

    Mutation — remove the format check in _extract_fact: the wrong-format
    target fact is accepted and build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(
        b'format="ixt:num-dot-decimal"',
        b'format="ixt:num-comma-decimal"',
        1,
    )
    with pytest.raises(DiligenceError, match="format"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


def test_target_fact_with_missing_format_still_raises_diligence_error() -> None:
    """Guard: absent format attribute on a target-concept fact is still refused.

    Mutation — remove the format check in _extract_fact: a target fact with no
    format attribute is accepted and build_published_analysis succeeds.
    """
    modified = recorded_filing().replace(b' format="ixt:num-dot-decimal"', b"", 1)
    with pytest.raises(DiligenceError, match="format"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )


# ---------------------------------------------------------------------------
# Blocker 2 — nested ix:nonFraction involving the target concept is refused
# ---------------------------------------------------------------------------


def test_nested_nonfraction_with_target_concept_raises_diligence_error() -> None:
    """Guard: a nested ix:nonFraction where the outer element is the target concept is refused.

    The slice is fail-closed: nesting that involves a target fact is never
    admitted.  With the stack-based implementation, removing the nesting
    detection causes both the outer 999,999 and the existing 109,417 copies
    to be recorded for the target concept in c-18.  _extract_fact detects
    the conflict and raises DiligenceError with message "conflicting", not
    "nested", so pytest.raises(match="nested") fails and the test reds.
    """
    filing = recorded_filing()
    # Insert a nested ix:nonFraction: outer = target concept with 999,999 in
    # c-18 (a conflicting duplicate if both were recorded), inner = non-target.
    nested = (
        b"<ix:nonFraction"
        b' name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"'
        b' contextRef="c-18" unitRef="usd" decimals="-6" scale="6"'
        b' format="ixt:num-dot-decimal" id="f-nest-outer-999">999,999'
        b'<ix:nonFraction name="us-gaap:OtherExpenses"'
        b' contextRef="c-18" unitRef="usd" decimals="-6" scale="6"'
        b' format="ixt:num-dot-decimal"'
        b' id="f-nest-inner-888">50,000</ix:nonFraction>'
        b"</ix:nonFraction>"
    )
    modified = filing.replace(b"</body>", nested + b"</body>", 1)
    with pytest.raises(DiligenceError, match="nested"):
        build_published_analysis(
            filing_html=modified,
            filing_sha256=hashlib.sha256(modified).hexdigest(),
            source_url=_SOURCE_URL,
            as_of_date=_AS_OF_DATE,
        )
