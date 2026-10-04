"""Deterministic diligence domain: Inline XBRL extraction, net-sales
calculation, fixed memo, and evidence manifest.

``build_published_analysis`` is the single public entry point for T2.  It
reads one canonical Inline XBRL filing, validates its identity and structure,
computes the quarterly net-sales year-over-year change with ``Decimal``
arithmetic, and returns an immutable artifact carrying the memo and a
fully-linked evidence manifest.

No model call, no filing prose, no provider dependency.  All output bytes
come from fixed constants, arithmetic on parsed numeric values, and
caller-supplied provenance metadata.  AC-0408: no model, provider, tool
call, or filing-derived string contributes any byte of the artifact.

Standard library only: ``html.parser``, ``decimal``, ``hashlib``, ``json``,
``dataclasses``.  No new package dependency is introduced.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from typing import Any, Final

__all__ = [
    "DiligenceError",
    "PublishedAnalysis",
    "EvidenceManifest",
    "EvidenceSource",
    "FilingFact",
    "Calculation",
    "ClaimLink",
    "Claim",
    "Memo",
    "Period",
    "build_published_analysis",
    "canonical_bytes",
    "parse_published_analysis",
]


# ---------------------------------------------------------------------------
# Domain error
# ---------------------------------------------------------------------------


class DiligenceError(Exception):
    """Single domain error type for all fail-closed diligence refusals.

    Raised by ``build_published_analysis``, ``canonical_bytes``, and
    ``parse_published_analysis`` on absent, conflicting, mismatched,
    or unparseable input.
    """


# ---------------------------------------------------------------------------
# Constants — target values for the canonical Apple 10-Q slice
# ---------------------------------------------------------------------------

_SCHEMA_VERSION: Final = "first-published-analysis/1"

#: Canonical CIK, padded to ten digits, as it appears in XBRL contexts.
_CANONICAL_CIK: Final = "0000320193"

#: SEC CIK identifier scheme URI.
_CANONICAL_CIK_SCHEME: Final = "http://www.sec.gov/CIK"

#: The one XBRL concept selected for this slice.
_TARGET_CONCEPT: Final = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"

#: The unit measure that all selected facts must carry.
_TARGET_UNIT_MEASURE: Final = "iso4217:USD"

#: Required scale attribute on each selected fact element.
_TARGET_SCALE: Final = 6

#: Required decimals attribute on each selected fact element.
_TARGET_DECIMALS: Final = "-6"

#: XBRL context id for the current-period (FY2026 Q3) fact.
_CURRENT_CONTEXT_ID: Final = "c-18"

#: XBRL context id for the prior-period (FY2025 Q3) fact.
_PRIOR_CONTEXT_ID: Final = "c-19"

#: Required period end date for the current context.
_CURRENT_PERIOD_END: Final = "2026-06-27"

#: Required period end date for the prior context.
_PRIOR_PERIOD_END: Final = "2025-06-28"

# --- Fixed memo text (AC-0408) -------------------------------------------

#: Memo title — structural, not a factual claim.
_MEMO_TITLE: Final = "Quarterly net sales year-over-year analysis"

#: The one approved factual sentence form. Every number in it is rendered from
#: the calculation and its scale-6 input facts; no filing prose contributes a byte.
_MEMO_SENTENCE_FORM: Final = (
    "Quarterly net sales increased {result}% year over year, "
    "from USD {prior} billion to USD {current} billion."
)

#: Scale 6 is millions; one billion is 10^3 of those, so billions keep three places.
_BILLIONS_PER_SCALED_UNIT: Final = Decimal("0.001")


def _render_memo_sentence(current: Decimal, prior: Decimal, result: Decimal) -> str:
    """Render the approved sentence from Decimal values, never from floats.

    Only an increase has an approved wording, so any other direction refuses.
    """
    if result <= 0:
        raise DiligenceError("only an increase has an approved memo sentence")
    return _MEMO_SENTENCE_FORM.format(
        result=f"{result:.2f}",
        prior=f"{prior * _BILLIONS_PER_SCALED_UNIT:.3f}",
        current=f"{current * _BILLIONS_PER_SCALED_UNIT:.3f}",
    )


# --- Internal evidence IDs — stable across builds -------------------------

_SOURCE_ID: Final = "source-primary-filing"
_CURRENT_FACT_ID: Final = "fact-revenue-c18"
_PRIOR_FACT_ID: Final = "fact-revenue-c19"
_CALC_ID: Final = "calc-net-sales-yoy-pct"
_CLAIM_ID: Final = "claim-net-sales-yoy-pct"


# ---------------------------------------------------------------------------
# Immutable public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    """An XBRL duration context period (start and end date strings)."""

    start_date: str
    end_date: str


@dataclass(frozen=True)
class EvidenceSource:
    """One archived SEC source referenced by the evidence manifest."""

    source_id: str
    archived_url: str
    digest: str  # SHA-256 hex of the filing bytes
    source_ref: str  # object-store key; empty when not yet stored


@dataclass(frozen=True)
class FilingFact:
    """One validated XBRL numeric fact extracted from the filing."""

    evidence_id: str
    concept: str
    context: str
    period: Period
    unit: str  # e.g. "iso4217:USD"
    scale: int
    decimal_value: Decimal
    source_id: str
    source_fragment: str  # e.g. "#f-56"


@dataclass(frozen=True)
class Calculation:
    """Lineage record for one deterministic arithmetic claim.

    Every Decimal field is stored as a Decimal, not a float, so the
    canonical string representation is exact.  AC-0407.
    """

    evidence_id: str
    operation: str  # "year_over_year_percent_change"
    input_fact_refs: tuple[str, ...]
    formula: str
    numerator: Decimal
    denominator: Decimal
    rounding_rule: str  # "ROUND_HALF_UP"
    output_scale: int  # decimal places
    unit: str  # "percent"
    value: Decimal


@dataclass(frozen=True)
class ClaimLink:
    """One entry in the manifest linking a claim id to a calculation."""

    claim_id: str
    calculation_ref: str  # evidence_id of the Calculation


@dataclass(frozen=True)
class Claim:
    """One factual claim in the memo."""

    claim_id: str
    text: str
    evidence_refs: tuple[str, ...]  # evidence_ids of Calculations or FilingFacts


@dataclass(frozen=True)
class Memo:
    """The fixed-format research memo."""

    title: str
    claims: tuple[Claim, ...]


@dataclass(frozen=True)
class EvidenceManifest:
    """Machine-readable evidence manifest for one analysis artifact."""

    sources: tuple[EvidenceSource, ...]
    facts: tuple[FilingFact, ...]
    calculations: tuple[Calculation, ...]
    claim_links: tuple[ClaimLink, ...]


@dataclass(frozen=True)
class PublishedAnalysis:
    """Complete deterministic analysis artifact.

    Execution-varying fields (run id, retrieval time) are excluded so
    byte-identical inputs produce byte-identical canonical JSON.  AC-0410.
    """

    schema_version: str
    cik: str
    as_of_date: str
    source_url: str
    filing_digest: str
    memo: Memo
    evidence_manifest: EvidenceManifest

    def unresolved_claim_ids(self) -> tuple[str, ...]:
        """Return ids of claims with any missing or dangling lineage edge.

        Walks: claims → claim_links → calculations → facts → sources →
        fragments.  Returns an empty tuple when every claim is fully linked.
        AC-0409.
        """
        manifest = self.evidence_manifest
        calc_by_id = {c.evidence_id: c for c in manifest.calculations}
        fact_by_id = {f.evidence_id: f for f in manifest.facts}
        source_by_id = {s.source_id: s for s in manifest.sources}
        link_by_claim = {cl.claim_id: cl for cl in manifest.claim_links}

        unresolved: set[str] = set()

        for claim in self.memo.claims:
            cid = claim.claim_id

            # 1. Each claim must carry at least one evidence_ref.
            if not claim.evidence_refs:
                unresolved.add(cid)
                continue

            # 2. Each evidence_ref must point to a known calculation or fact.
            for ref in claim.evidence_refs:
                if ref not in calc_by_id and ref not in fact_by_id:
                    unresolved.add(cid)
                    break

            # 3. The claim must have a corresponding claim_link.
            if cid not in link_by_claim:
                unresolved.add(cid)
                continue

            link = link_by_claim[cid]

            # 4. The claim_link's calculation_ref must resolve.
            if link.calculation_ref not in calc_by_id:
                unresolved.add(cid)
                continue

            calc = calc_by_id[link.calculation_ref]

            # 5. Each input_fact_ref must resolve.
            all_facts_ok = True
            for fref in calc.input_fact_refs:
                if fref not in fact_by_id:
                    unresolved.add(cid)
                    all_facts_ok = False
                    break

            if not all_facts_ok:
                continue

            # 6. Each fact must resolve to a source with a non-empty fragment.
            for fref in calc.input_fact_refs:
                fact = fact_by_id[fref]
                if fact.source_id not in source_by_id:
                    unresolved.add(cid)
                    break
                if not fact.source_fragment:
                    unresolved.add(cid)
                    break

        return tuple(sorted(unresolved))


# ---------------------------------------------------------------------------
# Internal: raw parsed structures
# ---------------------------------------------------------------------------


@dataclass
class _RawContext:
    id: str
    scheme: str
    cik: str
    start_date: str
    end_date: str


@dataclass
class _RawFact:
    id: str
    name: str
    context_ref: str
    unit_ref: str
    decimals: str
    scale: str
    display_value: str


# ---------------------------------------------------------------------------
# Internal: attribute reader (single-read rule — mirrors quarantine/mint.py)
# ---------------------------------------------------------------------------


def _read_attr(
    attrs: list[tuple[str, str | None]],
    attr_name: str,
) -> str | None:
    """Return the single value of *attr_name*, or ``None`` if absent.

    Raises ``DiligenceError`` if the attribute is declared more than once.
    Applying the same declare-at-most-once rule as ``quarantine/mint.py``
    prevents last-wins resolution of filer-controlled attributes.
    """
    found = [v for name, v in attrs if name == attr_name]
    if len(found) > 1:
        raise DiligenceError(
            f"attribute {attr_name!r} declared {len(found)} times in one element; "
            f"no value ranks the occurrences — refusing"
        )
    return found[0] if found else None


def _require_attr(
    attrs: list[tuple[str, str | None]],
    attr_name: str,
    element: str,
) -> str:
    """Return the single non-empty value of *attr_name*, or raise ``DiligenceError``."""
    v = _read_attr(attrs, attr_name)
    if not v:
        raise DiligenceError(f"element <{element}> is missing required attribute {attr_name!r}")
    return v


# ---------------------------------------------------------------------------
# Internal: Inline XBRL parser
# ---------------------------------------------------------------------------


class _FilingReader(HTMLParser):
    """Collect XBRL contexts, units, and numeric facts from an Inline XBRL file.

    ``html.parser`` lowercases tag and attribute names, so ``ix:nonFraction``
    becomes ``ix:nonfraction`` and ``contextRef`` becomes ``contextref``.
    Attribute values are filer-authored; the single-read rule applies via
    ``_read_attr`` and ``_require_attr``.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)

        # Results populated during parsing.
        self.contexts: dict[str, _RawContext] = {}
        self.units: dict[str, str] = {}  # unit id → measure value
        self.raw_facts: list[_RawFact] = []

        # --- Context parsing state ---
        self._ctx_id: str | None = None
        self._ctx_scheme: str | None = None
        self._ctx_cik: str | None = None
        self._ctx_start: str | None = None
        self._ctx_end: str | None = None

        # --- Unit parsing state ---
        self._unit_id: str | None = None
        self._unit_measure: str | None = None

        # --- Fact parsing state ---
        self._fact_attrs: list[tuple[str, str | None]] | None = None
        self._fact_parts: list[str] = []

        # --- Generic text accumulator ---
        # Used for identifier/startdate/enddate/measure text.
        self._text_parts: list[str] = []
        self._collecting_for: str = ""  # end tag that will claim the text

    # ---- text accumulation helpers -----------------------------------------

    def _start_collect(self, for_tag: str) -> None:
        self._collecting_for = for_tag
        self._text_parts = []

    def _end_collect(self) -> str:
        text = "".join(self._text_parts).strip()
        self._collecting_for = ""
        self._text_parts = []
        return text

    # ---- HTMLParser overrides -----------------------------------------------

    def handle_data(self, data: str) -> None:
        if self._collecting_for:
            self._text_parts.append(data)
        if self._fact_attrs is not None:
            self._fact_parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "xbrli:context":
            self._ctx_id = _require_attr(attrs, "id", "xbrli:context")
            self._ctx_scheme = None
            self._ctx_cik = None
            self._ctx_start = None
            self._ctx_end = None

        elif tag == "xbrli:identifier":
            self._ctx_scheme = _read_attr(attrs, "scheme") or ""
            self._start_collect("xbrli:identifier")

        elif tag == "xbrli:startdate":
            self._start_collect("xbrli:startdate")

        elif tag == "xbrli:enddate":
            self._start_collect("xbrli:enddate")

        elif tag == "xbrli:unit":
            self._unit_id = _require_attr(attrs, "id", "xbrli:unit")
            self._unit_measure = None

        elif tag == "xbrli:measure":
            self._start_collect("xbrli:measure")

        elif tag == "ix:nonfraction":
            self._fact_attrs = attrs
            self._fact_parts = []

    def handle_endtag(self, tag: str) -> None:  # noqa: C901 – state machine
        if tag == "xbrli:identifier":
            self._ctx_cik = self._end_collect()

        elif tag == "xbrli:startdate":
            self._ctx_start = self._end_collect()

        elif tag == "xbrli:enddate":
            self._ctx_end = self._end_collect()

        elif tag == "xbrli:context":
            if self._ctx_id is None:
                return
            cid = self._ctx_id
            if cid in self.contexts:
                raise DiligenceError(f"duplicate context id {cid!r} in filing")
            self.contexts[cid] = _RawContext(
                id=cid,
                scheme=self._ctx_scheme or "",
                cik=self._ctx_cik or "",
                start_date=self._ctx_start or "",
                end_date=self._ctx_end or "",
            )
            self._ctx_id = None

        elif tag == "xbrli:measure":
            self._unit_measure = self._end_collect()

        elif tag == "xbrli:unit":
            uid = self._unit_id
            measure = self._unit_measure
            if uid and measure:
                if uid in self.units:
                    raise DiligenceError(f"duplicate unit id {uid!r} in filing")
                self.units[uid] = measure
            self._unit_id = None
            self._unit_measure = None

        elif tag == "ix:nonfraction":
            fa = self._fact_attrs
            if fa is None:
                return
            display = "".join(self._fact_parts).strip()
            self.raw_facts.append(
                _RawFact(
                    id=_read_attr(fa, "id") or "",
                    name=_require_attr(fa, "name", "ix:nonfraction"),
                    context_ref=_require_attr(fa, "contextref", "ix:nonfraction"),
                    unit_ref=_read_attr(fa, "unitref") or "",
                    decimals=_read_attr(fa, "decimals") or "",
                    scale=_read_attr(fa, "scale") or "",
                    display_value=display,
                )
            )
            self._fact_attrs = None
            self._fact_parts = []


# ---------------------------------------------------------------------------
# Internal: validation helpers
# ---------------------------------------------------------------------------


def _validate_context_identity(ctx: _RawContext) -> None:
    """Validate entity CIK scheme and value against the canonical filing."""
    if ctx.scheme != _CANONICAL_CIK_SCHEME:
        raise DiligenceError(
            f"context {ctx.id!r}: identifier scheme {ctx.scheme!r} "
            f"is not the canonical scheme {_CANONICAL_CIK_SCHEME!r}"
        )
    if ctx.cik != _CANONICAL_CIK:
        raise DiligenceError(
            f"context {ctx.id!r}: CIK mismatch — got {ctx.cik!r}, expected {_CANONICAL_CIK!r}"
        )


def _require_context(
    reader: _FilingReader,
    ctx_id: str,
    expected_period_end: str,
) -> _RawContext:
    """Return the validated context, or raise ``DiligenceError``."""
    ctx = reader.contexts.get(ctx_id)
    if ctx is None:
        raise DiligenceError(f"required XBRL context {ctx_id!r} is absent from filing")
    _validate_context_identity(ctx)
    if ctx.end_date != expected_period_end:
        raise DiligenceError(
            f"context {ctx_id!r}: period end {ctx.end_date!r} "
            f"does not match expected {expected_period_end!r}"
        )
    return ctx


def _find_unit_by_measure(reader: _FilingReader, target_measure: str) -> str | None:
    """Return the id of the first unit whose measure equals *target_measure*."""
    for uid, measure in reader.units.items():
        if measure == target_measure:
            return uid
    return None


def _parse_display_value(display: str) -> Decimal:
    """Parse a dot-decimal XBRL display value to ``Decimal``.  Fail closed."""
    normalized = display.strip().replace(",", "")
    if not normalized:
        raise DiligenceError("empty display value for XBRL fact")
    try:
        return Decimal(normalized)
    except Exception as exc:
        raise DiligenceError(f"cannot parse display value {display!r} as Decimal") from exc


def _extract_fact(
    reader: _FilingReader,
    concept: str,
    context_ref: str,
    unit_id: str,
) -> _RawFact:
    """Extract and validate the fact for (concept, context_ref).

    Collapses identical duplicates (same Decimal value) by choosing the
    lexically smallest element id for stable fragment selection.  Raises
    ``DiligenceError`` on conflicts, absent unit, or scale/decimals
    mismatch.  AC-0406.
    """
    matches = [
        rf for rf in reader.raw_facts if rf.name == concept and rf.context_ref == context_ref
    ]
    if not matches:
        raise DiligenceError(
            f"required fact ({concept!r}, {context_ref!r}) is absent from filing"
        )

    # Validate unit, scale, decimals on every copy.
    for rf in matches:
        if rf.unit_ref != unit_id:
            raise DiligenceError(
                f"fact ({concept!r}, {context_ref!r}): "
                f"unit ref {rf.unit_ref!r} does not match expected {unit_id!r}"
            )
        try:
            scale = int(rf.scale)
        except ValueError:
            raise DiligenceError(
                f"fact ({concept!r}, {context_ref!r}): "
                f"scale {rf.scale!r} is not a valid integer"
            ) from None
        if scale != _TARGET_SCALE:
            raise DiligenceError(
                f"fact ({concept!r}, {context_ref!r}): "
                f"scale {scale} does not match expected {_TARGET_SCALE}"
            )
        if rf.decimals != _TARGET_DECIMALS:
            raise DiligenceError(
                f"fact ({concept!r}, {context_ref!r}): "
                f"decimals {rf.decimals!r} does not match expected {_TARGET_DECIMALS!r}"
            )

    # Reject conflicting values; collapse identical duplicates.
    normalized_values = {rf.display_value.strip().replace(",", "") for rf in matches}
    if len(normalized_values) > 1:
        raise DiligenceError(
            f"conflicting duplicate values for fact "
            f"({concept!r}, {context_ref!r}): {sorted(normalized_values)!r}"
        )

    # Stable selection: lexically smallest element id among identical copies.
    return min(matches, key=lambda rf: rf.id)


# ---------------------------------------------------------------------------
# Internal: serialisation helpers
# ---------------------------------------------------------------------------


def _replace_decimals(obj: Any) -> Any:
    """Recursively replace ``Decimal`` with its canonical string form.

    ``dataclasses.asdict`` converts tuples to lists (correct for JSON) and
    recurses into nested dataclasses, but does not touch ``Decimal``.  This
    converter runs over the result so ``json.dumps`` receives only standard
    JSON-serialisable types.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _replace_decimals(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        # dataclasses.asdict preserves tuple types; normalise both to list for JSON.
        return [_replace_decimals(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Internal: parse helpers for parse_published_analysis
# ---------------------------------------------------------------------------


def _pstr(d: dict[str, Any], key: str) -> str:
    v = d[key]
    if not isinstance(v, str):
        raise TypeError(f"field {key!r} must be a string, got {type(v).__name__!r}")
    return v


def _pint(d: dict[str, Any], key: str) -> int:
    v = d[key]
    if not isinstance(v, int) or isinstance(v, bool):
        raise TypeError(f"field {key!r} must be an integer, got {type(v).__name__!r}")
    return v


def _pdecimal(d: dict[str, Any], key: str) -> Decimal:
    s = _pstr(d, key)
    try:
        return Decimal(s)
    except Exception as exc:
        raise ValueError(f"cannot parse {key!r} as Decimal: {exc}") from exc


def _pdict(d: dict[str, Any], key: str) -> dict[str, Any]:
    v = d[key]
    if not isinstance(v, dict):
        raise TypeError(f"field {key!r} must be an object, got {type(v).__name__!r}")
    return v


def _plist(d: dict[str, Any], key: str) -> list[Any]:
    v = d[key]
    if not isinstance(v, list):
        raise TypeError(f"field {key!r} must be an array, got {type(v).__name__!r}")
    return v


def _pdict_item(item: Any, parent_key: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise TypeError(
            f"item in {parent_key!r} must be an object, got {type(item).__name__!r}"
        )
    return item


def _parse_period(d: dict[str, Any]) -> Period:
    return Period(start_date=_pstr(d, "start_date"), end_date=_pstr(d, "end_date"))


def _parse_source(d: dict[str, Any]) -> EvidenceSource:
    return EvidenceSource(
        source_id=_pstr(d, "source_id"),
        archived_url=_pstr(d, "archived_url"),
        digest=_pstr(d, "digest"),
        source_ref=_pstr(d, "source_ref"),
    )


def _parse_fact(d: dict[str, Any]) -> FilingFact:
    return FilingFact(
        evidence_id=_pstr(d, "evidence_id"),
        concept=_pstr(d, "concept"),
        context=_pstr(d, "context"),
        period=_parse_period(_pdict(d, "period")),
        unit=_pstr(d, "unit"),
        scale=_pint(d, "scale"),
        decimal_value=_pdecimal(d, "decimal_value"),
        source_id=_pstr(d, "source_id"),
        source_fragment=_pstr(d, "source_fragment"),
    )


def _parse_calculation(d: dict[str, Any]) -> Calculation:
    return Calculation(
        evidence_id=_pstr(d, "evidence_id"),
        operation=_pstr(d, "operation"),
        input_fact_refs=tuple(str(r) for r in _plist(d, "input_fact_refs")),
        formula=_pstr(d, "formula"),
        numerator=_pdecimal(d, "numerator"),
        denominator=_pdecimal(d, "denominator"),
        rounding_rule=_pstr(d, "rounding_rule"),
        output_scale=_pint(d, "output_scale"),
        unit=_pstr(d, "unit"),
        value=_pdecimal(d, "value"),
    )


def _parse_claim_link(d: dict[str, Any]) -> ClaimLink:
    return ClaimLink(
        claim_id=_pstr(d, "claim_id"),
        calculation_ref=_pstr(d, "calculation_ref"),
    )


def _parse_claim(d: dict[str, Any]) -> Claim:
    return Claim(
        claim_id=_pstr(d, "claim_id"),
        text=_pstr(d, "text"),
        evidence_refs=tuple(str(r) for r in _plist(d, "evidence_refs")),
    )


def _parse_memo(d: dict[str, Any]) -> Memo:
    return Memo(
        title=_pstr(d, "title"),
        claims=tuple(_parse_claim(_pdict_item(item, "claims")) for item in _plist(d, "claims")),
    )


def _parse_manifest(d: dict[str, Any]) -> EvidenceManifest:
    return EvidenceManifest(
        sources=tuple(
            _parse_source(_pdict_item(item, "sources")) for item in _plist(d, "sources")
        ),
        facts=tuple(_parse_fact(_pdict_item(item, "facts")) for item in _plist(d, "facts")),
        calculations=tuple(
            _parse_calculation(_pdict_item(item, "calculations"))
            for item in _plist(d, "calculations")
        ),
        claim_links=tuple(
            _parse_claim_link(_pdict_item(item, "claim_links"))
            for item in _plist(d, "claim_links")
        ),
    )


def _parse_artifact_dict(d: dict[str, Any]) -> PublishedAnalysis:
    """Reconstruct a ``PublishedAnalysis`` from a raw JSON dict."""
    schema_version = _pstr(d, "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {schema_version!r}; expected {_SCHEMA_VERSION!r}"
        )
    cik = _pstr(d, "cik")
    if cik != _CANONICAL_CIK:
        raise ValueError(f"CIK {cik!r} does not match canonical {_CANONICAL_CIK!r}")
    return PublishedAnalysis(
        schema_version=schema_version,
        cik=cik,
        as_of_date=_pstr(d, "as_of_date"),
        source_url=_pstr(d, "source_url"),
        filing_digest=_pstr(d, "filing_digest"),
        memo=_parse_memo(_pdict(d, "memo")),
        evidence_manifest=_parse_manifest(_pdict(d, "evidence_manifest")),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_published_analysis(
    filing_html: bytes,
    filing_sha256: str,
    source_url: str,
    as_of_date: str,
    *,
    filing_ref: str = "",
) -> PublishedAnalysis:
    """Build a deterministic analysis artifact from a pinned Inline XBRL filing.

    Parameters
    ----------
    filing_html:
        Raw bytes of the Inline XBRL filing.  Decoded as UTF-8; raises
        ``DiligenceError`` on undecodable input.
    filing_sha256:
        SHA-256 hex digest of *filing_html* as computed by the caller.
        Stored in the artifact as provenance; not re-verified here.
    source_url:
        The archived SEC URL the filing was retrieved from.
    as_of_date:
        Analysis as-of date (ISO 8601, e.g. ``"2026-07-31"``).
    filing_ref:
        Object-store reference for the filing bytes.  Supplied by the T3
        worker so T4 can re-read the raw bytes; empty string for T2 tests.

    Returns
    -------
    PublishedAnalysis
        Immutable artifact with fully linked memo and evidence manifest.

    Raises
    ------
    DiligenceError
        On absent, conflicting, mismatched, or unparseable input.
    """
    # 1. Decode — fail closed on non-UTF-8 bytes.
    try:
        html_text = filing_html.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiligenceError(f"filing bytes are not valid UTF-8: {exc}") from exc

    # 2. Parse the Inline XBRL.
    reader = _FilingReader()
    reader.feed(html_text)
    reader.close()

    # 3. Validate required contexts (identity + period end).
    current_ctx = _require_context(reader, _CURRENT_CONTEXT_ID, _CURRENT_PERIOD_END)
    prior_ctx = _require_context(reader, _PRIOR_CONTEXT_ID, _PRIOR_PERIOD_END)

    # 4. Validate required unit.
    usd_unit_id = _find_unit_by_measure(reader, _TARGET_UNIT_MEASURE)
    if usd_unit_id is None:
        raise DiligenceError(f"no unit with measure {_TARGET_UNIT_MEASURE!r} found in filing")

    # 5. Extract and validate selected facts (collapse identical duplicates).
    current_raw = _extract_fact(reader, _TARGET_CONCEPT, _CURRENT_CONTEXT_ID, usd_unit_id)
    prior_raw = _extract_fact(reader, _TARGET_CONCEPT, _PRIOR_CONTEXT_ID, usd_unit_id)

    # 6. Parse display values to Decimal (no float conversion).
    current_val = _parse_display_value(current_raw.display_value)
    prior_val = _parse_display_value(prior_raw.display_value)

    # 7. Decimal calculation (AC-0407).
    #    Formula: (current - prior) / prior × 100, rounded once to 2 dp.
    numerator = current_val - prior_val
    denominator = prior_val
    raw_pct = (numerator / denominator) * Decimal("100")
    result = raw_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 8. Assemble artifact — every structural piece is a fixed constant or
    #    derived from caller-supplied parameters; no filing prose is used.
    source = EvidenceSource(
        source_id=_SOURCE_ID,
        archived_url=source_url,
        digest=filing_sha256,
        source_ref=filing_ref,
    )

    current_fact = FilingFact(
        evidence_id=_CURRENT_FACT_ID,
        concept=current_raw.name,
        context=current_raw.context_ref,
        period=Period(
            start_date=current_ctx.start_date,
            end_date=current_ctx.end_date,
        ),
        unit=_TARGET_UNIT_MEASURE,
        scale=_TARGET_SCALE,
        decimal_value=current_val,
        source_id=_SOURCE_ID,
        source_fragment=f"#{current_raw.id}",
    )

    prior_fact = FilingFact(
        evidence_id=_PRIOR_FACT_ID,
        concept=prior_raw.name,
        context=prior_raw.context_ref,
        period=Period(
            start_date=prior_ctx.start_date,
            end_date=prior_ctx.end_date,
        ),
        unit=_TARGET_UNIT_MEASURE,
        scale=_TARGET_SCALE,
        decimal_value=prior_val,
        source_id=_SOURCE_ID,
        source_fragment=f"#{prior_raw.id}",
    )

    calculation = Calculation(
        evidence_id=_CALC_ID,
        operation="year_over_year_percent_change",
        input_fact_refs=(_CURRENT_FACT_ID, _PRIOR_FACT_ID),
        formula="(current - prior) / prior × 100",
        numerator=numerator,
        denominator=denominator,
        rounding_rule="ROUND_HALF_UP",
        output_scale=2,
        unit="percent",
        value=result,
    )

    claim = Claim(
        claim_id=_CLAIM_ID,
        text=_render_memo_sentence(current_val, prior_val, result),
        evidence_refs=(_CALC_ID,),
    )

    memo = Memo(title=_MEMO_TITLE, claims=(claim,))

    manifest = EvidenceManifest(
        sources=(source,),
        facts=(current_fact, prior_fact),
        calculations=(calculation,),
        claim_links=(ClaimLink(claim_id=_CLAIM_ID, calculation_ref=_CALC_ID),),
    )

    return PublishedAnalysis(
        schema_version=_SCHEMA_VERSION,
        cik=_CANONICAL_CIK,
        as_of_date=as_of_date,
        source_url=source_url,
        filing_digest=filing_sha256,
        memo=memo,
        evidence_manifest=manifest,
    )


def canonical_bytes(artifact: PublishedAnalysis) -> bytes:
    """Return canonical JSON bytes for *artifact*.

    Validates complete lineage before serialising; raises ``DiligenceError``
    if any claim lacks complete lineage (AC-0409).  Two builds from identical
    inputs produce byte-identical output (AC-0410).

    Format: sorted keys, no insignificant whitespace, ``Decimal`` as canonical
    strings, UTF-8.
    """
    unresolved = artifact.unresolved_claim_ids()
    if unresolved:
        raise DiligenceError(
            f"lineage incomplete for claim ids {sorted(unresolved)!r}; serialisation refused"
        )
    raw = dataclasses.asdict(artifact)
    data = _replace_decimals(raw)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def parse_published_analysis(data: bytes) -> PublishedAnalysis:
    """Strictly parse and validate a canonical JSON artifact.

    Raises ``DiligenceError`` on any missing field, wrong type, unknown
    schema version, or CIK mismatch.  Fail closed — a partially valid
    artifact is refused rather than partially accepted.  AC-0414.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiligenceError(f"artifact bytes are not valid UTF-8: {exc}") from exc
    try:
        raw: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiligenceError(f"artifact is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise DiligenceError("artifact root must be a JSON object")
    try:
        return _parse_artifact_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise DiligenceError(f"artifact schema invalid: {exc}") from exc
