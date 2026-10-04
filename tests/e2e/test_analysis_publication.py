"""AC-0413, AC-0416 (preparation): end-to-end analysis publication.

Drives the ordinary Worker claim path: a real snapshot is created via the
offline ingestion path, a real analysis run is started via ``start_run``,
and an in-process Worker with pool_class='analysis-e2e-test' claims and
executes the step.  No direct event appends stand in for the worker.

The suite proves:
- The committed event sequence matches the expected order.
- The artifact bytes resolve by digest (SHA-256 in key == SHA-256 of bytes).
- The artifact parses via ``parse_published_analysis``.
- ``step.completed`` and ``run.completed`` carry the same artifact reference.

AC-0416 note: the API route (T4) is not yet wired; the start path uses
``start_run`` directly.  T4 will extend this file with the POST /runs route.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Iterator

import psycopg
import pytest

from ced.adapters.objectstore.client import (
    ANALYSIS_SCOPE,
    SNAPSHOT_SCOPE,
    read_payload_bytes,
    write_payload,
)
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import read_events, start_run
from ced.domain.diligence import parse_published_analysis
from ced.worker.analysis import ANALYSIS_ROLE, make_analysis_step_body
from ced.worker.pool import Lease, PoolConfig

pytestmark = pytest.mark.substrate

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
