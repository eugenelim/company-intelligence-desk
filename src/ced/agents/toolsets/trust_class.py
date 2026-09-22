"""The innermost wrapped layer: parse an integration's result, fail closed.

`worker-runtime.md` r5 § 2 puts this layer innermost of the three so it parses
an integration's result *before* any layer above observes the return value. A
free-text result therefore cannot reach the attribution record or the agent:
the step-event layer above sees only what the parser admitted, and so does the
agent.

**The parser itself is T3's and is injected here, not written here.** This
spec's `Never do` refuses typed output standing in for the deterministic
parser, so the boundary has to be a parser the compiler wires in rather than a
serializer this layer trusts. `parse_result` is the named seam; T3 supplies
the callable from `ced.domain.quarantine` and may narrow the protocol below,
which is why `trust_class.py` is in that task's `Touches` as well as this
one's. Nothing here stubs a parser, because a stub would compete with the one
T3 lands; until it does, the compiler wires a parser that refuses whatever it
is handed, which is the fail-closed direction and not a parse.

**What this does not establish.** No tool body executes anywhere in this spec
— the decision point refuses every call until the successor's predicate
arrives — so `call_tool` below is unreached by contract rather than by
omission, and no test here observes a parse. Separately,
[ADR-0006](../../../../docs/adr/0006-four-r5-deviations-for-phase-1.md) D3
means no Phase 1 role can hold a `free-text` integration at all, so the
free-text case this layer exists for stays unexercised even after the
predicate arrives. That is the safe posture and it is deliberate; it also
means the quarantine criteria establish the admitted-types path only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic_ai import RunContext
from pydantic_ai.toolsets import ToolsetTool

from ced.adapters.framework_contract import WrapperToolset

__all__ = ["ResultParser", "TrustClassToolset"]


@runtime_checkable
class ResultParser(Protocol):
    """Turns a raw integration result into an admitted value, or refuses.

    Refusal is by raising. Returning the raw value on a parse failure would
    be the detection-based defence r8 rejects, so this layer has no
    fall-through: whatever the parser raises propagates unchanged.
    """

    def __call__(self, tool_name: str, result: Any) -> Any:
        """Return the admitted value, or raise if the result is not admissible."""


@dataclass
class TrustClassToolset(WrapperToolset[Any]):
    """Innermost wrapped layer. Nothing above it sees an unparsed result.

    A `dataclass`, because `WrapperToolset` is one and rebuilds this layer
    with `dataclasses.replace` in `for_run` and `for_run_step`; a plain
    subclass carrying an extra attribute raises `TypeError` there.
    """

    parse_result: ResultParser

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        """Delegate to the integration, then return only what the parser admits."""
        raw = await super().call_tool(name, tool_args, ctx, tool)
        return self.parse_result(name, raw)
