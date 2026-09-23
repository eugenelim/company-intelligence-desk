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

**One consequence worth stating, because it is easy to undo.** `declare`
raises `CeilingDeclarationRefused` on *every* path, including where a
predicate argument turned out to have no canonical form. Letting
`ContainmentUndecidable` out of the authoring surface would hand the decision
point the signal it reads as a denied call for a declaration that is simply
not authorable — the exact confusion the two types exist to keep apart.
`tests/containment/test_authoring_refusals.py` asserts the property, not just
the exception parentage, because parentage alone does not catch a leak.

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
canonicaliser carries seven rules — six over `url`, one over `fs-path` — and
every one records the clause it implements in its `clause` field.
`tests/containment/test_canonicalisation_rules.py` asserts both that each
rule's clause appears in the paragraph and that the paragraph itself is
unchanged, so a clause added upstream reds rather than passing quietly.

Three departures from a one-clause-one-rule mapping, each with a reason:

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
- **`fs-path` has one rule and not two.** `os.path.realpath` both resolves
  symlinks and removes dot segments, so a lexical pass after it never changes
  a value. An earlier draft carried one; deleting it left the whole suite
  green, which is what a rule carrying no weight looks like, so it is gone
  rather than kept as an entry AC-0216 could not exercise.

**Two clauses are implemented in the parse rather than as rules.** Splitting
the userinfo off the authority, and splitting the port off the host, are not
clauses — they are what every host predicate needs before any rule runs. An
earlier draft seeded the host with the naive reading, everything before the
first colon, so that removing `drop-default-ports` would flip a case. That
made the rule's evidence measure the authority split rather than the clause
the rule records, and it left a wrong value sitting in a field in production
code. The parse now splits the authority correctly, and
`refuse-ambiguous-parse` — whose clause is "reject an ambiguous parse rather
than guessing" — is what refuses an authority whose port is not a port.

## T1 — AC-0216 is unmet for two of r5's six clauses, and cannot be met

**Date:** 2026-09-23. **Status: needs an owner decision.** AC-0216 is
unchecked in `spec.md` because of this entry, and it is the only criterion T1
does not close.

**What AC-0216 asks.** For every rule r5 names under "What the canonicalizer
must do", an input the canonicaliser refuses and that is **admitted** when
that one rule is disabled.

**What is true of two of them.** `lowercase the host and not the path` and
`drop default ports` are *normalisations*, and their omission fails closed.
That is provable rather than merely unfound:

- **`drop default ports`.** r5's `url` row gives four constructors —
  `scheme_in`, `host_eq`, `host_in_domain`, `path_within` — and not one of
  them ranges over a port. Port normalisation therefore changes the value
  handed on and cannot change an admit-or-deny outcome under **any**
  implementation of this fragment.
- **`lowercase the host and not the path`.** The clause's second half is not
  an operation: the rule leaves the path alone, so removing it leaves the
  path alone too. Its first half folds the value's host, and a ceiling's host
  argument is canonical — folded — by the time it is compared. So every value
  admitted without folding is admitted with it, and the admitted set can only
  shrink when the rule goes.

**What was tried and rejected.** An earlier draft met the criterion's letter
for the first clause by substituting a miswrite — fold case over the path as
well — for the removal. That measures the miswrite, not the rule's absence.
A genuine removal-shaped case did exist at that point, but only because
`host_eq`'s argument was not canonicalised, which was a defect in its own
right and is now fixed; resting AC-0216's evidence on it would have been
resting it on a bug. Shaping the fragment so a mutation flips is the same
move the naive-host seeding made, and `AGENTS.md` § Agent Rules is explicit:
where implementation shows a ratified document wrong, stop and say so rather
than designing around it. What r5 shows wrong is its own framing sentence,
"because each omission is a known bypass" — true of the traversal, encoding
and ambiguity clauses, and not of these two.

**What the suite does instead, for those two rules only.** Three checks, all
green:

1. The rule does its job — the host comes back folded and the path does not;
   `:443` is dropped and `:8443` is kept.
2. Removing the rule admits nothing the full pipeline refuses, asserted over
   a universe built for these two rules — hosts differing in case, a punycode
   host, and authorities carrying a default port, a non-default port and none
   — spanning both sides of the ceiling, plus every other rule's case.
3. Removing the rule leaves every other rule's case refused, exactly as for
   the five rules that do have a mutation case.

Check 2 carries an anti-vacuity guard of its own, because a substitute for a
missing mutation case is exactly where a test that cannot fail hides: a
separate check asserts the rule changes the canonical form of at least two
universe members, and both checks were confirmed to red when pointed at a
rule that *is* load-bearing.

**Corroborated independently.** An adversarial reviewer ran a
7,488-combination sweep over uppercase, punycode, IDN and ported hosts
against canonicalised `host_eq`, `host_in_domain` and `path_within` ceilings
and found zero deny-to-admit flips for either rule.

**Where the gap is recorded for a gate.** AC-0216 carries
`(deferred: canonicaliser)` in `spec.md`, resolving to the
`ac-0216-two-clauses-fail-closed` entry in `workspace.toml` `[backlog].open`,
which `lint-spec-status.py` checks. **T1's pinned `Done when` requires
AC-0213 through AC-0218 green and is therefore not met**, which is the second
thing the owner is being asked to rule on.

**Recommended amendment**, for the owner to rule on. Reword AC-0216 so the
mutation case is required of every rule whose omission *can* admit, and the
fail-closed direction is required of the rest, with the reason recorded per
rule. That keeps the criterion's force — no rule ships unexercised — and
stops it asking for evidence that cannot exist. The two alternatives are to
accept the miswrite substitution as "disabled", which weakens the criterion
wherever it is applied later, or to turn `drop default ports` from a
normalisation into a refusal, which changes a ratified rule and is an
Ask-first of its own.

## T1 — the DNS root label is normalised in the parse, not in a clause

**Date:** 2026-09-23. Found by adversarial review.

`host_in_domain("gov.")` was authorable and the resulting ceiling admitted
`https://attacker.gov./`. The trailing dot is the DNS root label: a resolver
reads `sec.gov.` and `sec.gov` as one name, so the public-suffix dataset was
being asked about a spelling it does not carry and answered no. The same gap
made `host_in_domain("")` authorable, which satisfies AC-0240's
host-constraining requirement and admits every host written with a root
label — a default-allow wearing the shape of a constraint.

Two things were needed and both are in. The root label is dropped **in the
parse**, on the value's host and on a ceiling's host argument alike, because
a normalisation only one side runs is a differential rather than a canonical
form. And a host with an empty label — no labels at all, a bare dot, a
doubled dot, a leading dot — is refused: at authoring time for a predicate
argument, and by `refuse-ambiguous-parse` for a value.

It sits in the parse rather than in a rule for the same reason the userinfo
and port splits do: r5's clause list does not name it, and every host
predicate needs a single spelling of the name before any clause runs.

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
1 failed, 397 passed, 195 deselected in 16.00s
```
