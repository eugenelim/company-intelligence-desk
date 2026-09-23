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

Three things were needed and all three are in.

**Label structure is decided on the encoder's output.** This defect was
found three times, and the first two repairs each closed it by lengthening a
hand-kept list of separator characters. IDNA splits on four characters
directly, and its own NFKC pass turns two more — U+2024 and U+FE52 — into a
full stop *inside* a label, so a list kept here is a snapshot of one codec
version rather than the rule. The host is encoded first and split afterwards,
which makes the guard hold for whatever the encoder maps, and the encoder's
answer is the spelling the resolver will see.

**Then the root label is dropped**, on the value's host and on a ceiling's
host argument alike, because a normalisation only one side runs is a
differential rather than a canonical form. The written spelling's root label
goes in the parse and the encoded spelling's in `idna-normalise-host`.

**Then a host with an empty label is refused.** Two paths reach that answer
and both are refusals: a separator the encoder splits on directly leaves it
an empty label to encode and it refuses the host outright, while one the
encoder's normalisation produces survives into the output where the label
check sees it. `refuse-ambiguous-parse` makes the same refusal against the
spelling the caller wrote, which is the half that does not depend on the
codec — asserted with `idna-normalise-host` removed, because against the
full pipeline that assertion would pass whether or not this package had a
guard.

**The suite derives the separator set rather than listing it.**
`tests/containment/test_authoring_refusals.py` reads the characters the codec
splits on from the codec, and computes the rest by scanning for characters
whose NFKC form is a full stop, with a setup check that the derived set is
non-empty and not ASCII-only. A list written by hand is what let this defect
survive two repairs.

It sits in the parse rather than in a rule for the same reason the userinfo
and port splits do: r5's clause list does not name it, and every host
predicate needs a single spelling of the name before any clause runs.

## T1 — four strengthenings beyond the criteria, all fail-closed

**Date:** 2026-09-23. **Status: needs an owner decision.** Found by the
implementation security and quality reviews. Each closes a default-allow the
criteria do not reach, each fails closed, and each is reversible in one
place. They are listed here and in `spec.md` § Follow-ons so the owner can
ratify or reverse them rather than inherit them.

| Strengthening | What was open | Where |
| --- | --- | --- |
| A `url` argument must carry a scheme-constraining predicate | `file://sec.gov/etc/passwd` satisfied `host_eq("sec.gov")`, and every resolver ignores that authority, so the predicate AC-0240 forces to be present decided nothing | `ceiling.declare` |
| A call must supply every argument the entry constrains | `evaluate(entry, {})` was an admission against any ceiling, and a callee's default for an omitted parameter sat outside the ceiling | `ceiling.evaluate` |
| `within("/")` is refused | Present, satisfying AC-0316, and admitting `/etc/passwd` — the filesystem twin of `host_in_domain("gov")`, which AC-0215 does refuse | `ceiling.declare` |
| Nothing but this package's two types leaves `evaluate` | A NUL in a path, a NaN, and a `datetime` where a `date` was declared each escaped as a builtin, so a model-chosen argument became an uncaught error in the worker step rather than a logged denial | `canonicaliser`, `predicates` |

The fourth is not really a strengthening: AC-0315 fixes the seam's signal as
a raise and this ledger fixes which raise, so a builtin escaping was a defect
against both. The first three add refusals no criterion states.

**The completeness rule changes what AC-0218 looks like.** Its two admitting
values now travel in one call rather than two, which the criterion's wording
— "each evaluate to an admitting result against the same ceiling AC-0213
uses" — permits, and AC-0213's rows each travel with a known-admitted value
for the argument they are not about. `test_the_companion_values_are_admitted_on_their_own`
is what stops a row passing because its companion was refused.

## T1 — the public-suffix dataset has no refresh path

**Date:** 2026-09-23. Found by the implementation security review, and it
falsifies a reason this ledger and the manifest both gave.

`publicsuffix2` bundles a snapshot published 2019-12-21 and has shipped no
release since. So `pages.dev`, `vercel.app`, `netlify.app` and `r2.dev` — the
platform suffixes under which anyone can register a name, which is exactly
the class AC-0215 exists to keep out of `host_in_domain` — answer "not a
public suffix" and are authorable.

The dependency was justified on the grounds that a bundled dataset "goes
stale at a version bump a reviewer can see". **That is false as pinned**: no
bump exists, so the staleness is silent. The plan's § Risks names dataset
ageing, so the risk is accepted; what was wrong is the mitigation claimed for
it. `PUBLIC_SUFFIX_DATASET_AS_OF` now carries the snapshot's date beside the
lookup, a test asserts it and reds if the snapshot moves, and
`longest_public_suffix` makes the oracle a seam rather than a singleton
nothing can pin. Choosing a dataset with a refresh path is a dependency
change and so an Ask-first for the owner.

## T1 — the plan's independence claim about the property test is too strong

**Date:** 2026-09-23. **Plan error, corrected here rather than in the plan.**

`plan.md` § Approach and T1's pinned `Tests` bullet both say the property
test's "oracle computes set containment independently of the implementation
under test", and § Construction tests adds that "a property test whose oracle
shares the implementation's parser proves only that the parser agrees with
itself". The oracle does not share the parser. It does share two comparison
helpers: `contains(HostInDomain, …)` and `admits(HostInDomain, …)` both call
`_in_domain`, and the `PathWithin` arms both call `_within_path`.

**Measured, not supposed.** Replacing `_in_domain` with `host.endswith(domain)`
and `_within_path` with a bare `startswith` leaves every check in
`test_containment_property.py` green while the rest of the suite reds. Those
two arms are covered by `tests/containment/test_boundaries_are_load_bearing.py`
instead, which puts direct fixtures on both sides of a label break and a
segment break.

The `Tests` bullet is pinned, so this is recorded rather than edited; the
module's own docstring now states what it shares and names the module that
covers those arms. The claim is true of the other eight arms and of the
parser, which is what the bullet was reaching for.

## T1 — two failures from one predicate, and a review target that moved

**Date:** 2026-09-23. Two notes, both worth keeping.

**`str.isdigit` is not "is a port".** `_valid_port` used it. It is true of 128
characters `int()` refuses — U+00B2 SUPERSCRIPT TWO among them — so
`https://sec.gov:\xb2/x` crashed the guard with a `ValueError` instead of
refusing, which is a builtin out of `evaluate` for a value a model can
choose. And it is true of the Arabic-Indic digits, which `int()` accepts, so
`https://h.example:\u0664\u0664\u0663/a` was admitted and normalised into
`https://h.example/a` — an authority RFC 3986 does not admit, rewritten into
one that looks valid. The predicate is now ASCII digits in range, and the
escape property's generator draws ports from an alphabet that includes both
classes, because the earlier generator could not build a port at all.

**A review target has to be a stable object.** Three reviewers were
dispatched in parallel and then the tree was edited while they read it, so
one of them reviewed a state that existed in no commit and reported gate
numbers that described neither. That is a process error, not a finding
against the code: fixes now land in a commit before any reviewer is
re-dispatched.

## T1 — everything this fragment says out loud is bounded

**Date:** 2026-09-23. Found by the security and adversarial reviews, which
reached the same defect independently, and finished by the quality review.

A `Denied` reason becomes the consumer's `policy.decision`, and AC-0315
makes a `ContainmentUndecidable` the signal the decision point records as a
denial too. **So every text this package produces is written to the event
log**, and an unbounded one lets a single refused call write a row as large
as the caller cares to make it, repeatedly and for free. A tool call's
argument *names* are model-chosen exactly as its values are.

The bound was installed once and then found half-installed three times, each
time on a sibling path the first fix did not reach:

1. The `Denied` value was capped and the `ContainmentUndecidable` messages
   were not — measured at over 8,000 characters apiece.
2. The unknown-argument denial interpolated the caller's argument name whole
   — 100,101 characters from a 100,000-character key — and the
   incomplete-call denial interpolated its argument list whole.
3. The predicate half was summarised for `in_minted_set` and fell through to
   a bare `repr` for `one_of`, so a denial against a 5,000-member enumeration
   wrote all 5,000 members; and the `scheme_in` arm sorted its whole set into
   the text.

`for_the_record` now lives in `errors.py`, the lowest module, and every
message in the package goes through it; `_describe` summarises every
set-valued constructor, listing a small scheme set and counting a large one.
`test_every_message_a_consumer_records_is_bounded` drives all ten paths that
can carry a model-chosen fragment, with a setup check that all ten were
reached — because a bound asserted over paths nothing enters is no bound.

Then it was found half-installed a fourth time, on paths nobody had thought
to look at: `_refuse`'s own entry and argument names, the domain-type name,
and — the one that mattered — `{error}`, the text of an exception this
package did not compose. CPython's NFKC branch of `urlsplit`'s `ValueError`
embeds the entire netloc in its own message, so bounding the value and then
appending the error reintroduced exactly what the bound existed to remove.

**So the rule is now structural, because four call-site fixes were not
enough.** `tests/containment/test_every_message_is_bounded_by_construction.py`
reads the package's syntax tree and requires every value interpolated into
any message to pass through `for_the_record`. A new raise site cannot pass
without it, whether or not anyone remembers the rule exists. One exemption,
named in the test with its reason: `_refuse`'s `why`, which arrives already
composed by a caller whose own interpolations the same scan checks.

**The lesson is the one the canonicaliser taught earlier.** A control
installed on the path where the defect was found, rather than on the class
the defect belongs to, looks installed and is not — and "I checked the other
paths" is not the same as a check. Both times the fix was to move the rule
to the lowest place every path passes through; this time it also needed a
test that reads the code rather than its behaviour.

## T1 — three more checks that could not fail

**Date:** 2026-09-23. Found by the quality review's third pass, and each is
the same shape as one already repaired: a guard defined by a set, with one
witness.

- `_describe`'s `one_of` and `scheme_in` arms could each fall through to the
  `repr` fallback with the suite green. Driven now, and `one_of` on both
  domain types it is expressible on.
- `_AMBIGUOUS_CHARACTERS` is C0 plus DEL and was driven by a tab alone, so
  either edge of the set could move silently — after which a space or a DEL
  reached the adapter inside a canonical path. Both edges have a case.
- `_valid_port`'s lower bound had none, so `:0` was admissible as a port.

And a fifth pass found five more of the same shape, of which one was a hole
rather than only weak evidence:

- **`EXPRESSIBLE_PREDICATES` was pinned by the union of its rows**, so any
  single row could be widened silently. The one that bites is `one_of` on
  `content-locator`: r5 makes that type "membership in the runtime-minted
  set for this step", so a ceiling bounded by a set its author typed instead
  is that row's whole content gone, with every criterion green. The suite
  now compares the table row by row against r5's, restated in the test
  rather than read from the implementation under test, with a negative case
  per row.
- `_ENCODED_SEPARATOR` had a case per alternative and not per member of its
  character classes, all of them lowercase. Percent-encoding is
  case-insensitive, so `%252E%252E` walked out of the path root while the
  gates stayed green.
- The `number` type was only ever driven with a `Decimal`, and a tool
  argument deserialised from a model's JSON arrives as an `int` — the
  admitted path that will actually run had no case. Its `bool` exclusion,
  which stops `True` being read as `1`, had none either.
- `_DEFAULT_PORTS` has two entries and one witness.
- `for_the_record`'s `repr` is there so a control character is escaped
  rather than written into a log line, and only the length half was
  asserted.

Two branches were found unreachable rather than untested, and are recorded
as such in the code: the bracket guards in `_split_authority`, which
`urlsplit` now rejects first, are deleted; the `OSError` and `RuntimeError`
arms of the `realpath` translation are kept, because the platform and not
this package decides whether they can fire.

## T1 — a guard deleted as unreachable, on the wrong evidence

**Date:** 2026-09-23. **The one regression this work introduced, and the
reason it happened is worth more than the fix.**

A quality finding reported two refusals in `_split_authority` as unreachable,
on the evidence that "deleting either leaves the suite green". That evidence
was accepted and one of them was deleted. It was wrong: **a green suite is
evidence about the suite, not about the parser.**

`urlsplit` validates the *netloc*. `_canonicalise_url` then splits the
userinfo off with `rpartition("@")` and hands `_split_authority` a substring
the parser never validated. So a `]` before the last `@` satisfies CPython's
bracket check while the `[` after it goes unclosed in the slice that arrives
— `http://]@[::1/` and `https://a]@[::1/p` both pass the parse — and
`authority.index("]")` then raised a bare `ValueError` out of `evaluate`, for
a value a model can choose. That is the fail direction AC-0315 exists to fix,
reopened.

Two reviewers found it independently, one by fuzzing with `]@[` in its
alphabet and one by re-deriving the composition it had reasoned about the
first time. Neither this package's own generated check nor either reviewer's
earlier sweep reached the ordering, which is why the repair is a **named
case** rather than a wider generator: some shapes are found by construction
and not by search.

The guard is back, with the parser predicate that makes the *other* deletion
sound written beside it — `urlsplit` does refuse trailing text after a closed
literal, checked against CPython rather than inferred. **The rule this
leaves: a guard may be removed as unreachable only against the upstream
predicate that makes it so, read from the thing that enforces it.**

## T1 — the structural rule had the reach its own objection warns about

**Date:** 2026-09-23.

`test_every_message_is_bounded_by_construction.py` was written because four
call-site fixes in a row had missed a sibling path. Its first version walked
for f-string interpolations inside a call to a bare-named message builder —
which is a rule that lists the shapes it knows, one level up from the
mistake it exists to stop. Five ordinary spellings reported nothing while
interpolating raw: a message composed into a local first, `%`-formatting,
`str.format`, concatenation, and a builder reached as an attribute.

It now **rejects by shape rather than detecting by shape**: a message
builder's argument must be a literal, a bounded call, or an f-string whose
every interpolation is bounded, and anything else fails — including a shape
nobody anticipated. It also scans the helpers its own allowlist trusts,
because an allowlisted helper that nothing checks is the hole the allowlist
creates; `_describe`'s fall-through arm, which handles seven of the ten
constructors, was exactly that.

All five evading spellings were checked against the hardened rule and each
is caught.

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

## T1 — what the evidence proves, and how that was checked

**Date:** 2026-09-23. The quality review found that three comparisons
deciding containment — the label boundary in `_in_domain`, the segment
boundary in `_within_path`, and the same in `within(root)` — could each be
deleted with the whole suite green. They are the "passes a string check,
means something else to the callee" shape the spec exists to refuse, one
level in from the canonicaliser, and nothing was on either side of a
boundary. `tests/containment/test_boundaries_are_load_bearing.py` is the
module that fixes it; deleting each boundary now reds 2, 3 and 4 checks
respectively.

Two more pieces of evidence were weaker than they read:

- **`refuse-ambiguous-parse` held four guards and exercised one.** AC-0216
  indexes its evidence per rule, which does not reach inside a rule that
  bundles clauses, so the control-character and invalid-port guards could
  each be deleted with the suite green. The rule is now four rules sharing
  r5's ambiguity clause, each with its own case, and the residual-separator
  pattern has a case per alternative rather than one for `%2e`.
- **Four of `contains`'s ten arms were reached by nothing**, so `Prefix`,
  `Within`, `InMintedSet` and `DateRange` shipped as untested authorization
  logic. The generated pair space covers all ten, and a setup check reads
  the expected set from `EXPRESSIBLE_PREDICATES` so a constructor added to
  the fragment reds until it is generated. Replacing each of the four arms
  with `return True` now reds.

**The property test's independence claim was overstated and is corrected.**
`contains` and the oracle's `admits` share `_in_domain` and `_within_path`,
so a boundary deleted from either helper moves both sides together and the
property stays green. The correction sits in
`test_containment_property.py`'s own docstring, where the claim was made,
and names the module that covers those two arms. An earlier attempt put the
retraction only in the covering module, which left the overstated claim in
the one place a reader goes to size that evidence — the state a false claim
is worst in, because it stops anyone looking. The plan states the same claim
in a pinned `Tests` bullet, which is why it is also recorded above as a plan
error.

**Four more checks that could not fail, found in the same pass and closed the
same way.** A URL's query could be dropped from the canonical rendering with
the suite green, which would hand an adapter a different request from the one
decided. Dot-segment removal's above-root guard could be deleted, turning
`/../x` into the *relative* path `x`. Its trailing-separator fixup had no
case. And `contains`'s documented cross-kind refusal — raise, never `False`,
because two predicates over different components stand in no containment
relation — was reached by nothing, so the raise could have become the `False`
a caller reads as a decision. Each now reds under its own mutation.

**Every claim above was checked by mutation**, not by reading: each boundary,
each new guard, each `contains` arm, and the two fail-closed rules' substitute
checks were deleted or stubbed in turn and the suite re-run.

## T1 — the library exercised as its consumer will use it

**Date:** 2026-09-23. The suite is not the artifact. This is the package
imported and driven from a fresh interpreter outside the repository, the way
`walking-skeleton-policy-decision-point` will drive it.

```
$ .../.venv/bin/python   # from a scratch directory, not the worktree
>>> from ced.domain.containment import declare, evaluate, ...
declared: fetch_filing -> ['path', 'url']
  the in-ceiling call                ADMIT  https://www.sec.gov/evidence/report.pdf
  subdomain-suffix bypass            DENY   argument 'url' is outside "HostInDomain(domain='sec.gov')" …
  userinfo bypass                    DENY   argument 'url' is outside "HostInDomain(domain='sec.gov')" …
  encoded traversal                  DENY   argument 'url' is outside "PathWithin(prefix='/evidence/')" …
  path traversal on fs-path          DENY   argument 'path' is outside "Within(root='/evidence')" …
  ambiguous authority                RAISE  authority 'a@attacker.example@www.sec.gov' carries more than one '@' …
  an argument the ceiling omits      DENY   ceiling entry 'fetch_filing' attaches no predicate to argument 'token' …

authoring refusals:
  prefix on a url                    REFUSE a string prefix is not expressible …
  host_in_domain over a suffix       REFUSE 'gov' is a public suffix …
  url with no host predicate         REFUSE a url argument carries no host-constraining predicate …
```

Three outcomes and no fourth, the documented bypasses refused over the parsed
value, and the positive path admitted with a canonical value carrying no
userinfo, no default port and no dot segments.

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
1 failed, 514 passed, 195 deselected in 12.57s
```
