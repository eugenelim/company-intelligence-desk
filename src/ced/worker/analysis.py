"""Analysis step body: deterministic publication under the lease fence.

Dispatched by the pool's ``run()`` when ``CED_POOL_CLASS=analysis``.  This
module owns the analysis path end-to-end:

1. Read the run's initiating principal and the request payload reference from
   the committed ``run.requested`` event.
1b. Check ``lease.agent_role == ANALYSIS_ROLE``; a mismatch commits
    ``step.started`` then appends fenced failure events before raising.
1c. Validate the ``payload_ref`` is present; a missing ref commits
    ``step.started`` then appends fenced failure events before raising.
2. Append ``step.started`` atomically with the requested→running state change,
   exactly as the model executor does.
3. Load the request object from the object store; extract ``cik``,
   ``as_of_date``, and ``snapshot_ref``.
4. Load raw snapshot manifest bytes; recompute SHA-256 and verify against the
   key encoded in ``snapshot_ref``.
5. Load raw filing bytes from the manifest's ``filing_ref``; recompute SHA-256
   and verify against both the key and the manifest's ``filing_sha256`` field.
6. Verify manifest ``cik`` and ``as_of_date`` agree with the request.
7. Call ``build_published_analysis`` and ``canonical_bytes``.
8. Write the artifact bytes to the object store under ``ANALYSIS_SCOPE``.
9. Append ``step.completed`` and ``run.completed`` with the artifact reference,
   both fenced on the lease epoch.

Any failure at steps 3–8 appends fenced ``step.failed`` followed by terminal
``run.failed`` through the existing run-terminal path, then re-raises so the
pool records the step as failed.  No partial artifact is ever stored without a
reference, no ``run.completed`` is ever appended after a failure, and the run is
always left terminal.

AC-0413, AC-0418.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading

import psycopg

from ced.adapters.objectstore.client import (
    ANALYSIS_SCOPE,
    READINESS_SCOPE,
    head_object,
    read_payload,
    read_payload_bytes,
    write_payload_bytes,
)
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import (
    append_run_terminal,
    append_step_event,
    read_run_principal,
)
from ced.domain.diligence import DiligenceError, build_published_analysis, canonical_bytes
from ced.worker.pool import Lease, StepBody

log = logging.getLogger("ced.worker.analysis")

#: The only agent role this body handles.
ANALYSIS_ROLE: str = "first-published-analysis"

#: Fixed bytes for the AC-0418 readiness sentinel.
READINESS_BYTES: bytes = b"ced-object-store-readiness-v1"


class _AnalysisBodyFailed(Exception):
    """Raised to signal the pool to record the step as failed.

    Mirrors ``executor._StepBodyFailed``: the pool's body wrapper catches any
    ``Exception`` and records ``outcome = "failed"``, which causes
    ``steps.state`` to be set to ``'failed'``.
    """


def ensure_readiness() -> None:
    """AC-0418: idempotently ensure bucket, write sentinel, head-check it.

    Called by ``pool.run()`` after database boot checks and before the poll
    loop starts.  ``write_payload_bytes`` calls ``_ensure_bucket`` internally,
    so a clean MinIO store needs no separate provisioning step.

    Raises any ``botocore.exceptions.ClientError`` or connection error on
    bucket, put, or head failure — each of which prevents the poll loop from
    starting, leaving seeded analysis work unclaimed.
    """
    key = write_payload_bytes(READINESS_BYTES, owner_scope=READINESS_SCOPE)
    head_object(key)
    log.info("readiness: sentinel written and verified at %s", key)


def _append_failure(
    lease: Lease,
    principal: str,
) -> None:
    """Append fenced ``step.failed`` then terminal ``run.failed``.

    Both are committed through the existing append functions so the fence
    check applies.  A ``Fenced`` exception from either append propagates to
    the caller; the pool handles it as a normal abandon.
    """
    with psycopg.connect(database_url("worker")) as conn:
        append_step_event(
            conn,
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            type="step.failed",
            principal=principal,
            agent_role=ANALYSIS_ROLE,
        )
        append_run_terminal(
            conn,
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            type="run.failed",
            principal=principal,
            agent_role=ANALYSIS_ROLE,
        )


def _commit_step_started(lease: Lease, principal: str) -> None:
    """Commit ``step.started`` atomically with the ``requested`` → ``running`` state change."""
    with psycopg.connect(database_url("worker")) as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE runs SET state = 'running' WHERE run_id = %s AND state = 'requested'",
                (lease.run_id,),
            )
            append_step_event(
                conn,
                run_id=lease.run_id,
                step_id=lease.step_id,
                lease_epoch=lease.epoch,
                type="step.started",
                principal=principal,
                agent_role=ANALYSIS_ROLE,
            )


def _analysis_body(lease: Lease, stop: threading.Event) -> None:
    """Execute one analysis step end-to-end under the lease fence."""
    # ── Phase 1: read durable identifiers from the event log ────────────────
    with psycopg.connect(database_url("worker")) as conn:
        try:
            principal = read_run_principal(conn, run_id=lease.run_id)
        except Exception as exc:
            # No event can be built without the principal, so the run stays
            # non-terminal. Raising makes the pool record the step as failed.
            log.error(
                "analysis: could not read principal for run %s — abandoning",
                lease.run_id,
            )
            raise _AnalysisBodyFailed("principal unreadable") from exc

        row = conn.execute(
            "SELECT payload_ref FROM events"
            " WHERE run_id = %s AND type = 'run.requested'"
            " ORDER BY seq LIMIT 1",
            (lease.run_id,),
        ).fetchone()
        conn.commit()

    # ── Phase 1b: role dispatch ──────────────────────────────────────────────
    # This body handles only ANALYSIS_ROLE.  An unexpected role is a fatal
    # configuration error: commit step.started (requested→running) then fail
    # terminally so the run is never left non-terminal.
    if lease.agent_role != ANALYSIS_ROLE:
        log.error(
            "analysis: step %s has unexpected role %r (expected %r) — failing",
            lease.step_id,
            lease.agent_role,
            ANALYSIS_ROLE,
        )
        _commit_step_started(lease, principal)
        _append_failure(lease, principal)
        raise _AnalysisBodyFailed(
            f"analysis body dispatched for unexpected role {lease.agent_role!r}"
        )

    # ── Phase 1c: validate request payload_ref ───────────────────────────────
    # A missing payload_ref cannot be recovered without re-running the request.
    # Commit step.started then fail terminally so the run is never left in the
    # 'requested' state (non-terminal).
    if row is None or row[0] is None:
        log.error(
            "analysis: no request payload_ref on run.requested for run %s — failing",
            lease.run_id,
        )
        _commit_step_started(lease, principal)
        _append_failure(lease, principal)
        raise _AnalysisBodyFailed("no request payload_ref on run.requested")

    request_ref = str(row[0])

    # ── Phase 2: commit step.started + requested→running atomically ─────────
    _commit_step_started(lease, principal)

    # ── Phase 3: load, verify, compute, store ───────────────────────────────
    try:
        # Load the request object.
        request_obj = read_payload(request_ref)
        cik = str(request_obj["cik"])
        as_of_date = str(request_obj["as_of_date"])
        snapshot_ref = str(request_obj["snapshot_ref"])

        # Load raw snapshot manifest bytes; verify digest against key.
        snapshot_bytes = read_payload_bytes(snapshot_ref)
        snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        expected_snapshot_sha256 = snapshot_ref.rsplit("/", 1)[-1]
        if snapshot_sha256 != expected_snapshot_sha256:
            raise DiligenceError(
                f"snapshot digest mismatch: computed {snapshot_sha256!r} "
                f"but key encodes {expected_snapshot_sha256!r}"
            )

        manifest = json.loads(snapshot_bytes)

        # Verify manifest agrees with request.
        if manifest.get("cik") != cik:
            raise DiligenceError(
                f"manifest cik {manifest.get('cik')!r} disagrees with request cik {cik!r}"
            )
        if manifest.get("as_of_date") != as_of_date:
            raise DiligenceError(
                f"manifest as_of_date {manifest.get('as_of_date')!r} "
                f"disagrees with request as_of_date {as_of_date!r}"
            )

        # Load raw filing bytes; verify digest against key and manifest field.
        filing_ref = str(manifest["filing_ref"])
        filing_bytes = read_payload_bytes(filing_ref)
        filing_sha256 = hashlib.sha256(filing_bytes).hexdigest()

        expected_filing_key_sha256 = filing_ref.rsplit("/", 1)[-1]
        if filing_sha256 != expected_filing_key_sha256:
            raise DiligenceError(
                f"filing digest mismatch against key: computed {filing_sha256!r} "
                f"but key encodes {expected_filing_key_sha256!r}"
            )

        manifest_filing_sha256 = str(manifest.get("filing_sha256", ""))
        if filing_sha256 != manifest_filing_sha256:
            raise DiligenceError(
                f"filing digest mismatch against manifest: computed {filing_sha256!r} "
                f"but manifest records {manifest_filing_sha256!r}"
            )

        # Build and serialize the deterministic artifact.
        artifact = build_published_analysis(
            filing_html=filing_bytes,
            filing_sha256=filing_sha256,
            source_url=str(manifest["source_url"]),
            as_of_date=as_of_date,
            filing_ref=filing_ref,
        )
        artifact_bytes = canonical_bytes(artifact)

        # Write artifact before the fenced append that references it.
        artifact_ref = write_payload_bytes(artifact_bytes, owner_scope=ANALYSIS_SCOPE)

    except Exception as exc:
        log.error("analysis: step %s failed: %s", lease.step_id, exc)
        _append_failure(lease, principal)
        raise _AnalysisBodyFailed("analysis step failed") from exc

    # ── Phase 4: commit step.completed + run.completed ──────────────────────
    with psycopg.connect(database_url("worker")) as conn:
        append_step_event(
            conn,
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            type="step.completed",
            principal=principal,
            agent_role=ANALYSIS_ROLE,
            payload_ref=artifact_ref,
        )
        append_run_terminal(
            conn,
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            type="run.completed",
            principal=principal,
            agent_role=ANALYSIS_ROLE,
            payload_ref=artifact_ref,
        )
    log.info("analysis: step %s completed; artifact at %s", lease.step_id, artifact_ref)


def make_analysis_step_body() -> StepBody:
    """Return the step body for the ``analysis`` pool class.

    The returned callable matches the ``StepBody`` protocol: it receives the
    claimed ``Lease`` and a stop ``threading.Event`` and returns ``None``.
    It opens its own database connections per call, never holds one across the
    object-store or computation phases.
    """
    return _analysis_body
