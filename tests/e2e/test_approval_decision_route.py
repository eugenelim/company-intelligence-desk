"""AC-0328: the approval decision route, driven end-to-end over the wire.

AC-0328 requires:
- A missing Origin is refused with 400.
- A foreign Origin is refused with 400.
- These refusals happen before any append (the DB is not touched).
- The decision set is bounded (too many pairs → 422 before append).
- 404 for a nonexistent run.
- 409 when the step is not in the run.
- The happy path commits a decision.

AC-0303: ``require_distinct_approver`` is deployment configuration, not
caller-supplied. The test configures the flag both ways (by setting
``app.state.require_distinct_approver``) and reads back two different
appended payload values, so a module constant cannot satisfy it.

All tests drive the shipped route over a real uvicorn server on a loopback
port. ``e2e_server`` is session-scoped so startup cost is paid once. Tests
that change ``app.state`` reset it in a finally block to avoid contaminating
the session.
"""

from __future__ import annotations

import json
import threading
import uuid

import psycopg
import pytest

from ced.adapters.objectstore.client import read_payload
from ced.adapters.postgres.dsn import database_url

from .conftest import E2EClient, SuspendedE2E

pytestmark = pytest.mark.substrate


# ── AC-0328: Origin defence ──────────────────────────────────────────────────


def test_origin_absent_is_refused(e2e_server: E2EClient) -> None:
    """AC-0328: an absent Origin header is refused with 400 before any append.

    The route checks Origin before touching the database (``_require_run`` is
    not called), so no run needs to exist.  Mutation-proof: if the Origin check
    is dropped, the route falls through to ``_require_run`` and returns 404,
    not 400 — a different status code that reds this assertion.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{run_id}/steps/{step_id}/decision",
        payload={
            "suspension_seq": 1,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        # No Origin header — should be refused with 400.
    )
    assert resp.status == 400, f"expected 400 for absent Origin, got {resp.status}: {resp.body}"
    assert "origin" in str(resp.body).lower(), (
        f"expected 'origin' in error detail, got {resp.body!r}"
    )


def test_foreign_origin_is_refused(e2e_server: E2EClient) -> None:
    """AC-0328: a foreign Origin is refused with 400 before any append.

    Mutation-proof: if the origin comparison is removed, the request falls
    through to ``_require_run`` and returns 404 for this non-existent run,
    not 400 — a different status that reds this assertion.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{run_id}/steps/{step_id}/decision",
        payload={
            "suspension_seq": 1,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status == 400, (
        f"expected 400 for foreign Origin, got {resp.status}: {resp.body}"
    )
    assert "does not match" in str(resp.body).lower() or "origin" in str(resp.body).lower(), (
        f"expected origin mismatch in error detail, got {resp.body!r}"
    )


def test_nonexistent_run_is_404(e2e_server: E2EClient) -> None:
    """AC-0328: a run that does not exist returns 404."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{run_id}/steps/{step_id}/decision",
        payload={
            "suspension_seq": 1,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 404, (
        f"expected 404 for nonexistent run, got {resp.status}: {resp.body}"
    )


def test_step_not_in_run_is_404(e2e_server: E2EClient, suspended_e2e: SuspendedE2E) -> None:
    """AC-0328: a step that does not belong to the run returns 404."""
    other_step = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{other_step}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 404, (
        f"expected 404 for step not in run, got {resp.status}: {resp.body}"
    )


def test_decision_set_bound_is_refused_before_append(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0328: too many decision pairs is refused (422) before any append.

    The ``decisions`` field is bounded at ``ATTRIBUTION_MAX_LENGTH`` entries by
    Pydantic, which validates before the route body runs. Mutation-proof: if the
    bound is removed, the request succeeds (not 422), and the status assertion
    reds. The "refused before any append" half is verified by reading the event
    count before and after — it must not change.
    """
    from ced.api.models import ATTRIBUTION_MAX_LENGTH

    with psycopg.connect(database_url("migration")) as conn:
        count_before = conn.execute(
            "SELECT count(*) FROM events WHERE run_id = %s",
            (suspended_e2e.run_id,),
        ).fetchone()[0]  # type: ignore[index]

    oversized_decisions = [
        {"call_id": f"call-{i}", "granted": True} for i in range(ATTRIBUTION_MAX_LENGTH + 1)
    ]
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq,
            "decisions": oversized_decisions,
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 422, (
        f"expected 422 for oversized decision set, got {resp.status}: {resp.body}"
    )

    with psycopg.connect(database_url("migration")) as conn:
        count_after = conn.execute(
            "SELECT count(*) FROM events WHERE run_id = %s",
            (suspended_e2e.run_id,),
        ).fetchone()[0]  # type: ignore[index]

    assert count_after == count_before, (
        f"event count changed from {count_before} to {count_after}: "
        "the oversized request must not append any event"
    )


def test_overlength_call_id_is_refused_before_append(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0328: a call_id that exceeds ATTRIBUTION_MAX_LENGTH is refused (422) before append.

    The bound is on DecisionPair.call_id, a distinct field from the list-count
    bound on ApprovalDecisionRequest.decisions. Mutation-proof: remove
    max_length=ATTRIBUTION_MAX_LENGTH from models.py:101 — the request succeeds
    (not 422) and the status assertion reds.
    """
    from ced.api.models import ATTRIBUTION_MAX_LENGTH

    with psycopg.connect(database_url("migration")) as conn:
        count_before = conn.execute(
            "SELECT count(*) FROM events WHERE run_id = %s",
            (suspended_e2e.run_id,),
        ).fetchone()[0]  # type: ignore[index]

    overlength_call_id = "x" * (ATTRIBUTION_MAX_LENGTH + 1)
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq,
            "decisions": [{"call_id": overlength_call_id, "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 422, (
        f"expected 422 for over-length call_id, got {resp.status}: {resp.body}"
    )

    with psycopg.connect(database_url("migration")) as conn:
        count_after = conn.execute(
            "SELECT count(*) FROM events WHERE run_id = %s",
            (suspended_e2e.run_id,),
        ).fetchone()[0]  # type: ignore[index]

    assert count_after == count_before, (
        f"event count changed from {count_before} to {count_after}: "
        "the over-length call_id request must not append any event"
    )


def test_wrong_suspension_seq_is_409(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0328: a decision naming a stale suspension seq returns 409."""
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq + 99,  # wrong seq
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 409, (
        f"expected 409 for stale suspension seq, got {resp.status}: {resp.body}"
    )


def test_happy_path_commits_and_returns_last_seq(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0328: a well-formed decision over the right suspension commits."""
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 200, f"expected 200 for happy path, got {resp.status}: {resp.body}"
    assert "last_seq" in resp.body, f"response missing last_seq: {resp.body!r}"
    assert resp.body["last_seq"] > 0


# ── AC-0303: require_distinct_approver — deployment configuration ─────────────


def test_require_distinct_configured_false_records_false_in_payload(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0303: with the flag off, the payload records false and the same
    principal as the run's initiator is accepted.

    This is one of two required configurations. The flag is read from
    ``app.state`` (deployment config), not from the request body.
    """
    from ced.api.main import app as _app  # the module-level singleton

    _app.state.require_distinct_approver = False
    try:
        resp = e2e_server.post(
            f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
            payload={
                "suspension_seq": suspended_e2e.suspension_seq,
                "decisions": [{"call_id": "c1", "granted": True}],
                # Same as initiating principal — must succeed when flag is False.
                "principal": suspended_e2e.initiating_principal,
            },
            headers={"Origin": e2e_server.origin},
        )
    finally:
        _app.state.require_distinct_approver = False  # restore

    assert resp.status == 200, (
        f"expected 200 when require_distinct_approver=false, got {resp.status}: {resp.body}"
    )

    # Read the payload_ref from the committed event and load it from the object store.
    last_seq = resp.body["last_seq"]
    with psycopg.connect(database_url("migration")) as conn:
        row = conn.execute(
            "SELECT payload_ref FROM events WHERE run_id = %s AND seq = %s",
            (suspended_e2e.run_id, last_seq),
        ).fetchone()
    assert row is not None and row[0] is not None, "committed event has no payload_ref"
    payload = read_payload(row[0])
    assert payload.get("require_distinct_approver") is False, (
        f"payload must record require_distinct_approver=false when flag is off, "
        f"got {payload.get('require_distinct_approver')!r}"
    )


def test_require_distinct_configured_true_refuses_same_principal(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0303: with the flag on, the same principal as the initiator is refused.

    This is the second required configuration. The flag is deployment config;
    the caller cannot override it by sending a different request body field.
    Mutation-proof: if the guard is absent, the request succeeds (200) and
    this assertion reds on the 200 status.
    """
    from ced.api.main import app as _app

    _app.state.require_distinct_approver = True
    try:
        resp = e2e_server.post(
            f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
            payload={
                "suspension_seq": suspended_e2e.suspension_seq,
                "decisions": [{"call_id": "c1", "granted": True}],
                # Same as initiating principal — must be refused when flag is True.
                "principal": suspended_e2e.initiating_principal,
            },
            headers={"Origin": e2e_server.origin},
        )
    finally:
        _app.state.require_distinct_approver = False  # restore

    assert resp.status == 409, (
        f"expected 409 when require_distinct_approver=true and same principal, "
        f"got {resp.status}: {resp.body}"
    )
    assert "distinct" in str(resp.body).lower() or "principal" in str(resp.body).lower(), (
        f"expected 'distinct' or 'principal' in error detail, got {resp.body!r}"
    )


def test_require_distinct_configured_true_records_true_in_payload(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0303: with the flag on, a distinct principal succeeds and the payload
    records true — producing a different value than the flag-off case.

    This completes the "configuring both ways and reading back two different
    appended values" requirement. A module constant set to False would fail
    this assertion (because it could not record True); a constant set to True
    would fail test_require_distinct_configured_false_records_false_in_payload.
    """
    from ced.api.main import app as _app

    _app.state.require_distinct_approver = True
    try:
        resp = e2e_server.post(
            f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
            payload={
                "suspension_seq": suspended_e2e.suspension_seq,
                "decisions": [{"call_id": "c1", "granted": True}],
                # DIFFERENT from initiating principal — must succeed.
                "principal": "distinct-approver-principal",
            },
            headers={"Origin": e2e_server.origin},
        )
    finally:
        _app.state.require_distinct_approver = False  # restore

    assert resp.status == 200, (
        f"expected 200 when require_distinct_approver=true and distinct principal, "
        f"got {resp.status}: {resp.body}"
    )

    last_seq = resp.body["last_seq"]
    with psycopg.connect(database_url("migration")) as conn:
        row = conn.execute(
            "SELECT payload_ref FROM events WHERE run_id = %s AND seq = %s",
            (suspended_e2e.run_id, last_seq),
        ).fetchone()
    assert row is not None and row[0] is not None, "committed event has no payload_ref"
    payload = read_payload(row[0])
    assert payload.get("require_distinct_approver") is True, (
        f"payload must record require_distinct_approver=true when flag is on, "
        f"got {payload.get('require_distinct_approver')!r}"
    )


# ── AC-0303: granting principal is recorded in events.principal ───────────────


def test_approval_granted_event_records_the_granting_principal(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0303: the committed approval.granted event carries events.principal.

    The granting principal comes from the request body, not from a constant.
    Mutation-proof: if the caller at main.py passes a constant instead of
    request_body.principal, the event's principal would be the constant, not the
    value submitted, and this assertion would red.
    """
    from ced.api.main import app as _app

    submitted_principal = "unique-approver-for-principal-check"
    _app.state.require_distinct_approver = False
    try:
        resp = e2e_server.post(
            f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
            payload={
                "suspension_seq": suspended_e2e.suspension_seq,
                "decisions": [{"call_id": "c1", "granted": True}],
                "principal": submitted_principal,
            },
            headers={"Origin": e2e_server.origin},
        )
    finally:
        _app.state.require_distinct_approver = False

    assert resp.status == 200, f"expected 200, got {resp.status}: {resp.body}"

    with psycopg.connect(database_url("migration")) as conn:
        row = conn.execute(
            "SELECT principal FROM events WHERE run_id = %s AND type = 'approval.granted'",
            (suspended_e2e.run_id,),
        ).fetchone()

    assert row is not None, "no approval.granted event found"
    assert row[0] == submitted_principal, (
        f"events.principal is {row[0]!r}, expected {submitted_principal!r}; "
        "mutation: passing a constant principal would mismatch this assertion"
    )


# ── Entry 4: full resume-to-publication cycle ─────────────────────────────────


def test_granted_decision_lets_pool_reclaim_and_reach_run_completed(
    e2e_server: E2EClient,
) -> None:
    """Entry 4: grant via HTTP → pool reclaim → run.completed.

    Full cycle from suspension through an HTTP grant decision to run.completed.
    Drives two executor body passes directly (no full worker loop) so the test
    controls the model on each pass independently.

    Two mutations that must red independently:

    Mutation 1 (``approval_cycles > 0 → False`` at executor.py): second body
    skips ``_body_resume`` and runs the fresh agent path — no ``step.resumed``
    event is appended; the first assertion reds.

    Mutation 2 (``return`` before ``append_run_terminal`` in ``_body_resume``):
    ``step.resumed`` is written and ``step.completed`` is written but
    ``run.completed`` is never appended; ``runs.state`` stays ``'running'``
    and the second assertion reds.
    """
    from pydantic_ai.models.test import TestModel

    from ced.adapters.postgres.event_log import read_events, start_run
    from ced.worker.executor import make_step_body
    from ced.worker.persistence import load_suspension_payload
    from ced.worker.pool import Lease, PoolConfig, claim_one

    _POOL_CLASS = f"t2-e4-{uuid.uuid4().hex[:8]}"
    _ROLE = f"t2-e4-role-{uuid.uuid4().hex[:8]}"
    _PRINCIPAL = "t2-entry4-principal"
    _LIMITS: dict[str, int | bool] = {
        "per_request_input_tokens_limit": 4_000,
        "input_tokens_limit": 40_000,
        "request_limit": 8,
        "tool_calls_limit": 4,
        "count_tokens_before_request": False,
    }

    # Stateful factory: first call returns a suspending model; second returns a
    # completing model.  Compile_role calls the factory once per body pass.
    call_count = [0]

    def _factory(model_id: str) -> TestModel:
        call_count[0] += 1
        if call_count[0] == 1:
            return TestModel(call_tools=["request_approval"])
        return TestModel(call_tools=[], custom_output_args={"references": []})

    config = PoolConfig(
        worker_id="t2-e4-worker",
        default_limits=_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=_factory,
        pool_class=_POOL_CLASS,
    )

    model_settings = json.dumps(
        {"model_id": "stub:counting", "settings": {}, "limits": {}, "needs_approval": True}
    )
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            """
            INSERT INTO agent_role
                (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
            VALUES (%s, 1, '[]'::jsonb, '', %s::jsonb, 'reference-selection')
            ON CONFLICT (role_name, version) DO UPDATE
                SET model_settings = EXCLUDED.model_settings
            """,
            (_ROLE, model_settings),
        )
        conn.commit()

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    try:
        with psycopg.connect(database_url("api")) as conn:
            start_run(
                conn, run_id=run_id, step_id=step_id, principal=_PRINCIPAL, agent_role=_ROLE
            )

        # Lease the step manually so we can hand it to the executor body.
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
        assert row is not None
        lease = Lease(step_id=step_id, run_id=run_id, epoch=int(row[0]), agent_role=_ROLE)

        # First body pass: factory[0] → TestModel(call_tools=["request_approval"])
        # → agent calls request_approval → DeferredToolRequests → suspension.
        make_step_body(config)(lease, threading.Event())

        # Read the suspension event to get the pending call ids and seq.
        with psycopg.connect(database_url("worker")) as conn:
            suspended_events = [
                e for e in read_events(conn, run_id=run_id) if e.type == "step.suspended"
            ]
        assert len(suspended_events) == 1, (
            f"expected 1 step.suspended, got {[e.type for e in suspended_events]}"
        )
        assert suspended_events[0].payload_ref is not None
        _, pending_call_ids = load_suspension_payload(suspended_events[0].payload_ref)
        suspension_seq = suspended_events[0].seq

        # Grant via the real HTTP route (Entry 4's composed path).
        resp = e2e_server.post(
            f"/runs/{run_id}/steps/{step_id}/decision",
            payload={
                "suspension_seq": suspension_seq,
                "decisions": [{"call_id": cid, "granted": True} for cid in pending_call_ids],
                "principal": "e2e-approver",
            },
            headers={"Origin": e2e_server.origin},
        )
        assert resp.status == 200, f"grant decision failed: {resp.status}: {resp.body}"

        # Re-claim: awaiting_decision was cleared by the grant; claim_one can now
        # find the step (state='runnable', awaiting_decision=false, approval_cycles=1).
        with psycopg.connect(database_url("worker")) as conn:
            new_lease = claim_one(conn, config)
        assert new_lease is not None, "claim_one must find the step after the grant"
        assert new_lease.step_id == step_id, (
            f"expected to claim {step_id!s}, got {new_lease.step_id!s}"
        )

        # Second body pass: factory[1] → TestModel(call_tools='none', ...)
        # approval_cycles=1 → _body_resume → resume_step → completion.
        make_step_body(config)(new_lease, threading.Event())

        # Mutation 1 proof: step.resumed is written only by the resume path.
        # If approval_cycles > 0 is patched to False, second body takes the
        # fresh path, never calls _body_resume, and step.resumed is absent.
        with psycopg.connect(database_url("worker")) as conn:
            all_event_types = [e.type for e in read_events(conn, run_id=run_id)]
        assert "step.resumed" in all_event_types, (
            f"step.resumed must be appended by _body_resume; events: {all_event_types}; "
            "mutation 1 (approval_cycles > 0 → False): fresh path is taken, "
            "step.resumed is absent, this assertion reds"
        )

        # Mutation 2 proof: runs.state='completed' requires append_run_terminal.
        # If _body_resume returns before append_run_terminal, run.completed is
        # never written and runs.state stays 'running'.
        with psycopg.connect(database_url("migration")) as conn:
            run_row = conn.execute(
                "SELECT state FROM runs WHERE run_id = %s", (run_id,)
            ).fetchone()
        assert run_row is not None and run_row[0] == "completed", (
            f"runs.state must be 'completed' after run.completed; got {run_row[0]!r}; "
            "mutation 2 (return before append_run_terminal in _body_resume): "
            "run.completed is never written, runs.state stays 'running', this assertion reds"
        )
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM agent_role WHERE role_name = %s", (_ROLE,))
            conn.commit()
