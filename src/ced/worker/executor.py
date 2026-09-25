"""Step body factory: compile the role, run the agent, record the outcome.

``make_step_body(config)`` returns a ``StepBody`` that carries the full
execution sequence for one claimed step:

 1. Read the initiating principal from the run's ``run.requested`` event.
 2. Load the role record from the database and compile it against the pool.
 3. Build the fourteen-field producer tuple (r8 § 5).
 4. Write the producer tuple as a content-addressed payload object — **before**
    the fenced append, per r5 § 3's crash-ordering requirement.
 5. Append ``step.started`` with the payload key as ``payload_ref``.
 6. Run the compiled agent.
 7. Append ``step.completed``, or ``step.failed`` on an agent error.

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
  ``ced.adapters.bedrock.payload``, which lives in ``adapters/``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Mapping, Sequence
from typing import Any

import psycopg

from ced.adapters.bedrock.model_factory import FETCH_ADAPTER_NAME, MODEL_ADAPTER_NAME
from ced.adapters.bedrock.payload import write_payload
from ced.adapters.framework_contract import PINNED_FRAMEWORK_VERSION
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import append_step_event, read_run_principal
from ced.adapters.postgres.roles import LoadedRole, RoleLoadError, load_role
from ced.agents.compiler import (
    CompiledRole,
    RoleCompileError,
    append_role_refusal,
    compile_role,
)
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


def make_step_body(config: PoolConfig) -> StepBody:
    """Return a step body that compiles and runs the leased step's role.

    The returned body opens its own database connections per the ``StepBody``
    contract (``(Lease, threading.Event) -> None``), which carries no
    connection argument.
    """
    pool_map = _pool_mapping(config)

    def body(lease: Lease, stop: threading.Event) -> None:
        """Execute one step: load, compile, record, run, complete."""
        del stop  # T1: no cancellation token yet; T2 adds step_deadline.
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

        # Run the agent. Any exception is caught and recorded as step.failed.
        try:
            compiled.agent.run_sync(
                "Return an empty list of references.",
                usage_limits=compiled.limits,
            )
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
