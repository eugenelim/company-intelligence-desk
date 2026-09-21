"""The observability layer: `tool.invoked` and `tool.completed`.

`worker-runtime.md` r5 § 2 places this layer second from the outside: below
the decision point, so it records only calls the boundary already admitted,
and above the trust-class layer, so `tool.completed` can record the parse
outcome and a rejected result is attributable rather than merely absent.

**The step context is injected, not discovered here.** The live connection and
the `lease_epoch` the append is fenced on belong to the step path, which
`walking-skeleton-step-lifecycle` owns and which no task in this spec builds.
They arrive together as `StepContext` so that this layer stays a layer: it
derives the key and calls the two append functions that already exist, and it
is not an event-appending machine of its own. Until that path exists the
context is `None` — the compiler still builds the layer, because the stack's
order is fixed, and an unbound layer refuses a call rather than appending
nowhere.

**What this does not establish.** Nothing in this spec executes a tool body —
the decision point refuses every call until the successor spec's predicate
arrives — so `call_tool` below is unreached by contract rather than by
omission. No test here observes an append. The first one runs under
`walking-skeleton-authority-containment`, against the step path
`walking-skeleton-step-lifecycle` builds.

**A second limit, recorded rather than designed around.** r5 wants
`tool.completed` to carry the parse outcome, so a result the trust-class layer
rejects is attributable. The shipped `events` envelope has no column for an
outcome and no payload object is written until
`walking-skeleton-step-lifecycle`, so a raising parse leaves `tool.invoked`
appended and no completion beside it. What a reader can tell today is that the
call started and did not finish, which is weaker than r5 asks for; the spec
that adds the payload object is where the outcome lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from pydantic_ai import RunContext
from pydantic_ai.toolsets import ToolsetTool

from ced.adapters.framework_contract import WrapperToolset
from ced.adapters.postgres.event_log import append_step_event
from ced.domain.events import TOOL_COMPLETED, TOOL_INVOKED, derived_idempotency_key

__all__ = ["StepContext", "StepEventToolset"]


@dataclass(frozen=True)
class StepContext:
    """What the step path injects: the live connection and the fenced identity.

    One object rather than six constructor parameters, because there is one
    state in which none of them is knowable — this spec compiles agents with
    no step path to supply them, and six independently-optional fields would
    make "unbound" a combination rather than a value.
    """

    connection: psycopg.Connection[Any]
    run_id: UUID
    step_id: UUID
    lease_epoch: int
    principal: str
    agent_role: str


@dataclass
class StepEventToolset(WrapperToolset[Any]):
    """Records the invocation pair around a call, keyed for idempotency.

    A `dataclass`, because `WrapperToolset` is one and rebuilds this layer
    with `dataclasses.replace` in `for_run` and `for_run_step`; a plain
    subclass carrying extra attributes raises `TypeError` there.

    `step` is `None` until the step path exists. The compiler builds this
    layer either way, because the stack's order is fixed and a missing layer
    is a different agent; an unbound layer refuses rather than appending
    nowhere, which is reachable only if the decision point above it ever
    admits a call.
    """

    step: StepContext | None = None

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        """Append `tool.invoked`, delegate, then append `tool.completed`."""
        if self.step is None:
            raise RuntimeError(
                f"tool {name!r} reached the step-event layer with no step context; "
                "the step path that injects one is not built in this spec"
            )
        if ctx.tool_call_id is None:
            raise ValueError(
                f"tool {name!r} reached the step-event layer with no tool_call_id; "
                "the idempotency key cannot be derived without one"
            )
        key = derived_idempotency_key(self.step.run_id, self.step.step_id, ctx.tool_call_id)
        self._append(self.step, TOOL_INVOKED, key)
        result = await super().call_tool(name, tool_args, ctx, tool)
        self._append(self.step, TOOL_COMPLETED, key)
        return result

    @staticmethod
    def _append(step: StepContext, type: str, idempotency_key: str) -> None:
        append_step_event(
            step.connection,
            run_id=step.run_id,
            step_id=step.step_id,
            lease_epoch=step.lease_epoch,
            type=type,
            principal=step.principal,
            agent_role=step.agent_role,
            idempotency_key=idempotency_key,
        )
