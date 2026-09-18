"""The two append paths, the privilege split, and the r7 schema additions.

Revision ID: 0002
Revises: 0001
Created: 2026-09-18

Postgres has no row-value-level grant, so the invariant r7 § Identity commits
to — *the database role that writes a `policy.decision` event is not the role
that performs the worker's general writes, and no runtime identity holds both* —
is built from revoked table privileges plus `SECURITY DEFINER` functions with
**disjoint** `EXECUTE` grants. Nothing holds an unqualified `events` insert,
`api` included: an internet-facing component able to write a policy decision
would defeat the split entirely, so it is constrained by the same mechanism
rather than trusted.

Four functions, and each one's owner is load-bearing:

  append_step_event       ced_owner   fenced; refuses the reserved type
  append_run_event        ced_owner   unfenced; only the two r7 names
  append_policy_decision  ced_owner   fenced; the reserved type, and only it
  fence_step              ced_fence   the row lock, at its own privilege

**`fence_step` is owned by `ced_fence`, a `NOLOGIN` role granted to no
application identity.** `worker-runtime.md` § Changes this design asks of r7
item 1 offers two ways to fence the policy append and prefers the second, a
definer fence *owned by `worker`*. Review round 1 established that option is
unsafe: a function's owner can always `DROP` or `ALTER` it regardless of schema
`CREATE` privilege, so owning the fence would let the role the split distrusts
disable the authorization-audit write path. ADR-0004 records the third owner as
an owner-approved narrowing of r4 item 1. `ced_fence` still holds only `SELECT`
and `UPDATE` on `steps`, so the privilege narrowing r4 wanted is preserved and
the DDL authority is not conferred.

**Every relation reference is schema-qualified and `search_path` is
`pg_catalog, pg_temp`.** Postgres resolves an unqualified relation name against
the session's *temporary* schema first whenever `pg_temp` is not listed
explicitly. Before this was fixed, a caller running `CREATE TEMP TABLE events`
had its append written into its own schema while `public.runs.next_seq` still
advanced — a suppressed audit record plus exactly the permanent sequence hole
the row-update counter exists to prevent — and a temp `runs` let the caller
choose its own `seq` in the real table. Observed, not theorised. Qualification
is the fix; naming `pg_temp` last is the belt to its braces.

`session_user`, never `current_user`. Inside a `SECURITY DEFINER` function
`current_user` is the *definer*, so an audit trail built on it names the wrong
principal every time. Phase 0 spike P1 found this.

Lock order is `steps` before `runs` on every path, the fence included. Both
that and fence-before-allocate follow from one property: the `runs` row lock
serialises appends per run, so it must be taken last and held briefly.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

#: r7 § Identity. The one event type the worker's general write path refuses.
RESERVED_EVENT_TYPE = "policy.decision"

#: r7 § Event log — the run-lifecycle path is "used by `api` for run.requested
#: and run.cancelled, which are appended before any step exists". Exactly two.
RUN_LIFECYCLE_TYPES = ("run.requested", "run.cancelled")

#: r7 § Event log — liveness and termination. Named here because the step path
#: must refuse them: they close the stream, and a worker writing one would end
#: a run's stream from a path that carries no terminal-state guard.
TERMINAL_EVENT_TYPES = ("run.completed", "run.failed", "run.cancelled")

#: What `append_step_event` refuses. r7 § Identity's symmetry clause restricts
#: `worker` "to its step-scoped types", and the run-lifecycle and terminal
#: vocabulary is by construction not step-scoped. This is a *negative* rule, so
#: it does not conflict with the recorded decision not to enumerate the
#: step-scoped vocabulary — the database still enforces only what may not be
#: written, never a frozen list of what may.
NON_STEP_EVENT_TYPES = tuple(
    dict.fromkeys((RESERVED_EVENT_TYPE, *RUN_LIFECYCLE_TYPES, *TERMINAL_EVENT_TYPES))
)


#: Rendered explicitly rather than by `repr` of the tuple. A tuple's repr is
#: valid SQL only by coincidence of arity — a one-element tuple renders a
#: trailing comma and fails to parse — and it escapes nothing.
def _sql_list(values: tuple[str, ...]) -> str:
    """Render a tuple as a SQL `IN` list, quoting each value.

    A tuple's `repr` is valid SQL only by coincidence of arity — a one-element
    tuple renders a trailing comma and fails to parse — and it escapes nothing.
    """
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


_RUN_LIFECYCLE_SQL_LIST = _sql_list(RUN_LIFECYCLE_TYPES)
_NON_STEP_SQL_LIST = _sql_list(NON_STEP_EVENT_TYPES)

#: The hardened definer preamble. `pg_catalog` is searched implicitly first in
#: any case; naming `pg_temp` explicitly and last is what stops the temporary
#: schema capturing an unqualified relation name.
_DEFINER_SEARCH_PATH = "SET search_path = pg_catalog, pg_temp"


def upgrade() -> None:
    # ── r7 changes 3 and 4: two nullable, additive columns ───────────────────
    # `pool_class` is read by T5's claim predicate; MVP has one class, so the
    # check is a no-op until the day it is not. What it buys is the ability to
    # run high-sensitivity integrations on a separate service with a different
    # task role, which is the only form of credential isolation that holds.
    op.execute("ALTER TABLE public.steps ADD COLUMN pool_class text NOT NULL DEFAULT 'default'")

    # `owner_scope` is read by nothing in this spec and taken now because
    # backfilling ownership onto executed runs is guesswork. This is the one
    # one-way door in the foundation spec.
    for table in ("runs", "steps", "agent_role", "integration_registry"):
        op.execute(
            f"ALTER TABLE public.{table} ADD COLUMN owner_scope text NOT NULL DEFAULT 'default'"
        )

    # ── r7 change 2: the partial unique index the derived key needs ──────────
    # Without it a derived idempotency key dedups nothing. Partial, because
    # every other event type leaves the column null and a null is not unique.
    op.execute("""
        CREATE UNIQUE INDEX events_tool_invoked_idempotency_idx
            ON public.events (run_id, idempotency_key)
         WHERE type = 'tool.invoked' AND idempotency_key IS NOT NULL
    """)

    # ── The fence, at its own privilege and under its own owner ─────────────
    op.execute(f"""
        CREATE FUNCTION public.fence_step(p_step_id uuid, p_lease_epoch bigint)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        {_DEFINER_SEARCH_PATH}
        AS $$
        BEGIN
            -- The steps row lock, taken before any runs lock on every path.
            PERFORM 1 FROM public.steps
             WHERE step_id = p_step_id AND lease_epoch = p_lease_epoch
               FOR UPDATE;
            RETURN FOUND;
        END $$
    """)
    # `ced_fence` needs exactly what the row lock needs and nothing else:
    # `SELECT ... FOR UPDATE` requires UPDATE privilege as well as SELECT.
    op.execute("GRANT SELECT, UPDATE ON public.steps TO ced_fence")
    # `ALTER FUNCTION ... OWNER TO` requires the incoming owner to hold CREATE
    # on the schema, so the grant is opened and closed around the one statement
    # and `ced_fence` holds no standing CREATE privilege afterwards. Unlike the
    # earlier `app_worker` version of this sequence, a transient grant to
    # `ced_fence` is unreachable in any case: it is NOLOGIN and granted to no
    # application role, so nothing can authenticate as it to use one.
    op.execute("GRANT CREATE ON SCHEMA public TO ced_fence")
    op.execute("ALTER FUNCTION public.fence_step(uuid, bigint) OWNER TO ced_fence")
    op.execute("REVOKE CREATE ON SCHEMA public FROM ced_fence")

    # ── The worker path: fenced, step-scoped, refuses the reserved type ─────
    op.execute(f"""
        CREATE FUNCTION public.append_step_event(
            p_run_id uuid, p_step_id uuid, p_lease_epoch bigint,
            p_type text, p_principal text,
            p_agent_role text DEFAULT NULL,
            p_payload_ref text DEFAULT NULL,
            p_idempotency_key text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        {_DEFINER_SEARCH_PATH}
        AS $$
        DECLARE v_seq bigint;
        BEGIN
            -- The reserved type and the whole run-lifecycle/terminal
            -- namespace. Refusing only `policy.decision` let the worker write
            -- `run.completed` and `run.cancelled` with a step_id attached —
            -- and `events_terminal_idx` indexes exactly those names, so the
            -- write closed the stream from a path with no terminal guard.
            IF p_type IN ({_NON_STEP_SQL_LIST}) THEN
                -- session_user, not current_user: inside a definer function
                -- current_user is ced_owner, which would name the wrong
                -- principal in every audit record. Found by spike P1.
                RAISE EXCEPTION
                    'append_step_event refuses % (caller %)',
                    p_type, session_user
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            IF p_step_id IS NULL THEN
                RAISE EXCEPTION
                    'append_step_event needs a step_id; run-lifecycle events '
                    'go through append_run_event (caller %)', session_user
                    USING ERRCODE = 'null_value_not_allowed';
            END IF;

            -- Fence first, then allocate. Zero rows means the lease moved on:
            -- roll back with no additional side effects.
            IF NOT public.fence_step(p_step_id, p_lease_epoch) THEN
                RAISE EXCEPTION 'fenced: step % epoch %', p_step_id, p_lease_epoch
                    USING ERRCODE = 'serialization_failure';
            END IF;

            -- The fence proves a lease on this *step*; it does not prove the
            -- step belongs to the run being written. Without this, one live
            -- lease authorized an append — with a caller-chosen `principal`
            -- and `agent_role` — into any run's log, on a wrong-argument bug
            -- as readily as on a malicious call. The `steps` row is already
            -- locked by the fence above, so this reads it without taking a
            -- new lock and without disturbing the steps-before-runs order.
            IF NOT EXISTS (
                SELECT 1 FROM public.steps
                 WHERE step_id = p_step_id AND run_id = p_run_id
            ) THEN
                RAISE EXCEPTION
                    'step % does not belong to run % (caller %)',
                    p_step_id, p_run_id, session_user
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            -- A row UPDATE, inside this transaction. This is what makes a
            -- rolled-back append leave no hole: rollback undoes the increment,
            -- where a bigserial allocation would survive it.
            UPDATE public.runs SET next_seq = next_seq + 1
             WHERE run_id = p_run_id RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'no such run %', p_run_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            INSERT INTO public.events (run_id, seq, type, step_id, agent_role,
                                       principal, payload_ref, idempotency_key)
            VALUES (p_run_id, v_seq, p_type, p_step_id, p_agent_role,
                    p_principal, p_payload_ref, p_idempotency_key);
            RETURN v_seq;
        END $$
    """)

    # ── The run-lifecycle path: unfenced, step_id null, two types ───────────
    op.execute(f"""
        CREATE FUNCTION public.append_run_event(
            p_run_id uuid, p_type text, p_principal text,
            p_payload_ref text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        {_DEFINER_SEARCH_PATH}
        AS $$
        DECLARE v_seq bigint;
        BEGIN
            IF p_type NOT IN ({_RUN_LIFECYCLE_SQL_LIST}) THEN
                RAISE EXCEPTION
                    'append_run_event refuses % (caller %)', p_type, session_user
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- The terminal-state guard, and it is not cosmetic. The stream
            -- closes on a terminal event, so a run.cancelled committing after
            -- run.completed would be invisible to every live client while
            -- present in the log — a reconstruction divergence.
            UPDATE public.runs SET next_seq = next_seq + 1
             WHERE run_id = p_run_id
               AND state NOT IN ('completed', 'failed', 'cancelled')
             RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'run % is absent or already terminal', p_run_id
                    USING ERRCODE = 'serialization_failure';
            END IF;

            INSERT INTO public.events (run_id, seq, type, step_id, principal,
                                       payload_ref)
            VALUES (p_run_id, v_seq, p_type, NULL, p_principal, p_payload_ref);
            RETURN v_seq;
        END $$
    """)

    # ── The policy path: the reserved type, and only it ─────────────────────
    op.execute(f"""
        CREATE FUNCTION public.append_policy_decision(
            p_run_id uuid, p_step_id uuid, p_lease_epoch bigint,
            p_principal text, p_agent_role text DEFAULT NULL,
            p_payload_ref text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        {_DEFINER_SEARCH_PATH}
        AS $$
        DECLARE v_seq bigint;
        BEGIN
            -- r7 change 1: this append is fenced too, through the same fence,
            -- in the same lock order. Spike P2 ran without a second locker on
            -- `steps`, so this ordering is argued from that result rather than
            -- demonstrated by it — which is why the suite also shows a mixed
            -- order deadlocking.
            IF NOT public.fence_step(p_step_id, p_lease_epoch) THEN
                RAISE EXCEPTION 'fenced: step % epoch %', p_step_id, p_lease_epoch
                    USING ERRCODE = 'serialization_failure';
            END IF;

            -- The fence proves a lease on this *step*; it does not prove the
            -- step belongs to the run being written. Without this, one live
            -- lease authorized an append — with a caller-chosen `principal`
            -- and `agent_role` — into any run's log, on a wrong-argument bug
            -- as readily as on a malicious call. The `steps` row is already
            -- locked by the fence above, so this reads it without taking a
            -- new lock and without disturbing the steps-before-runs order.
            IF NOT EXISTS (
                SELECT 1 FROM public.steps
                 WHERE step_id = p_step_id AND run_id = p_run_id
            ) THEN
                RAISE EXCEPTION
                    'step % does not belong to run % (caller %)',
                    p_step_id, p_run_id, session_user
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            UPDATE public.runs SET next_seq = next_seq + 1
             WHERE run_id = p_run_id RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'no such run %', p_run_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            INSERT INTO public.events (run_id, seq, type, step_id, agent_role,
                                       principal, payload_ref)
            VALUES (p_run_id, v_seq, '{RESERVED_EVENT_TYPE}', p_step_id,
                    p_agent_role, p_principal, p_payload_ref);
            RETURN v_seq;
        END $$
    """)

    # ── Disjoint EXECUTE grants are the whole control ──────────────────────
    # Direct DML on `events` goes first: with it in place the functions would
    # be a convention rather than a boundary.
    op.execute("REVOKE ALL ON public.events FROM PUBLIC")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.events "
        "FROM app_api, app_worker, app_policy"
    )

    for signature in (
        "public.fence_step(uuid, bigint)",
        "public.append_step_event(uuid, uuid, bigint, text, text, text, text, text)",
        "public.append_run_event(uuid, text, text, text)",
        "public.append_policy_decision(uuid, uuid, bigint, text, text, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")

    # `ced_owner` needs EXECUTE on the fence because the three owner-definer
    # append functions call it, and PUBLIC's grant has just been revoked.
    op.execute("GRANT EXECUTE ON FUNCTION public.fence_step(uuid, bigint) TO ced_owner")
    # **No direct grant to `app_worker`.** An earlier version granted it on the
    # stated ground that "the heartbeat renews on it", which is false: `renew`
    # issues a direct `UPDATE steps … FROM runs` and no code in `src/` calls
    # `fence_step` at all. The three append functions reach the fence at
    # `ced_owner`'s privilege through the grant above, so the worker's grant was
    # unused and let the role take `FOR UPDATE` row locks on arbitrary `steps`
    # rows. Removed under `AGENTS.md` § Cut before adding rung 1.

    op.execute(
        "GRANT EXECUTE ON FUNCTION public.append_step_event"
        "(uuid, uuid, bigint, text, text, text, text, text) TO app_worker"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.append_run_event(uuid, text, text, text) TO app_api"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.append_policy_decision"
        "(uuid, uuid, bigint, text, text, text) TO app_policy"
    )


def downgrade() -> None:
    raise NotImplementedError("migrations are expand-only; there is no downgrade path")
