"""The innermost wrapped layer: parse an integration's result, fail closed.

`worker-runtime.md` r5 § 2 puts this layer innermost of the three so it parses
an integration's result *before* any layer above observes the return value. A
free-text result therefore cannot reach the attribution record or the agent:
the step-event layer above sees only what the parser admitted, and so does the
agent.

**The parser is injected here, not written here.** This spec's `Never do`
refuses typed output standing in for the deterministic parser, so the
boundary has to be a parser the compiler wires in rather than a serializer
this layer trusts. `parse_result` is the named seam, and what the compiler
now wires into it is
`ced.domain.quarantine.parser.parse_integration_result` — the real boundary,
which narrows `admit(value, candidates)` to the two-argument protocol below
and passes no candidate set. That is the fail-closed direction and not an
omission: an integration result is not the minting pipeline's output, so a
reference arriving through one was minted by nobody and is refused.

**What this does not establish.** No tool body executes anywhere in this spec
— the decision point refuses every call until the successor's predicate
arrives — so `call_tool` below is unreached by contract rather than by
omission, and no test observes a parse made *through this layer*. What is
asserted is the wiring and the parser either side of it: one check walks the
compiled stack and holds that `parse_result` **is**
`parse_integration_result`, and the quarantine suite decides that function's
refusing and admitting directions by calling it directly. Separately,
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
