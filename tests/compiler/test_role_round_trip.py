"""The migration and the loader, joined — because nothing else joins them.

`tests/schema/test_role_configuration_schema.py` names each column the
migration adds, and `test_role_loader.py` feeds the decode seam records. Both
are green when the migration spells a column one way and the loader reads
another, and the first observation of that would be a step failing at compile
time in production.

This check writes a role row and its pinned registry rows, reads them back
through the **real** `load_role`, and asserts what the compiler reads. It is
the ratified design's own inspectability verification: "one `SELECT` on
`agent_role` returns the model id, the four declarable limits, the
output-contract name and the ceiling".

**It also drives one malformed record through the real `load_role`.**
AC-0251's omitted-`model_id` clause, AC-0262, AC-0266 and AC-0273's bound-row
shapes all say *fails to load* and are otherwise decided only on the decode
seam, so a `load_role` that parsed inline and never called that seam would ship
with all four green. The malformed record is a ceiling that is a JSON object —
a shape the query accepts and returns, so its refusal can only have come from
the decode seam. A shape the query itself rejects would never reach the seam
and would establish nothing.
"""

from __future__ import annotations

import psycopg
import pytest

from ced.adapters.postgres.roles import (
    RoleLoadError,
    list_integration_tools,
    list_roles,
    load_role,
)
from tests.fixtures.registry_seed import (
    SEED_PREFIX,
    VALID_MODEL_SETTINGS,
    ceiling_entry,
    insert_integration,
    insert_role,
    seeded,
)

pytestmark = pytest.mark.substrate

ROLE = SEED_PREFIX + "analysis"
INTEGRATION = SEED_PREFIX + "sec-filings"
TOOLS = ["fetch_filing", "list_filings"]


def test_a_stored_role_round_trips_through_the_real_loader(
    owner_conn: psycopg.Connection,
) -> None:
    """Every value the compiler reads, back out of the database it went into."""
    with seeded(owner_conn) as conn:
        insert_integration(
            conn,
            integration_name=INTEGRATION,
            version=2,
            trust_class="admitted-types",
            tools=TOOLS,
            pool_classes=["default"],
        )
        insert_role(
            conn,
            role_name=ROLE,
            ceiling=[ceiling_entry(INTEGRATION, 2, "fetch_filing")],
            pool_class="default",
            output_schema_ref="finding-set",
        )
        conn.commit()

        loaded = load_role(ROLE, 1)

        role = loaded.role
        assert role["role_name"] == ROLE
        assert role["model_settings"]["model_id"] == VALID_MODEL_SETTINGS["model_id"]
        # The four declarable limits, each by name: three of the framework's
        # `UsageLimits` fields default to `None`, which is unlimited, so a
        # limit lost between the column and the record is silently no limit.
        assert role["model_settings"]["limits"] == VALID_MODEL_SETTINGS["limits"]
        assert role["output_schema_ref"] == "finding-set"
        assert role["ceiling"] == [ceiling_entry(INTEGRATION, 2, "fetch_filing")]
        assert role["pool_class"] == "default"

        # The registry columns the compiler reads. `pool_classes` is otherwise
        # read only by an offline criterion fed a record, so this is the only
        # place a name the migration and the loader spell differently reds.
        assert len(loaded.integrations) == 1
        integration = loaded.integrations[0]
        assert integration["integration_name"] == INTEGRATION
        assert integration["version"] == 2
        assert integration["trust_class"] == "admitted-types"
        assert integration["tools"] == TOOLS
        assert integration["pool_classes"] == ["default"]


def test_the_pinned_version_is_what_the_ceiling_names(
    owner_conn: psycopg.Connection,
) -> None:
    """Two versions of one integration, and the ceiling selects one.

    There is no "current version" concept — the pinned pair is the only
    selector — so a loader taking the newest row, or both, would compile the
    role against tools it was never bound to. The widened primary key is what
    makes the second row storable at all.
    """
    with seeded(owner_conn) as conn:
        insert_integration(conn, integration_name=INTEGRATION, version=1, tools=["old"])
        insert_integration(conn, integration_name=INTEGRATION, version=2, tools=["new"])
        insert_role(
            conn,
            role_name=ROLE,
            ceiling=[ceiling_entry(INTEGRATION, 1, "old")],
        )
        conn.commit()

        loaded = load_role(ROLE, 1)

        assert [(r["version"], r["tools"]) for r in loaded.integrations] == [(1, ["old"])]


def test_a_malformed_record_is_refused_by_the_real_load_role(
    owner_conn: psycopg.Connection,
) -> None:
    """The delegation check. Without it `load_role` can parse inline and pass.

    The ceiling stored here is a JSON object, which the column's `NOT NULL`
    admits and the query returns unchanged, so the refusal can only come from
    `decode_role_record`.
    """
    with seeded(owner_conn) as conn:
        insert_role(conn, role_name=ROLE, ceiling={})
        conn.commit()

        with pytest.raises(RoleLoadError) as caught:
            load_role(ROLE, 1)

    assert "ceiling" in str(caught.value)


def test_the_two_enumerations_read_the_tables(owner_conn: psycopg.Connection) -> None:
    """`list_roles` and `list_integration_tools` against rows that exist.

    Both open their own queries, so a column renamed on one side fails here and
    nowhere in the offline suite. `list_integration_tools` spans every row and
    returns one entry per tool, which is the surface AC-0233 enumerates; this
    check asserts the shape it returns, not that criterion.
    """
    with seeded(owner_conn) as conn:
        insert_integration(conn, integration_name=INTEGRATION, version=2, tools=TOOLS)
        insert_role(conn, role_name=ROLE, ceiling=[])
        conn.commit()

        assert [(r.role_name, r.version) for r in list_roles() if r.role_name == ROLE] == [
            (ROLE, 1)
        ]

        seeded_tools = [
            t for t in list_integration_tools() if t.integration_name == INTEGRATION
        ]
        assert [(t.integration_version, t.tool_name) for t in seeded_tools] == [
            (2, "fetch_filing"),
            (2, "list_filings"),
        ]
