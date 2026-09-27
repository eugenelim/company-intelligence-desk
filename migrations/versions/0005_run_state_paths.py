"""The two new append paths, two new columns, the decision index, and the narrowing.

Revision ID: 0005
Revises: 0004
Created: 2026-09-27

This revision builds the schema half of the run state machine. Revision 0002
shipped the event log with no path that can close a run or record an approval
decision; this one adds both. Nothing in the tree could write `run.completed`,
`run.failed`, `approval.granted` or `approval.rejected` before this revision
applies, and after it only the identities ADR-0009 records may do so.

Seven parts, enumerated here rather than scattered because `plan.md` § Constraints
declares this the canonical list and warns against restatement:

  1. append_run_terminal     ced_owner   fenced; run.completed and run.failed only;
                                         writes step_id null; updates runs.state
  2. append_approval_decision ced_owner  unfenced; approval.granted and
                                         approval.rejected only; keyed on
                                         <suspension_seq>:<call_id>
  3. steps.approval_cycles   integer NOT NULL DEFAULT 0
  4. steps.awaiting_decision boolean NOT NULL DEFAULT false
  5. events_decision_idempotency_idx  partial unique on (run_id, idempotency_key)
                                       for the two decision types
  6. EXECUTE grants: append_run_terminal → app_worker;
                     append_approval_decision → app_api
  7. CREATE OR REPLACE FUNCTION public.append_step_event carrying the two
     decision types in its refusal list — ADR-0009 D3

**Parts 3 and 4 are not expand-only.** Both columns are `NOT NULL` with
defaults. A nullable `awaiting_decision` makes `claim_one`'s `AND NOT
awaiting_decision` predicate three-valued — evaluating to `NULL` for every row
that predates this revision — silently excluding all pre-existing steps from
every claim and stalling the pool with no error. The defaults are load-bearing
rather than tidy.

**Part 7 narrows a foundation-owned function.** `CREATE OR REPLACE` re-issues
the whole definition, so a drift in the eight-argument signature creates a second
overload rather than replacing — a newly created function carrying the default
`EXECUTE TO PUBLIC` that revision 0002 had to revoke explicitly. The signature,
the `SECURITY DEFINER` attribute, the pinned `search_path`, and the owner are
all preserved. The change to the function's observable behaviour is the addition
of `approval.granted` and `approval.rejected` to its refusal list: after this
revision, `app_worker` can no longer append decision events through the step
path, and `append_approval_decision` is the only route. AC-0332 guards what the
replacement preserves.

**The `CREATE OR REPLACE` approach, not an edit to revision 0002.** The
`NON_STEP_EVENT_TYPES` constant in 0002 is rendered into `append_step_event`'s
body at `CREATE FUNCTION` time. Editing 0002 changes only what a fresh-volume
build creates: every database already at revision 0002 or later keeps the old
body, and `app_worker` keeps the admitted decision types. The `substrate` gate
rebuilds from a clean volume, so an edit to 0002 would go green precisely where
the control exists and red only where it does not. This revision cannot share
that defect — it issues `CREATE OR REPLACE`, which reaches the running database.

**Lock order: steps before runs on every new path**, matching every shipped
append function. The deadlock suite exists to catch a third order; do not add
one.

**`session_user`, never `current_user`.** Inside a `SECURITY DEFINER` function
`current_user` is the definer (`ced_owner`), naming the wrong principal in
every audit trail. Spike P1 found this; the shipped functions all use
`session_user` and so do these.

**Updating the `idempotency_key` column comment.** `0001_base_schema.py`
documents `events.idempotency_key` as "Null on every event type but
`tool.invoked`". This revision falsifies that: `approval.granted` and
`approval.rejected` also carry a key (`<suspension_seq>:<call_id>`). That file's
executable text is unchanged; the falsified claim is recorded here because this
is the revision that widens the set.
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# ── Constants re-declared for self-containment ─────────────────────────────
# Each migration must be self-contained: a revision applied in isolation must
# produce the same result as one applied in sequence, so it cannot import from
# a previous revision's module (whose constants are rendered into SQL at
# creation time and do not survive as importable objects after deployment).

#: Definer preamble — schema-qualifies every relation and pins pg_temp last.
_DEFINER_SEARCH_PATH = "SET search_path = pg_catalog, pg_temp"

#: The forgiven padding characters, trimmed from p_type before comparison.
_TYPE_SPACE_CLASS = (
    r"\s"
    r"  "
    r" -‏"
    r"    ⁠"
    r"　﻿"
)

#: The canonical shape: a dotted run of lowercase ASCII alphanumerics.
_TYPE_SHAPE = r"^[a-z0-9]+(\.[a-z0-9]+)+$"

#: The two types the run-terminal path admits. Named as an allowlist rather
#: than adding them to the step path's denylist, because the terminal path
#: carries its own predicate set and should refuse everything else.
TERMINAL_APPEND_TYPES = ("run.completed", "run.failed")

#: The two types the approval-decision path admits.
DECISION_TYPES = ("approval.granted", "approval.rejected")

#: The widened step-path denylist. Mirrors 0002's `NON_STEP_EVENT_TYPES` with
#: the two decision types appended. `dict.fromkeys` deduplicates while
#: preserving order; any type appearing in both TERMINAL_EVENT_TYPES (which
#: includes `run.cancelled`) and the lists below appears once.
_NON_STEP_EVENT_TYPES_V2 = tuple(
    dict.fromkeys(
        (
            "policy.decision",
            "run.requested",
            "run.cancelled",
            "run.completed",
            "run.failed",
            "approval.granted",
            "approval.rejected",
        )
    )
)


def _sql_list(values: tuple[str, ...]) -> str:
    """Render a tuple as a SQL `IN` list, quoting each value.

    A tuple's `repr` is valid SQL only by coincidence of arity — a one-element
    tuple renders a trailing comma and fails to parse — and it escapes nothing.
    Re-declared from 0002 for self-containment.
    """
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _canonical_type(arg: str) -> str:
    """The one normalised form: trim forgiven padding, fold to lowercase.

    Re-declared from 0002 for self-containment. The `CREATE OR REPLACE`
    body must match 0002's canonicaliser exactly, because the shape rule
    in the column CHECK and in the function body must remain identical.
    """
    return (
        f"lower(regexp_replace({arg}, "
        f"'^[{_TYPE_SPACE_CLASS}]+|[{_TYPE_SPACE_CLASS}]+$', '', 'g'))"
    )


_TERMINAL_APPEND_SQL_LIST = _sql_list(TERMINAL_APPEND_TYPES)
_DECISION_SQL_LIST = _sql_list(DECISION_TYPES)
_NON_STEP_SQL_LIST_V2 = _sql_list(_NON_STEP_EVENT_TYPES_V2)


def upgrade() -> None:
    # ── Parts 3 and 4: two new NOT NULL columns on steps ────────────────────
    # Both carry a finite, non-null default. A nullable `awaiting_decision`
    # makes the claim predicate's `AND NOT awaiting_decision` three-valued
    # for every row that predates this revision, silently excluding all
    # pre-existing steps from every claim. The defaults are load-bearing.
    op.execute("ALTER TABLE public.steps ADD COLUMN approval_cycles integer NOT NULL DEFAULT 0")
    op.execute(
        "ALTER TABLE public.steps ADD COLUMN awaiting_decision boolean NOT NULL DEFAULT false"
    )

    # ── Part 5: partial unique index for the decision idempotency key ────────
    # A replayed decision with the same (suspension_seq, call_id) pair must
    # be refused at the database level, not only by application code. The
    # idempotency_key for a decision event is `<suspension_seq>:<call_id>`.
    # Partial on the two decision types, mirroring `events_tool_invoked_idempotency_idx`
    # in 0002 — null is not unique, and every other event type leaves the
    # column null. The index is over (run_id, idempotency_key) rather than
    # step_id because a suspension seq is unique within the run by construction
    # (it is the seq of the step.suspended event, allocated by the run's own
    # next_seq counter), so a step component adds nothing.
    op.execute(f"""
        CREATE UNIQUE INDEX events_decision_idempotency_idx
            ON public.events (run_id, idempotency_key)
         WHERE type IN ({_DECISION_SQL_LIST}) AND idempotency_key IS NOT NULL
    """)

    # ── Part 1: the run-terminal path ───────────────────────────────────────
    # Fenced through the shipped fence_step (steps before runs lock order).
    # Writes step_id null in the event: terminal events are run-scoped.
    # Updates runs.state in the same statement as the seq advance, so the
    # state change and the event commit together or not at all. ADR-0009 D1.
    op.execute(f"""
        CREATE FUNCTION public.append_run_terminal(
            p_run_id uuid, p_step_id uuid, p_lease_epoch bigint,
            p_type text, p_principal text,
            p_agent_role text DEFAULT NULL,
            p_payload_ref text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        {_DEFINER_SEARCH_PATH}
        AS $$
        DECLARE v_seq bigint;
        BEGIN
            -- Null first: null canonicalises to null, so neither equality
            -- check below fires, and the INSERT would fail with an unmapped
            -- NOT NULL violation rather than the stated refusal.
            IF p_type IS NULL THEN
                RAISE EXCEPTION
                    'append_run_terminal refuses a null type (caller %)',
                    session_user
                    USING ERRCODE = 'CED01';
            END IF;

            -- Only the two terminal types. Any other value, including
            -- run-lifecycle, decision, or step-scoped types, is refused.
            IF lower(p_type) NOT IN ({_TERMINAL_APPEND_SQL_LIST}) THEN
                RAISE EXCEPTION
                    'append_run_terminal refuses % (caller %)',
                    p_type, session_user
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- Fence first: proves lease possession and takes the steps row
            -- lock (steps before runs on every path).
            IF NOT public.fence_step(p_step_id, p_lease_epoch) THEN
                RAISE EXCEPTION 'fenced: step % epoch %', p_step_id, p_lease_epoch
                    USING ERRCODE = 'serialization_failure';
            END IF;

            -- The fence proves a lease on this *step*; it does not prove the
            -- step belongs to the run being written. The steps row is already
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

            -- Source-state predicate and terminal guard in one statement.
            -- `state = ''running''` refuses both a run still at `requested`
            -- (which has not entered the committed transition set) and a run
            -- already terminal (which cannot re-enter it). The state change
            -- and the seq advance commit together: neither can land without
            -- the other. ADR-0009 D1: the null step_id in the event is what
            -- keeps §4''s disjointness intact while §3''s
            -- worker-appends-terminal reading is used.
            UPDATE public.runs
               SET state = CASE
                               WHEN lower(p_type) = 'run.completed'
                               THEN 'completed'::text
                               ELSE 'failed'::text
                           END,
                   next_seq = next_seq + 1
             WHERE run_id = p_run_id AND state = 'running'
             RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'run % is absent, already terminal, or not in running '
                    'state (caller %)',
                    p_run_id, session_user
                    USING ERRCODE = 'object_not_in_prerequisite_state';
            END IF;

            -- step_id written null: terminal events are run-scoped.
            INSERT INTO public.events (run_id, seq, type, step_id, agent_role,
                                       principal, payload_ref)
            VALUES (p_run_id, v_seq, lower(p_type), NULL,
                    p_agent_role, p_principal, p_payload_ref);
            RETURN v_seq;
        END $$
    """)

    # ── Part 2: the approval-decision path ──────────────────────────────────
    # Unfenced — the lease is released before the approver acts (r5 § 3).
    # Substitutes three structural predicates for the fence: a committed
    # step.suspended event (only the fenced step path can write one), a
    # step-run membership check, and the awaiting_decision hold. ADR-0009 D2.
    # Lock order: steps FOR UPDATE before runs UPDATE, matching every other path.
    op.execute(f"""
        CREATE FUNCTION public.append_approval_decision(
            p_run_id uuid, p_step_id uuid,
            p_type text, p_principal text,
            p_suspension_seq bigint, p_call_id text,
            p_agent_role text DEFAULT NULL,
            p_payload_ref text DEFAULT NULL)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        {_DEFINER_SEARCH_PATH}
        AS $$
        DECLARE
            v_seq bigint;
            v_step_run_id uuid;
            v_awaiting boolean;
            v_latest_susp_seq bigint;
        BEGIN
            -- Null check before the IN comparison (same discipline as
            -- append_step_event: null IN (...) evaluates to null, never true
            -- or false, so a null type escapes the refusal and reaches the
            -- NOT NULL constraint with an unmapped error shape).
            IF p_type IS NULL THEN
                RAISE EXCEPTION
                    'append_approval_decision refuses a null type (caller %)',
                    session_user
                    USING ERRCODE = 'CED01';
            END IF;

            IF lower(p_type) NOT IN ({_DECISION_SQL_LIST}) THEN
                RAISE EXCEPTION
                    'append_approval_decision refuses % (caller %)',
                    p_type, session_user
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- Lock the steps row first (steps before runs on every path).
            -- The FOR UPDATE serialises concurrent decisions on the same step:
            -- the second concurrent caller sees awaiting_decision = false
            -- after the first commits and is refused below, so exactly one
            -- decision per suspension commits. AC-0324.
            SELECT run_id, awaiting_decision
              INTO v_step_run_id, v_awaiting
              FROM public.steps
             WHERE step_id = p_step_id
               FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'step % does not exist (caller %)',
                    p_step_id, session_user
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            IF v_step_run_id <> p_run_id THEN
                RAISE EXCEPTION
                    'step % does not belong to run % (caller %)',
                    p_step_id, p_run_id, session_user
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;

            -- The step must carry a committed step.suspended event at the
            -- named seq. Only append_step_event (the fenced worker path) can
            -- write step.suspended, so this predicate substitutes for the
            -- fence that the approval path cannot hold. ADR-0009 D2.
            IF NOT EXISTS (
                SELECT 1 FROM public.events
                 WHERE step_id = p_step_id
                   AND type = 'step.suspended'
                   AND seq = p_suspension_seq
            ) THEN
                RAISE EXCEPTION
                    'step % has no step.suspended event at seq % (caller %)',
                    p_step_id, p_suspension_seq, session_user
                    USING ERRCODE = 'serialization_failure';
            END IF;

            -- The named seq must be the *latest* suspension for this step.
            -- A decision carried forward from an earlier cycle and submitted
            -- after the next suspension has opened is refused rather than
            -- stamped against the current cycle. Binding to the suspension
            -- seq (not the cycle counter) makes this refusal possible: a
            -- cycle counter read at commit time would be the post-advance
            -- value and would not identify which suspension was answered.
            SELECT max(seq) INTO v_latest_susp_seq
              FROM public.events
             WHERE step_id = p_step_id AND type = 'step.suspended';
            IF v_latest_susp_seq <> p_suspension_seq THEN
                RAISE EXCEPTION
                    'seq % is not the latest suspension for step % '
                    '(latest is %) (caller %)',
                    p_suspension_seq, p_step_id, v_latest_susp_seq,
                    session_user
                    USING ERRCODE = 'serialization_failure';
            END IF;

            -- The step must be awaiting a decision. The FOR UPDATE above
            -- makes this check and the clear below atomic: a concurrent
            -- second decision sees false after the first commits and is
            -- refused here rather than committing a duplicate. AC-0324.
            IF NOT v_awaiting THEN
                RAISE EXCEPTION
                    'step % is not awaiting a decision (caller %)',
                    p_step_id, session_user
                    USING ERRCODE = 'serialization_failure';
            END IF;

            -- Clear the hold and advance the cycle counter. Both are read by
            -- AC-0324''s and AC-0330''s predicates. The pre-advance value is
            -- what AC-0330''s resume matches on (the cycle that opened the
            -- suspension); stamping the post-advance value would make every
            -- resume refuse. The counter is advanced here rather than by the
            -- worker, so the resume reads a stable value even across a worker
            -- handoff. AC-0333.
            UPDATE public.steps
               SET awaiting_decision = false,
                   approval_cycles = approval_cycles + 1
             WHERE step_id = p_step_id;

            -- Advance the run''s sequence counter. Runs lock taken after
            -- steps lock, preserving the steps-before-runs order.
            UPDATE public.runs SET next_seq = next_seq + 1
             WHERE run_id = p_run_id RETURNING next_seq INTO v_seq;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'no such run %', p_run_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;

            -- idempotency_key = <suspension_seq>:<call_id>. The suspension
            -- seq is unique within the run by construction (it is the seq of
            -- the step.suspended event, allocated by the run''s own next_seq
            -- counter), so this key identifies exactly one pending call in one
            -- suspension occurrence. No step component is needed. AC-0334.
            INSERT INTO public.events (run_id, seq, type, step_id, agent_role,
                                       principal, payload_ref, idempotency_key)
            VALUES (p_run_id, v_seq, lower(p_type), p_step_id,
                    p_agent_role, p_principal, p_payload_ref,
                    p_suspension_seq::text || ':' || p_call_id);
            RETURN v_seq;
        END $$
    """)

    # ── Part 6: disjoint EXECUTE grants ─────────────────────────────────────
    # The grants are what make each path exclusive. PUBLIC is revoked from
    # both new functions before granting to the named roles, matching the
    # pattern revision 0002 established.
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.append_run_terminal(uuid, uuid, bigint, text, text, text, text) "
        "FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.append_approval_decision(uuid, uuid, text, text, bigint, text, text, text) "
        "FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "public.append_run_terminal(uuid, uuid, bigint, text, text, text, text) "
        "TO app_worker"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "public.append_approval_decision(uuid, uuid, text, text, bigint, text, text, text) "
        "TO app_api"
    )

    # ── Part 7: widen append_step_event's refusal list ──────────────────────
    # ADR-0009 D3. The two decision types are added to NON_STEP_EVENT_TYPES so
    # that the exclusivity is at the type level rather than only at the
    # function level (`app_worker` held EXECUTE on append_step_event, and
    # approval.granted was an admitted step-scoped type on that path).
    #
    # The signature must match 0002's exactly. An eight-argument overload that
    # differs in any parameter type or default creates a second pg_proc row
    # carrying the default EXECUTE TO PUBLIC that 0002 had to revoke; it does
    # not replace. AC-0332 guards what this replacement preserves.
    #
    # The body is replicated from 0002 with one change: _NON_STEP_SQL_LIST_V2
    # in place of _NON_STEP_SQL_LIST. All other text — SECURITY DEFINER,
    # search_path, DECLARE, variable names, error codes, comments stripped
    # from the SQL string below — is identical in structure and intent. The
    # comments in 0002 explain the why; this body carries only the executable.
    op.execute(f"""
        CREATE OR REPLACE FUNCTION public.append_step_event(
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
            IF p_type IS NULL THEN
                RAISE EXCEPTION
                    'append_step_event refuses a null type (caller %)',
                    session_user
                    USING ERRCODE = 'CED01';
            END IF;

            IF {_canonical_type("p_type")} IN ({_NON_STEP_SQL_LIST_V2}) THEN
                RAISE EXCEPTION
                    'append_step_event refuses % (caller %)',
                    p_type, session_user
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            IF {_canonical_type("p_type")} !~ '{_TYPE_SHAPE}' THEN
                RAISE EXCEPTION
                    'append_step_event refuses a type outside the canonical '
                    'shape: % (caller %)', p_type, session_user
                    USING ERRCODE = 'CED01';
            END IF;

            IF p_step_id IS NULL THEN
                RAISE EXCEPTION
                    'append_step_event needs a step_id; run-lifecycle events '
                    'go through append_run_event (caller %)', session_user
                    USING ERRCODE = 'null_value_not_allowed';
            END IF;

            IF NOT public.fence_step(p_step_id, p_lease_epoch) THEN
                RAISE EXCEPTION 'fenced: step % epoch %', p_step_id, p_lease_epoch
                    USING ERRCODE = 'serialization_failure';
            END IF;

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
                                       principal, payload_ref, idempotency_key)
            VALUES (p_run_id, v_seq, {_canonical_type("p_type")}, p_step_id,
                    p_agent_role, p_principal, p_payload_ref,
                    p_idempotency_key);
            RETURN v_seq;
        END $$
    """)


def downgrade() -> None:
    raise NotImplementedError("migrations are expand-only; there is no downgrade path")
