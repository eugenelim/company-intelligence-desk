# Plan: Walking skeleton — role compilation and the quarantine boundary

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 2 Structural Model ("An agent role compiles to an agent", "The toolset stack, innermost to outermost", the three responsibility catalogues) and § 4 Contracts and Invariants ("The integration registry", "Inputs, outputs, and tool reach"). **No analogous production implementation exists.** The substitute is `spikes/phase-0/pydantic_ai_bedrock_spike.py`, which holds executable precedent for the `WrapperToolset` authorization hook. **Named deviation:** that spike's hook appended to a Python list — no database, no second connection — so it is precedent for the *seam*, not for any persistence mechanism.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-role-compilation/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Build the guards before the thing they guard, and keep the provider out of the
loop entirely — no task here reaches one.

The compiler comes first because it is where every other guarantee in the Phase 1
runtime is asserted: the structural invariant, the four compile-time role
refusals, the usage-limit narrowing. The stack it composes is the full four
layers, including the policy decision point, because the decision point's
*position* is the security property and it cannot be asserted against a chain
that is missing it. Its *predicate* arrives in
`walking-skeleton-authority-containment`; until then the decision point has
nothing that can decide a ceiling entry, so it refuses every call. AC-0233 pins
that with no predicate installed the whole tool surface refuses, and AC-0234
that a refusal is terminal. AC-0233 is deliberately scoped to that
configuration: phrased to also cover the predicate being present, it would read
"refused unless the predicate admits it", which no oracle outside the
implementation can decide — a lookup miss that falls through would satisfy it.
The fall-through guard therefore lives where a real lookup exists, as
`walking-skeleton-authority-containment`'s AC-0235. AC-0234 carries across
unscoped, because a refusal is terminal in every configuration.

The quarantine boundary follows and is the largest single piece of new thinking,
because the ratified design moved reference production *out* of the model: a
deterministic pipeline mints the candidate set before the quarantined agent
runs, so forgery is unrepresentable rather than detected. That is a different
construction from the one spike 4 tested and falsified, and building the weaker
one by accident is the most likely way to get this wrong.

**The riskiest part is the quarantine boundary**, and the risk is not that it
fails a test. It is that the boundary can be built so that its tests pass while
the guarantee is weaker than the criteria read — a parser that validates shape
without a minting authority admits an attacker-chosen value inside a well-formed
reference. AC-0221 exists to catch precisely that, and it is the criterion to
write first and trust least.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — the framework at step-level-reasoning-library position; `Model` as the portability contract; `WrapperToolset.call_tool` as the decision point. ADR-0002 pins 2.45.0.
- `runtime-architecture.md` r8 — ratified with its five accepted limits in § 9 accepted **open**. The first of those limits in particular narrows the quarantine guarantee's *scope*; it does not license leaving the guarantee unverified, which is why this spec adds criteria for it.
- `worker-runtime.md` r5 — see § DR dispositions below. The amendments it once asked of its parent are folded into r8; see § Amendments the worker runtime asked of its parent.
- **Hard dependency:** `walking-skeleton-foundation` ships the schema, both append paths, the privilege split and the pool. Nothing here adds a column.
- **Out of scope:** the containment fragment and the decision point's predicate, owned by `walking-skeleton-authority-containment`, which follows this spec; the provider call, suspension and persistence, owned by `walking-skeleton-step-lifecycle`, which follows that one; the run state machine, publication, the browser stream and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

## DR dispositions

The spec makes changing any DR decision an Ask-first boundary, enforceable only
if each carries a disposition. **This table lists only the DRs this spec
constructs.** A DR absent from it is not this spec's; the Phase 1 routing is the
union of this table, the two sibling plans' and the foundation plan's, and no
plan restates another's rows — a negative row is a sentence about a document
this one does not own, and three copies of it go wrong the next time one moves.

| DR | Decision | Disposition |
| --- | --- | --- |
| DR6 | Three spend ceilings; the step one is pre-call | **Partly here** — the per-step `cost_limit` with pre-request counting, `request_limit` and `tool_calls_limit` land in T2 under AC-0206. The per-run ceiling is the evidence spec's, and the per-account AWS Budgets alarm is outside the application entirely |
| DR8 | Thinking off, and reasoning parts stripped before persisting | **Partly here** — AC-0204 is the primary control and lands in T2. The storage backstop is `walking-skeleton-step-lifecycle`'s |
| DR9 | Zero tool and output retries on the quarantined role | **Lands**, T2, AC-0205 |
| DR13 | `trust_class` is a construction, not a declaration | **Lands** — AC-0203 is the compile-time refusal and AC-0219 the compiled-agent assertion in T2, AC-0220 the parser and AC-0221 the minting authority in T3 |

## Amendments the worker runtime asked of its parent

r5 § 10 Rollout records that every amendment this subsystem required is now
folded into `runtime-architecture.md` r8 and is no longer asked for from here,
so there is nothing left for a spec to disposition. r5 names three as
load-bearing for its § 4 invariants: the fenced policy append, the narrowed
decidable fragment, and scope-qualified object keys.

**None of the three is this spec's.** The first two are `walking-skeleton-authority-containment`'s and the third is `walking-skeleton-step-lifecycle`'s.

## Grounding probe

Run before this plan was written, against the pinned version, to disconfirm the
API claims the ratified design rests on. **It disconfirmed none on
`pydantic-ai` 2.45.0**, which is what licenses treating the pin move off
ADR-0001 D5's 2.44.0 as cheap. Some rows carry more than one assertion.

**This table is the single home for the framework-seam probe.** The two sibling
specs cite it here rather than repeating rows.

| Claim under test | Source of the claim | Result |
| --- | --- | --- |
| `Agent.run` accepts `cancellation_token` | r5 § 2 Structural Model, the pool | present in signature |
| `UsageLimits` has `cost_limit`, `count_tokens_before_request`, `request_limit`, `tool_calls_limit` | DR6 | all present |
| Tool and output retries budget separately, both zeroable | DR9 | the retry type carries exactly those two budgets |
| `ModelSettings.thinking` exists; a reasoning part is the thing to strip | DR8 | both present |
| `WrapperToolset.call_tool` is an overridable seam | ADR-0001 D3 | `(self, name, tool_args, ctx, tool)` |
| `DeferredToolRequests` carries `calls` as well as `approvals` | r5 § 3 Runtime Model, the approval gate | both present |
| `BedrockConverseModel` takes a model id and nothing else | ADR-0001 D2 | only the model name is required |
| A realistic history round-trips byte-identically | r5 § 10 Rollout criterion 6 | identical on second dump, over tool call, tool return and retry parts |
| A reasoning-stripped history round-trips and leaks nothing | DR8 | identical, no reasoning in the bytes |
| `result.usage` is a property; `stream_text` debounces by default | probe-established; no upstream document states either | both confirmed |

`DeferredToolRequests` resolves from a private module re-exported at the package
root. T1 imports it from the root and the framework-seam contract test pins
that, because a re-export moving is exactly the additive-minor drift r5's risk
register names.

That probe also surfaced the closure gotcha: a tool registered on a nested
function raises a context-parameter error, because the framework infers a
context parameter it cannot resolve. The compiler builds toolsets inside a
function, so it resolves module-level callables from the registry.

No probe is committed. Their content becomes the framework-seam contract suite
in T1, which is the ratified mitigation for version drift — exact pins plus
contract tests at the framework seam — and a throwaway script is not that. The
provider seam is `walking-skeleton-step-lifecycle`'s; no task here reaches one.

## Construction tests

**Integration tests:**
- One quarantine end-to-end: the deterministic pipeline mints a reference set from the recorded filing, the quarantined agent selects among them, the parser admits, and a planning step receives references and scalars only. This is the spine AC-0219 through AC-0222 read.
- One framework-seam contract suite (T1) asserting every check in § Grounding probe, so a version bump fails the build rather than a runtime.

**Manual verification:** none. Every criterion here is machine-checkable.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Current architecture — the `worker-runtime.md` marker | T4 | This spec's clause moved from unbuilt to built | The header's built and unbuilt lists match the repository |
| Current architecture — `docs/architecture/README.md` § What is built | T4 | The compiler, the toolset stack and the quarantined agent moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Reusable learning — `spikes/README.md` | T4 | A section stating what was and was not established | Hypothesis checks separated from setup |

## Design (LLD)

Shape is `service`; the sub-sections below are the set that shape selects.

### Design decisions

- **The compiler is the only constructor of the agent.** It asserts the agent holds exactly one toolset, that it is the decision point, and that the chain beneath it is the specified order. Nesting order only governs tools reached *through* the wrapped stack, so a sibling tool has no ceiling entry to violate and no behavioural test can catch it. Traces to: AC-0201, AC-0202.
- **The structural check is a function over a constructed chain, not a parameter on the compiler.** Asserting order by making the compiler accept an ordered layer list would widen a production contract to make a test possible, and would put stack order in a caller's hands. Instead the compiler builds the chain and calls a checker; the checker is unit-tested against hand-built wrong chains, and the compiled agent is asserted by walking it. Traces to: AC-0202.
- **The decision point ships with its position, not its predicate, and refuses everything in between.** Splitting the stack's composition from its containment logic is what makes two reviewable specs out of one; making the interval admit anything would turn the split into a security regression. The interval's rule is not "a lookup miss denies" — there is no lookup to miss, and a criterion phrased around one would pass while every entered tool ran unchecked. Nor is it "refused unless a predicate admits it", which is circular once a predicate exists: the implementation's own verdict becomes the oracle, and a fall-through satisfies it. So AC-0233 is scoped to the no-predicate configuration, where an enumeration over the tool surface decides it outright, and the permanent fall-through guard is `walking-skeleton-authority-containment`'s AC-0235, which a real lookup can fail. AC-0234 keeps the refusal terminal from the first refusal this repository raises; AC-0208 asserts a different property once the real denial path exists — that the denial handler does not also swallow a tool-body bug. Traces to: AC-0202, AC-0233, AC-0234.
- **Rejected: typed output as the quarantine boundary.** It would delete the parser and a reviewer will ask. It makes the boundary depend on the framework's serializer and the model's cooperation — the same class of argument r8 uses to reject detection-based defence. Typed output stays as a layer.

### Interfaces & contracts

No external interface. The internal seams are the compiler's input (an
`agent_role` version plus a resolved integration set) and its output (an agent
with one toolset), and the parser's admitted-type contract. Each is exercised
directly by its own suite. Traces to: AC-0201, AC-0220.

### Data & schema

No schema change. This spec reads `agent_role`, `integration_registry` and
`entitlements`, all created by the foundation spec. It writes no payload object;
the first one is `walking-skeleton-step-lifecycle`'s, which is where object keys
become scope-qualified.

### Failure, edge cases & resilience

One ordering carries the story and it is not negotiable: with no predicate
installed, the decision point refuses, and the refusal is terminal. That is the
same failure direction the containment predicate uses when it arrives, which is
why installing it now costs nothing and closes the interval between the two
specs. What it does **not** close is a lookup miss falling through once a real
predicate exists; that is `walking-skeleton-authority-containment`'s AC-0235,
because it cannot be decided here. Traces to: AC-0233, AC-0234.

The quarantine boundary's resilience story is structural rather than
recovery-shaped: the candidate reference set is minted before the quarantined
agent runs, so an agent cannot produce an identifier the runtime must then
decide about. Traces to: AC-0221.

### Quality attributes (NFRs)

Inspectability is the attribute this spec carries, and the compiler is where it
lands: a compiled agent's role version, ceiling and stack are readable from the
constructed object rather than inferred from configuration.

### Dependencies & integration

New dependencies, recorded before being added per `AGENTS.md`:
`pydantic-ai-slim[bedrock]` 2.45.0. The `[bedrock]` extra is pinned here rather
than in `walking-skeleton-step-lifecycle` because T1's contract suite asserts
the `BedrockConverseModel` row of § Grounding probe, and a seam contract that
cannot import the seam is not one. Everything else is inherited from the
foundation spec's manifest.

External: none. SEC EDGAR is **not** a dependency — the corpus is the recorded
fixture. No task here reaches a provider.

## Tasks

### T1: The framework seam is pinned

**Depends on:** none

**Touches:** pyproject.toml, src/**/adapters/framework_contract.py, tests/contract/**

**Tests:**
- The contract suite asserts every check in § Grounding probe, including the package-root import path for the deferred-requests type. A re-export moving is additive-minor drift the vendor does not class as breaking, so it must red here rather than in a runtime.
- A deliberate downgrade of the pin reds the suite. Without this the suite proves the current version behaves as documented and nothing about its ability to notice a change, which is the only thing it exists for.

**Approach:**
- Add the framework dependencies to the manifest the foundation spec created.

**Done when:** both checks above hold.

### T2: A role compiles, five bad roles refuse to, and the stack denies

**Depends on:** T1

**Touches:** src/**/agents/compiler.py, src/**/agents/toolsets/**, tests/compiler/**

**Tests:**
- AC-0201 has two cases, each a compile error rather than a call-time denial.
- AC-0202 walks the constructed chain and asserts the type order; the checker is separately unit-tested against hand-built wrong chains, which is what lets the ordering be asserted without the compiler accepting a layer list.
- AC-0203, AC-0204, AC-0205, AC-0219 and AC-0251 are each a role record the compiler must reject or constrain. AC-0203's case set covers every non-quarantined role the skeleton carries, not just the planning one, because that is the scope r5's R2 states. AC-0205 asserts the compiled budgets are zero rather than that the role record requested zero — the record is the input, the compiled agent is the fact.
- AC-0246 uses a stub model that records whether its request method ran, with a ceiling below the counted tokens. A settings read would pass on a flag that is set and never consulted; the stub is what makes "before the request" observable. AC-0206 cannot see this either way.
- AC-0206 needs both directions: a role wider than the pool default fails the build, a narrower one compiles to its own value. Only the widening case protects the operator's reviewable deploy, and it fails rather than clamps so the role file and the limit in force cannot disagree.
- AC-0233 enumerates the skeleton's roles and registered tools, drives a call through each with a spy the tool body increments, and asserts no spy moved. The spy is what makes "did not execute" observable rather than inferred, and the enumeration is what stops the criterion passing on a miss path alone. The suite runs in the no-predicate configuration the criterion names, so it retires with that configuration rather than being carried forward by the successor.
- AC-0234 asserts the raised type is not the framework's retry type nor a subclass. A bare "raises" assertion passes on the wrong one, and the wrong one degrades the boundary into a negotiation with no visible failure.
- Tools resolve as module-level callables from the registry; a closure trips the framework's context-parameter inference, which the probe hit directly.

**Approach:**
- The refusal seam is the compiler's return path, not the agent's: a role record that violates a guard never produces an agent, so there is no object a caller could hold and invoke. That is what makes AC-0201 through AC-0205 compile errors rather than call-time denials.
- The usage-limit narrowing is applied where the pool default is known, so the compiled agent carries the resolved value and the role record keeps the requested one. Resolving it at call time would make AC-0206's widening case unobservable on the compiled agent.
- The decision point is installed as the outermost layer with no predicate bound to it. It holds a reference to a resolver that has no entries, which is what makes the interval refuse by construction rather than by a branch someone can delete.

**Done when:** AC-0201 through AC-0206, AC-0219, AC-0233, AC-0234, AC-0246 and AC-0251 are green.

### T3: Free text does not cross the boundary

**Depends on:** T2

**Touches:** src/**/domain/quarantine/**, src/**/agents/toolsets/trust_class.py, tests/quarantine/**

**Tests:**
- AC-0220 feeds the parser output that is neither a closed-vocabulary label nor a typed scalar and asserts the step fails. The parser is the runtime's, outside the agent — a test that drives the agent's structured output instead is testing the layer, not the boundary.
- AC-0221 is the criterion to write first and trust least: a well-formed reference that resolves in *another* step's set must still fail. Shape validity is not provenance, and a parser that checks only shape admits an attacker-chosen value inside a well-formed reference.
- AC-0238 asserts an ordering and an equality, not a value: the recorded mint precedes the agent's first model turn, and the before and after snapshots match. AC-0250 is separate because a set nothing tries to mutate satisfies AC-0238 with no enforcement built at all. A post-run probe alone cannot see a resolver that consults a second source while the agent runs, which is the "agent emits, resolver accommodates" shape this criterion exists to catch.
- AC-0242 drives a refused integration result whose text is distinctive, then searches the run's events **and every payload object they reference** for it. Stopping at the events table leaves the prose one dereference away, still streamed and still readable by a later context assembler. The parser's rejection is the thing under test; the diagnostic carrying the rejected prose into the log is the thing this catches.
- AC-0222 runs a quarantined step over the recorded filing, then a planning step, and asserts the planning step's assembled context contains no free text — including after a round trip through the database, which is the indirect path that would otherwise reopen the boundary.

**Approach:**
- The integration result the parser judges arrives through the runtime's own retrieval path, not as a tool-body return value, so AC-0220, AC-0242 and AC-0233's blanket refusal are consistent. This is the same construction AC-0219 forces: a quarantined role resolves no integrations, so it has no tool to call.
- The quarantine spine reaches no registered tool. The quarantined role resolves no integrations (AC-0219) and the planning step in AC-0222 is asserted on its assembled context, not on a tool call, so the spine and AC-0233's blanket refusal are satisfiable together.
- The deterministic pipeline mints the candidate reference set *before* the quarantined agent runs. The agent selects and labels among candidates that already resolve and cannot mint an identifier. Building the weaker construction — agent emits, parser rejects — is the failure mode here, and it is the one spike 4 measured and the design explicitly moved away from.

**Done when:** AC-0220, AC-0221, AC-0222, AC-0238, AC-0242 and AC-0250 are green.

### T4: The record says what this spec established and what it did not

**Depends on:** T3

**Touches:** spikes/README.md, docs/architecture/README.md, docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md

**Tests:**
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.

**Approach:**
- State plainly that the quarantine criteria establish the boundary holds against the cases written, and establish nothing about an adaptive adversary — r8 records that no structural defence has been tested under an unlimited budget, and that gap stays open.
- Update `docs/architecture/README.md` § What is built, which is the map where partial progress is expressible. r5's STATUS header lists the agent layer, the authorization boundary and the provider call as unbuilt. Move the first clause only; the other two are the siblings'.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** three stacked PRs — T1+T2, T3, T4. Each leaves the repository working and is independently reviewable.
- **Review shape:** T3 is **DEEP** and is sized as its own PR for that reason: it is security-boundary work that attracts a mandatory security review, and it carries a failure mode that is invisible in a passing suite. T2 is **MIXED** — the compiler plus seven refusal cases — and splits at the seam between construction and the structural checker if the diff outgrows one reviewable unit. No task here is WIDE.

## Risks

- **The quarantine boundary can be built weak and still pass a shape test.** The pipeline-first construction is the whole guarantee, and a parser that validates shape without a minting authority looks identical in a green suite. AC-0221 is the specific guard; it is named here because it is the criterion most worth an adversarial read.
- **The decision point stands on a framework object.** A change to the wrapper's `call_tool` contract is a change to the authorization boundary and could land in a minor release without being classed as breaking. Mitigated by the T1 contract suite.
- **The blanket refusal can be quietly widened when the predicate lands.** `walking-skeleton-authority-containment` replaces "nothing admits" with a real lookup, and the cheapest way to make its own positive-path criterion pass is to let a miss fall through. AC-0233 cannot catch that — it is scoped to the configuration being replaced — which is why the guard is a criterion in that spec, AC-0235, rather than a re-run of this one.
- **A schema need discovered here is an amendment to a shipped sibling spec.** Mitigated by the foundation spec creating the three agent tables up front, but not eliminated.

## Changelog

- 2026-09-20: initial plan. Cut from `walking-skeleton-agent-runtime`, whose single contract carried AC-0201 through AC-0232 across nine tasks and six stacked PRs — roughly two and a half times either Phase 1 sibling. This spec takes the compiler, the toolset stack and the quarantine boundary; the containment fragment and decision point go to `walking-skeleton-authority-containment`, and the step lifecycle to `walking-skeleton-step-lifecycle` after it. AC-0233 and AC-0234 are the criteria the split creates: the parent spec never needed either, because the decision point's position and its predicate landed in the same contract. The three form a chain: an earlier draft claimed the last two were parallel, which an adversarial spec review falsified, because `walking-skeleton-step-lifecycle`'s AC-0227 requires an approved tool body to run and nothing can admit a call until the predicate exists.
