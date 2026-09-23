"""Seeding `agent_role` and `integration_registry` for the substrate checks.

Both tables are empty in a fresh substrate and every other suite leaves them
that way, so a check that reads them has to write them first. The helper is
shared rather than copied because two checks — the migration-to-loader
round-trip and the whole-registry enumeration — need the same rows written the
same way, and a second spelling of the same insert is exactly the drift the
round-trip exists to catch.

**Every seeded row is removed on the way out**, and the names carry a prefix
nothing else uses. `tests/schema/test_migration_applies.py` already records
what happens when a substrate check assumes an empty table: it asserted a count
of zero and duly failed once another check's rows were still present.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

#: Prefix for every name these helpers write, so a leak is attributable and a
#: cleanup can never reach a row another suite owns.
SEED_PREFIX = "t2a-"

#: A role record that loads. Each check copies it and breaks exactly one field,
#: so the field under test is the only difference from a passing row.
VALID_MODEL_SETTINGS: Mapping[str, Any] = {
    "model_id": "stub:counting",
    "settings": {"max_tokens": 1024, "temperature": 0.0, "thinking": False},
    "limits": {
        "per_request_input_tokens_limit": 40000,
        "input_tokens_limit": 200000,
        "request_limit": 8,
        "tool_calls_limit": 16,
    },
}


def insert_integration(
    conn: psycopg.Connection[Any],
    *,
    integration_name: str,
    version: int = 1,
    trust_class: str = "admitted-types",
    tools: Sequence[str] | None = ("fetch_filing",),
    pool_classes: Sequence[str] = (),
) -> None:
    """Write one registry row.

    `tools` defaults to a one-element array and takes `None` for the omitted
    case, which the column admits because revision 0003 makes it nullable with
    no default — that nullability is the thing AC-0273 exists to notice.
    """
    conn.execute(
        """
        INSERT INTO integration_registry
            (integration_name, version, trust_class, kind, adapter_ref,
             pool_classes, tools)
        VALUES (%s, %s, %s, 'http', 'stub', %s, %s)
        """,
        (
            integration_name,
            version,
            trust_class,
            Jsonb(list(pool_classes)),
            None if tools is None else Jsonb(list(tools)),
        ),
    )


def insert_role(
    conn: psycopg.Connection[Any],
    *,
    role_name: str,
    version: int = 1,
    ceiling: Any = (),
    pool_class: str | None = None,
    model_settings: Mapping[str, Any] | None = None,
    output_schema_ref: str = "finding-set",
    display_name: str | None = None,
) -> None:
    """Write one role row.

    `ceiling` is passed through to `jsonb` as given, so a check can store the
    malformed shapes AC-0262 names — an object, a string — and not only a list.
    """
    conn.execute(
        """
        INSERT INTO agent_role
            (role_name, version, ceiling, pool_class, instructions,
             model_settings, output_schema_ref, display_name)
        VALUES (%s, %s, %s, %s, 'seeded by tests/fixtures/registry_seed.py',
                %s, %s, %s)
        """,
        (
            role_name,
            version,
            Jsonb(list(ceiling) if isinstance(ceiling, tuple) else ceiling),
            pool_class,
            Jsonb(dict(VALID_MODEL_SETTINGS if model_settings is None else model_settings)),
            output_schema_ref,
            display_name,
        ),
    )


def ceiling_entry(
    integration_name: str,
    integration_version: int = 1,
    tool_name: str = "fetch_filing",
) -> dict[str, Any]:
    """One ceiling entry in the ratified binding shape.

    `predicates` is present and empty, which is the encoding for "no
    predicates" and not a placeholder: `ced.agents.ceilings` installs **no**
    resolver entry for such a row, so a call to that tool denies by lookup
    miss. A seeded value with structure would put a real ceiling behind every
    check in this file that does not want one.
    """
    return {
        "integration_name": integration_name,
        "integration_version": integration_version,
        "tool_name": tool_name,
        "predicates": [],
    }


@contextmanager
def seeded(conn: psycopg.Connection[Any]) -> Iterator[psycopg.Connection[Any]]:
    """Yield `conn` for seeding, then delete every prefixed row and commit.

    **The caller commits its inserts.** `load_role` and `list_integration_tools`
    open their own connections as `app_worker`, so uncommitted rows on this
    connection are invisible to them and the check would read an empty table
    while looking like it seeded one.

    The cleanup runs on the failure path too, so one red check does not leave
    rows behind that red the next one for a different reason.
    """
    try:
        yield conn
        conn.commit()
    finally:
        conn.rollback()
        conn.execute("DELETE FROM agent_role WHERE role_name LIKE %s", (SEED_PREFIX + "%",))
        conn.execute(
            "DELETE FROM integration_registry WHERE integration_name LIKE %s",
            (SEED_PREFIX + "%",),
        )
        conn.commit()
