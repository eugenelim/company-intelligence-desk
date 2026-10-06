"""AC-0001 — a run starts over HTTP and is readable in state `requested`."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import psycopg
import pytest

from ced.adapters.objectstore.client import (
    BUCKET_NAME,
    OWNER_SCOPE,
    SNAPSHOT_SCOPE,
    ObjectStoreError,
    write_payload_bytes,
)
from ced.adapters.postgres.event_log import read_events
from ced.api.models import ATTRIBUTION_MAX_LENGTH

from .conftest import Client

pytestmark = pytest.mark.substrate


def test_post_runs_returns_an_identifier_and_the_run_is_readable(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0001, end to end over the wire."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})

    assert created.status == 201, created.body
    run_id = created.body["run_id"]
    assert uuid.UUID(run_id)
    assert created.body["seq"] == 1

    snapshot = api_server.get(f"/runs/{run_id}/snapshot")

    assert snapshot.status == 200, snapshot.body
    assert snapshot.body["state"] == "requested"
    assert snapshot.body["run_id"] == run_id
    assert snapshot.body["as_of_seq"] == 1


def test_the_run_requested_event_is_readable_with_the_envelope_r7_specifies(
    api_server: Client, clean_runs: None
) -> None:
    """The event log is the system of record; the snapshot projects over it."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    page = api_server.get(f"/runs/{run_id}/events")

    assert page.status == 200, page.body
    assert page.body["run_id"] == run_id
    assert len(page.body["events"]) == 1
    event = page.body["events"][0]
    assert event["type"] == "run.requested"
    assert event["seq"] == 1
    assert event["principal"] == "operator"
    assert event["schema_version"] == 1
    # Null on the run-lifecycle path, per the r7 envelope: the event is
    # appended before any step is leased.
    assert event["step_id"] is None
    assert event["agent_role"] is None


def test_the_coordinator_step_exists_and_is_runnable(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """A run with no coordinator step is a run nothing will ever claim."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})

    row = owner_conn.execute(
        "SELECT step_id, state, agent_role, pool_class FROM steps WHERE run_id = %s",
        (uuid.UUID(created.body["run_id"]),),
    ).fetchall()

    assert len(row) == 1
    step_id, state, agent_role, pool_class = row[0]
    assert str(step_id) == created.body["step_id"]
    assert state == "runnable"
    assert agent_role == "coordinator"
    # r7 change 3: one class in MVP, so the claim predicate is a no-op until
    # the day it is not.
    assert pool_class == "default"


def test_the_cursor_is_the_clients_and_after_is_honoured(
    api_server: Client, clean_runs: None
) -> None:
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    assert api_server.get(f"/runs/{run_id}/events?after=0").body["events"]
    assert api_server.get(f"/runs/{run_id}/events?after=1").body["events"] == []


def test_an_unknown_run_is_404_not_an_empty_page(api_server: Client) -> None:
    """An empty page would read as "this run has no events yet", which is a
    different fact from "there is no such run"."""
    missing = uuid.uuid4()

    assert api_server.get(f"/runs/{missing}/snapshot").status == 404
    assert api_server.get(f"/runs/{missing}/events").status == 404


def test_a_malformed_body_is_refused(
    api_server: Client, owner_conn: psycopg.Connection
) -> None:
    """422, per the contract, and no run is created.

    The second clause is asserted rather than stated. It was stated only, in a
    suite whose standard is recording what a check does not establish.
    """
    before = owner_conn.execute("SELECT count(*) FROM runs").fetchone()

    assert api_server.post("/runs", {"principal": ""}).status == 422
    assert api_server.post("/runs", {}).status == 422

    assert owner_conn.execute("SELECT count(*) FROM runs").fetchone() == before


def test_a_malformed_run_id_is_refused_rather_than_looked_up(
    api_server: Client,
) -> None:
    assert api_server.get("/runs/not-a-uuid/snapshot").status == 422


def test_an_out_of_range_cursor_is_refused(api_server: Client, clean_runs: None) -> None:
    """The contract bounds `after` and `limit`; the served routes must too."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    assert api_server.get(f"/runs/{run_id}/events?after=-1").status == 422
    assert api_server.get(f"/runs/{run_id}/events?limit=0").status == 422
    assert api_server.get(f"/runs/{run_id}/events?limit=1001").status == 422


def test_the_api_identity_cannot_reach_a_model_or_forge_a_decision(
    api_server: Client, clean_runs: None
) -> None:
    """A structural check on the served surface, not on the grants.

    The grant tests in `tests/event_log` assert what the database refuses this
    role. This asserts the complementary fact about the HTTP surface: there is
    no route through which a client could ask the API to append anything but
    the two run-lifecycle types and approval decisions, because no such route
    exists. The approval-decision route (AC-0328) is the intentional addition
    from the run-state spec; it reaches only `append_approval_decision`, which
    the grant tests confirm is exclusive to `app_api`. The analysis read route
    is intentionally included: it returns public-source SEC data and requires
    no model call, no tool authority, and no ability to forge a policy decision.

    Break: add a route that calls a model or appends a policy event; this
    assertion changes, and the change is the signal that a reviewer needs.
    """
    served = api_server.get("/openapi.json").body

    assert sorted(served["paths"]) == [
        "/runs",
        "/runs/{run_id}/analysis",
        "/runs/{run_id}/events",
        "/runs/{run_id}/events/stream",
        "/runs/{run_id}/snapshot",
        "/runs/{run_id}/steps/{step_id}/decision",
    ]


def test_analysis_role_requires_analysis_object(api_server: Client, clean_runs: None) -> None:
    """AC-0411: analysis role without analysis object returns 422.

    No object-store read, request object, or run row is created.

    Break: remove the ``if request.analysis is None`` check in start_run.
    Red: status 201 instead of 422.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
        },
    )
    assert response.status == 422


def test_non_analysis_role_refuses_analysis_object(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0411: any other role with an analysis object returns 422.

    Break: remove the ``elif request.analysis is not None`` check.
    Red: status 201 instead of 422.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "coordinator",
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-07-31",
                "snapshot_ref": "ced-first-published-analysis-snapshot/" + "a" * 64,
            },
        },
    )
    assert response.status == 422


def test_analysis_object_refuses_unknown_fields(api_server: Client, clean_runs: None) -> None:
    """AC-0411: extra fields in the analysis object return 422.

    The AnalysisRequest model uses extra='forbid' so unknown keys are
    refused by Pydantic before the route body runs.

    Break: remove ``model_config = ConfigDict(extra='forbid')`` from AnalysisRequest.
    Red: status 201 (or an object-store error) instead of 422.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-07-31",
                "snapshot_ref": "ced-first-published-analysis-snapshot/" + "a" * 64,
                "unknown_field": "should be refused",
            },
        },
    )
    assert response.status == 422


def test_analysis_object_refuses_unsupported_cik(api_server: Client, clean_runs: None) -> None:
    """AC-0411: unsupported but well-formed CIK returns 422 before any object-store read.

    Break: remove the cik equality check.
    Red: status 503 or 422 from object-store, not from field validation.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
            "analysis": {
                "cik": "0000000001",
                "as_of_date": "2026-07-31",
                "snapshot_ref": "ced-first-published-analysis-snapshot/" + "a" * 64,
            },
        },
    )
    assert response.status == 422


def test_analysis_object_refuses_unsupported_as_of_date(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0411: unsupported as-of date returns 422 before any object-store read.

    Break: remove the as_of_date equality check.
    Red: the route proceeds to the object-store read and returns 422 from
    there (or 503) rather than from field validation.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-01-01",
                "snapshot_ref": "ced-first-published-analysis-snapshot/" + "a" * 64,
            },
        },
    )
    assert response.status == 422


def test_analysis_object_refuses_wrong_scope_snapshot_ref(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0411: wrong scope in snapshot_ref returns 422 before any object-store read.

    Break: remove the regex fullmatch check.
    Red: the route proceeds to the object-store read and returns 422 from
    NoSuchKey rather than from pattern validation.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-07-31",
                "snapshot_ref": "ced-step-lifecycle/" + "a" * 64,
            },
        },
    )
    assert response.status == 422


def test_analysis_object_refuses_uppercase_hex_snapshot_ref(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0411: uppercase hex in snapshot_ref returns 422 before any object-store read.

    Break: use re.match with a case-insensitive flag.
    Red: the route proceeds to the object-store read instead of failing on pattern.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-07-31",
                "snapshot_ref": "ced-first-published-analysis-snapshot/" + "A" * 64,
            },
        },
    )
    assert response.status == 422


def test_analysis_object_refuses_overlong_snapshot_ref(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0411: overlong hex (65 chars) in snapshot_ref returns 422.

    Break: use r'[0-9a-f]+' instead of r'[0-9a-f]{64}'.
    Red: the route proceeds to the object-store read.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-07-31",
                "snapshot_ref": "ced-first-published-analysis-snapshot/" + "a" * 65,
            },
        },
    )
    assert response.status == 422


def test_analysis_object_refuses_trailing_newline_snapshot_ref(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0411: trailing newline in snapshot_ref returns 422.

    re.fullmatch rejects the newline; re.match + '$' would admit it because
    '$' matches before a trailing newline.

    Break: use re.match(pattern + '$', ref) instead of re.fullmatch(pattern, ref).
    Red: the route proceeds to the object-store read with a key that has a
    trailing newline.
    """
    response = api_server.post(
        "/runs",
        {
            "principal": "operator",
            "agent_role": "first-published-analysis",
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-07-31",
                "snapshot_ref": "ced-first-published-analysis-snapshot/" + "a" * 64 + "\n",
            },
        },
    )
    assert response.status == 422


def test_an_oversized_attribution_field_is_refused(
    api_server: Client, clean_runs: None
) -> None:
    """The bound on `principal` and `agent_role`, driven rather than declared.

    Both are self-asserted attribution on an unauthenticated surface and land
    in unconstrained `text` columns, so without a bound one request persists an
    arbitrarily large string that every later read of the run returns.

    The contract and the model carry the same number;
    `test_the_published_attribution_bound_matches_the_model` is what holds them
    in step, since AC-0009's route-table comparison excludes
    `components.schemas`. This asserts the served route actually enforces the
    bound, and that a value at the bound still works — a check that only ever
    rejected would pass a model whose maximum was far too low.
    """
    at_bound = "p" * ATTRIBUTION_MAX_LENGTH
    over_bound = "p" * (ATTRIBUTION_MAX_LENGTH + 1)

    # Both fields at the bound, not just `principal`. With only `principal`
    # driven, any `agent_role` maximum between 12 (longer than "coordinator")
    # and 255 would have passed — a positive control has to cover each field it
    # claims to.
    assert (
        api_server.post("/runs", {"principal": at_bound, "agent_role": "coordinator"}).status
        == 201
    )
    assert (
        api_server.post("/runs", {"principal": "operator", "agent_role": at_bound}).status
        == 201
    )
    assert (
        api_server.post("/runs", {"principal": over_bound, "agent_role": "coordinator"}).status
        == 422
    )
    assert (
        api_server.post("/runs", {"principal": "operator", "agent_role": over_bound}).status
        == 422
    )


# --- AC-0411: snapshot refusals after the object-store read ---------------

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CIK = "0000320193"
_AS_OF = "2026-07-31"
_PRINCIPAL = "analysis-start-test-principal"

# The exact key set a snapshot manifest carries.
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "cik",
        "as_of_date",
        "form",
        "filing_date",
        "report_date",
        "accession",
        "source_url",
        "retrieved_at",
        "filing_sha256",
        "filing_ref",
    }
)


# ---------------------------------------------------------------------------
# S3 helper — raw boto3 client for test-only writes outside the adapter scope
# ---------------------------------------------------------------------------


def _s3() -> Any:
    """Raw boto3 S3 client backed by the same endpoint as the adapter."""
    import boto3

    endpoint = os.environ.get("CED_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:59000")
    access = os.environ.get("CED_OBJECT_STORE_ACCESS_KEY", "local_only_not_a_secret")
    secret = os.environ.get("CED_OBJECT_STORE_SECRET_KEY", "local_only_not_a_secret")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name="us-east-1",
    )


# ---------------------------------------------------------------------------
# Object-count helpers
# ---------------------------------------------------------------------------


def _count_owner_scope_objects() -> int:
    """Count objects stored under OWNER_SCOPE (the request-object prefix)."""
    s3 = _s3()
    paginator = s3.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=OWNER_SCOPE + "/"):
        total += page.get("KeyCount", 0)
    return total


# ---------------------------------------------------------------------------
# Snapshot manifest factory
# ---------------------------------------------------------------------------


def _make_valid_snapshot(*, cik: str = _CIK, as_of_date: str = _AS_OF) -> str:
    """Write a valid snapshot manifest to MinIO and return the snapshot_ref.

    Writes fake filing bytes first (to get a real filing_ref under SNAPSHOT_SCOPE),
    then writes the manifest that references them.  The result is a key that
    passes every check in ``_is_snapshot_manifest``.
    """
    # Write fake filing bytes under SNAPSHOT_SCOPE.
    filing_bytes = b"fake-filing-body-for-test"
    filing_ref = write_payload_bytes(filing_bytes, owner_scope=SNAPSHOT_SCOPE)
    filing_sha256 = filing_ref.rsplit("/", 1)[-1]

    # Build a manifest with the exact key set the route requires.
    manifest: dict[str, str] = {
        "schema_version": "1",
        "cik": cik,
        "as_of_date": as_of_date,
        "form": "10-K",
        "filing_date": as_of_date,
        "report_date": as_of_date,
        "accession": "0000000000-00-000000",
        "source_url": "https://example.com/filing",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "filing_sha256": filing_sha256,
        "filing_ref": filing_ref,
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    snapshot_ref = write_payload_bytes(manifest_bytes, owner_scope=SNAPSHOT_SCOPE)
    return snapshot_ref


def _valid_body(snapshot_ref: str) -> dict[str, Any]:
    """POST /runs request body for a valid analysis run."""
    return {
        "principal": _PRINCIPAL,
        "agent_role": "first-published-analysis",
        "analysis": {
            "cik": _CIK,
            "as_of_date": _AS_OF,
            "snapshot_ref": snapshot_ref,
        },
    }


# ---------------------------------------------------------------------------
# Log capture helper
# ---------------------------------------------------------------------------


@contextmanager
def _capture_logs(logger_name: str = "ced.api.analysis") -> Iterator[list[logging.LogRecord]]:
    """Capture every LogRecord emitted to ``logger_name`` within the block."""
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# Shared refusal assertion
# ---------------------------------------------------------------------------


def _assert_single_log_record(
    records: list[logging.LogRecord],
    expected_reason: str,
) -> None:
    """One log record, correct reason_class, no leaking values."""
    assert len(records) == 1, (
        f"expected exactly one log record with reason_class={expected_reason!r}; "
        f"got {len(records)}: {[r.getMessage() for r in records]}"
    )
    record = records[0]
    actual = record.__dict__.get("reason_class")
    assert actual == expected_reason, (
        f"expected reason_class={expected_reason!r}; got {actual!r}"
    )
    # The message must not contain object keys, bytes, principal values,
    # or anything that resembles a SEC contact string.
    msg = record.getMessage()
    assert OWNER_SCOPE not in msg, "log message must not contain an object key scope"
    assert SNAPSHOT_SCOPE not in msg, "log message must not contain an object key scope"
    assert _PRINCIPAL not in msg, "log message must not contain a principal value"


# ---------------------------------------------------------------------------
# Test 1 — Positive control (AC-0411)
# ---------------------------------------------------------------------------


def test_positive_control_request_object_has_three_keys(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """A valid POST /runs creates a run and stores exactly {cik, as_of_date, snapshot_ref}.

    Break: write a request object with different keys.
    Red: the set equality assertion on the stored payload fails.
    """
    snapshot_ref = _make_valid_snapshot()
    response = api_server.post("/runs", _valid_body(snapshot_ref))
    assert response.status == 201, response.body

    run_id = uuid.UUID(response.body["run_id"])

    # Read the run.requested event and follow its payload_ref.
    events = read_events(owner_conn, run_id=run_id)
    assert events, "expected at least one event after start"
    req_event = events[0]
    assert req_event.type == "run.requested"
    assert req_event.payload_ref is not None, "run.requested must carry a payload_ref"

    from ced.adapters.objectstore.client import read_payload

    stored = read_payload(req_event.payload_ref)
    assert set(stored.keys()) == {"cik", "as_of_date", "snapshot_ref"}, (
        f"request object must have exactly {{cik, as_of_date, snapshot_ref}}; "
        f"got {set(stored.keys())}"
    )
    assert stored["cik"] == _CIK
    assert stored["as_of_date"] == _AS_OF
    assert stored["snapshot_ref"] == snapshot_ref


# ---------------------------------------------------------------------------
# Test 2 — Absent snapshot (AC-0411)
# ---------------------------------------------------------------------------


def test_absent_snapshot_returns_422_detail_free(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Well-formed ref with no stored object → 422, no detail, no run created.

    Break: remove the ObjectNotFoundError catch so ClientError propagates as 500.
    Red: response.status == 500 instead of 422.
    """
    # A hex that no object has been written for.
    fake_hex = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
    snapshot_ref = f"{SNAPSHOT_SCOPE}/{fake_hex}"

    before = _count_owner_scope_objects()
    before_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]

    with _capture_logs() as records:
        response = api_server.post("/runs", _valid_body(snapshot_ref))

    assert response.status == 422, response.body
    # detail-free: the body has no custom detail beyond the HTTP phrase
    if response.body and isinstance(response.body, dict):
        detail = response.body.get("detail")
        assert not isinstance(detail, str) or detail in (
            "Unprocessable Entity",
            "Unprocessable Content",
        ), f"unexpected detail: {detail!r}"

    after_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]
    assert after_runs == before_runs, "no run row must be created on refusal"
    assert _count_owner_scope_objects() == before, "no request object must be written"
    _assert_single_log_record(records, "snapshot_not_found")


# ---------------------------------------------------------------------------
# Test 3 — Digest mismatch (AC-0411)
# ---------------------------------------------------------------------------


def test_digest_mismatch_returns_422(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Bytes stored whose SHA-256 disagrees with the key hex → 422.

    Write content_a legitimately (gets key = SNAPSHOT_SCOPE/sha256(a)), then
    overwrite it with content_b (sha256(b) != sha256(a)) via raw boto3.

    Break: remove the digest comparison in start_run.
    Red: the route proceeds to json.loads of content_b, which may parse or fail
    with a different status code — never 422 from the digest check.
    """
    content_a = b"content-a-for-digest-test"
    snapshot_ref = write_payload_bytes(content_a, owner_scope=SNAPSHOT_SCOPE)

    content_b = b"content-b-different-sha256"
    assert hashlib.sha256(content_b).hexdigest() != snapshot_ref.rsplit("/", 1)[-1]
    _s3().put_object(Bucket=BUCKET_NAME, Key=snapshot_ref, Body=content_b)

    before = _count_owner_scope_objects()
    before_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]

    with _capture_logs() as records:
        response = api_server.post("/runs", _valid_body(snapshot_ref))

    assert response.status == 422, response.body
    after_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]
    assert after_runs == before_runs, "no run row must be created on refusal"
    assert _count_owner_scope_objects() == before, "no request object must be written"
    _assert_single_log_record(records, "snapshot_digest_mismatch")


# ---------------------------------------------------------------------------
# Helpers for manifest-mismatch variants
# ---------------------------------------------------------------------------


def _write_snapshot_bytes(body: bytes) -> str:
    """Write raw bytes under SNAPSHOT_SCOPE and return the key.

    The bytes are written legitimately (digest matches the key), so the digest
    check passes and the manifest check runs.
    """
    return write_payload_bytes(body, owner_scope=SNAPSHOT_SCOPE)


def _write_snapshot_manifest(manifest: dict[str, str]) -> str:
    """Write a manifest dict as canonical JSON under SNAPSHOT_SCOPE."""
    body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return _write_snapshot_bytes(body)


def _base_manifest(*, extra: dict[str, str] | None = None) -> dict[str, str]:
    """A manifest that passes _is_snapshot_manifest; callers mutate it."""
    # Build a real filing_ref so the cross-field check passes by default.
    filing_bytes = b"base-filing-for-manifest-test"
    filing_ref = write_payload_bytes(filing_bytes, owner_scope=SNAPSHOT_SCOPE)
    filing_sha256 = filing_ref.rsplit("/", 1)[-1]
    m: dict[str, str] = {
        "schema_version": "1",
        "cik": _CIK,
        "as_of_date": _AS_OF,
        "form": "10-K",
        "filing_date": _AS_OF,
        "report_date": _AS_OF,
        "accession": "0000000000-00-000001",
        "source_url": "https://example.com/filing2",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "filing_sha256": filing_sha256,
        "filing_ref": filing_ref,
    }
    if extra:
        m.update(extra)
    return m


def _assert_manifest_mismatch(
    api_server: Client,
    owner_conn: psycopg.Connection,
    snapshot_ref: str,
) -> None:
    """Common assertion block for manifest-mismatch cases."""
    before = _count_owner_scope_objects()
    before_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]

    with _capture_logs() as records:
        response = api_server.post("/runs", _valid_body(snapshot_ref))

    assert response.status == 422, response.body
    after_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]
    assert after_runs == before_runs, "no run row must be created on manifest mismatch"
    assert _count_owner_scope_objects() == before, "no request object must be written"
    _assert_single_log_record(records, "snapshot_manifest_mismatch")


# ---------------------------------------------------------------------------
# Test 4a — Manifest cik mismatch (AC-0411)
# ---------------------------------------------------------------------------


def test_manifest_mismatch_wrong_cik_returns_422(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Manifest cik disagrees with the request → 422, reason snapshot_manifest_mismatch.

    Break: remove the cik check from _is_snapshot_manifest.
    Red: the route accepts the wrong-cik manifest and creates a run.
    """
    m = _base_manifest()
    m["cik"] = "0000000001"
    snapshot_ref = _write_snapshot_manifest(m)
    _assert_manifest_mismatch(api_server, owner_conn, snapshot_ref)


# ---------------------------------------------------------------------------
# Test 4b — Manifest as_of_date mismatch (AC-0411)
# ---------------------------------------------------------------------------


def test_manifest_mismatch_wrong_as_of_date_returns_422(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Manifest as_of_date disagrees with the request → 422.

    Break: remove the as_of_date check from _is_snapshot_manifest.
    Red: the route accepts the wrong-date manifest.
    """
    m = _base_manifest()
    m["as_of_date"] = "2025-01-01"
    snapshot_ref = _write_snapshot_manifest(m)
    _assert_manifest_mismatch(api_server, owner_conn, snapshot_ref)


# ---------------------------------------------------------------------------
# Test 4c — Filing bytes as snapshot_ref (AC-0411)
# ---------------------------------------------------------------------------


def test_manifest_mismatch_filing_bytes_as_snapshot_ref_returns_422(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Raw non-JSON bytes stored at the snapshot_ref → 422.

    A filing stored under SNAPSHOT_SCOPE fails json.loads, producing
    reason_class=snapshot_manifest_mismatch via the JSON-parse branch.

    Break: remove _is_snapshot_manifest and accept any JSON as a manifest.
    Red: raw non-JSON bytes would produce a JSONDecodeError 500, not 422.
    """
    snapshot_ref = _write_snapshot_bytes(b"<html>raw-filing-body</html>")
    _assert_manifest_mismatch(api_server, owner_conn, snapshot_ref)


# ---------------------------------------------------------------------------
# Test 4d — Request-object-shaped JSON as snapshot_ref (AC-0411)
# ---------------------------------------------------------------------------


def test_manifest_mismatch_request_object_shaped_json_returns_422(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """A {cik, as_of_date, snapshot_ref} JSON under SNAPSHOT_SCOPE → 422.

    This is the shape of the request object (three keys), which has too few
    keys to pass the exact-key-set check in _is_snapshot_manifest.

    Break: write the request object under SNAPSHOT_SCOPE instead of OWNER_SCOPE
    — a request_ref could then be offered back as a snapshot_ref and pass.
    Red: the route accepts the three-key payload as a manifest.
    """
    request_shaped = {
        "cik": _CIK,
        "as_of_date": _AS_OF,
        "snapshot_ref": f"{SNAPSHOT_SCOPE}/{'a' * 64}",
    }
    body = json.dumps(request_shaped, sort_keys=True, separators=(",", ":")).encode()
    snapshot_ref = _write_snapshot_bytes(body)
    _assert_manifest_mismatch(api_server, owner_conn, snapshot_ref)


# ---------------------------------------------------------------------------
# Test 4e — Extra key in manifest (AC-0411)
# ---------------------------------------------------------------------------


def test_manifest_mismatch_extra_key_returns_422(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Manifest with one extra key fails the exact-key-set check → 422.

    Break: change `set(manifest) != _MANIFEST_KEYS` to `not _MANIFEST_KEYS.issubset(manifest)`.
    Red: a superset of the required keys is accepted.
    """
    m = _base_manifest(extra={"unexpected_key": "value"})
    snapshot_ref = _write_snapshot_manifest(m)
    _assert_manifest_mismatch(api_server, owner_conn, snapshot_ref)


# ---------------------------------------------------------------------------
# Test 4f — Missing key in manifest (AC-0411)
# ---------------------------------------------------------------------------


def test_manifest_mismatch_missing_key_returns_422(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Manifest with one missing key fails the exact-key-set check → 422.

    Break: change `set(manifest) != _MANIFEST_KEYS` to `not set(manifest).issuperset(...)`.
    Red: a subset of the required keys is accepted.
    """
    m = _base_manifest()
    del m["form"]  # remove one required key
    snapshot_ref = _write_snapshot_manifest(m)
    _assert_manifest_mismatch(api_server, owner_conn, snapshot_ref)


# ---------------------------------------------------------------------------
# Test 5a — Object store unavailable on snapshot read (AC-0411)
# ---------------------------------------------------------------------------


def test_store_unavailable_on_snapshot_read_returns_503_detail_free(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """ObjectStoreError on read_payload_bytes_checked → 503, detail-free, no run.

    Patching in the server process works because the server runs in the same
    Python process (a daemon thread), sharing the module namespace.

    Break: remove the ObjectStoreError catch or map it to 422.
    Red: 422 or 500 is returned instead of 503.
    """
    snapshot_ref = f"{SNAPSHOT_SCOPE}/{'b' * 64}"

    before = _count_owner_scope_objects()
    before_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]

    with (
        _capture_logs() as records,
        patch(
            "ced.api.main.read_payload_bytes_checked",
            side_effect=ObjectStoreError("injected"),
        ),
    ):
        response = api_server.post("/runs", _valid_body(snapshot_ref))

    assert response.status == 503, response.body
    if response.body and isinstance(response.body, dict):
        detail = response.body.get("detail")
        assert not isinstance(detail, str) or detail in ("Service Unavailable",), (
            f"unexpected detail: {detail!r}"
        )

    after_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]
    assert after_runs == before_runs, "no run row must be created on store failure"
    assert _count_owner_scope_objects() == before, "no request object must be written"
    _assert_single_log_record(records, "snapshot_store_unavailable")


# ---------------------------------------------------------------------------
# Test 5b — Request-object write failure (AC-0411)
# ---------------------------------------------------------------------------


def test_request_object_write_failure_returns_503(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """Exception from write_payload for the request object → 503, no run created.

    The snapshot read and validation succeed; only the write step is patched.

    Break: remove the except block around write_payload in start_run.
    Red: the exception propagates as an unhandled 500.
    """
    snapshot_ref = _make_valid_snapshot()

    before = _count_owner_scope_objects()
    before_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]

    with (
        _capture_logs() as records,
        patch(
            "ced.api.main.write_payload",
            side_effect=OSError("injected write failure"),
        ),
    ):
        response = api_server.post("/runs", _valid_body(snapshot_ref))

    assert response.status == 503, response.body
    after_runs = owner_conn.execute("SELECT count(*) FROM runs").fetchone()[0]
    assert after_runs == before_runs, "no run row must be created when write fails"
    assert _count_owner_scope_objects() == before, "write_payload was patched; no object"
    _assert_single_log_record(records, "request_store_unavailable")
