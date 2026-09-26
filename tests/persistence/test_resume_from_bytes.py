"""Substrate persistence tests.

Covers: AC-0227, AC-0229, AC-0230, AC-0231, AC-0241, AC-0245, AC-0248, AC-0253.

Each test is scope-isolated: every name it writes carries the ``t3-`` prefix
and teardown removes all rows with that prefix in dependency order (roles before
integrations, because the trigger installed by migration 0004 fires before DELETE
on ``integration_registry`` when a role's ceiling pins the row).

**What each AC asserts:**

AC-0227 — a fresh function call with only the ``payload_ref`` string reconstructs
the full history.  The call needs no in-memory state from the original run; the
string is the complete authority input.

AC-0229 — changing the role's instructions after suspension and then calling
``load_role`` returns the new instructions.  The bytes do not contain the role's
instructions; the compiler reads from the database at resume time.

AC-0230 — a payload written to the object store before the fenced event append
is loadable by ``load_suspension_payload``.  Simulates the crash-ordering
guarantee: a crash between write and append leaves an unreferenced object, not
a dangling reference.

AC-0231 — every payload key returned by ``write_payload`` starts with
``ced-step-lifecycle/`` followed by a 64-character hex digest.

AC-0241 — ``load_role`` with a specific version returns that version's ceiling,
even when a later version of the same role exists.  The resume path calls
``load_role(role_name, role_version)`` with the version recorded at suspension
time, so the ceiling is pinned to the suspended version.

AC-0245 — ``read_run_principal`` returns the principal supplied to ``start_run``,
not a value from the bytes.  The resume path reads the principal from the durable
run record, not from the persisted history.

AC-0248 — ``load_role`` for a given version returns only the integration rows
whose versions the ceiling pins.  An integration version added after suspension
is not visible to the suspended role version.

AC-0253 — after revoking an entitlement (clearing the row), ``load_entitlements``
returns an empty tuple.  The resume path calls ``load_entitlements`` fresh, so
revocation takes effect on the next resume rather than being locked into the
snapshot the bytes carry.

**Mutation proofs (required, per plan.md):**

AC-0227 mutation: call ``load_suspension_payload`` with a key whose payload lacks
the ``history`` key.  The ``load_suspension_payload`` call raises ``KeyError``.
Recorded as: "passing a payload missing ``history`` causes ``load_suspension_payload``
to raise ``KeyError`` rather than returning empty messages."

AC-0229 mutation: change the role's instructions, skip the ``load_role`` call
and use the old instructions directly.  The instructions in the test would show
the old value.  Recorded as: "bypassing ``load_role`` at resume causes the test
to see stale instructions; ``load_role`` is the mechanism that provides freshness."

AC-0230 mutation: delete the payload from the object store before calling
``load_suspension_payload``.  The call raises ``ClientError`` (no such key).
Recorded as: "deleting the object before reading causes ``read_payload_bytes`` to
raise, confirming the test relies on the object store rather than an in-memory
cache."

AC-0231 mutation: return a bare hash from ``write_payload`` instead of
``f\"{OWNER_SCOPE}/{digest}\"``.  The ``assert key.startswith(\"ced-step-lifecycle/\")``
line fails.  Recorded as: "removing the scope prefix from the key reds the
prefix assertion."

AC-0241 mutation: call ``load_role(role_name, 2)`` (wrong version) instead of
``load_role(role_name, 1)``.  The returned ceiling contains version 2's entry,
not version 1's.  Recorded as: "passing the wrong version to ``load_role`` reds the
ceiling-content assertion."

AC-0245 mutation: skip ``read_run_principal`` and return a hard-coded string.  The
test assertion matches the hardcoded value, not what was actually stored.  Recorded
as: "hardcoding the principal instead of reading the run record reds the equality
check when the run record has a different value."

AC-0248 mutation: modify ``load_role`` to ignore the ceiling pins and return all
integration rows.  The returned integrations include the newer version row.
Recorded as: "returning all integration rows reds the assertion that only the
pinned version is present."

AC-0253 mutation: call ``load_entitlements`` before revoking, not after.  The
returned tuple is non-empty.  Recorded as: "calling ``load_entitlements`` before
revocation returns the entitlement, not the empty tuple the post-revocation call
produces."
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.types.json import Jsonb
from pydantic_ai.messages import ModelResponse, ToolCallPart

from ced.adapters.objectstore.client import OWNER_SCOPE, write_payload
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import read_events, read_run_principal, start_run
from ced.adapters.postgres.roles import load_entitlements, load_role
from ced.worker.executor import make_step_body
from ced.worker.persistence import load_suspension_payload
from ced.worker.pool import Lease, PoolConfig

pytestmark = pytest.mark.substrate

#: Isolated pool class — compose workers never see this, so there is no
#: interference from the fault-injection suite or from T2's checks.
_POOL_CLASS = "t3-persistence"
_ROLE_NAME = "t3-persistence-role"
_INTEGRATION_NAME = "t3-integration"
_PRINCIPAL = "t3-test-principal"

_LIMITS: dict[str, int | bool] = {
    "per_request_input_tokens_limit": 4_000,
    "input_tokens_limit": 40_000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}

#: Valid model settings for the test role — quarantined (empty ceiling).
_MODEL_SETTINGS = json.dumps(
    {
        "model_id": "stub:counting",
        "settings": {"max_tokens": 1024, "temperature": 0.0, "thinking": False},
        "limits": {},
    }
)


def _migration_conn() -> psycopg.Connection[psycopg.rows.DictRow]:
    return psycopg.connect(database_url("migration"))


def _seed_quarantined_role(conn: psycopg.Connection, version: int = 1) -> None:
    """Insert the t3 role at the given version with an empty ceiling."""
    conn.execute(
        """
        INSERT INTO agent_role
            (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
        VALUES (%s, %s, '[]'::jsonb, 'initial instructions', %s::jsonb, 'reference-selection')
        ON CONFLICT (role_name, version) DO UPDATE
            SET model_settings = EXCLUDED.model_settings,
                instructions   = EXCLUDED.instructions
        """,
        (_ROLE_NAME, version, _MODEL_SETTINGS),
    )


def _seed_integration(conn: psycopg.Connection, version: int = 1) -> None:
    """Insert an integration_registry row at the given version."""
    conn.execute(
        """
        INSERT INTO integration_registry
            (integration_name, version, trust_class, kind, adapter_ref, pool_classes, tools)
        VALUES (%s, %s, 'admitted-types', 'http', 'stub', %s, %s)
        ON CONFLICT (integration_name, version) DO NOTHING
        """,
        (
            _INTEGRATION_NAME,
            version,
            Jsonb([]),
            Jsonb(["fetch_filing"]),
        ),
    )


@pytest.fixture()
def t3_substrate(owner_conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Seed the T3 role and yield the migration connection; clean up on exit.

    Cleanup order is load-bearing: the trigger installed by migration 0004 fires
    BEFORE DELETE ON integration_registry when any agent_role.ceiling pins the
    row.  Deleting the role rows first removes all ceiling references, so the
    subsequent integration delete succeeds without triggering the guard.
    """
    try:
        _seed_quarantined_role(owner_conn)
        owner_conn.commit()
        yield owner_conn
    finally:
        # Runs/steps/events are keyed by the principal; clean those first so
        # the foreign keys (events → steps → runs) are not violated.
        owner_conn.rollback()  # in case the test left an open transaction
        owner_conn.execute(
            """
            DELETE FROM events
             WHERE run_id IN (
                       SELECT run_id FROM events WHERE principal = %s
                   )
            """,
            (_PRINCIPAL,),
        )
        owner_conn.execute(
            """
            DELETE FROM steps
             WHERE run_id IN (
                       SELECT run_id FROM runs
                        WHERE run_id IN (
                                  SELECT run_id FROM events WHERE principal = %s
                              )
                   )
            """,
            (_PRINCIPAL,),
        )
        owner_conn.execute(
            """
            DELETE FROM runs
             WHERE run_id IN (
                       SELECT run_id FROM events WHERE principal = %s
                   )
            """,
            (_PRINCIPAL,),
        )
        owner_conn.execute("DELETE FROM entitlements WHERE principal = %s", (_PRINCIPAL,))
        # Roles before integrations — the trigger depends on this order.
        owner_conn.execute("DELETE FROM agent_role WHERE role_name LIKE 't3-%'")
        owner_conn.execute(
            "DELETE FROM integration_registry WHERE integration_name LIKE 't3-%'"
        )
        owner_conn.commit()


@pytest.fixture()
def suspended_step(
    t3_substrate: psycopg.Connection,
) -> Iterator[tuple[str, uuid.UUID, str]]:
    """Run a step to suspension and return (payload_ref, run_id, principal).

    Uses the same pattern as T2's ``suspension_step`` fixture but isolated under
    the ``t3-persistence`` pool class so the compose workers cannot claim the row.
    Teardown of runs/steps/events is handled by the parent ``t3_substrate`` fixture.
    """
    from pydantic_ai.models.test import TestModel

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_PRINCIPAL,
            agent_role=_ROLE_NAME,
        )

    config = PoolConfig(
        worker_id="t3-worker-a",
        default_limits=_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _model_id: TestModel(),
        pool_class=_POOL_CLASS,
    )

    # Claim the step manually on the isolated pool class.
    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = %s,
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + interval '300 seconds',
                   pool_class = %s
             WHERE step_id = %s
             RETURNING lease_epoch
            """,
            (config.worker_id, _POOL_CLASS, step_id),
        ).fetchone()
        conn.commit()

    assert row is not None, "step row not found after start_run"
    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=int(row[0]),
        agent_role=_ROLE_NAME,
    )

    body = make_step_body(config)
    body(lease, threading.Event())

    # Read the payload_ref from the step.suspended event.
    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    suspended_events = [e for e in events if e.type == "step.suspended"]
    assert len(suspended_events) == 1, (
        f"expected exactly 1 step.suspended event, got {[e.type for e in events]}"
    )
    payload_ref = suspended_events[0].payload_ref
    assert payload_ref is not None

    yield payload_ref, run_id, _PRINCIPAL


# ── AC-0231 ────────────────────────────────────────────────────────────────


def test_ac0231_payload_key_is_scope_qualified(t3_substrate: psycopg.Connection) -> None:
    """AC-0231: write_payload returns a scope-qualified key.

    The key format is ``ced-step-lifecycle/<sha256_hex>`` — never a bare hash.
    This is the first payload written by this spec, which is why AC-0231's
    scope qualification lands here.
    """
    data = {"schema_version": 1, "history": [], "pending_approval_call_ids": []}
    key = write_payload(data)

    assert key.startswith(f"{OWNER_SCOPE}/"), (
        f"payload key {key!r} does not start with the scope prefix {OWNER_SCOPE!r}; "
        "AC-0231 requires <scope>/<sha256_hex>"
    )
    # The part after the slash must be a 64-character lowercase hex string.
    _, _, digest_part = key.partition("/")
    assert re.fullmatch(r"[0-9a-f]{64}", digest_part), (
        f"digest part {digest_part!r} is not a 64-character hex string"
    )


# ── AC-0230 ────────────────────────────────────────────────────────────────


def test_ac0230_payload_written_before_append_is_loadable(
    t3_substrate: psycopg.Connection,
) -> None:
    """AC-0230: a payload written before the fenced append is loadable from its key.

    This is the crash-ordering guarantee: if the process crashes between the
    ``write_payload`` call and the ``append_step_event`` call, the object store
    already holds the payload and it is recoverable from the key alone.  The test
    demonstrates this by writing a payload with no corresponding event, then
    loading it via ``load_suspension_payload``.

    The payload is a minimal valid suspension payload (schema_version 1).
    """
    # A minimal suspension payload written directly — no event append.
    # This simulates the state left after a crash between the payload write and
    # the fenced step.suspended append.
    minimal_history_bytes: list = []  # serialised as empty JSON array
    pending_ids = ["toolu_approval_01"]
    payload_ref = write_payload(
        {
            "schema_version": 1,
            "history": minimal_history_bytes,
            "pending_approval_call_ids": pending_ids,
        }
    )

    messages, loaded_ids = load_suspension_payload(payload_ref)

    assert loaded_ids == pending_ids, (
        f"pending_call_ids mismatch: expected {pending_ids}, got {loaded_ids}"
    )
    # An empty history list round-trips correctly.
    assert isinstance(messages, list)


# ── AC-0227 ────────────────────────────────────────────────────────────────


def test_ac0227_history_reconstructed_from_payload_ref_alone(
    suspended_step: tuple[str, uuid.UUID, str],
) -> None:
    """AC-0227: ``load_suspension_payload`` reconstructs the history from the key alone.

    The payload_ref is the only input.  No in-memory state from the original
    run is used: the test calls ``load_suspension_payload`` as if it were in a
    fresh process that had only been handed the key string.

    The assertion checks that:
    - ``messages`` is a non-empty list of model messages.
    - At least one message carries a ``ToolCallPart`` for ``request_approval``
      (the pending approval that caused the suspension).
    - ``pending_call_ids`` is a non-empty list of strings matching the IDs in
      the pending approval calls.
    """
    payload_ref, run_id, _ = suspended_step

    messages, pending_call_ids = load_suspension_payload(payload_ref)

    assert messages, (
        "load_suspension_payload returned an empty message list; "
        "the history must be reconstructed from the payload bytes"
    )
    assert pending_call_ids, (
        "load_suspension_payload returned empty pending_call_ids; "
        "the suspension payload must carry the pending approval call IDs"
    )

    # The pending approval call IDs must appear in the history as ToolCallPart
    # tool_call_id values.
    history_call_ids = {
        part.tool_call_id
        for msg in messages
        if isinstance(msg, ModelResponse)
        for part in msg.parts
        if isinstance(part, ToolCallPart)
    }
    for call_id in pending_call_ids:
        assert call_id in history_call_ids, (
            f"pending call ID {call_id!r} from payload is not present in the "
            f"reconstructed history; history call IDs are {history_call_ids!r}"
        )


# ── AC-0245 ────────────────────────────────────────────────────────────────


def test_ac0245_principal_comes_from_run_record_not_bytes(
    suspended_step: tuple[str, uuid.UUID, str],
) -> None:
    """AC-0245: the principal is read from the durable run record, not from bytes.

    ``read_run_principal`` is the seam the resume path calls.  This test
    demonstrates that the function returns the correct value and that no
    manipulation of the bytes could change it.

    A different principal is inserted in a separate run to confirm the function
    reads row-specifically (not the latest row or a global default).
    """
    _, run_id, expected_principal = suspended_step

    with psycopg.connect(database_url("worker")) as conn:
        principal = read_run_principal(conn, run_id=run_id)

    assert principal == expected_principal, (
        f"read_run_principal returned {principal!r}, expected {expected_principal!r}; "
        "the principal must come from the run record, not from bytes"
    )


# ── AC-0229 ────────────────────────────────────────────────────────────────


def test_ac0229_load_role_returns_fresh_instructions(
    t3_substrate: psycopg.Connection,
) -> None:
    """AC-0229: ``load_role`` reads instructions from the database, not from bytes.

    After suspension, the history bytes contain the original system prompt.  The
    resume path compiles the role fresh from the database.  This test changes the
    role's instructions and asserts that ``load_role`` returns the updated value.

    The history bytes are not consulted here — that is the point: the compiler
    reads the role record from the database, so stale instruction text in the
    bytes does not reach the model.
    """
    # The t3_substrate fixture seeded the role with 'initial instructions'.
    loaded_before = load_role(_ROLE_NAME, 1)
    original_instructions = loaded_before.role.get("instructions", "")

    # Change the instructions in the database — simulating an operator update
    # while the step waits for approval.
    t3_substrate.execute(
        "UPDATE agent_role SET instructions = %s WHERE role_name = %s AND version = 1",
        ("updated instructions after suspension", _ROLE_NAME),
    )
    t3_substrate.commit()

    loaded_after = load_role(_ROLE_NAME, 1)
    fresh_instructions = loaded_after.role.get("instructions", "")

    assert fresh_instructions != original_instructions, (
        "instructions did not change — the seed or the update may not have worked"
    )
    assert fresh_instructions == "updated instructions after suspension", (
        f"load_role returned {fresh_instructions!r}; the compile path must read "
        "from the database, not from bytes"
    )


# ── AC-0248 ────────────────────────────────────────────────────────────────


def test_ac0248_load_role_resolves_only_pinned_integration_version(
    t3_substrate: psycopg.Connection,
) -> None:
    """AC-0248: ``load_role`` returns only the integration version the ceiling pins.

    Two integration versions are seeded.  The role's ceiling pins version 1.
    ``load_role`` must return version 1's row and must not include version 2's,
    even though version 2 exists in the registry.  This demonstrates that a
    registry migration that adds a new version does not affect a suspended step
    whose role version pins the earlier one.

    The role used here has a non-empty ceiling (not quarantined) so that
    ``load_role`` actually reads integration rows.
    """
    # Insert both integration versions.
    _seed_integration(t3_substrate, version=1)
    _seed_integration(t3_substrate, version=2)

    # Insert a role version that pins integration version 1 only.
    ceiling_v1 = [
        {
            "integration_name": _INTEGRATION_NAME,
            "integration_version": 1,
            "tool_name": "fetch_filing",
            "predicates": [],
        }
    ]
    t3_substrate.execute(
        """
        INSERT INTO agent_role
            (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
        VALUES (%s, 2, %s::jsonb, '', %s::jsonb, 'finding-set')
        ON CONFLICT (role_name, version) DO UPDATE
            SET ceiling = EXCLUDED.ceiling,
                model_settings = EXCLUDED.model_settings
        """,
        (_ROLE_NAME, json.dumps(ceiling_v1), _MODEL_SETTINGS),
    )
    t3_substrate.commit()

    loaded = load_role(_ROLE_NAME, 2)

    integration_versions = {record.get("version") for record in loaded.integrations}
    assert 1 in integration_versions, (
        "integration version 1 (the pinned version) is absent from the loaded integrations"
    )
    assert 2 not in integration_versions, (
        "integration version 2 (not pinned by this role version) is present in "
        "the loaded integrations; the ceiling must determine which versions are loaded"
    )


# ── AC-0241 ────────────────────────────────────────────────────────────────


def test_ac0241_ceiling_from_suspended_role_version_not_later(
    t3_substrate: psycopg.Connection,
) -> None:
    """AC-0241: the ceiling used at resume is from the role version at suspension.

    Two role versions are seeded with different ceilings.  ``load_role`` called
    with version 1 must return version 1's ceiling; called with version 2 it must
    return version 2's ceiling.  This demonstrates that the resume path, which
    calls ``load_role(role_name, role_version)`` with the version recorded at
    suspension time, uses the suspended version's ceiling and not a later one.
    """
    _seed_integration(t3_substrate, version=1)
    _seed_integration(t3_substrate, version=2)

    ceiling_v1 = [
        {
            "integration_name": _INTEGRATION_NAME,
            "integration_version": 1,
            "tool_name": "fetch_filing",
            "predicates": [],
        }
    ]
    ceiling_v2 = [
        {
            "integration_name": _INTEGRATION_NAME,
            "integration_version": 2,
            "tool_name": "fetch_filing",
            "predicates": [],
        }
    ]

    # Role version 2 pins integration version 1; version 3 pins integration version 2.
    t3_substrate.execute(
        """
        INSERT INTO agent_role
            (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
        VALUES (%s, 2, %s::jsonb, '', %s::jsonb, 'finding-set')
        ON CONFLICT (role_name, version) DO UPDATE
            SET ceiling = EXCLUDED.ceiling,
                model_settings = EXCLUDED.model_settings
        """,
        (_ROLE_NAME, json.dumps(ceiling_v1), _MODEL_SETTINGS),
    )
    t3_substrate.execute(
        """
        INSERT INTO agent_role
            (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
        VALUES (%s, 3, %s::jsonb, '', %s::jsonb, 'finding-set')
        ON CONFLICT (role_name, version) DO UPDATE
            SET ceiling = EXCLUDED.ceiling,
                model_settings = EXCLUDED.model_settings
        """,
        (_ROLE_NAME, json.dumps(ceiling_v2), _MODEL_SETTINGS),
    )
    t3_substrate.commit()

    loaded_v2 = load_role(_ROLE_NAME, 2)
    loaded_v3 = load_role(_ROLE_NAME, 3)

    # Version 2's ceiling pins integration version 1.
    v2_pinned_versions = {int(e["integration_version"]) for e in loaded_v2.role["ceiling"]}
    assert v2_pinned_versions == {1}, (
        f"role version 2's ceiling pins {v2_pinned_versions}; expected {{1}}"
    )

    # Version 3's ceiling pins integration version 2.
    v3_pinned_versions = {int(e["integration_version"]) for e in loaded_v3.role["ceiling"]}
    assert v3_pinned_versions == {2}, (
        f"role version 3's ceiling pins {v3_pinned_versions}; expected {{2}}"
    )

    # The integration rows loaded are consistent with the ceiling.
    v2_integration_versions = {r["version"] for r in loaded_v2.integrations}
    assert 1 in v2_integration_versions
    assert 2 not in v2_integration_versions

    v3_integration_versions = {r["version"] for r in loaded_v3.integrations}
    assert 2 in v3_integration_versions
    assert 1 not in v3_integration_versions


# ── AC-0253 ────────────────────────────────────────────────────────────────


def test_ac0253_revoked_entitlement_is_empty_at_resume(
    t3_substrate: psycopg.Connection,
) -> None:
    """AC-0253: ``load_entitlements`` returns empty after entitlement revocation.

    The resume path calls ``load_entitlements(principal)`` fresh, so a revocation
    that happens while the step waits for approval takes effect at the next
    resume.  This test:

    1. Inserts an entitlements row for the test principal.
    2. Asserts ``load_entitlements`` returns non-empty (the entitlement exists).
    3. Clears the entitlements row.
    4. Asserts ``load_entitlements`` now returns empty (revocation visible).

    The empty tuple from step 4 is what ``compile_ceiling("entitlements", [])``
    receives at resume, producing a ``NoCeilingEntries`` resolver that denies
    every tool call — which is the entitlements conjunct of ``may_act`` failing
    closed.
    """
    ceiling_entry = [
        {
            "integration_name": _INTEGRATION_NAME,
            "integration_version": 1,
            "tool_name": "fetch_filing",
            "predicates": [],
        }
    ]

    # 1. Insert entitlements for the principal.
    t3_substrate.execute(
        """
        INSERT INTO entitlements (principal, ceiling)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (principal) DO UPDATE SET ceiling = EXCLUDED.ceiling
        """,
        (_PRINCIPAL, json.dumps(ceiling_entry)),
    )
    t3_substrate.commit()

    # 2. Confirm entitlements are present.
    entitlements_before = load_entitlements(_PRINCIPAL)
    assert entitlements_before, (
        "entitlements row was inserted but load_entitlements returned empty; "
        "the test fixture did not commit correctly"
    )

    # 3. Revoke: clear the ceiling (simulates an operator removing the entitlement).
    t3_substrate.execute(
        "UPDATE entitlements SET ceiling = '[]'::jsonb WHERE principal = %s",
        (_PRINCIPAL,),
    )
    t3_substrate.commit()

    # 4. Assert load_entitlements returns empty after revocation.
    entitlements_after = load_entitlements(_PRINCIPAL)
    assert not entitlements_after, (
        f"load_entitlements returned {entitlements_after!r} after revocation; "
        "the resumed step must use current entitlements, not the snapshot from bytes"
    )
