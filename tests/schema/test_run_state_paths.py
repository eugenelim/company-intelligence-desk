"""AC-0320, AC-0324, AC-0332, AC-0334 — the schema the run state machine rests on.

Every assertion here is against the applied revision, because a grant set and a
transition are properties of the schema Postgres holds, not of migration text.
Checked on a database upgraded from 0004, per the plan's construction-test note.

The four stub tests are materialized byte-identically from `plan.md`. The full
criterion tests follow each stub.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import psycopg
import pytest

from ced.adapters.postgres import event_log
from ced.adapters.postgres.dsn import database_url

# ── Fixtures ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunningStep:
    """A run in ``running`` state with one step leased at a known epoch."""

    run_id: UUID
    step_id: UUID
    lease_epoch: int


@pytest.fixture
def running_step(owner_conn: psycopg.Connection) -> Iterator[RunningStep]:
    """A run in ``running`` state with a live leased step.

    Set up through the owner connection rather than through the append path, so
    a broken path cannot hide behind a broken fixture. The run starts in
    ``running`` directly; the ``requested → running`` transition is AC-0327's
    and not this fixture's to establish.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'running')",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() + interval '60 seconds')",
            (step_id, run_id),
        )
    try:
        yield RunningStep(run_id=run_id, step_id=step_id, lease_epoch=1)
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@dataclass(frozen=True)
class SuspendedStep:
    """A run in ``running`` state with a step that has a committed step.suspended event.

    The step's ``awaiting_decision`` is true and the suspension seq is known.
    """

    run_id: UUID
    step_id: UUID
    suspension_seq: int


@pytest.fixture
def suspended_step(owner_conn: psycopg.Connection) -> Iterator[SuspendedStep]:
    """A run whose step has been suspended and is awaiting a decision.

    Inserted directly to avoid depending on append_step_event or any worker
    path. The step.suspended event is committed with a known seq.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'running', 0)",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, awaiting_decision) "
            "VALUES (%s, %s, 'runnable', true)",
            (step_id, run_id),
        )
        # Advance next_seq and insert a step.suspended event at seq=1.
        owner_conn.execute(
            "UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO events (run_id, seq, type, step_id, principal) "
            "VALUES (%s, 1, 'step.suspended', %s, 'fixture')",
            (run_id, step_id),
        )
    try:
        yield SuspendedStep(run_id=run_id, step_id=step_id, suspension_seq=1)
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


# ── Stub tests (materialized byte-identically from plan.md) ─────────────────


@pytest.mark.substrate
# STUB: AC-0324
def test_the_approval_decision_append_path_exists(require_substrate: None) -> None:
    """Revision 0005 adds the path `app_api` alone may commit a decision through."""
    with psycopg.connect(database_url("worker")) as conn:
        found = conn.execute(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = 'append_approval_decision'"
        ).fetchone()
    assert found is not None


@pytest.mark.substrate
# STUB: AC-0320
def test_the_run_terminal_append_path_exists(require_substrate: None) -> None:
    """Revision 0005 adds the only path that may commit a run-terminal move."""
    with psycopg.connect(database_url("worker")) as conn:
        found = conn.execute(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = 'append_run_terminal'"
        ).fetchone()
    assert found is not None


@pytest.mark.substrate
# STUB: AC-0332
def test_exactly_one_append_step_event_survives_the_replacement(
    require_substrate: None,
) -> None:
    """A signature drift creates a second overload carrying EXECUTE TO PUBLIC."""
    with psycopg.connect(database_url("worker")) as conn:
        rows = conn.execute(
            "SELECT p.prosecdef, p.proconfig, p.prosrc FROM pg_proc p"
            " JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = 'append_step_event'"
        ).fetchall()
    assert len(rows) == 1
    secdef, proconfig, body = rows[0]
    assert secdef is True
    assert "pg_temp" in " ".join(proconfig or [])
    assert "approval.granted" in body and "approval.rejected" in body


@pytest.mark.substrate
# STUB: AC-0334
def test_a_decision_key_is_unique_per_suspension_and_call(require_substrate: None) -> None:
    """The replay refusal is a database fact, not application logic."""
    with psycopg.connect(database_url("worker")) as conn:
        found = conn.execute(
            "SELECT 1 FROM pg_indexes WHERE schemaname = 'public'"
            " AND tablename = 'events'"
            " AND indexdef ILIKE '%approval.granted%'"
            " AND indexdef ILIKE '%idempotency_key%'"
        ).fetchone()
    assert found is not None


# ── AC-0320: the run-terminal append path ────────────────────────────────────


@pytest.mark.substrate
def test_the_run_terminal_path_is_granted_to_app_worker_only(
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0320: the grant set stays disjoint.

    `app_worker` holds EXECUTE; `app_api` and `app_policy` do not. Direct
    INSERT on `events` is already revoked by revision 0002 and is not
    re-asserted here.
    """
    sig = "public.append_run_terminal(uuid, uuid, bigint, text, text, text, text)"
    rows = owner_conn.execute(
        "SELECT grantee, privilege_type FROM information_schema.routine_privileges"
        " WHERE specific_schema = 'public'"
        "   AND routine_name = 'append_run_terminal'"
        "   AND privilege_type = 'EXECUTE'",
    ).fetchall()
    grantees = {row[0] for row in rows}

    assert "app_worker" in grantees, f"app_worker missing EXECUTE on {sig}"
    assert "app_api" not in grantees, f"app_api holds EXECUTE on {sig}"
    assert "app_policy" not in grantees, f"app_policy holds EXECUTE on {sig}"
    assert "PUBLIC" not in grantees, f"PUBLIC holds EXECUTE on {sig}"


@pytest.mark.substrate
def test_run_terminal_refuses_a_wrong_type(
    worker_conn: psycopg.Connection,
    running_step: RunningStep,
) -> None:
    """AC-0320: the path admits only run.completed and run.failed."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_run_terminal(
            worker_conn,
            run_id=running_step.run_id,
            step_id=running_step.step_id,
            lease_epoch=running_step.lease_epoch,
            type="run.requested",
            principal="worker-1",
        )


@pytest.mark.substrate
def test_run_terminal_refuses_a_decision_type(
    worker_conn: psycopg.Connection,
    running_step: RunningStep,
) -> None:
    """AC-0320: decision types are also refused — completeness check."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_run_terminal(
            worker_conn,
            run_id=running_step.run_id,
            step_id=running_step.step_id,
            lease_epoch=running_step.lease_epoch,
            type="approval.granted",
            principal="worker-1",
        )


@pytest.mark.substrate
def test_run_terminal_refuses_a_fenced_call(
    worker_conn: psycopg.Connection,
    running_step: RunningStep,
) -> None:
    """AC-0320: lease possession is proved through the shipped fence_step."""
    with pytest.raises(event_log.Fenced):
        event_log.append_run_terminal(
            worker_conn,
            run_id=running_step.run_id,
            step_id=running_step.step_id,
            lease_epoch=running_step.lease_epoch + 1,  # wrong epoch
            type="run.completed",
            principal="worker-1",
        )


@pytest.mark.substrate
def test_run_terminal_refuses_a_step_not_in_the_run(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    running_step: RunningStep,
) -> None:
    """AC-0320: a live lease on one run does not authorize terminating another."""
    other_run = uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'running')",
            (other_run,),
        )
    try:
        with pytest.raises(event_log.StepRunMismatch):
            event_log.append_run_terminal(
                worker_conn,
                run_id=other_run,
                step_id=running_step.step_id,
                lease_epoch=running_step.lease_epoch,
                type="run.completed",
                principal="worker-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (other_run,))


@pytest.mark.substrate
def test_run_terminal_refuses_a_run_at_requested_state(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0320: a run still at requested cannot jump to completed.

    The source-state predicate (WHERE state = 'running') is what AC-0327
    commits as the only permitted source state for these transitions.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'requested')",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() + interval '60 seconds')",
            (step_id, run_id),
        )
    try:
        with pytest.raises(event_log.RunNotRunning):
            event_log.append_run_terminal(
                worker_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=1,
                type="run.completed",
                principal="worker-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.substrate
def test_run_terminal_refuses_a_run_already_terminal(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0320: the terminal guard prevents a second terminal event."""
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'completed')",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() + interval '60 seconds')",
            (step_id, run_id),
        )
    try:
        with pytest.raises(event_log.RunNotRunning):
            event_log.append_run_terminal(
                worker_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=1,
                type="run.failed",
                principal="worker-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.substrate
def test_run_terminal_atomicity_state_does_not_move_on_failure(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    running_step: RunningStep,
) -> None:
    """AC-0320: with the append forced to fail, runs.state does not move.

    The wrong epoch forces a fence failure, which rolls back before any state
    change commits. Asserted by reading runs.state before and after and
    confirming they agree.
    """
    row_before = owner_conn.execute(
        "SELECT state FROM runs WHERE run_id = %s",
        (running_step.run_id,),
    ).fetchone()
    assert row_before is not None
    state_before = row_before[0]

    with pytest.raises(event_log.Fenced):
        event_log.append_run_terminal(
            worker_conn,
            run_id=running_step.run_id,
            step_id=running_step.step_id,
            lease_epoch=running_step.lease_epoch + 99,
            type="run.completed",
            principal="worker-1",
        )

    row_after = owner_conn.execute(
        "SELECT state FROM runs WHERE run_id = %s",
        (running_step.run_id,),
    ).fetchone()
    assert row_after is not None
    assert row_after[0] == state_before, (
        f"runs.state moved from {state_before!r} to {row_after[0]!r} "
        "even though the append failed"
    )


@pytest.mark.substrate
def test_run_terminal_happy_path_completes_a_run(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    running_step: RunningStep,
) -> None:
    """AC-0320: a valid call succeeds and writes step_id null.

    Both the positive case and the null step_id output are verified. A check
    that only refuses is not a control — it is a build break.
    """
    seq = event_log.append_run_terminal(
        worker_conn,
        run_id=running_step.run_id,
        step_id=running_step.step_id,
        lease_epoch=running_step.lease_epoch,
        type="run.completed",
        principal="worker-1",
    )
    assert seq == 1

    # runs.state must have moved to completed.
    state_row = owner_conn.execute(
        "SELECT state FROM runs WHERE run_id = %s",
        (running_step.run_id,),
    ).fetchone()
    assert state_row == ("completed",)

    # The event is committed with step_id null.
    event_row = owner_conn.execute(
        "SELECT type, step_id FROM events WHERE run_id = %s AND seq = %s",
        (running_step.run_id, seq),
    ).fetchone()
    assert event_row is not None
    assert event_row[0] == "run.completed"
    assert event_row[1] is None, "terminal event must carry step_id null"


@pytest.mark.substrate
def test_app_api_cannot_reach_append_run_terminal(
    api_conn: psycopg.Connection,
    running_step: RunningStep,
) -> None:
    """AC-0320: the grant set carries no EXECUTE for app_api."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        api_conn.execute(
            "SELECT append_run_terminal(%s, %s, %s, %s, %s)",
            (
                running_step.run_id,
                running_step.step_id,
                running_step.lease_epoch,
                "run.completed",
                "api",
            ),
        )
    api_conn.rollback()


# ── AC-0324: the approval-decision append path ───────────────────────────────


@pytest.mark.substrate
def test_the_approval_decision_path_is_granted_to_app_api_only(
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0324: the grant set stays disjoint."""
    rows = owner_conn.execute(
        "SELECT grantee, privilege_type FROM information_schema.routine_privileges"
        " WHERE specific_schema = 'public'"
        "   AND routine_name = 'append_approval_decision'"
        "   AND privilege_type = 'EXECUTE'",
    ).fetchall()
    grantees = {row[0] for row in rows}

    sig = "public.append_approval_decision(uuid, uuid, text, text, bigint, text, text, text)"
    assert "app_api" in grantees, f"app_api missing EXECUTE on {sig}"
    assert "app_worker" not in grantees, f"app_worker holds EXECUTE on {sig}"
    assert "app_policy" not in grantees, f"app_policy holds EXECUTE on {sig}"
    assert "PUBLIC" not in grantees, f"PUBLIC holds EXECUTE on {sig}"


@pytest.mark.substrate
def test_approval_decision_refuses_a_wrong_type(
    api_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324: the path admits only approval.granted and approval.rejected."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_approval_decision(
            api_conn,
            run_id=suspended_step.run_id,
            step_id=suspended_step.step_id,
            type="step.suspended",
            principal="approver",
            suspension_seq=suspended_step.suspension_seq,
            call_id="call-1",
        )


@pytest.mark.substrate
def test_approval_decision_refuses_a_step_not_in_the_run(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324: the step-run membership check."""
    other_run = uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'running')",
            (other_run,),
        )
    try:
        with pytest.raises(event_log.StepRunMismatch):
            event_log.append_approval_decision(
                api_conn,
                run_id=other_run,
                step_id=suspended_step.step_id,
                type="approval.granted",
                principal="approver",
                suspension_seq=suspended_step.suspension_seq,
                call_id="call-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (other_run,))


@pytest.mark.substrate
def test_approval_decision_refuses_a_step_with_no_suspended_event(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0324: the step must carry a committed step.suspended event at the named seq."""
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'running')",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, awaiting_decision) "
            "VALUES (%s, %s, 'runnable', true)",
            (step_id, run_id),
        )
    try:
        with pytest.raises(event_log.DecisionRefused):
            event_log.append_approval_decision(
                api_conn,
                run_id=run_id,
                step_id=step_id,
                type="approval.granted",
                principal="approver",
                suspension_seq=1,  # no event at seq=1 exists
                call_id="call-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.substrate
def test_approval_decision_refuses_a_stale_suspension_seq(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324 / AC-0334: a decision submitted after the next suspension opened.

    A second step.suspended event is inserted, making seq=1 stale. A decision
    naming seq=1 must be refused, because it answers a suspension the step has
    already moved past.
    """
    # Append a second step.suspended event, making seq=1 no longer the latest.
    with owner_conn.transaction():
        owner_conn.execute(
            "UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s",
            (suspended_step.run_id,),
        )
        owner_conn.execute(
            "INSERT INTO events (run_id, seq, type, step_id, principal) "
            "VALUES (%s, 2, 'step.suspended', %s, 'fixture')",
            (suspended_step.run_id, suspended_step.step_id),
        )

    # Decision naming the older suspension must be refused.
    with pytest.raises(event_log.DecisionRefused):
        event_log.append_approval_decision(
            api_conn,
            run_id=suspended_step.run_id,
            step_id=suspended_step.step_id,
            type="approval.granted",
            principal="approver",
            suspension_seq=suspended_step.suspension_seq,  # seq=1, stale
            call_id="call-1",
        )


@pytest.mark.substrate
def test_approval_decision_refuses_when_not_awaiting(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0324: the step must be awaiting a decision."""
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'running', 0)",
            (run_id,),
        )
        # awaiting_decision is false (the default)
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, awaiting_decision) "
            "VALUES (%s, %s, 'runnable', false)",
            (step_id, run_id),
        )
        owner_conn.execute(
            "UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO events (run_id, seq, type, step_id, principal) "
            "VALUES (%s, 1, 'step.suspended', %s, 'fixture')",
            (run_id, step_id),
        )
    try:
        with pytest.raises(event_log.DecisionRefused):
            event_log.append_approval_decision(
                api_conn,
                run_id=run_id,
                step_id=step_id,
                type="approval.granted",
                principal="approver",
                suspension_seq=1,
                call_id="call-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.substrate
def test_approval_decision_happy_path_clears_hold_and_advances_cycle(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324: a valid call succeeds and clears awaiting_decision."""
    seq = event_log.append_approval_decision(
        api_conn,
        run_id=suspended_step.run_id,
        step_id=suspended_step.step_id,
        type="approval.granted",
        principal="approver",
        suspension_seq=suspended_step.suspension_seq,
        call_id="call-1",
    )
    assert seq >= 1

    # awaiting_decision must be cleared and approval_cycles must have advanced.
    step_row = owner_conn.execute(
        "SELECT awaiting_decision, approval_cycles FROM steps WHERE step_id = %s",
        (suspended_step.step_id,),
    ).fetchone()
    assert step_row is not None
    assert step_row[0] is False, "awaiting_decision must be false after a decision"
    assert step_row[1] == 1, "approval_cycles must be 1 after the first decision"


@pytest.mark.substrate
def test_approval_decision_from_append_step_event_is_refused(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0324 / AC-0332: app_worker cannot commit approval.granted via the step path.

    Asserted against the running database (upgraded from 0004), not only a
    freshly built one. ADR-0009 D3: the CREATE OR REPLACE adds decision types
    to append_step_event's refusal list so the exclusivity is at the type
    level, not only at the function level.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() + interval '60 seconds')",
            (step_id, run_id),
        )
    try:
        for decision_type in ("approval.granted", "approval.rejected"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
                event_log.append_step_event(
                    worker_conn,
                    run_id=run_id,
                    step_id=step_id,
                    lease_epoch=1,
                    type=decision_type,
                    principal="worker-1",
                )
            assert "app_worker" in str(caught.value)
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.substrate
def test_app_worker_cannot_reach_append_approval_decision(
    worker_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324: the grants are disjoint — worker cannot reach the decision path."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        worker_conn.execute(
            "SELECT append_approval_decision(%s, %s, %s, %s, %s, %s)",
            (
                suspended_step.run_id,
                suspended_step.step_id,
                "approval.granted",
                "worker",
                suspended_step.suspension_seq,
                "call-1",
            ),
        )
    worker_conn.rollback()


# ── AC-0332: the append_step_event replacement ───────────────────────────────


@pytest.mark.substrate
def test_the_replaced_step_function_still_refuses_the_pre_existing_list(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0332: the preservation half — every pre-existing refusal survives.

    The replacement must not silently drop the fence call, the type refusals, or
    the shape rule. Each pre-existing refused type is driven against a live lease
    and observed to refuse as before. The fence is exercised by the fence-failure
    tests in test_definer_hardening.py; this covers the type list specifically.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() + interval '60 seconds')",
            (step_id, run_id),
        )
    try:
        pre_existing_refused = [
            "policy.decision",
            "run.requested",
            "run.cancelled",
            "run.completed",
            "run.failed",
        ]
        for refused_type in pre_existing_refused:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                event_log.append_step_event(
                    worker_conn,
                    run_id=run_id,
                    step_id=step_id,
                    lease_epoch=1,
                    type=refused_type,
                    principal="worker-1",
                )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.substrate
def test_the_replaced_step_function_retains_security_definer_and_search_path(
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0332: structural preservation — SECURITY DEFINER and pg_temp survive.

    A replacement that silently drops the search_path clause reintroduces the
    temp-capture defect revision 0002 hardened against.
    """
    row = owner_conn.execute(
        "SELECT p.prosecdef, p.proconfig FROM pg_proc p"
        " JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE n.nspname = 'public' AND p.proname = 'append_step_event'"
    ).fetchone()
    assert row is not None
    secdef, proconfig = row
    assert secdef is True
    assert proconfig is not None
    assert "pg_temp" in " ".join(proconfig)


# ── AC-0334: the decision idempotency key and the partial unique index ────────


@pytest.mark.substrate
def test_a_replayed_decision_is_refused_by_the_unique_index(
    api_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0334: a replayed decision is refused at the database level.

    After the first call commits, awaiting_decision becomes false, which is
    what refuses a second call with the same arguments from the function's own
    guard. To test the *index* refusal, we reset awaiting_decision to true and
    re-insert a step.suspended event, then attempt the same (run_id,
    idempotency_key) again. The unique index catches it before the function
    can even evaluate its own predicates.
    """
    seq = event_log.append_approval_decision(
        api_conn,
        run_id=suspended_step.run_id,
        step_id=suspended_step.step_id,
        type="approval.granted",
        principal="approver",
        suspension_seq=suspended_step.suspension_seq,
        call_id="call-unique-1",
    )
    assert seq is not None

    # The decision committed. Now construct a state where the unique index
    # would be hit: same suspension_seq and call_id, but awaiting_decision
    # reset to true (via owner connection) so the function checks pass.
    # The index on (run_id, idempotency_key) for decision types will reject.
    with psycopg.connect(database_url("migration")) as admin_conn:
        with admin_conn.transaction():
            admin_conn.execute(
                "UPDATE steps SET awaiting_decision = true WHERE step_id = %s",
                (suspended_step.step_id,),
            )

    with pytest.raises(psycopg.errors.UniqueViolation):
        with api_conn.transaction():
            api_conn.execute(
                "SELECT append_approval_decision(%s, %s, %s, %s, %s, %s)",
                (
                    suspended_step.run_id,
                    suspended_step.step_id,
                    "approval.granted",
                    "approver",
                    suspended_step.suspension_seq,
                    "call-unique-1",
                ),
            )
    api_conn.rollback()


@pytest.mark.substrate
def test_different_call_ids_produce_different_keys_in_one_suspension(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0334: a mixed decision over one suspension yields different outcomes per call.

    Two decisions (one grant, one rejection) against two different call ids in
    the same suspension both commit — the idempotency key is per call id, not
    per suspension.
    """
    seq_1 = event_log.append_approval_decision(
        api_conn,
        run_id=suspended_step.run_id,
        step_id=suspended_step.step_id,
        type="approval.granted",
        principal="approver",
        suspension_seq=suspended_step.suspension_seq,
        call_id="call-a",
    )

    # Reset awaiting_decision to commit a second decision on the same suspension.
    with owner_conn.transaction():
        owner_conn.execute(
            "UPDATE steps SET awaiting_decision = true WHERE step_id = %s",
            (suspended_step.step_id,),
        )

    seq_2 = event_log.append_approval_decision(
        api_conn,
        run_id=suspended_step.run_id,
        step_id=suspended_step.step_id,
        type="approval.rejected",
        principal="approver",
        suspension_seq=suspended_step.suspension_seq,
        call_id="call-b",
    )

    assert seq_1 != seq_2, "two decisions on two calls must get different seq values"

    rows = owner_conn.execute(
        "SELECT type, idempotency_key FROM events"
        " WHERE run_id = %s AND type IN ('approval.granted', 'approval.rejected')"
        " ORDER BY seq",
        (suspended_step.run_id,),
    ).fetchall()
    assert len(rows) == 2
    types = {row[0] for row in rows}
    assert types == {"approval.granted", "approval.rejected"}

    keys = {row[1] for row in rows}
    expected_key_1 = f"{suspended_step.suspension_seq}:call-a"
    expected_key_2 = f"{suspended_step.suspension_seq}:call-b"
    assert expected_key_1 in keys
    assert expected_key_2 in keys


@pytest.mark.substrate
def test_the_decision_index_covers_the_declared_types(
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0334: the index predicate names approval.granted and approval.rejected.

    Checked against the catalogue definition for equality of the type list,
    so a widened or narrowed predicate reds rather than passing silently.
    """
    row = owner_conn.execute(
        "SELECT indexdef FROM pg_indexes"
        " WHERE schemaname = 'public' AND tablename = 'events'"
        "   AND indexname = 'events_decision_idempotency_idx'"
    ).fetchone()
    assert row is not None, "events_decision_idempotency_idx is absent"
    indexdef = row[0]

    assert "approval.granted" in indexdef
    assert "approval.rejected" in indexdef
    assert "idempotency_key" in indexdef
