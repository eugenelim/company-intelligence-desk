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
- **Hard dependency:** `walking-skeleton-authority-containment` ships the containment fragment, and `walking-skeleton-policy-decision-point` decodes a stored ceiling into it and installs the result on the decision point. AC-0227 requires an approved tool body to run, and the decision point admits nothing until both exist. Two entries would read as two independent edges; they are one chain, separated by the cut of 2026-09-23.
- **Hard dependency:** `walking-skeleton-foundation` ships the schema, both append paths, the privilege split and the pool. Nothing here adds a column.
- **Placement and re-cut rules:** [`docs/specs/README.md`](../README.md) § Cutting one outcome into several specs.
- **Out of scope:** the compiler, and the quarantine boundary's *construction* — the parser, the minting pipeline and the compile-time refusals — all owned by `walking-skeleton-role-compilation`. **In scope by exception:** AC-0222, AC-0242, AC-0255 and AC-0256, that spec's by subject but observable only through a running step, owned here by T5; the containment fragment, owned by `walking-skeleton-authority-containment`, and the decision point itself, owned by `walking-skeleton-policy-decision-point`. All three precede this spec; the run state machine, publication, the browser stream and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

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
| DR8 | Thinking off, and reasoning parts stripped before persisting | **Lands here** — AC-0228 is the storage backstop and lands in T3. `walking-skeleton-role-compilation`'s AC-0204 compiles the disable, and its own security review found the compiled value does not reach the provider; AC-0275 carries the compile-time half in T6 and AC-0276 the run-path half in T7, so the thinking half of DR8 is enforced in this spec rather than asserted in the one that cannot observe it. **Enforced at those two seams and no earlier:** a boot-time refusal was drafted, found to have no sound seam in Phase 1 and withdrawn to the spec's § Follow-ons |
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
- **No authority input crosses the suspension boundary in the persisted bytes.** The role version is named in the step record and the compilation is fresh from it; the initiating principal comes from the run record; the integration registry resolves at the versions that role version named. The decision point `walking-skeleton-policy-decision-point` builds evaluates the ceiling and the entitlements conjunct, so this spec's change is confined to what the resume path hands it. Traces to: AC-0229, AC-0241, AC-0245, AC-0248, AC-0253.

### Interfaces & contracts

No external interface. The internal seams are the `Model` subclass, the
serialised history's byte contract, and the payload object's key format. Each is
exercised directly by its own suite. Traces to: AC-0223, AC-0226, AC-0231.

### Data & schema

No new column, and `runs` carries no producer column — the foundation spec created it with `run_id`, `state`, `next_seq` and `created_at`. The producer tuple is therefore written as the payload of the run's opening event, under AC-0231's scope-qualified key rule when it exceeds an inline scalar. "The run header" in AC-0225 names that payload, not a column. This spec reads the tables the foundation spec created and
writes `events` and payload objects through the append paths that spec owns.
**Something is added that is not a column, and this section does not say what.**
`migrations/versions/**` is in T3's Touches because a database-level seam is the
expected route for AC-0264: `0003_role_configuration_records.py` widened
`integration_registry`'s primary key to `(integration_name, version)` and states
in place that r5 § 4's "a version in use is immutable" "needs enforcement this
delta does not build", naming this spec as its owner. **The seam itself stays the
implementation's choice**, which is what `spec.md` AC-0264 and T3's pinned
`Tests` both say; an earlier draft of this paragraph excluded an application-level
check outright, which contradicted both and, by pointing at a constraint, pointed
at the one database mechanism that cannot express the predicate — `ceiling` is a
column on `agent_role`, not on the table being written, so a `CHECK` cannot
reference it and a trigger would be needed.
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

**Depends on:** T6 — merged, not merely authored, before the repository's first live provider call.

**Touches:** src/**/adapters/bedrock/**, src/**/worker/executor.py, tests/provider/**

**Tests:**
- AC-0223 reads the event log for a `step.completed` whose producer tuple names the live adapter, so the evidence is what the system recorded rather than what the harness arranged.
- AC-0224 scans the running container for a long-lived credential, not the compose file — the compose file is the intent, the container is the fact. It asserts the absence of a static key, not the absence of session credentials, which ambient workload identity necessarily delivers to the process.
- AC-0225 reads the producer tuple back off the run header, and AC-0254 asserts the three security-bearing members are present in it. Asserting the tuple exists without naming those members leaves AC-0223's live-versus-replay check resting on a field nothing requires.
- The scoped role is created and assumed by the test setup, as spikes 1 and 7 did.

**Approach:**
- The IAM shape carries over from spike 1 unchanged and is **not** re-derived: inference-profile ARN pinned to the calling region, foundation-model ARN region-wildcarded, no requested-region condition. Both plausible tightenings deny the call outright.

**Done when:** AC-0223, AC-0224, AC-0225 and AC-0254 are green against a real Bedrock call under the scoped role, **and T6's PR is merged before this PR opens.** T6's criteria are named here as a gate, not as ownership — T6 and T7 own them, and this sentence avoids repeating their identifiers because the alignment lint cannot tell a gate from an owner. T1 is the first live call in the repository and T6 is what stops it reasoning: on the pin the disable reaches the wire only for the Claude families T6's compile-time refusal admits, and this spec's model id must be one of them. AC-0228's storage backstop does not land until T3, so between these points the durable record is protected by the request-side control alone — stated because that is a real uncovered interval, not a covered one.

### T2: A step suspends for approval and releases its lease

**Depends on:** T1

**Touches:** src/**/worker/executor.py, src/**/agents/tools/approval.py, tests/suspension/**, tests/usage_limits/**

**Tests:**
- AC-0232 uses a `Model` stub that hangs, so the deadline path is exercised with no provider spend.
- AC-0237 observes the lease column itself after suspension, not the absence of an error, and then has a second worker actually claim the row — the released-and-claimable half is the property AC-0227 depends on and a null lease column alone does not establish it. The release must also follow the payload write and the fenced append, so the test asserts the event is present before the lease clears.
- The suspension path produces a payload object and a fenced append in that order, which AC-0230 asserts in T3.
- **AC-0263 lands here, in two halves.** Both are properties of the step path this task builds rather than of the compiler that resolved the values. **Identity:** a tool inside the compiled stack reads `RunContext.usage_limits` mid-run and the test asserts it equals what `compile_role` resolved. The read is production-side — the executor places that value, the test only observes it — which is what keeps the caller-supplied bound from being the thing asserted. **Enforcement:** a run is driven past one of the resolved thresholds and the test asserts it is refused. **The halves are not independent and the plan says so rather than implying otherwise:** on this pin the framework enforces against the same object it exposes as `RunContext.usage_limits`, so identity implies enforcement. The converse fails — enforcement alone passes on a caller's bound — so identity is the load-bearing half and enforcement is kept as a framework-regression guard against a later pin that accepts a limits object and stops applying it. **The criterion's original observable had no seam** — it named a stub model recording the limits it was invoked under, and no model-side seam on the pin receives `UsageLimits`, so the only writable test was the fail-open the criterion forbids; the spec's wording was corrected on 2026-09-24 and this bullet follows it. No provider is reached, so both halves run offline and carry no `substrate` marker. **It is here because it had no owning task at all** — the pre-EXECUTE review of 2026-09-24 found it live in § Acceptance Criteria and named in no `Tests` or `Done when`, which would have made it an unchecked `- [ ]` and a HARD `lint-spec-status.py` violation at the `Shipped` transition.

**Approach:**
- The agent's only lever is a contentless `request_approval()`. It cannot publish; the published artifact is the application's typed artifact, which is the evidence spec's transition.

**Done when:** AC-0232, AC-0237 and AC-0263 are green.

### T3: A suspended step resumes from bytes alone

**Depends on:** T2

**Touches:** src/**/worker/persistence.py, src/**/adapters/objectstore/**, src/**/agents/toolsets/policy.py, migrations/versions/**, tests/persistence/**

**Tests:**
- AC-0226 uses a history carrying a tool call, a tool return, a retry part **and** a pending approval. The probe showed each half works; the combination is what spike 7 never asserted.
- AC-0227 builds the resuming agent in a separate process, sharing nothing but the bytes. Same-process reuse would pass on in-memory state the design forbids relying on. The approved tool needs a ceiling entry the installed containment predicate admits, which is why `walking-skeleton-authority-containment` and `walking-skeleton-policy-decision-point` are hard dependencies and not peers.
- AC-0228 persists a history that carried a reasoning part and asserts the bytes contain none — a storage property, asserted on storage.
- AC-0253 revokes an entitlement while a step waits for approval, then resumes it, and asserts the call is refused; AC-0245 is the separate provenance half, driven with a history naming a different principal from the run's. The conjunct is evaluated in the decision point `walking-skeleton-policy-decision-point` builds, so this task's change is that the resume path hands it the current entitlements rather than a snapshot lifted from the persisted history; the file is in Touches for that reason. The revocation must bite through the entitlements conjunct, because AC-0241 pins the ceiling half to the suspended version and it cannot carry revocation.
- AC-0248 resumes a step after the registry has moved on and asserts the compilation resolved the versions the suspended role version named. The observable is which registry rows the compilation read, not whether the call is refused, because a ceiling can survive a schema change and still mean something different.
- AC-0241 resumes a step whose role version was narrowed after suspension and asserts the tool call is judged against the suspended version's ceiling. The ceiling's source is the assertion; a test that only checks the call is refused passes on the wrong ceiling.
- AC-0229 replays a history carrying stale instruction text and asserts the model receives a fresh compilation of the suspended role version, not the bytes' text and not a later version. Asserting only that the stale text is absent would pass on a compilation of the wrong version, which is the half AC-0241 depends on.
- AC-0230 injects a crash between the payload write and the fenced append.
- AC-0231 asserts the key's scope prefix.
- **AC-0264 lands here; `spec.md` owns the seam question and leaves it to the implementation.** `migrations/versions/0003_role_configuration_records.py` widened the `integration_registry` primary key to `(integration_name, version)` and states in place that r5 § 4's "a version in use is immutable" "needs enforcement this delta does not build; `walking-skeleton-step-lifecycle` owns it, since its AC-0248 depends on it" — so the obligation was handed to this spec by the migration that created the gap, and `migrations/versions/**` joins Touches for it. The test rewrites an `integration_registry` row at a version a role's `ceiling` pins and asserts the write is refused; the refusal is contract and the enforcement seam is the implementation's choice. **The check must be shown non-vacuous, and this is a required obligation of the task rather than a reviewer's request.** `0001_base_schema.py` grants `app_api` and `app_worker` only `SELECT` on `integration_registry` and `app_policy` no table access at all, so three of the four connection fixtures `tests/conftest.py` exposes cannot perform this write in the first place — a test written on any of them gets permission-denied, the refusal assertion passes, and the criterion goes green while the enforcement was never built. T3 must therefore demonstrate the check **reds when the new enforcement is absent** and not merely when a pre-existing grant denies the writer, and record that demonstration in `notes/verification-ledger.md`. The attacking identity follows from whichever seam the implementation chooses and is deliberately not fixed here. It pairs with AC-0248, which is green throughout the attack it prevents: an in-place edit of a pinned row's `arg_schema` reclassifies an argument under a step already in flight and reopens the prefix constructor that `walking-skeleton-authority-containment` removed. **That neighbouring spec's criterion is named by description and not by identifier**, because the alignment lint reads any identifier in a pinned `Tests:` field as a claim of ownership and resolves it against this spec's criteria alone. Carries `@pytest.mark.substrate` because the check needs a live Postgres to attempt the write at all, whichever seam refuses it. **It is here because it had no owning task at all**, on the same 2026-09-24 finding that gave T2 its usage-limits criterion — named by task rather than by identifier for the reason just given.

**Approach:**
- The reasoning strip happens in the executor before serialising, per § Design decisions.

**Done when:** AC-0226 through AC-0231, AC-0241, AC-0245, AC-0248, AC-0253 and AC-0264 are green.

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
- **Stub** (`stub: true`) for AC-0255 — the parser seam is pinned by `walking-skeleton-role-compilation`'s own stub, so this criterion does not wait on discovery:

  ```python
  # STUB: AC-0255
  # tests/quarantine_step/test_agent_output_is_parsed.py
  import pytest

  from ced.domain.quarantine.parser import AdmittedTypeRefused, admit


  def test_agent_output_fields_go_through_the_parser() -> None:
      with pytest.raises(AdmittedTypeRefused):
          admit("Apple reported record revenue this quarter.")
  ```

  Validation: fails at collection with `ModuleNotFoundError: No module named 'ced.domain.quarantine'`. The widening arm grows from this surface once the output-contract member exists.
- **`no stub (implementation-discovered)`** for AC-0222, AC-0242 and AC-0256. Discovery predicate: the context assembler's seam is chosen while building the step path T1 and T3 define, and `src/ced/worker/context.py` does not exist. Proof obligation: write one compilable red assertion per criterion against the assembler as discovered, prove each red, and record the seam in `notes/verification-ledger.md` before production code.

**Approach:**
- The assembler is AC-0256's enforcement point and runs before the agent is constructed, so a context carrying free text never reaches a model. AC-0255's parser is the sibling spec's; this task drives it through a step rather than reimplementing it.
- AC-0242's redaction point is where a rejection diagnostic is written, which is why the event-log and object-store paths are in `Touches`.

**Done when:** AC-0255 and AC-0256 are green under `pytest -m 'not substrate'`, and AC-0222 and AC-0242 are green under the full `pytest` run against the Compose substrate.

### T6: A role cannot compile against a model that would reason

**Depends on:** none. `compile_role` is public today and already resolves the
model itself, and the `adapters/` seam this task adds needs no live provider, so
nothing here waits on the model seam. **T6 ships first and T1 depends on it**,
which is what keeps the repository's first live provider call from reasoning.

**Touches:** src/**/adapters/**, src/**/agents/compiler.py, src/**/worker/pool.py, tests/worker/test_pool_configuration.py, tests/compiler/role_records.py,
deploy/compose.yaml, AGENTS.md, tests/thinking_reaches_the_model/**

`walking-skeleton-role-compilation` ships the compiler this task adds a refusal
to. That spec is `Shipped` and its contract frozen, so the **criterion** is this
spec's while the **code** lands in the module it built. Nothing here reopens
AC-0204, whose carve-out stays as written; AC-0275 is a superset of it.

**Tests:**
- **The `adapters/` seam lands here**, and it is the reason `src/**/adapters/**` is in Touches: it answers, for a resolved model, whether the request that model would send carries a provider-level disable, by running the model's own settings-to-request resolution. It is the only place a provider's rendering is named, which is what keeps `agents/` free of provider knowledge and this criterion clear of r5 § 2 R3.
- **The non-provider declaration lands here too**, as `CED_POOL_NON_PROVIDER_MODEL_IDS`, a pool value separate from `CED_POOL_ALLOWED_MODEL_IDS`, with no in-code default, an absent value declaring no id, and a malformed value refused by `verify_boot` on the same terms as the pool's other two. **`AGENTS.md` is in Touches for this:** § Running the two deployables documents the worker invocation with exactly two pool variables and says **both are required**, and this change adds a third that is **optional** — an absent value declares no id, which is a different contract from the other two and is the documentation delta the reader needs. **An earlier draft justified this differently and the justification was false**, found by the pre-EXECUTE review of 2026-09-24: it claimed the documented command would yield a worker that boots and then refuses its first role compile, but `compile_role` has no production caller — it appears under `src/` only inside `agents/compiler.py` and nowhere under `src/ced/worker/` — so a worker started that way compiles no role at all, and the same bullet already predicted the opposite four sentences later. `deploy/compose.yaml` sets the variable on both services beside the other two, and its worker services run a sleeping step body, which is the same reason. Reading allow-list membership as the declaration admits every id that reaches compilation, so the declaration needs a check that can fail. **The deployment's own configuration cannot be that check:** nothing wires a `model_factory`, so `resolve_model` yields no model for `stub:counting` and the compile is already admitted by the no-adapter case — removing the declaration leaves it green, and the check passes identically with the carve-out absent. That is the dead-check shape this repository already has a register entry for on `tests/quarantine/test_label_vocabulary.py`. The discriminating check therefore runs against a pool whose factory **does** resolve `stub:counting` to a model the seam would otherwise refuse, so the declaration is the only thing admitting it and removing it alone reds the compile — with the allowed set left intact, so the refusal cannot be AC-0251's. The deployment's unwired-factory compile is a separate check and proves only the boot and compose half.
- AC-0275 compiles once per outcome. The set below is not closed by the count in this bullet — the carve-out bullet above adds two more required compiles — and these four are required, a refusal-only suite being unable to show the guard discriminates: an adapter whose resolved request carries a disable is admitted; one whose request carries none is refused naming the model id; a pool with no adapter wired is admitted, that case belonging to T7 and named by task rather than by identifier, since the alignment lint reads a pinned `Tests:` mention as ownership; a model id resolving to no profile is **refused**, not treated as a fixture, since an unrecognised real id resolves to no profile too; a model whose **class** the seam cannot interrogate is refused on the same reasoning; and a model whose rendering carries thinking **enabled** or **adaptive** is refused, without which a presence-of-a-thinking-key predicate passes the whole suite.
- **Two further required checks, each closing a normative AC-0275 clause the enumeration above left out.** Both were found by the pre-EXECUTE review of 2026-09-24, which noted that `Done when` binds "AC-0275 is green" — the whole criterion — while the enumerated set named neither, so the obligation was bound and the required check was not. **(a)** A declared non-provider id that nonetheless resolves to a **provider-backed** model is refused. This is the clause that keeps the declaration from becoming an operator-supplied bypass, and it is what makes the stated evaluation order a tiebreak over the uninterrogable case rather than a blanket admission. **(b)** A malformed `CED_POOL_NON_PROVIDER_MODEL_IDS` is refused by `verify_boot` before it opens a database connection, on the same terms as the pool's other two values, and the refusal names the variable. **It is hosted in `tests/worker/test_pool_configuration.py`**, which is where every `verify_boot` refusal already lives and which owns the `no_database` fixture that makes "the refusal precedes the connection" an assertion rather than an assumption; re-creating it under `tests/thinking_reaches_the_model/` without that fixture would pass on any machine with the substrate up, for the wrong reason. Those same terms settle the empty value by reference: an unset variable declares no id, an empty string is refused like the other two. The check drives the unquoted-array hand-edit — `'[stub:counting]'` — because a parser returning `()` on a decode error would silently declare no id, boot both workers green, and surface only as an unexplained compile refusal in production.
- **At least one admitted/refused pair is decided against a real provider adapter, not a test double.** The pair is a constructed `BedrockConverseModel` on **provider-prefixed Bedrock model ids**, geo prefix optional — one resolving to a non-adaptive family, which must be admitted, and one resolving to an adaptive family, which must be refused. **The id form is load-bearing and the bare family names § Assumptions lists are not constructor arguments.** They are the family prefixes a Bedrock id resolves *to*: `split_bedrock_model_id` returns no provider for a bare `claude-sonnet-4-5`, so the profile lookup misses, `bedrock_thinking_variant` is unset and the rendered blob carries no `thinking` key at all — rendering `None`, which is byte-identical to what an adaptive member renders. A pair built from bare names therefore decides its admitted half through the **no-profile** refusal rather than through the rendering it exists to calibrate, and the obvious repair for that red removes the only real-model check standing before T1's first live call. Measured on the pin on 2026-09-24: `claude-sonnet-4-5` renders `None`, while `anthropic.claude-sonnet-4-5-v1:0` and `us.anthropic.claude-sonnet-4-5-20250929-v1:0` both render `{'thinking': {'type': 'disabled'}}` and `us.anthropic.claude-sonnet-5` renders `None`. This is verified offline and reaches no provider — the adapter constructs from a region name alone with no credentials, and the seam issues no call. **The reason it is required here rather than in T7** is that the calibration clause tying the seam's answer to the request a model actually builds belongs to T7's criterion, and T7 depends on T1 — so the repository's first live provider call would otherwise be gated by a seam whose answer nothing had ever checked against a real model. T7's criterion is named by task here rather than by identifier, because the alignment lint reads any identifier in a pinned `Tests:` field as a claim that this task verifies it. A seam that reports "carries a disable" for every profile passes an all-double suite and fails this pair.
- A declared non-provider model is admitted, and the declaration is what admits it. The test asserts the deployment's own `stub:counting` compiles, and that removing the declaration while leaving the id makes the same compile fail — otherwise the carve-out is indistinguishable from the unrecognised-prefix drop it must not become.
- The seam's probe begins at `ModelSettings(thinking=False)` and runs the model's full settings-to-request resolution, not the renderer alone. A test that hands a hand-built parameters object to the renderer skips the always-thinking discard and the neither-flag case, and is green today only because no Bedrock Anthropic profile sets `thinking_always_enabled` on this pin — which is a property of the pin, not of the guard.
- **Mutation proof is the task's own obligation, not a review's.** Disable the guard and record in `notes/verification-ledger.md` which checks red and which stay green. **One case is mandatory:** prove each check reds for the guard's own reason and not on a missing fixture or an import error — the shape that shipped green twice in this task's own stubs.
- **Stub** (`stub: true`) for AC-0275:

  ```python
  # STUB: AC-0275
  # tests/thinking_reaches_the_model/test_compile_refuses_an_unreachable_disable.py
  import pytest

  from ced.agents.compiler import ThinkingDisableUnreachable, compile_role


  def test_compiling_against_an_adapter_that_renders_no_disable_is_refused() -> None:
      pool = _pool_resolving_to(_renders_nothing())
      with pytest.raises(ThinkingDisableUnreachable):
          compile_role(a_role(), (), pool)
  ```

  Validation: fails at collection with `ImportError: cannot import name 'ThinkingDisableUnreachable' from 'ced.agents.compiler'`. **That is collection-time red only and is not sufficient on its own** — `a_role()`, `_renders_nothing()` and `_pool_resolving_to()` are the implementer's, so until they exist the stub cannot show its assertion reaches the guard. **It passes no adapter argument**: `compile_role` already resolves the model itself via `resolve_model(str(model_settings["model_id"]), pool)`, passed inline to the `Agent(...)` construction — cited by symbol rather than by line, because an earlier draft cited line 501 and the call had drifted to 507, so the checked object is the one the compiled agent carries. An earlier draft added a fourth argument and justified it by that function's docstring; the reservation there is for the event layer's `StepContext` specifically, not a general licence, and the citation was wrong. Proof obligation, discharged before production code: once the symbol exists, prove the assertion reds for the guard's own reason, not on a missing helper. **The first version of this stub was wrong twice** and is recorded so the correction is auditable: it passed `{}` as the role, which raises `KeyError` on `role["role_name"]` before any guard, and it asserted a refusal for `adapter=None`, a case AC-0275 admits.

**Approach:**
- The obligation is a property, not a mechanism list, because several layers defeat the compiled value independently and a guard scoped to any one leaves the rest open. **The canonical account of those layers is the spec's § Assumptions and nowhere else** — this plan, the register entry and the predecessor spec's Follow-ons point at it rather than restating it, because the first draft carried four copies and they had drifted apart by the first review.
- **Residual harm before this task lands is bounded, not absent:** no provider call ships in `walking-skeleton-role-compilation`, and the deployed pool admits only `stub:counting`. The exposure is configuration rather than code, which is why the refusal reads the resolved model rather than the deployment's id list.

**Done when:** AC-0275 is green under `pytest -m 'not substrate'` — including the declared-but-provider-backed refusal, the `verify_boot` malformed-value refusal, and the real-adapter admitted/refused pair — the deployment's own `stub:counting` configuration still compiles and both worker services still boot, and the verification ledger records which checks red when the guard is disabled and which stay green.

### T7: No path to the provider can re-enable reasoning

**Depends on:** T1, T2 — the step path and the model seam it installs.

**Touches:** src/**/adapters/**, src/**/worker/executor.py, tests/thinking_reaches_the_model/**. `src/**/agents/models.py` is deliberately **not** here: it is `resolve_model`, the pool-factory path, and a guard bound there is bypassed by the per-step substitution this task's fourth route drives. The seam that does satisfy the criterion's stated outcome is undiscovered, and locating and recording it is part of the discovery obligation below.

**Tests:**
- AC-0276 asserts no call reaches a provider unless the model actually invoked would send a disable, driven five ways: per-run settings, an attached thinking capability, a caller-supplied adapter-native carrier, a model substituted after compilation, and a capability wrapping the request that replaces its context, **driven from the framework's innermost ordering tier** — the tier the bundled durable-execution capabilities declare — since a guard outrun only by an innermost peer passes a route driven by an ordinary capability. **Each route is driven twice against the same model**, once re-enabling reasoning and refused and once without it and admitted, so a guard that refuses everything it cannot classify is distinguishable from one that observes the route. One predicate decides them all; reading `ModelRequestParameters.thinking` is refused as the observable, being green on the third route and on every profile declaring neither flag.
- The guard is asserted against the **outcome** the criterion states — it sees the model and settings the invoked model actually receives — and not against a named seam, which has been wrong twice and which this task's own Touches records as undiscovered. The one claim worth keeping from the earlier wording: a test proving the guard only from the executor's call site proves it above the settings layering, so it is not sufficient. The test drives a real agent run so the layering actually happens.
- **Every model method reaching the provider is asserted**, which for this adapter on this pin is the request path and `count_tokens`. **One interception point may not cover both:** `count_tokens` runs outside the request-wrapping chain, so a guard placed in that chain never sees it while a guard placed before the model request does. The ledger records which point guards each method; discharging the task with one point and one method attributed leaves the other unguarded. Streaming and non-streaming both funnel into one build site and are not the distinction that matters; `count_tokens` is the genuinely separate one, a wrapper forwards it unguarded, and ADR-0006 D1's return condition plans to switch it on.
- **A model substituted after compilation is the fourth route.** The framework re-resolves the step's model from a selector or capability and reassigns it per step, so a guard bound to the instance compiled against or wrapped at construction misses it. The test substitutes a reasoning model mid-run and asserts the call is refused.
- The guard asks the same `adapters/` seam T6 adds and does not re-derive the answer itself; a seam guard with its own rendering logic is the restatement T6's criterion forbids, running in production.
- The unwired-factory case is asserted here rather than in T6: `model_factory` defaults to `None`, T6's criterion admits that compile by design, and this is where the resulting call is refused.
- **`no stub (implementation-discovered)`** for AC-0276. Discovery predicate: its seam is the model-seam guard the step path installs, and neither `src/ced/worker/executor.py` nor that guard exists. Proof obligation: one compilable red assertion against the seam as discovered, proved red for its own reason, with the seam recorded in `notes/verification-ledger.md` before production code.
- **Mutation proof:** disable the guard and record which of the five routes red and which stay green, per route rather than in aggregate. The paired admit case is what makes each red attributable to its route.

**Approach:**
- Split from T6 because T6 depends on nothing and gates T1, while this needs the seam T1 and T2 build. One task declared a cycle: T1 would depend on T6 and T6 on T1.
- AC-0276's recording construction is the shape AC-0263 uses for usage limits. That is a precedent for the shape only — AC-0263 is **T2's**, not T7's, so the identifier stays in this working-material field rather than in `Tests:`, where naming it would report it as verified here. **This sentence previously said AC-0263 was owned by no task in this plan, and that was the whole of the record for it**; the pre-EXECUTE review of 2026-09-24 found that an unowned live criterion is a HARD `lint-spec-status.py` violation at the `Shipped` transition, and the owner's decision of that date gave it T2.
- T1's live call runs before this task. Not free, and stated rather than implied: AC-0275 has already refused every model whose request would carry no disable, so the call cannot reason through the compiled path; what remains uncovered until here is a caller re-enabling it at the seam, and the case T6's criterion admits undecided because no adapter was wired — both of which in T1 are this spec's own code and not a third party's, and the second is narrow because T1 must wire an adapter for AC-0223 to be green at all.

**Done when:** AC-0276 is green under `pytest -m 'not substrate'` with all five routes driven in refused/admitted pairs on every provider-reaching method, and the ledger records the mutation result per route.

### T4: The record says what this spec established and what it did not

**Depends on:** T3, T5, T6, T7

**Touches:** spikes/README.md, docs/architecture/README.md, docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md

**Tests:**
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.

**Approach:**
- Record what the local substitution does not establish: on a deployed fleet the task role supplies credentials with no session key in the process environment, and that stronger property is not what AC-0224 demonstrates.
- Update `docs/architecture/README.md` § What is built, which is the map where partial progress is expressible. r5's STATUS header lists the provider call as unbuilt. Move that clause, and decide in the same edit whether `STATUS: PLANNED` still holds once the provider-call clause is cleared. **That clause is the header's only remaining unbuilt one** — it currently reads that the pool, the lease protocol, the privilege split, the agent layer and the authorization boundary are built and the provider call is not, the last two having moved to built since this plan was drafted, so an earlier "all three" wording described a state the header no longer has.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** five stacked PRs — T6, T1+T2+T7, T3, T5, T4. **T6 is its own PR and merges before the PR carrying T1**, stated once and in one way: intra-PR ordering is enforced by no gate, so "T6 ships inside T1's PR, earlier in the branch" would rest the repository's first live provider call on a reviewer reading commits in order. A separate merged PR is a condition a gate can check. The task graph is acyclic: T6 depends on nothing, T1 on T6, T7 on T1 and T2. Each leaves the repository working and is independently reviewable.
- **Review shape:** T1 is the only spend-bearing task and the only one needing a cloud credential, which is why it leads rather than trails. T5 is **DEEP** and is sized as its own PR: it is security-boundary work carrying a mandatory security review, and its failure mode — a boundary whose tests pass while the guarantee is weaker than the criteria read — is invisible in a green suite. T6 is **DEEP** and is sized as its own review; § Delivery owns its ordering and is the only statement of it. It carries a mandatory security review, and its failure mode is the one this row cites for T5 — tests pass while the guarantee is weaker than the criteria read — which has already happened once on this exact obligation. Two criteria over two seams — the compiler and the model seam — split across T6 and T7, each independently reviewable. **T7 is DEEP and carries the mandatory security review too**, classified against the same rule as T5 rather than left to the catch-all: it owns the refusal that actually stops a call reaching the provider, across five defeat routes, at a seam that does not yet exist, and its failure mode is the one this row names — tests pass while the guarantee is weaker than the criteria read. Every other task here is **MIXED** or smaller.

## Risks

- **The credential criterion reads stronger than it is.** A locally running container is not a deployed fleet, and a reader who skips the caveat will take AC-0224 as proof of a property it cannot see. Mitigated by T4's record, not by the criterion.
- **The deadline can fire on a step that already succeeded.** The window is between the agent run returning and the commit. Mitigated by disarming the cancellation token the moment the run returns; named because the failure is silent data loss rather than an error.
- **The crash ordering is the one part no probe touched.** AC-0230 needs an object store, so it is the criterion with the least executable precedent behind it.
- **A schema need discovered here is an amendment to a shipped sibling spec.** Mitigated by the foundation spec creating the three agent tables up front, but not eliminated.

## Changelog

- 2026-09-20: initial plan. Cut from `walking-skeleton-agent-runtime`, whose single contract carried AC-0201 through AC-0232 across nine tasks and six stacked PRs. This spec takes the parent plan's T6, T7 and T8, and keeps the parent's dependency on the decision point: an earlier draft claimed independence from `walking-skeleton-authority-containment` by arguing the parent's T7→T6 edge was sequencing, which an adversarial spec review falsified — the edge that carried the dependency was T5→T4, because AC-0227 requires an approved tool body to run and nothing admits a call without the containment predicate. The three specs are a chain.
- 2026-09-20: spec approved by eugenelim
- 2026-09-20: plan approved by eugenelim
- 2026-09-22: spec and plan returned to `Draft`/`Drafting` to carry an inherited obligation as contract **before this spec's baseline seals**. `walking-skeleton-role-compilation`'s AC-0204 compiles `thinking=False`; its mandatory security review found the value does not reach the provider, and its § Follow-ons routed the new controls to the spec that first issues a provider call. AC-0275 and AC-0276 and task T6 carry it. **Two criteria rather than one**, because the compile-time refusal and the run-path property have different seams and different mutation proofs, and one criterion goes green on whichever half holds. **Both here rather than an amendment to `walking-skeleton-role-compilation`'s compiler**, on three grounds: that spec is `Shipped` and its controlled-amendment transition is unavailable, as the closed `tools-array-elements-unchecked` register entry already records for the same compiler; its own § Follow-ons routes the controls here; and the adapter-rendering half cannot be decided without an adapter, which that spec does not ship. The refusal's code still lands in the compiler it built — the contract moves, not the module. **AC-0204 is not reworded**: its carve-out describes a `prepare_request` drop that is genuinely unreachable on a `supports_thinking`-only profile, and the widened obligation is a superset of it. No engine run was initialised. **The first recorded reason for that was wrong and is corrected here:** the `engine-state.json` guard is per spec directory, this directory has none, so `loop-engine init --mode spec-plan` would have succeeded. The actual reason is what that run would leave behind — a spec-plan run ends at `DONE`, and `init` then refuses the code-mode implementation run until someone performs the destructive `loop-cohort reset` / `loop-engine reset` pair, which needs human authorization. One engine run per spec is the pattern `walking-skeleton-role-compilation` follows, whose single run is `mode: code`. **Re-approval of both gates is owed to eugenelim.**
- 2026-09-22: round 2 of both reviews. **The round-1 text repeated the defect it was written to fix.** AC-0276 pinned its read to `ModelRequestParameters.thinking`, which is assigned at one site gated on the unified key surviving the merge — and a `False` there still renders nothing on an adaptive profile, so the criterion could have gone green while the provider reasoned, exactly as AC-0204 does. The observable is now the rendered request, which also makes all three adversarial routes decidable by one predicate and closes the wrapper-forwarding hole. **A second read-one-branch error was caught and corrected:** "the current Claude families take the adaptive branch" is false for `claude-sonnet-4-5` and earlier, which do render the disable. **Owner decision of 2026-09-22 restricts Phase 1 to the families where the unified setting reaches the wire**, which removes the compiler-supplied carrier the round-1 text introduced and with it the conflict with r5 § 2 R3; Sonnet 5 and Opus 5 are out of Phase 1 on Bedrock and the § Follow-ons entry records the return condition. **The task graph declared a T1 ↔ T6 cycle**, now split: T6 depends on nothing and gates T1, T7 carries AC-0276 behind the executor. **Both stubs were broken and are rewritten** — one asserted a refusal AC-0275 admits and passed a role record that raises `KeyError` before any guard, the other went green on the `ValueError` for a missing `CED_POOL_DEFAULT_LIMITS`; each is recorded in place so the correction is auditable, and the validation sentences now say collection-time red is not sufficient.
- 2026-09-22: round 3 of both reviews, which converged and settled the shape at **two criteria**. **AC-0277 is withdrawn and its identifier is not reallocated.** A boot-time refusal was undecidable everywhere it could sit: `verify_boot` is in `worker/`, the rendering decision needs a constructed adapter and so a region or a client, and resolving it in `agents/` would put Bedrock knowledge and a boto3 edge where r5 § 2 R3 forbids them — the ground the owner had just rejected the compiler-supplied carrier on. It also refused `stub:counting`, the only id the deployment admits, which would have taken down both workers and the fault-injection suite. Nothing is lost: AC-0275 refuses such an id at the first role compilation, so boot would only have been earlier. **AC-0276's guard moved from the executor's call site to the model seam**, and the round-2 clause calling a wrapper seam insufficient was inverted and is corrected: the framework resolves agent, capability and per-run settings into one mapping *before* calling the model, so the model seam sees all three routes and the executor's call site sees one. The predicate now binds to **both** provider paths, the adapter building its request at two sites. AC-0275 gained the declared-non-provider carve-out `stub:counting` needs, with an explicit-declaration requirement so an unresolved profile is refused rather than read as a fixture — treating it as one would install a recorded defeat layer as policy — and its probe must run the model's full settings-to-request resolution rather than the renderer alone. The delivery order is stated once: T6 is its own PR and merges before T1's.
- 2026-09-22: round 4. **The observable had no seam that could produce it.** Both criteria decided on the request a model would send, but that rendering is a private method on a provider-specific class and `agents/` may name only `Model` — so as scoped, the only way to satisfy either was to name a provider's internals inside `agents/`, the r5 § 2 R3 coupling this spec had already rejected twice. A provider-agnostic seam owned by `adapters/` now answers the question and lands in T6. **The declared-non-provider carve-out was itself fail-open:** the only thing declaring `stub:counting` was `CED_POOL_ALLOWED_MODEL_IDS`, which every id reaching compilation is in by construction, so the carve-out admitted everything; the declaration is now a pool value of its own, and the residual it leaves — an operator declaring a real provider id non-provider-backed — is stated in the criterion rather than implied. **A fourth defeat route was found:** the framework re-resolves the step's model from a selector or capability and reassigns it per step, so a guard bound to the compiled or wrapped instance misses the one invoked. **Two of my own claims were wrong and are corrected:** the second build site is `count_tokens`, not the streaming path — streaming and non-streaming share one — and the fourth `compile_role` argument was justified by a docstring reservation that is specifically about the event layer's `StepContext`; `compile_role` already resolves the model itself, so the argument is dropped.
- 2026-09-22: round 5. **A fifth defeat route**: a capability wrapping the model request may hand the inner handler a replaced request context, model and settings included, after every earlier hook has run — the framework's own bundled durable-execution capabilities do exactly that. With per-step model substitution already route four, naming a seam has now been wrong twice, so **AC-0276 states its placement as an outcome** — the guard sees the model and settings the invoked model actually receives — and leaves locating one to T7's discovery obligation. **AC-0276 was fail-open on most routes** by inheriting AC-0275's probe, which begins at a synthesized `thinking=False`; it now asks the seam with the settings actually resolved for that call. **Every route is now driven in a refused/admitted pair**, because a refusal-only suite cannot distinguish a guard that observes the route from one that refuses whatever it cannot classify — the same discrimination T6 already required and T7 did not. The seam fails closed on error or an unrecognised answer and carries one calibration check against the request the model itself builds, so routing both criteria through it cannot leave a mis-probe with nothing able to disagree. AC-0275 gained two refusals: an uninterrogable model **class**, and a rendering carrying thinking enabled or adaptive, without which a presence-of-a-key predicate passed the whole suite. The declaration is named `CED_POOL_NON_PROVIDER_MODEL_IDS`, with no default and boot validation, and `AGENTS.md` joins T6's Touches because it documents the worker invocation as taking exactly two pool variables. **A fourth error of mine in the canonical § Assumptions is corrected:** `claude-haiku-5` is not adaptive, so "4.6 and later" was false as a rule — the flag is prefix-set membership the profile module declares, the criteria read the flag, and the enumeration is labelled a measurement of one pin rather than the rule.
- 2026-09-22: round 6, the last. Both reviews judged the contract shippable and found no remaining defeat path in the criteria; what follows is the construction contract and the record. **One required check could not fail:** the carve-out's discrimination test used the deployment's own configuration, where no `model_factory` is wired, so the compile was already admitted by the no-adapter case and removing the declaration left it green — the dead-check shape this repository already registers against `test_label_vocabulary.py`. It now runs against a pool whose factory resolves the id to a model the seam would refuse. **Two enumerations stated as rules were corrected**, the same error this spec has now made five times: the two provider-reaching methods are the Bedrock adapter's on this pin, not the framework's — `Model` also exposes `compact_messages` — so the binding is by property with an unenumerated method failing closed; and the § Follow-ons and register entry both reinstated the version ordering § Assumptions corrects, now stated as adaptive-flag membership. **Route five must be driven from the innermost ordering tier**, since a guard outrun only by an innermost peer passes a route driven by an ordinary capability. **One interception point may not cover both methods** — `count_tokens` runs outside the request-wrapping chain — so the ledger attributes each method to the point that guards it. AC-0275 now states that the declaration is evaluated before the uninterrogable-class refusal, which both fire on a fixture. T7 is classified **DEEP** with the mandatory security review, rather than left to the catch-all.
- 2026-09-22: **recorded conflict, not resolved here.** No documented route fits this edit, and the one taken is the closest available rather than a sanctioned one. `spec-and-plan-contract.md` says that from approval onward a correction takes the controlled-amendment path, not an in-flight edit; `delivery-contract-lifecycle.md` says that transition is unavailable outside `CODE-IMPLEMENTATION`, which a spec with no engine run cannot be in; and the hand reset of `Approved` to `Draft` used here is the rejected-gate recovery, while no gate was rejected. So the lifecycle has no route for widening an approved but unsealed contract, which is exactly the state this spec is in and the state the change was made early to exploit. Per root `AGENTS.md` this is surfaced rather than worked around, and it is now registered as `no-lifecycle-route-for-widening-an-approved-unsealed-contract` on `.claude/skills/new-spec/references/spec-and-plan-contract.md` in `workspace.toml` `[backlog].open`, so it outlives this plan's Changelog. The owner decides whether to accept the reset as the route, and whichever source owns the rule is the one that should gain the missing transition.
- 2026-09-22: revised on the spec-stage security review, before re-approval. A **fifth** defeat layer was found that the first draft missed: the framework ships a thinking capability whose settings mapping is layered between the agent's and the per-run one and defaults to on, so § Assumptions now states the layers as those found rather than as a closed set, and AC-0276 drives three adversarial routes instead of one. AC-0277 was added because `CED_POOL_ALLOWED_MODEL_IDS` is deployment-time and `verify_boot` already validates it, so the operator's mistake can fail at boot instead of per-role at the first claim. AC-0275 now refuses a model id whose adapter cannot be resolved, since `model_factory` is unwired by default and a skip-when-absent guard would be green on every compile that ships. AC-0276 became a refusal rather than an observation and its read is pinned to `ModelRequestParameters.thinking` after `prepare_request`, which strips the key either way. **Delivery was resequenced:** T1 is the repository's first live provider call and T6 now ships in its PR ahead of it, because a current Claude model on Bedrock takes the adaptive branch that emits nothing for `False`, so the first call would otherwise reason at the provider with AC-0223 reading the result back.
- 2026-09-22: spec re-approved by eugenelim, carrying AC-0275 and AC-0276 and the tasks T6 and T7 that own them. The scope decision is the widened one: this spec now owns the reasoning-disable controls `walking-skeleton-role-compilation` could not observe.
- 2026-09-22: plan re-approved by eugenelim. The baseline is not sealed — no work-loop engine run exists for this spec, and `plan-locked` is the code-mode run's to fire when implementation starts.
- 2026-09-24: round 7, the pre-EXECUTE gate of the code-mode engine run. **This is the first review of this contract that ran inside a work-loop engine run** — rounds 1 through 6 were authored before one existed, which is why the baseline could still be revised here rather than through the controlled amendment the entry of 2026-09-22 records as having no route. Ten findings were raised and independently adjudicated; **three were refuted and are recorded because the refutations are load-bearing.** The claim that AC-0275's carve-out clauses contradict each other was wrong — read whole they cover disjoint cases, and the proposed rewrite would have *admitted* the unresolvable-and-wrongly-declared id the criterion names as an accepted residual. The claim that the no-profile check cannot red for its own reason was wrong — `Model.profile` merges `provider.model_profile(...) or {}` and `self.provider` is public, so the condition is observable from the instance without naming internals. The claim that T6's `Done when` must sit in a Testing Strategy group misread a rule that governs criteria, not task fields. **Seven sustained findings were applied.** AC-0263 and AC-0264 were live criteria with **no owning task and no deferral carrier**, which `lint-spec-status.py` would have turned into a HARD violation at the `Shipped` transition however well every task completed; owner decision of 2026-09-24 gave AC-0263 to T2 and AC-0264 to T3 rather than moving either to § Follow-ons. AC-0264's seam was not invented here: `migrations/versions/0003_role_configuration_records.py` states in place that r5 § 4's in-flight immutability "needs enforcement this delta does not build" and names this spec as its owner. T6 gained three required checks — the declared-but-provider-backed refusal, the `verify_boot` malformed-value refusal, and an admitted/refused pair decided against a **real** `BedrockConverseModel` rather than a double, the last because AC-0276's calibration clause sits behind T1 and the first live call would otherwise be gated by a seam nothing had checked against a real model. **Two of this plan's own statements were false and are corrected rather than quietly dropped:** T6's reason for touching `AGENTS.md` predicted a compile refusal from a worker that compiles no role, since `compile_role` has no production caller; and the stub cited `compiler.py:501` for a call that sits at 507, now cited by symbol. The § Assumptions adaptive enumeration was re-measured and had omitted `claude-opus-4-7` and `claude-opus-4-8` — a paragraph that has repeatedly had to correct an enumeration, which is why the criteria read the flag and not the list — and § Follow-ons still led with the version ordering the same sentence refutes. **Re-approval of both gates is owed to eugenelim.**
- 2026-09-24: round 8, the second pre-EXECUTE pass, scoped to round 7's own deltas. **Applying seven findings introduced four new defects and this round found them**, which is the argument for re-reviewing a revision rather than trusting it. **The sharpest was mine.** Round 7 required T6's real-adapter pair to use "ids the spec's § Assumptions measurement names" — but that section names bare family prefixes, and `split_bedrock_model_id` returns no provider for a bare `claude-sonnet-4-5`, so the profile lookup misses and the rendered blob carries no `thinking` key: **byte-identical to what an adaptive model renders.** The pair would have decided its admitted half through the no-profile refusal rather than the rendering it exists to calibrate, and the obvious repair for that red would have deleted the only real-model check standing before T1's first live call. Measured by execution on 2026-09-24, not read: `claude-sonnet-4-5` renders `None`; `anthropic.claude-sonnet-4-5-v1:0` and `us.anthropic.claude-sonnet-4-5-20250929-v1:0` render `{'thinking': {'type': 'disabled'}}`; `us.anthropic.claude-sonnet-5` renders `None`. The bullet now requires provider-prefixed ids and says the bare names are what those ids resolve to. **Round 7 also left § Data & schema saying "No schema change" while T3's pinned Touches named a migration** — reconciled in place, since the pinned fields were right and the working-material section was stale; the section now states that AC-0264's refusal is a migration-borne constraint and that an application-level check would not satisfy it, because a `psql` session bypasses one. T6's `verify_boot` check had no admitted test location and now names `tests/worker/test_pool_configuration.py`, the module that owns the `no_database` fixture making "the refusal precedes the connection" an assertion; the empty-value case resolves there by reference rather than being left open. § Assumptions attributed `bedrock_supports_adaptive_thinking` to the profile module, which never sets it — the provider module derives it from the profile module's `anthropic_supports_adaptive_thinking`, and both are now named. **Two findings were refuted**: the empty-value case was already settled by the incorporation-by-reference the plan uses, and "exactly the families" is scoped by the noun it governs rather than claiming to be a complete account of AC-0275's refusals. **A tally I wrote was removed from both files** — "the sixth enumeration error" was not reconstructable from the record, which is the defect it was describing. **Re-approval of both gates is owed to eugenelim.**
- 2026-09-24: round 9, the third pre-EXECUTE pass. **Both blockers were in the two criteria round 7 had just given owning tasks, and that is the point of having given them one.** AC-0263 and AC-0264 had been live and unowned since this spec was cut; binding them to T2 and T3 forced their mechanisms to be checked for the first time, and neither survived. **AC-0263 named an observable that does not exist on the pin.** It decided the question on "a stub model that records the limits it was invoked under", and `UsageLimits` reaches no model-side seam on 2.45.0 — measured, not read: `Model.request` and `Model.count_tokens` take only `(messages, model_settings, model_request_parameters)`, and neither `ModelRequestParameters` nor `ModelRequestContext` carries a limits field. The only writable test would have handed the stub its own limits, which is the fail-open the criterion's own second sentence forbids. That is the fourth time in this spec's history that a criterion has named an observable with no seam behind it, after AC-0204, AC-0275 and AC-0276. **Owner decision of 2026-09-24 restated it as two halves that do not cover each other** — identity, a tool reading `RunContext.usage_limits` mid-run against what `compile_role` resolved, and enforcement, a run driven past a resolved threshold and refused — rather than either alone, because identity without enforcement certifies a value nothing applies and enforcement without identity passes on a caller's bound. **AC-0264's check would have passed for the wrong reason.** `0001_base_schema.py` grants `app_api` and `app_worker` only `SELECT` on `integration_registry` and `app_policy` nothing, so three of the four connection fixtures cannot perform the attacking write at all: the test would have caught permission-denied, asserted a refusal, and gone green while the enforcement migration 0003 handed this spec was never built — the dead-check shape this plan already registers against `test_label_vocabulary.py`. T3 now carries a non-vacuity obligation and a ledger entry for it. **The adjudicator narrowed the proposed fix and was right to:** requiring a specific database role would have presumed the seam AC-0264 deliberately leaves free, so what is required is that the check red when the enforcement is absent, with the attacking identity following from the seam chosen. **Two of round 8's own edits were corrected:** § Data and schema had narrowed that seam against both the spec and T3's pinned `Tests`, and had pointed at a `CHECK` constraint, the one database mechanism that cannot express a predicate over `agent_role.ceiling`. A surviving "all three clauses cleared" precondition was also false — r5's STATUS header now names one unbuilt clause, the provider call, the agent layer and the authorization boundary having moved to built. **Re-approval of both gates is owed to eugenelim.**
- 2026-09-24: round 10, the fourth pre-EXECUTE pass — and the round that **refuted a finding against this plan's own previous round**, which is worth recording because the refutation was the useful part. Round 9's AC-0263 restatement was reported as a tautology on the ground that `RunContext.usage_limits` is the identical object the caller passes to `agent.run` — measured and true. The criterion survives it: its forbidden caller is the **test**, not the executor, and T2's pinned `Tests` already requires the run be driven through the production step path with the test only observing. Driven that way the read discriminates, failing an executor that threads a default, `None`, or a pool value instead of `compile_role`'s resolved limits. The proposed repair was worse than the defect: dropping "not values the caller supplied" would have deleted the only contract-side prohibition on the fail-open the criterion exists to refuse. **One sustained finding was my false claim to the owner.** Round 9 justified taking both AC-0263 halves on the ground that neither covers the other; on this pin the framework enforces against the same object it exposes, so identity implies enforcement and only the converse holds. The owner's decision rested on that false premise and was re-put; the ruling of 2026-09-24 keeps both halves with the true reason recorded — enforcement is a **framework-regression guard** against a later pin that accepts a limits object and stops applying it — and both files now say so. **Round 7's blocker was not as closed as this plan claimed.** It was reported closed once AC-0263 and AC-0264 had owning tasks; an exhaustive extraction this round found **AC-0254** live, present in T1's `Tests` and in no task's `Done when` at all — the only one of the spec's twenty-four live criteria in that state, and the criterion AC-0223's live-versus-replay oracle depends on, since it is what requires `model_adapter` in the producer tuple. It is now bound to T1's gate. **Round 9's de-narrowing of AC-0264's seam had not reached two pinned statements**: T3's `Tests` header still opened "the seam is a migration" and both files justified the `substrate` marker on a database-owned refusal. `spec.md` AC-0264 is now the canonical statement of the seam's freedom and the marker rests on the check needing a live Postgres to attempt the write, whichever seam refuses it. A `Touches` path naming `policy_decision.py`, a module that has never existed, is corrected to `policy.py`. **Re-approval of both gates is owed to eugenelim.**
- 2026-09-24: round 11, the confirming pre-EXECUTE pass. It **verified by its own extraction** the four properties the previous rounds were supposed to have established — that all twenty-four live criteria are named in both a task's `Tests` and a task's `Done when`, that AC-0263's corrected premise holds on the pin, that `spec.md` AC-0264 is the single canonical statement of its seam's freedom, and that every pinned `Touches` path across all seven tasks resolves — rather than reading the Changelog's claims about them, which is the right way round given that round 10 had to reopen a closure round 7 recorded. **One concern survived.** `lint-contract-item-alignment.py` rule 5 builds its owner map from pinned `Tests:` and `Done when:` blocks and tests satisfaction rather than exclusivity, so a criterion named by a task that does not own it stays green after its real owner drops it — the rule this plan already states about itself in two places. **The instances introduced by these rounds are fixed; those that predate them are deliberately left.** The adjudicated fix was narrowed to exactly that split, on `AGENTS.md` § Development workflow keeping unrelated discoveries out of the current change: T6's two mentions of T7's criterion and T3's mentions of T2's criterion and of a neighbouring spec's now name the owning task or spec by description instead. Those remaining — T1's `Done when` naming a T3 criterion, T2's `Tests` naming two, T5's `Tests` naming one — are recorded here and in the pull request rather than silently swept, and no backlog entry is created for them, since the accepted intent does not require them. **One cited instance was refuted:** a cross-spec identifier masks nothing, because rule 5 iterates only the local `spec.md`'s criteria and each directory is checked alone; it was removed anyway as a new unresolved rule-4 line that this plan's base revision did not carry. **Re-approval of both gates is owed to eugenelim.**
- 2026-09-24: spec re-approved by eugenelim at the code-mode run's `SPEC-HUMAN-GATE`, carrying the six pre-EXECUTE review rounds of this date. The scope decision is the corrected one: AC-0263 and AC-0264 are delivered by T2 and T3 rather than deferred, AC-0263's observable is the identity-plus-enforcement pair rather than a stub model no seam on the pin can supply, AC-0264's refusal is contract while its enforcement seam stays the implementation's choice, and AC-0254 is bound to T1's gate. Twenty findings were raised across those rounds and nine were refuted; the refutations are recorded in the entries above because two of them would have weakened the contract if applied.
- 2026-09-24: plan re-approved by eugenelim at the code-mode run's `PLAN-HUMAN-GATE`. The build-strategy decision is the seven-task graph in the order T6, T1, T2, T3, then T5 and T7, then T4, delivered as a stack of pull requests with **T6 merged before T1's PR opens** — the constraint that stops the repository's first live provider call reasoning at the wire. T7 stays classified DEEP with its mandatory security review and per-route mutation proof. **This approval seals the baseline**: from here a correction takes the controlled amendment path, which is the route the entry of 2026-09-22 recorded as unavailable to a spec with no engine run and which now exists, this run being `mode: code`.
- 2026-09-24: **controlled amendment during T6's implementation**, on the mandatory security review of the diff. Authority: owner decision of 2026-09-24 at the review gate. AC-0275's admission clause said a declared id wired to *a class the seam cannot interrogate* is admitted, with the declaration evaluated first and winning. Built exactly that way, the guard classified by identity with one adapter class — so a `WrapperModel` around a live Bedrock adapter, the shape instrumentation ships and on a deployment whose compose file already declares the stub id, read as a fixture and compiled green while the model would reason at the provider. Reproduced through the public seam before any repair: the wrapped model answered the admitting value while the model inside it rendered no disable. A second reviewer independently found the same hole via another provider's adapter, which is what showed the defect was the class-level predicate and not the wrapper case. **The criterion now states a positive rule** — admit only what the seam can name as an in-process double, descend wrapper chains first, refuse anything it can neither render nor prove local — and **carries three residuals instead of one**: the pre-existing resolves-to-nothing case, a delegating subclass of a double inheriting the admit, and a fallback chain being refused because it is not a wrapper chain on the pin. T6's `Touches` gains `tests/compiler/role_records.py`, which the task changes and the pinned field did not cover. **The old wording is quoted in the criterion rather than deleted**, because it described a fail-open and the next reader needs to know why the rule is positive. Both files were sealed at `plan-locked`; this is the controlled-amendment path and not an in-flight edit.
