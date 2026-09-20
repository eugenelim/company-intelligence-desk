# Spec: Walking skeleton — authority containment and the decision point

- **Status:** Approved <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md), ADR-0002 (version pin, created by the foundation spec)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § 10 Rollout, Phase 1
- **Discovery:** none
- **Contract:** none — this spec exposes no interface surface; it is reached through the foundation spec's API and the evidence spec's state machine
- **Shape:** service

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Boundaries`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Objective`, `Durable Outputs`, `Follow-ons` and `Assumptions`
> are working material, corrected in place without an amendment.

## Objective

The security core of the Phase 1 agent runtime. It builds the containment
fragment that decides what a tool call may carry, and the policy decision point
that applies it — the outermost layer of the toolset stack that
[`walking-skeleton-role-compilation`](../walking-skeleton-role-compilation/spec.md)
composes.

Security of the agent-authority boundary is the architecture's second-ranked
quality attribute and no managed control covers it. This is the spec that makes
it executable.

Success is that an unauthorised tool call is refused on its *argument value*
before the tool body runs, with the refusal recorded as an event; that a value
which passes a string prefix check but means something else to the callee is
refused; and that a predicate a reviewer cannot decide cannot be authored in the
first place. Each of those is currently a design claim with no executable
evidence.

**Its siblings.** [`walking-skeleton-foundation`](../walking-skeleton-foundation/spec.md)
owns the schema, both append paths, the privilege split and the pool.
`walking-skeleton-role-compilation` is a hard dependency: it ships the compiler,
the four-layer stack and the fail-closed default this spec replaces with a real
predicate. [`walking-skeleton-step-lifecycle`](../walking-skeleton-step-lifecycle/spec.md)
follows this spec, because resuming a suspended step means an approved tool body
runs and nothing can admit a call until this spec's predicate exists.
[`walking-skeleton-evidence`](../walking-skeleton-evidence/spec.md) consumes all
three.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Decision rationale | Applicable — the r5 containment table omits a bypass this spec's criteria carry | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` § 4, "Why a prefix predicate is not safe on an interpreted argument" | work-loop | The userinfo row added to the unsafe-prefix table | The criterion's referenced table is complete |
| Current architecture | Applicable — `docs/architecture/README.md` § What is built is the current map and this spec changes it | `docs/architecture/README.md` § What is built | work-loop | The containment fragment and the decision point moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Current architecture — the `worker-runtime.md` marker | Applicable — r5's STATUS header names the authorization boundary as unbuilt, and this spec builds it | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` header | work-loop | The authorization boundary moved from unbuilt to built, the other clauses untouched | The header's built and unbuilt lists match the repository |
| Reusable learning | Applicable — this spec produces the containment evidence Phase 2 plans against | `spikes/README.md` | work-loop | A section stating what was established **and what was not** | Hypothesis checks reported separately from setup |
| Interface compatibility | Not applicable — no interface surface; the API belongs to the foundation spec | — | — | — | — |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Boundaries

### Always do

- Treat r8 and r5 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision. The plan gives every DR decision this spec constructs a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No test-only bypass surface inside a shipped security control.** Mutation evidence is produced by patching in the test process, never by a switch the production canonicaliser carries.
- **No widening of the fail-closed default.** Replacing "nothing admits" with a real lookup must not turn a lookup miss into a fall-through. AC-0235 is the guard, and `walking-skeleton-role-compilation`'s AC-0234 — a refusal is never `ModelRetry` nor a subclass — stays green across this spec's work.
- **No `pydantic_ai` import outside `agents/` and `adapters/`.**

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0207, AC-0208, AC-0209, AC-0210, AC-0211, AC-0212, AC-0213, AC-0214, AC-0215, AC-0216, AC-0217, AC-0218, AC-0235, AC-0236, AC-0239, AC-0240, AC-0243, AC-0247, AC-0249, AC-0252)** — all of it, because all of it is a compressible invariant with a cheap oracle and no provider in the loop. The framework ships `TestModel` and `FunctionModel`, so the containment fragment and the decision point are both exercised without a model call. The containment criteria (AC-0213 through AC-0218) additionally carry a *property test* over generated predicate pairs, because the claim is set-theoretic containment over a fragment rather than behaviour at chosen values.

No criterion here calls a provider, so this spec needs no cloud credential and
carries no spend. AC-0209, AC-0211, AC-0212, AC-0236, AC-0239, AC-0243 and AC-0249 reach
the database, which the foundation spec's local substrate supplies.

## Acceptance Criteria

Obligations come from `runtime-architecture.md` § 10 Rollout, Phase 1 criterion 6 —
"attempt a well-typed unauthorised tool call and observe refusal" — and from
`worker-runtime.md` § 10 Rollout criteria 5 (commit-before-action under failure)
and 8 (the containment property test with interpreted arguments). Those three
sources cover AC-0207, AC-0211, AC-0213, AC-0214 and AC-0215. AC-0209 is
source-derived too, from r5 § 4's gate block — `may_act(call)` is "recorded as
the `policy.decision`" at call time, on both the admit and the refuse path —
rather than from a § 10 Rollout criterion, which is why it is not tabled below. Obligations
**beyond** them are tabled below, and the approval gate rules on each rather
than inheriting it.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Make a denial catchable without swallowing bugs | AC-0208 | r5 § 2 Structural Model, the toolset stack makes the denial terminal, but no § Rollout criterion asserts how a caller tells a denial apart from a defect. That the refusal is not `ModelRetry` is `walking-skeleton-role-compilation`'s AC-0234, which holds from the first refusal; this criterion asserts a different property, that the denial handler is narrow enough not to catch a tool-body bug | A denial handler swallows genuine defects, and the boundary reports a clean refusal where the system is actually broken |
| Fence the decision append on the caller's own epoch | AC-0239 | r5 § 4 Contracts and Invariants makes the fenced append the control, and the foundation spec built it correctly. Its efficacy rests entirely on the decision point passing the epoch it holds: one that re-reads the current epoch from the database defeats the fence and passes AC-0209, AC-0211 and the foundation's AC-0004 alike. r5 § 4 gives the failure semantics as the fenced worker's decision rolling back, and § 7 prices the consequence as a report published twice | The fence is present, bypassable from the one call site that matters, and green everywhere |
| Bound a `url` argument by host | AC-0240 | AC-0215 and AC-0217 narrow a predicate's *form*; neither requires the set on a `url` argument to constrain the host. A ceiling of `scheme_in{https}` alone is well-formed and admits the instance metadata endpoint — which AC-0224 requires the container to reach. The compensating control r5 and r8 both name, an egress proxy with a hostname allowlist, is part of the AWS deployment these specs place out of scope. **AC-0240 bounds the name, not the resolved address**; address-level confinement stays with that proxy and is not claimed here | The fragment ships able to express a ceiling that authorises SSRF, and the only thing stopping it is that Phase 1 registers no URL-taking tool |
| Force the append failure on a call that would otherwise run | AC-0243 | AC-0211 does not say the call under test is one the predicate admits. Forcing the append to fail on a call that was going to be refused anyway leaves the spy unmoved whatever the ordering, so commit-before-action can be unimplemented with AC-0211 green. AC-0218 is the only admit-path criterion and carries no append-failure case | The ratified ordering is asserted by a test that cannot observe it |
| Decide the undecidable append failure | AC-0252 | AC-0211 and AC-0243 terminate the step, AC-0239 abandons it on an attributable fence loss, and the discriminator is whether the fence was held. That is knowable from the serialization failure `append_policy_decision` raises and not from a connection-level failure, where the worker cannot tell whether the transaction reached the fence at all. Without a stated direction the exception handler picks one by accident. Terminate rather than abandon, because abandoning turns an authorization decision that could not be recorded into a lease-expiry reclaim and a silent re-execution — the denial-becomes-a-retry shape the design forbids everywhere else | The three criteria partition the space they name and leave a real state outside it, decided by catch order |
| Deny an evaluation that raises | AC-0236 | Three states can reach the decision point: no entry, an entry whose value is outside, and an entry whose evaluation raises — a malformed ceiling row, an unparseable value, a public-suffix dataset that fails to load, an unknown domain type. AC-0235 and AC-0207 cover the first two. Nothing covers the third, and whichever `except` an implementer writes around the predicate silently decides the boundary | The fail direction on an error path is chosen by accident, and no test can go red on the wrong choice |
| Deny a lookup that finds nothing | AC-0235 | `walking-skeleton-role-compilation`'s AC-0233 covers the interval before any predicate exists and cannot be decided once one does. This is the permanent guard: replacing "nothing admits" with a real lookup is exactly where a miss becomes a fall-through, and no other criterion here reaches it — AC-0207 needs a ceiling entry to fall outside of | The split's cheapest regression ships unobserved: a role with no entry for a tool runs it |
| Enforce the entitlements conjunct | AC-0210 | `may_act` is a conjunction of ceiling **and** initiating-user entitlements; a criterion covering only the ceiling half leaves the other unbuilt | Half the authorization predicate ships unverified |
| Assert the grant the split rests on | AC-0249 | r5 § 6 says the privilege split's strength "rests on the database grant rather than on credential separation", and § 4 states the invariant over every runtime identity: no runtime identity holds write on `agent_role` or the integration registry. `0001_base_schema.py` grants the same SELECT to `app_api` as to `app_worker`, so a criterion naming only one covers half the invariant. Every authorization criterion here presumes the identity being constrained cannot rewrite the constraint. That presumption is one `GRANT SELECT` line in `migrations/versions/0001_base_schema.py` that no test would notice losing; the foundation's AC-0005 asserts the adjacent event-type case and not this one | The elevation-of-privilege case the whole design is built against is unasserted, and a migration edit silently removes it |
| Fail a duplicate invocation loudly | AC-0212 | r5 identifies the derived key plus the index as the sole mechanism making the double-publication hazard fail rather than execute twice | The at-most-once control ships with its behaviour untested |
| Prove each canonicalisation rule is load-bearing | AC-0216 | r5 criterion 8 asks for the table rows, the adapter assertion and the public-suffix refusal. It does not ask whether any individual rule in § 4, "Why a prefix predicate is not safe on an interpreted argument"'s "What the canonicalizer must do" list actually carries weight, and a rule nobody's case exercises is indistinguishable from an absent one | A canonicaliser can lose a rule in a refactor with every test still green |
| Narrow the decidable fragment at authoring time | AC-0217 | This is the narrowed decidable fragment amendment, which narrows the ratified fragment; it is a design change this spec implements rather than a § Rollout criterion | A prefix predicate stays expressible on an interpreted type, which is the one unsound constructor the change exists to remove |
| Exercise the trust-class layer, not just its position | AC-0247 | r5 § 2 makes that layer's innermost position a security property because it must parse an integration's result *before* any layer above observes the return value. `walking-skeleton-role-compilation` AC-0202 asserts the layer is in the chain and AC-0242 covers the retrieval path; nothing asserts the layer parses a **tool return** — AC-0220 covers the same parser on the retrieval path — and this is the first spec where a tool body runs at all | The layer is composed by one criterion and exercised by none, and free text reaches the attribution record by the one path r5 positions it to block |
| Admit the positive path | AC-0218 | Every other containment criterion is a refusal, and a canonicaliser that refuses all input satisfies all of them | The fragment ships correct by being useless, and nothing catches it |

**Authorizing a call**

- [ ] **AC-0207.** A well-typed tool call whose argument *value* falls outside the acting role's ceiling is refused, and the tool body does not execute.
- [ ] **AC-0235.** A tool call for which the acting role holds no ceiling entry at all is refused and the tool body does not execute, asserted with the containment predicate installed, so a lookup that finds nothing denies rather than falling through.
- [ ] **AC-0239.** A decision point whose step lease has been taken by another worker, observed as the serialization failure the fenced append raises, refuses the call, does not execute the tool body, and leaves no committed `policy.decision`. The evicted worker abandons the step to its new owner rather than failing it.
- [ ] **AC-0252.** An append failure the worker cannot attribute to fence loss is treated as fence-held: the worker attempts to terminate the step, as AC-0211 and AC-0243 require. Where the worker had in fact been evicted, that termination is itself a fenced write and the database refuses it, leaving the true owner untouched.
- [ ] **AC-0243.** With the `policy.decision` append forced to fail on its own connection inside the decision point while the fence is still held, on a call the installed predicate **admits**, the tool body does not execute and the step terminates.
- [ ] **AC-0236.** A predicate evaluation that raises — driven by a fault patched into the predicate **in the test process**, not by a malformed argument and not by a switch the shipped predicate carries — refuses the call, commits the `policy.decision` denial, and does not execute the tool body.
- [ ] **AC-0208.** A refusal by the decision point raises a domain exception a caller can catch without also catching a programming error, demonstrated by a case in which a genuine bug raised inside a tool body is not caught by the denial handler.
- [ ] **AC-0209.** A call the containment predicate decides — admitted or refused — commits a `policy.decision` event recording the decision, the acting agent role, and the initiating principal, before the tool body runs or the refusal is raised. AC-0211, AC-0239, AC-0243 and AC-0252 govern the cases where that append does not succeed.
- [ ] **AC-0210.** A call whose arguments fall inside the acting role's ceiling but outside the initiating user's entitlements is refused.
- [ ] **AC-0211.** With the `policy.decision` append forced to fail on its own connection inside the decision point while the fence is still held, the tool body does not execute and the step terminates.
- [ ] **AC-0212.** A second invocation deriving an idempotency key already recorded for the run terminates the step as a duplicate-detected failure, and the tool body executes at most once across both attempts.

**Holding the layers and grants the boundary rests on**

- [ ] **AC-0247.** A tool return from an integration declared `admitted-types` that carries free text is refused by the trust-class layer before any layer above it observes the value, so neither the step-event toolset's attribution record nor the agent ever sees it.
- [ ] **AC-0249.** A connection on any runtime identity — `app_worker` or `app_api` — attempting to write `agent_role`, `integration_registry` or `entitlements` is refused by the database.

**Containing an interpreted argument**

- [ ] **AC-0213.** Every row of `worker-runtime.md` § 4, "Why a prefix predicate is not safe on an interpreted argument"'s unsafe-prefix table is refused, plus the userinfo case `https://www.sec.gov@attacker.example/`, which a prefix check admits while the parsed host is `attacker.example`. A row added to that table upstream is an amendment trigger for this criterion.
- [ ] **AC-0214.** The adapter observes the canonical value rather than the original string, asserted at the adapter rather than at the validator.
- [ ] **AC-0215.** Declaring a domain-containment predicate whose argument is a public suffix is refused at authoring time, resolved against a public-suffix dataset rather than a hand-kept list.
- [ ] **AC-0216.** For every canonicalisation rule `worker-runtime.md` § 4, "Why a prefix predicate is not safe on an interpreted argument" names under "What the canonicalizer must do", the suite holds an input that the canonicaliser refuses and that is admitted when that one rule is disabled by patching the canonicaliser **in the test process**. Disabling one rule reds that rule's case and leaves the others passing. A rule added to that list upstream is an amendment trigger for this criterion.
- [ ] **AC-0240.** Declaring a `url`-typed argument with no host-constraining predicate is refused at authoring time.
- [ ] **AC-0217.** Declaring a prefix predicate on an argument whose domain type is `url`, `fs-path`, or `content-locator` is refused, and the same predicate on `opaque-string` is accepted.
- [ ] **AC-0218.** A canonical in-ceiling `url` and an in-root `fs-path` are admitted against the same ceiling AC-0213 uses, and the tool body executes.

## Follow-ons

Every item below is a criterion-wording defect a spec-stage shaping or security
review found in text this spec carries unchanged from the deleted
`walking-skeleton-agent-runtime`. They were left unreworded by owner decision of
2026-09-20, so the carry-across stays auditable against the parent; each needs an
amendment rather than an in-place correction.

- eugenelim: `workspace.toml` `[backlog].open` — **AC-0213 double-counts the row its own task files upstream.** T1 amends the r5 unsafe-prefix table to add the userinfo row, after which the criterion's "plus the userinfo case" names a row already in the table and its own amendment trigger fires on the change the task made.
- eugenelim: `workspace.toml` `[backlog].open` — **AC-0216 proves rule presence, not rule order.** Disabling one canonicalisation rule at a time cannot see a refactor that keeps every rule and transposes percent-decode with dot-segment removal, which the plan's own probe records as load-bearing.
- eugenelim: `workspace.toml` `[backlog].open` — **AC-0217 hand-enumerates three of seven domain types.** r5 states the rule at the level of "not parsed by their consumer"; adding an interpreted type later leaves the criterion green and the fragment unsound.
- eugenelim: `workspace.toml` `[backlog].open` — **no explicit symlink case.** r5 requires normalisation to resolve symlinks, but AC-0213's enumerated cases are all name-only, so CWE-59 confinement escape rests on an implementer reading one prose clause as a listed rule.

- eugenelim: `workspace.toml` `[backlog].open` — **`may_exist`, the authoring-time containment gate** (`worker-runtime.md` r5 § 4's third gate, `may_exist`). Designed, not built. The charter holds the substrate single-author in operation until the governance gaps are *built*, and this is one of them; a single operator authors every role here, which is the condition that makes deferring it safe.
- eugenelim: `workspace.toml` `[backlog].open` — **`may_run`, the spawn-time containment gate.** Recording `role.ceiling ⊆ parent_role.ceiling` as an event at spawn needs a coordinator that spawns children, which this skeleton's single analysis step does not exercise. Named rather than absent.

## Assumptions

- Technical: `pydantic-ai` is pinned to 2.45.0 rather than ADR-0001 D5's 2.44.0 (source: user decision 2026-09-18). The framework-seam probe that established this is recorded once, in `walking-skeleton-role-compilation/plan.md` § Grounding probe; this spec cites it there rather than repeating it.
- Technical: refusing a public-suffix argument needs a public-suffix dataset; the standard library has none (source: probe against `urllib`, 2026-09-18).
- Technical: both rows of the r5 unsafe-prefix table behave as documented, a third bypass exists that the table omits, and decode-before-normalise is load-bearing and order-dependent (source: probe, 2026-09-18, recorded in `plan.md` § Containment probe).
- Technical: `walking-skeleton-role-compilation` ships the compiler, the four-layer toolset stack and a decision point that admits nothing without a predicate. This spec supplies that predicate and composes no new layer. Its AC-0233 is scoped to the no-predicate configuration and retires with it; AC-0235 here is the permanent replacement, and AC-0234 stays green unchanged (source: `walking-skeleton-role-compilation/spec.md` AC-0202, AC-0233 and AC-0234).
- Process: three criteria carried into *this spec* have had their wording changed. **AC-0209 and AC-0211** were scoped on 2026-09-20 by owner ruling, after an adversarial review found them universally quantified over refusals while AC-0239 names a refusal that records nothing and a step that is abandoned rather than failed: AC-0209 now covers a call the containment predicate **decides**, admitted or refused, and names the four criteria that govern a failed append; a first attempt scoped it by fence liveness, which two reviewers showed is the variable separating abandon from terminate rather than recorded from unrecorded. AC-0211 covers an append forced to fail **while the fence is still held**. Without those qualifiers no implementation satisfied all four criteria, and no added criterion can repair a false universal claim. Neither scoping widens authority; each narrows a claim to the states it was always meant to cover. **AC-0208** is the third: the parent spec stated both the concrete exception type and the negative "not `ModelRetry` nor any subclass"; the negative moved to `walking-skeleton-role-compilation`'s AC-0234, which holds from the interval onward, so restating it here would give one obligation two homes and two approval-gate rows (source: adversarial spec review round 2, 2026-09-20).
- Technical: the foundation spec ships the schema, both append paths, the privilege split and the pool. This spec adds no column (source: `walking-skeleton-foundation/plan.md` § Data & schema).
- Process: this spec is one of three cut from `walking-skeleton-agent-runtime`, whose directory was deleted on 2026-09-20. AC-0207, AC-0210 and AC-0212 through AC-0218 carry across with their wording unchanged. Three are exceptions, each recorded in the entry above: AC-0208, AC-0209 and AC-0211. AC-0235, AC-0236, AC-0239, AC-0240, AC-0243, AC-0247, AC-0249 and AC-0252 are new (source: user decision 2026-09-20; owner rulings of the same date).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Product: the skeleton carries one analysis role with a single registered tool, over the recorded fixture rather than a live corpus — the thinnest agent set that exercises every criterion (source: assumption stated 2026-09-18, to be confirmed at the approval gate).
- Governance: r8 and r5 are ratified as of 2026-09-18, r8 with its five accepted limits in § 9 open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
