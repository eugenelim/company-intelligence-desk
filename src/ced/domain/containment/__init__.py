"""Authority containment: does this argument *value* fall inside the ceiling?

A pure domain library. No database, no framework, no agent — the consumer is
[`walking-skeleton-policy-decision-point`](../../../../docs/specs/walking-skeleton-policy-decision-point/spec.md),
which installs this fragment and decides what to do with what it returns.

Four modules:

  `domain_types`  the seven types an argument may declare, and the one type a
                  string prefix is sound on
  `predicates`    the decidable fragment, plus `admits` over a value and
                  `contains` over a pair
  `canonicaliser` what the callee will actually see, rule by named rule
  `ceiling`       the authoring surface that refuses, and the evaluation that
                  decides
  `errors`        the two refusals, as types the far side of the seam catches

**The seam signal is a raise.** `ContainmentUndecidable` is what evaluation
does with an input it cannot decide; there is no "inside" default and no
passthrough. `errors` records why the type is settled here rather than in
either spec's prose.
"""

from __future__ import annotations

from ced.domain.containment.canonicaliser import (
    FS_PATH_RULES,
    URL_RULES,
    CanonicalisationRule,
    CanonicalUrl,
    canonicalise,
    canonicalise_fs_root,
    rule_names,
)
from ced.domain.containment.ceiling import (
    Admitted,
    CeilingArgument,
    CeilingEntry,
    Decision,
    Denied,
    declare,
    evaluate,
    is_public_suffix,
)
from ced.domain.containment.domain_types import DomainType, prefix_expressible
from ced.domain.containment.errors import CeilingDeclarationRefused, ContainmentUndecidable
from ced.domain.containment.predicates import (
    EXPRESSIBLE_PREDICATES,
    DateRange,
    HostEq,
    HostInDomain,
    InMintedSet,
    NumberRange,
    OneOf,
    PathWithin,
    Predicate,
    Prefix,
    SchemeIn,
    Within,
    admits,
    constrains_host,
    contains,
)

__all__ = [
    "EXPRESSIBLE_PREDICATES",
    "FS_PATH_RULES",
    "URL_RULES",
    "Admitted",
    "CanonicalUrl",
    "CanonicalisationRule",
    "CeilingArgument",
    "CeilingDeclarationRefused",
    "CeilingEntry",
    "ContainmentUndecidable",
    "DateRange",
    "Decision",
    "Denied",
    "DomainType",
    "HostEq",
    "HostInDomain",
    "InMintedSet",
    "NumberRange",
    "OneOf",
    "PathWithin",
    "Predicate",
    "Prefix",
    "SchemeIn",
    "Within",
    "admits",
    "canonicalise",
    "canonicalise_fs_root",
    "constrains_host",
    "contains",
    "declare",
    "evaluate",
    "is_public_suffix",
    "prefix_expressible",
    "rule_names",
]
