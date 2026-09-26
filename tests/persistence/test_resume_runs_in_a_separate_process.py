"""AC-0227 and its companions, decided on the resume path in a fresh process.

**Why this module exists.** The sibling module asserts the *components* the
resume path uses — `load_role`, `read_run_principal`, `load_entitlements` —
and reasons in prose that the path calls them. A mutation sweep on 2026-09-25
showed that reasoning was not evidence: `resume_step` could be changed to read
the principal from the history bytes, or to compile the wrong role version,
and the whole suite stayed green, because nothing called `resume_step` at all.

Five criteria are written about the resumed step rather than about its parts.
AC-0245 says "a **resumed step's** entitlements conjunct is looked up for the
principal named in the run record". That `read_run_principal` returns the
right principal does not establish that the resumed step acts as it.

**The role here carries a ceiling, and that is load-bearing.** The plan says
the approved tool "needs a ceiling entry the installed containment predicate
admits". On an empty ceiling the compiled agent has no domain tool, the
decision point evaluates nothing, and a resume records nothing — so the check
would pass on a path that did no work. No tool *body* runs in this spec by
design: `unresolved_tool` raises and the decision point refuses every call
before a body is reached, so what the resume produces is a recorded
**policy decision**, which is the durable evidence this module reads back.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterator

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import read_events, start_run
from ced.worker.executor import make_step_body
from ced.worker.pool import Lease, PoolConfig

from .test_resume_from_bytes import (
    _INTEGRATION_NAME,
    _LIMITS,
    _MODEL_SETTINGS,
    _POOL_CLASS,
    _PRINCIPAL,
    _seed_integration,
    t3_substrate,  # noqa: F401 — used as a fixture by name
)

pytestmark = pytest.mark.substrate

_RUNNER = pathlib.Path(__file__).with_name("resume_runner.py")

#: **A role name of its own, at version 1.** The executor loads version 1 from
#: the step's `agent_role` string — a T1 simplification recorded in the ledger
#: — so a ceiling-bearing role cannot be introduced as a later version of the
#: sibling module's role without changing what its own checks compile against.
_RESUME_ROLE = "t3-resume-role"
_RESUME_VERSION = 1

#: **A real argument predicate, because an empty one admits nothing.**
#: `compile_ceiling` states it plainly: "an entry whose `predicates` encoding
#: is absent or empty contributes **no** entry, so a call to that tool denies
#: by lookup miss" — the fragment is fail-closed, and both `[]` and `{}` were
#: tried before reading that. Admission matters here because `may_act` is a
#: conjunction: a ceiling that refuses first decides the call before the
#: entitlements term is reached, and a revocation could never be seen to bite.
#: AC-0253 requires exactly that it bite, since AC-0241 pins the ceiling half
#: to the suspended role version and it cannot carry revocation.
_CEILING = [
    {
        "integration_name": _INTEGRATION_NAME,
        "integration_version": 1,
        "tool_name": "fetch_filing",
        "predicates": {
            "ticker": {
                "domain_type": "opaque-string",
                "predicates": [{"kind": "prefix", "value": "AA"}],
            }
        },
    }
]


def _seed_resume_role(conn: psycopg.Connection) -> None:
    """A role whose ceiling admits one tool, so a decision can be recorded."""
    _seed_integration(conn, version=1)
    conn.execute(
        """
        INSERT INTO agent_role
            (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
        VALUES (%s, %s, %s::jsonb, 'resume-path instructions', %s::jsonb, 'finding-set')
        ON CONFLICT (role_name, version) DO UPDATE
            SET ceiling = EXCLUDED.ceiling,
                instructions = EXCLUDED.instructions,
                model_settings = EXCLUDED.model_settings
        """,
        (_RESUME_ROLE, _RESUME_VERSION, json.dumps(_CEILING), _MODEL_SETTINGS),
    )
    conn.execute(
        """
        INSERT INTO entitlements (principal, ceiling)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (principal) DO UPDATE SET ceiling = EXCLUDED.ceiling
        """,
        (_PRINCIPAL, json.dumps(_CEILING)),
    )
    conn.commit()


@pytest.fixture()
def suspended_on_a_ceiling_bearing_role(
    t3_substrate: psycopg.Connection,  # noqa: F811
) -> Iterator[tuple[str, uuid.UUID, uuid.UUID, str]]:
    """Suspend a step on a role whose ceiling admits a tool.

    Yields the object-store key and the durable identifiers a fresh process
    needs to find the step — nothing else crosses to the resume.
    """
    from pydantic_ai.models.test import TestModel

    _seed_resume_role(t3_substrate)

    # **A pool class unique to this run.** The resuming process claims from the
    # pool rather than being handed an epoch, and a shared class lets it claim
    # some other suspended step — including one left behind by an earlier
    # failure. Isolating the class makes "the step I claimed is the step I
    # suspended" true by construction rather than by luck.
    pool_class = f"{_POOL_CLASS}-{uuid.uuid4().hex[:8]}"

    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn, run_id=run_id, step_id=step_id, principal=_PRINCIPAL, agent_role=_RESUME_ROLE
        )

    config = PoolConfig(
        worker_id="t3-resume-worker",
        default_limits=_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        # **Only the approval tool on the suspending run.** TestModel calls
        # every tool it is offered by default, and the domain tool is refused
        # by the decision point — correct behaviour, but it fails the step
        # before it can suspend. The resume is where the domain call belongs:
        # the fresh process offers the same tools and the decision point
        # evaluates one there, which is what gives the resume a durable
        # outcome to read back.
        model_factory=lambda _model_id: TestModel(call_tools=["request_approval"]),
        pool_class=pool_class,
    )

    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased', owner = %s, lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + interval '300 seconds', pool_class = %s
             WHERE step_id = %s
             RETURNING lease_epoch
            """,
            ("t3-resume-worker", pool_class, step_id),
        ).fetchone()
        conn.commit()
    assert row is not None
    epoch = int(row[0])

    make_step_body(config)(
        Lease(step_id=step_id, run_id=run_id, epoch=epoch, agent_role=_RESUME_ROLE),
        threading.Event(),
    )

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)
    suspended = [e for e in events if e.type == "step.suspended"]
    assert len(suspended) == 1, f"expected a suspension, got {[e.type for e in events]}"
    assert suspended[0].payload_ref is not None

    yield suspended[0].payload_ref, run_id, step_id, pool_class

    with psycopg.connect(database_url("migration")) as conn:
        conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM agent_role WHERE role_name = %s", (_RESUME_ROLE,))
        conn.commit()


def test_a_separate_process_resumes_the_step_and_acts_as_the_runs_principal(
    suspended_on_a_ceiling_bearing_role: tuple[str, uuid.UUID, uuid.UUID, str],
) -> None:
    """AC-0227 and AC-0245, decided on the resume path rather than its parts.

    The subprocess receives only identifiers and the object-store key, and
    builds its own pool wiring — so no object from the suspending run crosses
    the boundary, which is what "sharing nothing with the original run but
    those bytes" has to mean to be worth asserting.

    Both properties are read back from the log: the resume recorded something,
    and what it recorded carries the principal from the **run record**.
    Sabotaging `resume_step` to take the principal from the history instead
    reds this; before this module existed that sabotage was invisible.
    """
    payload_ref, run_id, step_id, pool_class = suspended_on_a_ceiling_bearing_role

    with psycopg.connect(database_url("worker")) as conn:
        before = len(read_events(conn, run_id=run_id))

    done = subprocess.run(
        [
            sys.executable,
            str(_RUNNER),
            str(run_id),
            str(step_id),
            pool_class,
            _RESUME_ROLE,
            str(_RESUME_VERSION),
            payload_ref,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert done.returncode == 0, (
        f"the separate process failed to resume:\nstdout: {done.stdout[-1500:]}\n"
        f"stderr: {done.stderr[-1500:]}"
    )

    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    assert len(events) > before, (
        "the resumed step recorded nothing; a resume that leaves the log "
        "unchanged has applied no decision"
    )

    resumed = events[before:]

    # **The admitted half of AC-0253's pair.** With the entitlement standing,
    # the resumed call must reach a recorded decision. Without this the
    # revocation check below is satisfied by a resume that refuses everything
    # — including one that never read entitlements at all — and a
    # refusal-only pair cannot tell those apart.
    assert [e for e in resumed if e.type == "policy.decision"], (
        "the resumed call must reach a recorded policy decision while the "
        f"principal's entitlement stands. Recorded: {[e.type for e in resumed]}"
    )

    principals = {e.principal for e in resumed if e.principal is not None}
    assert principals == {_PRINCIPAL}, (
        "the resumed step must act as the principal named in the run record, "
        f"never one carried in the persisted bytes; recorded {sorted(principals)}"
    )


def test_an_entitlement_revoked_while_the_step_waits_refuses_the_resumed_call(
    suspended_on_a_ceiling_bearing_role: tuple[str, uuid.UUID, uuid.UUID, str],
) -> None:
    """AC-0253, decided on the resume path and paired against the admitted case.

    The ceiling admits this call, which is what lets the criterion be observed
    at all: `may_act` is a conjunction and the decision point short-circuits,
    so a ceiling that refused first would decide the call before the
    entitlements term was reached. AC-0241 pins the ceiling half to the
    suspended role version, so the ceiling cannot carry revocation — the
    entitlements term is the only one that can, which is precisely what this
    criterion says.

    Revocation happens while the step is suspended, which is the window the
    criterion names.
    """
    payload_ref, run_id, step_id, pool_class = suspended_on_a_ceiling_bearing_role

    with psycopg.connect(database_url("migration")) as conn:
        conn.execute("DELETE FROM entitlements WHERE principal = %s", (_PRINCIPAL,))
        conn.commit()

    with psycopg.connect(database_url("worker")) as conn:
        before = len(read_events(conn, run_id=run_id))

    done = subprocess.run(
        [
            sys.executable,
            str(_RUNNER),
            str(run_id),
            str(step_id),
            pool_class,
            _RESUME_ROLE,
            str(_RESUME_VERSION),
            payload_ref,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )

    with psycopg.connect(database_url("worker")) as conn:
        resumed = read_events(conn, run_id=run_id)[before:]

    # **A decision is recorded either way, so the event type cannot be the
    # observable.** `policy.decision` records what the decision point decided,
    # admit or deny — an earlier version of this check asserted the event was
    # absent and failed for that reason. What distinguishes the two is the
    # outcome: an admitted call ends at the uninstalled tool body, a denied one
    # never reaches it.
    assert [e for e in resumed if e.type == "policy.decision"], (
        "the revoked call must still reach a recorded decision; the refusal is "
        "a decision, and a call that recorded nothing was never evaluated"
    )
    assert done.returncode != 0, (
        "a call made after the principal's entitlement was revoked must be "
        "denied, not admitted to the tool body"
    )
    assert "entitlements" in done.stderr, (
        "the refusal must come from the entitlements conjunct — the only term "
        "that can carry a revocation, since AC-0241 pins the ceiling half to "
        f"the suspended role version. stderr tail: {done.stderr[-400:]}"
    )
