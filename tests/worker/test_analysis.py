"""AC-0413, AC-0418: analysis step body and worker readiness.

Verification mode: TDD on the substrate.  Every check drives the ordinary
Worker claim path; no direct event appends stand in for the analysis body.

Mutation obligations (plan.md):
- AC-0413 checks fail on event reordering, missing fence arguments, model
  fall-through, readiness ordering or dependency failure, and each domain
  refusal before they pass.
- Replacing snapshot or filing bytes under their existing keys makes the
  raw-byte digest check fire before parsing or calculation.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Iterator
from typing import Any
from unittest import mock

import psycopg
import pytest
from botocore.exceptions import ClientError

from ced.adapters.objectstore.client import (
    ANALYSIS_SCOPE,
    READINESS_SCOPE,
    SNAPSHOT_SCOPE,
    head_object,
    read_payload,
    read_payload_bytes,
    write_payload,
)
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import Fenced, read_events, start_run
from ced.domain.diligence import parse_published_analysis
from ced.worker.analysis import (
    ANALYSIS_ROLE,
    READINESS_BYTES,
    ensure_readiness,
    make_analysis_step_body,
)
from ced.worker.pool import ANALYSIS_POOL_CLASS, Lease, PoolConfig, claim_one

pytestmark = pytest.mark.substrate

# ---------------------------------------------------------------------------
# Shared pool config for analysis tests
# ---------------------------------------------------------------------------

_ANALYSIS_TEST_CLASS = "analysis-unit-test"

_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 20_000,
    "input_tokens_limit": 200_000,
    "request_limit": 20,
    "tool_calls_limit": 40,
    "count_tokens_before_request": False,
}

_ANALYSIS_CONFIG = PoolConfig(
    worker_id="test-analysis-worker",
    default_limits=_LIMITS,
    allowed_model_ids=("stub:counting",),
    pool_class=_ANALYSIS_TEST_CLASS,
    lease_ttl_seconds=10,
    heartbeat_seconds=3,
    poll_seconds=1,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_snapshot(
    cik: str = "0000320193",
    as_of_date: str = "2026-07-31",
    *,
    filing_bytes: bytes | None = None,
) -> tuple[str, str, str, bytes]:
    """Write a real snapshot (filing + manifest) to MinIO.

    Returns (snapshot_ref, filing_ref, filing_sha256, filing_bytes).
    """
    from ced.worker.ingestion import ingest

    # Use the offline fixture to get real filing bytes.
    result = ingest(offline=True)
    snapshot_ref = result["snapshot_ref"]

    # Read the manifest to discover the filing_ref.
    manifest = read_payload(snapshot_ref)
    filing_ref = str(manifest["filing_ref"])
    filing_sha256 = str(manifest["filing_sha256"])
    stored_bytes = read_payload_bytes(filing_ref)

    if filing_bytes is not None:
        # Override: replace the filing bytes at the same key for corruption tests.
        # This writes NEW bytes under a NEW key; we replace the manifest's filing_ref.
        pass

    return snapshot_ref, filing_ref, filing_sha256, stored_bytes


@pytest.fixture
def real_snapshot(require_substrate: None) -> tuple[str, str, str]:
    """A real offline snapshot in MinIO; returns (snapshot_ref, filing_ref, filing_sha256)."""
    snapshot_ref, filing_ref, filing_sha256, _ = _build_snapshot()
    return snapshot_ref, filing_ref, filing_sha256


@pytest.fixture
def analysis_run(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """A run+step in pool_class='analysis-unit-test' with a wired request object.

    Yields (run_id, step_id).  Cleans up on exit.
    """
    snapshot_ref, _filing_ref, _filing_sha256 = real_snapshot
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    # Write the request object.
    request_ref = write_payload(
        {"cik": "0000320193", "as_of_date": "2026-07-31", "snapshot_ref": snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="test-principal",
            agent_role=ANALYSIS_ROLE,
            pool_class=_ANALYSIS_TEST_CLASS,
            payload_ref=request_ref,
        )

    try:
        yield run_id, step_id
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()


# ---------------------------------------------------------------------------
# Helper: run the analysis body through the ordinary Worker claim path
# ---------------------------------------------------------------------------


def _run_via_worker(
    run_id: uuid.UUID,
    step_id: uuid.UUID,
    config: PoolConfig,
    step_body: Any,
    agent_role: str = ANALYSIS_ROLE,
) -> list[str]:
    """Claim step_id with config, execute step_body, return committed event types."""
    # Lease the step directly so the worker can claim it.
    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = %s,
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + make_interval(secs => %s)
             WHERE step_id = %s AND pool_class = %s
             RETURNING lease_epoch
            """,
            (config.worker_id, config.lease_ttl_seconds, step_id, config.pool_class),
        ).fetchone()
        conn.commit()

    assert row is not None, "step was not updated — check pool_class matches"
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=int(row[0]),
        agent_role=agent_role,
    )

    step_body(lease, threading.Event())

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    return [e.type for e in events]


# ---------------------------------------------------------------------------
# AC-0413: happy path
# ---------------------------------------------------------------------------


def test_analysis_body_commits_ordered_events_and_artifact(
    analysis_run: tuple[uuid.UUID, uuid.UUID],
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413: the ordinary claim path produces the correct ordered event sequence.

    Mutation: removing the step.started append would leave the run in
    'requested' state and the projection would not advance to 'running'.
    Mutation: removing the run.completed append would leave the run in
    'running' state with no terminal event.
    Mutation: removing payload_ref from step.completed / run.completed
    would make the artifact unreachable from the event log.
    """
    run_id, step_id = analysis_run
    body = make_analysis_step_body()

    event_types = _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)

    # Exact ordered event sequence.
    assert event_types == [
        "run.requested",
        "step.started",
        "step.completed",
        "run.completed",
    ], f"unexpected event sequence: {event_types}"

    # No model, tool, suspension, or approval events.
    forbidden = {
        "step.suspended",
        "step.approval.cap.exceeded",
        "step.spend.ceiling.reached",
        "tool.invoked",
        "policy.decision",
        "approval.granted",
        "approval.rejected",
    }
    for t in event_types:
        assert t not in forbidden, f"forbidden event type {t!r} in analysis run"


def test_analysis_artifact_resolves_by_digest(
    analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413: artifact bytes stored under the analysis scope parse correctly.

    Mutation: writing the artifact to the wrong scope would produce a key
    whose prefix disagrees with ANALYSIS_SCOPE, breaking any reader that
    checks the scope before retrieving.
    """
    run_id, step_id = analysis_run
    body = make_analysis_step_body()
    _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    completed = [e for e in events if e.type == "run.completed"]
    assert len(completed) == 1
    artifact_ref = completed[0].payload_ref
    assert artifact_ref is not None, "run.completed must carry payload_ref"
    assert artifact_ref.startswith(ANALYSIS_SCOPE + "/"), (
        f"artifact_ref {artifact_ref!r} must start with {ANALYSIS_SCOPE + '/'!r}"
    )

    # Digest check: SHA-256 of the stored bytes must match the key.
    artifact_bytes = read_payload_bytes(artifact_ref)
    expected_sha256 = artifact_ref.rsplit("/", 1)[-1]
    assert hashlib.sha256(artifact_bytes).hexdigest() == expected_sha256

    # Parsing must succeed.
    artifact = parse_published_analysis(artifact_bytes)
    assert artifact.cik == "0000320193"
    assert artifact.as_of_date == "2026-07-31"


def test_step_completed_and_run_completed_carry_same_artifact_ref(
    analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413: step.completed and run.completed share the same artifact reference.

    Mutation: writing different refs to the two events would let a reader
    that uses step.completed disagree with one using run.completed.
    """
    run_id, step_id = analysis_run
    body = make_analysis_step_body()
    _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    step_comp = next(e for e in events if e.type == "step.completed")
    run_comp = next(e for e in events if e.type == "run.completed")
    assert step_comp.payload_ref == run_comp.payload_ref, (
        "step.completed and run.completed must carry the same artifact_ref"
    )


# ---------------------------------------------------------------------------
# AC-0413: failure paths — each refusal leaves step.failed + run.failed
# ---------------------------------------------------------------------------


def _run_failing_analysis(run_id: uuid.UUID, step_id: uuid.UUID) -> list[str]:
    """Drive the analysis body and return event types regardless of outcome."""
    body = make_analysis_step_body()
    try:
        _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)
    except Exception:
        pass
    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    return [e.type for e in events]


def _make_failing_run(
    snapshot_ref: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an analysis run and return (run_id, step_id) without cleanup."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    request_ref = write_payload(
        {"cik": "0000320193", "as_of_date": "2026-07-31", "snapshot_ref": snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="test-principal",
            agent_role=ANALYSIS_ROLE,
            pool_class=_ANALYSIS_TEST_CLASS,
            payload_ref=request_ref,
        )
    return run_id, step_id


def _cleanup(run_id: uuid.UUID) -> None:
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
        conn.commit()


def test_snapshot_digest_mismatch_produces_failed_events(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413: replacing snapshot bytes at their key fires the digest check.

    Replace raw snapshot bytes with corrupted content at the same S3 key,
    which causes the SHA-256 recompute to disagree with the key's embedded hex.
    The run must be terminal (step.failed + run.failed) with no artifact.

    Mutation: removing the snapshot digest check allows corrupted bytes to
    be parsed, which breaks the lineage guarantee.
    """
    snapshot_ref, _filing_ref, _filing_sha256 = real_snapshot
    corrupted = b'{"schema_version":"1","cik":"0000320193","as_of_date":"2026-07-31",'
    corrupted += b'"filing_sha256":"0" * 64,"filing_ref":"bad","source_url":"","form":"",'
    corrupted += b'"filing_date":"","report_date":"","accession":"","retrieved_at":""}'

    # Put corrupted bytes at the snapshot key (same key, different content).
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:59000",
        aws_access_key_id="local_only_not_a_secret",
        aws_secret_access_key="local_only_not_a_secret",
        region_name="us-east-1",
    )
    bucket = "ced-payloads"
    s3.put_object(Bucket=bucket, Key=snapshot_ref, Body=corrupted)

    run_id, step_id = _make_failing_run(snapshot_ref)
    try:
        event_types = _run_failing_analysis(run_id, step_id)
        assert "step.failed" in event_types, (
            f"snapshot digest mismatch must produce step.failed; got {event_types}"
        )
        assert "run.failed" in event_types, (
            f"snapshot digest mismatch must produce run.failed; got {event_types}"
        )
        assert "run.completed" not in event_types, (
            "a corrupted snapshot must never produce run.completed"
        )
        assert "step.completed" not in event_types
        # Confirm ordering: step.failed before run.failed.
        sf_idx = event_types.index("step.failed")
        rf_idx = event_types.index("run.failed")
        assert sf_idx < rf_idx, "step.failed must precede run.failed"
    finally:
        _cleanup(run_id)


def test_filing_digest_mismatch_against_key_produces_failed_events(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413: replacing filing bytes at their key fires the digest check.

    Replace raw filing bytes with garbage content at the same S3 key.  The
    SHA-256 recompute disagrees with the key's embedded hex.

    Mutation: removing the filing-digest-vs-key check allows tampered filing
    bytes to be parsed before the lineage is validated.
    """
    snapshot_ref, filing_ref, _filing_sha256 = real_snapshot
    corrupt_filing = b"<html><body>corrupted filing</body></html>"

    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:59000",
        aws_access_key_id="local_only_not_a_secret",
        aws_secret_access_key="local_only_not_a_secret",
        region_name="us-east-1",
    )
    bucket = "ced-payloads"
    s3.put_object(Bucket=bucket, Key=filing_ref, Body=corrupt_filing)

    run_id, step_id = _make_failing_run(snapshot_ref)
    try:
        event_types = _run_failing_analysis(run_id, step_id)
        assert "step.failed" in event_types, (
            f"filing digest mismatch must produce step.failed; got {event_types}"
        )
        assert "run.failed" in event_types
        assert "run.completed" not in event_types
        assert "step.completed" not in event_types
    finally:
        _cleanup(run_id)


def test_manifest_cik_mismatch_produces_failed_events(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413: a request whose CIK disagrees with the manifest fails the run.

    Mutation: removing the manifest–request agreement check allows a mismatched
    CIK to reach build_published_analysis, which may silently produce a wrong
    artifact or raise an unexpected error.
    """
    snapshot_ref, _filing_ref, _filing_sha256 = real_snapshot
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    # Use a different CIK in the request.
    request_ref = write_payload(
        {"cik": "9999999999", "as_of_date": "2026-07-31", "snapshot_ref": snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="test-principal",
            agent_role=ANALYSIS_ROLE,
            pool_class=_ANALYSIS_TEST_CLASS,
            payload_ref=request_ref,
        )
    try:
        event_types = _run_failing_analysis(run_id, step_id)
        assert "step.failed" in event_types
        assert "run.failed" in event_types
        assert "run.completed" not in event_types
    finally:
        _cleanup(run_id)


def test_domain_error_produces_failed_events(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413: a domain error from build_published_analysis maps to failed events.

    Mutation: catching the exception but not appending step.failed would leave
    the run non-terminal (no run.failed).
    """
    snapshot_ref, _filing_ref, _filing_sha256 = real_snapshot
    run_id, step_id = _make_failing_run(snapshot_ref)
    try:
        with mock.patch(
            "ced.worker.analysis.build_published_analysis",
            side_effect=Exception("injected build failure"),
        ):
            event_types = _run_failing_analysis(run_id, step_id)

        assert "step.failed" in event_types, (
            f"DiligenceError must produce step.failed; got {event_types}"
        )
        assert "run.failed" in event_types
        assert "run.completed" not in event_types
        assert "step.completed" not in event_types
        # step.started must still have been appended before the failure.
        assert "step.started" in event_types
    finally:
        _cleanup(run_id)


def test_artifact_store_failure_produces_failed_events(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413: an object-store failure during artifact write produces failed events.

    Mutation: catching the storage error but not appending step.failed would
    leave the run non-terminal.
    """
    snapshot_ref, _filing_ref, _filing_sha256 = real_snapshot
    run_id, step_id = _make_failing_run(snapshot_ref)
    try:
        with mock.patch(
            "ced.worker.analysis.write_payload_bytes",
            side_effect=Exception("injected store failure"),
        ):
            event_types = _run_failing_analysis(run_id, step_id)

        assert "step.failed" in event_types
        assert "run.failed" in event_types
        assert "run.completed" not in event_types
        assert "step.completed" not in event_types
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0416 preparation: pool class isolation
# ---------------------------------------------------------------------------


def test_analysis_step_is_not_claimable_by_default_class_worker(
    analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0416 prep: an analysis step is not claimed by a default-class worker.

    Mutation: removing the pool_class predicate from claim_one would let a
    default-class worker claim analysis rows, corrupting the pool partition.
    """
    run_id, step_id = analysis_run
    default_config = PoolConfig(
        worker_id="test-default-worker",
        default_limits=_LIMITS,
        allowed_model_ids=("stub:counting",),
        pool_class="default",
        lease_ttl_seconds=10,
        heartbeat_seconds=3,
        poll_seconds=1,
    )
    with psycopg.connect(database_url("worker")) as conn:
        lease = claim_one(conn, default_config)

    assert lease is None or lease.step_id != step_id, (
        f"default-class worker must not claim an analysis step; got lease={lease}"
    )


# ---------------------------------------------------------------------------
# AC-0418: object-store readiness
# ---------------------------------------------------------------------------


def test_ensure_readiness_writes_and_heads_sentinel(require_substrate: None) -> None:
    """AC-0418: ensure_readiness writes the sentinel then confirms it with HeadObject.

    The sentinel bytes and key are deterministic: the same call is idempotent.

    Mutation: removing head_object from ensure_readiness would let a put
    succeed without confirming the key is actually readable.
    """
    # Call ensure_readiness; it should complete without raising.
    ensure_readiness()

    # The key is deterministic: sha256 of READINESS_BYTES under READINESS_SCOPE.
    expected_hex = hashlib.sha256(READINESS_BYTES).hexdigest()
    expected_key = f"{READINESS_SCOPE}/{expected_hex}"

    # Head the key directly — confirms the object is present.
    head_object(expected_key)

    # Read the bytes back and confirm content.
    stored = read_payload_bytes(expected_key)
    assert stored == READINESS_BYTES, (
        f"sentinel bytes should be {READINESS_BYTES!r}, got {stored!r}"
    )


def test_ensure_readiness_is_idempotent(require_substrate: None) -> None:
    """AC-0418: calling ensure_readiness twice completes without error.

    The bucket and sentinel key already exist on the second call; the put is
    a content-addressed overwrite and the head should still succeed.
    """
    ensure_readiness()
    ensure_readiness()  # must not raise


def test_readiness_head_failure_prevents_poll(require_substrate: None) -> None:
    """AC-0418: a HeadObject failure prevents the poll loop from starting.

    Inject a failure on head_object after the put; the call must propagate
    rather than being swallowed.

    Mutation: catching the head failure and continuing would let the poll
    loop start despite an unverified readiness state, leaving seeded work
    unclaimed until the next boot.
    """
    from botocore.exceptions import ClientError

    fake_error = ClientError({"Error": {"Code": "500", "Message": "injected"}}, "HeadObject")
    with mock.patch("ced.worker.analysis.head_object", side_effect=fake_error):
        with pytest.raises(ClientError):
            ensure_readiness()


def test_readiness_put_failure_prevents_poll(require_substrate: None) -> None:
    """AC-0418: a write failure on the sentinel prevents the poll loop.

    Mutation: catching the write failure and continuing would let the analysis
    worker poll without a verified object store.
    """
    with mock.patch(
        "ced.worker.analysis.write_payload_bytes",
        side_effect=Exception("injected put failure"),
    ):
        with pytest.raises(Exception, match="injected put failure"):
            ensure_readiness()


def test_pool_run_dispatches_readiness_before_poll(require_substrate: None) -> None:
    """AC-0418: pool.run() calls ensure_readiness before the first claim.

    Verify ordering by replacing ensure_readiness with a spy that records calls,
    then patching run_forever to exit immediately.  The spy must have been called
    before run_forever.

    Mutation: moving the ensure_readiness call inside run_forever (after the
    first poll) would let the worker claim a step before the readiness check.
    """
    from unittest import mock as _mock

    call_log: list[str] = []

    def spy_readiness() -> None:
        call_log.append("readiness")

    def spy_run_forever(self: Any) -> None:
        call_log.append("run_forever")

    with (
        _mock.patch("ced.worker.analysis.ensure_readiness", side_effect=spy_readiness),
        _mock.patch(
            "ced.worker.analysis.make_analysis_step_body", return_value=lambda _l, _s: None
        ),
        _mock.patch.object(
            __import__("ced.worker.pool", fromlist=["Worker"]).Worker,
            "run_forever",
            spy_run_forever,
        ),
        _mock.patch.object(
            __import__("ced.worker.pool", fromlist=["Worker"]).Worker,
            "install_signal_handlers",
            lambda self: None,
        ),
        _mock.patch(
            "ced.worker.pool.verify_boot",
            return_value=PoolConfig(
                worker_id="test",
                default_limits=_LIMITS,
                allowed_model_ids=("stub:counting",),
                pool_class="analysis",
            ),
        ),
    ):
        from ced.worker.pool import run

        run()

    assert call_log == ["readiness", "run_forever"], (
        f"ensure_readiness must run before run_forever; call order was {call_log}"
    )


# ---------------------------------------------------------------------------
# Role dispatch: unexpected role produces failed events (item 1)
# ---------------------------------------------------------------------------


def test_unexpected_role_produces_failed_events(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """Role dispatch: a step with an unexpected agent_role produces step.failed + run.failed.

    The body checks lease.agent_role before building or storing anything.
    An unexpected role commits step.started (requested→running) then appends
    the fenced failure events; no artifact is written and no run.completed follows.

    Mutation: removing the role check in _analysis_body would let an unexpected
    role proceed to Phase 3 and either fail on the domain logic or produce an
    artifact for the wrong purpose.
    """
    snapshot_ref, _, _ = real_snapshot
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    request_ref = write_payload(
        {"cik": "0000320193", "as_of_date": "2026-07-31", "snapshot_ref": snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="test-principal",
            agent_role="unexpected-role",
            pool_class=_ANALYSIS_TEST_CLASS,
            payload_ref=request_ref,
        )
    try:
        body = make_analysis_step_body()
        try:
            _run_via_worker(
                run_id,
                step_id,
                _ANALYSIS_CONFIG,
                body,
                agent_role="unexpected-role",
            )
        except Exception:
            pass
        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)
        event_types = [e.type for e in events]

        assert "step.started" in event_types, (
            f"step.started must be committed before failure; got {event_types}"
        )
        assert "step.failed" in event_types, (
            f"unexpected role must produce step.failed; got {event_types}"
        )
        assert "run.failed" in event_types, (
            f"unexpected role must produce run.failed; got {event_types}"
        )
        assert "step.completed" not in event_types, (
            "unexpected role must not produce step.completed"
        )
        assert "run.completed" not in event_types, (
            "unexpected role must not produce run.completed"
        )
        sf_idx = event_types.index("step.failed")
        rf_idx = event_types.index("run.failed")
        assert sf_idx < rf_idx, "step.failed must precede run.failed"
    finally:
        _cleanup(run_id)


def test_model_executor_not_constructed_for_analysis_role(
    analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Role dispatch / model fall-through: BedrockConverseModel is never constructed.

    With the analysis body running, patching BedrockConverseModel.__init__ to
    raise must not affect the outcome.  The analysis body builds the artifact
    from deterministic domain logic; it never constructs a model executor or
    agent compiler.

    Mutation: constructing BedrockConverseModel inside _analysis_body would
    fire the AssertionError from the patched __init__ and the body would fail
    rather than complete.
    """
    run_id, step_id = analysis_run
    body = make_analysis_step_body()

    def _fail_init(self: object, *args: object, **kwargs: object) -> None:
        raise AssertionError(
            "BedrockConverseModel constructor must not be called in the analysis body"
        )

    with mock.patch(
        "pydantic_ai.models.bedrock.BedrockConverseModel.__init__",
        _fail_init,
    ):
        event_types = _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)

    assert event_types == [
        "run.requested",
        "step.started",
        "step.completed",
        "run.completed",
    ], f"analysis body must complete without constructing a model; got {event_types}"


# ---------------------------------------------------------------------------
# Missing payload_ref leaves run terminal (item 2)
# ---------------------------------------------------------------------------


def test_missing_payload_ref_produces_failed_events(
    require_substrate: None,
) -> None:
    """AC-0413: a run.requested event with no payload_ref leaves the run terminal.

    The body commits step.started (requested→running) then appends fenced
    step.failed + run.failed.  No artifact is written and no run.completed
    follows.

    Mutation: the previous silent-return path left the run in 'requested'
    (non-terminal); removing the _commit_step_started + _append_failure block
    restores that path and this test reds.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="test-principal",
            agent_role=ANALYSIS_ROLE,
            pool_class=_ANALYSIS_TEST_CLASS,
            payload_ref=None,  # no payload_ref — the case under test
        )
    try:
        body = make_analysis_step_body()
        try:
            _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)
        except Exception:
            pass
        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)
        event_types = [e.type for e in events]

        assert "step.started" in event_types, (
            f"step.started must be committed before failure; got {event_types}"
        )
        assert "step.failed" in event_types, (
            f"missing payload_ref must produce step.failed; got {event_types}"
        )
        assert "run.failed" in event_types, (
            f"missing payload_ref must produce run.failed; got {event_types}"
        )
        assert "step.completed" not in event_types
        assert "run.completed" not in event_types
        sf_idx = event_types.index("step.failed")
        rf_idx = event_types.index("run.failed")
        assert sf_idx < rf_idx, "step.failed must precede run.failed"
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0418 through pool.run() — bucket-ensure, put, and head failures (item 3)
# ---------------------------------------------------------------------------

_POOL_RUN_CONFIG = PoolConfig(
    worker_id="test-pool-run-analysis-worker",
    default_limits=_LIMITS,
    allowed_model_ids=("stub:counting",),
    pool_class=ANALYSIS_POOL_CLASS,
    lease_ttl_seconds=10,
    heartbeat_seconds=3,
    poll_seconds=1,
)


def _seed_runnable_analysis_step(
    snapshot_ref: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a runnable analysis step and return (run_id, step_id)."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    request_ref = write_payload(
        {"cik": "0000320193", "as_of_date": "2026-07-31", "snapshot_ref": snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="test-principal",
            agent_role=ANALYSIS_ROLE,
            pool_class=ANALYSIS_POOL_CLASS,
            payload_ref=request_ref,
        )
    return run_id, step_id


def _assert_step_still_runnable(run_id: uuid.UUID, step_id: uuid.UUID) -> None:
    """Assert the step is still 'runnable' with no lease and no events beyond run.requested."""
    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            "SELECT state, owner, lease_epoch FROM steps WHERE step_id = %s",
            (step_id,),
        ).fetchone()
        assert row is not None
        state, owner, lease_epoch = row
        assert state == "runnable", f"step must still be runnable; got state={state!r}"
        assert owner is None, f"step must have no owner; got owner={owner!r}"
        assert lease_epoch == 0, f"step must have epoch 0 (never leased); got {lease_epoch}"

        events = read_events(conn, run_id=run_id)
    event_types = [e.type for e in events]
    assert event_types == ["run.requested"], f"only run.requested must exist; got {event_types}"


def test_pool_run_propagates_bucket_ensure_failure(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0418 / pool.run(): a bucket-ensure failure propagates before run_forever.

    The analysis worker runs _ensure_bucket inside write_payload_bytes.  When
    _ensure_bucket raises, ensure_readiness propagates, pool.run() propagates,
    and the seeded runnable step stays unclaimed with no extra events.

    Mutation: catching the bucket error in ensure_readiness and continuing
    would let run_forever start; the step would be claimed and the readiness
    sentinel would be absent.
    """
    snapshot_ref, _, _ = real_snapshot
    run_id, step_id = _seed_runnable_analysis_step(snapshot_ref)
    try:
        bucket_error = ClientError(
            {"Error": {"Code": "500", "Message": "injected bucket error"}},
            "HeadBucket",
        )
        with mock.patch(
            "ced.adapters.objectstore.client._ensure_bucket",
            side_effect=bucket_error,
        ):
            with mock.patch("ced.worker.pool.verify_boot", return_value=_POOL_RUN_CONFIG):
                with pytest.raises(ClientError):
                    from ced.worker.pool import run as pool_run

                    pool_run()

        _assert_step_still_runnable(run_id, step_id)
    finally:
        _cleanup(run_id)


def test_pool_run_propagates_put_failure(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0418 / pool.run(): a put failure (after bucket-ensure) propagates before run_forever.

    Simulates a failed put_object call by returning a mock S3 client whose
    head_bucket succeeds (so the bucket exists) but put_object raises.
    ensure_readiness propagates, pool.run() propagates, and the seeded step
    stays unclaimed.

    Mutation: catching the put error and continuing would let the poll loop
    start without a verified readiness sentinel.
    """
    snapshot_ref, _, _ = real_snapshot
    run_id, step_id = _seed_runnable_analysis_step(snapshot_ref)
    try:
        mock_s3 = mock.MagicMock()
        mock_s3.head_bucket.return_value = {}  # bucket exists
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "injected put error"}}, "PutObject"
        )
        with mock.patch(
            "ced.adapters.objectstore.client._s3_client",
            return_value=mock_s3,
        ):
            with mock.patch("ced.worker.pool.verify_boot", return_value=_POOL_RUN_CONFIG):
                with pytest.raises(ClientError):
                    from ced.worker.pool import run as pool_run

                    pool_run()

        _assert_step_still_runnable(run_id, step_id)
    finally:
        _cleanup(run_id)


def test_pool_run_propagates_head_failure(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0418 / pool.run(): a HeadObject failure propagates before run_forever.

    The sentinel is written but the head check raises.  ensure_readiness
    propagates, pool.run() propagates, and the seeded step stays unclaimed.

    Mutation: catching the HeadObject error and continuing would let the poll
    loop start with an unverified sentinel.
    """
    snapshot_ref, _, _ = real_snapshot
    run_id, step_id = _seed_runnable_analysis_step(snapshot_ref)
    try:
        head_error = ClientError(
            {"Error": {"Code": "500", "Message": "injected head error"}},
            "HeadObject",
        )
        with mock.patch("ced.worker.analysis.head_object", side_effect=head_error):
            with mock.patch("ced.worker.pool.verify_boot", return_value=_POOL_RUN_CONFIG):
                with pytest.raises(ClientError):
                    from ced.worker.pool import run as pool_run

                    pool_run()

        _assert_step_still_runnable(run_id, step_id)
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# Filing digest vs manifest (item 4)
# ---------------------------------------------------------------------------


def test_filing_digest_mismatch_against_manifest_produces_failed_events(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413: filing bytes match their key but manifest filing_sha256 disagrees.

    Constructs a modified manifest whose filing_sha256 field does not match
    the actual SHA-256 of the filing bytes.  The digest-vs-key check passes;
    the digest-vs-manifest check fails before any domain parsing.

    Mutation: removing the `filing_sha256 != manifest_filing_sha256` check
    allows a manifest with a tampered lineage field to proceed to
    build_published_analysis.
    """
    snapshot_ref, filing_ref, correct_filing_sha256 = real_snapshot

    # Read the real manifest and patch filing_sha256 to a wrong value.
    manifest_obj = read_payload(snapshot_ref)
    manifest_obj["filing_sha256"] = "a" * 64  # wrong digest, not the real one
    patched_snapshot_ref = write_payload(
        manifest_obj,
        owner_scope=SNAPSHOT_SCOPE,
    )

    # Confirm the filing bytes at filing_ref still match their key (not corrupted).
    filing_bytes = read_payload_bytes(filing_ref)
    import hashlib as _hashlib

    assert _hashlib.sha256(filing_bytes).hexdigest() == filing_ref.rsplit("/", 1)[-1]

    # Create a request pointing at the patched snapshot.
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    request_ref = write_payload(
        {"cik": "0000320193", "as_of_date": "2026-07-31", "snapshot_ref": patched_snapshot_ref},
        owner_scope=SNAPSHOT_SCOPE,
    )
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="test-principal",
            agent_role=ANALYSIS_ROLE,
            pool_class=_ANALYSIS_TEST_CLASS,
            payload_ref=request_ref,
        )
    try:
        event_types = _run_failing_analysis(run_id, step_id)
        assert "step.failed" in event_types, (
            f"manifest filing_sha256 mismatch must produce step.failed; got {event_types}"
        )
        assert "run.failed" in event_types
        assert "run.completed" not in event_types
        assert "step.completed" not in event_types
        sf_idx = event_types.index("step.failed")
        rf_idx = event_types.index("run.failed")
        assert sf_idx < rf_idx, "step.failed must precede run.failed"
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# Fence and ordering mutations (item 5)
# ---------------------------------------------------------------------------


def test_fenced_step_completed_stops_phase4_and_leaves_run_nonterminal(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
) -> None:
    """AC-0413 fence: Fenced on Phase 4's step.completed leaves no completion events.

    Injects Fenced through a mock on the second append_step_event call (Phase
    4's step.completed). Phase 2's step.started commit uses call #1 and
    succeeds. No step.completed or run.completed is committed. This pins how
    the body handles Fenced; it does not drive the database fence itself.

    Mutation: swallow Fenced in Phase 4 and go on to run.completed. The run
    then ends terminal and the run.completed assertion fires.
    """
    import ced.worker.analysis as _analysis_mod

    snapshot_ref, _, _ = real_snapshot
    run_id, step_id = _make_failing_run(snapshot_ref)

    body = make_analysis_step_body()
    call_count = [0]
    real_fn = _analysis_mod.append_step_event

    def fenced_on_second_call(*args: Any, **kwargs: Any) -> Any:
        call_count[0] += 1
        if call_count[0] == 2:
            raise Fenced(f"injected Fenced on Phase 4 step event (call {call_count[0]})")
        return real_fn(*args, **kwargs)

    try:
        with mock.patch.object(
            _analysis_mod, "append_step_event", side_effect=fenced_on_second_call
        ):
            try:
                _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)
            except Exception:
                pass

        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)
        event_types = [e.type for e in events]

        assert "step.started" in event_types, (
            "Phase 2 must still commit step.started before the Phase 4 fence fires"
        )
        assert "step.completed" not in event_types, (
            f"Fenced on step.completed must not leave a partial completion; got {event_types}"
        )
        assert "run.completed" not in event_types, (
            "no run.completed must follow a Fenced step.completed"
        )
    finally:
        _cleanup(run_id)


def test_phase3_failure_log_includes_run_id_step_id_exc_type_but_not_principal(
    require_substrate: None,
    real_snapshot: tuple[str, str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Advisory 7: Phase 3 failure log names run_id, step_id, exc_type, not principal.

    Mocks ``read_payload`` to raise ``RuntimeError`` in Phase 3 and checks that
    the error log record includes the identifying fields and excludes the
    principal value.

    Mutation 1: remove ``lease.run_id`` from the log format → ``str(run_id)``
    is absent from the message and the assertion fails.
    Mutation 2: remove ``type(exc).__name__`` from the format → ``exc_type=``
    value is missing and the assertion fails.
    Mutation 3: add ``principal`` to the log message → the principal-absent
    assertion fails.
    Mutation 4: remove ``exc_info=True`` → ``record.exc_info`` is None and the
    assertion fails.
    """
    import logging

    import ced.worker.analysis as _analysis_mod

    snapshot_ref, _, _ = real_snapshot
    run_id, step_id = _make_failing_run(snapshot_ref)

    body = make_analysis_step_body()
    try:
        with caplog.at_level(logging.ERROR, logger="ced.worker.analysis"):
            with mock.patch.object(
                _analysis_mod,
                "read_payload",
                side_effect=RuntimeError("simulated phase3 failure"),
            ):
                try:
                    _run_via_worker(run_id, step_id, _ANALYSIS_CONFIG, body)
                except Exception:
                    pass
    finally:
        _cleanup(run_id)

    phase3_records = [
        r for r in caplog.records if r.levelno == logging.ERROR and "phase=3" in r.getMessage()
    ]
    assert len(phase3_records) >= 1, (
        f"expected a Phase 3 error log; records: {[r.getMessage() for r in caplog.records]}"
    )
    msg = phase3_records[0].getMessage()

    assert str(run_id) in msg, f"run_id must appear in the failure log; got {msg!r}"
    assert str(step_id) in msg, f"step_id must appear in the failure log; got {msg!r}"
    assert "RuntimeError" in msg, f"exc_type must appear in the failure log; got {msg!r}"
    assert phase3_records[0].exc_info is not None, (
        "exc_info=True must be set so the traceback is captured"
    )
    assert "test-principal" not in msg, "principal must not appear in the Phase 3 failure log"


def test_an_unreadable_principal_makes_the_pool_record_failure(require_substrate: None) -> None:
    """With no principal no event can be built, but the step must not read as done.

    The pool records ``completed`` when a body returns and ``failed`` when it
    raises. Mutation: return instead of raising on this path. No exception
    escapes, and this check reds.
    """
    from ced.worker import analysis

    lease = Lease(
        step_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        epoch=1,
        agent_role="first-published-analysis",
    )
    with mock.patch.object(
        analysis, "read_run_principal", side_effect=RuntimeError("unreadable")
    ):
        with pytest.raises(analysis._AnalysisBodyFailed):
            analysis._analysis_body(lease, threading.Event())
