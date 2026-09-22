"""AC-0233 — with no predicate installed, the whole tool surface refuses.

The criterion has four clauses and each is carried by its own assertion here,
because three of them are satisfiable by an implementation that fails the
fourth:

1. **The enumeration is non-empty and covers the skeleton's named roles.** It
   is made by reading `agent_role` and `integration_registry` through
   `list_roles()` and `list_integration_tools()`, which is why this check is
   `substrate`: a list held in the suite is exactly what the criterion
   forbids, and an in-memory fixture would be one.
2. **No tool body executes**, observed with a spy rather than inferred. The
   spy **replaces** the body — see the note on `_a_spy_for_every_tool_body`
   below, which is the trap layer (d) recorded before this layer began.
3. **At least one pair reaches the decision point and is refused *there*,**
   distinctly from a pair refused earlier at resolution. Without that
   distinction an implementation in which every pair dies at resolution, with
   the decision point never wired, satisfies every other clause.
4. **It runs in the no-predicate configuration the criterion names.** Asserted
   on every compiled stack rather than assumed, so the check retires with that
   configuration: `walking-skeleton-authority-containment`'s T2 removes this
   file in the same task that installs the predicate.

**The two refusal sites are two different exception types, and that is the
observation.** A pair whose role binds the tool resolves it inside the stack
and the decision point refuses the call, raising `ToolCallDenied`. A pair
whose role does not bind the tool never resolves: the framework has no such
tool to dispatch to, so it re-prompts until the tool-retry budget is spent and
raises `UnexpectedModelBehavior`. The call never reaches the decision point,
which is precisely the earlier refusal the criterion asks to be told apart.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ced.adapters.postgres.roles import (
    IntegrationTool,
    RoleRef,
    list_integration_tools,
    list_roles,
    load_role,
)
from ced.agents import compiler
from ced.agents.compiler import CompiledRole, compile_role
from ced.agents.toolsets import NoCeilingEntries, PolicyDecisionPoint, ToolCallDenied
from tests.compiler.role_records import STUB_MODEL_ID, a_pool
from tests.fixtures.registry_seed import (
    SEED_PREFIX,
    ceiling_entry,
    insert_integration,
    insert_role,
    seeded,
)

pytestmark = pytest.mark.substrate

#: The skeleton the spec's Assumptions name: one coordinator, one quarantined
#: role, and one analysis role with a single registered tool. Seeded under the
#: shared prefix so `seeded` removes every row on the way out.
COORDINATOR = SEED_PREFIX + "coordinator"
QUARANTINE = SEED_PREFIX + "quarantine"
ANALYSIS = SEED_PREFIX + "analysis"
SKELETON_ROLES = frozenset({COORDINATOR, QUARANTINE, ANALYSIS})

INTEGRATION = SEED_PREFIX + "sec-filings"
COORDINATOR_TOOL = "list_filings"
ANALYSIS_TOOL = "fetch_filing"

#: Limits left empty so every role inherits the pool's, which is what keeps
#: the seeded rows compilable against `a_pool()` without restating its values.
INHERITS_THE_POOL: dict[str, Any] = {
    "model_id": STUB_MODEL_ID,
    "settings": {},
    "limits": {},
}

#: The two sites a call can be refused at. Named rather than spelled inline,
#: because telling them apart is the criterion's third clause.
DECISION_POINT = "decision point"
RESOLUTION = "resolution"


class _CallsOneTool(FunctionModel):
    """A model that asks for one named tool and nothing else.

    A `FunctionModel` rather than `TestModel`: `TestModel` chooses which tools
    to call, and this check needs the pair under test driven deliberately.
    """

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(self.tool_name, {})])


@pytest.fixture
def the_skeleton(owner_conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Seed the three roles and the one integration, then clean them up."""
    with seeded(owner_conn) as conn:
        insert_integration(
            conn,
            integration_name=INTEGRATION,
            version=1,
            trust_class="admitted-types",
            tools=[ANALYSIS_TOOL, COORDINATOR_TOOL],
        )
        insert_role(
            conn,
            role_name=COORDINATOR,
            ceiling=[ceiling_entry(INTEGRATION, 1, COORDINATOR_TOOL)],
            model_settings=INHERITS_THE_POOL,
            output_schema_ref="finding-set",
        )
        insert_role(
            conn,
            role_name=QUARANTINE,
            ceiling=[],
            model_settings=INHERITS_THE_POOL,
            output_schema_ref="reference-selection",
        )
        insert_role(
            conn,
            role_name=ANALYSIS,
            ceiling=[ceiling_entry(INTEGRATION, 1, ANALYSIS_TOOL)],
            model_settings=INHERITS_THE_POOL,
            output_schema_ref="finding-set",
        )
        conn.commit()
        yield conn


@pytest.fixture
def a_spy_for_every_tool_body(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the body every bound tool resolves to, and record each entry.

    **Replaces rather than wraps, and that is load-bearing.** Phase 1 reads no
    `adapter_ref`, so every bound tool resolves to `compiler.unresolved_tool`,
    which *raises*. A spy wrapping that body would never move its counter —
    the wrapped body raises first — so the check would report "no body ran"
    for a runtime in which every body ran and blew up. Replacing it means an
    entered body returns normally and the list grows, which is the only way
    "no tool body executed" is an observation rather than an inference.

    The compiler reads the module global at build time, so patching the
    attribute reaches every stack compiled afterwards.
    """
    entered: list[str] = []

    def spy(**arguments: Any) -> str:
        entered.append(",".join(sorted(arguments)))
        return "a tool body ran"

    monkeypatch.setattr(compiler, "unresolved_tool", spy)
    return entered


def _compile(reference: RoleRef, model: FunctionModel) -> CompiledRole:
    """Load one role through the real loader and compile it against `model`."""
    loaded = load_role(reference.role_name, reference.version)
    return compile_role(loaded.role, loaded.integrations, a_pool(model=model))


def _drive(compiled: CompiledRole) -> str:
    """Run the agent to its one tool call and report where it was refused."""
    try:
        asyncio.run(compiled.agent.run("go"))
    except ToolCallDenied:
        return DECISION_POINT
    except UnexpectedModelBehavior as exc:
        assert "exceeded max retries" in str(exc), str(exc)
        return RESOLUTION
    raise AssertionError("the call was admitted; nothing may admit in this configuration")


def _sites_over_the_whole_surface(
    roles: tuple[RoleRef, ...],
    tools: tuple[IntegrationTool, ...],
) -> dict[tuple[str, str], str]:
    """Drive one call for every role-and-tool pair, and record each site."""
    sites: dict[tuple[str, str], str] = {}
    for reference in roles:
        for tool in tools:
            compiled = _compile(reference, _CallsOneTool(tool.tool_name))
            # Clause 4, asserted per compiled stack rather than assumed: this
            # is the no-predicate configuration, and the resolver holding no
            # entries is what makes the refusal structural.
            assert isinstance(compiled.stack, PolicyDecisionPoint)
            assert isinstance(compiled.stack.resolver, NoCeilingEntries)
            sites[(reference.role_name, tool.tool_name)] = _drive(compiled)
    return sites


def test_the_enumeration_reads_the_tables_and_covers_the_named_roles(
    the_skeleton: psycopg.Connection,
) -> None:
    """Clause 1. The universe under test is the tables', not the suite's.

    Also pins the shape the spec's Assumptions give the skeleton — one
    coordinator, one quarantined role, one analysis role with a single
    registered tool — because "covers the skeleton's named roles" is a claim
    about what was enumerated and not only that something was.
    """
    roles = list_roles()
    tools = list_integration_tools()

    assert roles, "no role rows to enumerate; the criterion decides nothing"
    assert tools, "no registry tools to enumerate; the criterion decides nothing"
    assert {reference.role_name for reference in roles} >= SKELETON_ROLES

    analysis = load_role(ANALYSIS, 1)
    assert [entry["tool_name"] for entry in analysis.role["ceiling"]] == [ANALYSIS_TOOL]
    quarantined = load_role(QUARANTINE, 1)
    assert quarantined.role["ceiling"] == []


def test_no_tool_body_executes_anywhere_on_the_surface(
    the_skeleton: psycopg.Connection,
    a_spy_for_every_tool_body: list[str],
) -> None:
    """Clauses 1 and 2. Every pair is driven, and the spy never moves."""
    roles = list_roles()
    tools = list_integration_tools()

    sites = _sites_over_the_whole_surface(roles, tools)

    assert len(sites) == len(roles) * len(tools)
    assert a_spy_for_every_tool_body == [], "a tool body ran despite the refusal"


def test_at_least_one_pair_is_refused_at_the_decision_point(
    the_skeleton: psycopg.Connection,
    a_spy_for_every_tool_body: list[str],
) -> None:
    """Clause 3, and the one clause the spy alone cannot carry.

    A pair the role binds must die *at the decision point*, and a pair it does
    not bind must die earlier. Asserting both directions is what rules out an
    implementation where the decision point is never wired and every pair
    fails at resolution — that implementation passes every other clause.
    """
    sites = _sites_over_the_whole_surface(list_roles(), list_integration_tools())

    assert sites[(ANALYSIS, ANALYSIS_TOOL)] == DECISION_POINT
    assert sites[(COORDINATOR, COORDINATOR_TOOL)] == DECISION_POINT
    # The quarantined role binds nothing, so neither tool resolves for it.
    assert sites[(QUARANTINE, ANALYSIS_TOOL)] == RESOLUTION
    assert sites[(QUARANTINE, COORDINATOR_TOOL)] == RESOLUTION
    # A role that binds one tool does not reach the decision point for the
    # other, which is the same distinction inside a single non-quarantined
    # role rather than between two roles.
    assert sites[(ANALYSIS, COORDINATOR_TOOL)] == RESOLUTION

    assert DECISION_POINT in sites.values()
    assert RESOLUTION in sites.values()
    assert a_spy_for_every_tool_body == []


def test_the_refusal_names_the_tool_and_says_nothing_admits(
    the_skeleton: psycopg.Connection,
    a_spy_for_every_tool_body: list[str],
) -> None:
    """An operator reading the failure has to be able to tell which call died.

    Kept here as well as on the hand-built stack in
    `test_decision_point_refuses.py`, because this is the first place the
    message is read off a stack the *compiler* built from a stored role.
    """
    compiled = _compile(RoleRef(ANALYSIS, 1), _CallsOneTool(ANALYSIS_TOOL))

    with pytest.raises(ToolCallDenied) as raised:
        asyncio.run(compiled.agent.run("go"))

    assert ANALYSIS_TOOL in str(raised.value)
    assert "no containment predicate is installed" in str(raised.value)
    assert a_spy_for_every_tool_body == []


def test_the_spy_would_notice_a_body_that_ran(
    the_skeleton: psycopg.Connection,
    a_spy_for_every_tool_body: list[str],
) -> None:
    """The control for clause 2. A spy nothing can move proves nothing.

    Calling the replaced body directly shows the list grows when a body runs,
    so the empty list above is a measurement rather than a property of the
    fixture. This reaches the patched callable, not the stack: nothing in this
    spec may drive a body through the stack, and the point is the spy.
    """
    spy: Callable[..., Any] = compiler.unresolved_tool

    assert spy(cik="0000000a") == "a tool body ran"
    assert a_spy_for_every_tool_body == ["cik"]
