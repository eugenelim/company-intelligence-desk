"""The observability layer: `tool.invoked` and `tool.completed`.

`worker-runtime.md` r5 § 2 places this layer second from the outside: below
the decision point, so it records only calls the boundary already admitted,
and above the trust-class layer, so `tool.completed` can record the parse
outcome and a rejected result is attributable rather than merely absent.

**The step context is injected, not discovered here.** The live connection and
the `lease_epoch` the append is fenced on belong to the step path, which
`walking-skeleton-step-lifecycle` owns and which no task in this spec builds.
They arrive as constructor parameters so that this layer stays a layer: it
derives the key and calls the two append functions that already exist, and it
is not an event-appending machine of its own.

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

__all__ = ["StepEventToolset"]


@dataclass
class StepEventToolset(WrapperToolset[Any]):
    """Records the invocation pair around a call, keyed for idempotency.

    A `dataclass`, because `WrapperToolset` is one and rebuilds this layer
    with `dataclasses.replace` in `for_run` and `for_run_step`; a plain
    subclass carrying extra attributes raises `TypeError` there.
    """

    connection: psycopg.Connection[Any]
    run_id: UUID
    step_id: UUID
    lease_epoch: int
    principal: str
    agent_role: str

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        """Append `tool.invoked`, delegate, then append `tool.completed`."""
        if ctx.tool_call_id is None:
            raise ValueError(
                f"tool {name!r} reached the step-event layer with no tool_call_id; "
                "the idempotency key cannot be derived without one"
            )
        key = derived_idempotency_key(self.run_id, self.step_id, ctx.tool_call_id)
        self._append(TOOL_INVOKED, key)
        result = await super().call_tool(name, tool_args, ctx, tool)
        self._append(TOOL_COMPLETED, key)
        return result

    def _append(self, type: str, idempotency_key: str) -> None:
        append_step_event(
            self.connection,
            run_id=self.run_id,
            step_id=self.step_id,
            lease_epoch=self.lease_epoch,
            type=type,
            principal=self.principal,
            agent_role=self.agent_role,
            idempotency_key=idempotency_key,
        )
