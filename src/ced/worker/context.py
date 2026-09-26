"""Context assembler: validate every value before a planning agent is built.

AC-0256 requires the assembler to fail *before* ``compile_role`` is reached.
AC-0255 requires that free-form output still fails through this assembler —
the deterministic parser, not the framework's schema serializer, is the
admitting component.

The assembler is the enforcement point: free text from a quarantined role
cannot reach a planning agent's context, whatever produced that content
and across every assembly path this delivery builds.

**No ``pydantic_ai`` import here.** This module lives in ``worker/``, and
``worker/`` is free of direct framework dependencies per the constraint in
``executor.py``'s module docstring.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ced.domain.quarantine.mint import CandidateSet
from ced.domain.quarantine.parser import AdmittedTypeRefused, admit

__all__ = ["ContextAssemblyError", "assemble_planning_context"]


class ContextAssemblyError(Exception):
    """A context value is outside the admitted types; the step must fail.

    Raised by :func:`assemble_planning_context` when any value fails
    :func:`~ced.domain.quarantine.parser.admit`. The caller must write a
    ``step.failed`` event before constructing any agent — the assembler is the
    fail-closed gate, and returning a sanitised substitute is not an option.
    """


def assemble_planning_context(
    package: Mapping[str, Any],
    candidate_set: CandidateSet | None = None,
) -> str:
    """Validate every value in *package* through the quarantine parser.

    For list values, each element is validated independently. Raises
    :class:`ContextAssemblyError` if any element fails
    :func:`~ced.domain.quarantine.parser.admit`, carrying the key and the
    original refusal reason.

    Returns an assembled context string with one ``key: value`` line per
    admitted scalar, or one line per list element. An empty package returns
    an empty string.

    ``candidate_set`` is the set the runtime minted for the current step. Pass
    ``None`` when no provenance is available — the parser refuses every
    reference in that case, which is the fail-closed direction.
    """
    lines: list[str] = []
    for key, value in package.items():
        items: list[Any] = value if isinstance(value, list) else [value]
        for item in items:
            try:
                admit(item, candidate_set)
            except AdmittedTypeRefused as exc:
                raise ContextAssemblyError(
                    f"context key {key!r} contains an inadmissible value: {exc}"
                ) from exc
            lines.append(f"{key}: {item}")
    return "\n".join(lines)
