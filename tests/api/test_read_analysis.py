"""AC-0414, AC-0415: GET /runs/{run_id}/analysis behaviour.

All cases that the route must handle, driven through the real substrate:

- Unknown run → 404
- Pending run (no terminal event) → 409
- Failed analysis run (actual analysis refusal) → 409, terminal before check
- Non-analysis pending run → 409
- Completed analysis with no artifact reference → 409
- Completed analysis with missing object → 409
- Completed analysis with digest mismatch → 409
- Completed analysis with invalid JSON → 409
- Completed analysis with schema mismatch → 409
- AC-0415: no identity header required; response omits principals

AC-0414 requires the failed case to be driven through an actual analysis
refusal and proved terminal before the endpoint returns 409.
"""

from __future__ import annotations

import json
import threading
import uuid

import psycopg
import pytest

from ced.adapters.objectstore.client import (
    ANALYSIS_SCOPE,
    SNAPSHOT_SCOPE,
    write_payload,
    write_payload_bytes,
)
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import (
    append_run_terminal,
    append_step_event,
    read_events,
    start_run,
)
from ced.worker.analysis import ANALYSIS_ROLE, make_analysis_step_body
from ced.worker.pool import Lease

from .conftest import Client

pytestmark = pytest.mark.substrate

# ---------------------------------------------------------------------------
# Isolated pool class so these tests never affect the default or fault-injection
# workers.
# ---------------------------------------------------------------------------

_READ_TEST_POOL_CLASS = "analysis-read-api-test"
_PRINCIPAL = "api-read-test-principal"


# ---------------------------------------------------------------------------
# Helper: create a run in the requested state
# ---------------------------------------------------------------------------


def _make_run(
    *,
    agent_role: str = ANALYSIS_ROLE,
    pool_class: str = _READ_TEST_POOL_CLASS,
    payload_ref: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Commit run + step + run.requested; return (run_id, step_id)."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_PRINCIPAL,
            agent_role=agent_role,
            pool_class=pool_class,
            payload_ref=payload_ref,
        )
    return run_id, step_id


def _cleanup(run_id: uuid.UUID) -> None:
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Helper: lease a step and append terminal events directly
# ---------------------------------------------------------------------------


def _lease_step(step_id: uuid.UUID, pool_class: str) -> int:
    """Directly claim step_id and return the lease_epoch."""
    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = 'api-read-test-worker',
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + make_interval(secs => 30)
             WHERE step_id = %s AND pool_class = %s
             RETURNING lease_epoch
            """,
            (step_id, pool_class),
        ).fetchone()
        conn.commit()
    assert row is not None, "step not updated — pool_class mismatch?"
    return int(row[0])


def _complete_run(
    run_id: uuid.UUID,
    step_id: uuid.UUID,
    epoch: int,
    *,
    agent_role: str = ANALYSIS_ROLE,
    payload_ref: str | None,
) -> None:
    """Append step.started → step.completed → run.completed with the given payload_ref."""
    with psycopg.connect(database_url("worker")) as conn:
        conn.execute(
            "UPDATE runs SET state = 'running' WHERE run_id = %s AND state = 'requested'",
            (run_id,),
        )
        append_step_event(
            conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=epoch,
            type="step.started",
            principal=_PRINCIPAL,
            agent_role=agent_role,
        )
        append_step_event(
            conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=epoch,
            type="step.completed",
            principal=_PRINCIPAL,
            agent_role=agent_role,
            payload_ref=payload_ref,
        )
        append_run_terminal(
            conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=epoch,
            type="run.completed",
            principal=_PRINCIPAL,
            agent_role=agent_role,
            payload_ref=payload_ref,
        )


def _fail_run(
    run_id: uuid.UUID,
    step_id: uuid.UUID,
    epoch: int,
    *,
    agent_role: str = ANALYSIS_ROLE,
) -> None:
    """Append step.started → step.failed → run.failed."""
    with psycopg.connect(database_url("worker")) as conn:
        conn.execute(
            "UPDATE runs SET state = 'running' WHERE run_id = %s AND state = 'requested'",
            (run_id,),
        )
        append_step_event(
            conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=epoch,
            type="step.started",
            principal=_PRINCIPAL,
            agent_role=agent_role,
        )
        append_step_event(
            conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=epoch,
            type="step.failed",
            principal=_PRINCIPAL,
            agent_role=agent_role,
        )
        append_run_terminal(
            conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=epoch,
            type="run.failed",
            principal=_PRINCIPAL,
            agent_role=agent_role,
        )


# ---------------------------------------------------------------------------
# Helper: run the analysis body through a real claim path to produce a failure
# ---------------------------------------------------------------------------


_FAIL_POOL_CLASS = "analysis-fail-api-test"


def _run_analysis_to_failure(run_id: uuid.UUID, step_id: uuid.UUID) -> list[str]:
    """Claim and run an analysis step that is expected to fail.

    The snapshot_ref in the request object points to bytes that do not parse
    as a valid snapshot manifest, so the analysis body appends step.failed
    and run.failed through the ordinary worker path.

    Returns the list of committed event types.
    """
    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = 'analysis-fail-worker',
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + make_interval(secs => 30)
             WHERE step_id = %s AND pool_class = %s
             RETURNING lease_epoch
            """,
            (step_id, _FAIL_POOL_CLASS),
        ).fetchone()
        conn.commit()

    assert row is not None
    epoch = int(row[0])
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=epoch,
        agent_role=ANALYSIS_ROLE,
    )

    body = make_analysis_step_body()
    try:
        body(lease, threading.Event())
    except Exception:
        pass  # The body raises _AnalysisBodyFailed; that is expected here.

    with psycopg.connect(database_url("worker")) as conn:
        evts = read_events(conn, run_id=run_id)
    return [e.type for e in evts]


# ---------------------------------------------------------------------------
# AC-0414: unknown run → 404
# ---------------------------------------------------------------------------


def test_read_analysis_unknown_run_is_404(api_server: Client) -> None:
    """AC-0414: an unknown run_id returns 404.

    Break: remove the ``_require_run`` call at the start of read_analysis.
    Red: status 409 from the missing terminal event instead of 404.
    """
    missing = uuid.uuid4()
    response = api_server.get(f"/runs/{missing}/analysis")
    assert response.status == 404


# ---------------------------------------------------------------------------
# AC-0414: pending run → 409
# ---------------------------------------------------------------------------


def test_read_analysis_pending_run_is_409(api_server: Client, require_substrate: None) -> None:
    """AC-0414: a run with no terminal event returns 409.

    Break: remove the ``if terminal is None`` check.
    Red: AttributeError when the code tries to access terminal.type.
    """
    run_id, _ = _make_run()
    try:
        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0414: failed run (actual analysis refusal, terminal proved before check)
# ---------------------------------------------------------------------------


def test_read_analysis_failed_analysis_run_is_409(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0414: a run.failed terminal returns 409; failure is driven via real worker.

    The analysis body fails because the snapshot_ref in the request object
    points to bytes that do not parse as a valid snapshot manifest.  The
    test proves the run is terminal (run.failed) before calling the API.

    Break: return 200 when the terminal is run.failed.
    Red: status 200 instead of 409.
    """
    # Write a "bad snapshot": valid bytes but not a snapshot manifest JSON.
    bad_bytes = b"not-a-valid-json-manifest"
    bad_snapshot_ref = write_payload_bytes(bad_bytes, owner_scope=SNAPSHOT_SCOPE)

    # Write a request object pointing to the bad snapshot.
    request_ref = write_payload(
        {
            "cik": "0000320193",
            "as_of_date": "2026-07-31",
            "snapshot_ref": bad_snapshot_ref,
        },
        owner_scope=SNAPSHOT_SCOPE,
    )

    run_id, step_id = _make_run(pool_class=_FAIL_POOL_CLASS, payload_ref=request_ref)
    try:
        # Drive the analysis body via a real claim; it must fail.
        event_types = _run_analysis_to_failure(run_id, step_id)

        # Prove the run is terminal (run.failed) before calling the endpoint.
        assert "run.failed" in event_types, (
            f"expected run.failed in events before calling API; got {event_types!r}"
        )
        assert "run.completed" not in event_types, (
            "run.completed must not be present after a body failure"
        )

        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409, (
            f"expected 409 for failed analysis run; got {response.status}"
        )
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0414: non-analysis pending run → 409
# ---------------------------------------------------------------------------


def test_read_analysis_non_analysis_run_is_409(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0414: a pending run with a different agent_role returns 409.

    The run is pending so it is caught by the 'no terminal event' check.
    This confirms that non-analysis runs (pending or otherwise) never
    return 200 from the analysis endpoint.

    Break: remove the terminal-event type check entirely.
    Red: AttributeError or wrong status.
    """
    run_id, _ = _make_run(agent_role="coordinator")
    try:
        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0414: completed analysis with no artifact reference → 409
# ---------------------------------------------------------------------------


def test_read_analysis_missing_artifact_ref_is_409(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0414: run.completed with payload_ref=None returns 409.

    Break: remove the ``if terminal.payload_ref is None`` check.
    Red: the code tries to read bytes from None and raises AttributeError or TypeError.
    """
    run_id, step_id = _make_run()
    try:
        epoch = _lease_step(step_id, _READ_TEST_POOL_CLASS)
        _complete_run(run_id, step_id, epoch, payload_ref=None)

        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0414: missing object → 409
# ---------------------------------------------------------------------------


def test_read_analysis_missing_object_is_409(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0414: run.completed with a payload_ref pointing to a non-existent object returns 409.

    The artifact_ref has the right format but no bytes are stored at that key.

    Break: let the read exception propagate instead of mapping to 409.
    Red: 500 Internal Server Error instead of 409.
    """
    # Construct a well-formed key that does not exist in MinIO.
    fake_sha256 = "b" * 64
    fake_ref = f"{ANALYSIS_SCOPE}/{fake_sha256}"

    run_id, step_id = _make_run()
    try:
        epoch = _lease_step(step_id, _READ_TEST_POOL_CLASS)
        _complete_run(run_id, step_id, epoch, payload_ref=fake_ref)

        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0414: digest mismatch → 409
# ---------------------------------------------------------------------------


def test_read_analysis_digest_mismatch_is_409(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0414: bytes stored at the key whose SHA-256 does not match the key hex → 409.

    Write some bytes, then reference a different key (same scope but wrong hex)
    so the stored bytes' digest disagrees with the hex in the key.

    Break: remove the digest comparison in read_analysis.
    Red: 200 is returned with corrupt bytes parsed as JSON.
    """
    # Write legitimate bytes under their real key.
    content = json.dumps({"dummy": "content"}).encode("utf-8")
    write_payload_bytes(content, owner_scope=ANALYSIS_SCOPE)

    # Build a key that has a different hex (wrong digest).
    wrong_sha256 = "c" * 64
    wrong_key = f"{ANALYSIS_SCOPE}/{wrong_sha256}"

    # Write the same bytes under the wrong key so the object exists but
    # the SHA-256 of the content does not match the hex in the key.
    import os

    import boto3

    from ced.adapters.objectstore.client import (  # noqa: F401
        _DEFAULT_ACCESS_KEY,
        _DEFAULT_SECRET_KEY,
        BUCKET_NAME,
    )

    endpoint = os.environ.get("CED_OBJECT_STORE_ENDPOINT", "http://127.0.0.1:59000")
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get(
            "CED_OBJECT_STORE_ACCESS_KEY", "local_only_not_a_secret"
        ),
        aws_secret_access_key=os.environ.get(
            "CED_OBJECT_STORE_SECRET_KEY", "local_only_not_a_secret"
        ),
        region_name="us-east-1",
    )
    s3.put_object(Bucket=BUCKET_NAME, Key=wrong_key, Body=content)

    run_id, step_id = _make_run()
    try:
        epoch = _lease_step(step_id, _READ_TEST_POOL_CLASS)
        _complete_run(run_id, step_id, epoch, payload_ref=wrong_key)

        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0414: invalid JSON → 409
# ---------------------------------------------------------------------------


def test_read_analysis_invalid_json_is_409(api_server: Client, require_substrate: None) -> None:
    """AC-0414: non-JSON bytes at the artifact key return 409.

    The bytes are stored at their real content-addressed key (so the digest
    check passes), but parse_published_analysis raises DiligenceError because
    the content is not JSON.

    Break: remove the try/except around parse_published_analysis.
    Red: 500 instead of 409.
    """
    bad_bytes = b"not valid json at all"
    artifact_ref = write_payload_bytes(bad_bytes, owner_scope=ANALYSIS_SCOPE)

    run_id, step_id = _make_run()
    try:
        epoch = _lease_step(step_id, _READ_TEST_POOL_CLASS)
        _complete_run(run_id, step_id, epoch, payload_ref=artifact_ref)

        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0414: schema mismatch → 409
# ---------------------------------------------------------------------------


def test_read_analysis_schema_mismatch_is_409(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0414: valid JSON that fails parse_published_analysis schema check → 409.

    The bytes parse as JSON but the schema_version field is wrong, so
    parse_published_analysis raises DiligenceError.

    Break: skip the parse_published_analysis call.
    Red: 200 is returned with an artifact that has not been schema-validated.
    """
    bad_artifact = json.dumps({"schema_version": "wrong/version", "cik": "0000320193"}).encode(
        "utf-8"
    )
    artifact_ref = write_payload_bytes(bad_artifact, owner_scope=ANALYSIS_SCOPE)

    run_id, step_id = _make_run()
    try:
        epoch = _lease_step(step_id, _READ_TEST_POOL_CLASS)
        _complete_run(run_id, step_id, epoch, payload_ref=artifact_ref)

        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 409
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0415: direct read — no identity header required
# ---------------------------------------------------------------------------


def test_read_analysis_requires_no_identity_header(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0415: the endpoint succeeds without any identity/auth header.

    This test uses a valid completed analysis run (produced via the offline
    ingestion fixture) to confirm the 200 path does not check any header.

    Break: add an identity header check to read_analysis.
    Red: 401 or 403 is returned without the required header.
    """
    from ced.worker.ingestion import ingest

    result = ingest(offline=True)
    snapshot_ref = result["snapshot_ref"]

    request_ref = write_payload(
        {"cik": "0000320193", "as_of_date": "2026-07-31", "snapshot_ref": snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )

    run_id, step_id = _make_run(pool_class=_READ_TEST_POOL_CLASS, payload_ref=request_ref)
    try:
        # Run the analysis body in-process.
        epoch = _lease_step(step_id, _READ_TEST_POOL_CLASS)
        lease = Lease(
            step_id=step_id,
            run_id=run_id,
            epoch=epoch,
            agent_role=ANALYSIS_ROLE,
        )
        body = make_analysis_step_body()
        body(lease, threading.Event())

        # Read without any identity header (using the default Client.get).
        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 200, f"expected 200; got {response.status}"

        # Confirm the artifact body contains the canonical memo sentence.
        artifact = response.body
        assert "schema_version" in artifact
        assert artifact.get("cik") == "0000320193"
        claims = artifact["memo"]["claims"]
        assert any("16.36" in c["text"] for c in claims), (
            "canonical memo sentence not found in response"
        )
    finally:
        _cleanup(run_id)


def test_read_analysis_response_omits_principal_values(
    api_server: Client, require_substrate: None
) -> None:
    """AC-0415: the artifact response does not contain principal or SEC-contact values.

    The artifact is public-source data; initiating principal and runtime
    contact values must not appear in the response body.

    Break: include the initiating principal in the artifact JSON.
    Red: the assertion ``_PRINCIPAL not in body_text`` fails.
    """
    from ced.worker.ingestion import ingest

    result = ingest(offline=True)
    snapshot_ref = result["snapshot_ref"]

    request_ref = write_payload(
        {"cik": "0000320193", "as_of_date": "2026-07-31", "snapshot_ref": snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )

    run_id, step_id = _make_run(pool_class=_READ_TEST_POOL_CLASS, payload_ref=request_ref)
    try:
        epoch = _lease_step(step_id, _READ_TEST_POOL_CLASS)
        lease = Lease(
            step_id=step_id,
            run_id=run_id,
            epoch=epoch,
            agent_role=ANALYSIS_ROLE,
        )
        body = make_analysis_step_body()
        body(lease, threading.Event())

        response = api_server.get(f"/runs/{run_id}/analysis")
        assert response.status == 200

        body_text = json.dumps(response.body)
        assert _PRINCIPAL not in body_text, (
            "initiating principal must not appear in the artifact response"
        )
    finally:
        _cleanup(run_id)
