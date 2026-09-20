# Spec: Walking skeleton — role compilation and the quarantine boundary

- **Status:** Draft <!-- Draft | Approved | Implementing | Shipped | Archived -->
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

The first of three specs delivering the Phase 1 agent runtime, and the one every
other guarantee is asserted against. It builds the compiler that turns an
`agent_role` record into a running agent, the four-layer toolset stack that
agent is allowed to hold, the compile-time refusals that stop a badly shaped
role from ever reaching a step, and the quarantine boundary that keeps
attacker-authored prose away from anything that can act.

Inspectability is the architecture's first-ranked quality attribute and security
of the untrusted-content boundary is its second. Both land here: the compiler is
where a role's decisions become readable, and the quarantine boundary is where
untrusted filing text stops.

Success is that a role which violates a settled design decision fails the build
rather than failing at call time; that the stack's composition is asserted by
walking the constructed chain rather than trusted; that no attacker-authored
free text reaches an agent that can act; and that the decision point this spec
puts in place refuses every call until
[`walking-skeleton-authority-containment`](../walking-skeleton-authority-containment/spec.md)
supplies its predicate. Each of those is currently a design claim with no
executable evidence.

**Its siblings.** [`walking-skeleton-foundation`](../walking-skeleton-foundation/spec.md)
is a hard dependency: it owns the schema, both append paths, the privilege split
and the pool this runs inside. [`walking-skeleton-authority-containment`](../walking-skeleton-authority-containment/spec.md)
follows this spec and supplies the decision point's predicate;
[`walking-skeleton-step-lifecycle`](../walking-skeleton-step-lifecycle/spec.md)
follows that one, because resuming a suspended step means a gated tool body
runs, and nothing can admit a call until the predicate exists.
[`walking-skeleton-evidence`](../walking-skeleton-evidence/spec.md) consumes all
three to produce the Phase 1 measurements and the browser stream.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Current architecture | Applicable — `docs/architecture/README.md` § What is built is the current map and this spec changes it | `docs/architecture/README.md` § What is built | work-loop | The compiler, the toolset stack and the quarantined agent moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Current architecture — the `worker-runtime.md` marker | Applicable — r5's STATUS header names three things as unbuilt: the agent layer, the authorization boundary and the provider call. This spec builds the first | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` header | work-loop | The agent layer moved from unbuilt to built, the other two clauses untouched | The header's built and unbuilt lists match the repository |
| Reusable learning | Applicable — this spec produces the compiler and quarantine evidence Phase 2 plans against | `spikes/README.md` | work-loop | A section stating what was established **and what was not** | Hypothesis checks reported separately from setup |
| Decision rationale | Not applicable — no ratified decision changes here; the r5 unsafe-prefix table amendment belongs to `walking-skeleton-authority-containment` | — | — | — | — |
| Interface compatibility | Not applicable — no interface surface; the API belongs to the foundation spec | — | — | — | — |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Boundaries

### Always do

- Treat r8 and r5 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Construct the agent per step, never cached across steps, because a cached agent is a cached role version.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision. The plan gives every DR decision this spec constructs a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No typed output standing in for the deterministic parser.** Structured output is a layer; the boundary is the parser, because a control must not rest on the model's cooperation or the framework's serializer.
- **No free text crossing from a quarantined role to a planning role**, including indirectly through stored state or a resolved value.
- **No decision point that admits by default.** Until `walking-skeleton-authority-containment` supplies the predicate, every tool call is refused. The predicate arrives in a later spec; the failure direction does not wait for it.
- **No `ModelRetry` on an authorization denial.** A denial is terminal. Converting it into advice the model can retry turns the authorization boundary into a negotiation the model keeps attempting, and the interval this spec governs is exactly when nothing else asserts the exception type.
- **No `pydantic_ai` import outside `agents/` and `adapters/`.**
- **No live SEC fetch on a run's request path.** The recorded fixture is the corpus.

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0201, AC-0202, AC-0203, AC-0204, AC-0205, AC-0206, AC-0219, AC-0251, AC-0220, AC-0221, AC-0222, AC-0233, AC-0234, AC-0238, AC-0242, AC-0246, AC-0250)** — all of it, because all of it is a compressible invariant with a cheap oracle and no provider in the loop. The framework ships `TestModel` and `FunctionModel`, so the compiler, the toolset stack and the quarantine boundary are all exercised without a model call. AC-0222 is exercised by an **integration** test: a quarantined step and a planning step together, across the database, because the indirect path is the one a unit test cannot see.

No criterion here calls a provider, so this spec needs no cloud credential and
carries no spend. **This contract deliberately ships a runtime in which no tool
body ever executes**, because AC-0233 refuses every call until the successor
spec's predicate arrives. AC-0202's stack is therefore asserted by construction
and never demonstrated end-to-end here; the first tool body to run anywhere does so under
`walking-skeleton-authority-containment`.

**A note on what the suite cannot see.** The quarantine criteria assert that
free text does not cross a boundary this system builds. Three limits stay open,
all of them r8's and none closed by anything here.

No structural defence has been tested under an unlimited adaptive budget. The
guarantee is "no attacker-authored free *text*", **not** "no attacker-influenced
signal" — r8's first accepted limit names selection influence explicitly. And
the reference-selection channel stays *unmitigated and unmeasured*: a closed
vocabulary bounds the alphabet, not the channel, so a quarantined agent can pass
signal into a planning agent's context by which references it chooses, and
resolution detects forged references rather than steered-but-valid ones. AC-0238 pins minting order and set immutability, which makes forgery
unrepresentable; it says nothing about steering, and adding it raises rather
than lowers the odds a reader takes reference integrity as solved.

## Acceptance Criteria

**No § Rollout criterion in either ratified document asks for anything in this
spec.** `runtime-architecture.md` § 10 Rollout, Phase 1's six clauses are a run, a
provider step, an event append, a browser stream, worker reacquisition and an
unauthorised-call refusal; the last is `walking-skeleton-authority-containment`'s
AC-0207 and the second is `walking-skeleton-step-lifecycle`'s AC-0223.
`worker-runtime.md` § 10 Rollout's added criteria 5, 6 and 8 belong to those two
specs as well. Every criterion here is therefore **beyond source**, and the
approval gate rules on each rather than inheriting it.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Keep every tool inside the wrapped stack | AC-0201 | r5 § 2 Structural Model, an agent role compiles to an agent makes the single-toolset shape the precondition for every later guarantee. A tool reachable beside the stack has no ceiling entry to violate, so no behavioural test anywhere can catch it | The authorization boundary is complete on paper and bypassable in one line |
| Assert the stack's composition | AC-0202 | ADR-0001 D3 and r5 § 2 Structural Model, the toolset stack make the policy decision point's position a security property, and reachability (AC-0201) is a different defect from ordering | A correctly-enclosed stack can still put the decision point too deep to see an unauthorised call |
| Enforce the compile-time role guards | AC-0203, AC-0204, AC-0205, AC-0206, AC-0251 | Each discharges a named upstream rule: AC-0203 r5 § 2's R2 (refuse a `free-text` integration on a non-quarantined role), AC-0204 R5's `thinking` disabled and DR8, AC-0205 DR9 — which r5 calls the control that stops a framework-conducted retry loop over attacker-authored filing text — AC-0206 R5's `effective limits = min(pool default, role value)` under § 4's compile-failure semantics, and AC-0251 R5's model-id-within-the-pool's-allowed-set. R5 is a list of six invariants, not one, so each is cited by the member it discharges; with AC-0251 the only member left unasserted is `ceiling ⊆ parent`, deferred as `may_run` | Four settled decisions ship as prose with nothing asserting them |
| Bound cost before the call, not after | AC-0246 | r5 § 7's quality-scenario table names the cost mechanism as a limit with **pre-request token counting**, with denial of wallet as the consequence if missed, and § 7 adds that only the innermost ceiling is genuinely pre-call. AC-0206 asserts a limit may only narrow and is green whether or not counting happens before the request | A role carries a cost ceiling that bounds nothing until the tokens are already spent |
| Fail closed for the interval | AC-0233 | This spec ships the decision point's position and `walking-skeleton-authority-containment` ships its predicate. AC-0233 covers the configuration in between, and is scoped to it: with the predicate installed the fall-through guard is that spec's AC-0235 and the error-path guard its AC-0236, both of which can be decided against a real lookup and this one cannot. **Retirement trigger:** that spec's T2 removes this criterion's suite in the same task that installs the predicate | An unguarded runtime looks finished and the gap is invisible in a passing build |
| Keep a denial terminal from the start | AC-0234 | The exception type is asserted from the first refusal this repository raises, rather than from the first *real* refusal. `walking-skeleton-authority-containment`'s AC-0208 names the concrete domain type; this one is the permanent negative and holds throughout | The interval's refusal ships as a retryable hint, and the boundary is a negotiation before anything asserts otherwise |
| Constrain the quarantined role at compile time | AC-0219 | DR13 makes `trust_class` a construction rather than a declaration, and the compiled agent is the fact while the role record is only the input. No § Rollout criterion asks for it. It is tabled apart from the three below because it is a compile-time property verified with them in the compiler task, not a runtime one | A role declared quarantined can still resolve an integration, and the construction is a declaration after all |
| Verify the quarantine boundary holds | AC-0220, AC-0221, AC-0222 | This spec builds the quarantined role and the parser. r8 ranks this boundary second of four quality attributes and r8 § 4 Contracts and Invariants owns its guarantee — r5 § 1's scope table puts that guarantee out of this subsystem's scope explicitly, leaving the subsystem the enforcement. No § 10 Rollout criterion in either document asks for it, which is an omission in those lists rather than a decision | The delivery builds a security boundary and measures only what it costs, never that it holds |
| Pin the pipeline-first construction | AC-0238, AC-0250 | `runtime-architecture.md` r8 § 4 Contracts and Invariants owns this guarantee and states it as "The model never produces a reference, and that is the difference between detecting forgery and making it unrepresentable"; r5 § 1's scope table routes it upstream rather than claiming it. Beyond source even so, because r8 § 10's Phase 1 asks for no criterion over it. AC-0221 asserts only that a non-minted reference fails, which is the detection backstop: an implementation that mints the set *from* the agent's output, or lets it grow mid-run, passes AC-0221 unchanged. The structural claim otherwise lives only in plan prose, which is working material | The guarantee the architecture ranks second of four is contract-free, and the weaker construction the plan names as the failure mode ships with a green suite |
| Keep rejected text out of the durable record | AC-0242 | The context package is not free text's only sink. A rejected result whose diagnostic carries the offending prose puts attacker-authored text into the event log, which the evidence spec streams to a browser and any later context assembler reads back | AC-0222 holds on the path it walks while the same text reaches a reader by another one |

**Compiling a role**

- [ ] **AC-0201.** Compiling an agent role whose tools are reachable outside the wrapped toolset stack fails the build. A decorator-registered tool and a second entry in `toolsets=[…]` each fail, and the failure is a compile error rather than a denial at call time.
- [ ] **AC-0202.** Every compiled agent's toolset chain is exactly the policy decision point wrapping the step-event toolset wrapping the trust-class toolset wrapping the function toolset, asserted by walking the constructed chain; and the compiler's structural check rejects a chain composed in any other order.
- [ ] **AC-0203.** Compiling any non-quarantined role bound to an integration declared `free-text` fails at compile time.
- [ ] **AC-0204.** Compiling a role whose model settings enable thinking fails at compile time.
- [ ] **AC-0205.** A compiled quarantined role carries a tool-retry budget of zero and an output-validation-retry budget of zero, so a malformed structured output raises rather than re-prompting the model over untrusted text.
- [ ] **AC-0206.** Compiling a role that declares a usage limit wider than the pool default fails the build, and one declaring a narrower limit compiles to its own value: a role may narrow and never widen.
- [ ] **AC-0251.** Compiling a role whose model id falls outside the pool's allowed set fails the build.
- [ ] **AC-0219.** A compiled quarantined role resolves no integrations, asserted on the compiled agent rather than on the role record.

- [ ] **AC-0246.** A compiled agent whose cost ceiling is below the counted tokens raises before the model's request is issued, demonstrated with a stub model that records whether it was called.

**Refusing before the predicate arrives**

- [ ] **AC-0233.** With no containment predicate installed, a call is refused and no tool body executes for every role in the role registry and every tool in the integration registry, enumerated from those registries rather than from a list held in the suite.
- [ ] **AC-0234.** A refusal raised by the decision point is neither `ModelRetry` nor any subclass of it, so the authorization boundary is never presented to the model as a retryable hint.

**Holding the quarantine boundary**

- [ ] **AC-0220.** Output from an integration declared `admitted-types` that is not a closed-vocabulary label or a typed scalar fails the step, refused by the runtime's deterministic parser rather than by the agent's structured output.
- [ ] **AC-0221.** A reference the runtime did not mint for this step fails the step, including one that is well-formed and resolvable in another step's reference set.
- [ ] **AC-0222.** No free text produced by a quarantined step reaches a planning step's context package, including by way of stored state read back from the database.
- [ ] **AC-0238.** The candidate reference set is complete before the quarantined agent's first model turn, and the set observed before that turn is identical to the set observed after the last one.
- [ ] **AC-0250.** A mutation of the candidate reference set attempted while the run is in flight is refused.
- [ ] **AC-0242.** A refused integration result records its rejection without the rejected text reaching the event log or any payload object an event of that run references.

## Follow-ons

Every item below is a criterion-wording defect a spec-stage shaping or security
review found in text this spec carries unchanged from the deleted
`walking-skeleton-agent-runtime`. They were left unreworded by owner decision of
2026-09-20, so the carry-across stays auditable against the parent; each needs an
amendment rather than an in-place correction.

- eugenelim: `workspace.toml` `[backlog].open` — **the compile-time egress check has no criterion.** r5 § 4 requires a `connection_ref` naming a host the egress proxy does not allow to fail at compile time, so the registry can select within egress and never widen it. That is a runtime obligation, not the proxy's, and it sits in this spec's own category of compile-time refusals. Deferred because Phase 1 ships no proxy and therefore no allowlist to check against; it becomes buildable with the AWS deployment.
- eugenelim: `workspace.toml` `[backlog].open` — **AC-0202 is two predicates under one checkbox.** The chain-order property and the structural checker's rejection of a hand-built wrong chain have separate failure modes and separate remedies, and the second names an internal helper the plan exists to decide.
- eugenelim: `workspace.toml` `[backlog].open` — **AC-0222 is universally quantified and proven on one path.** One quarantined step, one planning step, one fixture. The Testing Strategy caveats adaptive adversaries but not path coverage, so a reader takes a single-path result as universal.
- eugenelim: `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md` § Defence in depth — **the cheap local checks have no owner after the split.** Tool-result protocol validation, structural anomaly detection on retrieved chunks and YARA patterns are specified as implemented directly; no Phase 1 spec claims them. Low urgency, since the Phase 1 corpus is a fixed fixture and no attacker controls chunk size.

## Assumptions

- Technical: `pydantic-ai` is pinned to 2.45.0 rather than ADR-0001 D5's 2.44.0 (source: user decision 2026-09-18). Every load-bearing API claim the ratified design rests on was re-verified against 2.45.0 and all held; the probe is recorded once, in `plan.md` § Grounding probe, and the two sibling specs cite it there.
- Technical: registering a tool on a nested function trips the framework's context-parameter inference, so the compiler resolves module-level callables from the registry rather than closures (source: probe, 2026-09-18).
- Technical: a recorded Apple 10-Q fixture exists under `spikes/phase-0/fixtures/`, so the quarantine criteria need no live SEC fetch — which matters because EDGAR returns 403 to this network (source: `spikes/README.md` § Spike 4).
- Technical: the foundation spec ships the schema, both append paths, the privilege split and the pool. This spec adds no column (source: `walking-skeleton-foundation/plan.md` § Data & schema).
- Process: this spec is one of three cut from `walking-skeleton-agent-runtime`, whose directory was deleted on 2026-09-20 because a single contract carrying AC-0201 through AC-0232 was roughly two and a half times the size of either Phase 1 sibling. AC-0201, AC-0202, AC-0204, AC-0205 and AC-0219 through AC-0222 carry across with their wording unchanged. AC-0203 and AC-0206 were reworded by owner ruling of 2026-09-20 to match `worker-runtime.md` r5, which a shaping review found they contradicted: AC-0203 refused a `free-text` integration only on a *planning* role where r5 § 2's R2 refuses it on any *non-quarantined* one, and AC-0206 clamped a too-wide usage limit to the pool default where r5 § 4 gives that contract compile-failure semantics. Both rewords are strictly stricter and neither widens authority. AC-0233 and AC-0234 are new and exist only because the split separates the decision point's position from its predicate, as is `walking-skeleton-authority-containment`'s AC-0235 (source: user decision 2026-09-20; adversarial spec review rounds 1 and 2, 2026-09-20).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Product: the skeleton carries one coordinator role, one quarantined role, and one analysis role with a single registered tool, over the recorded fixture rather than a live corpus — the thinnest agent set that exercises every criterion (source: assumption stated 2026-09-18, to be confirmed at the approval gate).
- Governance: r8 and r5 are ratified as of 2026-09-18, r8 with its five accepted limits in § 9 open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
