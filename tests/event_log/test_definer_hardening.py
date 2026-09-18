"""The definer functions resolve their own tables, and the fence is immutable.

Both properties are regressions from review round 1, and both were *observed*
failing before the fix rather than reasoned about:

  * With `search_path = pg_catalog, public` and unqualified relation names, a
    caller running `CREATE TEMP TABLE events` had its append written into its
    own temporary schema while `public.runs.next_seq` still advanced — a
    suppressed audit record plus the permanent sequence hole the row-update
    counter exists to prevent. A temp `runs` seeded with `next_seq = 499` made
    the same call write `seq = 500` into the real `public.events`.
  * With `fence_step` owned by `app_worker`, that role could `DROP` it — which
    breaks the policy-decision append for every role — or `ALTER` its
    `search_path`.

Neither was caught by AC-0005, which asserts the forgery refusal and passes
with the fence fully subverted. These tests are what close that gap.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from ced.adapters.postgres import event_log

from .conftest import LeasedStep, next_seq_of, sequence_of

pytestmark = pytest.mark.substrate

_TEMP_EVENTS = """
    CREATE TEMP TABLE events (
        run_id uuid, seq bigint, occurred_at timestamptz DEFAULT now(),
        type text, step_id uuid, agent_role text, principal text,
        payload_ref text, idempotency_key text, schema_version int DEFAULT 1)
"""
_TEMP_RUNS = "CREATE TEMP TABLE runs (run_id uuid, next_seq bigint, state text)"
_TEMP_STEPS = "CREATE TEMP TABLE steps (step_id uuid, lease_epoch bigint)"


def test_the_definer_functions_are_configured_to_resist_temp_capture(
    owner_conn: psycopg.Connection,
) -> None:
    """A structural check, so the behavioural ones below have a named cause.

    `pg_temp` must appear in every definer `search_path`. Postgres searches the
    temporary schema *first* for relation names when it is not listed, so its
    absence — not its presence — is the defect.
    """
    rows = owner_conn.execute(
        """
        SELECT p.proname, array_to_string(p.proconfig, ',')
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public' AND p.prosecdef
        """
    ).fetchall()

    assert len(rows) == 4, f"expected four definer functions, found {rows}"
    for name, config in rows:
        assert config is not None, f"{name} sets no search_path at all"
        assert "pg_temp" in config, f"{name} omits pg_temp: {config!r}"


def test_a_temp_events_table_does_not_capture_the_append(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The event lands in `public.events`, and nothing lands in `pg_temp`."""
    worker_conn.execute(_TEMP_EVENTS)
    worker_conn.commit()

    seq = event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type="step.started",
        principal="worker-1",
    )

    assert seq == 1
    captured = worker_conn.execute("SELECT count(*) FROM pg_temp.events").fetchone()
    assert captured == (0,), "the append was captured by the caller's temp table"
    assert sequence_of(owner_conn, leased_step.run_id) == [1]


def test_a_temp_runs_table_does_not_let_the_caller_choose_its_own_seq(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """`seq` comes from `public.runs`, not from a counter the caller controls."""
    worker_conn.execute(_TEMP_RUNS)
    worker_conn.execute(
        "INSERT INTO pg_temp.runs VALUES (%s, 499, 'requested')",
        (leased_step.run_id,),
    )
    worker_conn.commit()

    seq = event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type="step.started",
        principal="worker-1",
    )

    assert seq == 1, "the caller's temp `runs` supplied the sequence number"
    assert next_seq_of(owner_conn, leased_step.run_id) == 1


def test_a_temp_steps_table_does_not_satisfy_the_fence(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """A fabricated step and epoch must still be fenced.

    This is the one that matters most: a temp `steps` row with any epoch the
    caller likes would make the fence return true for a lease the caller does
    not hold, which is the split-brain the epoch fence exists to stop.
    """
    worker_conn.execute(_TEMP_STEPS)
    worker_conn.execute("INSERT INTO pg_temp.steps VALUES (%s, 999)", (leased_step.step_id,))
    worker_conn.commit()

    with pytest.raises(event_log.Fenced):
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=999,
            type="step.started",
            principal="worker-1",
        )


def test_a_temp_steps_table_does_not_deny_the_policy_write_path(
    policy_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """The other half of the temp-capture defect, and it was a denial.

    Before the fix, a temp `steps` in the *policy* role's session turned
    `append_policy_decision` into `permission denied for table steps` — the
    definer could not read the caller's temporary table — so any caller could
    switch off the authorization-audit write path.
    """
    policy_conn.execute(_TEMP_STEPS)
    policy_conn.commit()

    seq = event_log.append_policy_decision(
        policy_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        principal="policy-writer",
    )
    assert seq == 1


# ── ADR-0004: the fence is not mutable by the role it constrains ────────────


def test_the_fence_is_owned_by_a_role_no_process_can_authenticate_as(
    owner_conn: psycopg.Connection,
) -> None:
    """ADR-0004 D1. `NOLOGIN`, and granted to no application role."""
    row = owner_conn.execute(
        """
        SELECT pg_get_userbyid(p.proowner), r.rolcanlogin
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
          JOIN pg_roles r ON r.oid = p.proowner
         WHERE n.nspname = 'public' AND p.proname = 'fence_step'
        """
    ).fetchone()
    assert row is not None, "fence_step is absent"
    owner, can_login = row

    assert owner == "ced_fence"
    assert can_login is False, "the fence's owner can log in"

    members = owner_conn.execute(
        """
        SELECT m.rolname
          FROM pg_auth_members am
          JOIN pg_roles r ON r.oid = am.roleid
          JOIN pg_roles m ON m.oid = am.member
         WHERE r.rolname = 'ced_fence'
        """
    ).fetchall()
    # `ced_owner` only, so a migration can assign ownership. No login role.
    assert {m[0] for m in members} == {"ced_owner"}


@pytest.mark.parametrize(
    "statement",
    [
        "DROP FUNCTION fence_step(uuid, bigint)",
        "ALTER FUNCTION fence_step(uuid, bigint) SET search_path = pg_temp, pg_catalog, public",
        "ALTER FUNCTION fence_step(uuid, bigint) OWNER TO app_worker",
        "CREATE OR REPLACE FUNCTION fence_step(p_step_id uuid, p_lease_epoch bigint) "
        "RETURNS boolean LANGUAGE sql AS $$ SELECT true $$",
    ],
)
def test_the_worker_cannot_alter_or_drop_the_fence(
    worker_conn: psycopg.Connection, statement: str
) -> None:
    """ADR-0004 D4 — a control whose defeat nobody has attempted is not one.

    Each of these succeeded while the fence was owned by `app_worker`, and each
    of them either disables the fence or redirects its name resolution.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        worker_conn.execute(statement)
    worker_conn.rollback()


# ── The fenced step must belong to the run being written ────────────────────


def test_a_lease_on_one_run_does_not_authorize_an_append_to_another(
    policy_conn: psycopg.Connection,
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The forgery the privilege split exists to contain, closed.

    The fence proves a lease on a *step*. It did not prove the step belonged to
    the run being appended to, so one live lease authorized an append — with a
    caller-chosen `principal` and `agent_role` — into any run's log. Observed
    as `app_policy`, the narrowest role in the system, which holds `SELECT` on
    `steps` and one `EXECUTE` and nothing else.
    """
    other_run = uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (other_run,))
    try:
        with pytest.raises(event_log.StepRunMismatch):
            event_log.append_policy_decision(
                policy_conn,
                run_id=other_run,
                step_id=leased_step.step_id,
                lease_epoch=leased_step.lease_epoch,
                principal="forged-principal",
                agent_role="forged-role",
            )
        with pytest.raises(event_log.StepRunMismatch):
            event_log.append_step_event(
                worker_conn,
                run_id=other_run,
                step_id=leased_step.step_id,
                lease_epoch=leased_step.lease_epoch,
                type="step.started",
                principal="worker-1",
            )

        # Neither attempt advanced the other run's counter or wrote an event.
        row = owner_conn.execute(
            "SELECT next_seq, (SELECT count(*) FROM events WHERE run_id = %s) "
            "FROM runs WHERE run_id = %s",
            (other_run, other_run),
        ).fetchone()
        assert row == (0, 0)
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (other_run,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (other_run,))


def test_the_coherent_pair_is_still_accepted(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """A check that only refuses is a build break, not a control."""
    assert (
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type="step.started",
            principal="worker-1",
        )
        == 1
    )


# ── The step path is restricted to step-scoped types ───────────────────────


@pytest.mark.parametrize(
    "event_type",
    ["run.requested", "run.cancelled", "run.completed", "run.failed"],
)
def test_the_step_path_refuses_the_run_lifecycle_namespace(
    worker_conn: psycopg.Connection, leased_step: LeasedStep, event_type: str
) -> None:
    """r7 § Identity restricts `worker` to its step-scoped types.

    Refusing only `policy.decision` let the worker write `run.completed` and
    `run.cancelled` with a step_id attached — and `events_terminal_idx` indexes
    exactly those names, so the write closed the stream from a path that
    carries no terminal-state guard. Observed before the fix.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=event_type,
            principal="worker-1",
        )
    assert "app_worker" in str(caught.value)


def test_the_refused_set_matches_the_migration_constant(
    owner_conn: psycopg.Connection,
) -> None:
    """The refusal list and the domain vocabulary must not drift apart."""
    from ced.domain.events import (
        RESERVED_EVENT_TYPE,
        RUN_LIFECYCLE_TYPES,
        TERMINAL_EVENT_TYPES,
    )

    row = owner_conn.execute(
        "SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'append_step_event'"
    ).fetchone()
    assert row is not None
    # The guard compares a normalised form, so the marker is the normalising
    # call rather than the bare parameter (ADR-0005's sibling fix).
    refused = row[0].split("lower(btrim(p_type)) IN (", 1)[1].split(")", 1)[0]
    names = {piece.strip().strip("'") for piece in refused.split(",")}

    expected = {RESERVED_EVENT_TYPE, *RUN_LIFECYCLE_TYPES, *TERMINAL_EVENT_TYPES}
    assert names == expected, (
        f"the step path refuses {sorted(names)} while the domain vocabulary "
        f"names {sorted(expected)}"
    )


def test_the_worker_holds_no_direct_execute_on_the_fence(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """The grant's stated rationale named a caller that does not exist.

    It read "the heartbeat renews on it", but `renew` issues a direct
    `UPDATE steps … FROM runs` and nothing in `src/` calls `fence_step`. The
    three append functions reach it at `ced_owner`'s privilege. The grant let
    the worker take `FOR UPDATE` row locks on arbitrary `steps` rows for no
    reason, so it was removed.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        worker_conn.execute(
            "SELECT fence_step(%s, %s)",
            (leased_step.step_id, leased_step.lease_epoch),
        )
    worker_conn.rollback()


def test_the_fence_owner_holds_no_standing_create_on_the_schema(
    owner_conn: psycopg.Connection,
) -> None:
    """Revision 0002 grants `ced_fence` CREATE transiently and revokes it.

    `ced_fence` is `NOLOGIN`, so a connection-based probe cannot reach it and
    the three login roles never held the grant — a failed or reordered revoke
    was invisible to the suite. This asserts the catalogue directly.
    """
    row = owner_conn.execute(
        "SELECT has_schema_privilege('ced_fence', 'public', 'CREATE'), "
        "       has_schema_privilege('ced_fence', 'public', 'USAGE')"
    ).fetchone()
    assert row == (False, True)


# ── ADR-0005: the fence proves possession, not knowledge of the epoch ───────


def test_a_never_claimed_step_is_not_appendable(
    policy_conn: psycopg.Connection,
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """The forgery ADR-0005 closes, on both fenced paths.

    `steps.lease_epoch` is `NOT NULL DEFAULT 0`, so before ADR-0005 a step no
    worker had ever leased was fenced at 0 — and `app_policy`, whose only
    capability is one `EXECUTE` grant, wrote a `policy.decision` against it
    with a caller-chosen `principal` and `agent_role`. Observed, not theorised.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id) VALUES (%s, %s)", (step_id, run_id)
        )
    try:
        with pytest.raises(event_log.Fenced):
            event_log.append_policy_decision(
                policy_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=0,
                principal="attacker-chosen-principal",
                agent_role="forged-role",
            )
        with pytest.raises(event_log.Fenced):
            event_log.append_step_event(
                worker_conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=0,
                type="step.started",
                principal="worker-1",
            )
        row = owner_conn.execute(
            "SELECT next_seq, (SELECT count(*) FROM events WHERE run_id = %s) "
            "FROM runs WHERE run_id = %s",
            (run_id, run_id),
        ).fetchone()
        assert row == (0, 0)
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


@pytest.mark.parametrize(
    ("label", "mutation"),
    [
        ("an expired lease", "lease_expires_at = clock_timestamp() - interval '1 s'"),
        ("a released lease", "lease_expires_at = NULL"),
        ("a drained lease", "lease_expires_at = clock_timestamp()"),
        ("an ownerless lease", "owner = NULL"),
    ],
)
def test_a_lease_that_is_not_live_and_owned_is_not_appendable(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
    label: str,
    mutation: str,
) -> None:
    """Each adjacent state the epoch-only fence admitted, now refused.

    `release` nulls the expiry and the drain sets it to `now()`; neither is a
    live lease, and the correct epoch is no longer sufficient on its own.
    """
    with owner_conn.transaction():
        owner_conn.execute(
            f"UPDATE steps SET {mutation} WHERE step_id = %s", (leased_step.step_id,)
        )

    with pytest.raises(event_log.Fenced):
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type="step.started",
            principal="worker-1",
        )


def test_the_fence_predicate_names_liveness_and_ownership(
    owner_conn: psycopg.Connection,
) -> None:
    """A structural check, so the behavioural ones above have a named cause."""
    row = owner_conn.execute(
        "SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'fence_step'"
    ).fetchone()
    assert row is not None, "fence_step is absent"
    body = row[0]

    assert "owner IS NOT NULL" in body, "the fence does not require an owner"
    assert "lease_expires_at > now()" in body, "the fence does not require liveness"


@pytest.mark.parametrize(
    "variant", ["run.completed ", "RUN.COMPLETED", " Run.Cancelled ", "POLICY.DECISION"]
)
def test_no_spelling_of_a_refused_type_reaches_the_log(
    worker_conn: psycopg.Connection, leased_step: LeasedStep, variant: str
) -> None:
    """The refusal is decided on a normalised form.

    It compared the raw argument, so a trimmed or case-varied spelling of a
    refused name was admitted and stored verbatim — a negative rule narrower
    than the rule it states, and a live bypass for any reader that normalises.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=variant,
            principal="worker-1",
        )


def test_an_admitted_type_is_stored_canonically(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """So no reader — here or in a sibling spec — has to normalise on the way out."""
    event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type="  Step.Started  ",
        principal="worker-1",
    )

    row = owner_conn.execute(
        "SELECT type FROM events WHERE run_id = %s", (leased_step.run_id,)
    ).fetchone()
    assert row == ("step.started",)
