"""The outermost toolset layer: the policy decision point, and its refusal type.

`worker-runtime.md` r5 § 2 *The toolset stack, innermost to outermost* puts
this layer outermost so nothing below it ever observes an unauthorized call,
and calls that order a security property rather than a style choice.

**`may_act` is a conjunction, and both halves are here.** A call is admitted
only when the acting role's ceiling admits it *and* the initiating user's
entitlements do. Two resolvers rather than one merged ceiling, because the two
are read from different tables at different times: the role's at compile time,
the principal's when the step binds.

**The decision is recorded before anything happens.** r5 § 4's gate block makes
`may_act(call)` "recorded as the `policy.decision`" at call time on both the
admit and the refuse path, so the append comes before the tool body runs and
before the refusal is raised. That ordering is the attributability claim, and it
is why an append that fails is a denial rather than a retry.

**One failure path, and the database is the discriminator.** On *any*
`policy.decision` append failure the decision point attempts a fenced step
termination and then raises. Where the fence was actually held the write takes
and the step terminates; where the worker was genuinely evicted the write matches
zero rows, the step stays with its new owner carrying no terminal state, and the
eviction is an abandon. Branching on the exception type cannot do this: an
injected serialization failure with the lease live and a real takeover both
surface as `Fenced`, so a branch would abandon exactly where the ratified
direction is to terminate.

**The denial handler is narrow by type, not by position.** The only thing inside
the `except ContainmentUndecidable` is the predicate call. A handler wrapped
around the delegation below would report a clean refusal for a genuine defect
raised inside a tool body, which is the case that makes a denial catchable
without swallowing bugs.

**Neither identity comes from the call.** The acting role and the initiating
principal are read from the claimed step and its run, and reach this layer on
the `StepContext`. `append_policy_decision` takes both as caller-supplied
parameters, so the seam is caller-trusting by construction and this is the
caller where that can be closed — an implementation reading either from a tool
argument or from model-authored content would let the agent select the
entitlements ceiling it is judged against.

**What this does not establish.** Nothing here binds `principal` to an
authenticated subject. `spec.md` § Follow-ons records that the trust root is the
ingress, that r7 puts OIDC there, and that this spec does not build it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic_ai import RunContext
from pydantic_ai.toolsets import ToolsetTool

from ced.adapters.framework_contract import WrapperToolset
from ced.adapters.postgres.event_log import append_policy_decision, terminate_step
from ced.agents.toolsets.step_events import StepContext
from ced.domain.containment.errors import ContainmentUndecidable, for_the_record

__all__ = [
    "CeilingResolver",
    "NoCeilingEntries",
    "PolicyDecisionNotRecorded",
    "PolicyDecisionPoint",
    "ToolCallDenied",
]


class ToolCallDenied(Exception):
    """The declared refusal type. A denial is terminal.

    Deliberately **not** `ModelRetry` and not a subclass of it, and
    `walking-skeleton-role-compilation`'s AC-0234 pins both directions. A denial
    delivered as a retryable hint turns the authorization boundary into a
    negotiation the model keeps attempting, with no visible failure.

    Derived from `Exception` and not from a broader base so that
    `except ToolCallDenied` around a call catches a denial and not a programming
    error raised inside the tool body.
    """


class PolicyDecisionNotRecorded(Exception):
    """The decision could not be committed, so the call does not proceed.

    A sibling of `ToolCallDenied` rather than a subclass: a caller catching a
    denial is handling a decision the boundary made, and this is the boundary
    failing to record one. The two want different handling — the first is an
    answer, the second is a step that is over.

    Raised after the fenced termination has been attempted. The tool body is
    unreachable from here by construction, because this raise precedes the
    delegation.
    """


@runtime_checkable
class CeilingResolver(Protocol):
    """Answers which ceiling entries admit a named tool call.

    An empty result denies. `ced.agents.ceilings.CompiledCeiling` is the
    implementation that reads a stored ceiling and evaluates the per-argument
    value constraints; the entry type stays opaque here so this layer holds no
    opinion about the fragment's shape.

    An implementation may raise `ContainmentUndecidable` for a call the fragment
    cannot decide. That is a denial here, recorded like any other.
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

    The default on both resolvers, and a resolver rather than a guard clause so
    that the failure direction survives someone editing the decision point.
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
    """Outermost layer. Records every decision, and admits only what both halves do.

    A `dataclass`, because `WrapperToolset` is one and its `for_run` and
    `for_run_step` rebuild the layer with `dataclasses.replace`; a plain
    subclass carrying extra attributes raises `TypeError` there. That is also
    how the step path binds `step` and `entitlements` onto a compiled stack.

    Both resolvers default to `NoCeilingEntries`, so a caller that forgets to
    supply one fails closed rather than open, and `step` defaults to `None`, so
    an unbound decision point refuses rather than appending nowhere.
    """

    resolver: CeilingResolver = field(default_factory=NoCeilingEntries)
    entitlements: CeilingResolver = field(default_factory=NoCeilingEntries)
    step: StepContext | None = None

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        """Decide, record, then admit or refuse. In that order, always."""
        step = self.step
        if step is None:
            # An admitted call commits a `policy.decision` first, so a decision
            # point with nowhere to record one cannot admit anything. Refusing
            # here rather than appending nowhere is what keeps "every decided
            # call is recorded" true of the runtime and not of what nobody
            # happened to call.
            raise ToolCallDenied(
                f"tool {name!r} reached the decision point with no step context, so "
                "its decision cannot be recorded and the call cannot be admitted"
            )

        denial = self._decide(name, tool_args)
        self._record(step, name)
        if denial is not None:
            raise ToolCallDenied(denial)
        return await super().call_tool(name, tool_args, ctx, tool)

    def _decide(self, name: str, tool_args: dict[str, Any]) -> str | None:
        """Return the denial reason, or `None` when both halves admit.

        **The `try` covers the predicate call and nothing else.** That narrowness
        is the control: widen it around the delegation and a genuine defect
        inside a tool body reads as a clean refusal at the boundary.

        Short-circuiting is deliberate. A call the role's own ceiling refuses is
        denied without consulting the entitlements ceiling, because the
        conjunction is already false and reading the second half would answer a
        question nobody asked of it.
        """
        try:
            if not self.resolver.entries_admitting(name, tool_args):
                return (
                    f"no ceiling entry of the acting role admits tool {name!r} with "
                    f"the arguments supplied"
                )
            if not self.entitlements.entries_admitting(name, tool_args):
                return (
                    f"tool {name!r} falls inside the acting role's ceiling and outside "
                    "the initiating user's entitlements"
                )
        except ContainmentUndecidable as error:
            # The receiving half of the fragment's AC-0315 seam. An input the
            # fragment cannot decide is a denial and not a defect, which is why
            # the fragment raises a type of its own rather than a builtin.
            return (
                f"the containment fragment could not decide tool {name!r}: "
                f"{for_the_record(error)}"
            )
        return None

    def _record(self, step: StepContext, name: str) -> None:
        """Commit the `policy.decision`, or end the step and raise.

        Both identities come from `step`. Nothing in `tool_args` is read here,
        and there is no parameter through which a call could supply either.

        On failure the fenced termination is attempted and the outcome is not
        branched on — see this module's docstring for why the database is the
        discriminator. A termination that cannot itself be performed
        **propagates, chained onto the append failure that caused it**: the
        natural `try`/`except` around a cleanup is the shape that continues into
        the tool body, and continuing is the one outcome every criterion here
        forbids. What the propagation costs is that the step falls to
        lease-expiry reclaim rather than terminating promptly.
        """
        try:
            append_policy_decision(
                step.policy_connection,
                run_id=step.run_id,
                step_id=step.step_id,
                lease_epoch=step.lease_epoch,
                principal=step.principal,
                agent_role=step.agent_role,
            )
        except Exception as error:
            # Deliberately every exception, and it swallows none of them: the
            # raise below is chained from this one. Narrowing it to the database
            # errors we can name would let an unforeseen failure skip the
            # termination and leave a leased step with no decision recorded,
            # which is the state this whole path exists to prevent.
            terminate_step(
                step.connection,
                step_id=step.step_id,
                lease_epoch=step.lease_epoch,
            )
            raise PolicyDecisionNotRecorded(
                f"the policy decision for tool {name!r} on step {step.step_id} could "
                f"not be committed, so the call does not proceed: {error}"
            ) from error
