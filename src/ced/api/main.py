"""The HTTP surface: four routes, and nothing that reasons.

The `api` identity holds **no model authority** and no unqualified `events`
insert — it reaches the event log only through ``append_run_event`` and
``append_approval_decision``, whose grant sets are disjoint from the worker's.
Compromising the internet-facing component therefore yields no model access and
no ability to forge a policy decision. The grant tests in `tests/event_log` are
what assert that; this module is only the thing they constrain.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request

from ced.adapters.objectstore.client import write_payload
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
from ced.domain.events import APPROVAL_GRANTED, APPROVAL_REJECTED

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


@app.post(
    "/runs",
    status_code=201,
    response_model=StartedRun,
    operation_id="start_run",
    summary="Start a run",
    description=(
        "Commits the run row, its coordinator step and the `run.requested` "
        "event in one transaction. All three or none."
    ),
)
def start_run(request: StartRunRequest, conn: Conn) -> StartedRun:
    started = event_log.start_run(
        conn,
        run_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        principal=request.principal,
        agent_role=request.agent_role,
    )
    return StartedRun(run_id=started.run_id, step_id=started.step_id, seq=started.seq)


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
    # CSRF defence: the Origin header must match the server's own origin.
    # A non-browser caller can forge it; that is recorded and out of scope.
    # A missing Origin is also refused (AC-0328: "so is one carrying no Origin").
    origin = raw_request.headers.get("origin")
    if origin is None:
        raise HTTPException(status_code=400, detail="Origin header is required")
    host = raw_request.headers.get("host", "")
    scheme = raw_request.url.scheme
    expected_origin = f"{scheme}://{host}"
    if origin != expected_origin:
        raise HTTPException(
            status_code=400,
            detail=f"Origin {origin!r} does not match {expected_origin!r}",
        )

    # Verify the run and step exist.
    _require_run(conn, run_id)
    step_row = conn.execute(
        "SELECT 1 FROM steps WHERE step_id = %s AND run_id = %s",
        (step_id, run_id),
    ).fetchone()
    if step_row is None:
        raise HTTPException(status_code=404, detail="no such step in this run")

    # Pre-validate the suspension seq and the awaiting_decision flag before
    # write_payload. This is not a guard against unbounded object-store growth:
    # write_payload is content-addressed and the decision payload has only two
    # possible values (require_distinct_approver true or false), so at most two
    # distinct keys exist in the store ever. The ordering is correct anyway —
    # skipping a pointless PUT on a refusal is a small real gain, and the
    # admitted path still follows crash ordering:
    # write_payload runs before append_approval_decision below.
    awaiting_row = conn.execute(
        "SELECT awaiting_decision FROM steps WHERE step_id = %s AND run_id = %s",
        (step_id, run_id),
    ).fetchone()
    if awaiting_row is None or not awaiting_row[0]:
        raise HTTPException(
            status_code=409,
            detail="step is not currently awaiting a decision",
        )
    suspension_seq_row = conn.execute(
        "SELECT max(seq) FROM events WHERE step_id = %s AND type = 'step.suspended'",
        (step_id,),
    ).fetchone()
    if suspension_seq_row is None or suspension_seq_row[0] != request_body.suspension_seq:
        raise HTTPException(
            status_code=409,
            detail=(
                f"suspension_seq {request_body.suspension_seq!r} does not match "
                f"the step's latest suspension"
            ),
        )

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
