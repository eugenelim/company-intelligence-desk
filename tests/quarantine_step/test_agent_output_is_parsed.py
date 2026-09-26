"""AC-0255: the deterministic parser, not the framework's schema, is the boundary.

Part 1 — approved stub (``test_agent_output_fields_go_through_the_parser``):
the parser refuses free text.  Pinned by the plan's approved stub; the seam
is ``ced.domain.quarantine.parser.admit``, which ``walking-skeleton-role-
compilation`` owns.

Part 2 — widening arm (``test_assembler_is_the_boundary_not_the_schema``):
``ReferenceSelection(references=["free text"])`` is a valid instance of the
quarantined role's output type — the framework's schema accepts any
``list[str]`` — yet the context assembler, which runs *outside* the agent
after schema validation, still refuses it.  The parser is the admitting
component, not the serializer.

No database, no model call, no provider spend.
"""

from __future__ import annotations

import pytest

from ced.domain.quarantine.parser import AdmittedTypeRefused, admit
from ced.worker.context import ContextAssemblyError, assemble_planning_context


def test_agent_output_fields_go_through_the_parser() -> None:
    """AC-0255 stub: the parser refuses free text."""
    with pytest.raises(AdmittedTypeRefused):
        admit("Apple reported record revenue this quarter.")


def test_assembler_is_the_boundary_not_the_schema() -> None:
    """AC-0255 widening arm: the assembler catches free text regardless of schema.

    ``ReferenceSelection(references=["free text"])`` passes the framework's
    schema (any ``list[str]`` is valid), but the context assembler, which runs
    outside the agent after schema validation, still refuses it.  The
    deterministic parser, not the serializer, is the admitting component.
    """
    free_text = "Apple reported record revenue this quarter."
    with pytest.raises(ContextAssemblyError):
        assemble_planning_context({"references": [free_text]})


def test_a_quarantined_role_cannot_declare_the_permissive_contract() -> None:
    """AC-0255: `free-form` is in the output set and refused for a quarantined role.

    The criterion adds the member and the guard together, and the guard is the
    one already there: `_check_derived_class` admits exactly
    `QUARANTINED_OUTPUT_CONTRACT` for an empty-ceiling role. Adding a third
    member therefore widens what the compiler *knows* without widening what a
    quarantined role may *declare* — which is the property worth pinning,
    because the next member added should inherit the same refusal for free.
    """
    from ced.agents.compiler import OUTPUT_CONTRACTS, RoleCompileError, compile_role

    from ..compiler.role_records import a_pool, a_role

    assert "free-form" in OUTPUT_CONTRACTS, (
        "AC-0255 adds `free-form` as the output set's third member"
    )

    with pytest.raises(RoleCompileError, match="free-form"):
        # An empty ceiling is what makes the role quarantined; the contract is
        # the part under test, so it is set directly rather than through the
        # quarantined helper, which pins `reference-selection` by definition.
        compile_role(
            a_role(role_name="quarantine", ceiling=[], output_schema_ref="free-form"),
            (),
            a_pool(),
        )


def test_the_permissive_contract_accepts_what_the_parser_refuses() -> None:
    """AC-0255's widening arm, driven through the contract the criterion names.

    `FreeForm` is a single unconstrained string, so the framework's schema
    validates the very free text the boundary exists to stop — that is the
    whole reason this member exists. The step still fails, and it fails in the
    parser outside the agent rather than in the serializer, which is what
    "the parser and not the serializer is the admitting component" means.
    """
    from ced.agents.compiler import FreeForm

    free_text = "Apple reported record revenue this quarter."

    # The schema admits it: a permissive contract validates unparsed.
    assert FreeForm(text=free_text).text == free_text

    # The parser does not.
    with pytest.raises(ContextAssemblyError):
        assemble_planning_context({"references": [free_text]})
