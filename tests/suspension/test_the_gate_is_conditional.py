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

import json
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
    start_run,
)
from ced.domain.events import APPROVAL_GRANTED, APPROVAL_REJECTED
from ced.worker.executor import _StepBodyFailed, make_step_body
from ced.worker.persistence import approval_results_for_cycle
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
            conn.execute(
                "INSERT INTO runs (run_id, state, next_seq)"
                " SELECT %s, 'running', 0 WHERE false",
                (run_id,),
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
