# Plan: Walking skeleton — agent runtime

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r4 §§ An agent role compiles to an Agent, The toolset stack, Authority containment, The quarantined agent, The model seam, and the integration registry under § Responsibility decomposition. **No analogous production implementation exists.** The substitute is `spikes/phase-0/pydantic_ai_bedrock_spike.py`, which holds executable precedent for the scoped-role Bedrock call, the `WrapperToolset` authorization hook, the history round trip and the approval gate across a process boundary. **Named deviation:** that spike's hook appended to a Python list — no database, no second connection, no failed-append path — so it is precedent for the *seam*, not for the mechanism AC-0211 asserts.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-agent-runtime/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Build the guards before the thing they guard, and keep the provider out of the
loop until the last possible task.

The compiler comes first because it is where every other guarantee is asserted:
the structural invariant, the four compile-time role refusals, the usage-limit
narrowing. The containment fragment follows, because the policy decision point
cannot refuse on argument value until something can decide what a value means —
and the fragment is where the one unsound constructor in the ratified design was
narrowed. Only then does the decision point itself go in, with the toolset stack
around it.

The quarantine boundary is next and is the largest single piece of new thinking,
because the ratified design moved reference production *out* of the model: a
deterministic pipeline mints the candidate set before the quarantined agent
runs, so forgery is unrepresentable rather than detected. That is a different
construction from the one spike 4 tested and falsified, and building the weaker
one by accident is the most likely way to get this wrong.

The provider call and persistence close the spec. Both are small, because the
grounding probe already established that the framework seams behave as the
design assumes.

**The riskiest part is the quarantine boundary**, and the risk is not that it
fails a test. It is that the boundary can be built so that its tests pass while
the guarantee is weaker than the criteria read — a parser that validates shape
without a minting authority admits an attacker-chosen value inside a well-formed
reference. AC-0221 exists to catch precisely that, and it is the criterion to
write first and trust least.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — the framework at step-level-reasoning-library position; `Model` as the portability contract; `WrapperToolset.call_tool` as the decision point; `DeferredToolRequests` carrying the approval gate. ADR-0002 pins 2.45.0.
- `runtime-architecture.md` r7 — ratified with its Known-at-ship gaps accepted **open**. Gap 1 in particular narrows the quarantine guarantee's *scope*; it does not license leaving the guarantee unverified, which is why this spec adds criteria for it.
- `worker-runtime.md` r4 — see § DR dispositions and § Changes asked of r7 below.
- **Hard dependency:** `walking-skeleton-foundation` ships the schema, both append paths, the privilege split and the pool. Nothing here adds a column.
- **Out of scope:** the run state machine, publication, the browser stream, and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

## DR dispositions

The spec makes changing any DR decision an Ask-first boundary, enforceable only
if each carries a disposition. The DRs this spec constructs:

| DR | Decision | Disposition |
| --- | --- | --- |
| DR1 | Publication is an executor transition, suspended by a contentless tool | **Partly here** — the contentless `request_approval()` tool and its suspension land in T7; the publication transition is the evidence spec's |
| DR2 | Two database roles, one process | **Foundation's**, asserted there against real roles |
| DR3 | The credential seam is the model/provider layer | **Lands**, T6 — `BedrockConverseModel` resolves the ambient chain and no `CredentialProvider` indirection is built |
| DR5 | Rejection resumes the conversation, capped at three cycles | **Deferred to the evidence spec**, which owns the approval state transitions. The cap is arbitrary by r4's own admission and Phase 1 is meant to replace it with an observed number |
| DR6 | Three spend ceilings; the step one is pre-call | **Partly here** — the per-step `cost_limit` with pre-request counting, `request_limit` and `tool_calls_limit` land in T2 under AC-0206. The per-run ceiling is the evidence spec's, and the per-account AWS Budgets alarm is outside the application entirely |
| DR8 | Thinking off, and reasoning parts stripped before persisting | **Lands**, T8 — AC-0204 is the primary control, AC-0228 the backstop that does not depend on a setting staying put |
| DR9 | Zero tool and output retries on the quarantined role | **Lands**, T2, AC-0205 |
| DR12 | Per-integration credential scoping is blast radius, not isolation | **Deferred** to the commissioned broker, recorded in the spec's Follow-ons. MVP has one integration, so the union this would bound is a single scope |
| DR13 | `trust_class` is a construction, not a declaration | **Lands**, T5 — AC-0220 is the parser, AC-0221 the minting authority, AC-0203 the compile-time refusal |
| DR4, DR7, DR10, DR11 | Liveness probe as watchdog; re-baseline at Phase 1; upgrade gate at Phase 2; charter amendment | **Not this spec's** — DR4 and DR7 are the evidence spec's, DR10 is triggered at Phase 2, DR11 is already applied to the charter |

## Changes asked of r7

| # | Change | Disposition |
| --- | --- | --- |
| 5 | Scope-qualified object keys | **Lands**, T8, AC-0231. A one-way door, taken before the corpus exists |
| 7 | The decidable fragment is narrowed | **Lands**, T3 — AC-0217 reds if prefix stays expressible on an interpreted type |
| 10 | `CredentialProvider` satisfied at the model boundary | **Lands**, T6, per DR3 |
| 8, 9 | `may_exist`; per-integration credential scopes | **Deferred** with owners, recorded in the spec's Follow-ons |
| 1, 2, 3, 4, 11 | The schema-shaped changes | **Foundation's.** Change 2's behavioural half — a duplicate terminating the step — is AC-0212 here |
| 6, 12 | `awaiting_input`; the `api` metric grant | **Not this spec's** — 6 is the evidence spec's, 12 feeds an AWS deployment that is out of scope |

## Grounding probe

Run before this plan was written, against the pinned version, to disconfirm the
API claims the ratified design rests on. **It disconfirmed none on
`pydantic-ai` 2.45.0**, which is what licenses treating the pin move off
ADR-0001 D5's 2.44.0 as cheap. Some rows carry more than one assertion.

| Claim under test | Source of the claim | Result |
| --- | --- | --- |
| `Agent.run` accepts `cancellation_token` | r4 § The pool | present in signature |
| `UsageLimits` has `cost_limit`, `count_tokens_before_request`, `request_limit`, `tool_calls_limit` | DR6 | all present |
| Tool and output retries budget separately, both zeroable | DR9 | the retry type carries exactly those two budgets |
| `ModelSettings.thinking` exists; a reasoning part is the thing to strip | DR8 | both present |
| `WrapperToolset.call_tool` is an overridable seam | ADR-0001 D3 | `(self, name, tool_args, ctx, tool)` |
| `DeferredToolRequests` carries `calls` as well as `approvals` | r4 GAP 2 | both present |
| `BedrockConverseModel` takes a model id and nothing else | ADR-0001 D2 | only the model name is required |
| A realistic history round-trips byte-identically | r4 § Rollout criterion 6 | identical on second dump, over tool call, tool return and retry parts |
| A reasoning-stripped history round-trips and leaks nothing | DR8 | identical, no reasoning in the bytes |
| `result.usage` is a property; `stream_text` debounces by default | probe-established; no upstream document states either | both confirmed |

`DeferredToolRequests` resolves from a private module re-exported at the package
root. T1 imports it from the root and the framework-seam contract test pins
that, because a re-export moving is exactly the additive-minor drift r4's risk
register names.

**A second probe closed the approval round trip.** A real deferred-approval
suspension driven by `TestModel`: the run suspends with a pending approval, the
suspended history round-trips byte-identically, the gated tool body has not run
at suspension, a fresh agent built from the bytes alone applies the decision and
the tool executes, and the post-approval history round-trips too. What remains
for T8 is the *combination* — a history both realistic in shape and carrying a
pending approval — rather than either half.

That probe also surfaced the closure gotcha: a tool registered on a nested
function raises a context-parameter error, because the framework infers a
context parameter it cannot resolve. The compiler builds toolsets inside a
function, so it resolves module-level callables from the registry.

**A third probe tested the containment bypasses.** Both rows of the r4 table
behave as documented. Three things followed: a **third bypass** the table omits
(`https://www.sec.gov@attacker.example/`, whose userinfo makes a prefix check
read the wrong host — the ratified rule handles it because predicates range over
parsed components, so this hardens the case set rather than holing the design);
**decode-before-normalise is load-bearing and confirmed**, since the encoded
traversal survives the reverse order; and the standard library has **no
public-suffix list**, so AC-0215 needs a dataset dependency.

No probe is committed. Their content becomes the framework-seam contract suite
in T1 and the containment cases in T3, which is the ratified mitigation for
version drift — exact pins plus contract tests at both seams — and a throwaway
script is not that.

## Construction tests

**Integration tests:**
- One quarantine end-to-end: the deterministic pipeline mints a reference set from the recorded filing, the quarantined agent selects among them, the parser admits, and a planning step receives references and scalars only. This is the spine AC-0219 through AC-0222 read.
- One framework-seam contract suite (T1) asserting every check in § Grounding probe, so a version bump fails the build rather than a runtime.

**Manual verification:** none. Every criterion here is machine-checkable.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Current architecture — `worker-runtime.md` status header | T9 | Marker moved off `PLANNED` for what exists | Header matches the repository |
| Decision rationale — the r4 unsafe-prefix table | T3 | The userinfo row added upstream | The table AC-0213 references is complete |
| Reusable learning — `spikes/README.md` | T9 | A section stating what was and was not established | Hypothesis checks separated from setup |

## Design (LLD)

Shape is `service`; the sub-sections below are the set that shape selects.

### Design decisions

- **The compiler is the only constructor of the agent.** It asserts the agent holds exactly one toolset, that it is the decision point, and that the chain beneath it is the specified order. Nesting order only governs tools reached *through* the wrapped stack, so a sibling tool has no ceiling entry to violate and no behavioural test can catch it. Traces to: AC-0201, AC-0202.
- **The structural check is a function over a constructed chain, not a parameter on the compiler.** Asserting order by making the compiler accept an ordered layer list would widen a production contract to make a test possible, and would put stack order in a caller's hands. Instead the compiler builds the chain and calls a checker; the checker is unit-tested against hand-built wrong chains, and the compiled agent is asserted by walking it. Traces to: AC-0202.
- **Mutation evidence is produced by patching in the test process.** The canonicaliser ships no disable switch: a security control carrying seven runtime bypasses to make its own tests expressible is a worse trade than a slightly more awkward test. Traces to: AC-0216.
- **Rejected: typed output as the quarantine boundary.** It would delete the parser and a reviewer will ask. It makes the boundary depend on the framework's serializer and the model's cooperation — the same class of argument r7 used to reject detection-based defence. Typed output stays as a layer.

### Interfaces & contracts

No external interface. The internal seams are the compiler's input (an
`agent_role` version plus a resolved integration set) and its output (an agent
with one toolset), the `Model` subclass, and the parser's admitted-type
contract. Each is exercised directly by its own suite. Traces to: AC-0201,
AC-0220.

### Data & schema

No schema change. This spec reads `agent_role`, `integration_registry` and
`entitlements`, all created by the foundation spec, and writes `events` and
payload objects through the append paths that spec owns. Object keys become
scope-qualified here because this spec writes the first payload object.
Traces to: AC-0231.

### Failure, edge cases & resilience

Three orderings carry the story, all ratified and none negotiable. The
`policy.decision` event commits **before** the invocation it authorises, on a
second connection, and a failed append is a denial rather than a retry. The
content-addressed payload object is written **before** the fenced append that
carries its hash, so a crash leaves an unreferenced object rather than a
dangling reference on a run that can never resume. And the cancellation token is
disarmed the moment the agent run returns, so a deadline firing between the
return and the commit cannot discard a step that succeeded.

The derived idempotency key plus the foundation's partial unique index make a
duplicate invocation fail loudly: the second append raises, the step-event
toolset does not delegate, and the step terminates as duplicate-detected. The
action executes at most once, which is the property the double-publication
hazard needs. Traces to: AC-0211, AC-0212, AC-0230, AC-0232.

### Quality attributes (NFRs)

`step_deadline` is a pool configuration value this spec consumes and the
evidence spec measures. AC-0232 asserts the *bound holds* against whatever value
is configured, which is deliberately independent of that value being the right
one — the calibration criterion lives with the measurement. Traces to: AC-0232.

### Dependencies & integration

New dependencies, recorded before being added per `AGENTS.md`:
`pydantic-ai-slim[bedrock]` 2.45.0, `hypothesis` (the containment property
test), `publicsuffix2` (AC-0215 — the standard library carries no public-suffix
list, established by probe). Everything else is inherited from the foundation
spec's manifest.

External: Amazon Bedrock under a scoped assumed role, reached by exactly one
task. SEC EDGAR is **not** a dependency — the corpus is the recorded fixture.

## Tasks

### T1: The framework seam is pinned

**Depends on:** none

**Touches:** pyproject.toml, src/**/adapters/framework_contract.py, tests/contract/**

**Tests:**
- The contract suite asserts every check in § Grounding probe, including the package-root import path for the deferred-requests type. A re-export moving is additive-minor drift the vendor does not class as breaking, so it must red here rather than in a runtime.

**Approach:**
- Add the framework dependencies to the manifest the foundation spec created.

**Done when:** the contract suite is green and a deliberate downgrade of the pin reds it.

### T2: A role compiles, and four bad roles refuse to

**Depends on:** T1

**Touches:** src/**/agents/compiler.py, tests/compiler/**

**Tests:**
- AC-0201 has two cases, each a compile error rather than a call-time denial.
- AC-0202 walks the constructed chain and asserts the type order; the checker is separately unit-tested against hand-built wrong chains, which is what lets the ordering be asserted without the compiler accepting a layer list.
- AC-0203, AC-0204, AC-0205 and AC-0219 are each a role record the compiler must reject or constrain. AC-0205 asserts the compiled budgets are zero rather than that the role record requested zero — the record is the input, the compiled agent is the fact.
- AC-0206 needs both directions: a role wider than the pool default compiles to the default, a narrower one to itself. Only the widening case protects the operator's reviewable deploy.
- Tools resolve as module-level callables from the registry; a closure trips the framework's context-parameter inference, which the probe hit directly.

**Done when:** AC-0201 through AC-0206 and AC-0219 are green.

### T3: Containment holds on arguments the callee parses

**Depends on:** T2

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

### T4: The decision point is the only way a tool is reached

**Depends on:** T3

**Touches:** src/**/agents/toolsets/**, tests/authorization/**

**Tests:**
- AC-0207 and AC-0208 are the authorization suite. AC-0208 asserts the exception *type* and that it is not the retry type nor a subclass; a bare "raises" assertion passes on the wrong one, and the wrong one degrades the boundary into a negotiation with no visible failure.
- AC-0209 asserts the denial is *recorded*, which is the attributability claim. A refusal that leaves no trace satisfies AC-0207 and still fails the ratified goal.
- AC-0210 uses a call inside the role ceiling and outside the initiating user's entitlements, which is the conjunct no ceiling-only test reaches.
- AC-0211 forces the decision append to fail on its own connection and asserts the tool body did not run, using a spy the body increments. The spy is what makes "did not run" observable rather than inferred.
- AC-0212 drives two invocations deriving the same key and asserts the body ran once and the step terminated duplicate-detected.

**Approach:**
- The decision point appends through the `policy-writer` identity on a second connection, taking the `steps` fence first so the ordering the foundation spec proved is preserved rather than extended.

**Done when:** AC-0207 through AC-0212 are green.

### T5: Free text does not cross the boundary

**Depends on:** T4

**Touches:** src/**/domain/quarantine/**, src/**/agents/toolsets/trust_class.py, tests/quarantine/**

**Tests:**
- AC-0220 feeds the parser output that is neither a closed-vocabulary label nor a typed scalar and asserts the step fails. The parser is the runtime's, outside the agent — a test that drives the agent's structured output instead is testing the layer, not the boundary.
- AC-0221 is the criterion to write first and trust least: a well-formed reference that resolves in *another* step's set must still fail. Shape validity is not provenance, and a parser that checks only shape admits an attacker-chosen value inside a well-formed reference.
- AC-0222 runs a quarantined step over the recorded filing, then a planning step, and asserts the planning step's assembled context contains no free text — including after a round trip through the database, which is the indirect path that would otherwise reopen the boundary.

**Approach:**
- The deterministic pipeline mints the candidate reference set *before* the quarantined agent runs. The agent selects and labels among candidates that already resolve and cannot mint an identifier. Building the weaker construction — agent emits, parser rejects — is the failure mode here, and it is the one spike 4 measured and the design explicitly moved away from.

**Done when:** AC-0220, AC-0221 and AC-0222 are green.

### T6: A real step runs under a scoped role

**Depends on:** T5

**Touches:** src/**/adapters/bedrock/**, src/**/worker/executor.py, tests/provider/**

**Tests:**
- AC-0223 reads the event log for a `step.completed` whose producer tuple names the live adapter, so the evidence is what the system recorded rather than what the harness arranged.
- AC-0224 scans the running container for a long-lived credential, not the compose file — the compose file is the intent, the container is the fact. It asserts the absence of a static key, not the absence of session credentials, which ambient workload identity necessarily delivers to the process.
- AC-0225 reads the producer tuple back off the run header.
- The scoped role is created and assumed by the test setup, as spikes 1 and 7 did.

**Approach:**
- The IAM shape carries over from spike 1 unchanged and is **not** re-derived: inference-profile ARN pinned to the calling region, foundation-model ARN region-wildcarded, no requested-region condition. Both plausible tightenings deny the call outright.
- Record what the local substitution does not establish: on a deployed fleet the task role supplies credentials with no session key in the process environment, and that stronger property is not what AC-0224 demonstrates.

**Done when:** AC-0223, AC-0224 and AC-0225 are green against a real Bedrock call under the scoped role.

### T7: A step suspends for approval and releases its lease

**Depends on:** T6

**Touches:** src/**/worker/executor.py, src/**/agents/tools/approval.py, tests/suspension/**

**Tests:**
- AC-0232 uses a `Model` stub that hangs, so the deadline path is exercised with no provider spend.
- The suspension path produces a payload object and a fenced append in that order, which AC-0230 asserts in T8.

**Approach:**
- The agent's only lever is a contentless `request_approval()`. It cannot publish; the published artifact is the application's typed artifact, which is the evidence spec's transition.

**Done when:** AC-0232 is green and a suspended step is observed releasing its lease.

### T8: A suspended step resumes from bytes alone

**Depends on:** T7

**Touches:** src/**/worker/persistence.py, src/**/adapters/objectstore/**, tests/persistence/**

**Tests:**
- AC-0226 uses a history carrying a tool call, a tool return, a retry part **and** a pending approval. The probe showed each half works; the combination is what spike 7 never asserted.
- AC-0227 builds the resuming agent in a separate process, sharing nothing but the bytes. Same-process reuse would pass on in-memory state the design forbids relying on.
- AC-0228 persists a history that carried a reasoning part and asserts the bytes contain none — a storage property, asserted on storage.
- AC-0229 replays a history carrying stale instruction text and asserts the model receives the current compilation. This is a security property, not an ergonomic one: the role compilation is where the ceiling's sibling text lives.
- AC-0230 injects a crash between the payload write and the fenced append.
- AC-0231 asserts the key's scope prefix.

**Approach:**
- Reasoning parts are stripped in the executor before serialising, not via a history processor — a processor changes what is *sent to the model* and leaves reasoning in exactly the artifact that must not hold it.

**Done when:** AC-0226 through AC-0231 are green.

### T9: The record says what this spec established and what it did not

**Depends on:** T8

**Touches:** spikes/README.md, docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md

**Tests:**
- `python3 .agents/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.

**Approach:**
- State plainly that the quarantine criteria establish the boundary holds against the cases written, and establish nothing about an adaptive adversary — r7 records that no structural defence has been tested under an unlimited budget, and that gap stays open.
- Move the `STATUS: PLANNED` marker only for what now exists.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** six stacked PRs — T1+T2, T3, T4, T5, T6+T7, T8+T9. Each leaves the repository working and is independently reviewable.
- **Review shape:** T4 and T5 are **DEEP** and are sized as their own PRs for that reason: both are security-boundary work that attracts a mandatory security review, and both carry a failure mode that is invisible in a passing suite. T2 is **MIXED** — the compiler plus six refusal cases — and splits at the seam between construction and the structural checker if the diff outgrows one reviewable unit. No task here is WIDE.
- **Reversible:** entirely. Nothing is deployed. The one-way door is the scope-qualified object key in T8, taken now because re-keying later invalidates recorded snapshot identifiers that historical runs must never see change.
- **Infrastructure:** the foundation spec's local Compose. The only cloud dependency is Bedrock, reached by T6 under a scoped assumed role.
- **Deployment sequencing:** none beyond task order; this spec adds no migration.

## Risks

- **The quarantine boundary can be built weak and still pass a shape test.** The pipeline-first construction is the whole guarantee, and a parser that validates shape without a minting authority looks identical in a green suite. AC-0221 is the specific guard; it is named here because it is the criterion most worth an adversarial read.
- **The decision point stands on a framework object.** A change to the wrapper's `call_tool` contract is a change to the authorization boundary and could land in a minor release without being classed as breaking. Mitigated by the T1 contract suite and by the authorization suite running on every build.
- **Denial-as-retry is a one-line footgun.** The difference between a terminal denial and a retryable hint is which exception a future contributor raises. AC-0208 asserts the type; the risk is named because it is the regression reviews miss.
- **T4 and T5 together are most of the security surface.** Split into separate PRs deliberately, so neither review has to hold both.
- **A schema need discovered here is an amendment to a shipped sibling spec.** Mitigated by the foundation spec creating the three agent tables up front, but not eliminated.

## Changelog

- 2026-09-18: initial plan. Split out of a single `walking-skeleton` spec after three review rounds did not converge; this spec carries seven of the eight blockers that split found, which is why it exists separately. The quarantine boundary, the denial record, the entitlements conjunct and the four compile-time role guards are new criteria rather than inherited ones — the monolithic spec built this subsystem and verified almost none of it.
