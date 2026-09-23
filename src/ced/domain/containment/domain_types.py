"""The seven domain types an argument may declare, and what each one means.

`worker-runtime.md` r5 § 4, "Why a prefix predicate is not safe on an
interpreted argument", rule 1: arguments carry a domain type, and the domain
type decides both which predicates are expressible and which canonicaliser
runs. The seven members here are that list, unchanged.

**`prefix_expressible` is the rule, not a list of exceptions.** r5 states it
as "prefix is expressible only on `opaque-string`", so that is how it is
written — one flag on one member rather than an enumeration of the types that
refuse it. AC-0217 names three interpreted types; a type added later inherits
the refusal from this flag instead of needing the criterion reworded.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["DomainType", "prefix_expressible"]


class DomainType(StrEnum):
    """A declared argument's domain type, spelled as r5 spells it."""

    OPAQUE_STRING = "opaque-string"
    URL = "url"
    FS_PATH = "fs-path"
    CONTENT_LOCATOR = "content-locator"
    ENUM = "enum"
    NUMBER = "number"
    DATE = "date"


def prefix_expressible(domain_type: DomainType) -> bool:
    """Return whether a string-prefix predicate is sound on `domain_type`.

    True for exactly one member. A prefix is a well-defined operation on
    strings and corresponds to no containment relation in a parsed domain, so
    it is expressible only where the registry declares the callee does not
    parse the argument.
    """
    return domain_type is DomainType.OPAQUE_STRING
