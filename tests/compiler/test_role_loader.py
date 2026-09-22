"""The loader's record-shape refusals, decided offline on the decode seam.

`decode_role_record(role_record, integration_records)` is the pure seam, and
`load_role(role_name, version)` opens its own query and cannot be handed a
record — so these criteria are decided here, against records, and the
substrate round-trip in `test_role_round_trip.py` holds the delegation that
makes them true of the real path too.

Criteria decided here:

  AC-0251 (load half)  a role omitting `model_settings.model_id`
  AC-0262              a `ceiling` absent, null, or any non-array JSON value
  AC-0266              a `trust_class` outside r5 § 4's closed set
  AC-0273              a bound row whose `tools` is absent, null, a non-array
                       or `[]`

AC-0273's unbound-row case is not here: it is decided against
`list_integration_tools()` under the `substrate` marker, because a row no role
binds is by definition absent from any one role's pinned rows.

Every case starts from a record that loads and breaks exactly one field, so a
refusal cannot come from a second defect the case did not intend.
"""

from __future__ import annotations

from typing import Any

import pytest

from ced.adapters.postgres.roles import (
    TRUST_CLASSES,
    RoleLoadError,
    decode_role_record,
)


def valid_role(**overrides: Any) -> dict[str, Any]:
    """A role record that loads, with `overrides` applied."""
    record: dict[str, Any] = {
        "role_name": "analysis",
        "version": 1,
        "ceiling": [],
        "pool_class": None,
        "instructions": "Summarise the filing.",
        "model_settings": {
            "model_id": "stub:counting",
            "settings": {"max_tokens": 1024, "temperature": 0.0, "thinking": False},
            "limits": {
                "per_request_input_tokens_limit": 40000,
                "input_tokens_limit": 200000,
                "request_limit": 8,
                "tool_calls_limit": 16,
            },
        },
        "output_schema_ref": "finding-set",
        "display_name": None,
        "owner_scope": "default",
    }
    record.update(overrides)
    return record


def valid_integration(**overrides: Any) -> dict[str, Any]:
    """A registry row that loads, with `overrides` applied."""
    record: dict[str, Any] = {
        "integration_name": "sec-filings",
        "version": 1,
        "trust_class": "admitted-types",
        "kind": "http",
        "adapter_ref": "stub",
        "connection_ref": None,
        "credential_scope": None,
        "arg_schema": {},
        "ceiling_fragment": {},
        "pool_classes": [],
        "tools": ["fetch_filing"],
        "owner_scope": "default",
    }
    record.update(overrides)
    return record


def test_a_record_that_satisfies_every_rule_decodes() -> None:
    """The admitted direction, so each refusal below is a difference of one field.

    Without it every case below passes against a seam that refuses everything.
    """
    integration = valid_integration()
    loaded = decode_role_record(valid_role(), [integration])

    assert loaded.role["role_name"] == "analysis"
    assert loaded.integrations == (integration,)


# ── AC-0251, load half ──────────────────────────────────────────────────────


def test_a_role_omitting_model_id_fails_to_load() -> None:
    """AC-0251's load clause. The compile clause is the compiler's."""
    record = valid_role(
        model_settings={"settings": {"thinking": False}, "limits": {}},
    )

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(record, [])

    assert "model_id" in str(caught.value)


# ── AC-0262 ─────────────────────────────────────────────────────────────────


def test_the_canonical_empty_ceiling_is_admitted() -> None:
    """`[]` is the empty ceiling and must load.

    Paired with the refusals below deliberately: role class is derived from the
    ceiling's emptiness, so a loader that refused `[]` along with the malformed
    shapes would make every quarantined role unloadable while every refusal
    case stayed green.
    """
    loaded = decode_role_record(valid_role(ceiling=[]), [])

    assert loaded.role["ceiling"] == []


def test_a_role_whose_ceiling_key_is_absent_fails_to_load() -> None:
    """AC-0262, the absent case."""
    record = valid_role()
    del record["ceiling"]

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(record, [])

    assert "ceiling" in str(caught.value)


@pytest.mark.parametrize(
    "ceiling",
    [
        pytest.param(None, id="null"),
        pytest.param({}, id="empty-object"),
        pytest.param({"sec-filings": ["fetch_filing"]}, id="object"),
        pytest.param("[]", id="string"),
        pytest.param(0, id="number"),
    ],
)
def test_a_ceiling_that_is_not_an_array_fails_to_load(ceiling: Any) -> None:
    """AC-0262, and the refusal must not be a coercion.

    `{}` and `"[]"` are the two shapes a coercing loader would most plausibly
    read as empty, which would reclassify an analysis role as quarantined
    without anything failing.
    """
    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(valid_role(ceiling=ceiling), [])

    assert "ceiling" in str(caught.value)


# ── AC-0266 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "trust_class",
    [
        pytest.param("admitted_types", id="underscore-near-miss"),
        pytest.param("Admitted-Types", id="casing-near-miss"),
        pytest.param("admitted-type", id="singular-near-miss"),
        pytest.param("free-text ", id="trailing-space-near-miss"),
        pytest.param("admitted-types + reference output", id="table-row-not-a-value"),
    ],
)
def test_a_trust_class_outside_the_closed_set_fails_to_load(trust_class: str) -> None:
    """AC-0266, and every case is a near-miss of a real member.

    An obviously foreign string would pass a substring test and a case-fold
    alike, so it would not distinguish membership from either. Each value here
    reds exactly one of those weaker implementations. The last is r5 § 4's
    second table row written out as a string: it is a rule about admitted-types
    output containing references, not a third storable column value, and a
    loader that admitted it would widen the set the migration adds no CHECK on.

    The refusal names the value, which is the criterion's own requirement.
    """
    record = valid_integration(trust_class=trust_class)

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(valid_role(), [record])

    assert trust_class in str(caught.value)


@pytest.mark.parametrize("trust_class", sorted(TRUST_CLASSES))
def test_each_member_of_the_closed_set_loads(trust_class: str) -> None:
    """Both members, so the guard is an allowlist and not a refusal of everything."""
    loaded = decode_role_record(valid_role(), [valid_integration(trust_class=trust_class)])

    assert loaded.integrations[0]["trust_class"] == trust_class


def test_the_closed_set_is_exactly_r5_section_4s_two_storable_values() -> None:
    """The set is pinned here so widening it is a reviewable diff.

    r5 § 4's Declared column has four rows: `admitted-types`, `admitted-types`
    + reference output, `free-text`, and absent. The second is a rule applying
    when admitted-types output carries references; the fourth is the table's
    name for not being registrable. Two are values a `text NOT NULL` column
    holds.
    """
    assert TRUST_CLASSES == frozenset({"admitted-types", "free-text"})


# ── AC-0273, the three bound-row shapes ─────────────────────────────────────


def test_a_bound_row_whose_tools_key_is_absent_fails_to_load() -> None:
    """AC-0273, the absent case, naming the row."""
    record = valid_integration()
    del record["tools"]

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(valid_role(), [record])

    assert "sec-filings" in str(caught.value)


@pytest.mark.parametrize(
    "tools",
    [
        pytest.param(None, id="null"),
        pytest.param("fetch_filing", id="string"),
        pytest.param({"fetch_filing": {}}, id="object"),
        pytest.param([], id="empty-array"),
    ],
)
def test_a_bound_row_whose_tools_value_is_wrong_fails_to_load(tools: Any) -> None:
    """AC-0273's null, non-array and empty-array shapes on a bound row.

    The empty array is here rather than in the substrate suite: only the
    *unbound* row is substrate, because an unbound row is absent from any one
    role's pinned rows by definition. Each refusal names the row, which is
    what an operator needs to find it.
    """
    record = valid_integration(tools=tools)

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(valid_role(), [record])

    assert "sec-filings" in str(caught.value)


def test_the_tools_rule_reaches_every_bound_row_not_only_the_first() -> None:
    """A loop that checks one row and returns satisfies each case above.

    The malformed row is second, so an implementation validating only the head
    of the sequence reds here and nowhere else.
    """
    records = [
        valid_integration(integration_name="sec-filings"),
        valid_integration(integration_name="market-data", tools=None),
    ]

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(valid_role(), records)

    assert "market-data" in str(caught.value)
