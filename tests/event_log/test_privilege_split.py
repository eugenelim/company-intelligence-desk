"""AC-0005 — the database refuses the reserved event type, not the application.

Every assertion here opens a *real* connection as the role under test, so the
refusal comes from Postgres. Spike P1 established this shape against the
spike's own schema; this asserts it against the schema this delivery ships,
which is the whole reason AC-0005 exists rather than being inherited.

Both halves matter. A split that also blocks the legitimate path proves
nothing — it is a build break wearing a security control's clothes.
"""

from __future__ import annotations

import psycopg
import pytest

from ced.adapters.postgres import event_log
from ced.domain.events import RESERVED_EVENT_TYPE

from .conftest import LeasedStep

pytestmark = pytest.mark.substrate


# ── What each role is refused ────────────────────────────────────────────────


def test_the_worker_path_refuses_the_reserved_type(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """AC-0005. The exception TYPE is asserted, not just that something raised.

    `insufficient_privilege` is the claim: a refusal arriving as a constraint
    violation or a generic error would mean the reserved type was rejected for
    some other reason and the split was never exercised.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
        event_log.append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=RESERVED_EVENT_TYPE,
            principal="worker-1",
        )

    # `session_user`, not `current_user`: inside a SECURITY DEFINER function
    # `current_user` is the definer, so an audit trail built on it would name
    # `ced_owner` for every caller. Spike P1 found this; this pins the fix.
    assert "app_worker" in str(caught.value)
    assert "ced_owner" not in str(caught.value)


def test_the_worker_cannot_reach_the_policy_function_at_all(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """The second refusal, and it is the one that makes the split a split.

    Refusing the type inside the worker's own function is not enough on its
    own: if the worker also held `EXECUTE` on the policy function it could
    simply call that instead. The grants are disjoint.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_policy_decision(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            principal="worker-1",
        )


def test_the_policy_role_cannot_reach_the_general_append_path(
    policy_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """Symmetry. The narrow role does not widen into the general one."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_step_event(
            policy_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type="step.started",
            principal="policy-writer",
        )


def test_the_api_role_cannot_write_a_step_event_or_a_decision(
    api_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """r7: "no role holds an unqualified `events` insert", `api` included.

    An internet-facing component able to write a policy decision would defeat
    the split entirely, so `api` is constrained by the same mechanism rather
    than trusted.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_step_event(
            api_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type="step.started",
            principal="api",
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_policy_decision(
            api_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            principal="api",
        )


def test_the_api_role_is_restricted_to_the_two_run_lifecycle_types(
    api_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """The run-lifecycle path is not a general-purpose insert either."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        event_log.append_run_event(
            api_conn,
            run_id=leased_step.run_id,
            type="run.completed",
            principal="api",
        )


@pytest.mark.parametrize("role", ["api", "worker", "policy"])
def test_no_role_holds_a_direct_insert_on_events(
    role: str, request: pytest.FixtureRequest, leased_step: LeasedStep
) -> None:
    """The functions are a boundary only because the table is closed.

    With direct DML in place the append functions would be a convention. This
    asserts the revoke, which is what makes every refusal above load-bearing.
    """
    conn: psycopg.Connection = request.getfixturevalue(f"{role}_conn")

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            "INSERT INTO events (run_id, seq, type, principal) VALUES (%s, 9999, %s, 'forged')",
            (leased_step.run_id, RESERVED_EVENT_TYPE),
        )


# ── What each role can still do ──────────────────────────────────────────────


def test_the_worker_can_append_its_own_step_event(
    worker_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    seq = event_log.append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type="step.started",
        principal="worker-1",
    )
    assert seq == 1


def test_the_policy_role_can_append_a_decision(
    policy_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """And it does so holding no table access whatsoever.

    The fence it needs is `fence_step`, owned by the `NOLOGIN` `ced_fence` and
    reached by `EXECUTE` alone — ADR-0004, which narrows r4 item 1's second
    option so the role the split distrusts cannot drop the control that
    constrains it.
    """
    seq = event_log.append_policy_decision(
        policy_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        principal="policy-writer",
    )
    assert seq == 1


def test_the_policy_role_holds_no_access_to_steps_at_all(
    policy_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    """r7 change 1's whole point: the narrow role gains no table access.

    The name and the reason both used to be wrong. They said "no access beyond
    `SELECT`" and attributed the refusal to the missing `UPDATE` that
    `SELECT ... FOR UPDATE` needs — a reading that required the role to *hold*
    `SELECT`. ADR-0005 D4 removed all of `app_policy`'s table reads, so the
    refusal below is now the plainer one: it holds nothing on `steps`, and the
    conclusion that the fence had to be a function rather than a grant follows
    a fortiori rather than from the lock's privilege requirement. The assertion
    itself never changed.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        policy_conn.execute(
            "SELECT 1 FROM steps WHERE step_id = %s FOR UPDATE",
            (leased_step.step_id,),
        )


def test_the_api_role_can_append_a_run_requested_event(
    api_conn: psycopg.Connection, leased_step: LeasedStep
) -> None:
    seq = event_log.append_run_event(
        api_conn,
        run_id=leased_step.run_id,
        type="run.requested",
        principal="operator",
    )
    assert seq == 1
