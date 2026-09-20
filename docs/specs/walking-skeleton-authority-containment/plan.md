# Plan: Walking skeleton — authority containment and the decision point

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r4 §§ The toolset stack and Authority containment. **No analogous production implementation exists.** The substitute is `spikes/phase-0/pydantic_ai_bedrock_spike.py`, which holds executable precedent for the `WrapperToolset` authorization hook. **Named deviation:** that spike's hook appended to a Python list — no database, no second connection, no failed-append path — so it is precedent for the *seam*, not for the mechanism AC-0211 asserts.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-authority-containment/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Build the fragment before the thing that applies it.

The containment fragment comes first, because the policy decision point cannot
refuse on argument value until something can decide what a value means — and the
fragment is where the one unsound constructor in the ratified design was
narrowed. It is a pure domain library: no database, no framework, no agent, so
its property test runs over generated predicate pairs with an oracle that
computes set containment independently of the implementation.

The decision point follows. Its position in the stack is already asserted by
`walking-skeleton-role-compilation` AC-0202. Its refusal direction during the
interval was that spec's AC-0233, which retires with the configuration it names;
AC-0235 here is the permanent guard, because this is where a lookup miss could
become a fall-through and a real lookup is what makes it decidable. What lands here is the predicate, the denial's exception type,
the denial's event, and the two ordering properties that make a failed append a
denial rather than a retry.

**The riskiest part is that a denial degrades quietly into advice.** The
difference between a terminal denial and a retryable hint is which exception a
future contributor raises, and a green suite looks the same either way. AC-0208
asserts the type and that it is not the retry type nor a subclass of it.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — `WrapperToolset.call_tool` as the decision point. ADR-0002 pins 2.45.0.
- `runtime-architecture.md` r7 — ratified with its Known-at-ship gaps accepted **open**.
- `worker-runtime.md` r4 — see § DR dispositions and § Changes asked of r7 below.
- **Hard dependency:** `walking-skeleton-role-compilation` ships the compiler, the four-layer stack and the fail-closed default. Its AC-0234 must stay green across this work; its AC-0233 is scoped to the no-predicate configuration and AC-0235 replaces it here.
- **Hard dependency:** `walking-skeleton-foundation` ships the schema, both append paths, the privilege split and the pool. Nothing here adds a column.
- **Out of scope:** the compiler and the quarantine boundary, owned by `walking-skeleton-role-compilation`, which precedes this spec; the provider call, suspension and persistence, owned by `walking-skeleton-step-lifecycle`, which follows it; the run state machine, publication, the browser stream and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

## DR dispositions

The spec makes changing any DR decision an Ask-first boundary, enforceable only
if each carries a disposition. **This table lists only the DRs this spec
constructs.** A DR absent from it is not this spec's; the Phase 1 routing is the
union of this table, the sibling plans' and the foundation plan's, and no plan
restates another's rows.

| DR | Decision | Disposition |
| --- | --- | --- |
| DR2 | Two database roles, one process | **Consumed here** — the decision point appends through the `policy-writer` identity the foundation spec created. The decision itself is the foundation's, asserted there against real roles |

## Changes asked of r7

**This table lists only the changes this spec constructs.** A change absent from
it is not this spec's, and no plan restates another's rows.

| # | Change | Disposition |
| --- | --- | --- |
| 7 | The decidable fragment is narrowed | **Lands**, T1 — AC-0217 reds if prefix stays expressible on an interpreted type |
| 2 | The behavioural half — a duplicate terminating the step | **Lands**, T2, AC-0212. The schema half is the foundation's |
| 8 | `may_exist`, the authoring-time containment gate | **Deferred** with an owner, recorded in the spec's Follow-ons |

## Grounding

The framework-seam probe is recorded once, in
[`walking-skeleton-role-compilation/plan.md`](../walking-skeleton-role-compilation/plan.md)
§ Grounding probe, and is not repeated here. The row this spec rests on is
`WrapperToolset.call_tool` as an overridable seam with signature
`(self, name, tool_args, ctx, tool)`; that spec's T1 contract suite pins it, so
a version bump reds there rather than in this spec's authorization suite.

### Containment probe

A probe run on 2026-09-18 tested the containment bypasses. Both rows of the r4
table behave as documented. Three things followed:

- A **third bypass** the table omits: `https://www.sec.gov@attacker.example/`, whose userinfo makes a prefix check read the wrong host. The ratified rule handles it because predicates range over parsed components, so this hardens the case set rather than holing the design.
- **Decode-before-normalise is load-bearing and confirmed**, since the encoded traversal survives the reverse order.
- The standard library has **no public-suffix list**, so AC-0215 needs a dataset dependency.

No probe is committed. Its content becomes the containment cases in T1, which is
the ratified mitigation for version drift — exact pins plus contract tests at
both seams — and a throwaway script is not that.

## Construction tests

**Integration tests:**
- One denial end-to-end: a call outside the ceiling reaches the decision point, the `policy.decision` event commits on the `policy-writer` connection, the domain exception raises, and the tool body's spy has not moved. This is the spine AC-0207 through AC-0211 read.

**Manual verification:** none. Every criterion here is machine-checkable.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Decision rationale — the r4 unsafe-prefix table | T1 | The userinfo row added upstream | The table AC-0213 references is complete |
| Current architecture — `docs/architecture/README.md` § What is built | T3 | The containment fragment and the decision point moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Reusable learning — `spikes/README.md` | T3 | A section stating what was and was not established | Hypothesis checks separated from setup |

## Design (LLD)

Shape is `service`; the sub-sections below are the set that shape selects.

### Design decisions

- **Mutation evidence is produced by patching in the test process.** The canonicaliser ships no disable switch: a security control carrying seven runtime bypasses to make its own tests expressible is a worse trade than a slightly more awkward test. Traces to: AC-0216.
- **The fragment is narrowed at authoring time, not at call time.** A predicate a reviewer cannot decide is refused when the role is authored rather than denied when it fires, because a call-time refusal makes an undecidable predicate look like a working one until the wrong argument arrives. Traces to: AC-0215, AC-0217.
- **Containment is asserted at the adapter, not at the validator.** A validator that canonicalises and an adapter that re-parses the original both pass a validator-side assertion while the callee sees the attacker's string. The assertion point is the differential the rule exists to close. Traces to: AC-0214.

### Interfaces & contracts

No external interface. The internal seams are the fragment's authoring surface
(a predicate declaration against a domain-typed argument), the canonicaliser's
input and output, and the decision point's `call_tool` override. Each is
exercised directly by its own suite. Traces to: AC-0215, AC-0217, AC-0207.

### Data & schema

No schema change. This spec reads `agent_role` and `entitlements`, and writes
`events` through the append path the foundation spec owns, on the
`policy-writer` identity that spec created.

### Failure, edge cases & resilience

Two orderings carry the story, both ratified and neither negotiable. The
`policy.decision` event commits **before** the invocation it authorises, on a
second connection, and a failed append is a denial rather than a retry. The
derived idempotency key plus the foundation's partial unique index make a
duplicate invocation fail loudly: the second append raises, the step-event
toolset does not delegate, and the step terminates as duplicate-detected. The
action executes at most once, which is the property the double-publication
hazard needs. Traces to: AC-0211, AC-0212.

### Quality attributes (NFRs)

Attributability is the ratified goal this spec carries, at 100%: every refusal
has a `policy.decision` event naming the acting role and the initiating
principal, and that event is the only place the refusal is recorded. Traces to:
AC-0209.

### Dependencies & integration

New dependencies, recorded before being added per `AGENTS.md`: `hypothesis` (the
containment property test) and `publicsuffix2` (AC-0215 — the standard library
carries no public-suffix list, established by probe). The framework itself is
pinned by `walking-skeleton-role-compilation`; everything else is inherited from
the foundation spec's manifest.

External: none. No task here reaches a provider.

## Tasks

### T1: Containment holds on arguments the callee parses

**Depends on:** none

**Touches:** src/**/domain/containment/**, tests/containment/**

**Tests:**
- AC-0213 uses the r4 table rows verbatim, because they are the documented bypasses and a paraphrase tests a different string, plus the userinfo row the probe found.
- AC-0214 asserts at the *adapter* that the value received is canonical. Asserting at the validator would pass while the adapter re-parses the original, which is the differential the rule exists to close.
- AC-0216 patches one canonicaliser rule at a time in the test process and asserts that rule's case reds while the others stay green. Both halves matter: a patch that reds everything shows the rule set is entangled, not that the rule is load-bearing.
- AC-0215 refuses a public-suffix argument at authoring time, resolved against the bundled dataset rather than a hand-kept list, so a newly delegated suffix does not silently become authorable.
- AC-0217 asserts both directions, because the refusing half alone is satisfied by a fragment that refuses every prefix.
- AC-0218 is the positive path, against the same ceiling AC-0213 uses, so a canonicaliser that refuses all input cannot pass this suite.
- The property test generates predicate pairs over the fragment; the oracle computes set containment independently of the implementation under test.

**Approach:**
- Domain types are `opaque-string`, `url`, `fs-path`, `content-locator`, `enum`, `number`, `date`. The canonicaliser decodes before dot-segment removal, which the probe confirmed is load-bearing and order-dependent.
- File the userinfo row back to the r4 table as an amendment, so the table AC-0213 references stops being incomplete.

**Done when:** AC-0213 through AC-0218 are green and the property test passes over its generated space.

### T2: The decision point is the only way a tool is reached

**Depends on:** T1, and `spec:walking-skeleton-role-compilation/T2`, whose no-predicate configuration this task both replaces and retires

**Touches:** src/**/agents/toolsets/policy_decision.py, src/**/agents/toolsets/step_events.py, tests/authorization/**

**Tests:**
- AC-0207 and AC-0208 are the authorization suite. AC-0208 asserts the exception *type* and that it is not the retry type nor a subclass; a bare "raises" assertion passes on the wrong one, and the wrong one degrades the boundary into a negotiation with no visible failure.
- AC-0209 asserts the denial is *recorded*, which is the attributability claim. A refusal that leaves no trace satisfies AC-0207 and still fails the ratified goal.
- AC-0210 uses a call inside the role ceiling and outside the initiating user's entitlements, which is the conjunct no ceiling-only test reaches.
- AC-0211 forces the decision append to fail on its own connection and asserts the tool body did not run, using a spy the body increments. The spy is what makes "did not run" observable rather than inferred.
- AC-0212 drives two invocations deriving the same key and asserts the body ran once and the step terminated duplicate-detected.
- AC-0236 injects a fault inside the predicate itself, so the error path is exercised rather than a malformed argument that the predicate handles normally. It asserts all three outcomes together — refusal, the committed denial, the unmoved spy — because an error path that denies without recording is the failure this criterion exists to catch.
- AC-0235 drives a call to a tool the acting role has no ceiling entry for, with the real predicate installed and the same spy AC-0211 uses. It is the only check here that a lookup finding nothing denies: AC-0207 needs an entry to fall outside of, and `walking-skeleton-role-compilation`'s AC-0233 was scoped to a configuration this task removes.
- `walking-skeleton-role-compilation` AC-0234 runs unchanged in this task's suite. It asserts a refusal is not the retry type, in every configuration; AC-0208 asserts which domain type it is. The two texts no longer overlap, so neither restates the other.
- AC-0212's mechanism is in the step-event toolset, which `walking-skeleton-role-compilation` composes as a layer but leaves inert. This task gives it the append behaviour, which is why its file is in Touches.

**Approach:**
- The decision point appends through the `policy-writer` identity on a second connection, taking the `steps` fence first so the ordering the foundation spec proved is preserved rather than extended.

**Done when:** AC-0207 through AC-0212, AC-0235 and AC-0236 are green; `walking-skeleton-role-compilation` AC-0234 is still green; and that spec's AC-0233 suite is removed in this task, because the no-predicate configuration it enumerates no longer ships.

### T3: The record says what this spec established and what it did not

**Depends on:** T2

**Touches:** spikes/README.md, docs/architecture/README.md

**Tests:**
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.

**Approach:**
- State plainly that the containment criteria establish the fragment refuses the documented bypasses and the generated predicate space, and establish nothing about a bypass nobody has written down.
- Update `docs/architecture/README.md` § What is built, which is the map where partial progress is expressible. The `STATUS: PLANNED` marker on `worker-runtime.md` is not touched; its header states the condition for its own move and `walking-skeleton-evidence` owns it.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** three stacked PRs — T1, T2, T3. Each leaves the repository working and is independently reviewable.
- **Review shape:** T2 is **DEEP** and is sized as its own PR for that reason: it is security-boundary work that attracts a mandatory security review, and it carries a failure mode that is invisible in a passing suite. T1 is **MIXED** — the fragment plus the canonicaliser plus the property test — and splits at the seam between the fragment and the canonicaliser if the diff outgrows one reviewable unit. No task here is WIDE.

## Risks

- **Denial-as-retry is a one-line footgun.** The difference between a terminal denial and a retryable hint is which exception a future contributor raises. AC-0208 asserts the type; the risk is named because it is the regression reviews miss.
- **The fail-closed default can be quietly widened here.** This is the spec that replaces "nothing admits" with a real lookup, and the cheapest way to make AC-0218's positive path pass is to let a lookup miss fall through. AC-0235 exists for that reason, and `walking-skeleton-role-compilation` AC-0234 runs in T2's suite alongside it.
- **The decision point stands on a framework object.** A change to the wrapper's `call_tool` contract is a change to the authorization boundary and could land in a minor release without being classed as breaking. Mitigated by the contract suite `walking-skeleton-role-compilation` T1 ships and by the authorization suite running on every build.
- **A schema need discovered here is an amendment to a shipped sibling spec.** Mitigated by the foundation spec creating the three agent tables up front, but not eliminated.

## Changelog

- 2026-09-20: initial plan. Cut from `walking-skeleton-agent-runtime`, whose single contract carried AC-0201 through AC-0232 across nine tasks and six stacked PRs. This spec takes the containment fragment and the decision point — the parent plan's T3 and T4, which it had already sized as separate PRs because both attract a mandatory security review. It follows `walking-skeleton-role-compilation` and precedes `walking-skeleton-step-lifecycle`: an earlier draft claimed the last two were parallel, which an adversarial spec review falsified, because that spec's AC-0227 requires an approved tool body to run and nothing can admit a call until this spec's predicate exists.
