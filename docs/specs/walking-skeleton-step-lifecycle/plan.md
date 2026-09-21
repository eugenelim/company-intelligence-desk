# Plan: Walking skeleton — the step lifecycle

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 3 Runtime Model ("The approval gate", "Deadline, cancellation, and the honest limit"), § 5 Data and State ("Object keys are scope-qualified from the first object written") and § 6 Deployment and Operations ("The model seam and fixture mode"). **No analogous production implementation exists.** The substitute is `spikes/phase-0/pydantic_ai_bedrock_spike.py`, which holds executable precedent for the scoped-role Bedrock call, the history round trip and the approval gate across a process boundary. **Named deviation:** that spike persisted to memory rather than to an object store, so it is precedent for the *round trip*, not for the crash-ordering AC-0230 asserts.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-step-lifecycle/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Reach the provider once, early, and keep it out of every other task.

The model seam goes in first because it is the only place in the Phase 1 runtime
that needs a cloud credential, and isolating it means the rest of the spec runs
offline. Its IAM shape carries over from spike 1 unchanged and is not
re-derived.

Suspension follows. The agent's only lever is a contentless
`request_approval()`; it cannot publish, and the published artifact is the
application's typed artifact, which is the evidence spec's transition. The
deadline lands in the same task because both are properties of a step that stops
short, and AC-0232 uses a hanging `Model` stub rather than a provider.

Persistence closes the spec. The grounding probes established that each half of
the round trip works; what remains is the combination — a history both realistic
in shape and carrying a pending approval — and the crash ordering, which no
probe touched because it needs an object store.

**The riskiest part is the credential claim.** AC-0224 scans a locally running
container, and the property a reader will assume it establishes — that a
deployed fleet's process environment holds no session key either — is strictly
stronger than what the scan can see. The record has to say so.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — `Model` as the portability contract; `DeferredToolRequests` carrying the approval gate. ADR-0002 pins 2.45.0.
- `runtime-architecture.md` r8 — ratified with its five accepted limits in § 9 accepted **open**.
- `worker-runtime.md` r5 — see § DR dispositions and § Amendments the worker runtime asked of its parent below.
- **Hard dependency:** `walking-skeleton-role-compilation` ships the compiler and pins the framework including the `[bedrock]` extra.
- **Hard dependency:** `walking-skeleton-authority-containment` ships the containment predicate. AC-0227 requires an approved tool body to run, and the decision point admits nothing until that predicate exists.
- **Hard dependency:** `walking-skeleton-foundation` ships the schema, both append paths, the privilege split and the pool. Nothing here adds a column.
- **Placement and re-cut rules:** [`docs/specs/README.md`](../README.md) § Cutting one outcome into several specs.
- **Out of scope:** the compiler, and the quarantine boundary's *construction* — the parser, the minting pipeline and the compile-time refusals — all owned by `walking-skeleton-role-compilation`. **In scope by exception:** AC-0222, AC-0242, AC-0255 and AC-0256, that spec's by subject but observable only through a running step, owned here by T5; the containment fragment and the decision point's predicate, owned by `walking-skeleton-authority-containment`. Both precede this spec; the run state machine, publication, the browser stream and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

## DR dispositions

The spec makes changing any DR decision an Ask-first boundary, enforceable only
if each carries a disposition. **This table lists only the DRs this spec
constructs.** A DR absent from it is not this spec's; the Phase 1 routing is the
union of this table, the sibling plans' and the foundation plan's, and no plan
restates another's rows.

| DR | Decision | Disposition |
| --- | --- | --- |
| DR1 | Publication is an executor transition, suspended by a contentless tool | **Partly here** — the contentless `request_approval()` tool, its suspension and its lease release land in T2; the publication transition is the evidence spec's |
| DR3 | The credential seam is the model/provider layer | **Lands**, T1 — `BedrockConverseModel` resolves the ambient chain and no `CredentialProvider` indirection is built |
| DR8 | Thinking off, and reasoning parts stripped before persisting | **Partly here** — AC-0228 is the storage backstop that does not depend on a setting staying put and lands in T3. The primary control is `walking-skeleton-role-compilation`'s |
| DR12 | Per-integration credential scoping is blast radius, not isolation | **Deferred** to the commissioned broker, recorded in the spec's Follow-ons. MVP has one integration, so the union this would bound is a single scope |

## Amendments the worker runtime asked of its parent

r5 § 10 Rollout records that every amendment this subsystem required is now
folded into `runtime-architecture.md` r8 and is no longer asked for from here,
so there is nothing left for a spec to disposition. r5 names three as
load-bearing for its § 4 invariants: the fenced policy append, the narrowed
decidable fragment, and scope-qualified object keys.

**One of the three is this spec's:** scope-qualified object keys, landing in T3 under AC-0231. A one-way door, taken before the corpus exists. The relocated credential seam is also this spec's, satisfied at the model boundary in T1 per DR3.

## Grounding

The framework-seam probe is recorded once, in
[`walking-skeleton-role-compilation/plan.md`](../walking-skeleton-role-compilation/plan.md)
§ Grounding probe, and is not repeated here. The rows this spec rests on are
`BedrockConverseModel` taking a model id and nothing else, `Agent.run` accepting
`cancellation_token`, `DeferredToolRequests` carrying `calls` as well as
`approvals`, and both history round-trip rows. That spec's T1 contract suite
pins all of them, so a version bump reds there rather than in this spec's
persistence suite.

### Approval probe

A probe run on 2026-09-18 closed the approval round trip. A real deferred-approval
suspension driven by `TestModel`: the run suspends with a pending approval, the
suspended history round-trips byte-identically, the gated tool body has not run
at suspension, a fresh agent built from the bytes alone applies the decision and
the tool executes, and the post-approval history round-trips too.

What remains for T3 is the *combination* — a history both realistic in shape and
carrying a pending approval — rather than either half. The crash ordering
AC-0230 asserts is untouched by any probe, because it needs an object store.

No probe is committed. Its content becomes the persistence suite in T3.

## Construction tests

**Integration tests:**
- One suspension-and-resume end-to-end: a step suspends on `request_approval()`, its history persists as a content-addressed payload object followed by the fenced append, the lease releases, and a separate process resumes from the bytes and applies the decision. This is the spine AC-0226 through AC-0231 read.

**Manual verification:** none. Every criterion here is machine-checkable.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Current architecture — the `worker-runtime.md` marker | T4 | The provider-call clause moved from unbuilt to built | The header's built and unbuilt lists match the repository |
| Current architecture — `docs/architecture/README.md` § What is built | T4 | The model seam, the approval gate and persistence moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Reusable learning — `spikes/README.md` | T4 | A section stating what was and was not established, including what the container scan does not show about a deployed fleet | Hypothesis checks separated from setup |

## Design (LLD)

Shape is `service`; the sub-sections below are the set that shape selects.

### Design decisions

- **Reasoning parts are stripped in the executor before serialising, not via a history processor.** A processor changes what is *sent to the model* and leaves reasoning in exactly the artifact that must not hold it. Traces to: AC-0228.
- **The agent's only approval lever is contentless.** `request_approval()` takes no payload, so the agent cannot choose what gets published; the published artifact is the application's typed artifact. Traces to: AC-0227.
- **The credential seam is the model layer and nothing indirects it.** `BedrockConverseModel` resolves the ambient chain, so there is no `CredentialProvider` object to misconfigure and no place to put a static key. Traces to: AC-0224.
- **No authority input crosses the suspension boundary in the persisted bytes.** The role version is named in the step record and the compilation is fresh from it; the initiating principal comes from the run record; the integration registry resolves at the versions that role version named. The decision point `walking-skeleton-authority-containment` builds evaluates the ceiling and the entitlements conjunct, so this spec's change is confined to what the resume path hands it. Traces to: AC-0229, AC-0241, AC-0245, AC-0248, AC-0253.

### Interfaces & contracts

No external interface. The internal seams are the `Model` subclass, the
serialised history's byte contract, and the payload object's key format. Each is
exercised directly by its own suite. Traces to: AC-0223, AC-0226, AC-0231.

### Data & schema

No schema change, and `runs` carries no producer column — the foundation spec created it with `run_id`, `state`, `next_seq` and `created_at`. The producer tuple is therefore written as the payload of the run's opening event, under AC-0231's scope-qualified key rule when it exceeds an inline scalar. "The run header" in AC-0225 names that payload, not a column. This spec reads the tables the foundation spec created and
writes `events` and payload objects through the append paths that spec owns.
Object keys become scope-qualified here because this spec writes the Phase 1
runtime's first payload object. Traces to: AC-0231.

### Failure, edge cases & resilience

Two orderings carry the story, both ratified and neither negotiable. The
content-addressed payload object is written **before** the fenced append that
carries its hash, so a crash leaves an unreferenced object rather than a
dangling reference on a run that can never resume. And the cancellation token is
disarmed the moment the agent run returns, so a deadline firing between the
return and the commit cannot discard a step that succeeded. Traces to: AC-0230,
AC-0232.

### Quality attributes (NFRs)

`step_deadline` is a pool configuration value this spec consumes and the
evidence spec measures. AC-0232 asserts the *bound holds* against whatever value
is configured, which is deliberately independent of that value being the right
one — the calibration criterion lives with the measurement. Traces to: AC-0232.

### Dependencies & integration

No new package dependency. The framework and its `[bedrock]` extra are pinned by
`walking-skeleton-role-compilation`; everything else is inherited from the
foundation spec's manifest.

External: Amazon Bedrock under a scoped assumed role, reached by exactly one
task. SEC EDGAR is **not** a dependency — the corpus is the recorded fixture.

## Tasks

### T1: A real step runs under a scoped role

**Depends on:** none

**Touches:** src/**/adapters/bedrock/**, src/**/worker/executor.py, tests/provider/**

**Tests:**
- AC-0223 reads the event log for a `step.completed` whose producer tuple names the live adapter, so the evidence is what the system recorded rather than what the harness arranged.
- AC-0224 scans the running container for a long-lived credential, not the compose file — the compose file is the intent, the container is the fact. It asserts the absence of a static key, not the absence of session credentials, which ambient workload identity necessarily delivers to the process.
- AC-0225 reads the producer tuple back off the run header, and AC-0254 asserts the three security-bearing members are present in it. Asserting the tuple exists without naming those members leaves AC-0223's live-versus-replay check resting on a field nothing requires.
- The scoped role is created and assumed by the test setup, as spikes 1 and 7 did.

**Approach:**
- The IAM shape carries over from spike 1 unchanged and is **not** re-derived: inference-profile ARN pinned to the calling region, foundation-model ARN region-wildcarded, no requested-region condition. Both plausible tightenings deny the call outright.

**Done when:** AC-0223, AC-0224 and AC-0225 are green against a real Bedrock call under the scoped role.

### T2: A step suspends for approval and releases its lease

**Depends on:** T1

**Touches:** src/**/worker/executor.py, src/**/agents/tools/approval.py, tests/suspension/**

**Tests:**
- AC-0232 uses a `Model` stub that hangs, so the deadline path is exercised with no provider spend.
- AC-0237 observes the lease column itself after suspension, not the absence of an error, and then has a second worker actually claim the row — the released-and-claimable half is the property AC-0227 depends on and a null lease column alone does not establish it. The release must also follow the payload write and the fenced append, so the test asserts the event is present before the lease clears.
- The suspension path produces a payload object and a fenced append in that order, which AC-0230 asserts in T3.

**Approach:**
- The agent's only lever is a contentless `request_approval()`. It cannot publish; the published artifact is the application's typed artifact, which is the evidence spec's transition.

**Done when:** AC-0232 and AC-0237 are green.

### T3: A suspended step resumes from bytes alone

**Depends on:** T2

**Touches:** src/**/worker/persistence.py, src/**/adapters/objectstore/**, src/**/agents/toolsets/policy_decision.py, tests/persistence/**

**Tests:**
- AC-0226 uses a history carrying a tool call, a tool return, a retry part **and** a pending approval. The probe showed each half works; the combination is what spike 7 never asserted.
- AC-0227 builds the resuming agent in a separate process, sharing nothing but the bytes. Same-process reuse would pass on in-memory state the design forbids relying on. The approved tool needs a ceiling entry the containment predicate admits, which is why `walking-skeleton-authority-containment` is a hard dependency and not a peer.
- AC-0228 persists a history that carried a reasoning part and asserts the bytes contain none — a storage property, asserted on storage.
- AC-0253 revokes an entitlement while a step waits for approval, then resumes it, and asserts the call is refused; AC-0245 is the separate provenance half, driven with a history naming a different principal from the run's. The conjunct is evaluated in the decision point `walking-skeleton-authority-containment` builds, so this task's change is that the resume path hands it the current entitlements rather than a snapshot lifted from the persisted history; the file is in Touches for that reason. The revocation must bite through the entitlements conjunct, because AC-0241 pins the ceiling half to the suspended version and it cannot carry revocation.
- AC-0248 resumes a step after the registry has moved on and asserts the compilation resolved the versions the suspended role version named. The observable is which registry rows the compilation read, not whether the call is refused, because a ceiling can survive a schema change and still mean something different.
- AC-0241 resumes a step whose role version was narrowed after suspension and asserts the tool call is judged against the suspended version's ceiling. The ceiling's source is the assertion; a test that only checks the call is refused passes on the wrong ceiling.
- AC-0229 replays a history carrying stale instruction text and asserts the model receives a fresh compilation of the suspended role version, not the bytes' text and not a later version. Asserting only that the stale text is absent would pass on a compilation of the wrong version, which is the half AC-0241 depends on.
- AC-0230 injects a crash between the payload write and the fenced append.
- AC-0231 asserts the key's scope prefix.

**Approach:**
- The reasoning strip happens in the executor before serialising, per § Design decisions.

**Done when:** AC-0226 through AC-0231, AC-0241, AC-0245, AC-0248 and AC-0253 are green.

### T5: The quarantine boundary holds through a running step

**Depends on:** T1, T3

**Touches:** src/**/worker/executor.py, src/**/worker/context.py, src/**/adapters/postgres/event_log.py, src/**/adapters/objectstore/**, tests/quarantine_step/**

Four criteria arrived from `walking-skeleton-role-compilation` by owner decision
of 2026-09-20. That spec builds the quarantined role, the parser and the
compiled stack; none of these can be observed without a running step and a
context assembler, and no task there could host the module they fail through.
`context.py` is that assembler, and it is new.

**Tests:**
- AC-0222 runs a quarantined step over the recorded filing, then a planning step, and asserts the planning step's assembled context contains no free text — including after a round trip through the database, which is the indirect path a unit test cannot see. Carries `@pytest.mark.substrate`.
- AC-0242 drives a refused integration result whose text is distinctive, then searches the run's events **and every payload object they reference**. AC-0231 makes this spec the first to write a payload object, so the second arm is live here rather than vacuous. Carries `@pytest.mark.substrate`.
- AC-0255 drives the quarantined agent's own output through the parser, then repeats with the role's `output_schema_ref` widened so the framework's schema would accept the refused value, and asserts the step still fails. Runs offline.
- AC-0256 assembles a planning role's context containing a value outside the admitted types by a path that does not originate in a quarantined step, and asserts the assembler fails the step before the agent is constructed. No database.
- **`no stub (implementation-discovered)`.** Discovery predicate: the context assembler's seam is chosen while building the step path T1 and T3 define, and `src/ced/worker/context.py` does not exist. Proof obligation: write one compilable red assertion per criterion against the assembler as discovered, prove each red, and record the seam in `notes/verification-ledger.md` before production code.

**Approach:**
- The assembler is AC-0256's enforcement point and runs before the agent is constructed, so a context carrying free text never reaches a model. AC-0255's parser is the sibling spec's; this task drives it through a step rather than reimplementing it.
- AC-0242's redaction point is where a rejection diagnostic is written, which is why the event-log and object-store paths are in `Touches`.

**Done when:** AC-0255 and AC-0256 are green under `pytest -m 'not substrate'`, and AC-0222 and AC-0242 are green under the full `pytest` run against the Compose substrate.

### T4: The record says what this spec established and what it did not

**Depends on:** T3, T5

**Touches:** spikes/README.md, docs/architecture/README.md, docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md

**Tests:**
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.

**Approach:**
- Record what the local substitution does not establish: on a deployed fleet the task role supplies credentials with no session key in the process environment, and that stronger property is not what AC-0224 demonstrates.
- Update `docs/architecture/README.md` § What is built, which is the map where partial progress is expressible. r5's STATUS header lists the provider call as unbuilt. Move that clause, and decide in the same edit whether `STATUS: PLANNED` still holds once all three are cleared.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** four stacked PRs — T1+T2, T3, T5, T4. Each leaves the repository working and is independently reviewable.
- **Review shape:** every task here is **MIXED** or smaller. T1 is the only spend-bearing task and the only one needing a cloud credential, which is why it leads rather than trails. T5 is **DEEP** and is sized as its own PR: it is security-boundary work carrying a mandatory security review, and its failure mode — a boundary whose tests pass while the guarantee is weaker than the criteria read — is invisible in a green suite.

## Risks

- **The credential criterion reads stronger than it is.** A locally running container is not a deployed fleet, and a reader who skips the caveat will take AC-0224 as proof of a property it cannot see. Mitigated by T4's record, not by the criterion.
- **The deadline can fire on a step that already succeeded.** The window is between the agent run returning and the commit. Mitigated by disarming the cancellation token the moment the run returns; named because the failure is silent data loss rather than an error.
- **The crash ordering is the one part no probe touched.** AC-0230 needs an object store, so it is the criterion with the least executable precedent behind it.
- **A schema need discovered here is an amendment to a shipped sibling spec.** Mitigated by the foundation spec creating the three agent tables up front, but not eliminated.

## Changelog

- 2026-09-20: initial plan. Cut from `walking-skeleton-agent-runtime`, whose single contract carried AC-0201 through AC-0232 across nine tasks and six stacked PRs. This spec takes the parent plan's T6, T7 and T8, and keeps the parent's dependency on the decision point: an earlier draft claimed independence from `walking-skeleton-authority-containment` by arguing the parent's T7→T6 edge was sequencing, which an adversarial spec review falsified — the edge that carried the dependency was T5→T4, because AC-0227 requires an approved tool body to run and nothing admits a call without the containment predicate. The three specs are a chain.
- 2026-09-20: spec approved by eugenelim
- 2026-09-20: plan approved by eugenelim
