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

Three functions, and each one's owner is load-bearing:

  append_step_event       ced_owner   fenced; refuses the reserved type
  append_run_event        ced_owner   unfenced; only the two r7 names
  append_policy_decision  ced_owner   fenced; the reserved type, and only it
  fence_step              app_worker  the row lock, at worker's privilege

`fence_step` is owned by `app_worker`, not by `ced_owner`. This is
`worker-runtime.md` § Changes this design asks of r7 item 1, taken the second
way: `policy-writer` needs the fence but must gain no table access, and a
definer function owned by the *worker* runs with worker's privileges — `SELECT`
and `UPDATE` on `steps` — rather than with the schema owner's full authority.
Doing the fence inside the owner-definer function would satisfy the access
rule and lose that narrowing.

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


def upgrade() -> None:
    # ── r7 changes 3 and 4: two nullable, additive columns ───────────────────
    # `pool_class` is read by T5's claim predicate; MVP has one class, so the
    # check is a no-op until the day it is not. What it buys is the ability to
    # run high-sensitivity integrations on a separate service with a different
    # task role, which is the only form of credential isolation that holds.
    op.execute("ALTER TABLE steps ADD COLUMN pool_class text NOT NULL DEFAULT 'default'")

    # `owner_scope` is read by nothing in this spec and taken now because
    # backfilling ownership onto executed runs is guesswork. This is the one
    # one-way door in the foundation spec.
    for table in ("runs", "steps", "agent_role", "integration_registry"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN owner_scope text NOT NULL DEFAULT 'default'"
        )

    # ── r7 change 2: the partial unique index the derived key needs ──────────
    # Without it a derived idempotency key dedups nothing. Partial, because
    # every other event type leaves the column null and a null is not unique.
    op.execute("""
        CREATE UNIQUE INDEX events_tool_invoked_idempotency_idx
            ON events (run_id, idempotency_key)
         WHERE type = 'tool.invoked' AND idempotency_key IS NOT NULL
    """)

    # ── The fence, at worker's privilege ────────────────────────────────────
    op.execute("""
        CREATE FUNCTION fence_step(p_step_id uuid, p_lease_epoch bigint)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            -- The steps row lock, taken before any runs lock on every path.
            PERFORM 1 FROM steps
             WHERE step_id = p_step_id AND lease_epoch = p_lease_epoch
               FOR UPDATE;
            RETURN FOUND;
        END $$
    """)
    # `ALTER FUNCTION ... OWNER TO` needs the incoming owner to hold CREATE on
    # the schema, so the grant is opened and closed around the one statement.
    # app_worker holds no standing CREATE privilege afterwards.
    op.execute("GRANT CREATE ON SCHEMA public TO app_worker")
    op.execute("ALTER FUNCTION fence_step(uuid, bigint) OWNER TO app_worker")
    op.execute("REVOKE CREATE ON SCHEMA public FROM app_worker")

    # ── The worker path: fenced, step-scoped, refuses the reserved type ─────
    op.execute(f"""
        CREATE FUNCTION append_step_event(
            p_run_id uuid, p_step_id uuid, p_lease_epoch bigint,
            p_type text, p_principal text,
            p_agent_role text DEFAULT NULL,
            p_payload_ref text DEFAULT NULL,
            p_idempotency_key text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE v_seq bigint;
        BEGIN
            IF p_type = '{RESERVED_EVENT_TYPE}' THEN
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
            IF NOT fence_step(p_step_id, p_lease_epoch) THEN
                RAISE EXCEPTION 'fenced: step % epoch %', p_step_id, p_lease_epoch
                    USING ERRCODE = 'serialization_failure';
            END IF;

            -- A row UPDATE, inside this transaction. This is what makes a
            -- rolled-back append leave no hole: rollback undoes the increment,
            -- where a bigserial allocation would survive it.
            UPDATE runs SET next_seq = next_seq + 1
             WHERE run_id = p_run_id RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'no such run %', p_run_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            INSERT INTO events (run_id, seq, type, step_id, agent_role,
                                principal, payload_ref, idempotency_key)
            VALUES (p_run_id, v_seq, p_type, p_step_id, p_agent_role,
                    p_principal, p_payload_ref, p_idempotency_key);
            RETURN v_seq;
        END $$
    """)

    # ── The run-lifecycle path: unfenced, step_id null, two types ───────────
    op.execute(f"""
        CREATE FUNCTION append_run_event(
            p_run_id uuid, p_type text, p_principal text,
            p_payload_ref text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE v_seq bigint;
        BEGIN
            IF p_type NOT IN {RUN_LIFECYCLE_TYPES!r} THEN
                RAISE EXCEPTION
                    'append_run_event refuses % (caller %)', p_type, session_user
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- The terminal-state guard, and it is not cosmetic. The stream
            -- closes on a terminal event, so a run.cancelled committing after
            -- run.completed would be invisible to every live client while
            -- present in the log — a reconstruction divergence.
            UPDATE runs SET next_seq = next_seq + 1
             WHERE run_id = p_run_id
               AND state NOT IN ('completed', 'failed', 'cancelled')
             RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'run % is absent or already terminal', p_run_id
                    USING ERRCODE = 'serialization_failure';
            END IF;

            INSERT INTO events (run_id, seq, type, step_id, principal, payload_ref)
            VALUES (p_run_id, v_seq, p_type, NULL, p_principal, p_payload_ref);
            RETURN v_seq;
        END $$
    """)

    # ── The policy path: the reserved type, and only it ─────────────────────
    op.execute(f"""
        CREATE FUNCTION append_policy_decision(
            p_run_id uuid, p_step_id uuid, p_lease_epoch bigint,
            p_principal text, p_agent_role text DEFAULT NULL,
            p_payload_ref text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE v_seq bigint;
        BEGIN
            -- r7 change 1: this append is fenced too, through the same
            -- worker-owned fence, in the same lock order. Spike P2 ran without
            -- a second locker on `steps`, so this ordering is argued from that
            -- result rather than demonstrated by it — which is why the suite
            -- also shows a mixed order deadlocking.
            IF NOT fence_step(p_step_id, p_lease_epoch) THEN
                RAISE EXCEPTION 'fenced: step % epoch %', p_step_id, p_lease_epoch
                    USING ERRCODE = 'serialization_failure';
            END IF;

            UPDATE runs SET next_seq = next_seq + 1
             WHERE run_id = p_run_id RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'no such run %', p_run_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            INSERT INTO events (run_id, seq, type, step_id, agent_role,
                                principal, payload_ref)
            VALUES (p_run_id, v_seq, '{RESERVED_EVENT_TYPE}', p_step_id,
                    p_agent_role, p_principal, p_payload_ref);
            RETURN v_seq;
        END $$
    """)

    # ── Disjoint EXECUTE grants are the whole control ──────────────────────
    # Direct DML on `events` goes first: with it in place the functions would
    # be a convention rather than a boundary.
    op.execute("REVOKE ALL ON events FROM PUBLIC")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON events FROM app_api, app_worker, app_policy"
    )

    for signature in (
        "fence_step(uuid, bigint)",
        "append_step_event(uuid, uuid, bigint, text, text, text, text, text)",
        "append_run_event(uuid, text, text, text)",
        "append_policy_decision(uuid, uuid, bigint, text, text, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")

    # `ced_owner` needs EXECUTE on the fence because the two owner-definer
    # append functions call it, and PUBLIC's grant has just been revoked.
    op.execute("GRANT EXECUTE ON FUNCTION fence_step(uuid, bigint) TO ced_owner")
    # The worker holds the fence directly too: the heartbeat renews on it.
    op.execute("GRANT EXECUTE ON FUNCTION fence_step(uuid, bigint) TO app_worker")

    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "append_step_event(uuid, uuid, bigint, text, text, text, text, text) "
        "TO app_worker"
    )
    op.execute("GRANT EXECUTE ON FUNCTION append_run_event(uuid, text, text, text) TO app_api")
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "append_policy_decision(uuid, uuid, bigint, text, text, text) TO app_policy"
    )


def downgrade() -> None:
    raise NotImplementedError("migrations are expand-only; there is no downgrade path")
