"""A standalone entry point that resumes a suspended step, for AC-0227.

**This file exists to be run as a subprocess, never imported by a check.**
AC-0227 requires "a fresh agent in a separate process, sharing nothing with
the original run but those bytes". A same-process call cannot establish that:
the plan is explicit that it "would pass on in-memory state the design forbids
relying on", and an in-process check would hold whether or not the resume path
read its authority inputs from durable records.

Everything this process needs arrives as argv — identifiers that locate
durable records — plus the object-store key. It constructs its own pool
wiring, so no object built by the original run crosses the boundary.
"""

from __future__ import annotations

import sys
import uuid
from typing import Any

import psycopg
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ced.adapters.postgres.dsn import database_url
from ced.agents.compiler import ToolBodyNotInstalled
from ced.worker.persistence import resume_step
from ced.worker.pool import PoolConfig, claim_one

#: Matches the pool the suspending run used. Built here rather than passed in,
#: because a factory is not picklable and passing one would defeat the point.
_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 20000,
    "input_tokens_limit": 200000,
    "request_limit": 20,
    "tool_calls_limit": 40,
    "count_tokens_before_request": False,
}


def _call_the_domain_tool(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Issue one `fetch_filing` call on the resumed turn, then finish.

    The second turn returns the output tool's call, because the run has to end
    somewhere; what matters for the criteria is that the first turn reaches the
    decision point.
    """
    already = any(
        isinstance(part, ToolCallPart) and part.tool_name == "fetch_filing"
        for message in messages
        for part in getattr(message, "parts", [])
    )
    if not already:
        return ModelResponse(parts=[ToolCallPart("fetch_filing", {"ticker": "AAPL"})])
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"findings": []})])


def main(argv: list[str]) -> int:
    """Resume the step named by argv. Exit 0 on success, non-zero otherwise."""
    run_id, step_id, pool_class, role_name, role_version, payload_ref = argv

    pool_map: dict[str, Any] = {
        "default_limits": dict(_LIMITS),
        "allowed_model_ids": ("stub:counting",),
        "non_provider_model_ids": ("stub:counting",),
        # **A `FunctionModel`, not a `TestModel`, and the distinction is
        # load-bearing.** Measured on the pin: `TestModel` calls each tool on a
        # fresh run but issues no call at all when resumed from a history — it
        # goes straight to final output. A resumed model that calls nothing
        # leaves the decision point unconsulted and the log unchanged, which
        # proves nothing about the authority inputs this criterion is about.
        #
        # This model issues exactly one domain call on the resumed turn, so the
        # decision point evaluates it against the ceiling of the role version
        # the step was suspended under and the entitlements read fresh at
        # resume, and records what it decided.
        "model_factory": lambda _model_id: FunctionModel(_call_the_domain_tool),
    }

    # **This process claims the step itself, as a resuming worker does.**
    # Suspension released the lease precisely so another worker could take it,
    # and the fenced append proves *possession*, not knowledge of an epoch —
    # `fence_step` requires a live `lease_expires_at`, so an epoch handed over
    # from outside would go stale between processes. Claiming here removes
    # that window and matches the flow AC-0237 established.
    claimed = claim_one(
        psycopg.connect(database_url("worker")),
        PoolConfig(
            worker_id="t3-resume-runner",
            default_limits=dict(_LIMITS),
            allowed_model_ids=("stub:counting",),
            non_provider_model_ids=("stub:counting",),
            pool_class=pool_class,
        ),
    )
    if claimed is None or str(claimed.step_id) != step_id:
        print(f"expected to claim {step_id}, got {claimed}", file=sys.stderr)
        return 1

    # **`ToolBodyNotInstalled` is the admitted terminus, not a failure.** No
    # tool body executes in this spec by design — `unresolved_tool` raises so
    # that "no tool body executes" is a property of the runtime rather than of
    # what nobody happened to call. A resumed call the decision point *admits*
    # therefore ends here, having already recorded its decision, and treating
    # that as a failure would make the admitted case indistinguishable from a
    # refused one.
    try:
        _resume(run_id, step_id, payload_ref, role_name, role_version, pool_map, claimed)
    except ToolBodyNotInstalled:
        return 0
    return 0


def _resume(
    run_id: str,
    step_id: str,
    payload_ref: str,
    role_name: str,
    role_version: str,
    pool_map: dict[str, Any],
    claimed: Any,
) -> None:
    """The resume itself, so the caller can name the admitted terminus."""
    resume_step(
        run_id=uuid.UUID(run_id),
        step_id=uuid.UUID(step_id),
        lease_epoch=claimed.epoch,
        role_name=role_name,
        role_version=int(role_version),
        payload_ref=payload_ref,
        pool_map=pool_map,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
