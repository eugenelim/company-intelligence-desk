"""The base schema: runs, steps, events, and the three tables a sibling fills.

Revision ID: 0001
Revises: None
Created: 2026-09-18

Table shapes come from `runtime-architecture.md` r7 § Event log and stream
mechanism (the event envelope), § Step execution (the lease columns) and
§ Run state machine (the state vocabulary).

`agent_role`, `integration_registry` and `entitlements` are created here and
populated by `walking-skeleton-agent-runtime`. An empty table that waits is
better than a schema split across two specs: a schema change discovered while
building the agent runtime would be an amendment to a shipped spec.

Grants here are read-only plus the table writes r7's Layer-1 identity table
allows. Nothing here can insert into `events` — direct DML on that table is
revoked in revision 0002, which is also where the two append functions and
their disjoint EXECUTE grants land.
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE runs (
            run_id      uuid PRIMARY KEY,
            -- r7 § Run state machine. `expired` is non-terminal and has real
            -- exits; the terminal set is completed, failed, cancelled. The
            -- *transitions* belong to walking-skeleton-evidence; this column
            -- is the value the heartbeat already reads.
            state       text NOT NULL DEFAULT 'requested'
                        CHECK (state IN ('requested', 'claimed', 'running',
                                         'awaiting_approval', 'expired',
                                         'completed', 'failed', 'cancelled')),
            -- The per-run event counter. A row UPDATE inside the append
            -- transaction, never a bigserial: a rolled-back bigserial
            -- allocation survives and leaves a hole a reader skips forever.
            next_seq    bigint NOT NULL DEFAULT 0,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE steps (
            step_id           uuid PRIMARY KEY,
            run_id            uuid NOT NULL REFERENCES runs(run_id),
            state             text NOT NULL DEFAULT 'runnable'
                              CHECK (state IN ('runnable', 'leased', 'suspended',
                                               'completed', 'failed')),
            agent_role        text,
            -- The lease. Row locking and lease expiry are different
            -- mechanisms: the claim commits immediately and the step executes
            -- outside any transaction, so a multi-minute step never pins an
            -- idle-in-transaction connection or holds xmin back.
            owner             text,
            lease_epoch       bigint NOT NULL DEFAULT 0,
            lease_expires_at  timestamptz,
            created_at        timestamptz NOT NULL DEFAULT now()
        )
    """)
    # The claim query's predicate, so `FOR UPDATE SKIP LOCKED` over runnable
    # steps does not degrade to a sequential scan as the log grows.
    op.execute("""
        CREATE INDEX steps_runnable_idx ON steps (state, lease_expires_at)
         WHERE state IN ('runnable', 'leased')
    """)
    op.execute("CREATE INDEX steps_run_id_idx ON steps (run_id)")

    op.execute("""
        CREATE TABLE events (
            run_id       uuid NOT NULL REFERENCES runs(run_id),
            -- Dense from 1 per run, allocated inside the append transaction.
            seq          bigint NOT NULL,
            occurred_at  timestamptz NOT NULL DEFAULT now(),
            type         text NOT NULL,
            -- Null for run-lifecycle events, which are appended by `api`
            -- before any step exists. r7 § Event log: the envelope's step_id
            -- and agent_role are null on that path.
            step_id      uuid REFERENCES steps(step_id),
            agent_role   text,
            principal    text NOT NULL,
            payload_ref  text,
            -- The derived key hash(run_id, step_id, tool_call_id), never
            -- minted per attempt. Null on every event type but tool.invoked;
            -- revision 0002 adds the partial unique index over it.
            idempotency_key  text,
            schema_version   integer NOT NULL DEFAULT 1,
            PRIMARY KEY (run_id, seq)
        )
    """)
    # The stream's cursor projection reads (run_id, seq) in order, which the
    # primary key already serves. This index serves the snapshot's terminal
    # check without scanning a run's whole history.
    op.execute("""
        CREATE INDEX events_terminal_idx ON events (run_id, seq)
         WHERE type IN ('run.completed', 'run.failed', 'run.cancelled')
    """)

    # ── The three tables a sibling spec fills ────────────────────────────────
    # An agent role is a first-class security object: named, versioned, stored
    # outside any model's context and assigned by the orchestrator, never by a
    # model. r7 § Identity — layer 2.
    op.execute("""
        CREATE TABLE agent_role (
            role_name    text NOT NULL,
            version      integer NOT NULL,
            -- The decidable fragment: closed enumerations, string prefixes,
            -- numeric ranges, set membership, as a conjunction of independent
            -- per-argument predicates. The compiler owns its shape;
            -- walking-skeleton-agent-runtime owns the compiler.
            ceiling      jsonb NOT NULL,
            pool_class   text,
            instructions text NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            -- A version in use by an in-flight run is immutable: writes
            -- create new versions that bind at the next spawn, so a recorded
            -- containment proof cannot go stale mid-run.
            PRIMARY KEY (role_name, version)
        )
    """)
    op.execute("""
        CREATE TABLE integration_registry (
            integration_name text PRIMARY KEY,
            -- Whether the integration's output is admitted directly or must
            -- cross the quarantine boundary. Settled as a construction, not a
            -- label: walking-skeleton-agent-runtime owns the parser.
            trust_class      text NOT NULL,
            config           jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at       timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE entitlements (
            principal   text NOT NULL,
            -- Expressed in the same decidable fragment as agent_role.ceiling,
            -- which the containment base case requires: it is itself a ⊆ check.
            ceiling     jsonb NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (principal)
        )
    """)

    # ── Grants: r7 § Identity — two layers, Postgres column ─────────────────
    # `api`: read all; write runs (including next_seq) and enqueue steps.
    #        Holds no model authority and no unqualified events insert.
    # `worker`: read/write runs and steps.
    # `policy`: read only. Its single write is the policy.decision append,
    #        which arrives in revision 0002 as a function call and gives it no
    #        table access at all.
    #
    # `UPDATE ON runs` is table-level for both `api` and `worker` because that
    # is exactly what r7's identity table grants — "write `runs` (incl.
    # `next_seq`)". It is wider than the append paths need: r7 also states that
    # `next_seq` is never bumped outside those two paths, and that rule is
    # enforced by convention above this grant rather than by the grant. What
    # AC-0003 and AC-0004 establish is therefore density under concurrent
    # *appends*, not that the column cannot be moved by a direct statement.
    # Recorded here and in the verification ledger rather than narrowed, because
    # narrowing it unilaterally would deviate from ratified authority.
    op.execute("GRANT SELECT ON runs, steps, events TO app_api, app_worker, app_policy")
    op.execute(
        "GRANT SELECT ON agent_role, integration_registry, entitlements "
        "TO app_api, app_worker, app_policy"
    )
    op.execute("GRANT INSERT, UPDATE ON runs  TO app_api")
    op.execute("GRANT UPDATE         ON runs  TO app_worker")
    # `api` gets INSERT only. r7's identity table grants it "`steps` enqueue",
    # and table-level UPDATE would additionally reach `lease_epoch` and `owner`
    # — the fence function's own inputs — from the internet-facing role, which
    # r7 does not grant and no code path needs.
    op.execute("GRANT INSERT         ON steps TO app_api")
    op.execute("GRANT INSERT, UPDATE ON steps TO app_worker")


def downgrade() -> None:
    raise NotImplementedError("migrations are expand-only; there is no downgrade path")
