"""Substrate test: AC-0264 — a pinned integration_registry row is immutable.

Migration 0004 installs a BEFORE UPDATE OR DELETE trigger on
``integration_registry`` that fires when any ``agent_role.ceiling`` contains an
entry matching the row being modified.  This test:

1. Inserts an integration row and a role whose ceiling pins it.
2. Attempts to UPDATE the integration row using the migration (superuser) identity
   — the identity that has full table privileges on ``integration_registry``.
3. Asserts the attempt is refused with SQLSTATE ``P0001``.

**Non-vacuity obligation (required, per plan.md § T3).**

The three application identities (``app_api``, ``app_worker``, ``app_policy``)
cannot write ``integration_registry`` at all — they hold only ``SELECT``.  A test
written on any of those connections would get ``InsufficientPrivilege`` before the
trigger fires; the assertion would pass on a non-existent trigger.

The attacking identity is therefore the migration identity (``ced_owner``, the
Postgres superuser for this deployment), which holds full table privileges.  A
refused write from that identity is refused by the trigger, not by a pre-existing
permission denial.

Non-vacuity is demonstrated in two parts:

(a) **The unpinned case succeeds.** An integration row that no ceiling pins is
    updateable.  If the trigger refused every write, this would fail.

(b) **The pinned case fails.** An integration row whose
    ``(integration_name, version)`` pair appears in at least one
    ``agent_role.ceiling`` is refused.  If the trigger were absent, the migration
    identity would succeed — which is why only this identity can carry the proof.

Together the two parts show that the trigger fires on the predicate (pinned-or-not)
and not on the writer's identity.

**Mutation proof:**

Drop the trigger function or the trigger itself, then re-run both parts.  Part (a)
still succeeds (unpinned write is always safe).  Part (b) also succeeds — the
update goes through, the ``pytest.raises`` block sees no exception, and the test
fails.  This confirms that the test's green state in the presence of the trigger
is caused by the trigger firing, not by a vacuous permission denial.

Recorded as: "dropping the trigger causes the pinned-case assertion to fail
because the migration identity's UPDATE succeeds; the non-vacuity proof depends
on the trigger being present."
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.types.json import Jsonb

from ced.adapters.postgres.dsn import database_url

pytestmark = pytest.mark.substrate

_INTEGRATION_NAME = "t3-immutable-integration"
_ROLE_NAME = "t3-immutable-role"

_MODEL_SETTINGS_JSON = '{"model_id":"stub:counting","settings":{},"limits":{}}'


@pytest.fixture()
def ac0264_substrate(owner_conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Seed the rows for AC-0264 and clean up regardless of outcome.

    Cleanup order: role rows before integration rows.  The trigger installed by
    migration 0004 fires BEFORE DELETE ON integration_registry when a ceiling
    pins the row, so the role (which carries the ceiling reference) must be
    removed first.
    """
    try:
        # Integration version 1 — the one the role's ceiling pins.
        owner_conn.execute(
            """
            INSERT INTO integration_registry
                (integration_name, version, trust_class, kind, adapter_ref,
                 pool_classes, tools)
            VALUES (%s, 1, 'admitted-types', 'http', 'stub', %s, %s)
            ON CONFLICT (integration_name, version) DO NOTHING
            """,
            (_INTEGRATION_NAME, Jsonb([]), Jsonb(["fetch_filing"])),
        )
        # Integration version 2 — unpinned; the trigger must not fire on it.
        owner_conn.execute(
            """
            INSERT INTO integration_registry
                (integration_name, version, trust_class, kind, adapter_ref,
                 pool_classes, tools)
            VALUES (%s, 2, 'admitted-types', 'http', 'stub', %s, %s)
            ON CONFLICT (integration_name, version) DO NOTHING
            """,
            (_INTEGRATION_NAME, Jsonb([]), Jsonb(["fetch_filing"])),
        )
        # A role whose ceiling pins integration version 1.
        ceiling = Jsonb(
            [
                {
                    "integration_name": _INTEGRATION_NAME,
                    "integration_version": 1,
                    "tool_name": "fetch_filing",
                    "predicates": [],
                }
            ]
        )
        owner_conn.execute(
            """
            INSERT INTO agent_role
                (role_name, version, ceiling, instructions, model_settings,
                 output_schema_ref)
            VALUES (%s, 1, %s, '', %s::jsonb, 'finding-set')
            ON CONFLICT (role_name, version) DO UPDATE
                SET ceiling = EXCLUDED.ceiling,
                    model_settings = EXCLUDED.model_settings
            """,
            (_ROLE_NAME, ceiling, _MODEL_SETTINGS_JSON),
        )
        owner_conn.commit()
        yield owner_conn
    finally:
        owner_conn.rollback()
        # Role rows first, because the trigger depends on ceiling contents.
        owner_conn.execute("DELETE FROM agent_role WHERE role_name LIKE 't3-%'")
        owner_conn.execute(
            "DELETE FROM integration_registry WHERE integration_name LIKE 't3-%'"
        )
        owner_conn.commit()


def test_ac0264_unpinned_row_is_updateable(
    ac0264_substrate: psycopg.Connection,
) -> None:
    """Non-vacuity (a): the trigger does not refuse an unpinned row.

    Integration version 2 is not referenced by any ``agent_role.ceiling``.
    The migration identity (``ced_owner``) must be able to update it.  If the
    trigger refused every write regardless of the ceiling predicate, this would
    fail — establishing that the trigger is selective, not a blanket block.
    """
    with psycopg.connect(database_url("migration")) as conn:
        # This must succeed: version 2 is not pinned.
        conn.execute(
            """
            UPDATE integration_registry
               SET kind = 'http'
             WHERE integration_name = %s AND version = 2
            """,
            (_INTEGRATION_NAME,),
        )
        conn.commit()


def test_ac0264_pinned_row_is_refused_by_trigger(
    ac0264_substrate: psycopg.Connection,
) -> None:
    """AC-0264: an UPDATE on a pinned row is refused by the trigger.

    Integration version 1 is pinned by the seeded role's ceiling.  The migration
    identity has full table privileges on ``integration_registry``.  The refusal
    must therefore come from the trigger (migration 0004) and not from a
    pre-existing permission denial.

    The expected SQLSTATE is ``P0001`` (raise_exception), which is what the
    trigger function uses:
        ``RAISE EXCEPTION ... USING ERRCODE = 'P0001'``

    **This test is the non-vacuity proof.**  If the trigger were absent and only
    the application-identity grants were in force, the migration identity's UPDATE
    would succeed and this assertion would fail — confirming that a green result
    here is caused by the trigger firing, not by a vacuous permission denial.
    """
    with psycopg.connect(database_url("migration")) as conn:
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            conn.execute(
                """
                UPDATE integration_registry
                   SET kind = 'http'
                 WHERE integration_name = %s AND version = 1
                """,
                (_INTEGRATION_NAME,),
            )
            conn.commit()

        assert (
            "immutable" in str(exc_info.value).lower()
            or "pinned" in str(exc_info.value).lower()
        ), (
            f"trigger raised an exception but the message did not mention immutability or "
            f"pinning: {exc_info.value!r}; the trigger installed by migration 0004 must "
            f"name the reason in its RAISE EXCEPTION message"
        )


def test_ac0264_delete_pinned_row_is_refused_by_trigger(
    ac0264_substrate: psycopg.Connection,
) -> None:
    """AC-0264 (DELETE path): a DELETE on a pinned row is also refused.

    The trigger fires on both UPDATE and DELETE.  Integration version 1 is pinned;
    the migration identity's DELETE must be refused by the trigger.
    """
    with psycopg.connect(database_url("migration")) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute(
                """
                DELETE FROM integration_registry
                 WHERE integration_name = %s AND version = 1
                """,
                (_INTEGRATION_NAME,),
            )
            conn.commit()
