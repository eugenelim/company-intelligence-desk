"""The HTTP surface: four routes, and nothing that reasons.

The `api` identity holds **no model authority** and no unqualified `events`
insert — it reaches the event log only through ``append_run_event`` and
``append_approval_decision``, whose grant sets are disjoint from the worker's.
Compromising the internet-facing component therefore yields no model access and
no ability to forge a policy decision. The grant tests in `tests/event_log` are
what assert that; this module is only the thing they constrain.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ced.adapters.objectstore.client import (
    ObjectNotFoundError,
    ObjectStoreError,
    read_payload_bytes,
    read_payload_bytes_checked,
    write_payload,
)
from ced.adapters.postgres import event_log
from ced.adapters.postgres.dsn import database_url
from ced.api.models import (
    ApprovalDecisionRequest,
    DecisionResult,
    Event,
    EventPage,
    Snapshot,
    StartedRun,
    StartRunRequest,
)
from ced.api.stream import committed_event_stream, highest_committed_seq, selected_cursor
from ced.domain.diligence import DiligenceError, parse_published_analysis
from ced.domain.events import APPROVAL_GRANTED, APPROVAL_REJECTED
from ced.worker.analysis import ANALYSIS_ROLE
from ced.worker.pool import ANALYSIS_POOL_CLASS

log = logging.getLogger("ced.api.analysis")

#: Canonical company identifier accepted by the analysis route.
_CANONICAL_CIK = "0000320193"

#: Canonical as-of date accepted by the analysis route.
_CANONICAL_AS_OF = "2026-07-31"

#: Compiled pattern for snapshot reference validation.  Using ``fullmatch``
#: anchors at both ends without relying on ``$``, which matches before a
#: trailing newline and would admit ``"...<hex>\n"`` (AC-0411).
_SNAPSHOT_REF_RE = re.compile(r"ced-first-published-analysis-snapshot/[0-9a-f]{64}")

#: The exact key set `ced-ingest` writes into a snapshot manifest.
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


def _is_snapshot_manifest(manifest: object, *, cik: str, as_of_date: str) -> bool:
    """Whether parsed bytes are a snapshot manifest agreeing with the request.

    Any other object in the snapshot scope, such as filing bytes that happen to
    parse, fails here rather than reaching a run.
    """
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        return False
    if not all(isinstance(value, str) for value in manifest.values()):
        return False
    filing_ref = manifest["filing_ref"]
    return (
        manifest["schema_version"] == "1"
        and manifest["cik"] == cik
        and manifest["as_of_date"] == as_of_date
        and _SNAPSHOT_REF_RE.fullmatch(filing_ref) is not None
        and filing_ref.rsplit("/", 1)[-1] == manifest["filing_sha256"]
    )


#: Environment variable for the require_distinct_approver flag.
#: When set to "1", "true", or "yes" (case-insensitive), the approval route
#: refuses a decision whose principal matches the run's initiating principal.
#: The in-force value is written into every committed decision payload so the
#: deployed policy is recoverable from the log (AC-0303, entry 4 adjudication).
_REQUIRE_DISTINCT_APPROVER_VAR = "CED_REQUIRE_DISTINCT_APPROVER"


def _parse_require_distinct_approver() -> bool:
    """Read ``CED_REQUIRE_DISTINCT_APPROVER`` from the environment.

    An absent variable defaults to ``False`` (off).  Any recognised truthy
    string (``"1"``, ``"true"``, ``"yes"``, case-insensitive) enables the
    check; any recognised falsy string (``"0"``, ``"false"``, ``"no"``)
    disables it explicitly.  A present but unrecognised value raises
    ``ValueError`` naming the variable, so the process refuses at startup
    rather than silently misreading the operator's intent.
    """
    raw = os.environ.get(_REQUIRE_DISTINCT_APPROVER_VAR)
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized in ("1", "true", "yes"):
        return True
    if normalized in ("0", "false", "no"):
        return False
    raise ValueError(
        f"{_REQUIRE_DISTINCT_APPROVER_VAR}={raw!r} is not a recognised boolean; "
        "use '1', 'true', or 'yes' to enable, or '0', 'false', or 'no' to disable"
    )


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Parse deployment configuration at startup and store on app state.

    A malformed ``CED_REQUIRE_DISTINCT_APPROVER`` value causes this context
    manager to raise before yielding, which prevents the application from
    starting with a silently misread policy flag.
    """
    application.state.require_distinct_approver = _parse_require_distinct_approver()
    yield


#: The document's `info` block must match the committed contract, because
#: AC-0009 compares the served document against it.
app = FastAPI(
    title="Company Intelligence Desk — runs",
    version="0.1.0",
    description=(
        "Starting a run, reading its current state, and reading its event "
        "log. The event log is the system of record; the snapshot is a "
        "projection over it."
    ),
    lifespan=_lifespan,
)

_STATIC_ROOT = Path(__file__).resolve().parent / "static"
_STATIC_INDEX = _STATIC_ROOT / "index.html"

if _STATIC_ROOT.exists():
    app.mount(
        "/static",
        StaticFiles(directory=_STATIC_ROOT, html=False, follow_symlink=False),
        name="static",
    )


@contextmanager
def _connection() -> Iterator[psycopg.Connection]:
    """One short-lived connection per request.

    A pool belongs with the deployment, which this spec does not have. Named
    rather than hidden: r7 § Risks records managed-service connection pooling
    as untested, and pretending to solve it here would be worse than saying so.
    """
    with psycopg.connect(database_url("api")) as conn:
        yield conn


def get_connection() -> Iterator[psycopg.Connection]:
    with _connection() as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_connection)]


def _require_run(conn: psycopg.Connection, run_id: UUID) -> str:
    row = conn.execute("SELECT state FROM runs WHERE run_id = %s", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such run")
    return str(row[0])


def _expected_origin(request: Request) -> str:
    host = request.headers.get("host", "")
    scheme = request.url.scheme
    return f"{scheme}://{host}"


def _guard_same_origin(request: Request, *, require_origin: bool) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        if require_origin:
            raise HTTPException(status_code=400, detail="Origin header is required")
        return
    expected_origin = _expected_origin(request)
    if origin != expected_origin:
        raise HTTPException(
            status_code=400,
            detail=f"Origin {origin!r} does not match {expected_origin!r}",
        )


@app.post(
    "/runs",
    status_code=201,
    response_model=StartedRun,
    operation_id="start_run",
    summary="Start a run",
    description=(
        "Commits the run row, its coordinator step and the `run.requested` "
        "event in one transaction. All three or none. When `agent_role` is "
        "`first-published-analysis`, the `analysis` object is required and "
        "the snapshot it names is validated before the run is created."
    ),
    responses={
        400: {"description": "A present Origin header does not match the API's origin."},
        503: {
            "x-spec": (
                "docs/specs/first-published-analysis/spec.md"
                "#publishing-through-the-existing-run-boundary"
            ),
            "description": "Object store dependency unavailable.",
        },
    },
)
def start_run(request: StartRunRequest, raw_request: Request, conn: Conn) -> StartedRun:
    """AC-0411: start a run, optionally with an analysis snapshot."""
    _guard_same_origin(raw_request, require_origin=False)

    if request.agent_role == ANALYSIS_ROLE:
        # Analysis role requires the analysis object.
        if request.analysis is None:
            raise HTTPException(
                status_code=422,
                detail="analysis object is required for role first-published-analysis",
            )
        ana = request.analysis

        # Validate canonical values before any object-store access.
        if ana.cik != _CANONICAL_CIK:
            raise HTTPException(status_code=422, detail="unsupported cik")
        if ana.as_of_date != _CANONICAL_AS_OF:
            raise HTTPException(status_code=422, detail="unsupported as_of_date")
        if not _SNAPSHOT_REF_RE.fullmatch(ana.snapshot_ref):
            raise HTTPException(status_code=422, detail="malformed snapshot_ref")

        # Read and validate the snapshot from the object store.
        snapshot_ref = ana.snapshot_ref
        try:
            snapshot_bytes = read_payload_bytes_checked(snapshot_ref)
        except ObjectNotFoundError as exc:
            log.error(
                "analysis start_run: snapshot_not_found",
                extra={"reason_class": "snapshot_not_found"},
            )
            raise HTTPException(status_code=422) from exc
        except ObjectStoreError as exc:
            log.error(
                "analysis start_run: snapshot_store_unavailable",
                extra={"reason_class": "snapshot_store_unavailable"},
            )
            raise HTTPException(status_code=503) from exc

        # Verify raw-byte digest against the key before parsing.
        expected_sha256 = snapshot_ref.rsplit("/", 1)[-1]
        if hashlib.sha256(snapshot_bytes).hexdigest() != expected_sha256:
            log.error(
                "analysis start_run: snapshot_digest_mismatch",
                extra={"reason_class": "snapshot_digest_mismatch"},
            )
            raise HTTPException(status_code=422)

        # Parse the snapshot manifest and verify it agrees with the request.
        try:
            manifest = json.loads(snapshot_bytes)
        except Exception:
            log.error(
                "analysis start_run: snapshot_manifest_mismatch (not JSON)",
                extra={"reason_class": "snapshot_manifest_mismatch"},
            )
            raise HTTPException(status_code=422) from None

        if not _is_snapshot_manifest(manifest, cik=ana.cik, as_of_date=ana.as_of_date):
            log.error(
                "analysis start_run: snapshot_manifest_mismatch",
                extra={"reason_class": "snapshot_manifest_mismatch"},
            )
            raise HTTPException(status_code=422)

        # Write the request object — only the three canonical fields.
        # Object write precedes event append per r5 § 3: an unreferenced object
        # is less harmful than a dangling payload_ref on a committed event.
        # The request lives outside the snapshot scope, so a request reference
        # can never be offered back as a snapshot reference.
        try:
            request_ref = write_payload(
                {
                    "cik": ana.cik,
                    "as_of_date": ana.as_of_date,
                    "snapshot_ref": snapshot_ref,
                }
            )
        except Exception as exc:
            log.error(
                "analysis start_run: request_store_unavailable",
                extra={"reason_class": "request_store_unavailable"},
            )
            raise HTTPException(status_code=503) from exc

        started = event_log.start_run(
            conn,
            run_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            principal=request.principal,
            agent_role=request.agent_role,
            pool_class=ANALYSIS_POOL_CLASS,
            payload_ref=request_ref,
        )

    elif request.analysis is not None:
        # Any non-analysis role with an analysis object is refused.
        raise HTTPException(
            status_code=422,
            detail="analysis object is not allowed for this agent_role",
        )

    else:
        # Existing non-analysis behaviour unchanged.
        started = event_log.start_run(
            conn,
            run_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            principal=request.principal,
            agent_role=request.agent_role,
        )

    return StartedRun(run_id=started.run_id, step_id=started.step_id, seq=started.seq)


#: Terminal event types that mark a completed or failed run.
_TERMINAL_TYPES: frozenset[str] = frozenset({"run.completed", "run.failed"})


@app.get(
    "/runs/{run_id}/analysis",
    status_code=200,
    operation_id="read_analysis",
    summary="Read a completed analysis artifact",
    description=(
        "Returns the complete typed analysis artifact when the run completed "
        "successfully. No authentication is required: the artifact contains "
        "only public SEC evidence. The Phase 1 direct-read posture applies "
        "(AC-0415): any caller that can reach the loopback-bound API and knows "
        "a run id may read it. The response omits initiating-principal and "
        "SEC-contact values."
    ),
    openapi_extra={
        "x-spec": (
            "docs/specs/first-published-analysis/spec.md"
            "#publishing-through-the-existing-run-boundary"
        ),
    },
    responses={
        200: {
            "description": "The complete analysis artifact.",
            "content": {"application/json": {"schema": {"type": "object"}}},
        },
        404: {"description": "No such run."},
        409: {
            "description": (
                "Run is not completed, is not an analysis run, or the artifact "
                "reference is absent, unreadable, digest-mismatched, "
                "or schema-invalid."
            )
        },
    },
)
def read_analysis(run_id: UUID, conn: Conn) -> Any:
    """AC-0414/0415: return the typed artifact for a completed analysis run."""
    # 404 for unknown run.
    _require_run(conn, run_id)

    # Read all events to find the terminal event.
    events = event_log.read_events(conn, run_id=run_id)
    terminal = next((e for e in events if e.type in _TERMINAL_TYPES), None)

    if terminal is None:
        log.error(
            "analysis read: pending run_id=%s reason=run_pending",
            run_id,
            extra={"reason_class": "run_pending"},
        )
        raise HTTPException(status_code=409, detail="run is not yet completed")

    if terminal.type != "run.completed":
        log.error(
            "analysis read: failed terminal run_id=%s reason=run_failed",
            run_id,
            extra={"reason_class": "run_failed"},
        )
        raise HTTPException(status_code=409, detail="run did not complete successfully")

    # Non-analysis run: check agent_role on the terminal event.
    if terminal.agent_role != ANALYSIS_ROLE:
        log.error(
            "analysis read: non-analysis run_id=%s agent_role=%r reason=not_analysis_run",
            run_id,
            terminal.agent_role,
            extra={"reason_class": "not_analysis_run"},
        )
        raise HTTPException(status_code=409, detail="run is not an analysis run")

    # Missing artifact reference.
    if terminal.payload_ref is None:
        log.error(
            "analysis read: missing artifact ref run_id=%s reason=missing_artifact_ref",
            run_id,
            extra={"reason_class": "missing_artifact_ref"},
        )
        raise HTTPException(status_code=409, detail="artifact reference is absent")

    artifact_ref = terminal.payload_ref

    # Read raw artifact bytes from the object store.
    try:
        artifact_bytes = read_payload_bytes(artifact_ref)
    except Exception:
        log.error(
            "analysis read: object not found run_id=%s reason=artifact_not_found",
            run_id,
            extra={"reason_class": "artifact_not_found"},
        )
        raise HTTPException(status_code=409, detail="artifact not found") from None

    # Verify raw-byte digest against the key before parsing.
    expected_sha256 = artifact_ref.rsplit("/", 1)[-1]
    if hashlib.sha256(artifact_bytes).hexdigest() != expected_sha256:
        log.error(
            "analysis read: digest mismatch run_id=%s reason=artifact_digest_mismatch",
            run_id,
            extra={"reason_class": "artifact_digest_mismatch"},
        )
        raise HTTPException(status_code=409, detail="artifact digest mismatch")

    # Validate the full typed schema.
    try:
        parse_published_analysis(artifact_bytes)
    except DiligenceError:
        log.error(
            "analysis read: schema invalid run_id=%s reason=artifact_schema_invalid",
            run_id,
            extra={"reason_class": "artifact_schema_invalid"},
        )
        raise HTTPException(status_code=409, detail="artifact schema invalid") from None

    # Return the artifact as JSON. The artifact bytes are already canonical JSON.
    return json.loads(artifact_bytes)


@app.get(
    "/runs/{run_id}/snapshot",
    response_model=Snapshot,
    operation_id="read_snapshot",
    summary="Read a run's current state and cursor",
    description=(
        "A client uncertain of its cursor reads this, discards local state "
        "and resumes at `as_of_seq`. No cursor is refused on age."
    ),
    responses={404: {"description": "No such run."}},
)
def read_snapshot(run_id: UUID, conn: Conn) -> Snapshot:
    state = _require_run(conn, run_id)
    row = conn.execute(
        "SELECT coalesce(max(seq), 0) FROM events WHERE run_id = %s", (run_id,)
    ).fetchone()
    assert row is not None
    # `as_of_seq` is the highest *committed* seq, not `runs.next_seq`. They
    # differ while an append is in flight, and a client resuming from
    # `next_seq` would skip the event that append is about to commit.
    return Snapshot(run_id=run_id, state=state, as_of_seq=int(row[0]))


@app.get(
    "/runs/{run_id}/events",
    response_model=EventPage,
    operation_id="read_events",
    summary="Read a run's committed events in sequence order",
    responses={404: {"description": "No such run."}},
)
def read_events(
    run_id: UUID,
    conn: Conn,
    after: Annotated[
        int,
        Query(
            ge=0,
            description=(
                "Return events with `seq` strictly greater than this. The "
                "client owns the cursor."
            ),
        ),
    ] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
) -> EventPage:
    _require_run(conn, run_id)
    envelopes = event_log.read_events(conn, run_id=run_id, after=after, limit=limit)
    return EventPage(run_id=run_id, events=[Event.of(envelope) for envelope in envelopes])


@app.get(
    "/runs/{run_id}/events/stream",
    operation_id="stream_events",
    summary="Stream a run's committed events in sequence order",
    # Without this, FastAPI merges its default JSON response into the 200 entry
    # and the served document lists `application/json` beside
    # `text/event-stream`, which the committed contract does not.
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Committed events after the selected cursor. The stream closes after "
                "`run.completed`, `run.failed`, or `run.cancelled`."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        404: {"description": "No such run."},
        422: {
            "description": (
                "`run_id` is not a UUID; or **any supplied** cursor — `Last-Event-ID` "
                "or `after`, whether or not it is the one selected — is not a bare "
                "non-negative decimal integer; or the **selected** cursor is ahead of "
                "the run's highest committed sequence. A malformed `after` is refused "
                "even when a valid `Last-Event-ID` outranks it."
            )
        },
    },
)
def stream_events(
    request: Request,
    run_id: UUID,
    after: Annotated[
        int,
        Query(
            ge=0,
            description=(
                "Emit events with `seq` strictly greater than this cursor when no "
                "`Last-Event-ID` header is present. The value must not be greater "
                "than the run's highest committed sequence."
            ),
        ),
    ] = 0,
    last_event_id: Annotated[
        str | None,
        Header(
            alias="Last-Event-ID",
            description=(
                "Preferred resume cursor. It must be a non-negative integer no "
                "greater than the run's highest committed sequence."
            ),
        ),
    ] = None,
) -> StreamingResponse:
    # Validate run existence and cursor on a short-lived connection that is
    # released *before* the StreamingResponse is constructed.  A generator
    # dependency (conn: Conn) is closed only after the response completes —
    # which for a non-terminal run never happens — so using one here would
    # leave a connection idle in transaction for the stream's whole lifetime.
    with _connection() as conn:
        _require_run(conn, run_id)
        # The typed `after` above is what the generated schema publishes
        # (`integer, minimum: 0`), but its *value* is already coerced: pydantic's
        # lax `int` turns `0_1`, `1.0` and `+1` into 1 before this line runs.
        # The raw query string is what the caller sent, so that is what the
        # cursor guard judges — one lexical predicate for both sources. Every
        # `after` value is passed, not only the last: a repeated parameter
        # binds just its last value, so `?after=x&after=1` would otherwise
        # escape the check that `?after=1&after=x` fails.
        raw_after = request.query_params.getlist("after")
        cursor = selected_cursor(raw_after, last_event_id, highest_committed_seq(conn, run_id))
    # The connection is closed here; the generator opens its own per-poll.
    return StreamingResponse(
        committed_event_stream(_connection, run_id=run_id, after=cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )


@app.get(
    "/runs/{run_id}",
    include_in_schema=False,
)
def read_run_page(run_id: str, conn: Conn) -> FileResponse:
    """Serve the browser client for a run, answering ``404`` when it does not exist.

    An unknown run still receives the page, with status ``404`` (AC-0338). The
    page's own history request then fails and the client shows the state
    matrix's Unavailable outcome — an error naming that request and a retry
    control — instead of a bare JSON body no reader can act on.

    ``run_id`` is taken as a string and parsed here, not by FastAPI, so a
    malformed id names no run and gets the same ``404`` page rather than the
    framework's JSON ``422``: the matrix routes an invalid run to Unavailable.
    """
    try:
        _require_run(conn, UUID(run_id))
        status_code = 200
    except ValueError:
        status_code = 404
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        status_code = 404
    if not _STATIC_INDEX.is_file():
        raise HTTPException(status_code=503, detail="browser client is not built")
    return FileResponse(_STATIC_INDEX, status_code=status_code, media_type="text/html")


@app.post(
    "/runs/{run_id}/steps/{step_id}/decision",
    status_code=200,
    response_model=DecisionResult,
    operation_id="record_approval_decision",
    summary="Record an approval decision for a suspended step",
    description=(
        "Grants or rejects pending tool calls for a suspended step. "
        "The request must name the `seq` of the `step.suspended` event it "
        "answers; a decision against an outdated suspension is refused. "
        "The `Origin` header must match the API's own origin; a missing or "
        "foreign origin is refused (CSRF defence, AC-0328)."
    ),
    responses={
        400: {"description": "Origin header absent or does not match."},
        404: {"description": "No such run or step."},
        409: {
            "description": (
                "Decision refused (wrong suspension seq, not awaiting, or malformed)."
            )
        },
        422: {"description": "Request body is not valid."},
    },
)
def record_approval_decision(
    run_id: UUID,
    step_id: UUID,
    request_body: ApprovalDecisionRequest,
    raw_request: Request,
    conn: Conn,
) -> DecisionResult:
    """AC-0328: receive and commit the approver's decision."""
    # CSRF defence: a present Origin must match the server's own origin. The
    # approval path also keeps its stricter shipped policy and refuses absence.
    _guard_same_origin(raw_request, require_origin=True)

    # Verify the run and step exist.
    _require_run(conn, run_id)
    step_row = conn.execute(
        "SELECT 1 FROM steps WHERE step_id = %s AND run_id = %s",
        (step_id, run_id),
    ).fetchone()
    if step_row is None:
        raise HTTPException(status_code=404, detail="no such step in this run")

    # Entry 4 (adjudication): require_distinct_approver — read the in-force
    # value from deployment configuration (app.state), not from the request.
    # The deployment configures the policy; the caller cannot select it.
    # Written into the decision payload so the committed event is self-describing
    # (AC-0303): a module constant cannot satisfy this because the test
    # configures the flag both ways and reads back two different payload values.
    require_distinct = getattr(raw_request.app.state, "require_distinct_approver", False)
    if require_distinct:
        try:
            initiating_principal = event_log.read_run_principal(conn, run_id=run_id)
        except event_log.PrincipalNotRecorded as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if request_body.principal == initiating_principal:
            raise HTTPException(
                status_code=409,
                detail=(
                    "require_distinct_approver is set: the approver principal "
                    "must differ from the run's initiating principal"
                ),
            )

    # Write the decision metadata payload before the fenced append (crash
    # ordering: an unreferenced object is less harmful than a dangling
    # payload_ref). The payload carries the in-force require_distinct_approver
    # value so the committed event is self-describing (AC-0303, entry 4).
    decision_payload_ref = write_payload(
        {
            "schema_version": 1,
            "require_distinct_approver": require_distinct,
        }
    )

    # Build parallel call_ids and decisions lists from the request body.
    call_ids = [pair.call_id for pair in request_body.decisions]
    decisions = [
        APPROVAL_GRANTED if pair.granted else APPROVAL_REJECTED
        for pair in request_body.decisions
    ]

    try:
        last_seq = event_log.append_approval_decision(
            conn,
            run_id=run_id,
            step_id=step_id,
            call_ids=call_ids,
            decisions=decisions,
            principal=request_body.principal,
            suspension_seq=request_body.suspension_seq,
            payload_ref=decision_payload_ref,
        )
    except event_log.DecisionRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except event_log.StepRunMismatch as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DecisionResult(last_seq=last_seq)


def run() -> None:
    """The `ced-api` entry point. One of the two deployables from one image.

    Host and port come from the environment because two deployables share one
    developer machine and 8000 is the most contended port on it. Loopback by
    default: nothing here is authenticated, and r7 puts OIDC at the ingress.
    """
    import os

    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("CED_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("CED_API_PORT", "8000")),
    )
