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

**The compile-time refusals over the role record all live in this one
function**, and each names what failed — the key, the value, the row or the
role — because an operator reading the failure is the point. They are the
`free-text` binding (AC-0203), the `thinking` setting (AC-0204), the limit
comparison (AC-0206), the settings allowlist (AC-0269), the output-contract
allowlist (AC-0267), the pool-class check (AC-0258) and ceiling binding
resolution (AC-0260). The pool's model-id set (AC-0251) is enforced one module
over, in `ced.agents.models`, which is where that set is read.

**Every one of them refuses on the return path, not at call time.** A role
that violates a guard never produces an agent, so there is no object a caller
could hold and invoke.

**`append_role_refusal` is the other half of that, and it lives here for a
layering reason rather than a thematic one.** § 3 makes the refusal an
operator-facing contract: the executor appends an event naming the stage that
refused and the role that failed, so a bad role file is distinguishable from a
runtime fault. The step executor that will call it is
`walking-skeleton-step-lifecycle`'s and does not exist yet, so the append has
to live beside one of the two stages it reports. This module is the only one
that can reach both refusal types without inverting a layer —
`RoleCompileError` comes from `ced.agents.models` and `RoleLoadError` from
`ced.adapters.postgres.roles`, and putting the mapping in `adapters/` would
make an adapter import `agents/`. It maps the raised type to the event type,
so which stage an event reports is decided by what was raised and never by
the caller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast
from uuid import UUID

import psycopg
from pydantic import BaseModel
from pydantic_ai.toolsets import AbstractToolset

from ced.adapters.framework_contract import (
    Agent,
    AgentRetries,
    FunctionToolset,
    ModelSettings,
    UsageLimits,
)
from ced.adapters.postgres.event_log import append_step_event
from ced.adapters.postgres.roles import RoleLoadError
from ced.agents.models import RoleCompileError, resolve_model
from ced.agents.toolsets import (
    PolicyDecisionPoint,
    StepEventToolset,
    TrustClassToolset,
    check_stack_order,
)
from ced.domain.events import ROLE_COMPILE_REFUSED, ROLE_LOAD_FAILED

__all__ = [
    "ADMITTED_SETTINGS",
    "COMPILED_THINKING",
    "DECLARABLE_LIMITS",
    "FREE_TEXT",
    "OUTPUT_CONTRACTS",
    "POOL_OWNED_LIMIT",
    "QUARANTINED_OUTPUT_CONTRACT",
    "QUARANTINED_RETRIES",
    "ROLE_REFUSAL_EVENT_TYPES",
    "ROLE_REFUSAL_TYPES",
    "CompiledRole",
    "FindingSet",
    "ReferenceSelection",
    "RoleCompileError",
    "SoleToolsetError",
    "ToolBodyNotInstalled",
    "append_role_refusal",
    "check_sole_toolset",
    "compile_role",
    "no_parser_installed",
    "unresolved_tool",
]


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

#: § 5's `settings` shape, applied as an allowlist rather than a denylist. On
#: the pinned 2.45.0 the framework's `ModelSettings` is a `total=False`
#: TypedDict of sixteen keys, `extra_headers` and `extra_body` among them, so
#: forwarding a role's `settings` unchecked would let role data set arbitrary
#: provider headers and request bodies — authority no ratified document
#: assigns it, reaching past the `Model` seam r8 relies on for portability.
ADMITTED_SETTINGS: Final = frozenset({"max_tokens", "temperature", "thinking"})

#: The one setting the compiler owns rather than reads, per § 5. It is set on
#: every compiled role and no other value is admitted: omitting the key would
#: leave `ThinkingLevel` unset and the provider's own default in force, which
#: may reason, so refusing only a truthy declaration would not give r5 § 4's
#: "`thinking=False` asserted at compile time".
COMPILED_THINKING: Final = False

#: § 5's four declarable limit keys — all integers, and all comparing against
#: the pool default. The three `UsageLimits` token and cost fields § 5 leaves
#: out are not declarable, so a role naming one is refused with every other
#: non-member.
DECLARABLE_LIMITS: Final = (
    "per_request_input_tokens_limit",
    "input_tokens_limit",
    "request_limit",
    "tool_calls_limit",
)

#: Pool-owned per § 5: the pool supplies it from `CED_POOL_DEFAULT_LIMITS` and
#: a role declaring it fails to compile. The name is written here as well as
#: at `ced.worker.pool.COUNT_TOKENS_KEY` because `agents/` does not import
#: `worker/` — that separation is why `compile_role` takes the pool as a plain
#: mapping at all.
POOL_OWNED_LIMIT: Final = "count_tokens_before_request"

#: The trust class r5 § 2 R2 refuses on any non-quarantined role. The closed
#: set this is one member of lives at `ced.adapters.postgres.roles`, where the
#: loader refuses every non-member; this is the one member the *compiler*
#: denies on top of that.
FREE_TEXT: Final = "free-text"

#: Which stage refused, keyed on the type that was raised rather than on an
#: argument. A caller that could choose the event type could file a compile
#: refusal as a load failure, or either as a runtime fault, which is exactly
#: the distinction AC-0261 exists to make readable.
#:
#: `RoleLoadError` is the stored record disagreeing with its ratified shape;
#: `RoleCompileError` is the role disagreeing with the pool or its own
#: bindings. Neither derives from the other, so the order here is
#: presentational.
ROLE_REFUSAL_EVENT_TYPES: Final[tuple[tuple[type[Exception], str], ...]] = (
    (RoleLoadError, ROLE_LOAD_FAILED),
    (RoleCompileError, ROLE_COMPILE_REFUSED),
)

#: The two event types the mapping above can produce, derived from it so a
#: reader — and a suite — never restates the pair.
ROLE_REFUSAL_TYPES: Final = frozenset(event for _, event in ROLE_REFUSAL_EVENT_TYPES)


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
    label: str, role_limits: Mapping[str, Any], pool_limits: Mapping[str, Any]
) -> UsageLimits:
    """Merge the pool's defaults with the role's declared values, or refuse.

    AC-0206's three clauses, in one place. A role value *wider* than the pool
    default fails the build rather than being clamped — ADR-0006 D4's strict
    reading, so the role file and the limit in force cannot disagree. A
    narrower value is carried as its own. A key the role omits inherits the
    pool's, and the merge is what makes that true of the **compiled** limits:
    dropping the key would leave the `UsageLimits` field unset, which 2.45.0
    treats as unlimited.

    Two keys are refused rather than compared. `count_tokens_before_request`
    is pool-owned, and a key outside § 5's four is not declarable at all —
    `cost_limit` among them, which would otherwise reach `UsageLimits`
    unexamined because the framework accepts it.
    """
    for key, value in role_limits.items():
        if key == POOL_OWNED_LIMIT:
            raise RoleCompileError(
                f"{label} declares {key!r}, which is pool-owned; the pool supplies "
                f"it and a role may not"
            )
        if key not in DECLARABLE_LIMITS:
            raise RoleCompileError(
                f"{label} declares limit {key!r}, which is outside the declarable "
                f"set {list(DECLARABLE_LIMITS)}"
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise RoleCompileError(
                f"{label} declares {key}={value!r}; all four declarable limits are integers"
            )
        default = pool_limits.get(key)
        if isinstance(default, int) and not isinstance(default, bool) and value > default:
            raise RoleCompileError(
                f"{label} declares {key}={value}, wider than the pool default of "
                f"{default}; a role may narrow and never widen"
            )

    merged: dict[str, Any] = {**pool_limits, **role_limits}
    return UsageLimits(**merged)


def _check_settings(label: str, settings: Mapping[str, Any]) -> None:
    """Refuse a `settings` key outside § 5's three, and any `thinking` value.

    AC-0269 and AC-0204's refusing half. The allowlist is the compiler's own
    and is narrower than the framework's `ModelSettings`, which is the point:
    a key the TypedDict accepts is exactly the case that distinguishes the two.
    """
    unknown = sorted(set(settings) - ADMITTED_SETTINGS)
    if unknown:
        raise RoleCompileError(
            f"{label} declares model setting(s) {unknown}, outside the admitted "
            f"set {sorted(ADMITTED_SETTINGS)}"
        )
    declared = settings.get("thinking", COMPILED_THINKING)
    if declared is not COMPILED_THINKING:
        raise RoleCompileError(
            f"{label} declares thinking={declared!r}; the compiler sets "
            f"thinking={COMPILED_THINKING!r} on every role and admits no other value"
        )


def _bound_integrations(
    label: str,
    pool_class: Any,
    ceiling: Sequence[Mapping[str, Any]],
    integrations: Sequence[Mapping[str, Any]],
) -> None:
    """Resolve every ceiling entry to a pinned registry row, and judge the row.

    Three refusals over the bindings, each naming the entry that failed:

    * AC-0260 — an entry naming an integration the compiler was not given, and
      an entry whose `tool_name` is absent from that row's `tools`.
    * AC-0203 — a `free-text` row on a non-quarantined role. Reached only for
      such a role by construction: a quarantined role's ceiling is empty, so
      this loop does not run for one. ADR-0006 D3 narrows the `free-text`
      exemption to unreachable in Phase 1, which bounds how often this fires
      and not whether it is right.
    * AC-0258 — a row that does not list the role's `pool_class`. An empty
      `pool_classes` means available to every class, so a role whose
      `pool_class` is absent matches those rows and no others.

    The rows are keyed on the pinned `(integration_name, integration_version)`
    pair, which is the only way a version is selected: there is no "current
    version" row to fall back on.
    """
    by_pin = {
        (record.get("integration_name"), record.get("version")): record
        for record in integrations
    }
    for entry in ceiling:
        pin = (entry.get("integration_name"), entry.get("integration_version"))
        record = by_pin.get(pin)
        if record is None:
            raise RoleCompileError(
                f"{label} binds integration {pin[0]!r} version {pin[1]!r}, which the "
                f"compiler was not given; the rows it holds are {sorted(map(repr, by_pin))}"
            )

        tools = record.get("tools") or ()
        tool_name = entry.get("tool_name")
        if tool_name not in tools:
            raise RoleCompileError(
                f"{label} binds tool {tool_name!r} on integration {pin[0]!r} version "
                f"{pin[1]!r}, whose tools are {sorted(tools)}"
            )

        trust_class = record.get("trust_class")
        if trust_class == FREE_TEXT:
            raise RoleCompileError(
                f"{label} has a non-empty ceiling, so it is not quarantined, and it "
                f"binds integration {pin[0]!r} version {pin[1]!r} whose trust_class "
                f"is {FREE_TEXT!r}"
            )

        pool_classes = record.get("pool_classes") or ()
        if pool_classes and pool_class not in pool_classes:
            raise RoleCompileError(
                f"{label} runs in pool class {pool_class!r}, which integration "
                f"{pin[0]!r} version {pin[1]!r} does not list; it is available to "
                f"{sorted(pool_classes)}"
            )


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

    `integrations` is the pinned registry rows the loader returned, and the
    binding guards read them: an entry resolving to no row here is AC-0260's
    compile failure, not a silently smaller toolset.
    """
    role_name = str(role["role_name"])
    version = int(role["version"])
    label = f"role {role_name!r} version {version}"
    ceiling = tuple(role["ceiling"])
    quarantined = not ceiling

    output_schema_ref = str(role["output_schema_ref"])
    # AC-0267. Membership first, so an unrecognised name is refused by the set
    # rather than by a `KeyError` from the lookup two lines down.
    if output_schema_ref not in OUTPUT_CONTRACTS:
        raise RoleCompileError(
            f"{label} declares output_schema_ref {output_schema_ref!r}, outside the "
            f"compiler's set {sorted(OUTPUT_CONTRACTS)}"
        )
    _check_derived_class(role_name, version, quarantined, output_schema_ref)
    output_type = OUTPUT_CONTRACTS[output_schema_ref]

    _bound_integrations(label, role.get("pool_class"), ceiling, integrations)

    model_settings = role["model_settings"]
    settings = dict(model_settings.get("settings", {}))
    _check_settings(label, settings)
    # § 5: set, never merely admitted. An omitted key leaves the provider's
    # default, so the compiled agent carries the value rather than the record.
    settings["thinking"] = COMPILED_THINKING
    limits = _resolved_limits(
        label, model_settings.get("limits", {}), pool.get("default_limits", {})
    )

    stack = PolicyDecisionPoint(
        StepEventToolset(TrustClassToolset(_domain_toolset(ceiling), no_parser_installed))
    )
    check_stack_order(stack)

    agent: Agent[None, Any] = Agent(
        model=resolve_model(str(model_settings["model_id"]), pool),
        output_type=output_type,
        toolsets=[stack],
        retries=QUARANTINED_RETRIES if quarantined else None,
        model_settings=cast(ModelSettings, settings),
        name=role_name,
    )
    check_sole_toolset(agent, stack)

    return CompiledRole(
        agent=agent,
        stack=stack,
        limits=limits,
        role_name=role_name,
        version=version,
        ceiling=ceiling,
        quarantined=quarantined,
    )


def append_role_refusal(
    conn: psycopg.Connection[Any],
    refusal: Exception,
    *,
    run_id: UUID,
    step_id: UUID,
    lease_epoch: int,
    principal: str,
    agent_role: str,
) -> int:
    """Record that a role never became an agent, and say at which stage.

    AC-0261. The event type comes from `refusal`'s own type, so the load
    stage and the compile stage are distinguishable by type and both are
    distinguishable from a runtime fault; `agent_role` names the role that
    failed, which is what the shipped envelope can carry. **Which guard
    refused is deliberately not recorded** — the envelope has no column for
    it and this spec writes no payload object.

    Goes through `append_step_event` because that is the only path admitting
    a step-scoped type: `append_run_event` accepts `run.requested` and
    `run.cancelled` alone. So the append is fenced on `lease_epoch` like
    every other worker write, which is right — a worker whose lease has moved
    on must not narrate a step it no longer owns.

    Raises `TypeError` on an exception it cannot classify rather than filing
    it under either stage. A refusal event for a failure that was neither a
    load nor a compile refusal would be a log that misleads, which is worse
    than one that is missing an entry.
    """
    for refusal_type, event_type in ROLE_REFUSAL_EVENT_TYPES:
        if isinstance(refusal, refusal_type):
            return append_step_event(
                conn,
                run_id=run_id,
                step_id=step_id,
                lease_epoch=lease_epoch,
                type=event_type,
                principal=principal,
                agent_role=agent_role,
            )
    raise TypeError(
        f"{type(refusal).__name__} is not a role refusal; "
        f"the stages this records are "
        f"{[t.__name__ for t, _ in ROLE_REFUSAL_EVENT_TYPES]}"
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
