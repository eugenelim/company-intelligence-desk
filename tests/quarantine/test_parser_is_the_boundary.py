"""AC-0220 — the refusal comes from the parser, not from a framework layer.

The stub in `test_parser_admits.py` pins the criterion's core case. This file
adds what the stub cannot say on its own: that the refusal is the *parser's*.
A test that drives the agent's structured output instead is testing the layer,
not the boundary — § Boundaries — Never do: **no typed output standing in for
the deterministic parser**.

So `admit` is called directly, with no agent constructed and no framework
object in the call. The proof that no agent is involved is structural: this
module imports nothing from `pydantic_ai` and nothing from `ced.agents`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ced.domain.quarantine.parser import AdmittedTypeRefused, admit

FREE_TEXT = (
    "Products gross margin expanded 560 bps YoY, driven partly by tariff refunds "
    "— a non-recurring tailwind that inflates reported profitability."
)


def test_free_prose_from_the_corpus_is_refused_by_the_parser_alone() -> None:
    """Spike 4's baseline finding, which is exactly what must not cross."""
    with pytest.raises(AdmittedTypeRefused):
        admit(FREE_TEXT)


def test_an_empty_string_and_whitespace_are_refused() -> None:
    """Neither is a label and neither is a scalar."""
    for value in ("", " ", "\n"):
        with pytest.raises(AdmittedTypeRefused):
            admit(value)


def test_a_structured_container_of_free_text_is_refused() -> None:
    """A list or a dict is not one of the three admitted classes."""
    for value in ([FREE_TEXT], {"summary": FREE_TEXT}, (FREE_TEXT,)):
        with pytest.raises(AdmittedTypeRefused):
            admit(value)


def test_this_module_reaches_no_agent_and_no_framework_object() -> None:
    """The refusal above cannot have come from a serializer that is not here."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith(("pydantic_ai", "ced.agents")) for name in imported)
