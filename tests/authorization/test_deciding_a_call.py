"""AC-0207, AC-0208, AC-0209, AC-0210, AC-0235, AC-0236, AC-0318, AC-0319.

The decision itself: what the boundary admits, what it refuses, what it records,
and where the two identities in that record come from.

**AC-0318 is the only check in this file that asserts the spy moved**, and it is
load-bearing for every other one: a decision point that denied unconditionally
would satisfy all the refusals here and the suite would agree with it.
"""

from __future__ import annotations

import psycopg
import pytest

from ced.agents.ceilings import CompiledCeiling
from ced.agents.toolsets import NoCeilingEntries, ToolCallDenied
from ced.agents.toolsets.step_events import StepContext
from ced.domain.containment.errors import ContainmentUndecidable
from tests.authorization.harness import (
    AGENT_ROLE,
    IMPERSONATED_PRINCIPAL,
    IMPERSONATED_ROLE,
    INSIDE,
    OUTSIDE,
    PRINCIPAL,
    TOOL,
    UNCONSTRAINED_TOOL,
    Claimed,
    Spy,
    a_prefix_ceiling,
    a_resolver,
    a_stack,
    decisions_for,
    drive,
)

pytestmark = pytest.mark.substrate


def test_a_value_outside_the_ceiling_is_refused_and_the_body_does_not_run(
    step: StepContext, claimed: Claimed, owner_conn: psycopg.Connection
) -> None:
    """AC-0207 — well-typed, decided, and outside.

    The call is well-formed in every way the framework can see: the tool exists,
    the argument is a string, the entry constrains that argument. Only the
    *value* falls outside, which is the case a type system cannot reach and the
    ceiling exists for.
    """
    stack, spy = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

    with pytest.raises(ToolCallDenied) as raised:
        drive(stack, {"cik": OUTSIDE})

    assert TOOL in str(raised.value)
    assert spy.calls == [], "the tool body ran despite the refusal"


def test_a_tool_with_no_ceiling_entry_is_refused_with_the_real_predicate_installed(
    step: StepContext, claimed: Claimed
) -> None:
    """AC-0235 — a lookup that finds nothing denies rather than falling through.

    The permanent guard. Asserted with the **real** resolver holding a real
    entry for a different tool, because the thing that can regress is a miss
    becoming a fall-through once a genuine lookup exists — which is exactly the
    configuration `walking-skeleton-role-compilation`'s AC-0233 could not reach.
    """
    resolver = a_resolver(a_prefix_ceiling(tool=TOOL))
    assert TOOL in resolver.entries, "the resolver under test holds no entry at all"

    stack, spy = a_stack(step, resolver=resolver, tool_names=(TOOL, UNCONSTRAINED_TOOL))

    with pytest.raises(ToolCallDenied) as raised:
        drive(stack, {"cik": INSIDE}, tool_name=UNCONSTRAINED_TOOL)

    assert UNCONSTRAINED_TOOL in str(raised.value)
    assert spy.calls == [], "a tool with no ceiling entry ran"


def test_a_predicate_that_raises_denies_and_records_the_denial(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-0236 — an evaluation that raises is a denial, and a recorded one.

    The fault is patched **into the predicate**, in this process: the shipped
    decision point and the shipped fragment carry no switch, which is the spec's
    first `Never do`. Patching `evaluate` is what makes this the error path
    rather than a malformed argument the fragment handles normally.

    All three outcomes together, because an error path that denies without
    recording is the failure this criterion exists to catch.
    """

    def raises(entry: object, call: object) -> object:
        raise ContainmentUndecidable("injected: the fragment could not decide")

    monkeypatch.setattr("ced.agents.ceilings.evaluate", raises)
    stack, spy = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

    with pytest.raises(ToolCallDenied):
        drive(stack, {"cik": INSIDE})

    assert spy.calls == [], "the tool body ran after the predicate raised"
    recorded = decisions_for(owner_conn, claimed.run_id)
    assert len(recorded) == 1, "the denial was not recorded"
    assert recorded[0].agent_role == AGENT_ROLE
    assert recorded[0].principal == PRINCIPAL


def test_a_denial_is_catchable_without_also_catching_a_tool_body_bug(
    step: StepContext, claimed: Claimed
) -> None:
    """AC-0208 — the denial handler is narrow by type, not by position.

    Two halves, and the second is the one a bare "raises" assertion misses. A
    genuine defect raised inside an **admitted** call's body must reach the
    caller as itself: a handler wrapped around the delegation would report a
    clean refusal for a system that is broken.
    """
    resolver = a_resolver(a_prefix_ceiling())

    denied_stack, _ = a_stack(step, resolver=resolver)
    with pytest.raises(ToolCallDenied):
        drive(denied_stack, {"cik": OUTSIDE})

    bug = ZeroDivisionError("a genuine defect inside the tool body")
    buggy_stack, spy = a_stack(step, resolver=resolver, spy=Spy(raises=bug))
    with pytest.raises(ZeroDivisionError) as raised:
        drive(buggy_stack, {"cik": INSIDE})

    assert not isinstance(raised.value, ToolCallDenied), (
        "a tool-body defect was converted into a clean refusal"
    )
    assert spy.calls != [], "the body never ran, so this proves nothing about the handler"


def test_both_decisions_are_recorded_naming_the_role_and_the_principal(
    step: StepContext, claimed: Claimed, owner_conn: psycopg.Connection
) -> None:
    """AC-0209 — admitted or refused, the decision is committed either way.

    The admit path is the one no other criterion reaches: AC-0243 shows an
    admit-path append exists by forcing it to fail, and never that it commits
    when it succeeds.
    """
    resolver = a_resolver(a_prefix_ceiling())

    admitted_stack, spy = a_stack(step, resolver=resolver)
    drive(admitted_stack, {"cik": INSIDE})

    refused_stack, _ = a_stack(step, resolver=resolver)
    with pytest.raises(ToolCallDenied):
        drive(refused_stack, {"cik": OUTSIDE})

    recorded = decisions_for(owner_conn, claimed.run_id)
    assert len(recorded) == 2, "one of the two decisions was not recorded"
    for event in recorded:
        assert event.agent_role == AGENT_ROLE
        assert event.principal == PRINCIPAL
        assert event.step_id == claimed.step_id
    assert len(spy.calls) == 1


def test_the_decision_precedes_the_body(
    step: StepContext, claimed: Claimed, owner_conn: psycopg.Connection
) -> None:
    """AC-0209's ordering half, observed rather than inferred.

    The spy reads the committed log at the moment it runs. A decision point that
    appended *after* delegating would pass every other assertion in this file
    and fail here, which is the whole reason the ordering is ratified.
    """
    seen: list[int] = []
    spy = Spy()
    original = spy.body

    def body(**arguments: object) -> object:
        seen.append(len(decisions_for(owner_conn, claimed.run_id)))
        return original(**arguments)

    spy.body = body  # type: ignore[method-assign]
    stack, _ = a_stack(step, resolver=a_resolver(a_prefix_ceiling()), spy=spy)
    drive(stack, {"cik": INSIDE})

    assert seen == [1], "the tool body ran before its decision was committed"


def test_a_call_inside_the_ceiling_and_outside_the_entitlements_is_refused(
    step: StepContext, claimed: Claimed
) -> None:
    """AC-0210 — the conjunct no ceiling-only check reaches.

    Both halves are real compiled ceilings over the same argument: the role's
    admits the value, the initiating user's does not. A criterion covering only
    the ceiling would leave the other half unbuilt and green.
    """
    role_ceiling = a_resolver(a_prefix_ceiling(prefix="0003"))
    user_ceiling = a_resolver(a_prefix_ceiling(prefix="0009"))
    assert role_ceiling.entries_admitting(TOOL, {"cik": INSIDE}), (
        "the role's own ceiling refuses this call, so the conjunct is untested"
    )

    stack, spy = a_stack(step, resolver=role_ceiling, entitlements=user_ceiling)

    with pytest.raises(ToolCallDenied) as raised:
        drive(stack, {"cik": INSIDE})

    assert "entitlements" in str(raised.value)
    assert spy.calls == []


def test_the_entitlements_half_defaults_to_admitting_nothing() -> None:
    """The fail-closed direction on the half AC-0210 exercises.

    A decision point built without an entitlements resolver must refuse, for the
    same reason the ceiling half does: a caller that forgets to supply one fails
    closed. Read on the constructed object rather than through a call, so an
    edit that changed the default reds here even if nothing is driven.
    """
    from ced.adapters.framework_contract import FunctionToolset
    from ced.agents.toolsets import PolicyDecisionPoint

    point = PolicyDecisionPoint(FunctionToolset[object]())
    assert isinstance(point.entitlements, NoCeilingEntries)
    assert point.entitlements.entries_admitting(TOOL, {}) == ()
    assert point.step is None


def test_an_admitted_call_runs_the_body_exactly_once(
    step: StepContext, claimed: Claimed, owner_conn: psycopg.Connection
) -> None:
    """AC-0318 — the positive path, and the guard on the whole suite.

    Every other criterion here is a refusal or a failed append, so a decision
    point that refused everything would satisfy them all. This is the one that
    does not agree with it.
    """
    stack, spy = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

    result = drive(stack, {"cik": INSIDE})

    assert len(spy.calls) == 1, f"the body ran {len(spy.calls)} time(s), not once"
    assert spy.calls[0]["cik"] == INSIDE
    assert result.output == "done"
    assert len(decisions_for(owner_conn, claimed.run_id)) == 1


def test_neither_identity_is_read_from_the_call(
    step: StepContext, claimed: Claimed, owner_conn: psycopg.Connection
) -> None:
    """AC-0319 — the role and the principal come from the step and its run.

    The impersonating call supplies `agent_role` and `principal` as *tool
    arguments*, and the ceiling constrains all three arguments so the call is
    admitted rather than being refused for an unrelated reason. Asserting only
    that the event is well-formed would pass on an implementation reading either
    value from the call; asserting the recorded values equal the step's is what
    catches it.

    Driven twice, because the criterion says the decision is the *same*: once
    with benign values for those two arguments and once with the impersonating
    ones.
    """
    ceiling = a_prefix_ceiling(prefix="0003", arguments=("cik", "agent_role", "principal"))
    resolver = a_resolver(ceiling)

    benign_stack, benign_spy = a_stack(step, resolver=resolver)
    drive(benign_stack, {"cik": INSIDE, "agent_role": "0003a", "principal": "0003b"})

    impersonating_stack, impersonating_spy = a_stack(step, resolver=resolver)
    drive(
        impersonating_stack,
        {
            "cik": INSIDE,
            "agent_role": "0003" + IMPERSONATED_ROLE,
            "principal": "0003" + IMPERSONATED_PRINCIPAL,
        },
    )

    assert len(benign_spy.calls) == 1, "the control call was not admitted"
    assert len(impersonating_spy.calls) == 1, (
        "the impersonating call reached a different decision"
    )

    recorded = decisions_for(owner_conn, claimed.run_id)
    assert len(recorded) == 2
    for event in recorded:
        assert event.agent_role == AGENT_ROLE
        assert event.principal == PRINCIPAL
    assert IMPERSONATED_ROLE not in {event.agent_role for event in recorded}
    assert IMPERSONATED_PRINCIPAL not in {event.principal for event in recorded}


def test_an_unbound_decision_point_refuses(claimed: Claimed) -> None:
    """AC-0209's consequence, and what retired the case this task deletes.

    An admitted call commits a `policy.decision` first, so a decision point with
    nowhere to record one cannot admit anything — however admitting its resolver
    is. The retired check asserted the opposite, that the body runs.
    """
    resolver: CompiledCeiling = a_resolver(a_prefix_ceiling())
    stack, spy = a_stack(None, resolver=resolver)

    with pytest.raises(ToolCallDenied) as raised:
        drive(stack, {"cik": INSIDE})

    assert "no step context" in str(raised.value)
    assert spy.calls == []
