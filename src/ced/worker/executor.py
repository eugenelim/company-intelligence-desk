"""Step body factory: compile the role, run the agent, record the outcome.

``make_step_body(config)`` returns a ``StepBody`` that carries the full
execution sequence for one claimed step:

 1. Read the initiating principal from the run's ``run.requested`` event.
 2. Load the role record from the database and compile it against the pool.
 3. Build the fourteen-field producer tuple (r8 § 5).
 4. Write the producer tuple as a content-addressed payload object — **before**
    the fenced append, per r5 § 3's crash-ordering requirement.
 5. Append ``step.started`` with the payload key as ``payload_ref``.
 6. Run the compiled agent, with a deadline-bound cancellation token.
 7. On suspension (``DeferredToolRequests`` output): write a suspension
    payload, append ``step.suspended`` with the payload key, then release the
    lease by clearing ``owner`` — the pool's subsequent ``release`` call is
    fenced on the old owner and silently finds zero rows.
 8. Append ``step.completed``, or ``step.failed`` on an agent error or a
    deadline-fired cancellation.

On a role load or compile failure ``append_role_refusal`` records the stage
that refused (AC-0261) and the body returns without appending ``step.completed``.

**No database connection is held during the model call.** The first connection
closes after ``step.started`` is committed; a new one opens after the agent
returns. Holding a transaction open across a multi-minute call would pin an
idle-in-transaction connection and block vacuum on the event-log tables — the
same reason the pool's own claim commits immediately.

**``PoolConfig`` is converted to a plain mapping before being handed to
``compile_role``.** ``compile_role`` takes ``pool: Mapping[str, Any]`` so
``agents/`` never imports ``worker/``. The mapping carries exactly the four
keys ``compile_role`` reads.

**Dependency constraints honoured here:**
- No ``pydantic_ai`` import: the framework type is reached through
  ``ced.agents.compiler.CompiledRole``, not imported directly.
- No ``boto3`` / ``botocore`` import: the object store is reached through
  ``ced.adapters.objectstore.client``, which lives in ``adapters/``.

**Deadline and suspension (T2):**
- ``_run_compiled_agent`` is the single call-site for ``agent.run_sync``.
  Keeping it in one named function lets tests call it directly — which is
  what makes AC-0263's identity check non-tautological: the test calls the
  executor's function, not ``agent.run_sync`` itself.
- The cancellation token is disarmed in a ``finally`` block, so a deadline
  firing between the agent return and the event commit cannot discard a step
  that already succeeded (AC-0232).
- Suspension releases the lease by setting ``owner = NULL``; the pool's own
  ``release`` is fenced on the caller's worker id and silently no-ops.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Mapping, Sequence
from typing import Any, cast

import psycopg

from ced.adapters.bedrock.model_factory import FETCH_ADAPTER_NAME, MODEL_ADAPTER_NAME
from ced.adapters.framework_contract import (
    PINNED_FRAMEWORK_VERSION,
    CancellationToken,
    DeferredToolRequests,
    FunctionToolset,
)
from ced.adapters.objectstore.client import write_payload
from ced.adapters.objectstore.history import serialise_history
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import append_step_event, read_run_principal
from ced.adapters.postgres.roles import (
    LoadedRole,
    RoleLoadError,
    load_entitlements,
    load_role,
)
from ced.agents.ceilings import compile_ceiling
from ced.agents.compiler import (
    CompiledRole,
    RoleCompileError,
    append_role_refusal,
    compile_role,
)
from ced.agents.tools.approval import request_approval
from ced.agents.toolsets import PolicyDecisionPoint
from ced.agents.toolsets.step_events import StepContext, StepEventToolset
from ced.worker.pool import Lease, PoolConfig, StepBody

log = logging.getLogger("ced.worker.executor")

__all__ = ["make_step_body"]


def _tool_manifest_hash(integrations: Sequence[Mapping[str, Any]]) -> str:
    """SHA-256 of the sorted list of tool names across all integration rows.

    An empty integration set yields the hash of ``[]``, which is the value for
    any quarantined role (empty ceiling, no integrations). AC-0254 requires
    this field so "what a step was exposed to" is recoverable from the log.
    """
    tools: list[str] = sorted(
        tool
        for record in integrations
        for tool in (record.get("tools") or [])
        if isinstance(tool, str)
    )
    return hashlib.sha256(json.dumps(tools, separators=(",", ":")).encode()).hexdigest()


def _producer_tuple(
    loaded: LoadedRole,
    model_adapter: str,
    fetch_adapter: str,
) -> dict[str, Any]:
    """Build the fourteen-field producer tuple (r8 § 5).

    Fields not yet tracked in Phase 1 (``model_version``,
    ``prompt_template_version``, ``context_assembler_version``,
    ``app_image_digest``) are set to ``None`` and recorded as unknowns rather
    than omitted, so the tuple's shape is stable across the version history.

    ``inference_profile`` is the same string as ``model_id`` for cross-region
    inference profiles: a ``us.*``-prefixed id *is* the profile id and names
    the region in which authorization is evaluated.
    """
    model_settings: Mapping[str, Any] = loaded.role.get("model_settings") or {}
    settings: Mapping[str, Any] = model_settings.get("settings") or {}
    model_id = str(model_settings.get("model_id", ""))

    return {
        "model_id": model_id,
        "model_version": None,
        "inference_profile": model_id,
        "temperature": settings.get("temperature"),
        "top_p": settings.get("top_p"),
        "max_tokens": settings.get("max_tokens"),
        "prompt_template_version": None,
        "tool_manifest_hash": _tool_manifest_hash(loaded.integrations),
        "agent_role_version": int(loaded.role.get("version", 1)),
        "context_assembler_version": None,
        "app_image_digest": None,
        "fetch_adapter": fetch_adapter,
        "model_adapter": model_adapter,
        "framework_version": PINNED_FRAMEWORK_VERSION,
    }


def _pool_mapping(config: PoolConfig) -> dict[str, Any]:
    """Convert ``PoolConfig`` to the plain mapping ``compile_role`` accepts.

    ``compile_role`` takes ``pool: Mapping[str, Any]`` so ``agents/`` never
    imports ``worker/``. This function bridges the gap: it is the only place
    that knows which fields ``compile_role`` reads and how they map to the
    dataclass.
    """
    return {
        "default_limits": config.default_limits,
        "allowed_model_ids": list(config.allowed_model_ids),
        "non_provider_model_ids": list(config.non_provider_model_ids),
        "model_factory": config.model_factory,
    }


def _cancel_when_stopped(stop: threading.Event, token: CancellationToken) -> None:
    """Cancel ``token`` when the pool signals drain.  Daemon thread target.

    The pool sets its ``body_stop`` event on drain; wiring it to the
    cancellation token lets ``run_sync`` raise ``RunCancelled`` rather than
    finishing a model call nobody will use.  The thread is daemon so it does
    not prevent the process from exiting if stop is never set.
    """
    stop.wait()
    token.cancel()


def _make_approval_toolset() -> FunctionToolset[Any]:
    """Build the run-time approval toolset the executor injects for each run.

    The toolset is **not** compiled into the agent; it is passed via
    ``toolsets=[...]`` on ``run_sync`` so the approval gate is outside the
    policy decision point's authority check (DR1).
    """
    toolset: FunctionToolset[Any] = FunctionToolset()
    toolset.add_function(request_approval, requires_approval=True)
    return toolset


def _run_compiled_agent(
    compiled: CompiledRole,
    approval_toolset: FunctionToolset[Any],
    cancellation_token: CancellationToken | None = None,
) -> Any:
    """Call ``agent.run_sync`` with the executor's bound, override, and token.

    **This function is the single call-site for ``agent.run_sync``.** Keeping
    the call here — rather than inline in ``body()`` — is what makes
    AC-0263's identity check non-tautological: a test that calls
    ``_run_compiled_agent`` is not calling ``agent.run_sync`` itself, so the
    ``usage_limits`` value it observes inside a tool is what the executor chose,
    not a value the test supplied.

    ``output_type`` is overridden at run time to admit ``DeferredToolRequests``
    alongside the role's own output type.  ``compiled.agent.output_type`` is
    unchanged (AC-0203's identity check in ``test_quarantined_role.py`` remains
    green).
    """
    return compiled.agent.run_sync(
        "Return an empty list of references.",
        usage_limits=compiled.limits,
        output_type=[compiled.agent.output_type, DeferredToolRequests],
        toolsets=[approval_toolset],
        cancellation_token=cancellation_token,
    )


def make_step_body(config: PoolConfig) -> StepBody:
    """Return a step body that compiles and runs the leased step's role.

    The returned body opens its own database connections per the ``StepBody``
    contract (``(Lease, threading.Event) -> None``), which carries no
    connection argument.
    """
    pool_map = _pool_mapping(config)

    def body(lease: Lease, stop: threading.Event) -> None:
        """Execute one step: load, compile, record, run, complete or suspend."""
        role_name = lease.agent_role or ""
        role_version = 1  # T1: agent_role column stores the role name; version 1 assumed.

        with psycopg.connect(database_url("worker")) as conn:
            # Read the initiating principal from the durable record — never
            # from the lease or from model-authored content.
            try:
                principal = read_run_principal(conn, run_id=lease.run_id)
            except Exception as exc:
                log.error(
                    "executor: could not read principal for run %s: %s",
                    lease.run_id,
                    exc,
                )
                return

            # Load the role from the registry (opens its own connection).
            try:
                loaded = load_role(role_name, role_version)
            except RoleLoadError as exc:
                append_role_refusal(
                    conn,
                    exc,
                    run_id=lease.run_id,
                    step_id=lease.step_id,
                    lease_epoch=lease.epoch,
                    principal=principal,
                    agent_role=role_name,
                )
                return

            # Compile the role against the pool configuration.
            try:
                compiled: CompiledRole = compile_role(
                    loaded.role, loaded.integrations, pool_map
                )
            except RoleCompileError as exc:
                append_role_refusal(
                    conn,
                    exc,
                    run_id=lease.run_id,
                    step_id=lease.step_id,
                    lease_epoch=lease.epoch,
                    principal=principal,
                    agent_role=role_name,
                )
                return

            # Write the producer tuple before the fenced append. A crash here
            # leaves an unreferenced object rather than a dangling payload_ref.
            payload_ref = write_payload(
                _producer_tuple(loaded, MODEL_ADAPTER_NAME, FETCH_ADAPTER_NAME)
            )

            append_step_event(
                conn,
                run_id=lease.run_id,
                step_id=lease.step_id,
                lease_epoch=lease.epoch,
                type="step.started",
                principal=principal,
                agent_role=role_name,
                payload_ref=payload_ref,
            )
        # Connection is released here; no transaction is held during the call.
        # The two the step context holds are opened next and closed in the
        # outer finally, because a tool call records through them mid-run.
        step_conn = psycopg.connect(database_url("worker"))
        policy_conn = psycopg.connect(database_url("policy"))

        # AC-0232: arm a deadline-bound cancellation token.  The stop_watcher
        # also cancels the token on pool drain, so a SIGTERM reaches the model
        # call promptly rather than waiting out the deadline.
        # **Bind the step context before the run, or a ceiling-bearing role
        # cannot execute at all.** Until AC-0227 needed one, every role this
        # executor ran was quarantined — an empty ceiling means no domain tool
        # exists and the decision point is never consulted — so the absence of
        # a binding was invisible. A domain tool reaching an unbound decision
        # point is refused with "no step context", which is the decision
        # point's own fail-closed behaviour and not a defect in it: a call it
        # cannot record is a call it must not admit.
        #
        # The entitlements conjunct is resolved here for the same principal the
        # run record names, which is the initial-run counterpart of what
        # `ced.worker.persistence.resume_step` does on the resume path.
        step_ctx = StepContext(
            connection=step_conn,
            policy_connection=policy_conn,
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            principal=principal,
            agent_role=role_name,
        )
        decision_point = cast(PolicyDecisionPoint, compiled.stack)
        decision_point.step = step_ctx
        cast(StepEventToolset, decision_point.wrapped).step = step_ctx
        decision_point.entitlements = compile_ceiling(
            "entitlements", list(load_entitlements(principal))
        )

        token = CancellationToken()
        threading.Thread(target=_cancel_when_stopped, args=(stop, token), daemon=True).start()
        deadline_timer: threading.Timer | None = None
        if config.step_deadline is not None:
            deadline_timer = threading.Timer(config.step_deadline, token.cancel)
            deadline_timer.start()

        # Run the agent. Any exception is caught and recorded as step.failed.
        # The finally block disarms the deadline timer whether the run succeeds,
        # suspends, or fails — so a late-firing timer cannot discard a completed
        # step (AC-0232).
        try:
            result = _run_compiled_agent(compiled, _make_approval_toolset(), token)
        except Exception as exc:
            log.error("executor: agent run failed for step %s: %s", lease.step_id, exc)
            with psycopg.connect(database_url("worker")) as conn:
                append_step_event(
                    conn,
                    run_id=lease.run_id,
                    step_id=lease.step_id,
                    lease_epoch=lease.epoch,
                    type="step.failed",
                    principal=principal,
                    agent_role=role_name,
                )
            return
        finally:
            if deadline_timer is not None:
                deadline_timer.cancel()
            step_conn.close()
            policy_conn.close()

        # AC-0237: suspension path.  Write the payload before the fenced append
        # (crash ordering per r5 § 3), then release the lease by clearing owner.
        # The pool's subsequent release call is fenced on the old owner value and
        # silently finds zero rows, so it cannot overwrite the suspension state.
        if isinstance(result.output, DeferredToolRequests):
            # AC-0228: strip reasoning parts before serialising (DR8 storage
            # backstop). AC-0226: write the full history so the suspended step
            # can be resumed from bytes alone (AC-0227).
            messages = result.all_messages()
            history_json_list = json.loads(serialise_history(messages))
            pending_call_ids = [call.tool_call_id for call in result.output.approvals]
            suspension_ref = write_payload(
                {
                    "schema_version": 1,
                    "history": history_json_list,
                    "pending_approval_call_ids": pending_call_ids,
                }
            )
            with psycopg.connect(database_url("worker")) as conn:
                append_step_event(
                    conn,
                    run_id=lease.run_id,
                    step_id=lease.step_id,
                    lease_epoch=lease.epoch,
                    type="step.suspended",
                    principal=principal,
                    agent_role=role_name,
                    payload_ref=suspension_ref,
                )
                conn.execute(
                    """
                    UPDATE steps
                       SET state = 'runnable',
                           lease_expires_at = NULL,
                           owner = NULL
                     WHERE step_id = %s
                       AND lease_epoch = %s
                       AND owner = %s
                    """,
                    (lease.step_id, lease.epoch, config.worker_id),
                )
                conn.commit()
            return

        with psycopg.connect(database_url("worker")) as conn:
            append_step_event(
                conn,
                run_id=lease.run_id,
                step_id=lease.step_id,
                lease_epoch=lease.epoch,
                type="step.completed",
                principal=principal,
                agent_role=role_name,
            )

    return body
