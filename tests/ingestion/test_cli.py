"""CLI-level tests for ``ced-ingest`` — findings 3 and 7.

Tests run offline (no substrate, no network).  Each guard earns a named
mutation red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ced.adapters.sec.client import SecClientError, _fake_gate
from ced.worker.ingestion import (
    IngestionError,
    _ingest_live,
    run,
)
from tests.ingestion.fixture import FakeSocket, make_http_response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "first_published_analysis.json"
)
_FIXTURE_HTML = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "first_published_analysis.html"
)

_CONTACT = "test-cli-fictional@example.com"

_OK_SUBMISSIONS = make_http_response(200, {}, _FIXTURE_JSON.read_bytes())
_OK_FILING = make_http_response(200, {}, _FIXTURE_HTML.read_bytes())


def _make_gate_factory(clock: Any = None) -> Any:
    def factory() -> Any:
        return _fake_gate(clock=clock)

    return factory


def _make_two_response_seam() -> tuple[Any, Any, Any]:
    """Build a seam that serves the submissions response then the filing response."""
    responses = [_OK_SUBMISSIONS, _OK_FILING]
    call_count = [0]

    def resolve(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        import socket as _socket

        return [(_socket.AF_INET, _socket.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_socket(address: Any, timeout: Any = None) -> Any:
        idx = call_count[0]
        call_count[0] += 1
        return FakeSocket(responses[idx % len(responses)])

    def wrap(sock: Any, server_hostname: str | None = None) -> Any:
        return sock

    return resolve, open_socket, wrap


# ---------------------------------------------------------------------------
# Finding 7 (advisory): run() catches SecClientError and emits error: line
# ---------------------------------------------------------------------------


def test_run_catches_sec_client_error_and_writes_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``run()`` converts a SecClientError to ``error: <msg>`` on stderr, exit 1.

    Before this fix a SecClientError from live ingestion (e.g. missing
    SEC_CONTACT, DNS failure) would propagate as an unhandled exception and
    produce a full traceback instead of a one-line error.

    Mutation: remove the ``SecClientError`` branch from the ``run()`` catch block
    → the error is a traceback, not an ``error:`` line, and the test fails on
    the stderr assertion.
    """
    # Use offline mode to avoid a real SEC call; force a SecClientError by
    # patching ingest() to raise one.
    monkeypatch.setattr(
        "ced.worker.ingestion.ingest",
        lambda **kw: (_ for _ in ()).throw(
            SecClientError("SEC_CONTACT is unset or blank; set it to the declared User-Agent")
        ),
    )

    monkeypatch.setattr(sys, "argv", ["ced-ingest"])

    with pytest.raises(SystemExit) as exc_info:
        run()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: "), (
        f"stderr must start with 'error: '; got: {captured.err!r}"
    )
    assert not captured.out, "no JSON must be written to stdout on failure"


def test_run_writes_sec_client_error_message_without_contact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The contact value must not appear in the stderr error line.

    Mutation: include ``contact`` in the SecClientError message → MARKER
    appears in stderr and the assertion fails.
    """
    contact_marker = "FICTIONAL-CLI-CONTACT-MARKER@example.com"

    # Raise a SecClientError that does NOT contain the contact (as the code
    # must ensure).  The test verifies the CLI also does not add it.
    err = SecClientError("configuration error (contact value redacted)")
    monkeypatch.setattr(
        "ced.worker.ingestion.ingest",
        lambda **kw: (_ for _ in ()).throw(err),
    )
    monkeypatch.setenv("SEC_CONTACT", contact_marker)
    monkeypatch.setattr(sys, "argv", ["ced-ingest"])

    with pytest.raises(SystemExit):
        run()

    captured = capsys.readouterr()
    assert contact_marker not in captured.err, (
        "contact value must not appear in the stderr error line"
    )


# ---------------------------------------------------------------------------
# Finding 3 (AC-0401): command-level test for unsupported CIK via run()
# ---------------------------------------------------------------------------


def test_run_offline_refuses_wrong_submissions_cik(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """``run()`` with ``--offline-fixture`` refuses a wrong submissions CIK.

    The refusal must produce zero object writes (tested indirectly — if ingest
    succeeds, stdout would have JSON; a refusal means only stderr output).

    Mutation: remove ``_validate_submissions_cik`` → wrong CIK is not detected
    and stdout would have a JSON result instead of an error line.
    """
    import ced.worker.ingestion as ingestion_module

    # Build a submissions fixture with a wrong CIK.
    submissions = json.loads(_FIXTURE_JSON.read_bytes())
    submissions["cik"] = "9999999999"
    bad_json = json.dumps(submissions).encode()

    # Patch the fixture path to a temp file with the wrong CIK.
    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_bytes(bad_json)

    monkeypatch.setattr(ingestion_module, "_FIXTURE_JSON", bad_json_path)
    monkeypatch.setattr(ingestion_module, "_FIXTURE_HTML", _FIXTURE_HTML)
    monkeypatch.setattr(sys, "argv", ["ced-ingest", "--offline-fixture"])

    with pytest.raises(SystemExit) as exc_info:
        run()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err, f"expected error line; got stderr={captured.err!r}"
    assert not captured.out, "no JSON must be written on a CIK refusal"


# ---------------------------------------------------------------------------
# Finding 7: live ingestion includes attempts in printed JSON on success
# ---------------------------------------------------------------------------


def test_ingest_live_includes_attempts_in_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_ingest_live`` returns an ``'attempts'`` list with two records on success.

    Before this fix ``_sub_record`` and ``_fil_record`` were discarded.

    Mutation: remove ``result['attempts'] = attempt_records`` → the key is
    absent and the assertion fails.
    """
    monkeypatch.setenv("SEC_CONTACT", _CONTACT)

    # Patch database_url to avoid needing the substrate (imported lazily in _ingest_live).
    monkeypatch.setattr("ced.adapters.postgres.dsn.database_url", lambda role: "unused-dsn")

    # Patch write_payload_bytes and write_payload to avoid MinIO.
    from ced.adapters.objectstore import client as obj_client

    monkeypatch.setattr(
        obj_client, "write_payload_bytes", lambda b, **kw: f"snap/{b[:4].hex()}"
    )
    monkeypatch.setattr(obj_client, "write_payload", lambda d, **kw: "snap/abc123")
    monkeypatch.setattr("ced.worker.ingestion._verify_round_trip", lambda fr, sr: None)

    resolve, open_socket, wrap = _make_two_response_seam()

    result = _ingest_live(
        gate_factory=_make_gate_factory(),
        resolve=resolve,
        open_socket=open_socket,
        wrap=wrap,
    )

    assert "attempts" in result, "live ingest result must include 'attempts'"
    attempts = result["attempts"]
    assert isinstance(attempts, list), "'attempts' must be a list"
    assert len(attempts) == 2, (
        f"expected two attempt records (submissions + filing), got {len(attempts)}"
    )
    for rec in attempts:
        assert "request_class" in rec
        assert "stop_condition" in rec


# ---------------------------------------------------------------------------
# AC-0401 / AC-0405: a metadata refusal on the live path makes no filing
# request and no object write
# ---------------------------------------------------------------------------


def _submissions_with(**changes: Any) -> bytes:
    """Return the fixture submissions document with top-level or recent-array edits."""
    doc = json.loads(_FIXTURE_JSON.read_bytes())
    recent = doc["filings"]["recent"]
    for key, value in changes.items():
        if key in recent:
            recent[key] = value
        else:
            doc[key] = value
    return json.dumps(doc).encode()


def _duplicate_canonical_entry() -> dict[str, Any]:
    """Recent arrays with the canonical accession listed twice."""
    recent = json.loads(_FIXTURE_JSON.read_bytes())["filings"]["recent"]
    index = recent["accessionNumber"].index("0000320193-26-000020")
    return {key: values + [values[index]] for key, values in recent.items()}


@pytest.mark.parametrize(
    "submissions",
    [
        pytest.param(_submissions_with(cik="789019"), id="other-company-cik"),
        pytest.param(
            _submissions_with(**_duplicate_canonical_entry()), id="duplicate-accession"
        ),
    ],
)
def test_a_live_metadata_refusal_makes_no_filing_request_and_no_write(
    monkeypatch: pytest.MonkeyPatch, submissions: bytes
) -> None:
    """Refusals decided from submission metadata stop before the filing fetch.

    The seam counts socket opens, so a filing request would be a second open.
    The store spy records every write. Mutation: drop the submissions CIK check,
    or restore the first-match ``break`` in ``_select_filing``. Its case then
    reaches the filing request, and this check reds.
    """
    monkeypatch.setenv("SEC_CONTACT", _CONTACT)
    monkeypatch.setattr("ced.adapters.postgres.dsn.database_url", lambda role: "unused-dsn")
    from ced.adapters.objectstore import client as obj_client

    writes: list[str] = []
    monkeypatch.setattr(
        obj_client, "write_payload_bytes", lambda b, **kw: writes.append("bytes")
    )
    monkeypatch.setattr(obj_client, "write_payload", lambda d, **kw: writes.append("json"))

    opens: list[Any] = []
    response = make_http_response(200, {}, submissions)

    def resolve(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        import socket as _socket

        return [(_socket.AF_INET, _socket.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_socket(address: Any, timeout: Any = None) -> Any:
        opens.append(address)
        return FakeSocket(response)

    with pytest.raises(IngestionError):
        _ingest_live(
            gate_factory=_make_gate_factory(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=lambda sock, server_hostname=None: sock,
        )

    assert len(opens) == 1, f"only the submissions request may be made; saw {len(opens)}"
    assert writes == [], f"no object may be written; saw {writes}"
