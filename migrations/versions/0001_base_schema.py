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

    # **Raw string, and that is load-bearing.** The shape CHECK below contains
    # `\.`, which is not a recognised Python escape: in a non-raw string it
    # emits `SyntaxWarning: invalid escape sequence` and is a future
    # `SyntaxError`. The backslash survived, so the shipped constraint was
    # correct — but the dangerous repair is a contributor silencing the warning
    # by deleting the backslash, which turns `\.` into `.` and matches any
    # character, reopening the admitted set rounds 3 through 5 closed. The
    # sibling copy in revision 0002 was already raw; this was the divergence.
    op.execute(r"""
        CREATE TABLE events (
            run_id       uuid NOT NULL REFERENCES runs(run_id),
            -- Dense from 1 per run, allocated inside the append transaction.
            seq          bigint NOT NULL,
            occurred_at  timestamptz NOT NULL DEFAULT now(),
            -- **A dotted run of lowercase ASCII alphanumerics, and nothing
            -- else.** This constrains the character *shape*, not the set of
            -- names: the step-scoped vocabulary is still unenumerated, so a
            -- sibling spec adds whatever `foo.bar` types it emits without a
            -- migration. See `src/ced/domain/events.py`.
            --
            -- **Dots only, and at least one.** Round 5 shipped
            -- `([._-][a-z0-9]+)*`, which admitted `tool_invoked` and
            -- `tool-invoked` while seven records described the rule as dotted
            -- — the code-versus-record defect this review keeps finding,
            -- introduced by the commit that fixed it. Round 6 narrowed the
            -- enforced set rather than restating the records, because every
            -- type in the system is `x.y`, nothing needs the other two
            -- separators, and a smaller admitted set is the safer default for
            -- a rule this load-bearing. The consequence to know about: a
            -- single dotless word is refused, so a sibling wanting one needs a
            -- migration. Adjudication refuted the framing of the separators as
            -- a dedup bypass — `tool-invoked` is a distinct type name, not a
            -- spelling of `tool.invoked` — so that is not the ground here.
            --
            -- Here rather than only in the append functions, because it is the
            -- structural closure. Two review rounds tried to close the
            -- reserved-type rule with a denylist of invisible characters
            -- inside revision 0002's functions, and each was walked through —
            -- U+00AD, U+180E, U+2800, U+2066, U+FE0F, U+034F, and finally a
            -- Cyrillic homoglyph no whitespace denylist could ever catch. A
            -- CHECK on the column holds on every path, including direct DML by
            -- the schema owner, which is the strongest caller there is. That
            -- is what makes revision 0002's negative reserved-name rule
            -- exhaustive by construction rather than by enumeration, and what
            -- keeps every admitted `tool.invoked` spelling inside
            -- `events_tool_invoked_idempotency_idx` — the dedup guarantee
            -- `worker-runtime.md` § The fence-detection window calls
            -- non-optional. It also refuses the empty string, which a
            -- pure-padding argument used to canonicalise down to and store.
            type         text NOT NULL
                         CONSTRAINT events_type_is_canonical
                         CHECK (type ~ '^[a-z0-9]+(\.[a-z0-9]+)+$'),
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
    # `policy`: **nothing**. No read, no write. Its single capability is the
    #        policy.decision append, which arrives in revision 0002 as an
    #        `EXECUTE` grant on one function and gives it no table access at
    #        all — which is exactly what r4 item 1 chose the definer fence for.
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
    # **`app_policy` gets no read at all.** r7's Layer-1 identity table grants
    # `policy-writer` "`runs.next_seq` bump + insert `policy.decision` events
    # **only**" — no read column — and r4 item 1 chose the definer-fence option
    # expressly "so `policy-writer` gains no table access at all". An earlier
    # version granted it `SELECT` on all six tables, which over-granted against
    # both documents and let it read the `lease_epoch` and `step_id` values the
    # fence compares. It needs none of them: its single write is a function
    # call, and the worker supplies the step and epoch at call time.
    op.execute("GRANT SELECT ON runs, steps, events TO app_api, app_worker")
    op.execute(
        "GRANT SELECT ON agent_role, integration_registry, entitlements TO app_api, app_worker"
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
