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

**The `tools` element group and the `ceiling` element group are beyond
their criterion and carry none of their own**, by owner decisions of
2026-09-22. AC-0273 enumerates exactly the four
whole-array shapes; a row storing `[1]` clears all four and reaches
`IntegrationTool(tool_name=1)` against a field declared `str`. AC-0262 speaks
only to the ceiling being an array; a ceiling storing `[1]` clears it, is
dropped by `_ceiling_pins`, is read as a real binding by the class
derivation, and reaches the compiler as an `AttributeError` that
`append_role_refusal` cannot classify into an event. Both groups are named
for what they assert rather than for a criterion they discharge, so a reader
is not sent looking for one.

Every case starts from a record that loads and breaks exactly one field, so a
refusal cannot come from a second defect the case did not intend.
"""

from __future__ import annotations

from typing import Any

import pytest

from ced.adapters.postgres.roles import (
    _CEILING_BINDING_FIELDS,
    TRUST_CLASSES,
    RoleLoadError,
    _ceiling_pins,
    decode_role_record,
)
from ced.agents.compiler import ROLE_REFUSAL_EVENT_TYPES


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


def a_binding(**overrides: Any) -> dict[str, Any]:
    """A ceiling entry that loads, with `overrides` applied.

    Carries the ratified binding shape — the three fields migration 0003
    fixes, plus the `predicates` that revision leaves to another spec — so a
    case built from these differs from a loadable entry in exactly the field
    it overrides.

    It makes no promise about compiling. Nothing in this module reaches the
    compiler, and `tool_name` values here need not appear in any registry
    row's `tools`.
    """
    entry: dict[str, Any] = {
        "integration_name": "sec-filings",
        "integration_version": 1,
        "tool_name": "fetch_filing",
        "predicates": [],
    }
    entry.update(overrides)
    return entry


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


# ── Beyond AC-0262 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(1, id="number"),
        pytest.param(True, id="bool"),
        pytest.param("sec-filings", id="string"),
        pytest.param(None, id="null"),
        pytest.param(["sec-filings", 1, "fetch_filing"], id="array"),
    ],
)
def test_a_ceiling_entry_that_is_not_an_object_fails_to_load(entry: Any) -> None:
    """A ceiling entry is a binding object, and the loader is where that is decided.

    Without this the entry survives the array check, `_ceiling_pins` drops it,
    `quarantined = not ceiling` in the compiler reads the surviving array as a
    real binding, and `_bound_integrations` reaches `entry.get(...)` on it as
    an `AttributeError`, which `append_role_refusal` cannot classify.

    `True` and `None` are here because jsonb stores JSON `true` and `null`
    as scalars an operator can write into a ceiling, and neither is caught
    by reasoning about numbers or strings. An array is here because it is the
    one non-object shape that survives a check written as "not a scalar".

    **The bad entry is third and the message is asserted whole**, to the
    same standard as the two branches below. A role may bind many
    integrations, so a message naming only the role would leave an operator
    reading the whole ceiling by hand.

    Placing it after well-formed bindings also pins that it is refused and
    never dropped: a loader that kept the good entries and skipped the bad
    one would compile a role holding a narrower authority than its record
    states, with nothing recording that the record and the agent disagree.

    `every entry must be a binding object` also separates this refusal from
    AC-0262's array-shape one, which names `ceiling` too — an assertion on
    that word alone is satisfied by either, so it could not tell the two
    apart.
    """
    record = valid_role(ceiling=[a_binding(), a_binding(tool_name="fetch_index"), entry])

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(record, [])

    message = str(caught.value)
    assert "role 'analysis' version 1" in message
    assert (
        f"ceiling[2] of type {type(entry).__name__}; every entry must be a binding object"
    ) in message


@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("integration_name", 5, id="name-number"),
        pytest.param("integration_name", None, id="name-null"),
        pytest.param("integration_name", ["sec-filings"], id="name-array"),
        pytest.param("integration_version", "1", id="version-string"),
        pytest.param("integration_version", True, id="version-bool"),
        pytest.param("integration_version", {"v": 1}, id="version-object"),
        pytest.param("tool_name", 7, id="tool-number"),
        pytest.param("tool_name", None, id="tool-null"),
    ],
)
def test_a_binding_field_of_the_wrong_type_fails_to_load(field: str, value: Any) -> None:
    """The ratified binding shape is three typed fields, not just an object.

    Migration 0003 fixes `integration_name`, `integration_version` and
    `tool_name`; `predicates` is left to
    `walking-skeleton-authority-containment` and is not judged here.

    **The bad entry is third, and the message is asserted whole.** An
    operator reading this refusal has to find one entry among many, so the
    role, the position and the field are each part of the remedy rather
    than decoration — a message losing any of them still names the field,
    and an assertion on the field alone would not notice. Both type names
    are pinned too: the type found and the type required are the only parts
    that vary per case, and they are what tells the operator what to write
    instead. The assertion is one contiguous fragment rather than several
    substrings, because a bare `in` on a type name can be satisfied by an
    unrelated part of the same message — `int` is a substring of
    `integration_name`. "is required" separates this branch from the range branch
    below, which also names `integration_version`.

    The array and object values are the sharp cases: `_bound_integrations`
    builds its pin as `(integration_name, integration_version)` and looks it
    up in a dict, so an unhashable value raises `TypeError` rather than
    AC-0260's `RoleCompileError` — and `TypeError` is outside
    `ROLE_REFUSAL_EVENT_TYPES`, so it appends no event. `True` is here
    because `isinstance(True, int)` holds.
    """
    record = valid_role(
        ceiling=[a_binding(), a_binding(tool_name="fetch_index"), a_binding(**{field: value})]
    )

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(record, [])

    expected_type = dict(_CEILING_BINDING_FIELDS)[field].__name__
    message = str(caught.value)
    assert "role 'analysis' version 1" in message
    assert (
        f"ceiling[2].{field} of type {type(value).__name__}; {expected_type} is required"
    ) in message


@pytest.mark.parametrize(
    "version",
    [
        pytest.param(2**31, id="just-above-int32"),
        pytest.param(99999999999, id="far-above-int32"),
        pytest.param(-(2**31) - 1, id="just-below-int32"),
    ],
)
def test_a_pinned_version_the_registry_cannot_hold_fails_to_load(version: int) -> None:
    """Type is not enough, because jsonb stores an integer of any width.

    `integration_registry.version` is `integer`, and `load_role` casts the
    pins to `::integer[]` in the query it runs *before* `decode_role_record`.
    So a wider value is not merely a pin that resolves to no row — it raises
    `NumericValueOutOfRange` out of the query, which is outside
    `ROLE_REFUSAL_EVENT_TYPES` and appends no event. `_ceiling_pins` drops it
    so the query never sees it, and this seam is where the refusal is stated.

    The bad entry is third and the whole message is asserted, including the
    rejected value and the column whose bound it exceeds: an operator cannot
    act on a bound they cannot see, or on one that does not say what it
    belongs to. "outside the range" separates this branch from the type
    branch above, which also names `integration_version`.
    """
    record = valid_role(
        ceiling=[
            a_binding(),
            a_binding(tool_name="fetch_index"),
            a_binding(integration_version=version),
        ]
    )

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(record, [])

    message = str(caught.value)
    assert "role 'analysis' version 1" in message
    assert (
        f"ceiling[2].integration_version {version}, outside the range "
        f"integration_registry.version can hold"
    ) in message


@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("integration_version", 2**31, id="version-above-int32"),
        pytest.param("integration_version", -(2**31) - 1, id="version-below-int32"),
        pytest.param("integration_version", True, id="version-bool"),
        pytest.param("integration_version", {"v": 1}, id="version-object"),
        pytest.param("integration_version", "1", id="version-string"),
        pytest.param("integration_name", ["x"], id="name-array"),
        pytest.param("integration_name", 5, id="name-number"),
    ],
)
def test_a_pin_the_query_cannot_carry_is_never_built(field: str, value: Any) -> None:
    """`_ceiling_pins` must not hand the registry query a value it will reject.

    Asserting the decode refusal alone would leave this green while
    `load_role` still failed in the query first, because the pin read and its
    query both run before the decode seam — and that ordering is the defect.
    Each case here drops one `_ceiling_pins` predicate if that predicate
    stops being applied.

    The values are paired with a well-formed binding on purpose, because two
    of them are only harmful in company. A boolean version fails just beside
    an `int`, where the version list becomes `[1, True]` and psycopg refuses
    to dump a mixed-type array; the hostile entry therefore carries its own
    `integration_name`, because `hash(True) == hash(1)` collapses it onto the
    well-formed pin when both share a name and nothing is left to see. A
    version that is neither `int` nor `bool` never reaches the query at all:
    it fails the type test that guards the range comparisons, which would
    otherwise raise `TypeError` inside the pin read.

    Both ends of the range are here. `integration_registry.version` is a
    signed `integer`, so a value below its floor overflows the `::integer[]`
    cast exactly as one above its ceiling does, and a bound written with
    only the upper comparison reds nothing without this case.
    """
    hostile = a_binding(integration_name="other")
    hostile[field] = value
    record = valid_role(ceiling=[a_binding(), hostile])

    assert _ceiling_pins(record) == (("sec-filings", 1),)


@pytest.mark.parametrize(
    "ceiling",
    [
        pytest.param([1], id="non-mapping"),
        pytest.param([{"integration_name": ["sec-filings"]}], id="unhashable-name"),
        pytest.param(
            [{"integration_name": "sec-filings", "integration_version": {"v": 1}}],
            id="unhashable-version",
        ),
        pytest.param([{}], id="empty-object"),
    ],
)
def test_every_malformed_ceiling_refusal_is_one_that_can_be_classified(
    ceiling: Any,
) -> None:
    """The defect was a missing event, not a missing refusal.

    `append_role_refusal` maps an exception to an event type by the
    exception's own type and raises `TypeError` on anything else, so a
    refusal outside that mapping appends nothing at all — in a system whose
    event log is its inspection surface.

    Most shapes here reach an *unclassifiable* exception when the loader
    lets them through: `AttributeError` for the non-mapping, and
    `TypeError` for each of the two unhashable pin values. `empty-object` is
    different and is here for coverage rather than for that argument — with
    the guard removed `_ceiling_pins` yields no pin for it at all, and the
    tuple `(None, None)` that `_bound_integrations` then builds resolves no
    row and raises a classifiable `RoleCompileError`. It is the
    absent-field shape, not a missing-event one.

    Asserting the exception's membership of the mapping, rather than its
    message, is what makes this a check about the event rather than the
    wording.

    **What this uniquely holds**, given each shape is also refused by a
    stronger case above: every one of those names `RoleLoadError` directly,
    so none of them notices if that type stops being one
    `append_role_refusal` maps. Removing `RoleLoadError` from
    `ROLE_REFUSAL_EVENT_TYPES` reds this check and no other offline check.
    """
    with pytest.raises(Exception) as caught:
        decode_role_record(valid_role(ceiling=ceiling), [])

    assert isinstance(caught.value, tuple(refusal for refusal, _ in ROLE_REFUSAL_EVENT_TYPES))


def test_a_ceiling_of_well_formed_bindings_loads() -> None:
    """The admitted direction, so the refusals above are not vacuous.

    Two entries, and `predicates` carried through untouched: the seam fixes
    the three binding fields and must not start judging the field whose
    encoding another spec owns.

    The expected ceiling is built independently rather than read back off
    `record`. `decode_role_record` returns the mapping it was handed, so
    comparing the result against that same object is `x == x` and would hold
    however the seam rewrote the entries.
    """
    expected = [
        {
            "integration_name": "sec-filings",
            "integration_version": 1,
            "tool_name": "fetch_filing",
            "predicates": [],
        },
        {
            "integration_name": "sec-filings",
            "integration_version": 1,
            "tool_name": "fetch_index",
            "predicates": [],
        },
    ]
    record = valid_role(ceiling=[a_binding(), a_binding(tool_name="fetch_index")])

    loaded = decode_role_record(record, [])

    assert loaded.role["ceiling"] == expected


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


# ── Beyond AC-0273: what is inside the array ────────────────────────────────


@pytest.mark.parametrize(
    "tool_name",
    [
        pytest.param(1, id="integer"),
        pytest.param(None, id="null"),
        pytest.param(True, id="boolean"),
        pytest.param(["fetch_filing"], id="nested-array"),
        pytest.param({"name": "fetch_filing"}, id="object"),
    ],
)
def test_a_tools_entry_that_is_not_a_string_fails_to_load(tool_name: Any) -> None:
    """A tool name is a string, and the loader is where that is decided.

    Without this the value reaches `IntegrationTool(tool_name=...)`, whose
    field is declared `str`, and the first observation is a wrongly typed
    entry inside AC-0233's enumeration rather than a refusal naming the row.
    `True` is here because `isinstance(True, int)` holds, so a check written
    against the wrong type still admits it.
    """
    record = valid_integration(tools=[tool_name])

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(valid_role(), [record])

    assert "sec-filings" in str(caught.value)


def test_the_refusal_names_which_entry_failed() -> None:
    """A row may carry many tools; the operator has to find the one that failed.

    The bad entry is third, so a message naming only the row would leave an
    operator reading the whole array by hand.
    """
    record = valid_integration(tools=["fetch_filing", "fetch_index", 7])

    with pytest.raises(RoleLoadError) as caught:
        decode_role_record(valid_role(), [record])

    assert "tools[2]" in str(caught.value)


def test_a_bad_entry_beside_good_ones_is_not_skipped() -> None:
    """Refused, never dropped.

    A loader that skipped the malformed entry and kept the rest would shrink
    the tool surface silently — the same defect AC-0273 closes one level up,
    reappearing one level down.
    """
    record = valid_integration(tools=["fetch_filing", 7])

    with pytest.raises(RoleLoadError):
        decode_role_record(valid_role(), [record])


def test_a_row_whose_entries_are_all_strings_loads() -> None:
    """The admitted direction, so the refusals above are not vacuous."""
    record = valid_integration(tools=["fetch_filing", "fetch_index"])

    loaded = decode_role_record(valid_role(), [record])

    assert loaded.integrations[0]["tools"] == ["fetch_filing", "fetch_index"]
