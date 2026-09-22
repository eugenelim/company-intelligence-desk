"""The deterministic fail-closed parser. The quarantine boundary itself.

`runtime-architecture.md` r8 § 4 Contracts and Invariants makes this the
enforcement of the quarantine contract: a planning agent receives **no
attacker-authored free text**, and non-conforming output **fails the step**.
`worker-runtime.md` r5 § 1 routes the guarantee upstream and leaves this
subsystem the enforcement.

**This is a function, called directly and outside any agent.** This spec's
`Never do` refuses typed output standing in for the deterministic parser:
structured output is a layer, and a control must not rest on the model's
cooperation or on the framework's serializer.

Four admitted shapes and one refusal, in this order:

1. A value whose type r8 § 4 declares but Phase 1 never mints — today, a
   content-addressed locator — is refused **categorically**, before provenance
   is consulted at all, so the refusal cannot be mistaken for a provenance
   check that happened to fail.
2. An enumerated unit is admitted when its unit is a declared member.
3. A decimal or a date is admitted on its exact type.
4. A string starting with the reference prefix is admitted only when **this
   step's** candidate set minted it. Shape validity is not provenance, and
   this branch performs no shape test whatsoever: membership is the whole of
   it. With no candidate set supplied, every reference is refused, which is
   the fail-closed direction.
5. Any other string is a closed-vocabulary label, admitted only on membership.

Everything else — free prose above all — is refused.

**Nothing here reads a role record, a registry row or model output.** The
signature has no parameter through which one could arrive, and the closed sets
live in `vocabulary.py` as module-level `frozenset`s with no widening
affordance.
"""

from __future__ import annotations

from ced.domain.quarantine.mint import CandidateSet
from ced.domain.quarantine.vocabulary import (
    ADMITTED_SCALAR_TYPES,
    ADMITTED_UNITS,
    CONTENT_ADDRESSING_REFUSAL,
    LABEL_VOCABULARY,
    REFERENCE_PREFIX,
    UNMINTED_SCALAR_TYPES,
    EnumeratedUnit,
)

__all__ = ["AdmittedTypeRefused", "admit", "parse_integration_result"]


class AdmittedTypeRefused(Exception):
    """A value did not cross the quarantine boundary, and the step fails.

    Raising is the only outcome for a non-conforming value. Returning it, or
    returning a sanitised substitute, would be the detection-based defence r8
    rejects.
    """


def admit(value: object, candidates: CandidateSet | None = None) -> object:
    """Return `value` if the boundary admits it; raise otherwise.

    `candidates` is the set the runtime minted for the current step. It is
    optional and defaults to none because most admitted values need no
    provenance — and because a caller with no set must still refuse every
    reference rather than fall through.
    """
    declared = type(value)

    if declared in UNMINTED_SCALAR_TYPES:
        raise AdmittedTypeRefused(
            f"a {declared.__name__} addresses stored content, and "
            f"{CONTENT_ADDRESSING_REFUSAL}, so every one of them is refused here"
        )

    if declared is EnumeratedUnit:
        unit = value.unit if isinstance(value, EnumeratedUnit) else None
        if unit in ADMITTED_UNITS:
            return value
        raise AdmittedTypeRefused(
            f"unit {unit!r} is not a member of the declared unit enumeration "
            f"{sorted(ADMITTED_UNITS)}"
        )

    if declared in ADMITTED_SCALAR_TYPES:
        return value

    if declared is str:
        text = str(value)
        if text.startswith(REFERENCE_PREFIX):
            if candidates is not None and text in candidates:
                return value
            raise AdmittedTypeRefused(
                f"reference {text!r} was not minted for the current candidate "
                f"set; shape validity is not provenance"
            )
        if text in LABEL_VOCABULARY:
            return value
        raise AdmittedTypeRefused(
            f"{text!r} is not a member of the declared label vocabulary "
            f"{sorted(LABEL_VOCABULARY)}"
        )

    raise AdmittedTypeRefused(
        f"a {declared.__name__} is neither a closed-vocabulary label nor one of "
        f"the declared admitted scalar types "
        f"{sorted(t.__name__ for t in ADMITTED_SCALAR_TYPES)}"
    )


def parse_integration_result(tool_name: str, result: object) -> object:
    """The `ResultParser` the compiler wires into the trust-class layer.

    Narrows `admit` to the two-argument seam that layer declares. No candidate
    set is passed, and that is the fail-closed direction rather than an
    omission: an integration result is not the minting pipeline's output, so a
    reference arriving through one was minted by nobody and is refused.
    """
    try:
        return admit(result)
    except AdmittedTypeRefused as refusal:
        raise AdmittedTypeRefused(
            f"{tool_name!r} returned a result the boundary refuses: {refusal}"
        ) from refusal
