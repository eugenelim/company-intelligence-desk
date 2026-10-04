"""ced-ingest: bounded SEC ingestion command.

Acquires one immutable evidence snapshot for the canonical Apple 10-Q as of
2026-07-31 and writes it to the local object store.

Two modes:

``ced-ingest``
    Live mode: fetches submissions metadata and the archived filing from SEC
    through the shared rate gate.  Requires ``SEC_CONTACT`` to be set.

``ced-ingest --offline-fixture``
    Offline mode: reads the privacy-safe committed fixture files
    ``tests/fixtures/first_published_analysis.html`` and
    ``tests/fixtures/first_published_analysis.json``.  No network call.
    Suitable for offline tests and the T5 end-to-end check.

``ced-ingest observe --out <path>``
    Observation mode: runs 60 scheduled requests through the same client and
    gate, writes ``notes/sec-access.json``-format JSON.  Requires
    ``SEC_CONTACT``.  Do not edit the output — its fields are generated.

Both ingest modes print one JSON line to stdout:
    ``{"snapshot_ref": "<scope>/<hex>", "filing_ref": "<scope>/<hex>",
       "cik": "...", "accession": "...", "form": "...",
       "filing_date": "...", "as_of_date": "..."}``

Live mode additionally includes ``"attempts": [...]`` — a list of redacted
``AttemptRecord`` dicts, one per SEC request made (submissions then filing).

AC-0401, AC-0404, AC-0405.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

__all__ = [
    "CANONICAL_CIK",
    "CANONICAL_AS_OF",
    "CANONICAL_ACCESSION",
    "CANONICAL_FORM",
    "CANONICAL_PRIMARY_DOC",
    "CANONICAL_SOURCE_URL",
    "PRIMARY_DOC_PATTERN",
    "IngestionError",
    "_normalize_cik",
    "_validate_submissions_cik",
    "_validate_accession_filer_prefix",
    "ingest",
    "run",
]

# ---------------------------------------------------------------------------
# Canonical filing constants (AC-0401)
# ---------------------------------------------------------------------------

#: Zero-padded 10-digit CIK.
CANONICAL_CIK: str = "0000320193"

#: The fixed as-of date for this slice.
CANONICAL_AS_OF: str = "2026-07-31"

#: The fixed accession number.
CANONICAL_ACCESSION: str = "0000320193-26-000020"

#: The expected form type.
CANONICAL_FORM: str = "10-Q"

#: The expected primary document filename.
CANONICAL_PRIMARY_DOC: str = "aapl-20260627.htm"

#: The archive URL for the primary document.
CANONICAL_SOURCE_URL: str = (
    "https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm"
)

#: Valid primary-document filename: must match this pattern (AC-0401).
PRIMARY_DOC_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}")

# ---------------------------------------------------------------------------
# Fixture paths (offline mode)
# ---------------------------------------------------------------------------

_FIXTURES_DIR: Path = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
_FIXTURE_HTML: Path = _FIXTURES_DIR / "first_published_analysis.html"
_FIXTURE_JSON: Path = _FIXTURES_DIR / "first_published_analysis.json"


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class IngestionError(Exception):
    """A validation or selection failure that prevents storing a snapshot."""


# ---------------------------------------------------------------------------
# Selection and validation helpers
# ---------------------------------------------------------------------------


def _validate_primary_doc(doc: str) -> str:
    """Validate and return the normalised primary-document basename (AC-0401).

    Refuses an absolute URL, userinfo, dot segment, path separator, traversal,
    or overlong name.  The normalised form is a single basename (no ``/``).
    """
    # Refuse any URL-like string (contains ://, @, ?)
    if any(c in doc for c in ("://", "@", "?")):
        raise IngestionError(
            "primary document looks like a URL or contains userinfo: "
            "refusing before any filing request"
        )
    # Refuse dot segments before path separators; ``../`` and ``./`` start with
    # a dot traversal prefix, and a bare ``.`` or ``..`` is also refused.
    if doc in (".", "..") or doc.startswith("./") or doc.startswith("../"):
        raise IngestionError(
            "primary document is a dot segment or traversal: refusing before any filing request"
        )
    # Refuse any path separator (raw or encoded)
    if "/" in doc or "\\" in doc or "%2f" in doc.lower() or "%5c" in doc.lower():
        raise IngestionError(
            "primary document contains a path separator: refusing before any filing request"
        )
    # Refuse overlong names explicitly before the pattern check so the message
    # names the limit clearly.
    if len(doc) > 256:
        raise IngestionError(
            f"primary document basename exceeds 256 characters "
            f"({len(doc)} chars): refusing before any filing request"
        )
    # Validate against the declared alphabet.
    if PRIMARY_DOC_PATTERN.fullmatch(doc) is None:
        raise IngestionError(
            "primary document fails the pattern check "
            "(must match [A-Za-z0-9][A-Za-z0-9._-]{0,255}): "
            "refusing before any filing request"
        )
    return doc


def _normalize_cik(raw: str) -> str:
    """Normalise a CIK to its zero-padded 10-digit canonical form.

    SEC submissions JSON may return a bare integer string ("320193") or the
    padded form ("0000320193"); both normalise to the same value so they can
    be compared.
    """
    stripped = raw.strip()
    # Strip leading zeros, then re-pad to 10 digits.
    return stripped.lstrip("0").zfill(10)


def _validate_submissions_cik(submissions: dict[str, object], required_cik: str) -> None:
    """Refuse when the submissions document's own CIK disagrees with required_cik.

    Normalises zero-padding before comparing so "320193" == "0000320193".
    Raises ``IngestionError`` before any filing request or write (AC-0401).
    """
    raw_cik = submissions.get("cik")
    if raw_cik is None:
        raise IngestionError(
            "submissions document has no 'cik' field: refusing before any filing request"
        )
    found_norm = _normalize_cik(str(raw_cik))
    required_norm = _normalize_cik(required_cik)
    if found_norm != required_norm:
        raise IngestionError(
            "submissions document CIK does not match the canonical CIK: "
            "refusing before any filing request"
        )


def _validate_accession_filer_prefix(accession: str, required_cik: str) -> None:
    """Refuse when the accession's filer prefix differs from the canonical CIK.

    The accession format is ``XXXXXXXXXX-YY-ZZZZZZ``; the first segment is the
    zero-padded 10-digit CIK of the filer.  Raises ``IngestionError`` before
    any filing request or write (AC-0401).
    """
    # Use the dashed form; if no dash, reconstruct.
    if "-" in accession:
        filer_prefix = accession.split("-")[0]
    else:
        filer_prefix = accession[:10]
    if _normalize_cik(filer_prefix) != _normalize_cik(required_cik):
        raise IngestionError(
            "accession filer prefix does not match the canonical CIK: "
            "refusing before any filing request"
        )


def _select_filing(
    recent: dict[str, list[Any]],
    as_of_date: str,
    required_accession: str,
) -> dict[str, str]:
    """Select the target filing from the submission metadata parallel arrays.

    Rules (AC-0401, AC-0405):
    - The selected accession must match ``required_accession`` exactly.
    - The filing date must be on or before ``as_of_date`` (compared as dates).
    - The selected form must equal ``CANONICAL_FORM``.
    - The selected ``filingDate`` and ``reportDate`` must be strict ISO calendar
      dates (``\\d{4}-\\d{2}-\\d{2}`` fullmatch + ``date.fromisoformat``).
    - Required arrays must all be lists of equal length; every element must be
      a string.
    - No fallback to a different filing is admitted.
    - Missing required fields or no matching filing fails ingestion.
    """
    required_keys = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument"]
    for key in required_keys:
        if key not in recent:
            raise IngestionError(f"submission metadata missing required field {key!r}")

    # All required fields must be lists.
    for key in required_keys:
        if not isinstance(recent[key], list):
            raise IngestionError(
                f"submission metadata field {key!r} is not an array: "
                "refusing before any filing request"
            )

    # All required arrays must have the same length.
    n = len(recent["accessionNumber"])
    for key in required_keys:
        if len(recent[key]) != n:
            raise IngestionError(
                "submission metadata required arrays have unequal lengths: "
                "refusing before any filing request"
            )

    # Every element of every required array must be a string (shape check
    # before any selection or date parsing).
    for key in required_keys:
        for j, elem in enumerate(recent[key]):
            if not isinstance(elem, str):
                raise IngestionError(
                    f"submission metadata {key!r} element {j} is not a string: "
                    "refusing before any filing request"
                )

    # Parse as_of_date once as a date object for safe calendar comparison.
    as_of = datetime.date.fromisoformat(as_of_date)

    # Normalise accession number: remove dashes for comparison.
    bare_acc = required_accession.replace("-", "")

    matches: list[dict[str, str]] = []

    for i in range(n):
        acc_raw = recent["accessionNumber"][i]  # already validated as str
        # SEC accession numbers come as "0000320193-26-000020" or "000032019326000020".
        acc_bare = acc_raw.replace("-", "")
        if acc_bare != bare_acc:
            continue

        # Validate and parse the filing date as a strict ISO calendar date.
        filing_date_raw = recent["filingDate"][i]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filing_date_raw):
            raise IngestionError(
                f"selected filingDate {filing_date_raw!r} is not a strict ISO calendar date "
                r"(\d{4}-\d{2}-\d{2}): refusing before any filing request"
            )
        try:
            filing_date_obj = datetime.date.fromisoformat(filing_date_raw)
        except ValueError as exc:
            raise IngestionError(
                f"selected filingDate {filing_date_raw!r} is not a valid calendar date: "
                "refusing before any filing request"
            ) from exc

        # Refuse any filing dated after as_of_date (AC-0405) — compared as dates
        # so whitespace, empty strings, or non-canonical orderings cannot bypass the guard.
        if filing_date_obj > as_of:
            raise IngestionError(
                f"selected filing date {filing_date_raw!r} is after the "
                f"requested as-of date {as_of_date!r}: refusing"
            )

        primary_doc = recent["primaryDocument"][i]

        # Validate form: only the canonical form is admitted into the manifest.
        form = recent["form"][i]
        if form != CANONICAL_FORM:
            raise IngestionError(
                f"selected filing form {form!r} is not {CANONICAL_FORM!r}: "
                "refusing before any filing request"
            )

        # Validate and parse the report date as a strict ISO calendar date.
        report_date_raw = recent["reportDate"][i]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date_raw):
            raise IngestionError(
                f"selected reportDate {report_date_raw!r} is not a strict ISO calendar date "
                r"(\d{4}-\d{2}-\d{2}): refusing before any filing request"
            )
        try:
            datetime.date.fromisoformat(report_date_raw)
        except ValueError as exc:
            raise IngestionError(
                f"selected reportDate {report_date_raw!r} is not a valid calendar date: "
                "refusing before any filing request"
            ) from exc

        # Rebuild accession in dashed form if it arrived without dashes.
        if "-" not in acc_raw:
            # Format: XXXXXXXXXX-YY-ZZZZZZ
            acc_dashed = f"{acc_raw[:10]}-{acc_raw[10:12]}-{acc_raw[12:]}"
        else:
            acc_dashed = acc_raw

        matches.append(
            {
                "accession": acc_dashed,
                "filing_date": filing_date_obj.isoformat(),  # normalised ISO calendar date
                "report_date": report_date_raw,
                "form": form,
                "primary_doc": primary_doc,
            }
        )

    if len(matches) == 0:
        raise IngestionError(
            f"accession {required_accession!r} not found in submission metadata"
        )
    if len(matches) > 1:
        raise IngestionError(
            f"accession {required_accession!r} matched {len(matches)} entries in "
            f"submission metadata; refusing ambiguous selection before any filing request"
        )
    return matches[0]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _store_snapshot(
    filing_bytes: bytes,
    cik: str,
    as_of_date: str,
    form: str,
    filing_date: str,
    report_date: str,
    accession: str,
    source_url: str,
) -> tuple[str, str]:
    """Store filing bytes and snapshot manifest; return (filing_ref, snapshot_ref).

    The filing is stored content-addressed by SHA-256 under the snapshot scope.
    The snapshot manifest is stored as canonical JSON, also content-addressed.

    Returns ``(filing_ref, snapshot_ref)`` — the manifest key.
    """
    from ced.adapters.objectstore.client import (
        SNAPSHOT_SCOPE,
        write_payload,
        write_payload_bytes,
    )

    # Store filing bytes.
    filing_ref = write_payload_bytes(filing_bytes, owner_scope=SNAPSHOT_SCOPE)
    filing_sha256 = hashlib.sha256(filing_bytes).hexdigest()

    retrieved_at = datetime.datetime.now(datetime.UTC).isoformat()

    manifest: dict[str, object] = {
        "schema_version": "1",
        "cik": cik,
        "as_of_date": as_of_date,
        "form": form,
        "filing_date": filing_date,
        "report_date": report_date,
        "accession": accession,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "filing_sha256": filing_sha256,
        "filing_ref": filing_ref,
    }
    snapshot_ref = write_payload(manifest, owner_scope=SNAPSHOT_SCOPE)
    return filing_ref, snapshot_ref


# ---------------------------------------------------------------------------
# Round-trip verification
# ---------------------------------------------------------------------------


def _verify_round_trip(filing_ref: str, snapshot_ref: str) -> None:
    """Recompute SHA-256 from stored bytes before parsing either object (AC-0404)."""
    from ced.adapters.objectstore.client import read_payload_bytes

    # Verify filing bytes.
    stored_filing = read_payload_bytes(filing_ref)
    stored_sha256 = hashlib.sha256(stored_filing).hexdigest()
    expected = filing_ref.split("/")[-1]  # last path segment is the sha256 hex
    if stored_sha256 != expected:
        raise IngestionError(
            "filing round-trip digest mismatch: stored bytes do not match "
            "the SHA-256 encoded in the filing object reference"
        )

    # Verify snapshot manifest bytes match the key.
    from ced.adapters.objectstore.client import read_payload_bytes as rpb

    snap_bytes = rpb(snapshot_ref)
    snap_sha256 = hashlib.sha256(snap_bytes).hexdigest()
    snap_expected = snapshot_ref.split("/")[-1]
    if snap_sha256 != snap_expected:
        raise IngestionError(
            "snapshot round-trip digest mismatch: stored bytes do not match "
            "the SHA-256 encoded in the snapshot object reference"
        )

    # Parse the manifest and verify internal digest field.
    snap_manifest = json.loads(snap_bytes)
    if snap_manifest.get("filing_sha256") != stored_sha256:
        raise IngestionError(
            "snapshot manifest filing_sha256 disagrees with the stored filing digest"
        )


# ---------------------------------------------------------------------------
# Public ingest function
# ---------------------------------------------------------------------------


def ingest(
    *,
    offline: bool = False,
    gate_factory: Any = None,
) -> dict[str, str]:
    """Run ingestion; return the result dict printed to stdout.

    Parameters
    ----------
    offline:
        When True, reads from the committed fixture files instead of the SEC.
    gate_factory:
        Callable returning a rate gate context manager; defaults to the
        Postgres gate in live mode.
    """
    if offline:
        return _ingest_offline()
    else:
        return _ingest_live(gate_factory=gate_factory)


def _ingest_offline() -> dict[str, str]:
    """Read from committed fixture files; validate selection; store snapshot."""
    # Read fixture files.  The fixtures live in the source tree and are not
    # installed with the package; refuse with a path-free message so the
    # absolute source-tree path does not appear in any error output.
    try:
        submissions_bytes = _FIXTURE_JSON.read_bytes()
    except OSError as exc:
        raise IngestionError(
            "--offline-fixture needs a source checkout; "
            "the fixture is not installed with the package"
        ) from exc
    try:
        filing_bytes = _FIXTURE_HTML.read_bytes()
    except OSError as exc:
        raise IngestionError(
            "--offline-fixture needs a source checkout; "
            "the fixture is not installed with the package"
        ) from exc

    return _run_ingest_from_bytes(submissions_bytes, filing_bytes)


def _ingest_live(
    *,
    gate_factory: Any = None,
    resolve: Any = None,
    open_socket: Any = None,
    wrap: Any = None,
) -> dict[str, str]:
    """Fetch from SEC, validate selection, store snapshot.

    Returns the result dict including ``"attempts"`` (list of redacted
    ``AttemptRecord`` dicts, one per SEC request made).  Raises
    ``IngestionError`` for validation failures or ``SecClientError`` for
    transport/configuration failures; in both cases the caller can inspect
    ``attempt_records`` on the raised exception when set.
    """
    from ced.adapters.postgres.dsn import database_url
    from ced.adapters.sec.client import (
        SecClientError,
        acquire_contact,
        fetch_filing,
        fetch_submissions,
        open_postgres_gate,
    )

    contact = acquire_contact()

    dsn = database_url("worker")

    if gate_factory is None:

        def gate_factory() -> Any:
            return open_postgres_gate(dsn)

    attempt_records: list[dict[str, object]] = []

    try:
        # Fetch submissions.
        submissions_bytes, sub_record = fetch_submissions(
            CANONICAL_CIK,
            contact,
            gate_factory(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
        attempt_records.append(sub_record.to_dict())

        # Parse and select filing.
        try:
            submissions = json.loads(submissions_bytes)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"submissions JSON is not valid: {exc}") from exc

        # Refuse a submissions document that is not a JSON object.
        if not isinstance(submissions, dict):
            raise IngestionError(
                "submissions document is not a JSON object: refusing before any filing request"
            )

        # Refuse submissions whose CIK disagrees with the canonical CIK (AC-0401).
        _validate_submissions_cik(submissions, CANONICAL_CIK)

        # Refuse a missing or non-object 'filings' or 'filings.recent'.
        filings = submissions.get("filings")
        if not isinstance(filings, dict):
            raise IngestionError(
                "submissions 'filings' field is missing or not a JSON object: "
                "refusing before any filing request"
            )
        recent = filings.get("recent")
        if not isinstance(recent, dict):
            raise IngestionError(
                "submissions 'filings.recent' field is missing or not a JSON object: "
                "refusing before any filing request"
            )
        filing_info = _select_filing(recent, CANONICAL_AS_OF, CANONICAL_ACCESSION)

        # Refuse if the selected accession's filer prefix does not match (AC-0401).
        _validate_accession_filer_prefix(filing_info["accession"], CANONICAL_CIK)

        primary_doc = _validate_primary_doc(filing_info["primary_doc"])

        # Validate the primary document matches the canonical one.
        if primary_doc != CANONICAL_PRIMARY_DOC:
            raise IngestionError(
                f"primary document from submissions {primary_doc!r} does not match "
                f"the canonical {CANONICAL_PRIMARY_DOC!r}: refusing"
            )

        # Fetch the filing.
        filing_bytes, fil_record = fetch_filing(
            CANONICAL_SOURCE_URL,
            contact,
            gate_factory(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
        attempt_records.append(fil_record.to_dict())

    except (IngestionError, SecClientError) as exc:
        # If a SecClientError carries its own attempt_record (singular), include it.
        single = getattr(exc, "attempt_record", None)
        if single is not None and single.to_dict() not in attempt_records:
            attempt_records.append(single.to_dict())
        # Attach the gathered list so the CLI can emit it before the error line.
        # attempt_records is a dynamic field added only on the live path; both
        # IngestionError and SecClientError allow __dict__ assignment.
        exc.attempt_records = attempt_records  # type: ignore[union-attr]
        raise

    result = _store_and_return(
        filing_bytes=filing_bytes,
        filing_info=filing_info,
    )
    result["attempts"] = attempt_records  # type: ignore[assignment]
    return result


def _run_ingest_from_bytes(
    submissions_bytes: bytes,
    filing_bytes: bytes,
) -> dict[str, str]:
    """Parse, select, validate, and store from already-fetched bytes."""
    # Parse submissions.
    try:
        submissions = json.loads(submissions_bytes)
    except json.JSONDecodeError as exc:
        raise IngestionError(f"submissions JSON is not valid: {exc}") from exc

    # Refuse a submissions document that is not a JSON object.
    if not isinstance(submissions, dict):
        raise IngestionError(
            "submissions document is not a JSON object: refusing before any filing request"
        )

    # Refuse submissions whose CIK disagrees with the canonical CIK (AC-0401).
    _validate_submissions_cik(submissions, CANONICAL_CIK)

    # Refuse a missing or non-object 'filings' or 'filings.recent'.
    filings = submissions.get("filings")
    if not isinstance(filings, dict):
        raise IngestionError(
            "submissions 'filings' field is missing or not a JSON object: "
            "refusing before any filing request"
        )
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        raise IngestionError(
            "submissions 'filings.recent' field is missing or not a JSON object: "
            "refusing before any filing request"
        )
    filing_info = _select_filing(recent, CANONICAL_AS_OF, CANONICAL_ACCESSION)

    # Refuse if the selected accession's filer prefix does not match (AC-0401).
    _validate_accession_filer_prefix(filing_info["accession"], CANONICAL_CIK)

    _validate_primary_doc(filing_info["primary_doc"])

    return _store_and_return(
        filing_bytes=filing_bytes,
        filing_info=filing_info,
    )


def _store_and_return(
    *,
    filing_bytes: bytes,
    filing_info: dict[str, str],
) -> dict[str, str]:
    """Store bytes and manifest; verify round-trip; return result dict."""
    filing_ref, snapshot_ref = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form=filing_info["form"],
        filing_date=filing_info["filing_date"],
        report_date=filing_info.get("report_date", ""),
        accession=filing_info["accession"],
        source_url=CANONICAL_SOURCE_URL,
    )

    _verify_round_trip(filing_ref, snapshot_ref)

    return {
        "snapshot_ref": snapshot_ref,
        "filing_ref": filing_ref,
        "cik": CANONICAL_CIK,
        "accession": filing_info["accession"],
        "form": filing_info["form"],
        "filing_date": filing_info["filing_date"],
        "as_of_date": CANONICAL_AS_OF,
    }


# ---------------------------------------------------------------------------
# Observation command
# ---------------------------------------------------------------------------


def _cmd_observe(args: argparse.Namespace) -> int:
    """Run the bounded SEC observation and write the result record."""
    from ced.adapters.postgres.dsn import database_url
    from ced.adapters.sec.client import (
        SecClientError,
        acquire_contact,
        open_postgres_gate,
        run_observation,
    )

    try:
        contact = acquire_contact()
    except SecClientError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    dsn = database_url("worker")

    def gate_factory() -> Any:
        return open_postgres_gate(dsn)

    try:
        record = run_observation(
            contact,
            gate_factory,
            n_attempts=60,
            interval_seconds=1.0,
        )
    except SecClientError as exc:
        sys.stderr.write(f"error: observation failed: {exc}\n")
        return 1

    output = json.dumps(record, indent=2)
    sys.stdout.write(output + "\n")

    out: str | None = getattr(args, "out", None)
    if out:
        _write_record(out, record)
        sys.stderr.write(f"written to {out}\n")

    return 0


def _write_record(out_path: str, payload: dict[str, object]) -> None:
    """Write or merge a JSON record atomically (same pattern as ced-evidence)."""
    existing: dict[str, object] = {}
    if os.path.exists(out_path):
        try:
            with open(out_path) as f:
                loaded = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{out_path}: cannot read: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"{out_path}: expected a JSON object")
        existing = loaded

    existing.update(payload)
    dir_path = os.path.dirname(os.path.abspath(out_path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(existing, indent=2) + "\n")
        os.replace(tmp_path, out_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run() -> None:
    """``ced-ingest`` console-script entry point."""
    parser = argparse.ArgumentParser(
        prog="ced-ingest",
        description="Bounded SEC ingestion — stores one immutable evidence snapshot.",
    )
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help=(
            "Read from the committed fixture files instead of fetching from SEC. "
            "No network call; no SEC_CONTACT required."
        ),
    )

    sub = parser.add_subparsers(dest="cmd")
    obs_p = sub.add_parser(
        "observe",
        help="Run the bounded 60-attempt SEC observation (requires SEC_CONTACT).",
    )
    obs_p.add_argument(
        "--out",
        metavar="PATH",
        help="Write observation JSON to PATH (creates or merges).",
    )

    args = parser.parse_args()

    if args.cmd == "observe":
        sys.exit(_cmd_observe(args))

    # Default: ingest mode.
    from ced.adapters.sec.client import SecClientError

    try:
        result = ingest(offline=args.offline_fixture)
    except (IngestionError, SecClientError) as exc:
        # On live failures the exception may carry attempt records gathered
        # before the failure; write them as one JSON line before the message.
        attempt_records: list[dict[str, object]] | None = getattr(exc, "attempt_records", None)
        if attempt_records:
            sys.stderr.write(json.dumps({"attempts": attempt_records}) + "\n")
        # The message must never contain the contact value; the contact is
        # never included in IngestionError or SecClientError messages.
        sys.stderr.write(f"error: {exc}\n")
        sys.exit(1)

    sys.stdout.write(json.dumps(result) + "\n")
    sys.exit(0)
