"""AC-0211, AC-0212, AC-0239, AC-0243, AC-0252.

What happens when the decision cannot be recorded, and who the step belongs to
afterwards. The failure space is partitioned and every part has a ratified
direction: fence lost and attributable — abandon; fence held — terminate;
unattributable — treat as fence-held and terminate.

**There is one code path and the database is the discriminator**, which is why
these checks assert the *step row* and not which branch ran. An injected
serialization failure with the lease live and a real takeover both surface as
`Fenced`, so an implementation branching on the exception type would abandon
exactly where AC-0211 requires a terminate — and every assertion here would
still be about an outcome, so it would be caught.

**Every fault is patched in this process.** The shipped decision point carries
no disable switch and no injected-failure flag; that is the spec's first
`Never do`.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from ced.adapters.postgres.event_log import Fenced
from ced.adapters.postgres.event_log import (
    append_policy_decision as real_append_policy_decision,
)
from ced.agents.toolsets import PolicyDecisionNotRecorded, ToolCallDenied
from ced.agents.toolsets.step_events import DuplicateInvocation, StepContext
from tests.authorization.harness import (
    INSIDE,
    OUTSIDE,
    POLICY_MODULE,
    Claimed,
    a_prefix_ceiling,
    a_resolver,
    a_second_worker_claims,
    a_stack,
    decisions_for,
    drive,
    step_row,
)

pytestmark = pytest.mark.substrate


def _fails_with(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    """Make the decision append fail, leaving everything else real.

    Patched at the decision point's own import site, so the fault is in the call
    this layer makes and not in the append path the rest of the suite relies on.
    """

    def raises(*args: Any, **kwargs: Any) -> int:
        raise error

    monkeypatch.setattr(f"{POLICY_MODULE}.append_policy_decision", raises)


def test_a_failed_append_on_a_refused_call_terminates_the_step(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-0211 — the fence is still held, so the step terminates.

    A serialization failure and not a connection-level one, which is what makes
    this the *attributable* case with the lease live: the worker still owns the
    step, so the fenced termination matches and the step ends.
    """
    _fails_with(monkeypatch, Fenced("injected: serialization failure, lease still held"))
    stack, spy = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

    with pytest.raises(PolicyDecisionNotRecorded):
        drive(stack, {"cik": OUTSIDE})

    assert spy.calls == [], "the tool body ran after the decision failed to commit"
    assert decisions_for(owner_conn, claimed.run_id) == []
    state, _, epoch = step_row(owner_conn, claimed.step_id)
    assert state == "failed", "the step was not terminated"
    assert epoch == claimed.epoch, "the epoch moved, so this was not the fence-held case"


def test_a_failed_append_on_an_admitted_call_terminates_the_step(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-0243 — AC-0211's admit-path twin, and it has to be its own case.

    AC-0211 does not say the call under test is one the predicate admits.
    Forcing the append to fail on a call that was going to be refused anyway
    leaves the spy unmoved whatever the ordering, so commit-before-action can be
    unimplemented with AC-0211 green. Here the spy **would** move but for the
    ordering, which is what makes the assertion mean something.
    """
    resolver = a_resolver(a_prefix_ceiling())
    assert resolver.entries_admitting("fetch_filing", {"cik": INSIDE}), (
        "the call under test is not one the predicate admits, so this is AC-0211 again"
    )

    _fails_with(monkeypatch, Fenced("injected: serialization failure, lease still held"))
    stack, spy = a_stack(step, resolver=resolver)

    with pytest.raises(PolicyDecisionNotRecorded):
        drive(stack, {"cik": INSIDE})

    assert spy.calls == [], "the tool body ran before its decision was committed"
    assert decisions_for(owner_conn, claimed.run_id) == []
    assert step_row(owner_conn, claimed.step_id)[0] == "failed"


def test_an_unattributable_append_failure_is_treated_as_fence_held(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-0252 — a connection-level fault, where the worker cannot tell.

    The worker cannot know whether the transaction reached the fence at all, so
    there is no attribution to make. The ratified direction is to treat it as
    fence-held and attempt the termination, because abandoning a step we do own
    turns an unrecorded authorization decision into a lease-expiry reclaim and a
    silent re-execution.
    """
    _fails_with(monkeypatch, psycopg.OperationalError("injected: the connection dropped"))
    stack, spy = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

    with pytest.raises(PolicyDecisionNotRecorded):
        drive(stack, {"cik": INSIDE})

    assert spy.calls == []
    assert decisions_for(owner_conn, claimed.run_id) == []
    assert step_row(owner_conn, claimed.step_id)[0] == "failed", (
        "the worker did not attempt the termination AC-0211 and AC-0243 require"
    )


def test_an_unattributable_failure_after_a_real_eviction_leaves_the_true_owner_untouched(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-0252's second half — terminating a step we may not own is safe.

    That is the whole reason the unattributable direction is *terminate*: the
    termination is itself a fenced write, so where the worker had in fact been
    evicted the database refuses it. This drives exactly that — a real takeover
    first, then the unattributable failure — and asserts the new owner keeps the
    step.
    """
    second, taken = a_second_worker_claims(owner_conn, claimed)
    try:
        _fails_with(monkeypatch, psycopg.OperationalError("injected: the connection dropped"))
        stack, spy = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

        with pytest.raises(PolicyDecisionNotRecorded):
            drive(stack, {"cik": INSIDE})

        assert spy.calls == []
        assert decisions_for(owner_conn, claimed.run_id) == []
        state, owner, epoch = step_row(owner_conn, claimed.step_id)
        assert epoch == taken.epoch, "the evicted worker's write reached the step"
        assert owner == "authz-worker-b", "the step left its true owner"
        assert state == "leased", "the evicted worker terminated a step it no longer owned"
    finally:
        second.close()


def test_a_real_takeover_abandons_the_step_to_its_new_owner(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0239 — a real second worker holding a later epoch, and four outcomes.

    **Not an injected serialization failure**, and the criterion says why: a
    decision point that re-read the current epoch inside the append would pass
    an injected one and fail a real takeover. Here the fence is the shipped
    one, refusing the shipped append, because the epoch the caller holds is no
    longer the step's.

    The fourth outcome is the discriminator. A test that asserted only the
    refusal, the absent decision and the unmoved spy would pass on an
    implementation that terminated the step — and terminating a step another
    worker now owns is the failure this criterion exists to prevent.
    """
    second, taken = a_second_worker_claims(owner_conn, claimed)
    try:
        stack, spy = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

        with pytest.raises(PolicyDecisionNotRecorded):
            drive(stack, {"cik": INSIDE})

        assert spy.calls == [], "the tool body ran for an evicted worker"
        assert decisions_for(owner_conn, claimed.run_id) == [], (
            "the evicted worker committed a policy decision"
        )
        state, owner, epoch = step_row(owner_conn, claimed.step_id)
        assert (state, owner, epoch) == ("leased", "authz-worker-b", taken.epoch), (
            "the step did not stay with its new owner"
        )
    finally:
        second.close()


def test_the_append_receives_the_epoch_the_caller_held(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-0239's second, redundant guard on the same property.

    Without this assertion a decision point that re-read the current epoch from
    the database passes every other criterion in this task. The takeover check
    above catches it too; this one catches it directly and reds with a message
    that names the defect rather than a step row.
    """
    second, taken = a_second_worker_claims(owner_conn, claimed)
    try:
        seen: list[int] = []

        def record(*args: Any, **kwargs: Any) -> int:
            # The real function taken from the module that *defines* it, not
            # from the decision point's namespace: reading it back through the
            # patched name would call this wrapper again, and the recursion
            # would surface as a `PolicyDecisionNotRecorded` like any other
            # append failure — so the check would look like it passed.
            seen.append(int(kwargs["lease_epoch"]))
            return real_append_policy_decision(*args, **kwargs)

        monkeypatch.setattr(f"{POLICY_MODULE}.append_policy_decision", record)
        stack, _ = a_stack(step, resolver=a_resolver(a_prefix_ceiling()))

        with pytest.raises(PolicyDecisionNotRecorded):
            drive(stack, {"cik": INSIDE})

        assert seen == [claimed.epoch], (
            f"the append received epoch {seen}, not the {claimed.epoch} the caller held; "
            f"the step's current epoch is {taken.epoch}, so the epoch was re-read"
        )
    finally:
        second.close()


def test_a_duplicate_invocation_fails_loudly_and_the_body_runs_once(
    step: StepContext,
    claimed: Claimed,
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0212 — the derived key plus the partial unique index, as a decision.

    Both invocations carry the same `tool_call_id`, so they derive the same key
    and are one logical invocation. The second `tool.invoked` append is refused
    by the index, the step terminates as duplicate-detected, and the action
    executed at most once — which is the property the double-publication hazard
    needs.
    """
    resolver = a_resolver(a_prefix_ceiling())
    first, spy = a_stack(step, resolver=resolver)
    drive(first, {"cik": INSIDE}, tool_call_id="toolu_01duplicate")
    assert len(spy.calls) == 1, "the first invocation did not run"

    second, second_spy = a_stack(step, resolver=resolver, spy=spy)
    with pytest.raises(DuplicateInvocation) as raised:
        drive(second, {"cik": INSIDE}, tool_call_id="toolu_01duplicate")

    assert second_spy is spy
    assert len(spy.calls) == 1, (
        f"the action executed {len(spy.calls)} times across both attempts"
    )
    assert not isinstance(raised.value, ToolCallDenied), (
        "a duplicate is not an authorization denial and must not read as one"
    )
    assert step_row(owner_conn, claimed.step_id)[0] == "failed", (
        "the step did not terminate as duplicate-detected"
    )
