"""AC-0263 — usage limits are in force during a step run: identity and enforcement.

**Identity:** a tool inside the executor's injected toolset reads
``RunContext.usage_limits`` during the run.  The test asserts that value is
the identical object ``compile_role`` resolved — not a value the test itself
supplied to ``run_sync``.  The distinction matters because ``RunContext.usage_limits``
is always the caller's own object (measured ``is`` → ``True``); a test that
passes the limits and reads them back asserts a tautology.  Here the test
calls ``_run_compiled_agent``, which is the executor's code path, so the test
never touches ``agent.run_sync`` directly.

**Enforcement:** a run driven past one of the resolved thresholds
(``request_limit = 0``) raises ``UsageLimitExceeded``.  This is a
framework-regression guard: on the 2.45.0 pin enforcement and identity are
inseparable (the framework enforces against the very object it exposes), but
a future pin that accepts a limits object and stops applying it would pass the
identity check and red this one.

Note: ``tool_calls_limit = 0`` is not used here because deferred tool
requests (``requires_approval=True``) bypass the ``tool_calls_limit`` check
— the framework intercepts them before counting, so the limit never fires.
``request_limit = 0`` fires before the first model call and is not
intercepted by the approval mechanism.

Neither half reaches a provider.  Both run offline.
"""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any

import psycopg
import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import read_events, start_run
from ced.agents.compiler import compile_role
from ced.agents.tools.approval import request_approval
from ced.worker.executor import _make_approval_toolset, _run_compiled_agent, make_step_body
from ced.worker.pool import Lease, PoolConfig
from tests.compiler.role_records import POOL_DEFAULT_LIMITS, a_pool, a_role


def test_usage_limits_identity() -> None:
    """``RunContext.usage_limits`` seen from the run equals ``compiled.limits``.

    The observation tool is in the executor-injected toolset, not the compiled
    stack, so no policy decision point stands between the model call and the
    observation.  ``_run_compiled_agent`` is the executor's own function; the
    test does not call ``agent.run_sync`` itself.
    """
    compiled = compile_role(a_role(), [], a_pool(model=TestModel()))

    captured: list[UsageLimits] = []

    def observe(ctx: RunContext[Any]) -> str:
        """Read and capture the usage limits the executor threaded through."""
        captured.append(ctx.usage_limits)
        return "observed"

    # Build an observation toolset that also includes the real approval tool so
    # TestModel's call_tools='all' triggers suspension after observing.
    toolset: FunctionToolset[Any] = FunctionToolset()
    toolset.add_function(observe)
    toolset.add_function(request_approval, requires_approval=True)

    # _run_compiled_agent is the executor's function — not agent.run_sync.
    # It passes compiled.limits as usage_limits; the test only observes.
    _run_compiled_agent(compiled, [toolset])

    assert len(captured) == 1, f"expected one observation, got {len(captured)}"
    assert captured[0] is compiled.limits, (
        "RunContext.usage_limits must be the identical object compile_role resolved, "
        f"got {captured[0]!r} (id={id(captured[0])}), expected id={id(compiled.limits)}"
    )


def test_usage_limits_are_enforced() -> None:
    """A run driven past a resolved threshold is refused by the framework.

    Sets ``request_limit = 0`` so the first model request exceeds the limit
    before any model response arrives.  This is the regression guard: a pin
    that carries limits but never enforces them would pass the identity test
    and red here.
    """
    tight_limits = {**POOL_DEFAULT_LIMITS, "request_limit": 0}
    compiled = compile_role(
        a_role(), [], a_pool(model=TestModel(), default_limits=tight_limits)
    )

    with pytest.raises(UsageLimitExceeded):
        _run_compiled_agent(compiled, [_make_approval_toolset()])


# ── AC-0325: spend ceiling pages rather than aborting ───────────────────────


_CEILING_POOL_CLASS = "t3-spend-ceiling"
_CEILING_PRINCIPAL = "t3-ceiling-test"
_CEILING_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}


@pytest.mark.substrate
def test_the_spend_ceiling_pages_rather_than_aborting(require_substrate: None) -> None:
    """AC-0325: the per-run spend ceiling appends a page event and does not abort.

    Inflates runs.next_seq to 100 (via the migration role) before the body
    runs, with per_run_token_ceiling=50 in the PoolConfig.  The executor reads
    next_seq=100 > 50 before committing step.started, then appends
    step.spend.ceiling.reached after step.started commits.  The agent still
    runs to completion, so step.completed and run.completed follow.

    Mutation that must red (spend check removal): remove the seq_row read and
    _spend_ceiling_reached assignment in executor.py.  step.spend.ceiling.reached
    is absent from the log; the assertion reds.
    """
    _CEILING_ROLE = "t3-spend-ceiling-role"

    config = PoolConfig(
        worker_id="t3-ceiling-worker",
        default_limits=_CEILING_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: TestModel(custom_output_args={"references": []}),
        pool_class=_CEILING_POOL_CLASS,
        per_run_token_ceiling=50,
    )

    model_settings: dict[str, Any] = {
        "model_id": "stub:counting",
        "settings": {},
        "limits": {},
    }
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            """
            INSERT INTO agent_role
                (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
            VALUES (%s, 1, '[]'::jsonb, '', %s::jsonb, 'reference-selection')
            ON CONFLICT (role_name, version) DO UPDATE
                SET model_settings = EXCLUDED.model_settings
            """,
            (_CEILING_ROLE, json.dumps(model_settings)),
        )
        conn.commit()

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_CEILING_PRINCIPAL,
            agent_role=_CEILING_ROLE,
        )

    # Inflate next_seq above the ceiling before the body runs.
    # The executor reads next_seq BEFORE step.started commits, so only
    # prior-step events are counted; 100 > 50 triggers the page.
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            "UPDATE runs SET next_seq = 100 WHERE run_id = %s",
            (run_id,),
        )
        conn.commit()

    # Claim the step manually, consistent with _insert_role_and_step.
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
            (config.worker_id, _CEILING_POOL_CLASS, step_id),
        ).fetchone()
        conn.commit()

    assert row is not None
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=int(row[0]),
        agent_role=_CEILING_ROLE,
    )

    try:
        # Body: reads next_seq=100 > ceiling=50 → flags ceiling reached.
        # Commits step.started, appends step.spend.ceiling.reached, then completes.
        body = make_step_body(config)
        body(lease, threading.Event())

        with psycopg.connect(database_url("worker")) as conn:
            events = read_events(conn, run_id=run_id)
        event_types = {e.type for e in events}

        assert "step.spend.ceiling.reached" in event_types, (
            f"step.spend.ceiling.reached must be appended when next_seq > ceiling; "
            f"got {event_types}; "
            "mutation: remove the seq_row read and _spend_ceiling_reached in executor.py "
            "→ event absent → reds"
        )
        assert "step.completed" in event_types, (
            f"step.completed must follow the ceiling page (ceiling pages, not aborts); "
            f"got {event_types}"
        )
        assert "run.completed" in event_types, (
            f"run.completed must follow (ceiling pages rather than aborts); got {event_types}"
        )
    finally:
        with psycopg.connect(database_url("migration")) as conn:
            conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()
