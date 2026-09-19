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

import re
import time
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
    # call rather than the bare parameter (ADR-0005's sibling fix). Matched by
    # pattern rather than by a literal prefix: the normaliser is now a
    # `regexp_replace` whose own parentheses broke the old `split(")")`, and a
    # marker that has to be rewritten whenever the expression is edited is a
    # check that reds for the wrong reason.
    match = re.search(r"regexp_replace\(p_type.*?\)\)\s+IN \(([^)]*)\)", row[0], re.S)
    assert match is not None, (
        "the refusal list is not where this check looks for it; the normaliser "
        "or the guard's shape changed"
    )
    refused = match.group(1)
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


def test_a_lease_that_lapsed_during_the_callers_transaction_is_not_appendable(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The one liveness shape the parametrized table above cannot reach.

    Every case there forces expiry into the absolute past, so transaction age
    cannot matter. Here the lease is live when the caller's transaction opens
    and dead in real time when it appends — which is the state a frozen
    `now()` admitted, because `SECURITY DEFINER` does not reset
    `transaction_timestamp()`. Reproduced as `app_policy` before the fix: the
    forged `policy.decision` committed against a lease dead by a second and a
    half.

    `psycopg`'s `conn.transaction()` nests as a savepoint once a transaction is
    open, so the append below genuinely runs under the older snapshot rather
    than starting its own.
    """
    with owner_conn.transaction():
        owner_conn.execute(
            "UPDATE steps SET lease_expires_at = clock_timestamp() "
            "+ interval '2 seconds' WHERE step_id = %s",
            (leased_step.step_id,),
        )

    # Open the caller's transaction while the lease is still live, and prove it
    # is open — an autocommit connection would reset the clock per statement
    # and the check would pass for the wrong reason.
    worker_conn.execute("SELECT 1")
    assert worker_conn.info.transaction_status.name == "INTRANS"
    frozen = worker_conn.execute("SELECT now()").fetchone()[0]

    time.sleep(3)

    # `expiry` is read here too, because the guard below needs it. Without that
    # guard this check degrades silently: a stall longer than the window
    # between the owner's commit and the `SELECT 1` puts the frozen timestamp
    # past expiry, where the *defective* `> now()` predicate also refuses — so
    # it would pass with the bug present, having quietly become one more row of
    # the absolute-past table above.
    still_frozen, really_dead, expiry = worker_conn.execute(
        "SELECT now() = %s, lease_expires_at < clock_timestamp(), lease_expires_at "
        "FROM steps WHERE step_id = %s",
        (frozen, leased_step.step_id),
    ).fetchone()
    assert still_frozen, (
        "the caller's transaction timestamp advanced, so this check is not "
        "exercising the frozen-clock caller it exists for"
    )
    assert really_dead, "the lease did not actually lapse; the wait was too short"
    assert frozen < expiry, (
        "the caller's transaction opened *after* the lease had already expired "
        f"({frozen} is past {expiry}), so a transaction-timestamp predicate "
        "would refuse this append too — the check would pass with the defect "
        "present instead of exercising it"
    )

    # Rolled back in `finally`, and that is not tidiness. This check has to
    # leave its transaction open to mean anything, so on the failure it exists
    # to catch — the append succeeding — the row locks it takes would still be
    # held when `leased_step` tears down, and the fixture's `DELETE` would
    # block on them indefinitely. The first version did exactly that and hung
    # the suite instead of redding it, which is strictly worse than no check.
    try:
        with pytest.raises(event_log.Fenced):
            event_log.append_step_event(
                worker_conn,
                run_id=leased_step.run_id,
                step_id=leased_step.step_id,
                lease_epoch=leased_step.lease_epoch,
                type="step.started",
                principal="worker-1",
            )
    finally:
        worker_conn.rollback()


def test_a_padded_admitted_type_cannot_escape_the_idempotency_index(
    worker_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The dedup consequence, which is worse than the forged-audit one.

    `events_tool_invoked_idempotency_idx` is partial on `type = 'tool.invoked'`,
    so before the fix a single trailing tab put the row outside the index
    entirely and two appends sharing one derived key both committed — defeating
    the guarantee `src/ced/domain/events.py` rests the two-worker overlap on.
    Canonicalising before the insert is what puts the variant back inside it.
    """
    key = "derived-key-for-one-tool-call"
    event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type="tool.invoked",
        principal="worker-1",
        idempotency_key=key,
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type="tool.invoked\t",
            principal="worker-1",
            idempotency_key=key,
        )

    # Read back the *padded* append under its own key, not the canonical one.
    # This asserted the stored type of `first`, whose argument was already
    # canonical — so it held under any change to how padding is treated, which
    # is precisely the regression this check sits under. The padded variant is
    # the only row that evidences the canonicalisation.
    padded_seq = event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type="tool.invoked\t",
        principal="worker-1",
        idempotency_key="a-second-tool-call",
    )
    stored = owner_conn.execute(
        "SELECT type FROM events WHERE run_id = %s AND seq = %s",
        (leased_step.run_id, padded_seq),
    ).fetchone()[0]
    assert stored == "tool.invoked", (
        f"a tab-padded `tool.invoked` stored as {stored!r}, so it sits outside "
        "`events_tool_invoked_idempotency_idx` and the derived key dedups "
        "nothing for that spelling"
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
    # `clock_timestamp()`, and the absence of `now()`, are both asserted. The
    # pin used to name `lease_expires_at > now()`, which is the defect round 4
    # found rather than the property: `now()` is the caller's
    # `transaction_timestamp()` and `SECURITY DEFINER` does not reset it, so a
    # caller holding a transaction open outlived its own lease. Pinning the
    # wrong spelling would have forced the defect back in on the next edit.
    assert "lease_expires_at > clock_timestamp()" in body, (
        "the fence does not decide liveness against the real current time"
    )
    assert "lease_expires_at > now()" not in body, (
        "the fence compares against the caller's transaction timestamp, which "
        "a caller can freeze by holding a transaction open"
    )


@pytest.mark.parametrize(
    "variant",
    [
        "run.completed ",
        "RUN.COMPLETED",
        " Run.Cancelled ",
        "POLICY.DECISION",
        # Round 4. The normaliser was `lower(btrim(...))`, and one-argument
        # `btrim` strips only U+0020 — so every spelling below was admitted and
        # stored verbatim, reproduced as `app_worker` against the substrate.
        # The table had only the space-padded and case-varied forms, so it
        # could not red for any of them.
        "policy.decision\t",
        "\tpolicy.decision",
        "policy.decision\n",
        "run.completed\r",
        "policy.decision\x0b",
        "policy.decision\x0c",
        "policy.decision\u00a0",
        "\u200bpolicy.decision",
        "policy.decision\u200b",
        "policy.decision\ufeff",
        "\u2003policy.decision\u2003",
        "policy.decision\u3000",
    ],
)
def test_a_padded_spelling_of_a_refused_type_reaches_the_reserved_name_rule(
    worker_conn: psycopg.Connection, leased_step: LeasedStep, variant: str
) -> None:
    """Padding of the forgiven kinds trims away, and the name is then refused.

    **This table is examples, not the guarantee, and its old name claimed
    otherwise.** It used to be called
    `test_no_spelling_of_a_refused_type_reaches_the_log` — a claim universally
    quantified over spellings, evidenced by an enumeration of characters that
    happened to be in the trim class. It was green in round 5 against U+00AD,
    U+180E, U+2800 and a Cyrillic homoglyph, because a table of inputs cannot
    establish a statement about all inputs. The guarantee now lives in two
    checks that do exist —
    `tests/schema/test_migration_applies.py::test_the_type_shape_is_one_rule_in_the_column_and_in_the_append_function`,
    which pins the shipped rule, and
    `test_the_shape_constraint_refuses_a_direct_insert_by_the_schema_owner`
    below, which drives it against the strongest caller. These cases only pin
    that the *trimming* still behaves.

    Every variant here refuses as a privilege failure, because trimming leaves
    a string equal to a reserved name. Spellings that do **not** trim away are
    a different refusal with a different type — see
    `test_a_type_outside_the_canonical_shape_is_refused`.
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


@pytest.mark.parametrize(
    "variant",
    [
        # Round 5 reproduced every one of these straight through round 4's
        # denylist, as `app_worker` on a live lease it owned. They are here as
        # regression examples; the closure is the shape rule, not this list.
        "policy.decision\xad",  # U+00AD SOFT HYPHEN
        "policy.decision\u180e",  # U+180E MONGOLIAN VOWEL SEPARATOR
        "policy.decision\u2800",  # U+2800 BRAILLE PATTERN BLANK
        "policy.decision\u2066",  # U+2066 LEFT-TO-RIGHT ISOLATE
        "policy.decision\ufe0f",  # U+FE0F VARIATION SELECTOR-16
        "policy.decision\u034f",  # U+034F COMBINING GRAPHEME JOINER
        "\u202epolicy.decision",  # U+202E RLO — reverses rendering
        "\u061cpolicy.decision",  # U+061C ARABIC LETTER MARK
        "run.completed\u2800",
        # Not whitespace at all, and the reason a denylist was the wrong shape:
        # Cyrillic es and o, rendering identically to the reserved name.
        "poli\u0441y.decision",
        "p\u043elicy.decision",
        # Interior padding, refused rather than collapsed.
        "tool. invoked",
        "step.\tstarted",
        # A pure-padding argument trims to the empty string, which used to be
        # stored as an untyped event.
        "   ",
        "",
        # Shapes the grammar refuses on structure rather than on characters.
        ".policy.decision",
        "policy.decision.",
        "policy..decision",
        "Policy.Decision\xad",
        # The separator set, pinned in the refusing direction. Round 5 shipped
        # `[._-]`, which admitted these while seven records described the rule
        # as dotted; round 6 narrowed the rule, and these cases are what stop
        # the separators being quietly re-admitted. A dotless single word is
        # refused too, which is the stated cost of requiring the dot.
        "policy_decision",
        "policy-decision",
        "tool_invoked",
        "tool-invoked",
        "policydecision",
    ],
)
def test_a_type_outside_the_canonical_shape_is_refused(
    worker_conn: psycopg.Connection, leased_step: LeasedStep, variant: str
) -> None:
    """The closure, by examples: anything not plain dotted lowercase ASCII.

    Two rounds tried to close this by enumerating invisible characters and both
    were walked through. The rule is now positive — a canonical form must be a
    dotted run of lowercase ASCII alphanumerics — so a character nobody
    enumerated is refused by default. The homoglyph cases are the ones that
    show why: they are not whitespace, so no denylist of spaces could have
    reached them.

    The refusal carries `MalformedEventType`, distinct from the privilege
    failure a reserved *name* raises, so the log distinguishes "you may not
    write that type" from "that is not a type".
    """
    with pytest.raises(event_log.MalformedEventType):
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=variant,
            principal="worker-1",
        )


def test_the_shape_constraint_refuses_a_direct_insert_by_the_schema_owner(
    owner_conn: psycopg.Connection,
) -> None:
    """The CHECK holds on paths that bypass the append functions entirely.

    **Named for what it evaluates.** It was
    `test_every_stored_type_matches_the_canonical_shape`, which quantified over
    stored types while reading none — the same over-claiming name round 5 had
    just renamed on its neighbour, reintroduced in the replacement. What this
    establishes is narrower and still worth having: the constraint refuses the
    strongest caller in the system, so no function-level rule has to be
    trusted for the guarantee to hold.

    The structural half — that the constraint is on `events.type`, covers only
    that column, carries exactly one pattern operand equal to the shipped
    shape, and carries no further accepting term — is
    `tests/schema/test_migration_applies.py`'s
    `test_the_type_shape_is_one_rule_in_the_column_and_in_the_append_function`,
    which is also what joins this rule to the copy inside the append function.
    """
    run_id = uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
    try:
        # As `ced_owner`, the strongest caller in the system, straight at the
        # table. If this is admitted, no function-level rule can close it.
        for forged in ("policy.decision\xad", "p\u043elicy.decision", ""):
            with pytest.raises(psycopg.errors.CheckViolation):
                with owner_conn.transaction():
                    owner_conn.execute(
                        "INSERT INTO events (run_id, seq, type, principal) "
                        "VALUES (%s, 1, %s, 'owner')",
                        (run_id, forged),
                    )
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


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
