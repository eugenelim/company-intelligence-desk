"""The HTTP surface: three routes, and nothing that reasons.

The `api` identity holds **no model authority** and no unqualified `events`
insert — it reaches the event log only through `append_run_event`, which admits
exactly `run.requested` and `run.cancelled`. Compromising the internet-facing
component therefore yields no model access and no ability to forge a policy
decision. The grant tests in `tests/event_log` are what assert that; this
module is only the thing they constrain.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from ced.adapters.postgres import event_log
from ced.adapters.postgres.dsn import database_url
from ced.api.models import Event, EventPage, Snapshot, StartedRun, StartRunRequest

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


@app.exception_handler(psycopg.errors.UniqueViolation)
def _unique_violation(request: object, exc: psycopg.errors.UniqueViolation) -> JSONResponse:
    """A collision is a conflict, not a server fault.

    The detail deliberately omits the database message: it names roles,
    functions and constraint identifiers, and this handler sits on the
    internet-facing surface.
    """
    return JSONResponse(status_code=409, content={"detail": "conflict"})


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
