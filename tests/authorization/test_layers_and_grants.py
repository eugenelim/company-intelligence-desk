"""AC-0247 and AC-0249 — the layer below the boundary, and the grant beneath both.

Two criteria that are not about the decision itself but about what the decision
rests on: that the trust-class layer parses a tool **return** before anything
above it sees the value, and that no runtime identity can rewrite the
configuration it is constrained by.
"""

from __future__ import annotations

import psycopg
import pytest

from ced.agents.toolsets.step_events import StepContext
from ced.domain.events import TOOL_COMPLETED, TOOL_INVOKED
from ced.domain.quarantine.parser import AdmittedTypeRefused
from tests.authorization.harness import (
    FREE_TEXT_RETURN,
    INSIDE,
    Claimed,
    Spy,
    a_prefix_ceiling,
    a_resolver,
    a_stack,
    connect_as,
    drive,
    event_text,
    runtime_login_identities,
)

pytestmark = pytest.mark.substrate

#: The three objects no runtime identity may write. `entitlements` is the third
#: deliberately: r5 § 4's invariant names two, and AC-0249 exceeds it because
#: `entitlements` is the conjunct AC-0210 rests on — aligning back to r5's two
#: would remove half the escalation guard while looking like a correction.
CONFIGURATION_TABLES = ("agent_role", "integration_registry", "entitlements")

#: Every privilege Postgres can grant on a table that *writes* it, and what to
#: attempt for each. Derived from the grantable set rather than from the two
#: verbs an implementer happened to think of: the criterion quantifies over
#: "attempting to write", and a later `GRANT DELETE` on any of these three
#: would let a runtime identity remove the row that constrains it while a check
#: testing only INSERT and UPDATE stayed green. `TRUNCATE` is here for the same
#: reason and is the one that empties the table outright.
#:
#: `REFERENCES` and `TRIGGER` are grantable on a table and are deliberately
#: absent: neither changes a row, so neither is a write in the sense r5 § 4's
#: invariant means.
WRITE_PRIVILEGES: tuple[tuple[str, str], ...] = (
    ("INSERT", "INSERT INTO {table} DEFAULT VALUES"),
    ("UPDATE", "UPDATE {table} SET created_at = now()"),
    ("DELETE", "DELETE FROM {table}"),
    ("TRUNCATE", "TRUNCATE {table}"),
)


def write_statements(table: str) -> list[str]:
    """One statement per grantable write privilege, against `table`."""
    return [template.format(table=table) for _, template in WRITE_PRIVILEGES]


def test_a_free_text_return_never_reaches_the_attribution_record_or_the_agent(
    step: StepContext, claimed: Claimed, owner_conn: psycopg.Connection
) -> None:
    """AC-0247 — the layer parses a tool return, not just a retrieval.

    r5 § 2 makes this layer's innermost position a security property precisely
    because it must parse an integration's result *before* any layer above
    observes the return value. This is the first spec where a tool body runs at
    all, so it is the first place that position can be exercised rather than
    asserted.

    **Asserting only that the step fails would pass on a layer that parses too
    late.** So the check reads the committed events whole and holds that the
    text is in none of them: `tool.invoked` is there, because the call did
    start; `tool.completed` is not, because the parse raised before the layer
    above could write one.
    """
    stack, spy = a_stack(
        step,
        resolver=a_resolver(a_prefix_ceiling()),
        spy=Spy(returns=FREE_TEXT_RETURN),
    )

    with pytest.raises(AdmittedTypeRefused):
        drive(stack, {"cik": INSIDE})

    assert len(spy.calls) == 1, "the body never ran, so nothing was parsed"

    recorded = event_text(owner_conn, claimed.run_id)
    assert FREE_TEXT_RETURN not in recorded, (
        "the free-text return reached the attribution record"
    )
    assert TOOL_INVOKED in recorded, "the call is not attributable at all"
    assert TOOL_COMPLETED not in recorded, (
        "a completion was recorded for a return the boundary refused"
    )


def test_the_refusal_is_the_parsers_and_not_the_frameworks(
    step: StepContext, claimed: Claimed
) -> None:
    """AC-0247's other half: which component refused.

    The value is a plain string and the tool's return annotation admits it, so
    nothing in the framework's own serialization would object. A check that only
    asserted "the run raised" could not tell this apart from a schema failure.
    """
    stack, _ = a_stack(
        step,
        resolver=a_resolver(a_prefix_ceiling()),
        spy=Spy(returns=FREE_TEXT_RETURN),
    )

    with pytest.raises(AdmittedTypeRefused) as raised:
        drive(stack, {"cik": INSIDE})

    assert "label vocabulary" in str(raised.value)


def test_the_deployment_creates_at_least_one_runtime_identity(
    owner_conn: psycopg.Connection,
) -> None:
    """Setup check for AC-0249: the enumeration found roles, not an empty set.

    Without it, a query that stopped matching would make the criterion below
    green by iterating over nothing — the shape of a check that cannot fail.
    """
    identities = runtime_login_identities(owner_conn)
    assert identities, "no runtime login identity was enumerated"
    assert "app_worker" in identities and "app_policy" in identities


@pytest.mark.parametrize("table", CONFIGURATION_TABLES)
def test_no_runtime_identity_can_write_the_configuration_it_is_bound_by(
    owner_conn: psycopg.Connection, table: str
) -> None:
    """AC-0249 — the database refuses, and the application is not asked to.

    r5 § 6 says the privilege split's strength "rests on the database grant
    rather than on credential separation". So the refusal has to come from
    Postgres: if the application were the thing that refused, the criterion
    would be testing the caller rather than the grant.

    **Enumerated at test time from `pg_roles`**, so a login role added later is
    covered without editing this criterion — which is the property the
    criterion's own text asks for. Every authorization criterion in this suite
    presumes the identity being constrained cannot rewrite the constraint, and
    that presumption is one `GRANT` line no other test would notice losing.
    """
    identities = runtime_login_identities(owner_conn)

    for identity in identities:
        with connect_as(identity) as conn:
            for statement in write_statements(table):
                with pytest.raises(psycopg.errors.InsufficientPrivilege) as raised:
                    conn.execute(statement)
                assert table in str(raised.value) or "permission denied" in str(raised.value)
                conn.rollback()
