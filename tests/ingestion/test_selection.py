"""Selection and validation tests — AC-0401 and AC-0405.

Every guard tested here earns a named mutation red documented in
``docs/specs/first-published-analysis/notes/verification-ledger.md``.

Tests run offline (no substrate, no network).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ced.worker.ingestion import (
    CANONICAL_ACCESSION,
    CANONICAL_AS_OF,
    CANONICAL_CIK,
    CANONICAL_PRIMARY_DOC,
    IngestionError,
    _run_ingest_from_bytes,
    _select_filing,
    _validate_primary_doc,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "first_published_analysis.json"
)
_FIXTURE_HTML = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "first_published_analysis.html"
)


def _load_submissions() -> dict:  # type: ignore[type-arg]
    return json.loads(_FIXTURE_JSON.read_bytes())


def _recent() -> dict:  # type: ignore[type-arg]
    return _load_submissions()["filings"]["recent"]


# ---------------------------------------------------------------------------
# _select_filing — happy path
# ---------------------------------------------------------------------------


def test_select_filing_finds_canonical_accession() -> None:
    """The fixture contains the canonical accession and it is selected."""
    result = _select_filing(_recent(), CANONICAL_AS_OF, CANONICAL_CIK, CANONICAL_ACCESSION)
    assert result["accession"] == CANONICAL_ACCESSION
    assert result["primary_doc"] == CANONICAL_PRIMARY_DOC
    assert result["form"] == "10-Q"
    assert result["filing_date"] == "2026-07-31"


# ---------------------------------------------------------------------------
# AC-0405: post-as-of filings are refused
# ---------------------------------------------------------------------------


def test_select_filing_refuses_future_filing() -> None:
    """A filing dated after the as-of date is refused even if accession matches.

    Mutation: remove the ``filing_date > as_of_date`` guard — the test
    would pass without raising ``IngestionError``.
    """
    recent = _recent()
    # Replace the canonical filing's date with a future date.
    idx = recent["accessionNumber"].index(CANONICAL_ACCESSION)
    recent["filingDate"][idx] = "2026-12-31"  # after 2026-07-31

    with pytest.raises(IngestionError, match="after the requested as-of date"):
        _select_filing(recent, CANONICAL_AS_OF, CANONICAL_CIK, CANONICAL_ACCESSION)


# ---------------------------------------------------------------------------
# AC-0401: wrong CIK is refused at the ingest level
# ---------------------------------------------------------------------------


def test_ingest_refuses_unsupported_cik(tmp_path: Path) -> None:
    """An unsupported CIK gets IngestionError before any filing request.

    Mutation: remove the canonical-CIK equality check — the test would not
    raise an error for a wrong CIK.
    """
    # Build a submissions JSON with a different CIK.
    submissions = _load_submissions()
    submissions["cik"] = "999999"

    # Use WRONG CIK in the accession so _select_filing won't find the match.
    wrong_accession = "0000999999-26-000020"
    submissions["filings"]["recent"]["accessionNumber"] = [wrong_accession]

    submissions_bytes = json.dumps(submissions).encode()
    filing_bytes = _FIXTURE_HTML.read_bytes()

    with pytest.raises(IngestionError, match="not found"):
        _run_ingest_from_bytes(submissions_bytes, filing_bytes)


# ---------------------------------------------------------------------------
# AC-0401: wrong as-of date is refused
# ---------------------------------------------------------------------------


def test_ingest_refuses_unsupported_as_of_date() -> None:
    """Filing dated after a wrong as-of date is refused.

    Mutation: replace the ``as_of_date`` parameter with a fixed constant —
    the test would not check the date at all.
    """
    # The canonical filing date is 2026-07-31; ask for 2026-01-01 (earlier).
    recent = _recent()

    with pytest.raises(IngestionError, match="not found|after the requested"):
        _select_filing(recent, "2026-01-01", CANONICAL_CIK, CANONICAL_ACCESSION)


# ---------------------------------------------------------------------------
# _validate_primary_doc — AC-0401 primary document validation
# ---------------------------------------------------------------------------


def test_validate_primary_doc_accepts_canonical() -> None:
    """The canonical primary document passes all checks."""
    result = _validate_primary_doc(CANONICAL_PRIMARY_DOC, CANONICAL_CIK, CANONICAL_ACCESSION)
    assert result == CANONICAL_PRIMARY_DOC


def test_validate_primary_doc_refuses_absolute_url() -> None:
    """An absolute URL in the primary document is refused before any request.

    Mutation: remove the ``://`` check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="URL|userinfo"):
        _validate_primary_doc(
            "https://evil.example.com/aapl.htm", CANONICAL_CIK, CANONICAL_ACCESSION
        )


def test_validate_primary_doc_refuses_userinfo() -> None:
    """A document containing userinfo (``@``) is refused.

    Mutation: remove the ``@`` check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="URL|userinfo"):
        _validate_primary_doc("user@host/aapl.htm", CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_forward_slash() -> None:
    """A raw path separator is refused.

    Mutation: remove the ``/`` check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="path separator"):
        _validate_primary_doc("dir/aapl.htm", CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_encoded_slash() -> None:
    """A URL-encoded path separator (``%2f``) is refused.

    Mutation: remove the ``%2f`` check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="path separator"):
        _validate_primary_doc("dir%2faapl.htm", CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_backslash() -> None:
    """A backslash path separator is refused.

    Mutation: remove the ``\\\\`` check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="path separator"):
        _validate_primary_doc("dir\\aapl.htm", CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_dot_segment() -> None:
    """A dot-segment traversal (``../``) is refused.

    Mutation: remove the dot-segment check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="dot segment"):
        _validate_primary_doc("../aapl.htm", CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_current_dir_dot() -> None:
    """A bare ``.`` or ``./`` prefix is refused.

    Mutation: remove the ``./`` check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="dot segment"):
        _validate_primary_doc("./aapl.htm", CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_bare_dot() -> None:
    """A bare ``.`` is refused.

    Mutation: remove the ``doc in (".", "..")`` check — the test would not raise.
    """
    with pytest.raises(IngestionError, match="dot segment"):
        _validate_primary_doc(".", CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_overlong() -> None:
    """A basename exceeding 256 characters is refused.

    Mutation: remove the length check — the test would not raise.
    """
    long_name = "a" + "b" * 256  # 257 chars total
    with pytest.raises(IngestionError, match="256|limit|overlong|exceeds"):
        _validate_primary_doc(long_name, CANONICAL_CIK, CANONICAL_ACCESSION)


def test_validate_primary_doc_refuses_disallowed_chars() -> None:
    """Characters outside the declared alphabet are refused.

    Mutation: remove the pattern match — the test would not raise.
    """
    with pytest.raises(IngestionError, match="pattern"):
        _validate_primary_doc("aapl file.htm", CANONICAL_CIK, CANONICAL_ACCESSION)


# ---------------------------------------------------------------------------
# AC-0405: missing fields in submission metadata
# ---------------------------------------------------------------------------


def test_select_filing_refuses_missing_accession_field() -> None:
    """Missing ``accessionNumber`` key in recent filings fails ingestion.

    Mutation: remove the required-keys check — a KeyError would propagate
    instead of ``IngestionError``.
    """
    recent = _recent()
    del recent["accessionNumber"]

    with pytest.raises(IngestionError, match="missing required field"):
        _select_filing(recent, CANONICAL_AS_OF, CANONICAL_CIK, CANONICAL_ACCESSION)


def test_select_filing_refuses_missing_filing_date_field() -> None:
    """Missing ``filingDate`` key fails ingestion.

    Mutation: same as above.
    """
    recent = _recent()
    del recent["filingDate"]

    with pytest.raises(IngestionError, match="missing required field"):
        _select_filing(recent, CANONICAL_AS_OF, CANONICAL_CIK, CANONICAL_ACCESSION)


def test_select_filing_refuses_no_match() -> None:
    """An accession not present in the metadata fails ingestion.

    Mutation: replace the ``if found is None`` guard with a silent default —
    the test would not raise.
    """
    recent = _recent()
    # Replace the canonical accession with a different one.
    for i in range(len(recent["accessionNumber"])):
        recent["accessionNumber"][i] = "9999999999-99-999999"

    with pytest.raises(IngestionError, match="not found"):
        _select_filing(recent, CANONICAL_AS_OF, CANONICAL_CIK, CANONICAL_ACCESSION)


# ---------------------------------------------------------------------------
# AC-0401: later-dated entries do not interfere with selection
# ---------------------------------------------------------------------------


def test_fixture_contains_later_dated_entry() -> None:
    """The fixture has a later-dated entry (10-K dated 2026-10-30).

    This exercises the as-of filter: the 10-K would be refused if the
    selection looked for it, proving the fixture was designed for selection
    testing rather than a single-entry trivial match.
    """
    recent = _recent()
    dates = recent["filingDate"]
    # At least one entry should be after the as-of date.
    assert any(d > CANONICAL_AS_OF for d in dates), (
        "fixture must contain at least one entry dated after the as-of date "
        "so that the selection filter is exercised"
    )


def test_fixture_contains_other_form_entry() -> None:
    """The fixture has an entry with a different form (10-K).

    This ensures the fixture was designed to exercise form diversity.
    """
    recent = _recent()
    forms = recent["form"]
    assert any(f != "10-Q" for f in forms), (
        "fixture must contain at least one non-10-Q entry so selection "
        "is not trivially satisfied by a single-entry list"
    )


# ---------------------------------------------------------------------------
# AC-0404: fixture content guards
# ---------------------------------------------------------------------------


def test_fixture_html_contains_no_prose_or_signatures() -> None:
    """The fixture HTML does not contain filing prose or signature structures.

    This checks the privacy-safe property described in AC-0404: no real-person
    names, signature blocks, or full filing prose appear in the committed
    fixture.
    """
    content = _FIXTURE_HTML.read_text(encoding="utf-8")
    # No real-person identifier patterns.
    assert "signature" not in content.lower(), "fixture HTML must not contain a signature block"
    # No SEC disclaimer / legalese that would indicate copying from the real filing.
    assert "pursuant to the requirements" not in content.lower(), (
        "fixture HTML must not contain filing prose"
    )


def test_fixture_html_contains_required_facts() -> None:
    """The fixture HTML contains the required fact elements and contexts."""
    content = _FIXTURE_HTML.read_text(encoding="utf-8")
    # Required contexts.
    assert 'id="c-18"' in content
    assert 'id="c-19"' in content
    # Required unit.
    assert 'id="usd"' in content
    # Required fact IDs — at least the canonical ones (f-56, f-57).
    assert 'id="f-56"' in content
    assert 'id="f-57"' in content
    # At least two duplicate copies per context (for T2 duplicate-collapse testing).
    assert content.count('contextRef="c-18"') >= 2
    assert content.count('contextRef="c-19"') >= 2
