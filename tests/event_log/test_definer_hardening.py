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


def test_the_worker_can_still_call_the_fence(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """The heartbeat renews on it, so refusing DDL must not refuse EXECUTE."""
    held = worker_conn.execute(
        "SELECT fence_step(%s, %s)", (leased_step.step_id, leased_step.lease_epoch)
    ).fetchone()
    assert held == (True,)
    worker_conn.rollback()
