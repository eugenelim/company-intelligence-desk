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

**It also drives malformed records through the real `load_role`.**
AC-0251's omitted-`model_id` clause, AC-0262, AC-0266 and AC-0273's bound-row
shapes all say *fails to load* and are otherwise decided only on the decode
seam, so a `load_role` that parsed inline and never called that seam would ship
with all four green. The delegation check stores a ceiling that is a JSON
object — a shape the query accepts and returns, so its refusal can only have
come from the decode seam.

**A shape the query itself rejects is the other half, and it is not
establishing nothing.** `load_role` reads the ceiling's pins and queries the
registry *before* it calls the decode seam, so an entry that query cannot
carry fails there, with a database error `append_role_refusal` maps to no
event type — the record never becomes an agent and the event log says nothing
about why. What no offline check can reach is the query's own rejection: the
offline checks can assert that `_ceiling_pins` withholds such a value, and
one does, but only a real query establishes that withholding it was
necessary, and only the real `load_role` runs the pin read and the decode
seam in their shipped order. That is checked here.

**And it carries AC-0273's unbound-row case**, which no offline check can
reach. A registry row no ceiling binds is absent from every record the decode
seam is handed, so the only seam that can see it is `list_integration_tools()`
— the whole-registry read.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from ced.adapters.postgres.roles import (
    RoleLoadError,
    list_integration_tools,
    list_roles,
    load_role,
)
from ced.agents.compiler import ROLE_REFUSAL_EVENT_TYPES
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
UNBOUND = SEED_PREFIX + "market-data"
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


def test_an_unbound_registry_row_with_null_tools_is_refused(
    owner_conn: psycopg.Connection,
) -> None:
    """AC-0273's unbound-row case, which only the whole-registry read can see.

    The row seeded here is bound by no role's ceiling, so it is absent from
    every `load_role` result and from every record the offline decode seam is
    ever handed. That is the point: a guard scoped to bound rows passes on it,
    and the row then contributes nothing to the tool surface while AC-0233's
    enumeration reports itself complete over a universe one row smaller.

    Both halves are asserted. The bound role still loads, which is what makes
    the row unbound rather than merely broken, and `list_integration_tools()`
    — the whole-registry read the ratified design states must read the tables
    — refuses, naming the row so an operator knows which one to fix.
    """
    with seeded(owner_conn) as conn:
        insert_integration(conn, integration_name=INTEGRATION, version=2, tools=TOOLS)
        insert_integration(conn, integration_name=UNBOUND, version=3, tools=None)
        insert_role(
            conn,
            role_name=ROLE,
            ceiling=[ceiling_entry(INTEGRATION, 2, "fetch_filing")],
        )
        conn.commit()

        # Unbound: the only ceiling in the table names the other integration,
        # so the null-tools row reaches no bound-row guard.
        loaded = load_role(ROLE, 1)
        assert [r["integration_name"] for r in loaded.integrations] == [INTEGRATION]

        with pytest.raises(RoleLoadError) as caught:
            list_integration_tools()

    message = str(caught.value)
    assert UNBOUND in message
    assert "3" in message
    assert "tools" in message


@pytest.mark.parametrize(
    "ceiling",
    [
        pytest.param([1], id="non-mapping-entry"),
        pytest.param(
            [{"integration_name": ["a"], "integration_version": 1, "tool_name": "t"}],
            id="unhashable-name",
        ),
        pytest.param(
            [{"integration_name": "a", "integration_version": {"v": 1}, "tool_name": "t"}],
            id="unhashable-version",
        ),
        pytest.param(
            [{"integration_name": "a", "integration_version": 2**31, "tool_name": "t"}],
            id="version-above-int32",
        ),
        pytest.param(
            [
                {
                    "integration_name": "a",
                    "integration_version": -(2**31) - 1,
                    "tool_name": "t",
                }
            ],
            id="version-below-int32",
        ),
        pytest.param(
            [
                {"integration_name": "a", "integration_version": 1, "tool_name": "t"},
                {"integration_name": "b", "integration_version": True, "tool_name": "t"},
            ],
            id="bool-version-beside-an-int-pin",
        ),
    ],
)
def test_a_malformed_ceiling_entry_refuses_in_a_way_the_log_can_record(
    owner_conn: psycopg.Connection, ceiling: Any
) -> None:
    """Every malformed ceiling entry reaches a refusal that can become an event.

    `append_role_refusal` maps an exception to an event type by the
    exception's own type and raises on anything else, so a refusal outside
    `ROLE_REFUSAL_EVENT_TYPES` appends nothing — and the event log is this
    system's inspection surface.

    **What this asserts is that the refusal is one the log can record** —
    membership of `ROLE_REFUSAL_EVENT_TYPES`, not a particular class, because
    that mapping is exactly what decides whether an event is appended. Today
    every shape here reaches it as a `RoleLoadError` from
    `decode_role_record`; a `RoleCompileError` would satisfy the assertion
    too, and rightly, since it is equally appendable.

    The two escape routes below are what the loader now prevents, not what
    it does.

    Each would otherwise leave by one of two routes.
    `version-above-int32` and `bool-version-beside-an-int-pin` would die
    *inside* `load_role`: reading the pins and querying the registry happens
    before the decode seam, so a version wider than
    `integration_registry.version` raises `NumericValueOutOfRange` from the
    `::integer[]` cast, and a boolean version beside an `int` one makes the
    version list mixed-type, which psycopg refuses to dump. `_ceiling_pins`
    withholds both, so the query never receives them.
    `non-mapping-entry`, `unhashable-name` and `unhashable-version` never
    reach that query — `_ceiling_pins` was already tolerant of them — and
    would instead survive the loader and die in the compiler's
    `_bound_integrations` as `AttributeError` and `TypeError`.

    **What needs the substrate is the query's rejection, not the shapes.**
    `test_a_pin_the_query_cannot_carry_is_never_built` in
    `test_role_loader.py` asserts offline that `_ceiling_pins` withholds
    every value the query cannot carry; only a real query can show what
    would happen if it did not, and only the real `load_role` runs the pin
    read and the decode seam in their shipped order.

    Asserting the exception's membership of the mapping, rather than its
    message, is what makes this a check about the event.
    """
    with seeded(owner_conn) as conn:
        insert_role(conn, role_name=ROLE, ceiling=ceiling)
        conn.commit()

        with pytest.raises(Exception) as caught:
            load_role(ROLE, 1)

    assert isinstance(caught.value, tuple(t for t, _ in ROLE_REFUSAL_EVENT_TYPES))
