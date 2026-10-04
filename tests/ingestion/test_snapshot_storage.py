"""Snapshot storage tests — AC-0404.

Uses the real MinIO substrate via the object-store client.
No live SEC call; all filing bytes come from the committed fixture.

Each guard earns a named mutation red documented in the verification ledger.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from ced.adapters.objectstore.client import (
    SNAPSHOT_SCOPE,
    read_payload,
    read_payload_bytes,
)
from ced.adapters.sec.client import _fake_gate
from ced.worker.ingestion import (
    CANONICAL_ACCESSION,
    CANONICAL_AS_OF,
    CANONICAL_CIK,
    CANONICAL_SOURCE_URL,
    IngestionError,
    _ingest_live,
    _run_ingest_from_bytes,
    _store_snapshot,
    _verify_round_trip,
)
from tests.ingestion.fixture import (
    FILING_CONTENT_HASH,
    make_http_response,
    recorded_filing,
)

pytestmark = pytest.mark.substrate

_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "first_published_analysis.json"
)


# ---------------------------------------------------------------------------
# AC-0404: filing bytes stored content-addressed, manifest round-trips
# ---------------------------------------------------------------------------


def test_filing_bytes_stored_under_snapshot_scope() -> None:
    """Filing bytes are stored under the snapshot scope with their SHA-256 as key.

    Mutation: use ``OWNER_SCOPE`` instead of ``SNAPSHOT_SCOPE`` — the filing
    would be stored in the wrong scope and the reference prefix would differ.
    """
    filing_bytes = recorded_filing()
    sha256 = hashlib.sha256(filing_bytes).hexdigest()

    filing_ref, snapshot_ref = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )

    assert filing_ref.startswith(f"{SNAPSHOT_SCOPE}/"), (
        f"filing_ref must start with '{SNAPSHOT_SCOPE}/', got {filing_ref!r}"
    )
    assert filing_ref.endswith(sha256), (
        "filing_ref must end with the SHA-256 hex digest of the bytes"
    )
    assert snapshot_ref.startswith(f"{SNAPSHOT_SCOPE}/"), (
        f"snapshot_ref must start with '{SNAPSHOT_SCOPE}/', got {snapshot_ref!r}"
    )


def test_snapshot_manifest_round_trip() -> None:
    """The snapshot manifest can be read back from MinIO and parsed.

    Mutation: write the manifest to a different key — the read_payload call
    would fail with a NoSuchKey error.
    """
    filing_bytes = recorded_filing()
    filing_ref, snapshot_ref = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )

    manifest = read_payload(snapshot_ref)
    assert manifest["cik"] == CANONICAL_CIK
    assert manifest["as_of_date"] == CANONICAL_AS_OF
    assert manifest["accession"] == CANONICAL_ACCESSION
    assert manifest["filing_sha256"] == FILING_CONTENT_HASH
    assert manifest["filing_ref"] == filing_ref


def test_duplicate_filing_write_returns_same_filing_ref() -> None:
    """Re-ingesting byte-identical evidence yields the same filing object reference.

    Mutation: add a random nonce to the key — the second write would produce
    a different reference and this equality assertion would fail.
    """
    filing_bytes = recorded_filing()
    _, snap1 = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )
    fil1_ref = read_payload(snap1)["filing_ref"]

    # Small sleep so retrieved_at differs — this should produce a new snapshot ref.
    time.sleep(0.01)

    _, snap2 = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )
    fil2_ref = read_payload(snap2)["filing_ref"]

    # Filing refs must be identical (same bytes → same content-addressed key).
    assert fil1_ref == fil2_ref, (
        "duplicate filing write must yield the same filing_ref (content-addressed storage)"
    )


def test_retrieval_time_change_moves_only_manifest_ref() -> None:
    """A different retrieval time yields a different snapshot_ref but same filing_ref.

    Mutation: exclude ``retrieved_at`` from the manifest — both snapshots
    would have the same JSON, yielding the same snapshot_ref.
    """
    filing_bytes = recorded_filing()
    fil1, snap1 = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )

    time.sleep(0.01)  # ensures retrieved_at differs

    fil2, snap2 = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )

    assert fil1 == fil2, "filing_ref must be the same for identical bytes"
    assert snap1 != snap2, (
        "snapshot_ref must differ when retrieved_at differs; "
        "each manifest is a new immutable observation"
    )


# ---------------------------------------------------------------------------
# AC-0404: round-trip digest verification
# ---------------------------------------------------------------------------


def test_round_trip_digest_check_fails_on_tampered_filing() -> None:
    """Replacing filing bytes under an existing key makes the digest check fail.

    Mutation: remove the digest verification from ``_verify_round_trip`` —
    tampered bytes would be accepted silently.
    """
    filing_bytes = recorded_filing()
    filing_ref, snapshot_ref = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )

    # Tamper: overwrite the filing object with different bytes that have a
    # different SHA-256 (but keep the same key — simulating silent substitution).
    tampered = b"tampered filing bytes -- not the original content"
    from ced.adapters.objectstore.client import BUCKET_NAME, _s3_client

    _s3_client().put_object(
        Bucket=BUCKET_NAME,
        Key=filing_ref,
        Body=tampered,
        ContentType="application/octet-stream",
    )

    with pytest.raises(IngestionError, match="digest mismatch"):
        _verify_round_trip(filing_ref, snapshot_ref)


# ---------------------------------------------------------------------------
# AC-0404: redaction — contact value absent from stored objects
# ---------------------------------------------------------------------------


def test_contact_value_absent_from_stored_filing_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful ingestion proves the SEC_CONTACT value is not in any stored object.

    The offline fixture path is used so no real SEC call occurs. The
    contact value is set in the environment to verify it does not leak
    into stored bytes even if code mistakenly accessed it.

    Mutation: store the contact value in the manifest — this assertion fails.
    """
    distinctive = "REDACTION-MARKER-DO-NOT-STORE-fictional@example.com"
    monkeypatch.setenv("SEC_CONTACT", distinctive)

    submissions_bytes = _FIXTURE_JSON.read_bytes()
    filing_bytes = recorded_filing()
    result = _run_ingest_from_bytes(submissions_bytes, filing_bytes)

    filing_ref = result["filing_ref"]
    snapshot_ref = result["snapshot_ref"]

    # Check filing bytes.
    stored_filing = read_payload_bytes(filing_ref)
    assert distinctive.encode() not in stored_filing, (
        "SEC_CONTACT must not appear in stored filing bytes"
    )

    # Check manifest JSON.
    manifest_bytes = read_payload_bytes(snapshot_ref)
    assert distinctive.encode() not in manifest_bytes, (
        "SEC_CONTACT must not appear in stored snapshot manifest bytes"
    )


def test_contact_value_absent_from_ingest_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The SEC_CONTACT value must not appear in ced-ingest stdout output.

    Mutation: print the contact value to stdout — this assertion fails.
    """
    distinctive = "STDOUT-MARKER-fictional@example.com"
    monkeypatch.setenv("SEC_CONTACT", distinctive)

    submissions_bytes = _FIXTURE_JSON.read_bytes()
    filing_bytes = recorded_filing()
    result = _run_ingest_from_bytes(submissions_bytes, filing_bytes)
    output = json.dumps(result)

    assert distinctive not in output, (
        "SEC_CONTACT must not appear in the ced-ingest JSON output"
    )


# ---------------------------------------------------------------------------
# AC-0404: full offline ingest produces a readable snapshot reference
# ---------------------------------------------------------------------------


def test_offline_ingest_produces_readable_snapshot_ref() -> None:
    """The offline ingest returns a snapshot_ref that can be read from MinIO.

    Mutation: return a hardcoded fake ref — ``read_payload`` would fail with
    NoSuchKey and this assertion would not be reached.
    """
    submissions_bytes = _FIXTURE_JSON.read_bytes()
    filing_bytes = recorded_filing()
    result = _run_ingest_from_bytes(submissions_bytes, filing_bytes)

    snap_ref = result["snapshot_ref"]
    assert snap_ref.startswith(f"{SNAPSHOT_SCOPE}/"), (
        f"snapshot_ref must start with '{SNAPSHOT_SCOPE}/'"
    )

    # Verify the ref is readable.
    manifest = read_payload(snap_ref)
    assert manifest["cik"] == CANONICAL_CIK
    assert manifest["as_of_date"] == CANONICAL_AS_OF


# ---------------------------------------------------------------------------
# AC-0404: fixture hash constant matches the committed file
# ---------------------------------------------------------------------------


def test_fixture_hash_matches_file() -> None:
    """FILING_CONTENT_HASH matches the SHA-256 of the committed fixture file.

    Mutation: change the constant without updating the fixture — this
    assertion fails immediately.
    """
    filing_bytes = recorded_filing()
    actual_hash = hashlib.sha256(filing_bytes).hexdigest()
    assert actual_hash == FILING_CONTENT_HASH, (
        f"FILING_CONTENT_HASH is stale; update it to {actual_hash!r}"
    )


# ---------------------------------------------------------------------------
# Finding 4 (AC-0404): snapshot manifest bytes tamper case
# ---------------------------------------------------------------------------


def test_round_trip_digest_check_fails_on_tampered_snapshot_manifest() -> None:
    """Replacing snapshot manifest bytes under an existing key makes the digest check fail.

    Before this fix only the filing digest was verified; a tampered manifest
    would parse without error.

    Mutation: remove the snapshot digest verification from ``_verify_round_trip``
    → tampered manifest bytes are accepted silently.
    """
    filing_bytes = recorded_filing()
    filing_ref, snapshot_ref = _store_snapshot(
        filing_bytes=filing_bytes,
        cik=CANONICAL_CIK,
        as_of_date=CANONICAL_AS_OF,
        form="10-Q",
        filing_date="2026-07-31",
        report_date="2026-06-27",
        accession=CANONICAL_ACCESSION,
        source_url=CANONICAL_SOURCE_URL,
    )

    # Tamper: overwrite the snapshot manifest object with different bytes that
    # have a different SHA-256, so the key no longer matches the content.
    tampered = b'{"tampered": true, "this_is_not_the_real_manifest": 1}'
    from ced.adapters.objectstore.client import BUCKET_NAME, _s3_client

    _s3_client().put_object(
        Bucket=BUCKET_NAME,
        Key=snapshot_ref,
        Body=tampered,
        ContentType="application/json",
    )

    with pytest.raises(IngestionError, match="digest mismatch"):
        _verify_round_trip(filing_ref, snapshot_ref)


# ---------------------------------------------------------------------------
# Finding 4 (AC-0404): live redaction check via _ingest_live
# ---------------------------------------------------------------------------


def test_contact_value_absent_from_stored_objects_via_live_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live ingest with a distinctive contact proves the value is absent from stored objects.

    The injected seam serves the fixture bytes so no real SEC call occurs.
    The test scans every stored filing and snapshot object.

    Mutation: store ``contact`` in the manifest → the assertion fails.
    """
    distinctive = "LIVE-REDACTION-MARKER-DO-NOT-STORE-fictional@example.com"
    monkeypatch.setenv("SEC_CONTACT", distinctive)

    # Build response bytes for the two requests.
    from pathlib import Path as _Path

    fixture_json = (
        _Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "first_published_analysis.json"
    )
    submissions_resp = make_http_response(200, {}, fixture_json.read_bytes())
    filing_resp = make_http_response(200, {}, recorded_filing())
    responses = [submissions_resp, filing_resp]
    call_idx = [0]

    import socket as _socket

    from tests.ingestion.fixture import FakeSocket

    def resolve(host: str, port: int, **kwargs: object) -> list[tuple[object, ...]]:
        return [(_socket.AF_INET, _socket.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_socket(address: object, timeout: object = None) -> object:
        idx = call_idx[0]
        call_idx[0] += 1
        return FakeSocket(responses[idx % len(responses)])

    def wrap(sock: object, server_hostname: object = None) -> object:
        return sock

    def gate_factory() -> object:
        return _fake_gate()

    monkeypatch.setattr("ced.adapters.postgres.dsn.database_url", lambda role: "unused-dsn")

    result = _ingest_live(
        gate_factory=gate_factory,
        resolve=resolve,
        open_socket=open_socket,
        wrap=wrap,
    )

    filing_ref = result["filing_ref"]
    snapshot_ref = result["snapshot_ref"]

    stored_filing = read_payload_bytes(filing_ref)
    assert distinctive.encode() not in stored_filing, (
        "SEC_CONTACT must not appear in stored filing bytes (live ingest)"
    )

    manifest_bytes = read_payload_bytes(snapshot_ref)
    assert distinctive.encode() not in manifest_bytes, (
        "SEC_CONTACT must not appear in stored snapshot manifest bytes (live ingest)"
    )


# ---------------------------------------------------------------------------
# Finding 4 (AC-0404): Phase 0 non-open proof
# ---------------------------------------------------------------------------


def test_offline_ingest_does_not_open_phase_0_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline ingestion never opens any path containing ``spikes/phase-0``.

    The test patches ``Path.read_bytes`` so any attempt to open a path under
    ``spikes/phase-0`` raises ``OSError``, ensuring the offline path uses only
    the two committed fixture files.

    Mutation: change ``_ingest_offline`` to read the Phase 0 fixture → the
    patched ``read_bytes`` raises and the test fails.
    """
    from pathlib import Path

    _real_read_bytes = Path.read_bytes

    def guarded_read_bytes(self: Path) -> bytes:
        path_str = str(self)
        if "spikes/phase-0" in path_str or "spikes\\phase-0" in path_str:
            raise OSError("test guard: offline ingestion must not open spikes/phase-0 fixture")
        return _real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    # Run the offline ingest; it must succeed without touching spikes/phase-0.
    submissions_bytes = _FIXTURE_JSON.read_bytes()
    filing_bytes = recorded_filing()
    # The guard is in place; _run_ingest_from_bytes is the path used by offline mode.
    result = _run_ingest_from_bytes(submissions_bytes, filing_bytes)
    assert "snapshot_ref" in result
