# Plan: Walking skeleton — authority containment

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 4 Contracts and Invariants ("Why a prefix predicate is not safe on an interpreted argument"), which states the three rules this fragment implements — domain-typed arguments, predicates over parsed components, and canonical pass-through. **No analogous production implementation exists**, and none is expected: this is a new pure domain library with no framework, database or agent dependency, so there is no seam to ground against. The nearest repository precedent for the *shape* is `src/ced/domain/quarantine/`, a deterministic domain package with its own offline suite. **Named deviation:** that package parses documents and mints identities; it decides no containment relation and carries no property test, so it is precedent for the package shape only.

> **Plan contract:** this is the implementation strategy. It may change
> substantively only while its Status is `Drafting`, before approval records its
> baseline. After approval, `spec.md` and `plan.md` are pinned in substance;
> only lifecycle bookkeeping is permitted, and execution observations belong in
> `docs/specs/walking-skeleton-authority-containment/notes/verification-ledger.md`.
> A genuine artifact error follows the controlled-amendment path.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads, and they are pinned. `Design`, `Approach`, `Grounding`
> and `Risks` are working material that an implementer corrects in place only
> before approval: approval hashes the whole plan. After approval, grounding for
> a seam recorded as `no stub (implementation-discovered)` goes to the
> verification ledger; a settled design decision that execution falsified is a
> plan error that follows the controlled-amendment procedure. Treating them as
> contract is how a review spends a round on prose no gate consumes.
> `Grounding` stays *recorded*, because a per-task resolution nobody wrote is
> not grounding; what it stops being is a claim a reviewer holds the plan to.

## Approach

Build the fragment that decides what a value means, and nothing that applies it.

The fragment comes first in Phase 1 because the policy decision point cannot
refuse on argument value until something can decide what a value *is* — and the
fragment is where the one unsound constructor in the ratified design was
narrowed. It is a pure domain library: no database, no framework, no agent, so
its property test runs over generated predicate pairs with an oracle that
computes set containment independently of the implementation under test.

**The riskiest part is the canonicaliser's rule order.** A probe on 2026-09-18
confirmed that percent-decoding must run before dot-segment removal, because the
encoded traversal survives the reverse order. AC-0216 proves each rule is
present by disabling one at a time; it cannot see a refactor that keeps every
rule and transposes two. The spec carries a `Never do` rule for the ordering and
T1 carries a pinned transposition case, because a criterion that cannot fail on
the real regression is not the control here.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — the framework decision. ADR-0002 pins `pydantic-ai` to 2.45.0. Neither binds this package, which imports no framework; both are listed because the fragment's consumer does.
- `runtime-architecture.md` r8 — ratified with its five accepted limits in § 9 accepted **open**.
- `worker-runtime.md` r5 — see § Amendments the worker runtime asked of its parent below.
- **Hard dependency:** `walking-skeleton-foundation` ships the schema, both append paths, the privilege split and the pool. Nothing here adds a column, and nothing here reaches the database.
- **Placement and re-cut rules:** [`docs/specs/README.md`](../README.md) § Cutting one outcome into several specs.
- **Out of scope:** the policy decision point, its `policy.decision` append, the fence, the duplicate-invocation failure and the grant assertion, all owned by [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md), which installs this fragment and follows this spec; the compiler and the quarantine boundary, owned by `walking-skeleton-role-compilation`; the provider call, suspension and persistence, owned by `walking-skeleton-step-lifecycle`; the run state machine, publication, the browser stream and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

## DR dispositions

**None.** This spec constructs no DR decision. It writes nothing, opens no
connection and holds no runtime identity, so DR2 — two database roles, one
process — is consumed by
[`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/plan.md)
rather than here. The Phase 1 routing is the union of the sibling plans' tables
and the foundation plan's, and no plan restates another's rows.

## Amendments the worker runtime asked of its parent

r5 § 10 Rollout records that every amendment this subsystem required is now
folded into `runtime-architecture.md` r8 and is no longer asked for from here,
so there is nothing left for a spec to disposition. r5 names three as
load-bearing for its § 4 invariants: the fenced policy append, the narrowed
decidable fragment, and scope-qualified object keys.

**One of the three is this spec's.** The narrowed decidable fragment is T1's,
asserted by AC-0217, which reds if prefix stays expressible on an interpreted
type. The fenced policy append is
[`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/plan.md)'s.

## Grounding

### Containment probe

A probe run on 2026-09-18 tested the containment bypasses. Both rows of the r5
table behave as documented. Three things followed:

- A **third bypass** the table omits: `https://www.sec.gov@attacker.example/`, whose userinfo makes a prefix check read the wrong host. The ratified rule handles it because predicates range over parsed components, so this hardens the case set rather than holing the design.
- **Decode-before-normalise is load-bearing and confirmed**, since the encoded traversal survives the reverse order. This is the finding the spec's `Never do` rule and T1's transposition case exist to hold; it is recorded here as the evidence, not as the control.
- The standard library has **no public-suffix list**, so AC-0215 needs a dataset dependency.

No probe is committed. Its content becomes the containment cases in T1, which is
the ratified mitigation for version drift — exact pins plus contract tests at
both seams — and a throwaway script is not that.

## Construction tests

**Cross-cutting tests:** the property test over generated predicate pairs spans
the fragment and the canonicaliser, so it is listed once here rather than under
either alone. Its oracle computes set containment independently of the
implementation under test; a property test whose oracle shares the
implementation's parser proves only that the parser agrees with itself.

**Integration tests:** none. Nothing here crosses a process or storage boundary.
The end-to-end denial spine belongs to
[`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/plan.md).

**Manual verification:** none. Every criterion here is machine-checkable.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Decision rationale — the r5 unsafe-prefix table | T1 | The userinfo row added upstream | The table AC-0213 references is complete |
| Current architecture — `docs/architecture/README.md` § What is built | T2 | The containment fragment moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Reusable learning — `spikes/README.md` | T2 | A section stating what was and was not established | Hypothesis checks separated from setup |

## Design (LLD)

Shape is `service`; the sub-sections below are the set that shape selects.
`Data & schema` is omitted: this spec reads and writes no persistent state.

### Design decisions

- **Mutation evidence is produced by patching in the test process.** The canonicaliser ships no disable switch: a security control carrying seven runtime bypasses to make its own tests expressible is a worse trade than a slightly more awkward test. Traces to: AC-0216.
- **The fragment is narrowed at authoring time, not at call time.** A predicate a reviewer cannot decide is refused when the role is authored rather than denied when it fires, because a call-time refusal makes an undecidable predicate look like a working one until the wrong argument arrives. Traces to: AC-0215, AC-0217, AC-0240.
- **Containment is asserted at the adapter, not at the validator.** A validator that canonicalises and an adapter that re-parses the original both pass a validator-side assertion while the callee sees the attacker's string. The assertion point is the differential the rule exists to close. Traces to: AC-0214.
- **Percent-decoding precedes dot-segment removal, and the order is pinned by a case rather than inferred.** Traces to: AC-0216.
- **A ceiling entry constrains every argument it names, or it is not a ceiling.** r5's conjunction is vacuously true on any argument no predicate ranges over, so the fragment refuses such an entry at authoring time and denies it at evaluation. Guarding only the authoring surface would leave an entry inserted by migration admitting everything. Traces to: AC-0316, AC-0317.
- *Owned by:* T1.

### Interfaces & contracts

No external interface. The internal seams are the fragment's authoring surface
(a predicate declaration against a domain-typed argument), the canonicaliser's
input and output, the canonical value handed to the consuming adapter, and the
`CeilingResolver` shape the decision point consumes — including the exception
it raises on an input it cannot decide.
Each is exercised directly by its own suite. Traces to: AC-0215, AC-0217,
AC-0240, AC-0214, AC-0315. *Owned by:* T1.

### Failure, edge cases & resilience

The fragment has one failure direction and it is refusal. An argument it cannot
parse, a domain type it does not recognise, and a predicate it cannot decide are
all refused rather than admitted or passed through — at authoring time by
AC-0215, AC-0217 and AC-0240 where the declaration can be judged, and at
evaluation time by AC-0315, which fixes the signal as a raise. What the
consumer then *does* with that raise is the decision point's question, not this
package's, and is
[`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md)'s
AC-0236. Traces to: AC-0215, AC-0217, AC-0240, AC-0315. *Owned by:* T1.

### Quality attributes (NFRs)

No NFR with a pass/fail bar applies. The fragment's quality claim is
correctness, carried by the property test rather than by a threshold.
*Owned by:* T1.

### Dependencies & integration

New dependencies, recorded before being added per `AGENTS.md`: `hypothesis` (the
containment property test) and `publicsuffix2` (AC-0215 — the standard library
carries no public-suffix list, established by probe). Everything else is
inherited from the foundation spec's manifest.

External: none. No task here reaches a provider or a database. *Owned by:* T1.

## Tasks

### T1: Containment holds on arguments the callee parses

**Depends on:** none

**Touches:** src/ced/domain/containment/**, tests/containment/**, docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md

**Tests:**
- AC-0213 uses the r5 table rows verbatim, because they are the documented bypasses and a paraphrase tests a different string, plus the userinfo row the probe found.
- AC-0214 asserts at the *adapter* that the value received is canonical. Asserting at the validator would pass while the adapter re-parses the original, which is the differential the rule exists to close. **No production adapter consumes the canonical value in this spec's scope** — `src/ced/adapters/` holds the framework contract and the Postgres adapters, and the tool-call path that will consume it is the decision point's, one spec over. T1 therefore asserts against a test double standing in for that consumer, which establishes the fragment *emits* the canonical value and **does not** establish that the production consumer declines to re-parse the original. The production-side half is asserted in [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/plan.md) T1, and this bullet is the record that T1 alone does not close the differential.
- AC-0216 patches one canonicaliser rule at a time in the test process and asserts that rule's case reds while the others stay green. Both halves matter: a patch that reds everything shows the rule set is entangled, not that the rule is load-bearing.
- **A transposition case pins the rule order**, separately from AC-0216: with percent-decoding and dot-segment removal swapped and every rule still present, the encoded-traversal input is admitted and the case reds. AC-0216 cannot reach this — it disables rules, never reorders them — and the probe established the order is load-bearing, so without this case a reordering refactor ships green. This row is pinned; it is the only gated check on the ordering the spec's `Never do` rule states.
- AC-0240 refuses a `url`-typed argument carrying no host-constraining predicate, alongside AC-0215 and AC-0217, because all three are authoring-time refusals over the same declaration surface.
- AC-0215 refuses a public-suffix argument at authoring time, resolved against the bundled dataset rather than a hand-kept list, so a newly delegated suffix does not silently become authorable.
- AC-0217 asserts both directions, because the refusing half alone is satisfied by a fragment that refuses every prefix.
- AC-0218 is the positive path, against the same ceiling AC-0213 uses, so a canonicaliser that refuses all input cannot pass this suite.
- AC-0316 declares a ceiling entry naming an argument with no predicate attached and asserts the authoring surface refuses it, naming the entry and the argument. AC-0317 installs such an entry **directly, bypassing the authoring surface**, and asserts evaluation denies — the two cannot share a case, because AC-0316 makes AC-0317's input unreachable through the front door, and an entry that arrives by migration or by a role authored before the refusal existed is exactly what AC-0317 is for.
- AC-0218 asserts the fragment returns an admitting result and stops there. It does not assert a tool body executes; nothing in this package can run one, and that half is `walking-skeleton-policy-decision-point`'s AC-0318.
- AC-0315 drives each of the three undecidable shapes separately — an unrecognised declared domain type, an ambiguous parse, and a predicate the fragment cannot evaluate against the given value — and asserts each raises. A single combined case would pass on a fragment that raises for one shape and returns "inside" for the other two, which is the fail-open the criterion exists to close. The raise is the seam signal `walking-skeleton-policy-decision-point`'s AC-0236 receives, so this task also asserts the exception type is the one that spec's decision point treats as a denial rather than a defect.
- The property test generates predicate pairs over the fragment; the oracle computes set containment independently of the implementation under test.

**Approach:**
- Domain types are `opaque-string`, `url`, `fs-path`, `content-locator`, `enum`, `number`, `date`. The canonicaliser decodes before dot-segment removal, which the probe confirmed is load-bearing and order-dependent.
- File the userinfo row back to the r5 table as an amendment, so the table AC-0213 references stops being incomplete.

**Done when:** AC-0213 through AC-0218, AC-0240 and AC-0315 through AC-0317 are green, the r5 unsafe-prefix table carries the userinfo row, the transposition case is green and reds when the two rules are swapped, and the property test passes over its generated space.

### T2: The record says what this spec established and what it did not

**Depends on:** T1

**Touches:** spikes/README.md, docs/architecture/README.md

**Tests:**
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.

**Approach:**
- State plainly that the containment criteria establish the fragment refuses the documented bypasses and the generated predicate space, and establish nothing about a bypass nobody has written down.
- Update `docs/architecture/README.md` § What is built, which is the map where partial progress is expressible. Move the containment fragment only; r5's STATUS header names the *authorization boundary*, which is not built until the decision point ships, so that marker is not touched here.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** two stacked PRs — T1, T2. Each leaves the repository working and is independently reviewable.
- **Review shape:** T1 is **MIXED** — the fragment plus the canonicaliser plus the property test — and splits at the seam between the fragment and the canonicaliser if the diff outgrows one reviewable unit. No task here is WIDE or DEEP; the DEEP lobe left with the decision point.

## Risks

- **A reordering refactor is invisible to the criterion set.** AC-0216 proves each canonicalisation rule is present and cannot prove the order. Mitigated by T1's pinned transposition case and the spec's `Never do` rule, not by a criterion — which is why the gap is also recorded in § Follow-ons.
- **The public-suffix dataset ages.** A newly delegated suffix that the bundled dataset does not carry becomes authorable until the dependency is bumped. Named rather than mitigated; Phase 1 registers no URL-taking tool.
- **The fragment can ship correct by being useless.** A canonicaliser that refuses everything satisfies every refusal criterion. AC-0218 is the only thing standing against it here, and it now stops at the fragment's own answer — the tool-body half moved to `walking-skeleton-policy-decision-point`'s AC-0318, so neither spec alone proves the positive path end to end.

## Changelog

- 2026-09-20: initial plan. Cut from `walking-skeleton-agent-runtime`, whose single contract carried AC-0201 through AC-0232 across nine tasks and six stacked PRs. This spec takes the containment fragment and the decision point — the parent plan's T3 and T4, which it had already sized as separate PRs because both attract a mandatory security review. It follows `walking-skeleton-role-compilation` and precedes `walking-skeleton-step-lifecycle`: an earlier draft claimed the last two were parallel, which an adversarial spec review falsified, because that spec's AC-0227 requires an approved tool body to run and nothing can admit a call until this spec's predicate exists.
- 2026-09-20: spec approved by eugenelim
- 2026-09-20: plan approved by eugenelim
- 2026-09-22: returned to `Draft`/`Drafting` by owner decision for a controlled amendment, authorized to do four things: migrate the spec to the current `new-spec` template shape; keep only unresolved items in § Assumptions; tighten the obligation table's prose; and update both contract notes. Declined in the same decision: reworking the four carried-across criterion-wording defects in § Follow-ons. A second owner decision the same day cut the decision-point lobe out to [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md), moving AC-0207 through AC-0212, AC-0235, AC-0236, AC-0239, AC-0243, AC-0247, AC-0249 and AC-0252 with it, and this spec keeps AC-0213 through AC-0218 and AC-0240. Round-1 spec-stage adversarial and security findings of the same date are applied. **2026-09-23:** round-2 findings applied against the split pair. This spec gained **AC-0315**, authored to close a fail-open state the cut created — the fragment's answer on an input it cannot decide was owned by neither spec — authorized by the owner on 2026-09-23 as a reviewed exception to the criteria-frozen scope. AC-0240's obligation row was corrected twice and now states what the criterion actually requires: a host-constraining predicate must be present, and neither the host it names nor the address that name resolves to is constrained; both gaps are recorded in § Follow-ons as unowned. **2026-09-23, round 3:** the review loop was stopped by owner decision rather than run to clean. Findings rose 19 → 21 → 29 across three rounds and both reviewers independently measured about half of round 3 as introduced by round-2 repairs, which is the diverging-loop condition `work-loop` says to surface rather than repair through. Four contract-level findings were applied and the rest recorded or left: this spec gained **AC-0316 and AC-0317**, closing a default-allow that predates the cut — r5's per-argument conjunction is vacuously true on any argument a ceiling entry names no predicate for, so an `fs-path` with no root admitted `/etc/passwd` with every criterion green. **AC-0218** was restated to what a pure domain library can observe; its tool-body clause moved to `walking-skeleton-policy-decision-point`'s AC-0318. T1's `Touches` gained the r5 architecture file its own Approach edits. The open class the loop kept circling — pinning a cross-boundary exception type in prose — is deliberately left for T1 to settle in code. **Re-approval of both gates is owed to eugenelim.**
- 2026-09-23: spec approved by eugenelim
- 2026-09-23: plan approved by eugenelim
- 2026-09-23: returned to `Draft`/`Drafting` by owner decision for a second controlled amendment, authorized to do one thing: reword AC-0216. T1's implementation established that two of the six clauses r5 names under "What the canonicalizer must do" cannot supply the evidence the criterion asked for. Dropping a default port cannot change an admit-or-deny outcome under **any** implementation of this fragment, because no predicate in r5's `url` row ranges over a port. Case-folding a host can only shrink what is admitted, because a ceiling's host argument is already folded when it is compared, and the clause's other half — leaving the path alone — is not an operation and so has nothing to remove. Two reviewers swept independently for a counterexample, one over 7,488 combinations of uppercase, punycode, IDN and ported hosts, and found none. The amendment keeps the criterion's force — no rule ships unexercised — and replaces one shape of evidence with two, the second being a normalisation check, a fail-closed check over a universe the rule acts on, and a recorded reason. **The first implementation attempt met the old wording by substituting a miswrite for a removal**, which is what a criterion demanding impossible evidence buys; that attempt is recorded in the verification ledger and was withdrawn. Declined in the same decision: accepting a miswrite as "disabled", which would weaken the criterion wherever it is later applied and in any case rescues only one of the two clauses; and turning `drop default ports` from a normalisation into a refusal, which changes a ratified rule so that a test becomes expressible.
- 2026-09-23: three refusals T1 made beyond the criteria ratified by eugenelim, each recorded in `spec.md` § Follow-ons with its grounds — a `url` argument must carry a scheme-constraining predicate, a call must supply every argument the entry constrains, and a `within` root must be absolute and not the filesystem root. None gains a criterion; what changed is that each is a decided behaviour rather than an unratified one.
- 2026-09-23: the public-suffix dependency decided by eugenelim. `publicsuffix2` bundles a 2019-12-21 snapshot and has shipped no release since, so a suffix delegated after that date is authorable against AC-0215. **The dependency stays**: nothing in Phase 1 registers a URL-taking tool, so nothing can reach the gap, and a swap would buy a review round against a risk nothing can reach. Declined in the same decision: replacing the dataset now. Recorded rather than triggered — an earlier wording of the § Follow-ons entry called the backlog record a trigger a reader of the queue would meet, which it is not, because integrations are data and registering a URL-taking tool is an operator insert that opens no pull request. Enforcement belongs to the path that compiles a ceiling from a registry row, which [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/plan.md) owns.
- 2026-09-23: the amendment's own first wording corrected before approval, on review. AC-0216's weaker limb had stated one ground — no predicate ranges over what the rule normalises — which admits `drop default ports` and **not** case-folding a host, since `host_eq` and `host_in_domain` both range over the host; the limb one of its two rules actually qualifies under is monotonicity against an already-canonical ceiling argument. Both grounds are now stated, both are derived from `EXPRESSIBLE_PREDICATES` by a check rather than asserted in a constant, and a predicate constructor added to the fragment is an amendment trigger alongside a rule added to r5's list. The scheme ratification was corrected on the same pass: requiring a scheme predicate's *presence* does not close the `file:` case its recorded grounds name, so the refusal now bounds the set to what r8 § 4's egress proxy can carry.
- 2026-09-23: spec approved by eugenelim, second amendment
- 2026-09-23: plan approved by eugenelim, second amendment
