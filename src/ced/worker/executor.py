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
from ced.adapters.postgres.event_log import (
    append_run_terminal,
    append_step_event,
    read_run_principal,
)
from ced.adapters.postgres.roles import (
    LoadedRole,
    RoleLoadError,
    load_entitlements,
    load_role,
)
from ced.adapters.reasoning_disable_guard import ReasoningDisableGuard
from ced.agents.ceilings import compile_ceiling
from ced.agents.compiler import (
    CompiledRole,
    ReferenceSelection,
    RoleCompileError,
    append_role_refusal,
    compile_role,
)
from ced.agents.tools.approval import request_approval
from ced.agents.toolsets import PolicyDecisionPoint
from ced.agents.toolsets.step_events import StepContext, StepEventToolset
from ced.worker.context import ContextAssemblyError, assemble_planning_context
from ced.worker.persistence import resume_step
from ced.worker.pool import Lease, PoolConfig, StepBody
from ced.worker.prerelease import check_prerelease_failed

log = logging.getLogger("ced.worker.executor")

__all__ = ["make_step_body", "offered_approval_gated_tools"]


class _StepBodyFailed(Exception):
    """Raised by the step body when it records step.failed.

    The pool's body wrapper catches any ``Exception`` and records
    ``outcome = "failed"``.  Raising here — rather than returning — means the
    pool writes ``steps.state = 'failed'`` rather than ``'completed'`` for a
    step whose last event is ``step.failed`` (entry 11 adjudication).
    """


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


def offered_approval_gated_tools(prerelease_failed: bool) -> list[FunctionToolset[Any]]:
    """Return the list of toolsets the agent is offered at run time.

    When the pre-release check passes (``prerelease_failed=False``) the list is
    empty and the agent never sees the gated tool — satisfying the "no
    unconditional approval gate" boundary (AC-0302, Boundaries § Never do).

    When the check fails the list contains the approval toolset. The toolset is
    built fresh per call so each run gets its own instance (ADR-0008: the gate
    stays outside the compiled stack and is injected at run time).
    """
    if not prerelease_failed:
        return []
    return [_make_approval_toolset()]


def _run_compiled_agent(
    compiled: CompiledRole,
    toolsets: list[FunctionToolset[Any]],
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

    ``toolsets`` is the list returned by ``offered_approval_gated_tools``: empty
    for a clean run, one entry for a flagged run. Passing the list rather than a
    single toolset avoids branching here and keeps the approval-gate decision in
    one place.
    """
    return compiled.agent.run_sync(
        "Return an empty list of references.",
        usage_limits=compiled.limits,
        output_type=[compiled.agent.output_type, DeferredToolRequests],
        toolsets=toolsets,
        cancellation_token=cancellation_token,
        # AC-0276: refuse any call that would reach a provider without disabling
        # reasoning.  The guard is at the 'innermost' ordering tier so it sees
        # the model and settings after all per-step substitution and capability
        # layering.  It covers both request() and count_tokens() — count_tokens
        # runs before wrap_model_request and after before_model_request, so a
        # guard in before_model_request is the single point that precedes both.
        capabilities=[ReasoningDisableGuard()],
    )


def _body_resume(
    lease: Lease,
    config: PoolConfig,
    pool_map: dict[str, Any],
    principal: str,
    role_name: str,
    role_version: int,
) -> None:
    """Execute the resume path for a suspended step.

    Entry 8 (adjudication): a step whose ``approval_cycles > 0`` has a
    committed decision and must route through ``resume_step`` rather than
    running the agent from scratch.

    The payload_ref on the latest ``step.suspended`` event is the object-store
    key for the persisted history. ``resume_step`` reads it, loads the approval
    map for the current cycle, and runs the agent with the committed decisions
    applied.

    Completion follows the same convention as the fresh path: ``step.completed``
    + ``run.completed`` on success; ``step.failed`` (no ``run.failed``) on an
    unhandled agent error. On a ``LookupError`` from the AC-0330 refusal,
    ``resume_step`` appends both ``step.failed`` and ``run.failed`` before
    re-raising; the caller only needs to return.
    """
    # Find the payload_ref of the most recent step.suspended event so
    # resume_step can load the persisted history from the object store.
    with psycopg.connect(database_url("worker")) as conn:
        ref_row = conn.execute(
            "SELECT payload_ref FROM events"
            " WHERE step_id = %s AND type = 'step.suspended'"
            " ORDER BY seq DESC LIMIT 1",
            (lease.step_id,),
        ).fetchone()
        conn.commit()

    if ref_row is None or ref_row[0] is None:
        log.error(
            "executor: no suspension payload_ref for step %s — cannot resume",
            lease.step_id,
        )
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
        raise _StepBodyFailed("no suspension payload_ref")

    payload_ref = str(ref_row[0])

    try:
        result = resume_step(
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            role_name=role_name,
            role_version=role_version,
            payload_ref=payload_ref,
            pool_map=pool_map,
        )
    except LookupError as exc:
        # AC-0330 refusal: resume_step already appended step.failed + run.failed.
        raise _StepBodyFailed("AC-0330 refusal") from exc
    except Exception as exc:
        log.error("executor: resume failed for step %s: %s", lease.step_id, exc)
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
        raise _StepBodyFailed("resume failed") from exc

    # Re-suspension: the agent suspended again waiting for another approval.
    if isinstance(result.output, DeferredToolRequests):
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
                       owner = NULL,
                       awaiting_decision = true
                 WHERE step_id = %s
                   AND lease_epoch = %s
                   AND owner = %s
                """,
                (lease.step_id, lease.epoch, config.worker_id),
            )
            conn.commit()
        return

    # Completion: write a publication payload, then step.completed and
    # run.completed. The resumed path is not quarantine-validated, since
    # quarantine is a fresh-run property, so there is no validated output to
    # publish and this writes a schema-version stub.
    #
    # The stub carries no output while still resolving readably, which is the
    # shape that let the fresh-run twin of this branch be deleted: an artifact
    # asserting only that `payload_ref` resolves would pass on it. Nothing
    # asserts the resumed `payload_ref` today, so it is not vacuous yet —
    # AC-0303's end-to-end reads `step.resumed` and `runs.state` only. The
    # ledger records it as a residual for T3/T4 rather than a claim that a
    # resumed run publishes anything meaningful.
    output_payload_ref = write_payload({"schema_version": 1})
    with psycopg.connect(database_url("worker")) as conn:
        append_step_event(
            conn,
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            type="step.completed",
            principal=principal,
            agent_role=role_name,
            payload_ref=output_payload_ref,
        )
        append_run_terminal(
            conn,
            run_id=lease.run_id,
            step_id=lease.step_id,
            lease_epoch=lease.epoch,
            type="run.completed",
            principal=principal,
            agent_role=role_name,
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

            # Detect resume: if approval_cycles > 0 this step was previously
            # suspended and has a committed decision; route to the resume path.
            cycle_row = conn.execute(
                "SELECT approval_cycles FROM steps WHERE step_id = %s",
                (lease.step_id,),
            ).fetchone()
            conn.commit()

        approval_cycles = int(cycle_row[0]) if cycle_row else 0

        # AC-0321: cycle cap.  The count is read from `steps.approval_cycles`
        # (survives a worker handoff — it is a database value, not in-process
        # state).  When the count reaches the configured cap the step and run
        # fail with a recorded cause rather than looping.  The check fires
        # before _body_resume so a capped step is never resumed.
        if approval_cycles >= config.approval_cycle_cap:
            log.warning(
                "executor: step %s reached the approval cycle cap (%d >= %d); failing run %s",
                lease.step_id,
                approval_cycles,
                config.approval_cycle_cap,
                lease.run_id,
            )
            with psycopg.connect(database_url("worker")) as conn:
                # A distinct type so the cause is recoverable from the log
                # without reading log.warning output or exception messages.
                # Scoped to the cap path; AC-0330's refusal path is unchanged.
                append_step_event(
                    conn,
                    run_id=lease.run_id,
                    step_id=lease.step_id,
                    lease_epoch=lease.epoch,
                    type="step.approval.cap.exceeded",
                    principal=principal,
                    agent_role=role_name,
                )
                append_run_terminal(
                    conn,
                    run_id=lease.run_id,
                    step_id=lease.step_id,
                    lease_epoch=lease.epoch,
                    type="run.failed",
                    principal=principal,
                    agent_role=role_name,
                )
            raise _StepBodyFailed("approval cycle cap exceeded")

        if approval_cycles > 0:
            # Entry 8 (adjudication): wire resume_step into the pool.
            # The resume path handles everything from loading the approval map
            # through running the agent; this function then handles the result.
            _body_resume(lease, config, pool_map, principal, role_name, role_version)
            return

        with psycopg.connect(database_url("worker")) as conn:
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

            # AC-0325: read the run's accumulated event count BEFORE committing
            # step.started, so only prior-step events are counted.  Phase 1
            # approximates spend as `runs.next_seq` (total events for the run),
            # because no per-step token count is stored in this delivery.  The
            # ceiling pages (appends `step.spend.ceiling.reached`) rather than
            # aborting, and only after step.started commits so the page event
            # follows the step start in the log.
            seq_row = conn.execute(
                "SELECT next_seq FROM runs WHERE run_id = %s",
                (lease.run_id,),
            ).fetchone()
            _spend_ceiling_reached = (
                seq_row is not None and int(seq_row[0]) > config.per_run_token_ceiling
            )

            # AC-0327: requested→running on step.started, committed together.
            # The inner conn.transaction() inside append_step_event creates a
            # SAVEPOINT under this outer transaction; both commit atomically
            # when the outer with-block exits.
            with conn.transaction():
                conn.execute(
                    "UPDATE runs SET state = 'running'"
                    " WHERE run_id = %s AND state = 'requested'",
                    (lease.run_id,),
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
        # Append the ceiling page event (if flagged) now that step.started has
        # committed, so the page event follows step.started in the log.
        if _spend_ceiling_reached:
            log.info(
                "executor: run %s exceeded the per-run spend ceiling "
                "(%d events); appending step.spend.ceiling.reached",
                lease.run_id,
                config.per_run_token_ceiling,
            )
            with psycopg.connect(database_url("worker")) as _cc:
                append_step_event(
                    _cc,
                    run_id=lease.run_id,
                    step_id=lease.step_id,
                    lease_epoch=lease.epoch,
                    type="step.spend.ceiling.reached",
                    principal=principal,
                    agent_role=role_name,
                )
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

        # AC-0302: offer the gated tool only when the pre-release check fails.
        # A clean role (no needs_approval flag) gets an empty toolset list, so
        # the agent never sees the approval tool. A flagged role gets one entry.
        # Entry 18 (adjudication): ValueError from a malformed model_settings
        # or non-bool needs_approval is a role-authoring error; record step.failed
        # and return rather than silently disabling the gate (fail-closed).
        try:
            prerelease_failed = check_prerelease_failed(loaded.role)
        except ValueError as exc:
            log.error(
                "executor: role configuration error for step %s: %s",
                lease.step_id,
                exc,
            )
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
            raise _StepBodyFailed("role configuration error") from exc
        approval_toolsets = offered_approval_gated_tools(prerelease_failed)

        # Run the agent. Any exception is caught and recorded as step.failed.
        # The finally block disarms the deadline timer whether the run succeeds,
        # suspends, or fails — so a late-firing timer cannot discard a completed
        # step (AC-0232).
        try:
            result = _run_compiled_agent(compiled, approval_toolsets, token)
        except Exception as exc:
            log.error("executor: agent run failed for step %s: %s", lease.step_id, exc)
            # Entry 12 (adjudication): only step.failed here; run stays in
            # 'running'. This path appends no terminal run event. AC-0327
            # enumerates two causes that do — AC-0321's cycle cap and AC-0330's
            # refused resume — so run.failed is not reserved for the refusal
            # path, which an earlier version of this comment claimed and which
            # stopped being true when T3 gave the cap its own append.
            # Entry 11 (adjudication): raise _StepBodyFailed so the pool
            # records outcome = "failed" rather than "completed" for a step
            # whose last event is step.failed.
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
            raise _StepBodyFailed("agent run failed") from exc
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
                # AC-0333: set awaiting_decision so the claim predicate excludes
                # this step until a decision commits. The step stays 'runnable'
                # so AC-0237's resume path works and nothing has to move it back.
                conn.execute(
                    """
                    UPDATE steps
                       SET state = 'runnable',
                           lease_expires_at = NULL,
                           owner = NULL,
                           awaiting_decision = true
                     WHERE step_id = %s
                       AND lease_epoch = %s
                       AND owner = %s
                    """,
                    (lease.step_id, lease.epoch, config.worker_id),
                )
                conn.commit()
            return

        # T5: For quarantined roles, validate the agent's output through the
        # context assembler before writing step.completed.  A refused value
        # never reaches any stored artifact (AC-0242): the assembler runs here
        # — outside the agent — so the parser, not the framework's schema
        # serializer, is the admitting component (AC-0255).  A valid output is
        # written as a content-addressed payload object *before* the fenced
        # append, honouring the crash-ordering requirement of r5 § 3.
        output_payload_ref: str | None = None
        if compiled.quarantined:
            refs = (
                result.output.references
                if isinstance(result.output, ReferenceSelection)
                else []
            )
            try:
                assemble_planning_context({"references": refs})
            except ContextAssemblyError as exc:
                log.error(
                    "executor: quarantine output refused for step %s: %s",
                    lease.step_id,
                    exc,
                )
                # Entry 12 (adjudication): only step.failed for quarantine
                # refusal; run stays in 'running'. This path appends no
                # terminal run event. AC-0327 enumerates two causes that do —
                # AC-0321's cycle cap and AC-0330's refused resume — and an
                # earlier version of this comment said the refusal was the only
                # one, which stopped being true when T3 gave the cap its own
                # append_run_terminal.
                # Entry 11 (adjudication): raise _StepBodyFailed so the pool
                # records outcome = "failed" rather than "completed".
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
                raise _StepBodyFailed("quarantine output refused") from exc
            # Crash ordering: write the payload object before the fenced
            # append that references it.  A crash between the two leaves an
            # unreferenced object rather than a dangling payload_ref.
            output_payload_ref = write_payload({"references": refs})

        with psycopg.connect(database_url("worker")) as conn:
            append_step_event(
                conn,
                run_id=lease.run_id,
                step_id=lease.step_id,
                lease_epoch=lease.epoch,
                type="step.completed",
                principal=principal,
                agent_role=role_name,
                payload_ref=output_payload_ref,
            )
            # AC-0327: running→completed on run.completed. Both step.completed
            # and run.completed are appended on the same connection, each in
            # its own internal transaction via the SECURITY DEFINER function.
            append_run_terminal(
                conn,
                run_id=lease.run_id,
                step_id=lease.step_id,
                lease_epoch=lease.epoch,
                type="run.completed",
                principal=principal,
                agent_role=role_name,
            )

    return body
