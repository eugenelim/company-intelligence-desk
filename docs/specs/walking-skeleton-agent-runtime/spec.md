# Spec: Walking skeleton — agent runtime

- **Status:** Approved <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r7, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r4, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md), ADR-0002 (version pin, created by the foundation spec)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § Rollout Phase 1
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

The second of three specs delivering the Phase 1 walking skeleton, and the one
that carries the security work. It builds the inside of a leased step: an agent
role compiled from data, a toolset stack with the policy decision point
outermost, the containment fragment that decides what a tool call may carry, the
quarantine boundary that keeps attacker-authored prose away from anything that
can act, a real model call under a scoped role, and a step whose conversation
survives being serialised and resumed by a different process.

Two of the architecture's four ranked quality attributes live here. Security of
the untrusted-content and agent-authority boundaries is the second-ranked
attribute and no managed control covers it. Inspectability is the first, and
this is where a step's context and decisions become readable from the log.

Success is that an unauthorised tool call is refused on its *argument value*
before the tool body runs, with the refusal recorded; that a value which passes
a string prefix check but means something else to the callee is refused; and
that no attacker-authored free text reaches an agent that can act. Each of
those is currently a design claim with no executable evidence.

**Its siblings.** `walking-skeleton-foundation` is a hard dependency: it owns
the schema, both append paths, the privilege split and the pool this runs
inside. `walking-skeleton-evidence` consumes this to produce the Phase 1
measurements and the browser stream.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Current architecture | Applicable — the `STATUS: PLANNED` marker on `worker-runtime.md` describes what this spec builds | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` header | work-loop | Marker moved off `PLANNED` for what now exists | Status header matches the repository |
| Decision rationale | Applicable — the r4 containment table omits a bypass this spec's criteria carry | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` § 4 Contracts and Invariants | work-loop | The userinfo row added to the unsafe-prefix table | The criterion's referenced table is complete |
| Reusable learning | Applicable — this spec produces the evidence Phase 2 plans against | `spikes/README.md` | work-loop | A section stating what was established **and what was not** | Hypothesis checks reported separately from setup |
| Interface compatibility | Not applicable — no interface surface; the API belongs to the foundation spec | — | — | — | — |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Boundaries

### Always do

- Treat r7 and r4 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Honour `worker-runtime.md` § 3 Runtime Model, the approval gate's step 2, as binding: the content-addressed payload object is written before the fenced append that carries its hash, on every persist path.
- Construct the agent per step, never cached across steps, because a cached agent is a cached role version.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision. The plan gives every DR decision and every change asked of r7 a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Any spend above the Phase 0 order of magnitude. Phase 0 cost about $0.05 in total; a task that would cost more than $5 stops and asks.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No `ModelRetry` on an authorization denial.** A denial is terminal. Converting it into advice the model can retry turns the authorization boundary into a negotiation the model keeps attempting.
- **No test-only bypass surface inside a shipped security control.** Mutation evidence is produced by patching in the test process, never by a switch the production canonicaliser carries.
- **No free text crossing from a quarantined role to a planning role**, including indirectly through stored state or a resolved value.
- **No typed output standing in for the deterministic parser.** Structured output is a layer; the boundary is the parser, because a control must not rest on the model's cooperation or the framework's serializer.
- **No static or long-lived model-provider credential anywhere** — no `AKIA`-prefixed key, no credentials file baked into an image, no inline secret.
- **No `pydantic_ai` import outside `agents/` and `adapters/`.**
- **No live SEC fetch on a run's request path.** The recorded fixture is the corpus.

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0201, AC-0202, AC-0203, AC-0204, AC-0205, AC-0206, AC-0207, AC-0208, AC-0209, AC-0210, AC-0211, AC-0212, AC-0213, AC-0214, AC-0215, AC-0216, AC-0217, AC-0218, AC-0219, AC-0220, AC-0221, AC-0222, AC-0226, AC-0227, AC-0228, AC-0229, AC-0230, AC-0231, AC-0232)** — nearly everything, because nearly everything here is a compressible invariant with a cheap oracle and no provider in the loop. The framework ships `TestModel` and `FunctionModel`, so the compiler, the toolset stack, the containment fragment, the quarantine boundary and the persistence round trip are all exercised without a model call. The containment criteria (AC-0213 through AC-0218) additionally carry a *property test* over generated predicate pairs, because the claim is set-theoretic containment over a fragment rather than behaviour at chosen values.
- **Goal-based check (AC-0224, AC-0225)** — a scan of the running container for a long-lived credential, and the producer tuple read back off the run header. A one-liner is the verdict.
- **End-to-end (AC-0223)** — the one criterion that calls a real provider, and the only reason this spec needs a cloud credential at all.

Every criterion touching the provider runs under a scoped assumed role, never
under an administrator profile: an administrator can invoke any model, so a
green result would say nothing about a scoped workload. This is the
construction spikes 1 and 7 used and it carries forward unchanged.

**A note on what the suite cannot see.** The quarantine criteria assert that
free text does not cross a boundary this system builds. They do not establish
that the boundary resists an adversary — r7 records that no structural defence
has been tested under an unlimited adaptive budget, and that remains an
accepted open gap rather than something these criteria close.

## Acceptance Criteria

Obligations come from `runtime-architecture.md` § Rollout Phase 1 criteria 2
and 6, and from `worker-runtime.md` § 10 Rollout, Migration, and Reversal criteria 5, 6 and 8. Obligations
**beyond** those sources are tabled below, and the approval gate rules on each
rather than inheriting it.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Verify the quarantine boundary holds | AC-0219, AC-0220, AC-0221, AC-0222 | This spec builds the quarantined role and the parser. r7 ranks this boundary second of four quality attributes and r4 § The quarantined agent says the parser is where the real guarantee lives. No § Rollout criterion asks for it, which is an omission in those lists rather than a decision | The delivery builds a security boundary and measures only what it costs, never that it holds |
| Record a denial | AC-0209 | r4 § The toolset stack: "the record of a refusal is the `policy.decision` event, which is the only place it should be." Attributability is a ratified goal at 100% | A refused call leaves no attributable trace, and the attributable-action goal is unmeasurable |
| Enforce the entitlements conjunct | AC-0210 | `may_act` is a conjunction of ceiling **and** initiating-user entitlements; a criterion covering only the ceiling half leaves the other unbuilt | Half the authorization predicate ships unverified |
| Enforce the compile-time role guards | AC-0203, AC-0204, AC-0205, AC-0206 | DR13, DR8, DR9 and R5 each specify a compile-time refusal. r4 calls the DR9 one the control that stops a framework-conducted retry loop over attacker-authored filing text | Four settled decisions ship as prose with nothing asserting them |
| Assert the stack's composition | AC-0202 | ADR-0001 D3 and r4 § The toolset stack make the policy decision point's position a security property, and reachability (AC-0201) is a different defect from ordering | A correctly-enclosed stack can still put the decision point too deep to see an unauthorised call |
| Fail a duplicate invocation loudly | AC-0212 | r4 identifies the derived key plus the index as the sole mechanism making the double-publication hazard fail rather than execute twice | The at-most-once control ships with its behaviour untested |
| Bound a hung step behaviourally | AC-0232 | r4 § Goals: "no step is *reported* running past `step_deadline`" | The delivery measures how bad a hung step is without ever bounding one |

**Compiling a role**

- [ ] **AC-0201.** Compiling an agent role whose tools are reachable outside the wrapped toolset stack fails the build. A decorator-registered tool and a second entry in `toolsets=[…]` each fail, and the failure is a compile error rather than a denial at call time.
- [ ] **AC-0202.** Every compiled agent's toolset chain is exactly the policy decision point wrapping the step-event toolset wrapping the trust-class toolset wrapping the function toolset, asserted by walking the constructed chain; and the compiler's structural check rejects a chain composed in any other order.
- [ ] **AC-0203.** Compiling a planning role bound to an integration declared `free-text` fails at compile time.
- [ ] **AC-0204.** Compiling a role whose model settings enable thinking fails at compile time.
- [ ] **AC-0205.** A compiled quarantined role carries a tool-retry budget of zero and an output-validation-retry budget of zero, so a malformed structured output raises rather than re-prompting the model over untrusted text.
- [ ] **AC-0206.** A role declaring a usage limit wider than the pool default compiles to the pool default, and one declaring a narrower limit compiles to its own: a role may narrow and never widen.
- [ ] **AC-0219.** A compiled quarantined role resolves no integrations, asserted on the compiled agent rather than on the role record.

**Authorizing a call**

- [ ] **AC-0207.** A well-typed tool call whose argument *value* falls outside the acting role's ceiling is refused, and the tool body does not execute.
- [ ] **AC-0208.** That refusal raises a domain exception whose type the authorization suite asserts, and which is not `ModelRetry` nor any subclass of it.
- [ ] **AC-0209.** A refused call commits a `policy.decision` event recording the denial, the acting agent role, and the initiating principal.
- [ ] **AC-0210.** A call whose arguments fall inside the acting role's ceiling but outside the initiating user's entitlements is refused.
- [ ] **AC-0211.** With the `policy.decision` append forced to fail on its own connection inside the decision point, the tool body does not execute and the step terminates.
- [ ] **AC-0212.** A second invocation deriving an idempotency key already recorded for the run terminates the step as a duplicate-detected failure, and the tool body executes at most once across both attempts.

**Containing an interpreted argument**

- [ ] **AC-0213.** Every row of `worker-runtime.md` § 4 Contracts and Invariants' unsafe-prefix table is refused, plus the userinfo case `https://www.sec.gov@attacker.example/`, which a prefix check admits while the parsed host is `attacker.example`. A row added to that table upstream is an amendment trigger for this criterion.
- [ ] **AC-0214.** The adapter observes the canonical value rather than the original string, asserted at the adapter rather than at the validator.
- [ ] **AC-0215.** Declaring a domain-containment predicate whose argument is a public suffix is refused at authoring time, resolved against a public-suffix dataset rather than a hand-kept list.
- [ ] **AC-0216.** For every canonicalisation rule `worker-runtime.md` § 4 Contracts and Invariants names under "what the canonicalizer must do", the suite holds an input that the canonicaliser refuses and that is admitted when that one rule is disabled by patching the canonicaliser **in the test process**. Disabling one rule reds that rule's case and leaves the others passing. A rule added to that list upstream is an amendment trigger for this criterion.
- [ ] **AC-0217.** Declaring a prefix predicate on an argument whose domain type is `url`, `fs-path`, or `content-locator` is refused, and the same predicate on `opaque-string` is accepted.
- [ ] **AC-0218.** A canonical in-ceiling `url` and an in-root `fs-path` are admitted against the same ceiling AC-0213 uses, and the tool body executes.

**Holding the quarantine boundary**

- [ ] **AC-0220.** Output from an integration declared `admitted-types` that is not a closed-vocabulary label or a typed scalar fails the step, refused by the runtime's deterministic parser rather than by the agent's structured output.
- [ ] **AC-0221.** A reference the runtime did not mint for this step fails the step, including one that is well-formed and resolvable in another step's reference set.
- [ ] **AC-0222.** No free text produced by a quarantined step reaches a planning step's context package, including by way of stored state read back from the database.

**Calling a real provider**

- [ ] **AC-0223.** A step completes a Bedrock call under a scoped assumed role and reaches `step.completed`, evidenced from the run's event log rather than from test setup.
- [ ] **AC-0224.** The running worker container holds no long-lived provider credential: no `AKIA`-prefixed access key, no credentials file baked into the image, and no credential that outlives the assumed-role session. Short-lived session credentials delivered to the process are what ambient workload identity yields and are in scope; what this criterion forbids is a static one.
- [ ] **AC-0225.** The run header records the producer tuple, including the resolved inference profile and the exact `pydantic-ai` version.

**Persisting and resuming a step**

- [ ] **AC-0226.** A message history containing a tool call, a tool return, a retry part, and a pending approval serialises, deserialises, and re-serialises to identical bytes.
- [ ] **AC-0227.** A fresh agent in a separate process, sharing nothing with the original run but those bytes, resumes the suspended step and applies the approval decision.
- [ ] **AC-0228.** No persisted message history contains a reasoning part, demonstrated against a history that carried one before persisting.
- [ ] **AC-0229.** A step resumed from a history that carries stale instruction text is prompted by the current role compilation, and the stale text does not reach the model.
- [ ] **AC-0230.** With a crash injected between the payload write and the fenced append, an unreferenced payload object remains and no event carries a payload reference that does not resolve.
- [ ] **AC-0231.** Every payload object key is scope-qualified as `<owner_scope>/<content_hash>`, so a bare content hash is never the key.

**Bounding a hung step**

- [ ] **AC-0232.** A step whose model call hangs is failed and its lease released within `step_deadline`, whether or not the underlying provider call terminated.

## Follow-ons

- eugenelim: `workspace.toml` `[backlog].open` — **`may_exist`, the authoring-time containment gate** (`runtime-architecture.md` r8 § 4, the `may_exist` gate; `worker-runtime.md` r4 change 8). Designed, not built. The charter holds the substrate single-author in operation until the governance gaps are *built*, and this is one of them; a single operator authors every role here, which is the condition that makes deferring it safe.
- eugenelim: `workspace.toml` `[backlog].open` — **`may_run`, the spawn-time containment gate.** Recording `role.ceiling ⊆ parent_role.ceiling` as an event at spawn needs a coordinator that spawns children, which this skeleton's single analysis step does not exercise. Named rather than absent.
- eugenelim: `workspace.toml` `[backlog].open` — the credential broker commissioned by DR12, which is where per-integration credential scopes (change 9) are carried. Already tracked.
- eugenelim: `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md` — the r8 consistency pass, named as outstanding in r7's own header.

## Assumptions

- Technical: `pydantic-ai` is pinned to 2.45.0 rather than ADR-0001 D5's 2.44.0 (source: user decision 2026-09-18). Every load-bearing API claim the ratified design rests on was re-verified against 2.45.0 and all held; the probe is recorded once, in `plan.md` § Grounding probe.
- Technical: a deferred-approval history round-trips byte-identically and a fresh agent resumes from the bytes alone, established offline before this spec was written. AC-0226's residual risk is therefore the *combination* of a realistic shape with a pending approval, not the mechanism (source: `plan.md` § Grounding probe).
- Technical: refusing a public-suffix argument needs a public-suffix dataset; the standard library has none (source: probe against `urllib`, 2026-09-18).
- Technical: registering a tool on a nested function trips the framework's context-parameter inference, so the compiler resolves module-level callables from the registry rather than closures (source: probe, 2026-09-18).
- Technical: a recorded Apple 10-Q fixture exists under `spikes/phase-0/fixtures/`, so the quarantine criteria need no live SEC fetch — which matters because EDGAR returns 403 to this network (source: `spikes/README.md` § Spike 4).
- Technical: the foundation spec ships the schema, both append paths, the privilege split and the pool. This spec adds no column (source: `walking-skeleton-foundation/plan.md` § Data & schema).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents — a shaping review over two rounds and an adversarial spec-mode review — and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Product: the skeleton carries one coordinator role, one quarantined role, and one analysis role with a single registered tool, over the recorded fixture rather than a live corpus — the thinnest agent set that exercises every criterion (source: assumption stated 2026-09-18, to be confirmed at the approval gate).
- Governance: r7 and r4 are ratified as of 2026-09-18, r7 with its Known-at-ship gaps accepted open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
