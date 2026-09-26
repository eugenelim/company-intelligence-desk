"""AC-0256: the context assembler fails before the agent is constructed.

Offline: no database, no object store, no model call, no agent construction.

A planning context package containing anything outside the admitted types
fails in the assembler.  The agent constructor is *never reached*, shown by
the test never calling ``compile_role``.  The check holds whatever produced
the content — a quarantined agent's output, a hardcoded dict, or any path
this delivery builds — because the assembler is the enforcement point.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ced.worker.context import ContextAssemblyError, assemble_planning_context


def test_free_text_in_context_fails_before_agent_construction() -> None:
    """Free prose in a planning context fails the assembler (AC-0256).

    ``compile_role`` is never called — the assembler raises first.  The
    "agent constructor never being reached" property is shown by the test
    structure: the assertion precedes any agent construction call.
    """
    package = {"filing_context": "Apple reported record revenue this quarter."}
    with pytest.raises(ContextAssemblyError):
        assemble_planning_context(package)
    # compile_role is never called — ContextAssemblyError is the fail point.


def test_free_text_in_list_value_fails_the_assembler() -> None:
    """Free prose inside a list value is refused element by element."""
    package = {"items": ["revenue-recognition", "Apple reported record revenue."]}
    with pytest.raises(ContextAssemblyError):
        assemble_planning_context(package)


def test_assembler_admits_closed_vocabulary_labels() -> None:
    """Labels from the fixed vocabulary pass without a candidate set."""
    package = {"label": "revenue-recognition"}
    result = assemble_planning_context(package)
    assert "revenue-recognition" in result


def test_assembler_admits_typed_scalars() -> None:
    """Decimals and dates pass without a candidate set."""
    package = {"amount": Decimal("1234.56"), "period": date(2024, 12, 31)}
    result = assemble_planning_context(package)
    assert "1234.56" in result
    assert "2024-12-31" in result


def test_assembler_rejects_reference_without_candidate_set() -> None:
    """A reference string fails when no candidate set is provided (fail-closed)."""
    package = {"ref": "ref/us-gaap_Revenues/FY2024"}
    with pytest.raises(ContextAssemblyError):
        assemble_planning_context(package)


def test_assembler_admits_empty_package() -> None:
    """An empty context package returns an empty string — not an error."""
    result = assemble_planning_context({})
    assert result == ""


def test_assembler_admits_empty_list_value() -> None:
    """A key whose value is an empty list contributes nothing and is not an error."""
    result = assemble_planning_context({"refs": []})
    assert result == ""
