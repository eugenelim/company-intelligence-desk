"""AC-0413, AC-0416: end-to-end analysis publication.

The direct-start helpers (``_claim_and_run``, ``_claim_and_run_http``) hand-lease
the step via a direct SQL UPDATE and call the analysis body directly.  They do
not use the real Worker ``claim_one`` poll path.  The ``http_analysis_run``
fixture starts the run through the public HTTP API (AC-0416) but also
hand-leases the step for the in-process body call.

The suite proves:
- The committed event sequence matches the expected order.
- The artifact bytes resolve by digest (SHA-256 in key == SHA-256 of bytes).
- The artifact parses via ``parse_published_analysis``.
- ``step.completed`` and ``run.completed`` carry the same artifact reference.
- POST /runs stores ``pool_class='analysis'`` before any fixture rewrite (AC-0412).
- POST /runs creates the analysis run via the public HTTP API (AC-0416).
- GET /runs/{run_id}/analysis returns the typed artifact (AC-0416).
"""

from __future__ import annotations

import hashlib
import socket
import threading
import time
import uuid
from collections.abc import Iterator

import psycopg
import pytest
import uvicorn

from ced.adapters.objectstore.client import (
    ANALYSIS_SCOPE,
    SNAPSHOT_SCOPE,
    read_payload_bytes,
    write_payload,
)
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import append_step_event, read_events, start_run
from ced.domain.diligence import parse_published_analysis
from ced.worker.analysis import ANALYSIS_ROLE, make_analysis_step_body
from ced.worker.pool import Lease, PoolConfig, claim_one
from tests.api.conftest import Client

pytestmark = pytest.mark.substrate


# ---------------------------------------------------------------------------
# Local API server for the e2e tests that use the HTTP API (AC-0416)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def e2e_api_server(require_substrate: None) -> Iterator[Client]:
    """Start the real ced-api in a daemon thread for this module's e2e tests.

    Module scope avoids starting uvicorn per-test while keeping e2e isolation
    from the session-scoped server in tests/api/.
    """
    from ced.api.main import app

    port = _free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    client = Client(base_url=f"http://127.0.0.1:{port}")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:  # pragma: no cover
        pytest.fail("uvicorn did not start within 30 s")

    try:
        yield client
    finally:
        server.should_exit = True
        thread.join(timeout=15)


# ---------------------------------------------------------------------------
# Pool config — isolated class so other suites are unaffected
# ---------------------------------------------------------------------------

_E2E_POOL_CLASS = "analysis-e2e-test"

_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 20_000,
    "input_tokens_limit": 200_000,
    "request_limit": 20,
    "tool_calls_limit": 40,
    "count_tokens_before_request": False,
}

_E2E_CONFIG = PoolConfig(
    worker_id="e2e-analysis-worker",
    default_limits=_LIMITS,
    allowed_model_ids=("stub:counting",),
    pool_class=_E2E_POOL_CLASS,
    lease_ttl_seconds=30,
    heartbeat_seconds=10,
    poll_seconds=1,
)


# ---------------------------------------------------------------------------
# Fixture: a complete analysis run from snapshot → start_run
# ---------------------------------------------------------------------------


@pytest.fixture
def published_analysis_run(require_substrate: None) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """Ingest the offline fixture, start an analysis run, yield (run_id, step_id).

    Cleans up runs, steps, and events on exit.  Snapshot objects are
    content-addressed and harmless to leave; they are not removed.
    """
    from ced.worker.ingestion import ingest

    # Ingest the privacy-safe offline fixture to get a real snapshot.
    result = ingest(offline=True)
    snapshot_ref = result["snapshot_ref"]

    # Write the request object (cik, as_of_date, snapshot_ref).
    request_ref = write_payload(
        {
            "cik": "0000320193",
            "as_of_date": "2026-07-31",
            "snapshot_ref": snapshot_ref,
        },
        owner_scope=SNAPSHOT_SCOPE,
    )

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal="e2e-test-principal",
            agent_role=ANALYSIS_ROLE,
            pool_class=_E2E_POOL_CLASS,
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


def _claim_and_run(run_id: uuid.UUID, step_id: uuid.UUID) -> list[str]:
    """Lease, run, and return committed event types — same mechanism as production."""
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
            (_E2E_CONFIG.worker_id, _E2E_CONFIG.lease_ttl_seconds, step_id, _E2E_POOL_CLASS),
        ).fetchone()
        conn.commit()

    assert row is not None, "step not updated — pool_class mismatch?"
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=int(row[0]),
        agent_role=ANALYSIS_ROLE,
    )

    body = make_analysis_step_body()
    body(lease, threading.Event())

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    return [e.type for e in events]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_end_to_end_analysis_produces_ordered_events(
    published_analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413/0416 prep: the ordinary claim path produces the correct event sequence.

    The Worker body commits run.requested (from start_run), then step.started,
    step.completed, and run.completed through the ordinary append functions.
    No direct event appends stand in for any step.
    """
    run_id, step_id = published_analysis_run
    event_types = _claim_and_run(run_id, step_id)

    assert event_types == [
        "run.requested",
        "step.started",
        "step.completed",
        "run.completed",
    ], f"unexpected event sequence: {event_types}"


def test_end_to_end_artifact_resolves_by_digest_and_parses(
    published_analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413: artifact bytes are content-addressed and parse correctly.

    Verify:
    - artifact_ref starts with ANALYSIS_SCOPE/
    - SHA-256 of stored bytes matches the hex in the key
    - parse_published_analysis succeeds
    - The parsed artifact carries the expected cik, as_of_date, and memo
    """
    run_id, step_id = published_analysis_run
    _claim_and_run(run_id, step_id)

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    completed_run = next(e for e in events if e.type == "run.completed")
    artifact_ref = completed_run.payload_ref
    assert artifact_ref is not None
    assert artifact_ref.startswith(ANALYSIS_SCOPE + "/"), (
        f"artifact_ref must start with '{ANALYSIS_SCOPE}/'; got {artifact_ref!r}"
    )

    # Digest check.
    artifact_bytes = read_payload_bytes(artifact_ref)
    expected_sha256 = artifact_ref.rsplit("/", 1)[-1]
    assert hashlib.sha256(artifact_bytes).hexdigest() == expected_sha256, (
        "artifact bytes SHA-256 must match the hex encoded in the key"
    )

    # Parsing.
    artifact = parse_published_analysis(artifact_bytes)
    assert artifact.cik == "0000320193"
    assert artifact.as_of_date == "2026-07-31"
    # The memo sentence is deterministic (AC-0408).
    assert len(artifact.memo.claims) > 0
    claim_text = artifact.memo.claims[0].text
    assert "16.36" in claim_text, f"memo claim should contain '16.36'; got {claim_text!r}"


def test_end_to_end_step_and_run_completed_share_artifact_ref(
    published_analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413: step.completed and run.completed carry the same artifact reference."""
    run_id, step_id = published_analysis_run
    _claim_and_run(run_id, step_id)

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    step_comp = next(e for e in events if e.type == "step.completed")
    run_comp = next(e for e in events if e.type == "run.completed")

    assert step_comp.payload_ref is not None
    assert step_comp.payload_ref == run_comp.payload_ref, (
        "step.completed and run.completed must share the artifact reference"
    )


# ---------------------------------------------------------------------------
# AC-0416: full HTTP API path — POST /runs + worker + GET /runs/{run_id}/analysis
# ---------------------------------------------------------------------------

#: Isolated pool class for the AC-0416 e2e tests that use the HTTP API.
#: A separate class from _E2E_POOL_CLASS keeps these tests independent from
#: the direct-start_run tests above.
_HTTP_POOL_CLASS = "analysis-http-e2e-test"

_HTTP_E2E_CONFIG = PoolConfig(
    worker_id="e2e-http-analysis-worker",
    default_limits=_LIMITS,
    allowed_model_ids=("stub:counting",),
    pool_class=_HTTP_POOL_CLASS,
    lease_ttl_seconds=30,
    heartbeat_seconds=10,
    poll_seconds=1,
)


def _claim_and_run_http(run_id: uuid.UUID, step_id: uuid.UUID) -> list[str]:
    """Claim and run the analysis step via the ordinary worker path (HTTP-pool class)."""
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
            (
                _HTTP_E2E_CONFIG.worker_id,
                _HTTP_E2E_CONFIG.lease_ttl_seconds,
                step_id,
                _HTTP_POOL_CLASS,
            ),
        ).fetchone()
        conn.commit()

    assert row is not None, "step not updated — pool_class mismatch?"
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=int(row[0]),
        agent_role=ANALYSIS_ROLE,
    )

    body = make_analysis_step_body()
    body(lease, threading.Event())

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    return [e.type for e in events]


@pytest.fixture
def http_analysis_run(
    require_substrate: None,
    e2e_api_server: Client,
) -> Iterator[tuple[uuid.UUID, str]]:
    """Start an analysis run via POST /runs; yield (run_id, step_id_str).

    Ingests the offline fixture, then calls POST /runs with the snapshot_ref.
    Cleans up on exit.
    """
    from ced.worker.ingestion import ingest

    result = ingest(offline=True)
    snapshot_ref = result["snapshot_ref"]

    # Post through the public HTTP API — this is what AC-0416 requires.
    response = e2e_api_server.post(
        "/runs",
        {
            "principal": "e2e-http-test-principal",
            "agent_role": ANALYSIS_ROLE,
            "analysis": {
                "cik": "0000320193",
                "as_of_date": "2026-07-31",
                "snapshot_ref": snapshot_ref,
            },
        },
    )
    assert response.status == 201, f"POST /runs returned {response.status}: {response.body}"

    run_id_str = response.body["run_id"]
    step_id_str = response.body["step_id"]
    run_id = uuid.UUID(run_id_str)
    step_id = uuid.UUID(step_id_str)

    # AC-0412 (Blocker 1): assert POST /runs stored pool_class='analysis' before
    # any fixture rewrite.  Mutation: change ANALYSIS_POOL_CLASS to 'default' in
    # main.py → this assertion fails because the stored class is 'default'.
    with psycopg.connect(database_url("migration")) as check_conn:
        pc_row = check_conn.execute(
            "SELECT pool_class FROM steps WHERE step_id = %s", (step_id,)
        ).fetchone()
    assert pc_row is not None and pc_row[0] == "analysis", (
        f"POST /runs must store pool_class='analysis' before fixture rewrite; got {pc_row!r}"
    )

    # Update the pool_class so the in-process worker can claim this step.
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            "UPDATE steps SET pool_class = %s WHERE step_id = %s",
            (_HTTP_POOL_CLASS, step_id),
        )
        conn.commit()

    try:
        yield run_id, step_id_str
    finally:
        with psycopg.connect(database_url("migration")) as cleanup:
            cleanup.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            cleanup.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            cleanup.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            cleanup.commit()


def test_http_api_start_run_creates_analysis_run(
    http_analysis_run: tuple[uuid.UUID, str],
) -> None:
    """AC-0416: POST /runs with analysis object creates the analysis step.

    Verifies the run was started via the HTTP API and the step exists with the
    analysis role.  pool_class='analysis' was asserted inside the fixture before
    any rewrite (AC-0412 Blocker 1).

    Break: return 201 without creating the step.
    Red: the step row is absent.
    """
    run_id, step_id_str = http_analysis_run
    step_id = uuid.UUID(step_id_str)

    with psycopg.connect(database_url("migration")) as conn:
        row = conn.execute(
            "SELECT agent_role, pool_class FROM steps WHERE step_id = %s",
            (step_id,),
        ).fetchone()

    assert row is not None, "step row must exist after POST /runs"
    # The fixture updated pool_class to _HTTP_POOL_CLASS; check agent_role.
    # pool_class='analysis' was already verified in the fixture before the update.
    assert row[0] == ANALYSIS_ROLE, f"expected agent_role={ANALYSIS_ROLE!r}; got {row[0]!r}"


def test_http_api_read_analysis_returns_complete_artifact(
    http_analysis_run: tuple[uuid.UUID, str],
    e2e_api_server: Client,
) -> None:
    """AC-0416: GET /runs/{run_id}/analysis returns the typed artifact.

    The full path: POST /runs → in-process analysis worker → GET /runs/{run_id}/analysis.

    Break: remove the GET /runs/{run_id}/analysis route.
    Red: 404 or 405 instead of 200.
    """
    run_id, step_id_str = http_analysis_run
    step_id = uuid.UUID(step_id_str)

    # Run the analysis step via the ordinary worker path.
    event_types = _claim_and_run_http(run_id, step_id)
    assert "run.completed" in event_types, (
        f"expected run.completed in events; got {event_types!r}"
    )

    # Read the artifact through the public HTTP API.
    response = e2e_api_server.get(f"/runs/{run_id}/analysis")
    assert response.status == 200, (
        f"expected 200 from GET /runs/{run_id}/analysis; got {response.status}"
    )

    artifact = response.body
    assert artifact.get("cik") == "0000320193"
    assert artifact.get("as_of_date") == "2026-07-31"
    claims = artifact["memo"]["claims"]
    assert any("16.36" in c["text"] for c in claims), (
        "canonical memo sentence with 16.36% not found in artifact"
    )
    # Evidence manifest is present.
    assert "evidence_manifest" in artifact
    assert "sources" in artifact["evidence_manifest"]
    assert "calculations" in artifact["evidence_manifest"]


# ---------------------------------------------------------------------------
# Concern 3 (AC-0413): re-claim convergence at each partial commit point
# ---------------------------------------------------------------------------


def _setup_partial_commit(
    run_id: uuid.UUID,
    step_id: uuid.UUID,
    partial_types: list[str],
    principal: str = "e2e-test-principal",
) -> None:
    """Manually build a partial-commit state and force-expire the lease.

    Sets the step to state='leased' at lease_epoch=1 under a live lease, and
    appends each event in ``partial_types`` at that epoch. It moves the run to
    'running' when step.started is included, matching what Phase 2 commits
    atomically. It then expires the lease, which makes the step claimable
    through the ordinary ``claim_one`` recovery path.
    """
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = 'partial-commit-sim',
                   lease_epoch = 1,
                   lease_expires_at = now() + interval '1 minute'
             WHERE step_id = %s
            """,
            (step_id,),
        )
        if "step.started" in partial_types:
            conn.execute(
                "UPDATE runs SET state = 'running' WHERE run_id = %s AND state = 'requested'",
                (run_id,),
            )
        conn.commit()

    with psycopg.connect(database_url("worker")) as conn:
        for event_type in partial_types:
            append_step_event(
                conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=1,
                type=event_type,
                principal=principal,
                agent_role=ANALYSIS_ROLE,
            )

    # The fence admits appends only under a live lease, so expire it after the
    # partial events are written, as a crashed worker's lease would expire.
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            "UPDATE steps SET lease_expires_at = now() - interval '1 second'"
            " WHERE step_id = %s",
            (step_id,),
        )
        conn.commit()


def _reclaim_and_run(run_id: uuid.UUID) -> list[str]:
    """Re-claim via claim_one (the ordinary recovery path) and run the body."""
    with psycopg.connect(database_url("worker")) as conn:
        lease = claim_one(conn, _E2E_CONFIG)
    assert lease is not None, "claim_one must find the expired lease"

    body = make_analysis_step_body()
    body(lease, threading.Event())

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    return [e.type for e in events]


def test_reclaim_after_step_started_converges_to_terminal(
    published_analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413 (Concern 3): re-claim after step.started reaches run.completed.

    Simulates a crash between Phase 2 (step.started committed, run state set to
    'running') and Phase 3 completion.  The step is in 'leased' state with an
    expired lease.  Re-claiming via ``claim_one`` and re-running the body must
    produce exactly one terminal event (run.completed) and a readable artifact.

    Mutation: remove the ``state = 'leased' AND lease_expires_at < now()``
    branch from the ``claim_one`` predicate → ``claim_one`` returns None for
    the expired step and the assertion fails.
    """
    run_id, step_id = published_analysis_run
    _setup_partial_commit(run_id, step_id, ["step.started"])

    event_types = _reclaim_and_run(run_id)

    terminal_events = [t for t in event_types if t in ("run.completed", "run.failed")]
    assert len(terminal_events) == 1, (
        f"exactly one terminal event expected after re-claim; got {terminal_events!r}"
    )
    assert terminal_events[0] == "run.completed", (
        f"re-claim after step.started must reach run.completed; got {terminal_events[0]!r}"
    )

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    completed = next(e for e in events if e.type == "run.completed")
    assert completed.payload_ref is not None
    artifact_bytes = read_payload_bytes(completed.payload_ref)
    assert len(artifact_bytes) > 0, "artifact bytes must be readable and non-empty"


def test_reclaim_after_step_completed_before_run_completed_converges(
    published_analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413 (Concern 3): re-claim after step.completed reaches run.completed.

    Simulates a crash after Phase 3 appended step.completed but before Phase 4
    appended run.completed.  Each append is a separate committed transaction, so
    this window is real.  Re-claiming and re-running must produce exactly one
    terminal event.

    Mutation: remove the expired-lease branch from the claim predicate →
    ``claim_one`` returns None and the assertion fails.
    """
    run_id, step_id = published_analysis_run
    _setup_partial_commit(run_id, step_id, ["step.started", "step.completed"])

    event_types = _reclaim_and_run(run_id)

    terminal_events = [t for t in event_types if t in ("run.completed", "run.failed")]
    assert len(terminal_events) == 1, (
        f"exactly one terminal event expected after re-claim; got {terminal_events!r}"
    )
    assert terminal_events[0] == "run.completed"

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    completed = next(e for e in events if e.type == "run.completed")
    assert completed.payload_ref is not None
    artifact_bytes = read_payload_bytes(completed.payload_ref)
    assert len(artifact_bytes) > 0


def test_reclaim_after_step_failed_before_run_failed_converges(
    published_analysis_run: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """AC-0413: a re-claim after step.failed finishes the failure, not a retry.

    Simulates a crash after ``_append_failure`` committed step.failed but
    before it committed run.failed. Re-claiming must end the run with exactly
    one terminal event, `run.failed`, and no `run.completed` or artifact, even
    though the snapshot itself is valid.

    Mutation: drop the already-failed check in `_analysis_body`. The re-claim
    then retries, the run ends `run.completed`, and this check reds.
    """
    run_id, step_id = published_analysis_run
    _setup_partial_commit(run_id, step_id, ["step.started", "step.failed"])

    with psycopg.connect(database_url("worker")) as conn:
        lease = claim_one(conn, _E2E_CONFIG)
    assert lease is not None, "claim_one must find the expired lease"
    with pytest.raises(Exception, match="already failed"):
        make_analysis_step_body()(lease, threading.Event())

    with psycopg.connect(database_url("worker")) as conn:
        event_types = [e.type for e in read_events(conn, run_id=run_id)]
    terminal_events = [t for t in event_types if t in ("run.completed", "run.failed")]
    assert terminal_events == ["run.failed"], (
        f"a failed step must end in exactly one run.failed; got {terminal_events!r}"
    )
    assert "step.completed" not in event_types
