"""Persistence: load a suspended step's history and resume it from bytes alone.

The two exported functions are the entry points T3's tests use.
``load_suspension_payload`` reads the object store; ``resume_step`` is the
full resume sequence that AC-0227 drives from a separate process.

**No authority input crosses the suspension boundary in the persisted bytes.**
Role version, initiating principal, integration-registry versions and
entitlements are all read from durable database records at resume time, not
from the serialised history.  The history carries only the model conversation.
This matches the § Design decisions entry in ``plan.md`` and makes the
persisted history non-authoritative by construction.

**``pydantic_ai`` is not imported here.** The serialisation/deserialisation
and the approval-apply call live in ``adapters/objectstore/history.py``, which
is the allowed import layer.  This module coordinates; it does not know what a
``ThinkingPart`` is.

**The step context is bound before running.** ``PolicyDecisionPoint`` and
``StepEventToolset`` both carry a ``step: StepContext | None`` field. The
compiler leaves them ``None``; the resume path sets them here so tool calls
are recorded and authorized against the fresh ceiling.

**Entitlements are looked up fresh at resume time (AC-0245, AC-0253).** The
principal comes from the run record, not from the history bytes; the
entitlements are looked up for that principal as they stand *now*, not as they
stood at suspension. This is how revocation bites through the entitlements
conjunct even though the ceiling is pinned to the suspended role version.
"""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID

import psycopg

from ced.adapters.framework_contract import DeferredToolRequests, FunctionToolset
from ced.adapters.objectstore.client import read_payload
from ced.adapters.objectstore.history import deserialise_history, run_with_approval
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import append_step_event, read_run_principal
from ced.adapters.postgres.roles import load_entitlements, load_role
from ced.agents.ceilings import compile_ceiling
from ced.agents.compiler import compile_role
from ced.agents.tools.approval import request_approval
from ced.agents.toolsets import PolicyDecisionPoint
from ced.agents.toolsets.step_events import StepContext, StepEventToolset

__all__ = ["load_suspension_payload", "resume_step"]


def load_suspension_payload(payload_ref: str) -> tuple[list[Any], list[str]]:
    """Load the history and pending approval call IDs from a suspension payload.

    Returns ``(messages, pending_call_ids)`` where ``messages`` is the
    deserialised conversation history and ``pending_call_ids`` is the list of
    ``tool_call_id`` values that were pending approval at suspension.
    """
    payload = read_payload(payload_ref)
    # The history is stored as a JSON list inside the outer dict; re-encode it
    # so ModelMessagesTypeAdapter can deserialise via its own type annotations.
    history_bytes = json.dumps(payload["history"]).encode()
    messages = deserialise_history(history_bytes)
    pending_call_ids = list(payload["pending_approval_call_ids"])
    return messages, pending_call_ids


def resume_step(
    *,
    run_id: UUID,
    step_id: UUID,
    lease_epoch: int,
    role_name: str,
    role_version: int,
    payload_ref: str,
    pool_map: dict[str, Any],
) -> Any:
    """Resume a suspended step from its persisted history.

    For AC-0227: called in a fresh process to demonstrate that no in-memory
    state from the original run is needed — only the ``payload_ref`` (the
    object-store key) and enough context to locate the durable records.

    **Authority inputs come from durable records, not from the bytes:**

    * ``role_version`` is the version the step was suspended under — read from
      the step record by the caller, not extracted from the history.
    * ``principal`` is read from the ``run.requested`` event (AC-0245).
    * Entitlements are looked up fresh for that principal (AC-0253).
    * The ceiling is compiled fresh from the role version record (AC-0241).
    * Integration-registry rows are those the role version's ceiling pins
      (AC-0248).
    """
    # Load history and pending approval calls from the object store.
    messages, pending_call_ids = load_suspension_payload(payload_ref)
    approval_map = {call_id: True for call_id in pending_call_ids}

    # Load the role from the database and compile it fresh.
    # AC-0229: fresh compilation means stale instruction text in the history
    # does not reach the model — the model receives the freshly compiled
    # system prompt from the role record.
    # AC-0248: load_role selects the registry rows that role_version's ceiling
    # pins, so the compilation resolves at exactly those versions.
    loaded = load_role(role_name, role_version)
    compiled = compile_role(loaded.role, loaded.integrations, pool_map)

    # Read the initiating principal from the run's durable record (AC-0245).
    with psycopg.connect(database_url("worker")) as conn:
        principal = read_run_principal(conn, run_id=run_id)

    # Look up entitlements fresh at resume time (AC-0245, AC-0253).
    # The principal comes from the run record, not from the history bytes.
    entitlements_raw = load_entitlements(principal)
    entitlements_resolver = compile_ceiling("entitlements", list(entitlements_raw))

    # **Record that the step was resumed, and by whom.** Until this existed
    # the resume path wrote nothing at all: a resumed step left the log
    # unchanged, so AC-0227's "applies the approval decision" had no
    # observable outcome and the authority inputs above could be sabotaged
    # without any check noticing. Inspectability is this architecture's
    # first-ranked quality attribute, and a step that resumes without trace
    # is the one shape that cannot be re-derived from the log.
    #
    # The principal written here is the one read from the **run record**
    # above, never one carried in the persisted bytes (AC-0245), and the
    # append is fenced on the lease epoch like every other step event.
    with psycopg.connect(database_url("worker")) as conn:
        append_step_event(
            conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=lease_epoch,
            type="step.resumed",
            principal=principal,
            agent_role=role_name,
        )

    # Open step-context connections for tool-call recording.  Held for the
    # duration of the model call, then closed in the finally block.
    worker_conn = psycopg.connect(database_url("worker"))
    policy_conn = psycopg.connect(database_url("policy"))
    try:
        step_ctx = StepContext(
            connection=worker_conn,
            policy_connection=policy_conn,
            run_id=run_id,
            step_id=step_id,
            lease_epoch=lease_epoch,
            principal=principal,
            agent_role=role_name,
        )

        # Bind the step context and entitlements to the compiled stack.
        # PolicyDecisionPoint.step — for recording policy decisions (AC-0241).
        # PolicyDecisionPoint.entitlements — for fresh entitlement lookup.
        # StepEventToolset.step — for recording tool.invoked / tool.completed.
        # None of these come from the history bytes; all come from durable
        # records read above.
        #
        # Casts are required because CompiledRole.stack is typed as the abstract
        # base; the compiler always builds a PolicyDecisionPoint wrapping a
        # StepEventToolset, and the cast is the documented layering contract.
        decision_point = cast(PolicyDecisionPoint, compiled.stack)
        decision_point.step = step_ctx
        cast(StepEventToolset, decision_point.wrapped).step = step_ctx
        decision_point.entitlements = entitlements_resolver  # AC-0241, AC-0253

        # Build the approval toolset (same as the initial run).
        approval_toolset: FunctionToolset[Any] = FunctionToolset()
        approval_toolset.add_function(request_approval, requires_approval=True)

        return run_with_approval(
            compiled.agent,
            history=messages,
            approval_map=approval_map,
            usage_limits=compiled.limits,
            output_type=[compiled.agent.output_type, DeferredToolRequests],
            approval_toolset=approval_toolset,
        )
    finally:
        worker_conn.close()
        policy_conn.close()
