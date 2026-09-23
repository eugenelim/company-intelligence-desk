# Verification ledger — walking-skeleton-authority-containment

Execution observations for this spec. The spec and plan are pinned; anything
learned while building goes here.

## T1 — the seam exception type

**Date:** 2026-09-23. **Decides:** what AC-0315's raise raises, which neither
this spec nor
[`walking-skeleton-policy-decision-point`](../../walking-skeleton-policy-decision-point/spec.md)
names, and which three review rounds left open on purpose for T1 to settle in
code.

**Decision.** `src/ced/domain/containment/errors.py` defines two exception
types and exports both from the package:

| Type | Raised by | What the far side does with it |
| --- | --- | --- |
| `ContainmentUndecidable` | `evaluate`, on an input the fragment cannot decide | Treated as a **denial**. This is the signal AC-0236 receives |
| `CeilingDeclarationRefused` | `declare`, on a declaration that is not authorable | Never reaches evaluation; an authoring-time refusal |

**Why two and not one.** The two failures happen at different times against
different authorities, and a single type would make the decision point's
handler catch an authoring fault as a call denial.

**Why neither derives from a builtin error class.** The decision point's
AC-0208 requires its denial handler to be narrow by type and to let a
programming error through. A fragment raising `TypeError` would make
`except TypeError` catch every mistyped call in the runtime as well, and the
fail direction would be settled by whichever builtin escaped first. Both types
derive from `Exception` and from no builtin error class an ordinary bug
produces;
`tests/containment/test_undecidable_input_raises.py::test_the_seam_exception_is_not_one_a_programming_error_raises`
is what holds that, and it reds if either type is ever reparented.

**Why this is a ledger entry and not an amendment.** The plan predicted this
seam — § Design (LLD) *Interfaces & contracts* names "the `CeilingResolver`
shape the decision point consumes — including the exception it raises on an
input it cannot decide" — and left the type unresolved. Grounding arriving for
a seam the plan predicted belongs here. Neither approved artifact needs
changing; the decision-point spec imports the name.

## T1 — how r5's clause list became seven named rules

**Date:** 2026-09-23. AC-0216 is indexed by *rule*, so what counts as one rule
had to be settled before the mutation evidence meant anything.

r5 § 4's "What the canonicalizer must do" paragraph states six clauses. The
canonicaliser carries seven rules, and every one records the clause it
implements in its `clause` field;
`tests/containment/test_canonicalisation_rules.py` asserts both that each
rule's clause appears in the paragraph and that the paragraph itself is
unchanged, so a clause added upstream reds rather than passing quietly.

Two clauses do not map one-to-one, and both departures are in the same
sentence:

- **`percent-decode-then-refuse-residual` is one rule, not two.** r5 states
  the decode and the residual refusal in one clause, and they cannot be
  separated in evidence either: the residual check has nothing to check
  without the decode that precedes it, so a suite that split them would show
  the residual rule's case admitting whenever the decode rule was removed.
  That is entanglement, which AC-0216 explicitly refuses as proof.
- **`remove-dot-segments` is separate**, although r5 names it inside the same
  clause. It is separable in evidence — a literal `/evidence/../etc/passwd`
  needs no decoding to escape, and a double-encoded path is refused by the
  residual half whether or not dot segments are removed — so splitting it
  proves one more rule load-bearing rather than fewer.

The rule also applies to `fs-path` under the same name. One rule with two
applications is one entry in the mutation evidence, and the mutation removes
it from both tuples.

## T1 — one rule's mutation is a miswrite, not a removal

**Date:** 2026-09-23. **Affects:** AC-0216 for `lowercase-host-not-path`.

AC-0216 asks for an input the canonicaliser refuses and that is admitted when
the rule is disabled. For six of the seven rules the mutation is a removal.
For `lowercase-host-not-path` it is a substitution, and the reason is a
property of the clause rather than a convenience.

r5's clause has two halves. **Case-folding a host is permissive**: it admits
strictly more values, so removing it refuses things that were admitted and
never admits things that were refused. There is therefore no input at all for
which that half's removal turns a refusal into an admission — its omission
fails closed. **The "and not the path" half is the one with a bypass behind
it**: folding a path's case admits `/EVIDENCE/x` against a ceiling of
`/evidence/` and hands a case-sensitive callee a different resource.

So the mutation for this rule is the miswrite r5 warns against — fold case
over the path as well — rather than the removal that would fail closed. It
lives in `tests/containment/fixture.py` as `_MISWRITES`, with the same
reasoning beside it. The independence half of the criterion is asserted for
this rule exactly as for the others.

**What this does and does not establish.** It establishes that the path half
of the clause is load-bearing and that getting it wrong admits a value the
fragment otherwise refuses. It does not establish that the host half is
load-bearing, because under the fragment's predicates it is not: a host
predicate compares against a canonical lowercase argument, so an unfolded host
is refused rather than admitted.

## T1 — what AC-0214 does not close

**Date:** 2026-09-23. Recorded because the plan asks for it in T1's `Tests`
and a reader of the suite alone would not see it.

`tests/containment/test_adapter_observes_the_canonical_value.py` asserts at a
**test double**, because no production adapter consumes the canonical value in
this spec's scope. It establishes that the fragment emits the canonical value
and hands over a parsed `CanonicalUrl` rather than a string, so the consumer
has no route back to the original. It does **not** establish that the real
consumer declines to re-parse the original; that half is
`walking-skeleton-policy-decision-point` T1's.

## T1 — a pre-existing gate failure, carried not fixed

**Date:** 2026-09-23.
`tests/architecture/test_recorded_layout.py::test_no_top_level_directory_is_unrecorded`
fails on `.github`, which is not in this change's diff. It is already recorded
in `workspace.toml` `[backlog].open` against
`.github/pull_request_template.md` as `pre-existing-no-top-level-directory`,
and it is Ask-first: the entry says ADR-0003 D2's amendment requirement
applies and that a claimed owner waiver needs recording or retracting. Carried
as a known skip.

```
$ ./.venv/bin/python -m pytest -m 'not substrate' -q
1 failed, 380 passed, 195 deselected in 24.17s
```
