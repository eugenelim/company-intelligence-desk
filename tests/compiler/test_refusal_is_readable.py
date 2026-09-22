"""AC-0261 — a role that never compiles is readable from the event log.

Two halves, and the criterion's point is that an operator can tell a bad role
file from a runtime fault without attaching a debugger:

* the **compile** refusal is appended with an event type of its own and an
  `agent_role` naming the role that failed;
* the **load** refusal is appended at its own stage — its own event type —
  rather than as a step fault.

**Read literally the criterion is self-contradictory**, because a type fixed
at `step.failed` cannot also be the thing that distinguishes. The ratified
design's § 3 settles the intent and is what is built here: each stage gets its
own canonical event type. Which *guard* refused is deliberately absent — the
`events` envelope migration 0001 ships has no column for it and this spec
writes no payload object, so that half is a Follow-on with a register entry.

**The type constraint is decided against the shipped database, not a copy of
it.** Revision 0001's `events_type_is_canonical` is
`^[a-z0-9]+(\\.[a-z0-9]+)+$` — each dot-separated segment lowercase
alphanumerics only. That pattern rejected `role.load_failed` twice while two
ratified drafts quoted the pattern in the same sentence that proposed the
name, so an assertion here about the *shape* of the chosen names would repeat
the mistake it is guarding. Instead every type is appended for real, and the
underscore spelling is appended too and must be refused, which is what
separates a satisfied constraint from a disabled one.

`substrate`: both halves are about what reaches the log.
"""

from __future__ import annotations

import psycopg
import pytest

from ced.adapters.postgres.event_log import (
    MalformedEventType,
    append_step_event,
    read_events,
)
from ced.adapters.postgres.roles import RoleLoadError, load_role
from ced.agents.compiler import (
    ROLE_REFUSAL_TYPES,
    append_role_refusal,
    compile_role,
)
from ced.agents.models import RoleCompileError
from ced.domain.events import (
    RESERVED_EVENT_TYPE,
    ROLE_COMPILE_REFUSED,
    ROLE_LOAD_FAILED,
    RUN_CANCELLED,
    RUN_REQUESTED,
    TERMINAL_EVENT_TYPES,
    TOOL_COMPLETED,
    TOOL_INVOKED,
    EventEnvelope,
    derived_idempotency_key,
)
from tests.compiler.role_records import a_planning_role, a_pool
from tests.event_log.conftest import LeasedStep, leased_step
from tests.fixtures.registry_seed import SEED_PREFIX, insert_role, seeded

pytestmark = pytest.mark.substrate

#: Imported for its fixture effect; named here so the import is not pruned.
__all__ = ["leased_step"]

#: The role whose record the loader refuses. Prefixed so `seeded` removes it.
STORED_ROLE = SEED_PREFIX + "malformed"

#: The name `role-configuration-seams.md` § 3 records as failing the shipped
#: CHECK — written into a ratified document twice, with the pattern that
#: rejects it quoted in the same sentence. It is the negative control.
THE_UNDERSCORE_SPELLING = "role.load_failed"

PRINCIPAL = "worker-1"


def _a_real_compile_refusal() -> RoleCompileError:
    """Provoke a compile refusal from the compiler rather than construct one.

    A hand-built exception would make the mapping in `append_role_refusal`
    agree with the test by construction. This is AC-0260's unresolved
    binding: a planning role whose ceiling names an integration the compiler
    was not given.
    """
    with pytest.raises(RoleCompileError) as caught:
        compile_role(a_planning_role(), integrations=(), pool=a_pool())
    return caught.value


def _a_real_load_refusal(owner_conn: psycopg.Connection) -> RoleLoadError:
    """Provoke a load refusal from the real `load_role` against a stored row.

    The ceiling stored is a JSON object, which the column admits and the query
    returns unchanged, so the refusal can only have come from the decode seam.
    """
    with seeded(owner_conn) as conn:
        insert_role(conn, role_name=STORED_ROLE, ceiling={})
        conn.commit()
        with pytest.raises(RoleLoadError) as caught:
            load_role(STORED_ROLE, 1)
    return caught.value


def _events(conn: psycopg.Connection, leased: LeasedStep) -> list[EventEnvelope]:
    """Read the step's log and **close the read transaction**.

    `read_events` is a plain `SELECT`, so it leaves an open transaction on a
    connection that is not in autocommit. A later append on the same
    connection then nests inside it as a savepoint, the outer transaction
    never commits, and the row lock `fence_step` took is still held when the
    fixture deletes the run — which blocks until the connection closes. Found
    by a teardown that hung rather than failed.
    """
    events = read_events(conn, run_id=leased.run_id)
    conn.commit()
    return events


def _event_at(conn: psycopg.Connection, leased: LeasedStep, seq: int) -> EventEnvelope:
    return next(event for event in _events(conn, leased) if event.seq == seq)


def test_a_compile_refusal_is_appended_with_its_own_type_naming_the_role(
    worker_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The first half. The stage is in the type; the role is in `agent_role`."""
    refusal = _a_real_compile_refusal()

    seq = append_role_refusal(
        worker_conn,
        refusal,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        principal=PRINCIPAL,
        agent_role="analysis",
    )

    event = _event_at(worker_conn, leased_step, seq)
    assert event.type == ROLE_COMPILE_REFUSED
    assert event.agent_role == "analysis"
    assert event.step_id == leased_step.step_id


def test_a_loader_refusal_is_appended_at_its_own_stage(
    owner_conn: psycopg.Connection,
    worker_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The second half. A refused record is not filed as a step fault.

    "Its own stage" is observable as its own type: the load stage and the
    compile stage produce different event types, and neither is any type this
    runtime already appends.
    """
    refusal = _a_real_load_refusal(owner_conn)

    seq = append_role_refusal(
        worker_conn,
        refusal,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        principal=PRINCIPAL,
        agent_role=STORED_ROLE,
    )

    event = _event_at(worker_conn, leased_step, seq)
    assert event.type == ROLE_LOAD_FAILED
    assert event.type != ROLE_COMPILE_REFUSED
    assert event.agent_role == STORED_ROLE


def test_an_operator_can_tell_a_bad_role_file_from_a_runtime_event(
    owner_conn: psycopg.Connection,
    worker_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The criterion's purpose, read off one step's log.

    The step carries a genuine runtime event — `tool.invoked`, which the
    observability layer appends — alongside both refusals. Selecting by type
    separates the role-configuration failures from the runtime one and names
    the role for each, which is the whole of what the shipped envelope can
    answer.
    """
    append_step_event(
        worker_conn,
        run_id=leased_step.run_id,
        step_id=leased_step.step_id,
        lease_epoch=leased_step.lease_epoch,
        type=TOOL_INVOKED,
        principal=PRINCIPAL,
        agent_role="analysis",
        idempotency_key=derived_idempotency_key(
            leased_step.run_id, leased_step.step_id, "a-tool-call"
        ),
    )
    for refusal, role_name in (
        (_a_real_load_refusal(owner_conn), STORED_ROLE),
        (_a_real_compile_refusal(), "analysis"),
    ):
        append_role_refusal(
            worker_conn,
            refusal,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            principal=PRINCIPAL,
            agent_role=role_name,
        )

    events = _events(worker_conn, leased_step)

    assert [
        (event.type, event.agent_role) for event in events if event.type in ROLE_REFUSAL_TYPES
    ] == [
        (ROLE_LOAD_FAILED, STORED_ROLE),
        (ROLE_COMPILE_REFUSED, "analysis"),
    ]
    assert [event.type for event in events if event.type not in ROLE_REFUSAL_TYPES] == [
        TOOL_INVOKED
    ]


def test_the_shipped_check_admits_both_types_and_refuses_the_underscore_one(
    worker_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """The constraint is decided by the database, not by a copy of its regex.

    Each chosen type is appended for real, which is the only proof it clears
    `events_type_is_canonical`. The underscore spelling is appended too and
    must be refused — without that, a constraint that had been dropped would
    look identical to one that is satisfied.
    """
    for event_type in sorted(ROLE_REFUSAL_TYPES):
        seq = append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=event_type,
            principal=PRINCIPAL,
            agent_role="analysis",
        )
        event = _event_at(worker_conn, leased_step, seq)
        assert event.type == event_type

    with pytest.raises(MalformedEventType):
        append_step_event(
            worker_conn,
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            type=THE_UNDERSCORE_SPELLING,
            principal=PRINCIPAL,
            agent_role="analysis",
        )


def test_the_refusal_types_are_not_types_this_runtime_already_appends() -> None:
    """ "Distinguishable from a runtime fault" needs the types to be unshared.

    Each name is imported rather than spelled, so a rename on either side reds
    here. **No runtime-fault type exists in this repository yet** — nothing
    appends a `step.failed`, and the step path that would is a successor
    spec's — so what is decidable today is that neither refusal collides with
    any type this runtime does append, and that the two stages differ from
    each other.
    """
    already_appended = {
        RESERVED_EVENT_TYPE,
        RUN_REQUESTED,
        RUN_CANCELLED,
        TOOL_INVOKED,
        TOOL_COMPLETED,
    } | set(TERMINAL_EVENT_TYPES)

    assert ROLE_REFUSAL_TYPES.isdisjoint(already_appended)
    assert ROLE_REFUSAL_TYPES == {ROLE_LOAD_FAILED, ROLE_COMPILE_REFUSED}


def test_a_failure_that_is_neither_stage_is_not_filed_as_a_role_refusal(
    worker_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """Fail closed. A log that misleads is worse than one missing an entry.

    Without this, an `append_role_refusal` that defaulted an unrecognised
    exception to either stage would report a runtime fault as a bad role file,
    which is the exact confusion the criterion exists to remove.
    """
    with pytest.raises(TypeError):
        append_role_refusal(
            worker_conn,
            RuntimeError("a tool body blew up"),
            run_id=leased_step.run_id,
            step_id=leased_step.step_id,
            lease_epoch=leased_step.lease_epoch,
            principal=PRINCIPAL,
            agent_role="analysis",
        )

    assert _events(worker_conn, leased_step) == []
