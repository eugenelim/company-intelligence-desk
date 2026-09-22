"""The quarantine boundary: the minting pipeline and the parser that enforces it.

Two modules and one set of constants. `mint` produces the per-step candidate
reference set before any model runs, `vocabulary` holds every closed set in
one place a reviewer can see change, and `parser` is the deterministic
fail-closed function the boundary actually is.

No framework import reaches here. `domain/` is not an admitted layer for
`pydantic_ai` — `tests/architecture/test_dependency_direction.py` is the gate
— which is also why the boundary is a plain function and not a serializer.
"""

from __future__ import annotations

from ced.domain.quarantine.mint import CandidateSet, CandidateSetSealed, mint_candidate_set
from ced.domain.quarantine.parser import AdmittedTypeRefused, admit, parse_integration_result
from ced.domain.quarantine.vocabulary import (
    ADMITTED_SCALAR_TYPES,
    ADMITTED_UNITS,
    CONTENT_ADDRESSING_REFUSAL,
    CONTENT_KEY_PATTERN,
    LABEL_VOCABULARY,
    REFERENCE_PREFIX,
    UNMINTED_SCALAR_TYPES,
    ContentLocator,
    EnumeratedUnit,
)

__all__ = [
    "ADMITTED_SCALAR_TYPES",
    "ADMITTED_UNITS",
    "CONTENT_ADDRESSING_REFUSAL",
    "CONTENT_KEY_PATTERN",
    "LABEL_VOCABULARY",
    "REFERENCE_PREFIX",
    "UNMINTED_SCALAR_TYPES",
    "AdmittedTypeRefused",
    "CandidateSet",
    "CandidateSetSealed",
    "ContentLocator",
    "EnumeratedUnit",
    "admit",
    "mint_candidate_set",
    "parse_integration_result",
]
