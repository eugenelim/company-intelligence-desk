"""AC-0237 and AC-0333 — a suspended step releases its lease; a decision clears the guard.

The step body is run with a ``TestModel`` whose default ``call_tools='all'``
causes it to call ``request_approval`` immediately.  The executor detects the
``DeferredToolRequests`` output, writes a suspension payload to the object
store, appends a fenced ``step.suspended`` event, sets ``awaiting_decision =
true``, and releases the lease by clearing ``owner`` — so the pool's subsequent
``release`` call (fenced on the old owner) is a silent no-op.

The test asserts:
- A ``step.suspended`` event with a non-null ``payload_ref`` is present in the
  event log (the event exists before the lease is cleared, by code ordering).
- The steps row has ``state = 'runnable'``, ``owner = NULL``,
  ``lease_expires_at = NULL`` after the body returns.
- **AC-0333:** A second worker cannot claim the step while ``awaiting_decision =
  true`` — the pool's ``AND NOT awaiting_decision`` predicate blocks it.
- After a decision is committed (clearing ``awaiting_decision``), the same
  second worker CAN claim the step via ``claim_one``.

Needs Postgres and MinIO up.  See ``AGENTS.md`` § The local substrate.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import append_approval_decision, read_events, start_run
from ced.domain.events import APPROVAL_GRANTED
from ced.worker.executor import make_step_body
from ced.worker.persistence import load_suspension_payload
from ced.worker.pool import Lease, PoolConfig, claim_one

pytestmark = pytest.mark.substrate

#: Isolated pool class — compose workers never see this class, so no
#: interference from the fault-injection suite.
_POOL_CLASS = "t2-suspension"
_ROLE_NAME = "t2-suspension-check"
_PRINCIPAL = "t2-test-principal"

_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}


@pytest.fixture
def suspension_step(
    owner_conn: psycopg.Connection,
) -> Iterator[tuple[Lease, PoolConfig, uuid.UUID]]:
    """Insert a runnable step, manually claim it, and yield (lease, config, run_id).

    The role record uses ``stub:counting`` as model_id; the pool's
    ``model_factory`` returns a ``TestModel`` so the executor calls no
    provider.  ``non_provider_model_ids`` declares that id so the
    reasoning-disable guard is satisfied.

    Cleanup removes all rows for the run regardless of outcome.
    """
    from pydantic_ai.models.test import TestModel

    # Insert the role record using the migration (owner) identity — app_api
    # and app_worker hold only SELECT on agent_role.
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
                _ROLE_NAME,
                json.dumps(
                    {
                        "model_id": "stub:counting",
                        "settings": {},
                        "limits": {},
                        # needs_approval=True so check_prerelease_failed returns True
                        # and the executor offers the gated tool to TestModel (AC-0302).
                        "needs_approval": True,
                    }
                ),
            ),
        )
        conn.commit()

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_PRINCIPAL,
            agent_role=_ROLE_NAME,
        )

    config = PoolConfig(
        worker_id="t2-worker-a",
        default_limits=_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _model_id: TestModel(),
        pool_class=_POOL_CLASS,
    )

    # Claim the step manually on the isolated pool class so the compose
    # workers cannot grab it.
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
        agent_role=_ROLE_NAME,
    )

    try:
        yield lease, config, run_id
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()


def test_a_step_suspends_releases_its_lease_and_is_claimable(
    suspension_step: tuple[Lease, PoolConfig, uuid.UUID],
    owner_conn: psycopg.Connection,
) -> None:
    """The suspended step's event is recorded; after a decision the step is claimable.

    Four assertions in order:

    1. ``step.suspended`` event present with a non-null ``payload_ref`` —
       the payload write happened before the fenced append.
    2. The steps row has its lease released: ``state = 'runnable'``, ``owner =
       NULL``, ``lease_expires_at = NULL``.
    3. **AC-0333:** A second worker cannot claim the step while
       ``awaiting_decision = true`` — ``claim_one`` must return ``None``.
    4. After a decision is committed (clearing ``awaiting_decision``), the
       same second worker claims the step successfully via ``claim_one``.

    **Open conflict with AC-0237 (claimability half).** The shipped
    step-lifecycle spec (``walking-skeleton-step-lifecycle``) was amended in
    commit ffeb5e1 to clarify that AC-0237 covers only the lease-release half,
    not claimability. That amendment is logged but the step-lifecycle spec's
    AC-0237 text still refers to claimability in some forms. This test's name
    (``..._releases_its_lease_and_is_claimable``) asserts assertion 4
    (claimable after decision), which is AC-0333's scope, not AC-0237's. The
    name is preserved to avoid churn; the behaviour is correct.
    """
    lease, config, run_id = suspension_step

    # Run the body synchronously.  TestModel calls request_approval → the
    # executor detects DeferredToolRequests and takes the suspension path.
    body = make_step_body(config)
    body(lease, threading.Event())

    # Assertion 1: step.suspended event exists with a payload_ref.
    # Reading before checking the lease proves the event was committed before
    # the lease was cleared (by code ordering in the executor).
    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    suspended = [e for e in events if e.type == "step.suspended"]
    assert len(suspended) == 1, (
        f"expected exactly 1 step.suspended event, got {[e.type for e in events]}"
    )
    assert suspended[0].payload_ref is not None, (
        "step.suspended must carry a payload_ref (suspension payload written before append)"
    )

    # Assertion 2: the lease is released.
    row = owner_conn.execute(
        "SELECT state, owner, lease_expires_at FROM steps WHERE step_id = %s",
        (lease.step_id,),
    ).fetchone()
    assert row is not None
    state, step_owner, lease_expires_at = row
    assert state == "runnable", f"expected state='runnable', got {state!r}"
    assert step_owner is None, f"expected owner=NULL, got {step_owner!r}"
    assert lease_expires_at is None, f"expected lease_expires_at=NULL, got {lease_expires_at}"

    config_b = PoolConfig(
        worker_id="t2-worker-b",
        default_limits=_LIMITS,
        allowed_model_ids=("stub:counting",),
        pool_class=_POOL_CLASS,
    )

    # Assertion 3 (AC-0333): the step is NOT claimable while awaiting a decision.
    # ``awaiting_decision = true`` was set by the executor on suspension;
    # ``AND NOT awaiting_decision`` in ``claim_one`` must block it.
    with psycopg.connect(database_url("worker")) as conn:
        premature = claim_one(conn, config_b)
    assert premature is None, (
        "claim_one must return None when awaiting_decision=true (AC-0333); "
        f"got a lease for step {premature.step_id if premature else '?'}"
    )

    # Commit a decision to clear ``awaiting_decision`` and advance
    # ``approval_cycles``, so the step becomes claimable again.
    _, pending_call_ids = load_suspension_payload(suspended[0].payload_ref)
    with psycopg.connect(database_url("api")) as api_conn:
        append_approval_decision(
            api_conn,
            run_id=run_id,
            step_id=lease.step_id,
            call_ids=pending_call_ids,
            decisions=[APPROVAL_GRANTED] * len(pending_call_ids),
            principal=_PRINCIPAL,
            suspension_seq=suspended[0].seq,
            agent_role=_ROLE_NAME,
            payload_ref=suspended[0].payload_ref,
        )

    # Assertion 4: after the decision the step is claimable.
    with psycopg.connect(database_url("worker")) as conn:
        second_lease = claim_one(conn, config_b)

    assert second_lease is not None, (
        "the suspended step must be claimable by a second worker after the "
        "decision clears awaiting_decision"
    )
    assert second_lease.step_id == lease.step_id, (
        f"second worker claimed {second_lease.step_id}, expected {lease.step_id}"
    )


# ── AC-0301: a clean run reaches completed with a readable payload_ref ────────

_CLEAN_POOL_CLASS = "t2-clean-run"
_CLEAN_ROLE_NAME = "t2-clean-run-role"
_CLEAN_PRINCIPAL = "t2-clean-principal"
_CLEAN_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}


def test_a_clean_run_reaches_completed_with_a_readable_payload_ref(
    require_substrate: None,
) -> None:
    """AC-0301: a clean run publishes its artifact; payload_ref resolves; no step.suspended.

    The role has no needs_approval flag, so the executor drives a clean path
    to step.completed + run.completed. The step.completed event's payload_ref
    resolves to a readable object in the object store.

    Mutation-proof:
    - Pass payload_ref=None at executor.py:711 — the payload_ref assertion reds.
    - Make the clean path append a step.suspended before completing — the
      no-step-suspended assertion reds.
    """
    from pydantic_ai.models.test import TestModel

    from ced.adapters.objectstore.client import read_payload

    config = PoolConfig(
        worker_id="t2-clean-worker",
        default_limits=_CLEAN_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        # custom_output_args={"references": []} produces ReferenceSelection(references=[])
        # which passes the quarantine check (empty list has nothing to validate).
        model_factory=lambda _: TestModel(custom_output_args={"references": []}),
        pool_class=_CLEAN_POOL_CLASS,
    )

    # Insert role without needs_approval (unflagged → clean run).
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
                _CLEAN_ROLE_NAME,
                json.dumps({"model_id": "stub:counting", "settings": {}, "limits": {}}),
            ),
        )
        conn.commit()

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_CLEAN_PRINCIPAL,
            agent_role=_CLEAN_ROLE_NAME,
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
            (config.worker_id, _CLEAN_POOL_CLASS, step_id),
        ).fetchone()
        conn.commit()

    assert row is not None
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=int(row[0]),
        agent_role=_CLEAN_ROLE_NAME,
    )

    try:
        body = make_step_body(config)
        body(lease, threading.Event())

        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)

        # Assert no step.suspended event.
        suspended_events = [e for e in events if e.type == "step.suspended"]
        assert not suspended_events, (
            f"clean run must not append step.suspended; got {[e.type for e in events]}"
        )

        # Assert step.completed has a non-null payload_ref.
        completed_events = [e for e in events if e.type == "step.completed"]
        assert len(completed_events) == 1, (
            f"expected exactly 1 step.completed, got {[e.type for e in events]}"
        )
        payload_ref = completed_events[0].payload_ref
        assert payload_ref is not None, (
            "step.completed must carry a non-null payload_ref (AC-0301)"
        )

        # Assert payload_ref resolves to a readable object.
        payload = read_payload(payload_ref)
        assert isinstance(payload, dict), (
            f"payload_ref must resolve to a dict, got {type(payload)!r}"
        )

        # Assert run.completed was committed.
        run_terminal = [e for e in events if e.type == "run.completed"]
        assert len(run_terminal) == 1, (
            f"expected exactly 1 run.completed, got {[e.type for e in events]}"
        )
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()
