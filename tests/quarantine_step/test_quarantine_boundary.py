"""AC-0222 and AC-0242: the quarantine boundary holds through a running step.

AC-0222: the quarantined step's admitted values are present in the assembled
context after a round trip through the database, and none of the fixture's
distinctive free text appears there.  Both halves are asserted — the absence
half alone is satisfied by an assembler that passes nothing through, which is
a severed channel rather than a held boundary.

AC-0242: a refused quarantine output records its rejection without the refused
text reaching the event log or any payload object an event of that run
references.  The quarantine output payload is the artifact T5 introduces;
without it the payload-search arm would be vacuous.

Needs Postgres and MinIO up.  See ``AGENTS.md`` § The local substrate.
"""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any

import psycopg
import pytest

from ced.adapters.objectstore.client import read_payload
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import read_events, start_run
from ced.worker.context import assemble_planning_context
from ced.worker.executor import _StepBodyFailed, make_step_body
from ced.worker.pool import Lease, PoolConfig

pytestmark = pytest.mark.substrate

#: Isolated pool class — compose workers never see this class.
_POOL_CLASS = "t5-quarantine-boundary"
_ROLE_NAME = "t5-quarantine-boundary-role"
_PRINCIPAL = "t5-boundary-principal"

_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}

#: Text that would appear in the planning context if the boundary failed.
#: Must not appear in any assembled context, event, or payload.
_DISTINCTIVE_FREE_TEXT = "Apple_reported_record_revenue_AC0242_DISTINCTIVE"

#: A closed-vocabulary label that the assembler admits without a candidate set.
_ADMITTED_LABEL = "revenue-recognition"


def _make_function_model(references: list[str]) -> Any:
    """Build a ``FunctionModel`` that outputs ``ReferenceSelection(references=...)``.

    Uses pydantic_ai's ``FunctionModel`` + ``ToolCallPart`` pattern from
    ``tests/compiler/role_records.py`` so the test controls the output exactly.
    """
    from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"references": references})]
        )

    return FunctionModel(respond)


def _insert_quarantine_role(role_name: str, model_id: str = "stub:counting") -> None:
    """Insert (or update) a quarantine role record using the migration identity."""
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            """
            INSERT INTO agent_role
                (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
            VALUES (%s, 1, '[]'::jsonb, '', %s::jsonb, 'reference-selection')
            ON CONFLICT (role_name, version) DO UPDATE
                SET model_settings = EXCLUDED.model_settings
            """,
            (
                role_name,
                json.dumps({"model_id": model_id, "settings": {}, "limits": {}}),
            ),
        )
        conn.commit()


def _start_and_claim(
    role_name: str,
    model: Any,
) -> tuple[Lease, PoolConfig, uuid.UUID]:
    """Insert a run + step, claim it under the isolated pool class, and return.

    The returned ``PoolConfig`` wires ``model`` via ``model_factory`` so the
    executor drives the stub rather than a provider.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_PRINCIPAL,
            agent_role=role_name,
        )

    config = PoolConfig(
        worker_id="t5-boundary-worker",
        default_limits=_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _mid: model,
        pool_class=_POOL_CLASS,
    )

    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = %s,
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + interval '300 seconds',
                   pool_class = %s
             WHERE step_id = %s
             RETURNING lease_epoch
            """,
            (config.worker_id, _POOL_CLASS, step_id),
        ).fetchone()
        conn.commit()

    assert row is not None, "step row not found after start_run"
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=int(row[0]),
        agent_role=role_name,
    )
    return lease, config, run_id


def _cleanup(run_id: uuid.UUID) -> None:
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
        conn.commit()


@pytest.fixture(autouse=True)
def _ensure_role(require_substrate: None) -> None:
    """Insert the shared quarantine role before each test in this module."""
    _insert_quarantine_role(_ROLE_NAME)


# ---------------------------------------------------------------------------
# AC-0222
# ---------------------------------------------------------------------------


def test_admitted_values_present_after_db_round_trip(
    require_substrate: None,
) -> None:
    """AC-0222: admitted values in the context, no distinctive free text, after DB round trip.

    The quarantined step outputs a closed-vocabulary label (``revenue-recognition``),
    which the context assembler admits.  The executor writes the output payload and
    commits ``step.completed``.  The test reads the output payload back from the
    object store — the database round trip — and calls the assembler on the
    retrieved content.

    Presence half: ``revenue-recognition`` is in the assembled context.
    Absence half: the distinctive filing text is not in the assembled context.
    """
    model = _make_function_model([_ADMITTED_LABEL])
    lease, config, run_id = _start_and_claim(_ROLE_NAME, model)
    try:
        body = make_step_body(config)
        body(lease, threading.Event())

        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)

        completed = [e for e in events if e.type == "step.completed"]
        assert len(completed) == 1, (
            f"expected exactly one step.completed; got {[e.type for e in events]}"
        )
        payload_ref = completed[0].payload_ref
        assert payload_ref is not None, (
            "step.completed must carry a payload_ref (quarantine output written before append)"
        )

        # Round trip: read the quarantine output back from the object store.
        output_payload = read_payload(payload_ref)
        assembled = assemble_planning_context(output_payload)

        # Presence half: the admitted label must be in the assembled context.
        assert _ADMITTED_LABEL in assembled, (
            f"expected {_ADMITTED_LABEL!r} in assembled context; got {assembled!r}"
        )
        # Absence half: distinctive filing free text must not appear.
        assert _DISTINCTIVE_FREE_TEXT not in assembled, (
            "distinctive free text must not cross into the planning context"
        )
    finally:
        _cleanup(run_id)


# ---------------------------------------------------------------------------
# AC-0242
# ---------------------------------------------------------------------------


def test_refused_output_leaves_no_trace_in_events_or_payloads(
    require_substrate: None,
) -> None:
    """AC-0242: a refused quarantine output never reaches any stored artifact.

    The quarantined step's model outputs the distinctive free text.  The
    context assembler refuses it.  The executor writes ``step.failed`` with no
    output payload.

    The test searches every event for the run and every payload object those
    events reference.  The distinctive text must not appear in any of them.
    """
    model = _make_function_model([_DISTINCTIVE_FREE_TEXT])
    lease, config, run_id = _start_and_claim(_ROLE_NAME, model)
    try:
        body = make_step_body(config)
        # Entry 11 (adjudication): the executor raises _StepBodyFailed so the
        # pool records outcome = "failed" rather than "completed". The test
        # catches the exception and proceeds to assert no durable artifact holds
        # the distinctive text (AC-0242).
        try:
            body(lease, threading.Event())
        except _StepBodyFailed:
            pass

        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)

        failed = [e for e in events if e.type == "step.failed"]
        assert len(failed) == 1, (
            f"expected exactly one step.failed; got {[e.type for e in events]}"
        )
        assert failed[0].payload_ref is None, (
            "step.failed must carry no payload_ref — the refused text must not be written"
        )

        # Search every event field for the distinctive text.
        for ev in events:
            for field_value in (ev.type, ev.principal, ev.agent_role, ev.payload_ref):
                if field_value is None:
                    continue
                assert _DISTINCTIVE_FREE_TEXT not in str(field_value), (
                    f"distinctive text found in event field {field_value!r}"
                )

        # Search every payload object referenced by an event.
        refs = [ev.payload_ref for ev in events if ev.payload_ref is not None]
        for ref in refs:
            payload = read_payload(ref)
            payload_text = json.dumps(payload)
            assert _DISTINCTIVE_FREE_TEXT not in payload_text, (
                f"distinctive text found in payload {ref!r}: {payload_text!r}"
            )
    finally:
        _cleanup(run_id)
