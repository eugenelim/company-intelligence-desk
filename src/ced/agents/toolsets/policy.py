"""The outermost toolset layer: the policy decision point, and its refusal type.

`worker-runtime.md` r5 § 2 *The toolset stack, innermost to outermost* puts
this layer outermost so nothing below it ever observes an unauthorized call,
and calls that order a security property rather than a style choice.

**This spec ships the position, not the predicate.** The containment predicate
arrives in `walking-skeleton-authority-containment`. In the interval the
decision point refuses every call, and the refusal is *by construction*: the
layer admits a call only when the resolver it holds returns an admitting
ceiling entry, and the resolver it holds by default has no entries at all.
There is no literal to invert and no branch to delete — installing the real
resolver is what changes the outcome, which is exactly the shape this spec's
`Never do` ("no decision point that admits by default") asks for.

**What this does not establish.** Because nothing admits, the admit path below
is unreachable in this spec; no tool body executes anywhere in it. That a
lookup *miss* denies once a real resolver exists is a different property and is
`walking-skeleton-authority-containment`'s AC-0235, which cannot be decided
here — there is no lookup to miss yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic_ai import RunContext
from pydantic_ai.toolsets import ToolsetTool

from ced.adapters.framework_contract import WrapperToolset

__all__ = [
    "CeilingResolver",
    "NoCeilingEntries",
    "PolicyDecisionPoint",
    "ToolCallDenied",
]


class ToolCallDenied(Exception):
    """The interval's declared refusal type. A denial is terminal.

    Deliberately **not** `ModelRetry` and not a subclass of it, and this
    spec's AC-0234 pins both directions. A denial delivered as a retryable
    hint turns the authorization boundary into a negotiation the model keeps
    attempting, with no visible failure. `walking-skeleton-authority-containment`'s
    AC-0208 asserts the complementary property once a real denial path exists
    — that catching this does not also catch a programming error — which is
    why it derives from `Exception` and not from a broader base.
    """


@runtime_checkable
class CeilingResolver(Protocol):
    """Answers which ceiling entries admit a named tool call.

    An empty result denies. The successor spec supplies the implementation
    that reads a compiled role's ceiling and evaluates the per-argument value
    constraints; the entry type is left opaque here on purpose, because
    naming it now would fix a shape that spec owns.
    """

    def entries_admitting(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> Sequence[object]:
        """Return the entries that admit this call, empty if none do."""


@dataclass(frozen=True)
class NoCeilingEntries:
    """A resolver holding no entries, so no call can be admitted through it.

    This is the interval's whole containment logic, and it is a resolver
    rather than a guard clause so that the failure direction survives someone
    editing the decision point.
    """

    def entries_admitting(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> Sequence[object]:
        """Always empty. There is nothing registered that could admit."""
        return ()


@dataclass
class PolicyDecisionPoint(WrapperToolset[Any]):
    """Outermost layer. Refuses a call no ceiling entry admits.

    A `dataclass`, because `WrapperToolset` is one and its `for_run` and
    `for_run_step` rebuild the layer with `dataclasses.replace`; a plain
    subclass carrying an extra attribute raises `TypeError` there.

    The resolver defaults to `NoCeilingEntries`, so a caller that forgets to
    supply one fails closed rather than open.
    """

    resolver: CeilingResolver = field(default_factory=NoCeilingEntries)

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        """Deny unless an entry admits. In this spec, always deny.

        The delegation below is unreachable while the resolver has no
        entries. It is present because the refusal must come from the
        resolver being empty and not from a hardcoded raise.
        """
        if not self.resolver.entries_admitting(name, tool_args):
            raise ToolCallDenied(
                f"no ceiling entry admits tool {name!r}; "
                "no containment predicate is installed, so nothing admits"
            )
        return await super().call_tool(name, tool_args, ctx, tool)
