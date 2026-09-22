# Spec: Walking skeleton — the step lifecycle

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

What happens to a leased step from the moment it calls a model to the moment a
different process picks it up again. It builds the model seam that reaches a
real provider under a scoped assumed role, the deadline that bounds a step whose
call never returns, the contentless tool that suspends a step for approval, and
the persistence path that lets a step's conversation survive being serialised
and resumed somewhere else.

Inspectability is the architecture's first-ranked quality attribute, and this is
where a run's producer tuple and a step's recorded outcome become readable from
the log rather than from test setup.

Success is that a step completes a real Bedrock call under a scoped role with no
long-lived credential anywhere in the running container; that a step whose model
call hangs is failed and its lease released within `step_deadline`; and that a
message history carrying a pending approval round-trips byte-identically and
resumes in a fresh process that shares nothing with the original but those
bytes. Each of those is currently a design claim with no executable evidence.

**Its siblings.** [`walking-skeleton-foundation`](../walking-skeleton-foundation/spec.md)
owns the schema, both append paths, the privilege split and the pool this runs
inside. [`walking-skeleton-role-compilation`](../walking-skeleton-role-compilation/spec.md)
is a hard dependency: it ships the compiler whose output this executes.
[`walking-skeleton-authority-containment`](../walking-skeleton-authority-containment/spec.md)
is a hard dependency too: AC-0227 requires a resumed step to apply an approval
decision, which means the previously gated tool body runs, and nothing can admit
a call until that spec's containment predicate exists.
[`walking-skeleton-evidence`](../walking-skeleton-evidence/spec.md) consumes all
three to produce the Phase 1 measurements and the browser stream.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Current architecture | Applicable — `docs/architecture/README.md` § What is built is the current map and this spec changes it | `docs/architecture/README.md` § What is built | work-loop | The model seam, the approval gate and persistence moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Current architecture — the `worker-runtime.md` marker | Applicable — r5's STATUS header names the provider call as unbuilt, and this spec builds it | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` header | work-loop | The provider call moved from unbuilt to built; with all three clauses cleared, whether `STATUS: PLANNED` itself still holds is decided in the same edit | The header's built and unbuilt lists match the repository |
| Reusable learning | Applicable — this spec produces the provider and persistence evidence Phase 2 plans against | `spikes/README.md` | work-loop | A section stating what was established **and what was not**, including what the local credential scan does not demonstrate about a deployed fleet | Hypothesis checks reported separately from setup |
| Decision rationale | Not applicable — no ratified decision changes here; the r5 unsafe-prefix table amendment belongs to `walking-skeleton-authority-containment` | — | — | — | — |
| Interface compatibility | Not applicable — no interface surface; the API belongs to the foundation spec | — | — | — | — |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Boundaries

### Always do

- Treat r8 and r5 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Honour `worker-runtime.md` § 3 Runtime Model, the approval gate's step 2 as binding: the content-addressed payload object is written before the fenced append that carries its hash, on every persist path.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision. The plan gives every DR decision this spec constructs a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Any spend above the Phase 0 order of magnitude. Phase 0 cost about $0.05 in total; a task that would cost more than $5 stops and asks.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No typed output standing in for the deterministic parser.** Structured output is a layer; the boundary is the parser, because a control must not rest on the model's cooperation or the framework's serializer. Carried from `walking-skeleton-role-compilation` § Boundaries with the four criteria it governs.
- **No free text crossing from a quarantined role to a planning role**, including indirectly through stored state or a resolved value. Carried with the same four.

- **No static or long-lived model-provider credential anywhere** — no `AKIA`-prefixed key, no credentials file baked into an image, no inline secret.
- **No history processor standing in for the executor's reasoning strip.** A processor changes what is *sent to the model* and leaves the reasoning part in exactly the artifact that must not hold it, which is the mistake AC-0228 is written to catch rather than restate.
- **No `pydantic_ai` import outside `agents/` and `adapters/`.**
- **No live SEC fetch on a run's request path.** The recorded fixture is the corpus.

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0226, AC-0227, AC-0228, AC-0229, AC-0230, AC-0231, AC-0232, AC-0237, AC-0241, AC-0245, AC-0248, AC-0253, AC-0254, AC-0222, AC-0242, AC-0255, AC-0256, AC-0263, AC-0264)** — the persistence and deadline criteria, plus the four quarantine criteria received from `walking-skeleton-role-compilation`. **AC-0222 and AC-0242 carry the `substrate` marker** — the first needs the database round trip that is its whole point, the second searches the run's events and the payload objects they reference — while AC-0255, AC-0256 and AC-0263 run offline and AC-0264 carries the marker, since it is a write the database refuses.

**Stub coverage:** AC-0255 carries a validated red stub against the parser seam; AC-0222, AC-0242 and AC-0256 carry `no stub (implementation-discovered)` with T5's discovery predicate. Each is a compressible invariant with a cheap oracle and no provider in the loop. AC-0232 uses a `Model` stub that hangs, so the deadline path is exercised with no spend. AC-0227 is exercised across a **process boundary**, because same-process reuse would pass on in-memory state the design forbids relying on.
- **Goal-based check (AC-0224, AC-0225)** — a scan of the running container for a long-lived credential, and the producer tuple read back off the run header. A one-liner is the verdict.
- **End-to-end (AC-0223)** — the one criterion that calls a real provider, and the only reason the Phase 1 runtime needs a cloud credential at all.

Every criterion touching the provider runs under a scoped assumed role, never
under an administrator profile: an administrator can invoke any model, so a
green result would say nothing about a scoped workload. This is the
construction spikes 1 and 7 used and it carries forward unchanged.

**A note on what the credential scan cannot see.** AC-0224 asserts the absence
of a static key in a locally running container. On a deployed fleet the task
role supplies credentials with no session key in the process environment at all,
and that stronger property is not what this criterion demonstrates.

## Acceptance Criteria

Obligations come from `runtime-architecture.md` § 10 Rollout, Phase 1 criterion 2 —
"execute one step against a real provider via workload identity" — and from
`worker-runtime.md` § 10 Rollout criterion 6, the byte-identical round trip over a
realistic history. Those two sources cover AC-0223, AC-0224 and AC-0226.
Obligations **beyond** them are tabled below, and the approval gate rules on
each rather than inheriting it.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Hold the quarantine boundary where a step can run | AC-0222, AC-0242, AC-0255, AC-0256 | Subject owner is `walking-skeleton-role-compilation`, which builds the quarantined role and the parser; each is decided against a running step and the context assembler this spec builds. [`../README.md`](../README.md) § Cutting one outcome into several specs sends a criterion whose observation needs a later spec's component to the spec that can execute it, and requires the row to cite the subject owner | The boundary r8 ranks second of four is asserted in a spec that cannot run it, and passes vacuously |
| Name the members that carry the tuple's integrity | AC-0254 | r8 § 5 enumerates fourteen producer fields; AC-0225 names two illustrative ones. Three are security-bearing and neither criterion required them: `model_adapter` and `fetch_adapter`, which r8 says exist "so a fixture run can never be mistaken for a live one", and `tool_manifest_hash`. AC-0223's oracle reads the log for a `step.completed` whose producer tuple names the live adapter — the one check distinguishing a real provider call from a replay — so it rests on a field no criterion required | The Phase 1 evidence base cannot tell a fixture run from a live one, and AC-0223 proves nothing it claims |
| Record the producer tuple | AC-0225 | Inspectability is r8's first-ranked quality attribute, and a recorded run whose producer is unknown cannot be re-derived or compared across a version bump. No § Rollout criterion asks for it | Phase 1's measurements cannot be attributed to the stack that produced them |
| Release the lease on suspension | AC-0237 | r5 § 3 Runtime Model, the approval gate step 3 makes lease release how a *different* worker resumes, which is exactly what AC-0227 then relies on. No § Rollout criterion asks for it, and AC-0232 covers only a hung step's release under `step_deadline` — a different path with a different trigger | A suspended step holds its lease until expiry, AC-0227's separate-process resume passes only because the test arranges it, and the approval gate stalls a worker for the whole TTL |
| Pin the registry version a resume compiles against | AC-0248 | Source-derived from r5 § 4's pinned-binding paragraph — bindings name `(integration_id, integration_version)`, a version in use is immutable, and R5 re-verifies the ceiling predicates against that pinned schema — and tabled here only because no § 10 Rollout criterion asks for it on the *resume* path. A ceiling authored against `arg_schema` at one version and evaluated against the next can change meaning in the unsound direction — an argument reclassified from `url` to `opaque-string` makes prefix expressible again, which is the constructor `walking-skeleton-authority-containment`'s AC-0217 exists to remove | Version provenance is contract on two axes and silent on the third, and a registry edit reopens a closed constructor on a step already in flight |
| Authorize a resumed step against a named role version | AC-0241 | AC-0229 covers the instruction text a resumed step is prompted with and says nothing about the ceiling, which its own rationale calls the load-bearing part — the role compilation is where the ceiling's sibling text lives. A resumed step whose ceiling comes from the bytes is authorized by whatever the suspended history carried | The ceiling travels in attacker-adjacent persisted state and a resumed step is authorized by whatever the bytes carried |
| Keep revocation effective across a suspension | AC-0245, AC-0253 | `may_act` is a conjunction, and pinning the ceiling to the suspended role version (AC-0241) means the ceiling half cannot carry revocation. `approval_timeout` defaults to none, so a step can wait indefinitely. The entitlements conjunct is the only term that can still bite, and freshness is undone if the principal it is looked up for comes from the bytes: AC-0229 and AC-0241 deliberately route the other two authority inputs through the suspended version, which makes the persisted artifact the natural place an implementer reaches for the third | An entitlement revoked while a step waits is honoured nowhere, and an indefinitely suspended step keeps authority its principal no longer has |
| Resume across a process boundary | AC-0227 | r5 criterion 6 asks only that the bytes round-trip. Bytes that round-trip and cannot be resumed satisfy it while the approval gate stays unusable | The persistence format is proved correct and never proved sufficient |
| Keep reasoning out of storage | AC-0228 | DR8's primary control is the compile-time thinking refusal, `walking-skeleton-role-compilation`'s AC-0204. This is the backstop that does not depend on that setting staying put | One settings regression silently puts reasoning traces in the durable record |
| Prompt from a fresh compilation | AC-0229 | A resumed history carries the instruction text it was suspended with. The role compilation is where the ceiling's sibling text lives, so this is a security property rather than an ergonomic one. "Fresh compilation of the suspended version" rather than "current version": r5 § 3 has the resuming worker construct from the same role version and § 5's durability table records strict immutability in flight, and AC-0241 pins the ceiling the same way, so instructions and ceiling come from one object | Instruction text travels in attacker-adjacent persisted state, or the two halves of a role version are taken from different versions |
| Survive a crash between the two writes | AC-0230 | r5 § 3 Runtime Model, the approval gate step 2 fixes the write order; nothing asserts what a crash in the gap leaves behind | The ordering ships as prose and the failure it prevents is never observed |
| Scope-qualify every payload key | AC-0231 | the scope-qualified object keys amendment, a one-way door taken before the corpus exists | A bare content hash becomes the key and the door closes the wrong way |
| Bound a hung step behaviourally | AC-0232 | r5 § 1 Scope and Context, Goals: "no step is *reported* running past `step_deadline`" | The delivery measures how bad a hung step is without ever bounding one |

**Calling a real provider**

- [ ] **AC-0223.** A step completes a Bedrock call under a scoped assumed role and reaches `step.completed`, evidenced from the run's event log rather than from test setup.
- [ ] **AC-0224.** The running worker container holds no long-lived provider credential: no `AKIA`-prefixed access key, no credentials file baked into the image, and no credential that outlives the assumed-role session. Short-lived session credentials delivered to the process are what ambient workload identity yields and are in scope; what this criterion forbids is a static one.
- [ ] **AC-0225.** The run header records the producer tuple, including the resolved inference profile and the exact `pydantic-ai` version.
- [ ] **AC-0254.** That producer tuple names `model_adapter` and `fetch_adapter`, so a fixture run cannot be read as a live one, and `tool_manifest_hash`, so what a step was exposed to is recoverable.

**Persisting and resuming a step**

- [ ] **AC-0226.** A message history containing a tool call, a tool return, a retry part, and a pending approval serialises, deserialises, and re-serialises to identical bytes.
- [ ] **AC-0237.** A step suspended on `request_approval()` releases its lease **after** the payload write and the fenced append that references it, so the row is claimable by another worker without waiting for the lease to expire and without the release making that append unfenced.
- [ ] **AC-0248.** A resumed step's fresh compilation resolves the integration registry at the versions the suspended role version resolved, so the `arg_schema` a ceiling was authored against is the one it is evaluated against.
- [ ] **AC-0241.** A resumed step's tool calls are authorized against the ceiling of the role version the step was suspended under, not against any ceiling carried in the persisted bytes.
- [ ] **AC-0245.** A resumed step's entitlements conjunct is looked up for the principal named in the run record, demonstrated against a history whose recorded principal differs from the run's.
- [ ] **AC-0253.** A resumed step's entitlements lookup reads that principal's entitlements as they stand at resume, demonstrated by revoking an entitlement while the step waits and observing the resumed call refused.
- [ ] **AC-0227.** A fresh agent in a separate process, sharing nothing with the original run but those bytes, resumes the suspended step and applies the approval decision.
- [ ] **AC-0228.** No persisted message history contains a reasoning part, demonstrated against a history that carried one before persisting.
- [ ] **AC-0229.** A step resumed from a history that carries stale instruction text is prompted by a fresh compilation of the role version it was suspended under, and the stale text does not reach the model.
- [ ] **AC-0230.** With a crash injected between the payload write and the fenced append, an unreferenced payload object remains and no event carries a payload reference that does not resolve.
- [ ] **AC-0231.** Every payload object key is scope-qualified as `<owner_scope>/<content_hash>`, so a bare content hash is never the key.

**Holding the quarantine boundary through a running step**

These four are `walking-skeleton-role-compilation`'s by subject — it builds the
quarantined role, the parser and the compiled stack — and sit here because none
can be observed without a running step and the context assembler this spec
builds. Placement per [`../README.md`](../README.md) § Cutting one outcome into
several specs; owner decision of 2026-09-20 after a design pass found no task in
that spec could host the module they fail through.

- [ ] **AC-0222.** The planning step succeeds with the quarantined step's admitted references and typed scalars present in its context package, and none of the fixture's distinctive free text appears there — including after a round trip through the database. Both halves are asserted: the absence alone is satisfied by an assembler that passes nothing through, which is a severed channel rather than a held boundary. *Subject owner: `walking-skeleton-role-compilation`.*
- [ ] **AC-0242.** A refused integration result records its rejection without the rejected text reaching the event log or any payload object an event of that run references. *Subject owner: `walking-skeleton-role-compilation`.*
- [ ] **AC-0255.** Every field of a quarantined agent's own output — labels, typed scalars and references alike — is admitted by the runtime's deterministic parser outside the agent. An agent declared with the permissive `free-form` output contract — which the framework's schema accepts unparsed — still fails the step, which is what shows the parser and not the serializer is the admitting component. This spec adds `free-form` as the output set's third member and the compiler guard that keeps a quarantined role from declaring it, since it is the spec that needs one. *Subject owner: `walking-skeleton-role-compilation`.*
- [ ] **AC-0256.** A planning role's context package containing anything outside r5 § 4's admitted types — references, closed-vocabulary labels and typed scalars — fails the step in the runtime's context assembler, observed by the agent constructor never being reached. It holds whatever produced the content, across every assembly path this delivery builds. *Subject owner: `walking-skeleton-role-compilation`.*

- [ ] **AC-0264.** A rewrite of an `integration_registry` row at a version a role's `ceiling` pins is refused. r5 § 4 states that a version in use is immutable, and the widened key alone does not enforce it: an in-place edit of a pinned row's `arg_schema` reclassifies an argument under a step already in flight, reopening the prefix constructor `walking-skeleton-authority-containment`'s AC-0217 exists to remove, with AC-0248 green throughout. The enforcement seam is the implementation's choice; the refusal is not.
- [ ] **AC-0263.** The usage limits in force at the model call are the compiled role's resolved values, observed on a stub model that records the limits it was invoked under — not values the caller supplied. A test that passes its own limits goes green while production bounds nothing.

**Bounding a hung step**

- [ ] **AC-0232.** A step whose model call hangs is failed and its lease released within `step_deadline`, whether or not the underlying provider call terminated.

## Follow-ons

**The two r5 suspensions this spec owns the return conditions for.** Each is a
follow-on with a register entry rather than an acceptance criterion, because
neither can be green while its deviation stands and an unchecked criterion is a
HARD violation at a `Shipped` transition. [ADR-0006](../../adr/0006-four-r5-deviations-for-phase-1.md)
§ Confirmation was amended on 2026-09-21 to admit this carrier; each becomes a
criterion in this spec when its deviation lifts. **AC-0271 and AC-0272 were
allocated to these two on 2026-09-21 and withdrawn the same day; neither
identifier is reallocated.** D1's *deployment* half is a separate obligation
already discharged as `walking-skeleton-role-compilation`'s AC-0270.

- eugenelim, register entry on `docs/adr/0006-four-r5-deviations-for-phase-1.md`: **ADR-0006 D1's return condition.** When the Bedrock IAM shape for `bedrock:CountTokens` against a geo-prefixed model id is re-derived and `count_tokens_before_request` can be enabled in production, this spec gains a criterion that a per-request token bound refuses a request under production wiring — a step whose counted input exceeds `per_request_input_tokens_limit` raises before the provider request is issued. Until then D1 stands and `request_limit` is the acting bound.
- eugenelim, register entry on `docs/adr/0006-four-r5-deviations-for-phase-1.md`: **ADR-0006 D2's return condition.** When the object-store write path exists, so a hash can be written as well as read, this spec gains a criterion that an instruction hash resolves from the event log alone — the text a step was prompted with is recoverable by following a content-addressed reference the event carries, without joining mutable state. Until then `agent_role.instructions` holds text inline.


- eugenelim: this spec § Acceptance Criteria — **AC-0222 is universally quantified and proven on one path.** One quarantined step, one planning step, one fixture. The Testing Strategy caveats adaptive adversaries but not path coverage, so a reader takes a single-path result as universal. Recorded here with the criterion; `walking-skeleton-role-compilation` is its subject owner.

- eugenelim: [`walking-skeleton-evidence`](../walking-skeleton-evidence/spec.md) § Follow-ons — **no criterion records who approved a publication.** That spec owns the transition and holds the finding; it is named here because this spec's approval gate is where the unattributed decision is taken.

- eugenelim: `walking-skeleton-evidence/spec.md` § Acceptance Criteria — **the DR5 reject-and-resume cycle cap has no acceptance criterion anywhere.** r5 § 3 Runtime Model is explicit that rejection resuming the conversation **is not** the forbidden negotiation pattern, because the model cannot publish at all and can only ask again. The three-cycle cap exists so the loop is bounded; r5 records the number as arbitrary and asks Phase 1 to replace it with an observed one. `walking-skeleton-evidence` owns the reject-and-resume transition the cap counts. Its plan dispositions DR5 to its own T1 as "lands, unmeasured", so what is missing is the criterion that observes the cap, not the cap itself, and adding one is an amendment to an Approved spec and out of this change's scope. The criterion that replaces it must also require the cap's configuration to carry a **finite default**, so it asserts a cap exists rather than that a config value is read. **AC-0244 is retired unused** — it was drafted here and moved before approval; the identifier is not reallocated.

Every item below is a criterion-wording defect a spec-stage shaping or security
review found in text this spec carries unchanged from the deleted
`walking-skeleton-agent-runtime`. They were left unreworded by owner decision of
2026-09-20, so the carry-across stays auditable against the parent; each needs an
amendment rather than an in-place correction.

- eugenelim: this spec § Acceptance Criteria — **AC-0224's third clause is not decidable by its named observation.** "No credential that outlives the assumed-role session" is temporal and a one-moment container scan cannot falsify it; "no credentials file baked into the image" cannot be decided by scanning the running filesystem, because a secret added in one layer and removed in a later one is still recoverable. That half is scanner-owned and no image or secret scanner is wired in this repository.
- eugenelim: this spec § Acceptance Criteria — **AC-0223 has no oracle distinguishing a scoped role from an administrator.** A run under an over-broad role is byte-identical in the event log. Spike 7 H1 already observed the negative, so the fix is one extra call: a model id outside the role's policy denied under the same credentials.
- eugenelim: this spec § Acceptance Criteria — **AC-0232 states a bound with no reference point.** "Within `step_deadline`" does not say whether the interval runs from lease acquisition, step start or the model call, and the three give different verdicts on the same run.

- eugenelim: `worker-runtime.md` r5 § 9 Risks — the credential broker, commissioned by DR12, which is where the per-integration credential scopes r5 § 10 folds into r8 are carried. r5 § 9 Risks holds its brief and § 11 Open Questions restates it as open; both are design sections, not a work register, and no Phase 1 spec claims the design. r5 itself never writes the `DR12` label; the § Decisions required that assigned it is gone.

## Assumptions

- Technical: `pydantic-ai` is pinned to 2.45.0 rather than ADR-0001 D5's 2.44.0 (source: user decision 2026-09-18). The framework-seam probe that established this is recorded once, in `walking-skeleton-role-compilation/plan.md` § Grounding probe; this spec cites it there rather than repeating it.
- Technical: a deferred-approval history round-trips byte-identically and a fresh agent resumes from the bytes alone, established offline before this spec was written. AC-0226's residual risk is therefore the *combination* of a realistic shape with a pending approval, not the mechanism (source: `plan.md` § Approval probe).
- Technical: `walking-skeleton-role-compilation` ships the compiler whose output this spec executes, and pins the framework including the `[bedrock]` extra. This spec adds no framework dependency (source: `walking-skeleton-role-compilation/plan.md` § Dependencies & integration).
- Process: ADR-0006 D1's and D2's return conditions were added on 2026-09-21, first as acceptance criteria AC-0271 and AC-0272 and then, the same day, as owned follow-ons with register entries. The first shape was wrong and the reason is worth keeping: a criterion that cannot be green while its deviation stands is an unchecked `- [ ]` line, and `lint-spec-status.py` makes every one of those a HARD violation at a `Shipped` transition with no deferral exemption, so the spec could not ship without either failing the gate or checking a box for something known false. ADR-0006 § Confirmation was amended to admit the follow-on carrier `spec-and-plan-contract.md` already prescribes. **Neither withdrawn identifier is reallocated.** The alternative considered and rejected was exempting return-condition criteria in the lint, which would have weakened a gate for every spec in the repository to fit two lines in this one (source: owner decision 2026-09-21, on adjudicated adversarial and quality-engineer findings).
- Process: AC-0229 is the one criterion carried into *this spec* whose wording changed. The parent said a resumed step is prompted by "the current role compilation", which reads as the latest version and contradicts `worker-runtime.md` r5 § 3 — the resuming worker constructs from the same role version — and therefore contradicted AC-0241, which pins the ceiling that way. The criterion now says a fresh compilation of the suspended version, which keeps its original security property, that instruction text must not come from the persisted bytes, and resolves the split (source: owner ruling 2026-09-20 after an adversarial spec review).
- Technical: `walking-skeleton-authority-containment` ships the containment predicate, and without it the decision point admits no call. AC-0227 needs an approved tool body to run, so that spec is a hard dependency rather than a peer (source: `walking-skeleton-role-compilation/spec.md` AC-0233; adversarial spec review, 2026-09-20).
- Technical: the foundation spec ships the schema, both append paths, the privilege split and the pool. This spec adds no column; it writes the Phase 1 runtime's first payload object, which is why object keys become scope-qualified here (source: `walking-skeleton-foundation/plan.md` § Data & schema).
- Technical: the IAM shape established by spike 1 admits the call — inference-profile ARN pinned to the calling region, foundation-model ARN region-wildcarded, no requested-region condition — and both plausible tightenings deny it outright (source: `spikes/README.md` § Spike 1).
- Process: this spec is one of three cut from `walking-skeleton-agent-runtime`, whose directory was deleted on 2026-09-20. AC-0223 through AC-0228 and AC-0230 through AC-0232 carry across with their wording unchanged; AC-0229 is the single exception, reworded as the entry above records (source: user decision 2026-09-20).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Product: the skeleton carries one analysis step over the recorded fixture rather than a live corpus — the thinnest construction that exercises every criterion (source: assumption stated 2026-09-18, to be confirmed at the approval gate).
- Governance: r8 and r5 are ratified as of 2026-09-18, r8 with its five accepted limits in § 9 open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
