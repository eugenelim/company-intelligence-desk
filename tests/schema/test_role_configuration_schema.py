"""Revision 0003's delta, named column by column.

`test_migration_applies.py`'s `EXPECTED_TABLES` assertions pass verbatim
against a revision that adds nothing — both tables already existed after 0001 —
so the new surface has to be named here to be gated at all.

**Naming a column proves the migration wrote it, not that the loader reads that
name.** That second half is `tests/compiler/test_role_round_trip.py`, which is
a separate check for a separate failure: a column the migration spells one way
and the loader spells another way is green on both sides here.

Every expectation below was read out of the migrated database rather than
inferred from the DDL text.
"""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.substrate

#: `(table, column, data_type, is_nullable, column_default)` for every column
#: revision 0003 adds. The defaults are Postgres's rendering, which is what
#: `information_schema` returns.
ADDED_COLUMNS = (
    ("agent_role", "model_settings", "jsonb", "NO", "'{}'::jsonb"),
    ("agent_role", "output_schema_ref", "text", "NO", "'finding-set'::text"),
    ("agent_role", "display_name", "text", "YES", None),
    ("integration_registry", "version", "integer", "NO", "1"),
    ("integration_registry", "arg_schema", "jsonb", "NO", "'{}'::jsonb"),
    ("integration_registry", "ceiling_fragment", "jsonb", "NO", "'{}'::jsonb"),
    ("integration_registry", "kind", "text", "YES", None),
    ("integration_registry", "adapter_ref", "text", "YES", None),
    ("integration_registry", "connection_ref", "text", "YES", None),
    ("integration_registry", "credential_scope", "text", "YES", None),
    ("integration_registry", "pool_classes", "jsonb", "NO", "'[]'::jsonb"),
    # Nullable with **no default**; the next check states why on its own.
    ("integration_registry", "tools", "jsonb", "YES", None),
)


@pytest.mark.parametrize(
    ("table", "column", "data_type", "is_nullable", "column_default"),
    ADDED_COLUMNS,
    ids=[f"{t}.{c}" for t, c, *_ in ADDED_COLUMNS],
)
def test_each_added_column_exists_with_its_declared_shape(
    owner_conn: psycopg.Connection,
    table: str,
    column: str,
    data_type: str,
    is_nullable: str,
    column_default: str | None,
) -> None:
    """Type, nullability and default, not merely presence.

    A `NOT NULL` column added without a default errors on a non-empty table, so
    the defaults are part of what makes this revision replayable rather than
    decoration.
    """
    row = owner_conn.execute(
        """
        SELECT data_type, is_nullable, column_default
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    ).fetchone()

    assert row is not None, f"{table}.{column} does not exist"
    assert row == (data_type, is_nullable, column_default)


def test_tools_is_nullable_and_carries_no_default(owner_conn: psycopg.Connection) -> None:
    """The design's load-bearing choice, and nothing else pins it.

    A default of `'[]'` would make every row inserted without `tools` born
    valid to the database and unloadable to the loader — and worse, a row that
    contributes nothing to the tool surface `list_integration_tools()`
    enumerates while failing nowhere. Nullable-with-no-default makes the
    omission visible where it happens.

    Stated apart from the table above because the parametrised case would still
    pass if someone relaxed one tuple, and because a reviewer needs to see the
    reason beside the assertion.
    """
    row = owner_conn.execute(
        """
        SELECT is_nullable, column_default
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'integration_registry'
           AND column_name = 'tools'
        """
    ).fetchone()

    assert row == ("YES", None)


def test_the_integration_registry_key_is_name_and_version(
    owner_conn: psycopg.Connection,
) -> None:
    """The widened key, asserted as the whole definition.

    Read from `pg_constraint` rather than counted: asserting two key columns
    exist would pass against a key of `(integration_name, trust_class)`, and
    the ordering matters to every index scan that uses it. A ceiling entry's
    pinned `(integration_name, integration_version)` is the only way a version
    is selected, so a key that left `version` out would let a second version of
    an integration be unstorable.
    """
    rows = owner_conn.execute(
        """
        SELECT conname, pg_get_constraintdef(oid)
          FROM pg_constraint
         WHERE conrelid = 'public.integration_registry'::regclass
           AND contype = 'p'
        """
    ).fetchall()

    assert rows == [("integration_registry_pkey", "PRIMARY KEY (integration_name, version)")]


def test_the_select_grants_from_revision_0001_are_retained(
    owner_conn: psycopg.Connection,
) -> None:
    """No grant was added, and none was lost.

    Revision 0003 adds no grant because a column inherits its table's, and this
    is the check that makes that claim falsifiable rather than a comment. The
    second assertion is the half that matters: `SELECT` and nothing wider, so a
    later revision cannot quietly hand either reading role a write on the
    tables that carry the authority ceiling.
    """
    granted = owner_conn.execute(
        """
        SELECT grantee, table_name, privilege_type
          FROM information_schema.table_privileges
         WHERE table_schema = 'public'
           AND table_name IN ('agent_role', 'integration_registry')
           AND grantee IN ('app_api', 'app_worker')
         ORDER BY grantee, table_name, privilege_type
        """
    ).fetchall()

    assert granted == [
        ("app_api", "agent_role", "SELECT"),
        ("app_api", "integration_registry", "SELECT"),
        ("app_worker", "agent_role", "SELECT"),
        ("app_worker", "integration_registry", "SELECT"),
    ]


def test_config_is_left_in_place_unread(owner_conn: psycopg.Connection) -> None:
    """Deprecated is not dropped, and the difference is a contract change.

    § 5 leaves `config` where it is with no backfill, because the table is
    empty and dropping a column a shipped revision created is a later decision
    than this one. Asserted so a well-meaning cleanup reds here rather than
    landing unnoticed.
    """
    row = owner_conn.execute(
        """
        SELECT data_type
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'integration_registry'
           AND column_name = 'config'
        """
    ).fetchone()

    assert row == ("jsonb",)
