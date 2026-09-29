"""AC-0302, AC-0330, and the prerelease check.

Mutation-proof discipline applied here:
- test_the_gated_tool_is_offered_only_when_a_check_failed covers the offered-list
  pure function. Mutating offered_approval_gated_tools to always return [] fails
  the non-empty assertion; mutating it to always return [...] fails the empty one.
- test_check_prerelease_returns_false_for_unflagged_role pins check_prerelease_failed
  at the function boundary the executor calls. A mutant that returns True for every
  role fails this case, catching the scenario where the gate becomes unconditional.
- test_check_prerelease_raises_on_malformed_model_settings pins the fail-closed
  direction for Entry 18 (adjudication): a non-mapping model_settings must raise,
  not silently disable the gate.

Entry 1 (adjudication): tests that drive through the executor body observe the
toolsets the executor actually passes to _run_compiled_agent, not just the output
of the pure offered-list function. Two mutations must each red a new assertion:
1. Replace offered_approval_gated_tools(prerelease_failed) with
   offered_approval_gated_tools(True) at executor.py:576.
2. Make check_prerelease_failed return True unconditionally.
Both mutations cause an unflagged role to receive a non-empty toolset list, which
the executor-level assertions detect.

Entry 5 (adjudication): AC-0330 mixed-outcome assertions. A suspension carrying
several pending calls with real committed approval.granted and approval.rejected
events; the rejected call's body must not execute.
"""

from __future__ import annotations

import functools
import json
import subprocess
import sys
import textwrap
import threading
import unittest.mock as mock
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import (
    append_approval_decision,
    read_events,
    start_run,
)
from ced.agents.tools.approval import request_approval as _real_request_approval
from ced.domain.events import APPROVAL_GRANTED, APPROVAL_REJECTED
from ced.worker.executor import _StepBodyFailed, make_step_body
from ced.worker.persistence import (
    approval_results_for_cycle,
    load_suspension_payload,
    resume_step,
)
from ced.worker.pool import Lease, PoolConfig, Worker, claim_one

# ── pure offered-list function (AC-0302) ─────────────────────────────────────


# AC-0302 — pure offered-list function
def test_the_gated_tool_is_offered_only_when_a_check_failed() -> None:
    """Exclusion paired with its positive case, so returning [] cannot pass."""
    from ced.worker.executor import offered_approval_gated_tools

    assert offered_approval_gated_tools(prerelease_failed=False) == []
    assert offered_approval_gated_tools(prerelease_failed=True) != []


# AC-0302 — executor-level gate (mutation-proof for check_prerelease_failed)
def test_check_prerelease_returns_false_for_unflagged_role() -> None:
    """A role without needs_approval does not trigger the gate.

    This pins check_prerelease_failed — the function the executor calls before
    offered_approval_gated_tools. A mutant that returns True for every role
    fails here, closing the gap where the gate becomes unconditional.
    """
    from ced.worker.prerelease import check_prerelease_failed

    assert check_prerelease_failed({}) is False
    assert check_prerelease_failed({"model_settings": None}) is False
    assert check_prerelease_failed({"model_settings": {"needs_approval": False}}) is False


def test_check_prerelease_returns_true_for_flagged_role() -> None:
    """A role with needs_approval=True triggers the gate."""
    from ced.worker.prerelease import check_prerelease_failed

    assert check_prerelease_failed({"model_settings": {"needs_approval": True}}) is True


def test_check_prerelease_raises_on_malformed_model_settings() -> None:
    """A non-mapping model_settings is refused, not silently treated as absent (Entry 18)."""
    from ced.worker.prerelease import check_prerelease_failed

    with pytest.raises(ValueError, match="not a mapping"):
        check_prerelease_failed({"model_settings": "string-not-a-mapping"})


def test_check_prerelease_raises_on_non_bool_needs_approval() -> None:
    """A non-boolean needs_approval is refused (Entry 18 fail-closed)."""
    from ced.worker.prerelease import check_prerelease_failed

    with pytest.raises(ValueError, match="must be a boolean"):
        check_prerelease_failed({"model_settings": {"needs_approval": "yes"}})


# ── executor-body level (AC-0302, Entry 1 adjudication) ──────────────────────

_GATE_POOL_CLASS = "t2-gate-executor"
_GATE_PRINCIPAL = "t2-gate-test"
_GATE_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}


def _insert_role_and_step(
    needs_approval: bool | None,
    role_name: str,
    pool_class: str,
    config: PoolConfig,
) -> tuple[uuid.UUID, uuid.UUID, Lease]:
    """Insert a role+run+step and claim the step. Returns (run_id, step_id, lease)."""
    model_settings: dict[str, Any] = {"model_id": "stub:counting", "settings": {}, "limits": {}}
    if needs_approval is not None:
        model_settings["needs_approval"] = needs_approval

    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            """
            INSERT INTO agent_role
                (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
            VALUES (%s, 1, '[]'::jsonb, '', %s::jsonb, 'reference-selection')
            ON CONFLICT (role_name, version) DO UPDATE
                SET model_settings = EXCLUDED.model_settings
            """,
            (role_name, json.dumps(model_settings)),
        )
        conn.commit()

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_GATE_PRINCIPAL,
            agent_role=role_name,
        )

    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = %s,
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + interval '300 seconds',
                   pool_class = %s
             WHERE step_id = %s
             RETURNING lease_epoch
            """,
            (config.worker_id, pool_class, step_id),
        ).fetchone()
        conn.commit()

    assert row is not None
    lease = Lease(step_id=step_id, run_id=run_id, epoch=int(row[0]), agent_role=role_name)
    return run_id, step_id, lease


def _cleanup_run(run_id: uuid.UUID) -> None:
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
        conn.commit()


@pytest.mark.substrate
def test_executor_passes_empty_toolsets_to_unflagged_role(require_substrate: None) -> None:
    """AC-0302 executor body: an unflagged role gets no approval toolsets (Entry 1).

    The executor calls offered_approval_gated_tools(prerelease_failed) and
    passes the result to _run_compiled_agent. Patching _run_compiled_agent to
    capture the toolsets argument asserts the executor's actual pass-through.

    Mutation that must red: replace offered_approval_gated_tools(prerelease_failed)
    with offered_approval_gated_tools(True) at executor.py — the unflagged role
    would receive a non-empty list, failing the 'toolsets == []' assertion below.
    Also red if check_prerelease_failed returns True unconditionally (same effect).
    """
    from pydantic_ai.models.test import TestModel

    role_name = "t2-gate-unflagged"
    config = PoolConfig(
        worker_id="t2-gate-unflagged-worker",
        default_limits=_GATE_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(),
        pool_class=_GATE_POOL_CLASS,
    )

    run_id, step_id, lease = _insert_role_and_step(
        needs_approval=False, role_name=role_name, pool_class=_GATE_POOL_CLASS, config=config
    )
    captured: list[list[Any]] = []

    sentinel = Exception("toolsets captured — stopping body")

    def capture_toolsets(
        compiled: Any, toolsets: list[Any], cancellation_token: Any = None
    ) -> Any:
        captured.append(list(toolsets))
        raise sentinel

    try:
        with mock.patch(
            "ced.worker.executor._run_compiled_agent", side_effect=capture_toolsets
        ):
            body = make_step_body(config)
            try:
                body(lease, threading.Event())
            except _StepBodyFailed:
                pass  # expected: executor catches sentinel → appends step.failed → raises
    finally:
        _cleanup_run(run_id)

    assert len(captured) == 1, f"_run_compiled_agent not called — captured: {captured!r}"
    assert captured[0] == [], (
        f"unflagged role must receive empty toolsets, got {captured[0]!r}; "
        "mutation: offered_approval_gated_tools(True) would give a non-empty list"
    )


@pytest.mark.substrate
def test_executor_passes_nonempty_toolsets_to_flagged_role(require_substrate: None) -> None:
    """AC-0302 executor body: a flagged role gets the approval toolset (Entry 1).

    Paired with the unflagged case: returning [] unconditionally would fail here.
    """
    from pydantic_ai.models.test import TestModel

    role_name = "t2-gate-flagged-executor"
    config = PoolConfig(
        worker_id="t2-gate-flagged-worker",
        default_limits=_GATE_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(),
        pool_class=_GATE_POOL_CLASS,
    )

    run_id, step_id, lease = _insert_role_and_step(
        needs_approval=True, role_name=role_name, pool_class=_GATE_POOL_CLASS, config=config
    )
    captured: list[list[Any]] = []
    sentinel = Exception("toolsets captured — stopping body")

    def capture_toolsets(
        compiled: Any, toolsets: list[Any], cancellation_token: Any = None
    ) -> Any:
        captured.append(list(toolsets))
        raise sentinel

    try:
        with mock.patch(
            "ced.worker.executor._run_compiled_agent", side_effect=capture_toolsets
        ):
            body = make_step_body(config)
            try:
                body(lease, threading.Event())
            except _StepBodyFailed:
                pass
    finally:
        _cleanup_run(run_id)

    assert len(captured) == 1, f"_run_compiled_agent not called — captured: {captured!r}"
    assert captured[0] != [], (
        f"flagged role must receive non-empty toolsets, got {captured[0]!r}; "
        "mutation: offered_approval_gated_tools([]) would give an empty list"
    )


# ── AC-0330: substrate refusal (no committed decision) ──────────────────────


@pytest.mark.substrate
# AC-0330
def test_a_resume_with_no_committed_decision_refuses_to_run(require_substrate: None) -> None:
    """Absent decision for this cycle is a refusal, not an approval."""
    with pytest.raises(LookupError):
        approval_results_for_cycle(
            step_id="11111111-2222-3333-4444-5555aaaabbbb", cycle=1, pending_call_ids=["c1"]
        )


def test_cycle_zero_is_refused_without_database() -> None:
    """cycle < 1 raises LookupError before any database call (AC-0330 guard).

    Differing outcome from the substrate case: cycle=0 is refused immediately
    with a message naming the cycle, not as 'no committed decision'.
    """
    with pytest.raises(LookupError, match="below 1"):
        approval_results_for_cycle(
            step_id="11111111-2222-3333-4444-5555aaaabbbb", cycle=0, pending_call_ids=["c1"]
        )


# ── AC-0330: mixed-outcome assertions (Entry 5) ─────────────────────────────


_MIXED_POOL_CLASS = "t2-mixed-outcomes"
_MIXED_PRINCIPAL = "t2-mixed-test"
_MIXED_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}


@pytest.fixture
def mixed_suspension(
    require_substrate: None,
) -> Iterator[tuple[uuid.UUID, uuid.UUID, int, str]]:
    """A run+step with a committed suspension carrying two pending call ids.

    Inserts run.requested and step.suspended under the migration role, sets
    awaiting_decision=true and approval_cycles=0. Yields
    (run_id, step_id, suspension_seq, pending_call_ids_json).

    Cleanup removes all rows for the run.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    pending = ["call-granted", "call-rejected"]

    with psycopg.connect(database_url("migration")) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'running', 0)",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO steps (step_id, run_id, state, awaiting_decision, pool_class)"
                " VALUES (%s, %s, 'runnable', true, %s)",
                (step_id, run_id, _MIXED_POOL_CLASS),
            )
            # seq 1: run.requested
            conn.execute("UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s", (run_id,))
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal)"
                " VALUES (%s, 1, 'run.requested', NULL, %s)",
                (run_id, _MIXED_PRINCIPAL),
            )
            # seq 2: step.suspended
            conn.execute("UPDATE runs SET next_seq = next_seq + 1 WHERE run_id = %s", (run_id,))
            conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal)"
                " VALUES (%s, 2, 'step.suspended', %s, %s)",
                (run_id, step_id, _MIXED_PRINCIPAL),
            )

    try:
        yield run_id, step_id, 2, pending
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()


@pytest.mark.substrate
def test_mixed_outcomes_per_call_for_one_cycle(
    mixed_suspension: tuple[uuid.UUID, uuid.UUID, int, list[str]],
) -> None:
    """AC-0330: per-call outcomes differ within one suspension (Entry 5).

    A grant for 'call-granted' and a rejection for 'call-rejected' are committed
    through append_approval_decision. approval_results_for_cycle must then return
    True for the granted call and False for the rejected one.

    Mutation that must red: replace the body of approval_results_for_cycle with
    {call_id: True for call_id in pending_call_ids} — the rejected call would
    receive True and the 'not results["call-rejected"]' assertion below would red.
    """
    run_id, step_id, suspension_seq, pending = mixed_suspension

    with psycopg.connect(database_url("api")) as conn:
        append_approval_decision(
            conn,
            run_id=run_id,
            step_id=step_id,
            call_ids=pending,
            decisions=[APPROVAL_GRANTED, APPROVAL_REJECTED],
            principal=_MIXED_PRINCIPAL,
            suspension_seq=suspension_seq,
        )

    results = approval_results_for_cycle(
        step_id=str(step_id), cycle=1, pending_call_ids=pending
    )

    assert results["call-granted"] is True, (
        f"expected call-granted to be True, got {results['call-granted']!r}"
    )
    assert results["call-rejected"] is False, (
        f"expected call-rejected to be False, got {results['call-rejected']!r}; "
        "mutation: returning True for all would fail this assertion"
    )


@pytest.mark.substrate
def test_pending_call_with_no_decision_makes_resume_refuse(
    mixed_suspension: tuple[uuid.UUID, uuid.UUID, int, list[str]],
) -> None:
    """AC-0330: a pending call with no committed decision causes a refusal (Entry 5).

    One call is granted; the other has no committed decision. approval_results_for_cycle
    must raise LookupError for the pending set that includes the undecided call.

    Mutation that must red: make the rejected result admit the call (return True
    for it) — without the missing-call check, this test would not raise.
    """
    run_id, step_id, suspension_seq, pending = mixed_suspension

    # Commit a grant for only the first call; leave the second pending.
    with psycopg.connect(database_url("api")) as conn:
        append_approval_decision(
            conn,
            run_id=run_id,
            step_id=step_id,
            call_ids=[pending[0]],  # only one
            decisions=[APPROVAL_GRANTED],
            principal=_MIXED_PRINCIPAL,
            suspension_seq=suspension_seq,
        )

    # Now request results for BOTH calls — one has no decision, so LookupError.
    with pytest.raises(LookupError, match="no committed decision"):
        approval_results_for_cycle(step_id=str(step_id), cycle=1, pending_call_ids=pending)


# ── AC-0333: third case — repeated-poll does not re-claim (Entry 10) ─────────


@pytest.mark.substrate
def test_suspension_path_sets_awaiting_decision_and_blocks_repoll(
    require_substrate: None,
) -> None:
    """AC-0333 third case: executor suspension path writes awaiting_decision=true.

    Drives the step through make_step_body (TestModel calls request_approval →
    executor suspends, writes awaiting_decision=true). Then polls claim_one
    three times and asserts the suspended step is never returned.

    Mutation that must red: change the suspension path at executor.py to write
    awaiting_decision=false. The step becomes claimable again immediately;
    claim_one returns it, failing the 'must not return suspended step' check.
    """
    _POOL_CLASS = "t2-awaiting-suspension-path"
    _ROLE = "t2-awaiting-suspension-path-role"

    from pydantic_ai.models.test import TestModel

    config = PoolConfig(
        worker_id="t2-await-worker",
        default_limits=_GATE_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(call_tools=["request_approval"]),
        pool_class=_POOL_CLASS,
    )

    run_id, step_id, lease = _insert_role_and_step(
        needs_approval=True, role_name=_ROLE, pool_class=_POOL_CLASS, config=config
    )

    try:
        # First pass: executor suspends the step (writes awaiting_decision=true).
        body = make_step_body(config)
        body(lease, threading.Event())

        # Verify the step is now awaiting a decision.
        with psycopg.connect(database_url("worker")) as conn:
            row = conn.execute(
                "SELECT awaiting_decision FROM steps WHERE step_id = %s",
                (step_id,),
            ).fetchone()
        assert row is not None and row[0] is True, (
            "executor suspension path must set awaiting_decision=true; "
            "mutation: write false → this assertion reds immediately"
        )

        # Poll three times: the suspended step must never be returned.
        with psycopg.connect(database_url("worker")) as conn:
            for i in range(3):
                claimed = claim_one(conn, config)
                assert claimed is None or claimed.step_id != step_id, (
                    f"poll {i}: claim_one returned the suspended step; "
                    "mutation: awaiting_decision=false → step claimable → this reds"
                )
    finally:
        _cleanup_run(run_id)


# ── AC-0321: cycle cap fires across a worker handoff ─────────────────────────

_CAP_POOL_CLASS = "t3-cycle-cap"
_CAP_PRINCIPAL = "t3-cycle-cap-test"
_CAP_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}


@pytest.mark.substrate
def test_the_cycle_cap_fires_across_a_handoff(require_substrate: None) -> None:
    """AC-0321: cycle cap reads approval_cycles from the DB; cause is in the log.

    Worker A suspends the step (approval_cycles=0 at suspension).  An approval
    decision commits, advancing steps.approval_cycles to 1.  Worker B runs in a
    **separate subprocess** — a genuine process boundary — and claims the step.
    Its body reads approval_cycles=1 from the DB, sees it >= cap=1, appends
    step.approval.cap.exceeded + run.failed, and exits.

    Three mutation proofs:

    - Cap check removal: remove 'if approval_cycles >= config.approval_cycle_cap'
      in executor.py → Worker B resumes; subprocess exits 2 (no cap); assertion
      on returncode == 0 reds.

    - Recorded-cause removal: replace step.approval.cap.exceeded with bare
      step.failed → 'step.approval.cap.exceeded' absent from log → assertion
      reds while event count stays the same.

    - Handoff assertion: run both bodies from one PoolConfig (one worker_id) in
      one process → claim_one sets steps.owner to Worker A's id → the
      owner assertion reds.
    """
    from pydantic_ai.models.test import TestModel

    _CAP_ROLE = "t3-cycle-cap-role"

    # Worker A: suspends the step (TestModel calls request_approval).
    config_a = PoolConfig(
        worker_id="t3-cap-worker-a",
        default_limits=_CAP_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(call_tools=["request_approval"]),
        pool_class=_CAP_POOL_CLASS,
        approval_cycle_cap=1,
    )

    run_id, step_id, lease_a = _insert_role_and_step(
        needs_approval=True,
        role_name=_CAP_ROLE,
        pool_class=_CAP_POOL_CLASS,
        config=config_a,
    )

    try:
        # Worker A (main process): body suspends (awaiting_decision=true,
        # approval_cycles=0).
        body_a = make_step_body(config_a)
        body_a(lease_a, threading.Event())

        # Read the suspension event to get payload_ref and suspension_seq.
        with psycopg.connect(database_url("worker")) as conn:
            events_after_suspend = read_events(conn, run_id=run_id)
        suspended = [e for e in events_after_suspend if e.type == "step.suspended"]
        assert len(suspended) == 1, (
            f"expected one suspension event; got {[e.type for e in events_after_suspend]}"
        )
        payload_ref = suspended[0].payload_ref
        suspension_seq = suspended[0].seq
        assert payload_ref is not None, "step.suspended must carry a payload_ref"

        _, pending_call_ids = load_suspension_payload(payload_ref)

        # Commit a grant decision — advances steps.approval_cycles to 1 and
        # clears awaiting_decision, making the step claimable.
        with psycopg.connect(database_url("api")) as conn:
            append_approval_decision(
                conn,
                run_id=run_id,
                step_id=step_id,
                call_ids=pending_call_ids,
                decisions=[APPROVAL_GRANTED] * len(pending_call_ids),
                principal=_CAP_PRINCIPAL,
                suspension_seq=suspension_seq,
            )

        # Worker B runs in a separate subprocess — a genuine process boundary.
        # The subprocess claims the step, runs the body, and exits 0 when the
        # cap fires (_StepBodyFailed caught) or 2 when the cap does not fire.
        # Subprocess exit 1 is an unexpected error.
        worker_b_script = textwrap.dedent(f"""\
            import sys
            import threading
            import uuid
            from pydantic_ai.models.test import TestModel
            from ced.adapters.postgres.dsn import database_url
            from ced.worker.pool import PoolConfig, claim_one
            from ced.worker.executor import make_step_body, _StepBodyFailed
            import psycopg

            config_b = PoolConfig(
                worker_id="t3-cap-worker-b",
                default_limits={{
                    "per_request_input_tokens_limit": 4_000,
                    "input_tokens_limit": 40_000,
                    "request_limit": 8,
                    "tool_calls_limit": 4,
                    "count_tokens_before_request": False,
                }},
                allowed_model_ids=("stub:counting",),
                non_provider_model_ids=("stub:counting",),
                model_factory=lambda _: TestModel(custom_output_args={{"references": []}}),
                pool_class="{_CAP_POOL_CLASS}",
                approval_cycle_cap=1,
            )
            with psycopg.connect(database_url("worker")) as conn:
                lease = claim_one(conn, config_b)
            if lease is None or str(lease.step_id) != "{step_id}":
                print(f"claim_one returned {{lease!r}}", file=sys.stderr)
                sys.exit(3)
            body = make_step_body(config_b)
            try:
                body(lease, threading.Event())
                sys.exit(2)  # unexpected: cap did not fire
            except _StepBodyFailed:
                sys.exit(0)  # expected: cap fired
            except Exception as exc:
                print(f"unexpected: {{exc}}", file=sys.stderr)
                sys.exit(1)
        """)
        result = subprocess.run(
            [sys.executable, "-c", worker_b_script],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Worker B subprocess expected exit 0 (cap fired); "
            f"got {result.returncode}. stderr: {result.stderr!r}. "
            "mutation: remove cap-check block in executor.py → body returns normally "
            "→ subprocess exits 2 → returncode != 0 → reds"
        )

        # Handoff assertion: steps.owner must be Worker B's id, not Worker A's.
        # Proves the count was read from the DB (not in-process state): if both
        # bodies were run from one PoolConfig (same worker_id), claim_one would
        # set owner to Worker A's id and this assertion would red.
        with psycopg.connect(database_url("migration")) as conn:
            owner_row = conn.execute(
                "SELECT owner FROM steps WHERE step_id = %s", (step_id,)
            ).fetchone()
        assert owner_row is not None and owner_row[0] != "t3-cap-worker-a", (
            f"steps.owner must be Worker B's id after the handoff; "
            f"got {owner_row[0]!r}; "
            "mutation: use one PoolConfig (worker_id='t3-cap-worker-a') for both bodies "
            "→ claim_one sets owner='t3-cap-worker-a' → this assertion reds"
        )

        # Recorded cause: the cap path must write a distinct event type so the
        # cause is recoverable from the log alone, not only from log.warning or
        # exception messages.  Scoped to the cap path; AC-0330's refusal path
        # is unchanged.
        with psycopg.connect(database_url("worker")) as conn:
            events_final = read_events(conn, run_id=run_id)
        event_types = {e.type for e in events_final}
        assert "step.approval.cap.exceeded" in event_types, (
            f"step.approval.cap.exceeded must be appended when the cycle cap fires; "
            f"got {event_types}; "
            "mutation: replace with bare step.failed → distinct type absent → reds"
        )
        assert "run.failed" in event_types, (
            f"run.failed must be appended when the cycle cap fires; got {event_types}"
        )

        # State assertion: the run must reach failed state, not only emit the
        # event.  A mutation that appends run.failed but then reverts
        # runs.state = 'running' would pass the event assertion and red here.
        with psycopg.connect(database_url("migration")) as conn:
            state_row = conn.execute(
                "SELECT state FROM runs WHERE run_id = %s", (run_id,)
            ).fetchone()
        assert state_row is not None and state_row[0] == "failed", (
            f"runs.state must be 'failed' after the cycle cap fires; "
            f"got {state_row[0]!r}; "
            "mutation: UPDATE runs SET state='running' after append_run_terminal "
            "→ event present but state wrong → reds"
        )
    finally:
        _cleanup_run(run_id)


@pytest.mark.substrate
def test_executor_agent_failure_sets_step_state_to_failed(
    require_substrate: None,
) -> None:
    """Entry 11: pool records steps.state='failed' when executor raises _StepBodyFailed.

    Patches _run_compiled_agent to raise RuntimeError, triggering the executor's
    agent-run failure path (line 612). That path appends step.failed and raises
    _StepBodyFailed. The pool's body() wrapper catches the exception and records
    outcome='failed', which release() writes as steps.state='failed'.

    Mutation that must red: change ``raise _StepBodyFailed("agent run failed") from exc``
    to ``return`` at executor.py line 612. The executor returns normally; the pool
    records outcome='completed'; release() writes steps.state='completed'; the
    'failed' assertion reds.
    """
    from pydantic_ai.models.test import TestModel

    _POOL_CLASS = "t2-pool-outcome-failure"
    _ROLE = "t2-pool-outcome-failure-role"

    config = PoolConfig(
        worker_id="t2-pool-outcome-worker",
        default_limits=_GATE_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(
            call_tools=[],
            custom_output_args={"references": []},
        ),
        pool_class=_POOL_CLASS,
    )

    run_id, step_id, lease = _insert_role_and_step(
        needs_approval=None, role_name=_ROLE, pool_class=_POOL_CLASS, config=config
    )

    try:
        with mock.patch(
            "ced.worker.executor._run_compiled_agent",
            side_effect=RuntimeError("simulated agent failure — Entry 11"),
        ):
            worker = Worker(config, step_body=make_step_body(config))
            with psycopg.connect(database_url("worker")) as conn:
                worker._execute(conn, lease)

        with psycopg.connect(database_url("migration")) as conn:
            row = conn.execute(
                "SELECT state FROM steps WHERE step_id = %s", (step_id,)
            ).fetchone()
        assert row is not None and row[0] == "failed", (
            f"expected steps.state='failed', got {row[0]!r}; "
            "mutation: change 'raise _StepBodyFailed' to 'return' at executor.py:612 → "
            "pool records 'completed' → steps.state='completed' → this assertion reds"
        )
    finally:
        _cleanup_run(run_id)


@pytest.mark.substrate
def test_repeated_poll_against_undecided_step_appends_nothing_and_consumes_no_lease(
    require_substrate: None,
) -> None:
    """AC-0333 third case (predicate guard): claim_one never returns a step with
    awaiting_decision=true.

    Creates an undecided step directly via raw SQL to pin the claim_one predicate
    independently of the suspension path. Three successive calls must return
    None (or the second non-awaiting step), never the awaiting step.

    Mutation that must red: negate 'AND NOT awaiting_decision' to 'AND awaiting_decision'
    in claim_one — the awaiting step is returned; the non-awaiting step is excluded.
    (Entry 9 mutation, confirmed earlier to red this test.)
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    pool_class = "t2-repeated-poll"

    with psycopg.connect(database_url("migration")) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'running', 0)",
                (run_id,),
            )
            conn.execute(
                "INSERT INTO steps (step_id, run_id, state, awaiting_decision, pool_class)"
                " VALUES (%s, %s, 'runnable', true, %s)",
                (step_id, run_id, pool_class),
            )

    # A second runnable step (not awaiting) ensures the pool is not empty
    run2_id = uuid.uuid4()
    step2_id = uuid.uuid4()

    try:
        with psycopg.connect(database_url("migration")) as conn:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO runs (run_id, state, next_seq) VALUES (%s, 'running', 0)",
                    (run2_id,),
                )
                conn.execute(
                    "INSERT INTO steps (step_id, run_id, state, awaiting_decision, pool_class)"
                    " VALUES (%s, %s, 'runnable', false, %s)",
                    (step2_id, run2_id, pool_class),
                )

        poll_config = PoolConfig(
            worker_id="t2-poll-worker",
            default_limits=_MIXED_LIMITS,
            allowed_model_ids=("stub:counting",),
            non_provider_model_ids=("stub:counting",),
            model_factory=lambda _: None,
            pool_class=pool_class,
        )

        # Read baseline event count and lease_epoch before any polls.
        # spec.md:178: "a worker polling repeatedly against the undecided step
        # appends nothing and consumes no lease."
        with psycopg.connect(database_url("migration")) as conn:
            event_count_before = int(
                conn.execute(
                    "SELECT count(*) FROM events WHERE run_id = %s", (run_id,)
                ).fetchone()[0]
            )
            epoch_before = int(
                conn.execute(
                    "SELECT lease_epoch FROM steps WHERE step_id = %s", (step_id,)
                ).fetchone()[0]
            )

        with psycopg.connect(database_url("worker")) as conn:
            # Three polls. The undecided step must never appear; the runnable
            # step2 may appear but step1 must never.
            for i in range(3):
                lease = claim_one(conn, poll_config)
                # If a lease was returned, it must not be for the undecided step.
                if lease is not None:
                    assert lease.step_id != step_id, (
                        f"poll {i}: claim_one returned the undecided step; "
                        "the awaiting_decision predicate is not excluding it"
                    )
                    # Release it so the next poll can find it again.
                    conn.execute(
                        "UPDATE steps SET state = 'runnable', owner = NULL,"
                        " lease_expires_at = NULL WHERE step_id = %s",
                        (lease.step_id,),
                    )
                    conn.commit()

        # Assert that no events were appended and the lease was not consumed.
        # Mutation that must red (lease_epoch): negate 'AND NOT awaiting_decision'
        # in claim_one — the awaiting step is claimed, lease_epoch advances for
        # each poll, and the epoch assertion reds. (The inner identity assertion
        # above also reds on this mutation; the epoch assertion provides the same
        # coverage independently, so either alone would catch it.)
        with psycopg.connect(database_url("migration")) as conn:
            event_count_after = int(
                conn.execute(
                    "SELECT count(*) FROM events WHERE run_id = %s", (run_id,)
                ).fetchone()[0]
            )
            epoch_after = int(
                conn.execute(
                    "SELECT lease_epoch FROM steps WHERE step_id = %s", (step_id,)
                ).fetchone()[0]
            )
        assert event_count_after == event_count_before, (
            f"repeated polls must append no events; before={event_count_before}, "
            f"after={event_count_after}"
        )
        assert epoch_after == epoch_before, (
            f"repeated polls must not consume the lease; lease_epoch before={epoch_before}, "
            f"after={epoch_after}; "
            "mutation: negate 'AND NOT awaiting_decision' in claim_one → awaiting step "
            "claimed → lease_epoch advances → this assertion reds"
        )

        # The undecided step still has its original awaiting_decision=true.
        with psycopg.connect(database_url("migration")) as conn:
            row = conn.execute(
                "SELECT awaiting_decision FROM steps WHERE step_id = %s",
                (step_id,),
            ).fetchone()
        assert row is not None and row[0] is True, (
            "undecided step should still have awaiting_decision=true after repeated polls"
        )
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id IN (%s, %s)", (run_id, run2_id))
            conn.execute("DELETE FROM steps WHERE run_id IN (%s, %s)", (run_id, run2_id))
            conn.execute("DELETE FROM runs WHERE run_id IN (%s, %s)", (run_id, run2_id))
            conn.commit()


# ── AC-0330: resume path — rejection non-execution, refusal, post-refusal ─────


@pytest.mark.substrate
def test_rejected_tool_body_does_not_run_on_resume(require_substrate: None) -> None:
    """AC-0330: a rejected deferred call does not invoke the tool body on resume.

    Suspends a step, commits APPROVAL_REJECTED for all pending calls, re-claims
    the step, patches ``request_approval`` with a spy, then calls ``resume_step``.
    With all calls rejected, pydantic_ai delivers the rejection to the model
    without executing the tool body — the spy must not fire.

    Mutation that must red: replace the ``approval_results_for_cycle`` return
    with ``{cid: True for cid in pending_call_ids}`` (all approved) at
    persistence.py — pydantic_ai re-executes the deferred call, the spy fires,
    and ``not body_called.is_set()`` reds.
    """
    from pydantic_ai.models.test import TestModel

    _POOL_CLASS = "t2-ac0330-rejection"
    _ROLE = "t2-ac0330-rejection-role"

    config = PoolConfig(
        worker_id="t2-ac0330-rejection-worker",
        default_limits=_GATE_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(call_tools=["request_approval"]),
        pool_class=_POOL_CLASS,
    )

    run_id, step_id, lease = _insert_role_and_step(
        needs_approval=True, role_name=_ROLE, pool_class=_POOL_CLASS, config=config
    )

    try:
        # Suspend the step (TestModel calls request_approval → executor suspends).
        make_step_body(config)(lease, threading.Event())

        # Read the suspension event to get payload_ref and suspension_seq.
        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)
        suspended_events = [e for e in events if e.type == "step.suspended"]
        assert len(suspended_events) == 1, (
            f"expected one suspension, got {[e.type for e in events]}"
        )
        payload_ref = suspended_events[0].payload_ref
        suspension_seq = suspended_events[0].seq
        assert payload_ref is not None, "step.suspended must carry a payload_ref"

        # Read pending_call_ids from the suspension payload.
        _, pending_call_ids = load_suspension_payload(payload_ref)

        # Commit APPROVAL_REJECTED for every pending call.
        with psycopg.connect(database_url("api")) as conn:
            append_approval_decision(
                conn,
                run_id=run_id,
                step_id=step_id,
                call_ids=pending_call_ids,
                decisions=[APPROVAL_REJECTED] * len(pending_call_ids),
                principal=_GATE_PRINCIPAL,
                suspension_seq=suspension_seq,
            )

        # Re-claim the step (awaiting_decision was cleared by the decision commit).
        resume_config = PoolConfig(
            worker_id="t2-ac0330-rejection-resume-worker",
            default_limits=_GATE_LIMITS,
            allowed_model_ids=("stub:counting",),
            non_provider_model_ids=("stub:counting",),
            model_factory=lambda _: TestModel(custom_output_args={"references": []}),
            pool_class=_POOL_CLASS,
        )
        with psycopg.connect(database_url("worker")) as conn:
            new_lease = claim_one(conn, resume_config)
        assert new_lease is not None and new_lease.step_id == step_id, (
            "claim_one must return the step after the decision clears awaiting_decision"
        )

        # Spy on request_approval: the body must not run when approval is False.
        # functools.wraps copies __name__ so pydantic_ai can match the deferred
        # call (stored as 'request_approval') back to the spy function.
        body_called = threading.Event()

        @functools.wraps(_real_request_approval)
        def _spy() -> None:
            body_called.set()

        pool_map: dict[str, Any] = {
            "default_limits": dict(_GATE_LIMITS),
            "allowed_model_ids": ("stub:counting",),
            "non_provider_model_ids": ("stub:counting",),
            "model_factory": lambda _: TestModel(custom_output_args={"references": []}),
        }

        with mock.patch("ced.worker.persistence.request_approval", _spy):
            resume_step(
                run_id=run_id,
                step_id=step_id,
                lease_epoch=new_lease.epoch,
                role_name=_ROLE,
                role_version=1,
                payload_ref=payload_ref,
                pool_map=pool_map,
            )

        assert not body_called.is_set(), (
            "request_approval body must not be called when all tool calls are rejected; "
            "mutation: replace approval_results_for_cycle return with {cid: True for all} → "
            "pydantic_ai re-executes the deferred call → spy fires → this assertion reds"
        )
    finally:
        _cleanup_run(run_id)


@pytest.mark.substrate
def test_refused_resume_commits_step_failed_and_run_failed(require_substrate: None) -> None:
    """AC-0330: resume with no committed decision appends step.failed and run.failed.

    Suspends a step then bypasses the decision gate (manually clears
    awaiting_decision without committing any decision), leaving approval_cycles=0.
    resume_step reads cycle=0, calls approval_results_for_cycle which raises
    LookupError (cycle < 1), catches it, appends the terminal pair, and re-raises.

    After the three-poll check (Test C of the adjudicator entry), no additional
    events and no lease advance must be observed.

    Mutation that must red (step.failed): delete the append_step_event('step.failed')
    call in persistence.py's refusal branch → step.failed absent → reds.
    Mutation that must red (run.failed): delete append_run_terminal('run.failed') →
    run.failed absent → reds.
    Mutation that must red (lease_epoch, post-refusal poll): if the refusal path
    set steps.state='runnable' (a bug), claim_one would re-claim the step →
    lease_epoch advances → reds.
    """
    from pydantic_ai.models.test import TestModel

    _POOL_CLASS = "t2-ac0330-refusal"
    _ROLE = "t2-ac0330-refusal-role"

    config = PoolConfig(
        worker_id="t2-ac0330-refusal-worker",
        default_limits=_GATE_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(call_tools=["request_approval"]),
        pool_class=_POOL_CLASS,
    )

    run_id, step_id, lease = _insert_role_and_step(
        needs_approval=True, role_name=_ROLE, pool_class=_POOL_CLASS, config=config
    )

    try:
        # Suspend the step.
        make_step_body(config)(lease, threading.Event())

        # Read payload_ref from the step.suspended event.
        with psycopg.connect(database_url("worker")) as conn:
            events_after_suspend = read_events(conn, run_id=run_id)
        suspended_events = [e for e in events_after_suspend if e.type == "step.suspended"]
        assert len(suspended_events) == 1, (
            f"expected one suspension, got {[e.type for e in events_after_suspend]}"
        )
        payload_ref = suspended_events[0].payload_ref
        assert payload_ref is not None

        # Do NOT commit any decision.  Manually clear awaiting_decision so
        # claim_one can reclaim the step.  This leaves approval_cycles=0, which
        # resume_step passes to approval_results_for_cycle as cycle=0 — a cycle
        # below 1, which raises LookupError immediately (the "below 1" guard).
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute(
                "UPDATE steps SET awaiting_decision = false WHERE step_id = %s",
                (step_id,),
            )
            conn.commit()

        # Re-claim the step.
        resume_config = PoolConfig(
            worker_id="t2-ac0330-refusal-resume-worker",
            default_limits=_GATE_LIMITS,
            allowed_model_ids=("stub:counting",),
            non_provider_model_ids=("stub:counting",),
            model_factory=lambda _: None,
            pool_class=_POOL_CLASS,
        )
        with psycopg.connect(database_url("worker")) as conn:
            new_lease = claim_one(conn, resume_config)
        assert new_lease is not None and new_lease.step_id == step_id, (
            "claim_one must return the step after awaiting_decision is cleared"
        )

        pool_map: dict[str, Any] = {
            "default_limits": dict(_GATE_LIMITS),
            "allowed_model_ids": ("stub:counting",),
            "non_provider_model_ids": ("stub:counting",),
            "model_factory": lambda _: None,
        }

        # resume_step must raise (no committed decision for cycle 0).
        with pytest.raises(LookupError):
            resume_step(
                run_id=run_id,
                step_id=step_id,
                lease_epoch=new_lease.epoch,
                role_name=_ROLE,
                role_version=1,
                payload_ref=payload_ref,
                pool_map=pool_map,
            )

        # Both terminal events must be in the log.
        with psycopg.connect(database_url("worker")) as conn:
            events_after_refusal = read_events(conn, run_id=run_id)
        event_types = {e.type for e in events_after_refusal}
        assert "step.failed" in event_types, (
            f"step.failed must be appended on resume refusal; got {event_types}; "
            "mutation: delete append_step_event('step.failed') in persistence.py "
            "refusal branch → absent → reds"
        )
        assert "run.failed" in event_types, (
            f"run.failed must be appended on resume refusal; got {event_types}; "
            "mutation: delete append_run_terminal('run.failed') in persistence.py "
            "refusal branch → absent → reds"
        )

        # Test C (repeated poll after refusal): additional polls must append no
        # events and must not advance the lease.  The step is still 'leased' with
        # a live lease; claim_one's OR branch (expired-lease recovery) does not
        # apply, so no claim is possible.  A mutation that sets steps.state =
        # 'runnable' in the refusal branch would make the step immediately
        # claimable, bumping lease_epoch and reding the epoch assertion.
        event_count_before = len(events_after_refusal)
        with psycopg.connect(database_url("migration")) as conn:
            epoch_before = int(
                conn.execute(
                    "SELECT lease_epoch FROM steps WHERE step_id = %s", (step_id,)
                ).fetchone()[0]
            )

        poll_config = PoolConfig(
            worker_id="t2-ac0330-refusal-poll-worker",
            default_limits=_GATE_LIMITS,
            allowed_model_ids=("stub:counting",),
            non_provider_model_ids=("stub:counting",),
            model_factory=lambda _: None,
            pool_class=_POOL_CLASS,
        )
        with psycopg.connect(database_url("worker")) as conn:
            for _ in range(3):
                claimed = claim_one(conn, poll_config)
                assert claimed is None, (
                    "claim_one must not return the step after a refused resume; "
                    "the step is leased with a live lease and must not be reclaimed"
                )

        with psycopg.connect(database_url("worker")) as conn:
            events_after_polls = read_events(conn, run_id=run_id)
        event_count_after = len(events_after_polls)
        with psycopg.connect(database_url("migration")) as conn:
            epoch_after = int(
                conn.execute(
                    "SELECT lease_epoch FROM steps WHERE step_id = %s", (step_id,)
                ).fetchone()[0]
            )
        assert event_count_after == event_count_before, (
            f"repeated polls after refusal must append no events; "
            f"before={event_count_before}, after={event_count_after}"
        )
        assert epoch_after == epoch_before, (
            f"repeated polls after refusal must not advance the lease; "
            f"epoch before={epoch_before}, after={epoch_after}; "
            "mutation: set steps.state='runnable' in the refusal branch → "
            "step immediately claimable → claim_one bumps lease_epoch → reds"
        )
    finally:
        _cleanup_run(run_id)
