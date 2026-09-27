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
    re-asserted here. The grant query is scoped by specific_name so a stray
    overload's grantees cannot fold into the disjointness set.
    """
    sig = "public.append_run_terminal(uuid, uuid, bigint, text, text, text, text)"
    # Resolve to the specific_name first so a stray overload is excluded.
    spec_row = owner_conn.execute(
        "SELECT specific_name FROM information_schema.routines"
        " WHERE routine_schema = 'public' AND routine_name = 'append_run_terminal'",
    ).fetchone()
    assert spec_row is not None, f"{sig} not found in information_schema.routines"
    specific_name = spec_row[0]

    rows = owner_conn.execute(
        "SELECT grantee, privilege_type FROM information_schema.routine_privileges"
        " WHERE specific_schema = 'public'"
        "   AND specific_name = %s"
        "   AND privilege_type = 'EXECUTE'",
        (specific_name,),
    ).fetchall()
    grantees = {row[0] for row in rows}

    # spec.md:135 binds the path to "app_worker and to no other role".
    # Named exclusions leave later additions silent; equality pins the full set.
    assert grantees == {"ced_owner", "app_worker"}, (
        f"append_run_terminal EXECUTE grantee set is {grantees!r}, "
        "expected exactly {{'ced_owner', 'app_worker'}}; "
        "an added grantee would satisfy the named-exclusion checks above"
    )


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
def test_run_terminal_refuses_a_never_leased_step(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0320: fence_step's possession half — owner IS NULL refuses at epoch 0.

    `lease_epoch` is NOT NULL DEFAULT 0, so epoch alone passed a fresh
    (never-leased) step on an earlier implementation. fence_step's second
    predicate (`owner IS NOT NULL AND lease_expires_at > clock_timestamp()`)
    closes this: a step that was never leased has owner=NULL and is refused.
    ADR-0005 records this as the observed forgery the possession check closes.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'running')",
            (run_id,),
        )
        # Insert a step that was never leased: owner=NULL, lease_epoch=0 (default).
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state) VALUES (%s, %s, 'runnable')",
            (step_id, run_id),
        )
    try:
        with pytest.raises(event_log.Fenced):
            event_log.append_run_terminal(
                worker_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=0,  # matches DEFAULT but owner IS NULL
                type="run.completed",
                principal="worker-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.substrate
def test_run_terminal_refuses_an_expired_lease(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0320: fence_step's possession half — an expired lease is refused.

    `lease_expires_at > clock_timestamp()` must use clock_timestamp(), not
    now(), which is the caller's transaction start time. fence_step uses
    clock_timestamp() so an expired lease is refused even when the caller's
    transaction started while the lease was still live. ADR-0005.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO runs (run_id, state) VALUES (%s, 'running')",
            (run_id,),
        )
        # Insert a step with an already-expired lease (past in the past).
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() - interval '10 seconds')",
            (step_id, run_id),
        )
    try:
        with pytest.raises(event_log.Fenced):
            event_log.append_run_terminal(
                worker_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=1,  # correct epoch, but lease is expired
                type="run.completed",
                principal="worker-1",
            )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


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
    """AC-0320: with the event INSERT forced to fail, runs.state does not move.

    Forces the INSERT into events to fail by pre-inserting a row at the seq
    the call will allocate (next_seq + 1 = 1 on a fresh run, so seq=1). The
    UPDATE public.runs commits its state change in the same statement as the
    seq advance; the INSERT then violates the primary key and the whole
    transaction rolls back, proving that runs.state and the event commit
    together or not at all.

    A fence failure (wrong epoch) would roll back before the UPDATE, so it
    would not distinguish a correct atomic implementation from one with a
    separate UPDATE and INSERT. This scenario forces the INSERT — not the
    fence — to be the failing layer.
    """
    # Pre-insert an events row at the seq the call will allocate (seq=1 on
    # this run, since next_seq starts at 0 and the function advances it to 1).
    with owner_conn.transaction():
        owner_conn.execute(
            "INSERT INTO events (run_id, seq, type, step_id, principal) "
            "VALUES (%s, 1, 'run.requested', NULL, 'blocker')",
            (running_step.run_id,),
        )

    row_before = owner_conn.execute(
        "SELECT state FROM runs WHERE run_id = %s",
        (running_step.run_id,),
    ).fetchone()
    assert row_before is not None
    state_before = row_before[0]

    with pytest.raises(psycopg.errors.UniqueViolation):
        # The INSERT into events fails with UniqueViolation on (run_id, seq).
        # The wrapper re-raises it: the generic DatabaseError catch only
        # intercepts CED01 and re-raises anything else, so UniqueViolation
        # (SQLSTATE 23505) propagates unchanged.
        event_log.append_run_terminal(
            worker_conn,
            run_id=running_step.run_id,
            step_id=running_step.step_id,
            lease_epoch=running_step.lease_epoch,
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
        "even though the event INSERT failed — the state change and the "
        "event insert do not commit atomically"
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
    """AC-0324: the grant set stays disjoint.

    The grant query is scoped by specific_name so a stray overload's grantees
    cannot fold into the disjointness set.
    """
    sig = (
        "public.append_approval_decision(uuid, uuid, text[], text[], text, bigint, text, text)"
    )
    # Resolve to the specific_name first so a stray overload is excluded.
    spec_row = owner_conn.execute(
        "SELECT specific_name FROM information_schema.routines"
        " WHERE routine_schema = 'public' AND routine_name = 'append_approval_decision'",
    ).fetchone()
    assert spec_row is not None, f"{sig} not found in information_schema.routines"
    specific_name = spec_row[0]

    rows = owner_conn.execute(
        "SELECT grantee, privilege_type FROM information_schema.routine_privileges"
        " WHERE specific_schema = 'public'"
        "   AND specific_name = %s"
        "   AND privilege_type = 'EXECUTE'",
        (specific_name,),
    ).fetchall()
    grantees = {row[0] for row in rows}

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
            call_ids=["call-1"],
            decisions=["step.suspended"],
            principal="approver",
            suspension_seq=suspended_step.suspension_seq,
        )


@pytest.mark.substrate
def test_approval_decision_refuses_an_empty_decision_set(
    api_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324: an empty call_ids list is refused before the steps lock is taken.

    Passing an empty array leaves no work to do and would clear awaiting_decision
    without recording any event. The function refuses this before any lock via
    serialization_failure, mapped to DecisionRefused — not StepRunMismatch
    (which signals run/step membership disagreement, not a malformed submission).
    """
    with pytest.raises(event_log.DecisionRefused):
        event_log.append_approval_decision(
            api_conn,
            run_id=suspended_step.run_id,
            step_id=suspended_step.step_id,
            call_ids=[],
            decisions=[],
            principal="approver",
            suspension_seq=suspended_step.suspension_seq,
        )


@pytest.mark.substrate
def test_approval_decision_refuses_an_empty_call_id(
    api_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324: a null or empty call_id element is refused before any INSERT.

    An empty string propagates through the idempotency_key expression as
    '<suspension_seq>:' — a non-null key the partial index can see. The function
    refuses it via serialization_failure, mapped to DecisionRefused — not
    MalformedEventType (which is CED01, documented as "the event type is not a
    dotted run of lowercase ASCII alphanumerics"; a call_id is not an event type).
    """
    with pytest.raises(event_log.DecisionRefused):
        event_log.append_approval_decision(
            api_conn,
            run_id=suspended_step.run_id,
            step_id=suspended_step.step_id,
            call_ids=[""],  # empty string, not a valid call_id
            decisions=["approval.granted"],
            principal="approver",
            suspension_seq=suspended_step.suspension_seq,
        )


@pytest.mark.substrate
def test_approval_decision_refuses_mismatched_array_lengths(
    api_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0324: call_ids and decisions must have the same cardinality.

    A mismatch means the parallel-array contract is violated. The function
    refuses before taking any lock via serialization_failure, mapped to
    DecisionRefused — not StepRunMismatch (which signals run/step membership
    disagreement, not a malformed submission).
    """
    with pytest.raises(event_log.DecisionRefused):
        event_log.append_approval_decision(
            api_conn,
            run_id=suspended_step.run_id,
            step_id=suspended_step.step_id,
            call_ids=["call-1", "call-2"],  # two call ids
            decisions=["approval.granted"],  # but only one decision
            principal="approver",
            suspension_seq=suspended_step.suspension_seq,
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
                call_ids=["call-1"],
                decisions=["approval.granted"],
                principal="approver",
                suspension_seq=suspended_step.suspension_seq,
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
                call_ids=["call-1"],
                decisions=["approval.granted"],
                principal="approver",
                suspension_seq=1,  # no event at seq=1 exists
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
            call_ids=["call-1"],
            decisions=["approval.granted"],
            principal="approver",
            suspension_seq=suspended_step.suspension_seq,  # seq=1, stale
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
                call_ids=["call-1"],
                decisions=["approval.granted"],
                principal="approver",
                suspension_seq=1,
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
    """AC-0324: a valid call succeeds and clears awaiting_decision.

    The fixture inserts step.suspended at seq=1 (next_seq advances to 1).
    The decision append advances next_seq to 2 and commits at seq=2.
    """
    seq = event_log.append_approval_decision(
        api_conn,
        run_id=suspended_step.run_id,
        step_id=suspended_step.step_id,
        call_ids=["call-1"],
        decisions=["approval.granted"],
        principal="approver",
        suspension_seq=suspended_step.suspension_seq,
    )
    assert seq == 2, f"expected seq 2 (step.suspended at 1, decision at 2), got {seq}"

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
            "SELECT append_approval_decision(%s, %s, %s::text[], %s::text[], %s, %s)",
            (
                suspended_step.run_id,
                suspended_step.step_id,
                ["call-1"],
                ["approval.granted"],
                "worker",
                suspended_step.suspension_seq,
            ),
        )
    worker_conn.rollback()


@pytest.mark.substrate
def test_concurrent_decisions_against_one_suspension_exactly_one_commits(
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0324: of two concurrent decisions against one suspension, exactly one commits.

    The FOR UPDATE on the steps row serialises concurrent callers. The second
    concurrent caller sees awaiting_decision = false after the first commits
    and is refused, so no two decision sets can commit against the same
    suspension. Asserted by driving overlapping transactions and confirming
    exactly one committed event and one refusal.
    """
    import threading

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
        owner_conn.execute(
            "UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s",
            (run_id,),
        )
        owner_conn.execute(
            "INSERT INTO events (run_id, seq, type, step_id, principal) "
            "VALUES (%s, 1, 'step.suspended', %s, 'fixture')",
            (run_id, step_id),
        )

    committed: list[int] = []
    refused: list[str] = []
    barrier = threading.Barrier(2)

    def attempt(call_id: str) -> None:
        from ced.adapters.postgres.dsn import database_url

        with psycopg.connect(database_url("api")) as conn:
            try:
                # Both threads reach the function at the same time. The FOR UPDATE
                # serialises them; one succeeds, the other sees awaiting_decision=false.
                barrier.wait(timeout=10.0)
                with conn.transaction():
                    row = conn.execute(
                        "SELECT append_approval_decision("
                        "%s, %s, %s::text[], %s::text[], %s, %s)",
                        (
                            run_id,
                            step_id,
                            [call_id],
                            ["approval.granted"],
                            "approver",
                            1,  # suspension_seq
                        ),
                    ).fetchone()
                assert row is not None
                committed.append(int(row[0]))
            except psycopg.errors.SerializationFailure as exc:
                refused.append(str(exc).splitlines()[0])

    threads = [
        threading.Thread(target=attempt, args=("call-concurrent-a",)),
        threading.Thread(target=attempt, args=("call-concurrent-b",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert len(committed) == 1, (
            f"expected exactly 1 commit, got {len(committed)}: "
            f"committed={committed}, refused={refused}"
        )
        assert len(refused) == 1, (
            f"expected exactly 1 refusal, got {len(refused)}: "
            f"committed={committed}, refused={refused}"
        )
        # Exactly one decision event must be in the log.
        event_rows = owner_conn.execute(
            "SELECT type FROM events WHERE run_id = %s"
            " AND type IN ('approval.granted', 'approval.rejected')",
            (run_id,),
        ).fetchall()
        assert len(event_rows) == 1, (
            f"expected 1 committed decision event, got {len(event_rows)}"
        )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


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
    """AC-0332: structural preservation — SECURITY DEFINER, pg_temp, and owner survive.

    A replacement that silently drops the search_path clause reintroduces the
    temp-capture defect revision 0002 hardened against. The owner assertion
    guards the case where CREATE OR REPLACE silently reassigns the definer
    function to a different owner — which would change the privilege context
    inside the SECURITY DEFINER body.
    """
    row = owner_conn.execute(
        "SELECT p.prosecdef, p.proconfig, pg_get_userbyid(p.proowner) FROM pg_proc p"
        " JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE n.nspname = 'public' AND p.proname = 'append_step_event'"
    ).fetchone()
    assert row is not None
    secdef, proconfig, owner = row
    assert secdef is True
    assert proconfig is not None
    # "pg_temp" in the joined string is too weak: search_path=pg_temp,public
    # would pass while putting pg_temp first — exactly the temp-capture ordering
    # the pin exists to prevent. Assert the exact entry instead.
    assert "search_path=pg_catalog, pg_temp" in proconfig, (
        f"append_step_event has proconfig {proconfig!r}; "
        "expected entry 'search_path=pg_catalog, pg_temp' to be present"
    )
    assert owner == "ced_owner", (
        f"append_step_event owner is {owner!r}, expected 'ced_owner'; "
        "a CREATE OR REPLACE that changed the owner would alter the definer context"
    )


# ── AC-0334: the decision idempotency key and the partial unique index ────────


@pytest.mark.substrate
def test_a_replayed_decision_is_refused_by_the_unique_index(
    api_conn: psycopg.Connection,
    suspended_step: SuspendedStep,
) -> None:
    """AC-0334: a replayed decision is refused at the database level.

    The set-valued function accepts parallel arrays. Passing the same call_id
    twice in one call reaches the partial unique index on the second INSERT:
    the first INSERT commits "1:call-replay" and the second INSERT of the
    same (run_id, idempotency_key) raises UniqueViolation, rolling back the
    whole transaction. The index — not the function's own guard — is the
    refusing layer. No out-of-band state manipulation is needed.
    """
    with pytest.raises(psycopg.errors.UniqueViolation):
        with api_conn.transaction():
            api_conn.execute(
                "SELECT append_approval_decision(%s, %s, %s::text[], %s::text[], %s, %s)",
                (
                    suspended_step.run_id,
                    suspended_step.step_id,
                    ["call-replay", "call-replay"],  # duplicate call_id
                    ["approval.granted", "approval.rejected"],
                    "approver",
                    suspended_step.suspension_seq,
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

    Both call ids are submitted in one set-valued call through the app_api
    grant alone — no out-of-band state edit between them. The function appends
    one event per pair, clears the hold once, and advances the cycle counter
    once. Both events commit in the same transaction against the one suspension.
    """
    last_seq = event_log.append_approval_decision(
        api_conn,
        run_id=suspended_step.run_id,
        step_id=suspended_step.step_id,
        call_ids=["call-a", "call-b"],
        decisions=["approval.granted", "approval.rejected"],
        principal="approver",
        suspension_seq=suspended_step.suspension_seq,
    )
    # The fixture puts step.suspended at seq=1; two decision events land at
    # seq=2 and seq=3. The function returns the last seq allocated.
    assert last_seq == 3, f"expected last_seq 3, got {last_seq}"

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

    # awaiting_decision cleared and approval_cycles advanced exactly once.
    step_row = owner_conn.execute(
        "SELECT awaiting_decision, approval_cycles FROM steps WHERE step_id = %s",
        (suspended_step.step_id,),
    ).fetchone()
    assert step_row is not None
    assert step_row[0] is False
    assert step_row[1] == 1


@pytest.mark.substrate
def test_the_decision_index_covers_the_declared_types(
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0334: the index predicate names exactly approval.granted and approval.rejected.

    Asserted by equality on the extracted type list so a widened or narrowed
    predicate reds rather than passing silently. Substring checks would pass
    for a predicate widened to a third decision type.
    """
    row = owner_conn.execute(
        "SELECT indexdef FROM pg_indexes"
        " WHERE schemaname = 'public' AND tablename = 'events'"
        "   AND indexname = 'events_decision_idempotency_idx'"
    ).fetchone()
    assert row is not None, "events_decision_idempotency_idx is absent"
    indexdef = row[0]

    # Extract the type list from the WHERE clause. PostgreSQL renders it as:
    # ... WHERE ((type = ANY (ARRAY['approval.granted'::text, ...])))
    # or: ... WHERE (type IN ('approval.granted', 'approval.rejected')) ...
    # Pull out quoted strings from the predicate and assert the exact set.
    import re

    quoted = re.findall(r"'([^']+)'", indexdef)
    type_values = {v for v in quoted if "." in v}  # filter to event-type-shaped values
    assert type_values == {
        "approval.granted",
        "approval.rejected",
    }, (
        f"index predicate type list {type_values!r} does not match the expected "
        "set; a widened or narrowed predicate is present"
    )
