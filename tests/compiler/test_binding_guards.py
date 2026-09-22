"""AC-0260, AC-0203 and AC-0258 — the guards over a role's ceiling bindings.

Each is a **compile error and not a denial at call time**: the refusal is on
`compile_role`'s return path, so a role that violates one never produces an
agent and there is no object a caller could hold and invoke. That is what
these checks assert by calling the compiler and expecting nothing back.

The three read the pinned registry rows the loader returned, which is why they
are the compiler's and not the loader's: the loader supplies `tools`,
`trust_class` and `pool_classes`, and the judgement against *this* role's
ceiling and pool class is made here.
"""

from __future__ import annotations

import pytest

from ced.agents.compiler import (
    OUTPUT_CONTRACTS,
    QUARANTINED_OUTPUT_CONTRACT,
    RoleCompileError,
    compile_role,
)

from .role_records import a_ceiling_entry, a_planning_role, a_pool, a_role, an_integration

#: Every non-quarantined role class the skeleton carries, derived from the
#: compiler's own output-contract set rather than listed here. AC-0203's scope
#: is r5 § 2 R2's — any non-quarantined role, not the planning one alone — so
#: a role class added to that set is covered without this file changing.
NON_QUARANTINED_CONTRACTS = sorted(set(OUTPUT_CONTRACTS) - {QUARANTINED_OUTPUT_CONTRACT})


def a_bound_role(**overrides: object) -> dict[str, object]:
    """A non-quarantined role binding one tool on one pinned integration."""
    return a_role(ceiling=[a_ceiling_entry()], output_schema_ref="finding-set", **overrides)


def test_a_ceiling_entry_naming_an_unknown_integration_fails_to_compile() -> None:
    """AC-0260, first case: the compiler was given no row for the pinned pair."""
    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=a_planning_role(), integrations=(), pool=a_pool())

    assert "filing-archive" in str(caught.value)


def test_a_ceiling_entry_naming_a_tool_the_row_does_not_list_fails_to_compile() -> None:
    """AC-0260, second case: the row resolves and the tool is absent from it."""
    with pytest.raises(RoleCompileError) as caught:
        compile_role(
            role=a_planning_role(),
            integrations=(an_integration(tools=("list_filings",)),),
            pool=a_pool(),
        )

    assert "fetch_filing" in str(caught.value)
    assert "list_filings" in str(caught.value)


def test_a_resolved_binding_compiles() -> None:
    """The contrast that keeps the two refusals above from passing vacuously."""
    compiled = compile_role(
        role=a_planning_role(), integrations=(an_integration(),), pool=a_pool()
    )

    assert compiled.ceiling[0]["tool_name"] == "fetch_filing"


@pytest.mark.parametrize("output_schema_ref", NON_QUARANTINED_CONTRACTS)
def test_a_free_text_integration_fails_to_compile_on_any_non_quarantined_role(
    output_schema_ref: str,
) -> None:
    """AC-0203, over every non-quarantined role class rather than one of them.

    ADR-0006 D3 narrows the `free-text` exemption to unreachable in Phase 1,
    so no Phase 1 role can hold such an integration. That bounds how often
    this guard fires; it does not make it optional, and r5 § 2 R2 states the
    rule over non-quarantined roles generally.
    """
    role = a_bound_role()
    role["output_schema_ref"] = output_schema_ref

    with pytest.raises(RoleCompileError) as caught:
        compile_role(
            role=role,
            integrations=(an_integration(trust_class="free-text"),),
            pool=a_pool(),
        )

    assert "free-text" in str(caught.value)


def test_an_admitted_types_integration_compiles_on_the_same_role() -> None:
    """The trust class is what the refusal above turns on, not the binding."""
    compiled = compile_role(
        role=a_bound_role(),
        integrations=(an_integration(trust_class="admitted-types"),),
        pool=a_pool(),
    )

    assert not compiled.quarantined


def test_an_integration_not_listing_the_roles_pool_class_fails_to_compile() -> None:
    """AC-0258: the row names classes and the role's is not among them."""
    with pytest.raises(RoleCompileError) as caught:
        compile_role(
            role=a_bound_role(pool_class="default"),
            integrations=(an_integration(pool_classes=("gpu",)),),
            pool=a_pool(),
        )

    assert "default" in str(caught.value)
    assert "gpu" in str(caught.value)


def test_an_integration_listing_the_roles_pool_class_compiles() -> None:
    """The admitted half of the same comparison."""
    compiled = compile_role(
        role=a_bound_role(pool_class="gpu"),
        integrations=(an_integration(pool_classes=("gpu", "default")),),
        pool=a_pool(),
    )

    assert compiled.role_name == "analysis"


def test_an_empty_pool_classes_list_admits_every_class() -> None:
    """The column's default: empty means available to every pool class."""
    compiled = compile_role(
        role=a_bound_role(pool_class="default"),
        integrations=(an_integration(pool_classes=()),),
        pool=a_pool(),
    )

    assert compiled.role_name == "analysis"


def test_a_role_without_a_pool_class_matches_only_an_empty_pool_classes_list() -> None:
    """The third clause, in both directions, because absent is not a wildcard."""
    compile_role(
        role=a_bound_role(pool_class=None),
        integrations=(an_integration(pool_classes=()),),
        pool=a_pool(),
    )

    with pytest.raises(RoleCompileError) as caught:
        compile_role(
            role=a_bound_role(pool_class=None),
            integrations=(an_integration(pool_classes=("default",)),),
            pool=a_pool(),
        )

    assert "None" in str(caught.value)
