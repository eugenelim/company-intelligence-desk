"""Turning a role record into an agent, and refusing rather than half-building.

`role-configuration-seams.md` § 3 gives the seam and the sequence:
`compile_role(role, integrations, pool)` returns a `CompiledRole` carrying
`.agent`, `.stack` and `.limits`, and on any refusal it **raises rather than
returning**, so no caller ever holds a partially compiled agent.

**This is the only constructor of the agent and of its stack.** It builds the
four ratified layers, calls `check_stack_order` on what it built, constructs
the `Agent` around that one toolset, and calls `check_sole_toolset` on the
constructed agent. The two checks are different defects: order is AC-0202 and
reachability is AC-0201, and the second is invisible to the first because the
`Agent` carries its own `_AgentFunctionToolset` beside anything passed —
`tests/contract/test_agent_surface.py` pins that observation.

**Role class is derived, never declared** (§ 4): a role is quarantined exactly
when its `ceiling` is empty. The compiler applies the two consequences that
derivation leaves contentful — the zero retry budgets and the
`reference-selection` output type — and refuses a record that declares
anything disagreeing with them in either direction. It never *overrides* a
declared value, because a silent override makes the record and the agent
disagree.

**Retry budgets are not declarable** (§ 5): zero for a quarantined role, the
framework's default otherwise. There is no role field to read and none is read.

**What this module does not yet enforce.** The compile-time refusals over the
role record — the `free-text` binding, the `thinking` setting, the settings
and output-contract allowlists, the pool's model-id set, the limit comparison,
the pool-class check and ceiling binding resolution — land beside the guards
below in the same function. Where they are absent today, a malformed record
fails on the framework's own error rather than on a named refusal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from pydantic import BaseModel
from pydantic_ai.toolsets import AbstractToolset

from ced.adapters.framework_contract import (
    Agent,
    AgentRetries,
    FunctionToolset,
    ModelSettings,
    UsageLimits,
)
from ced.agents.models import resolve_model
from ced.agents.toolsets import (
    PolicyDecisionPoint,
    StepEventToolset,
    TrustClassToolset,
    check_stack_order,
)

__all__ = [
    "OUTPUT_CONTRACTS",
    "QUARANTINED_OUTPUT_CONTRACT",
    "QUARANTINED_RETRIES",
    "CompiledRole",
    "FindingSet",
    "ReferenceSelection",
    "RoleCompileError",
    "SoleToolsetError",
    "ToolBodyNotInstalled",
    "check_sole_toolset",
    "compile_role",
    "no_parser_installed",
    "unresolved_tool",
]


class RoleCompileError(Exception):
    """The role record cannot become an agent.

    Distinct from `RoleLoadError`, which is the stored record disagreeing with
    its own shape. This is the role disagreeing with the pool, with its own
    bindings, or with what its derived class requires.
    """


class SoleToolsetError(Exception):
    """A constructed agent can reach a tool that is not inside the stack.

    Separate from `StackOrderError`: a chain in the ratified order still says
    nothing about a tool reachable *beside* it, and a tool with no ceiling
    entry has no ceiling entry to violate.
    """


class ToolBodyNotInstalled(Exception):
    """A domain tool body was reached. Nothing in this spec may reach one."""


class ReferenceSelection(BaseModel):
    """The quarantined role's closed-vocabulary result.

    Minimal on purpose. r5 § 7 requires a *closed-vocabulary* output type and
    names no fields; the reference vocabulary itself is minted outside the
    agent by `walking-skeleton-role-compilation`'s parser task, and the
    step path that carries a result anywhere is a successor spec's. What is
    load-bearing here is that the type is structured, so a malformed output
    fails validation instead of arriving as prose.
    """

    references: list[str]


class FindingSet(BaseModel):
    """The analysis role's typed result. Minimal for the same reason."""

    findings: list[str]


#: `role-configuration-seams.md` § 5's output-contract set, **a dict and not a
#: module** (§ 2). Two members: the quarantined role's closed-vocabulary type
#: and the analysis role's typed result. `walking-skeleton-step-lifecycle`'s
#: AC-0255 adds a third.
OUTPUT_CONTRACTS: Final[dict[str, type[BaseModel]]] = {
    "reference-selection": ReferenceSelection,
    "finding-set": FindingSet,
}

#: The one contract a quarantined role may declare, both ways round: an
#: empty-ceiling role declaring anything else is refused, and so is a
#: non-empty-ceiling role declaring this.
QUARANTINED_OUTPUT_CONTRACT: Final = "reference-selection"

#: r5 § 7 and § 5: both budgets zero for a quarantined role, so a validation
#: failure raises instead of re-prompting the model over attacker-authored
#: filing text. Not declarable — there is no role field for it.
QUARANTINED_RETRIES: Final[AgentRetries] = {"tools": 0, "output": 0}


def unresolved_tool(**arguments: Any) -> Any:
    """The body every domain tool is bound to in this spec. It never runs.

    Phase 1 reads no `adapter_ref` — `role-configuration-seams.md` § 2 adds
    that column nullable and unread — so no tool resolves to a real adapter
    here, and the decision point above refuses every call before any body is
    reached. A body that raises is what keeps "no tool body executes" a
    property of the runtime rather than of what nobody happened to call.

    A module-level callable, not a closure: the framework infers a
    context parameter from the signature, and a closure trips that inference.
    """
    raise ToolBodyNotInstalled(
        f"no tool body is installed in this spec; called with {sorted(arguments)}"
    )


def no_parser_installed(tool_name: str, result: Any) -> Any:
    """Stands where the deterministic parser will be wired, and refuses.

    The trust-class layer parses an integration's result before any layer
    above sees it. No integration returns a result in this spec, so there is
    nothing to parse; refusing is the fail-closed direction, and returning the
    raw value would be the detection-based defence r8 rejects.
    """
    raise ToolBodyNotInstalled(
        f"no result parser is installed in this spec; {tool_name!r} returned a result"
    )


@dataclass(frozen=True)
class CompiledRole:
    """One compiled agent and the facts a caller needs beside it.

    `.limits` exists because the framework takes `usage_limits` **per call,
    not per agent** — the pinned 2.45.0's `Agent.__init__` has no such
    parameter, verified against the installed package. Without a named carrier
    a test that passes limits itself passes while production bounds nothing;
    the step executor passes `compiled.limits` to `Agent.run`.

    `role_name`, `version`, `ceiling` and `quarantined` are here for the
    inspectability this spec carries: a compiled agent's role version, ceiling
    and stack are readable from the constructed object rather than inferred
    from configuration.
    """

    agent: Agent[None, Any]
    stack: AbstractToolset[Any]
    limits: UsageLimits
    role_name: str
    version: int
    ceiling: tuple[Mapping[str, Any], ...]
    quarantined: bool


def check_sole_toolset(agent: Agent[Any, Any], stack: AbstractToolset[Any]) -> None:
    """Raise unless `stack` is the only place a tool can be reached from.

    r5 § 2 R5's first two invariants: exactly one toolset and it is the
    decision point, and no decorator tools. The `Agent` always carries its own
    `_AgentFunctionToolset` — `tests/contract/test_agent_surface.py` pins that
    — so the property is not "one toolset" but "one toolset plus a framework
    toolset holding nothing".
    """
    if not isinstance(stack, PolicyDecisionPoint):
        raise SoleToolsetError(
            f"the agent's toolset is a {type(stack).__name__}, not the decision point"
        )

    siblings = [toolset for toolset in agent.toolsets if toolset is not stack]
    if len(siblings) != 1:
        raise SoleToolsetError(
            f"the agent carries {len(siblings)} toolset(s) beside the stack; "
            "exactly one is expected, the framework's own"
        )

    framework_toolset = siblings[0]
    decorated = sorted(getattr(framework_toolset, "tools", {}))
    if decorated:
        raise SoleToolsetError(
            f"tool(s) {decorated} are registered on the agent itself rather than "
            "inside the stack, so no ceiling entry governs them"
        )


def _tool_names(ceiling: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """The tool names a ceiling binds, in ceiling order and without repeats."""
    names = [str(entry["tool_name"]) for entry in ceiling]
    return tuple(dict.fromkeys(names))


def _domain_toolset(ceiling: Sequence[Mapping[str, Any]]) -> FunctionToolset[None]:
    """The framework's innermost layer, holding one entry per bound tool."""
    toolset = FunctionToolset[None]()
    for name in _tool_names(ceiling):
        toolset.add_function(unresolved_tool, name=name)
    return toolset


def _resolved_limits(
    role_limits: Mapping[str, Any], pool_limits: Mapping[str, Any]
) -> UsageLimits:
    """Merge the pool's defaults with the role's declared values.

    A key the role omits inherits the pool's. The comparison that refuses a
    role value *wider* than the pool's is AC-0206's and is not applied here
    yet, so today a wider value is simply carried.
    """
    merged: dict[str, Any] = {**pool_limits, **role_limits}
    return UsageLimits(**merged)


def compile_role(
    role: Mapping[str, Any],
    integrations: Sequence[Mapping[str, Any]],
    pool: Mapping[str, Any],
) -> CompiledRole:
    """Compile one role record into an agent, or raise.

    `pool` is the deployment-time configuration read by key — `PoolConfig`'s
    fields as a plain mapping — so the agent layer never imports the worker.

    **Three arguments, which is the seam the ratified design names.** The
    event layer is left unbound: its `StepContext` comes from the step path,
    which `walking-skeleton-step-lifecycle` builds and no caller here has, so
    a parameter for it would be one nothing in this spec supplies. An unbound
    event layer refuses a call rather than appending nowhere, and the spec
    that builds the step path adds the argument with the criterion reading
    it.

    `integrations` is the pinned registry rows the loader returned. They are
    read by the compile-time binding guards; with those not yet installed,
    the argument is carried and not inspected.
    """
    role_name = str(role["role_name"])
    version = int(role["version"])
    ceiling = tuple(role["ceiling"])
    quarantined = not ceiling

    output_schema_ref = str(role["output_schema_ref"])
    _check_derived_class(role_name, version, quarantined, output_schema_ref)
    output_type = OUTPUT_CONTRACTS[output_schema_ref]

    model_settings = role["model_settings"]
    stack = PolicyDecisionPoint(
        StepEventToolset(TrustClassToolset(_domain_toolset(ceiling), no_parser_installed))
    )
    check_stack_order(stack)

    agent: Agent[None, Any] = Agent(
        model=resolve_model(str(model_settings["model_id"]), pool),
        output_type=output_type,
        toolsets=[stack],
        retries=QUARANTINED_RETRIES if quarantined else None,
        model_settings=cast(ModelSettings, dict(model_settings.get("settings", {}))),
        name=role_name,
    )
    check_sole_toolset(agent, stack)

    return CompiledRole(
        agent=agent,
        stack=stack,
        limits=_resolved_limits(
            model_settings.get("limits", {}), pool.get("default_limits", {})
        ),
        role_name=role_name,
        version=version,
        ceiling=ceiling,
        quarantined=quarantined,
    )


def _check_derived_class(
    role_name: str, version: int, quarantined: bool, output_schema_ref: str
) -> None:
    """Refuse a record whose declared output contract contradicts its class.

    Guarded in both directions. An empty-ceiling role declaring anything other
    than `reference-selection` is refused rather than overridden, and a role
    declaring `reference-selection` with a non-empty ceiling is refused too —
    otherwise one ceiling entry silently promotes a quarantined role to a
    planning role and restores the retry budgets the zero ones exist to hold
    over attacker-authored text.
    """
    label = f"role {role_name!r} version {version}"
    if quarantined and output_schema_ref != QUARANTINED_OUTPUT_CONTRACT:
        raise RoleCompileError(
            f"{label} has an empty ceiling, so it is quarantined and its output "
            f"contract must be {QUARANTINED_OUTPUT_CONTRACT!r}; it declares "
            f"{output_schema_ref!r}"
        )
    if not quarantined and output_schema_ref == QUARANTINED_OUTPUT_CONTRACT:
        raise RoleCompileError(
            f"{label} declares the quarantined output contract "
            f"{QUARANTINED_OUTPUT_CONTRACT!r} but binds a non-empty ceiling, "
            f"so it is not quarantined"
        )
