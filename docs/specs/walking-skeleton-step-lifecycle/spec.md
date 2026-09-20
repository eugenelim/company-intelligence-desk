# Spec: Walking skeleton — the step lifecycle

- **Status:** Draft <!-- Draft | Approved | Implementing | Shipped | Archived -->
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
| Current architecture — the `worker-runtime.md` marker | Not applicable — that header states the condition for its own move, and `walking-skeleton-evidence` is the spec that clears it | — | — | — | — |
| Reusable learning | Applicable — this spec produces the provider and persistence evidence Phase 2 plans against | `spikes/README.md` | work-loop | A section stating what was established **and what was not**, including what the local credential scan does not demonstrate about a deployed fleet | Hypothesis checks reported separately from setup |
| Decision rationale | Not applicable — no ratified decision changes here; the r4 unsafe-prefix table amendment belongs to `walking-skeleton-authority-containment` | — | — | — | — |
| Interface compatibility | Not applicable — no interface surface; the API belongs to the foundation spec | — | — | — | — |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Boundaries

### Always do

- Treat r7 and r4 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Honour `worker-runtime.md` § The approval gate step 2 as binding: the content-addressed payload object is written before the fenced append that carries its hash, on every persist path.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision. The plan gives every DR decision and every change asked of r7 that this spec constructs a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Any spend above the Phase 0 order of magnitude. Phase 0 cost about $0.05 in total; a task that would cost more than $5 stops and asks.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No static or long-lived model-provider credential anywhere** — no `AKIA`-prefixed key, no credentials file baked into an image, no inline secret.
- **No history processor standing in for the executor's reasoning strip.** A processor changes what is *sent to the model* and leaves the reasoning part in exactly the artifact that must not hold it, which is the mistake AC-0228 is written to catch rather than restate.
- **No `pydantic_ai` import outside `agents/` and `adapters/`.**
- **No live SEC fetch on a run's request path.** The recorded fixture is the corpus.

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0226, AC-0227, AC-0228, AC-0229, AC-0230, AC-0231, AC-0232, AC-0237)** — the persistence and deadline criteria, because each is a compressible invariant with a cheap oracle and no provider in the loop. AC-0232 uses a `Model` stub that hangs, so the deadline path is exercised with no spend. AC-0227 is exercised across a **process boundary**, because same-process reuse would pass on in-memory state the design forbids relying on.
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

Obligations come from `runtime-architecture.md` § Rollout Phase 1 criterion 2 —
"execute one step against a real provider via workload identity" — and from
`worker-runtime.md` § Rollout criterion 6, the byte-identical round trip over a
realistic history. Those two sources cover AC-0223, AC-0224 and AC-0226.
Obligations **beyond** them are tabled below, and the approval gate rules on
each rather than inheriting it.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Record the producer tuple | AC-0225 | Inspectability is r7's first-ranked quality attribute, and a recorded run whose producer is unknown cannot be re-derived or compared across a version bump. No § Rollout criterion asks for it | Phase 1's measurements cannot be attributed to the stack that produced them |
| Release the lease on suspension | AC-0237 | r4 § The approval gate step 3 makes lease release how a *different* worker resumes, which is exactly what AC-0227 then relies on. No § Rollout criterion asks for it, and AC-0232 covers only a hung step's release under `step_deadline` — a different path with a different trigger | A suspended step holds its lease until expiry, AC-0227's separate-process resume passes only because the test arranges it, and the approval gate stalls a worker for the whole TTL |
| Resume across a process boundary | AC-0227 | r4 criterion 6 asks only that the bytes round-trip. Bytes that round-trip and cannot be resumed satisfy it while the approval gate stays unusable | The persistence format is proved correct and never proved sufficient |
| Keep reasoning out of storage | AC-0228 | DR8's primary control is the compile-time thinking refusal, `walking-skeleton-role-compilation`'s AC-0204. This is the backstop that does not depend on that setting staying put | One settings regression silently puts reasoning traces in the durable record |
| Prompt from the current compilation | AC-0229 | A resumed history carries the instruction text it was suspended with. The role compilation is where the ceiling's sibling text lives, so this is a security property rather than an ergonomic one | A resumed step is prompted by a role version that is no longer the authority |
| Survive a crash between the two writes | AC-0230 | r4 § The approval gate step 2 fixes the write order; nothing asserts what a crash in the gap leaves behind | The ordering ships as prose and the failure it prevents is never observed |
| Scope-qualify every payload key | AC-0231 | r7 change 5, a one-way door taken before the corpus exists | A bare content hash becomes the key and the door closes the wrong way |
| Bound a hung step behaviourally | AC-0232 | r4 § Goals: "no step is *reported* running past `step_deadline`" | The delivery measures how bad a hung step is without ever bounding one |

**Calling a real provider**

- [ ] **AC-0223.** A step completes a Bedrock call under a scoped assumed role and reaches `step.completed`, evidenced from the run's event log rather than from test setup.
- [ ] **AC-0224.** The running worker container holds no long-lived provider credential: no `AKIA`-prefixed access key, no credentials file baked into the image, and no credential that outlives the assumed-role session. Short-lived session credentials delivered to the process are what ambient workload identity yields and are in scope; what this criterion forbids is a static one.
- [ ] **AC-0225.** The run header records the producer tuple, including the resolved inference profile and the exact `pydantic-ai` version.

**Persisting and resuming a step**

- [ ] **AC-0226.** A message history containing a tool call, a tool return, a retry part, and a pending approval serialises, deserialises, and re-serialises to identical bytes.
- [ ] **AC-0237.** A step suspended on `request_approval()` releases its lease, so the row is claimable by another worker without waiting for the lease to expire.
- [ ] **AC-0227.** A fresh agent in a separate process, sharing nothing with the original run but those bytes, resumes the suspended step and applies the approval decision.
- [ ] **AC-0228.** No persisted message history contains a reasoning part, demonstrated against a history that carried one before persisting.
- [ ] **AC-0229.** A step resumed from a history that carries stale instruction text is prompted by the current role compilation, and the stale text does not reach the model.
- [ ] **AC-0230.** With a crash injected between the payload write and the fenced append, an unreferenced payload object remains and no event carries a payload reference that does not resolve.
- [ ] **AC-0231.** Every payload object key is scope-qualified as `<owner_scope>/<content_hash>`, so a bare content hash is never the key.

**Bounding a hung step**

- [ ] **AC-0232.** A step whose model call hangs is failed and its lease released within `step_deadline`, whether or not the underlying provider call terminated.

## Follow-ons

- eugenelim: `workspace.toml` `[backlog].open` — the credential broker commissioned by DR12, which is where per-integration credential scopes (`worker-runtime.md` change 9) are carried. Already tracked.

## Assumptions

- Technical: `pydantic-ai` is pinned to 2.45.0 rather than ADR-0001 D5's 2.44.0 (source: user decision 2026-09-18). The framework-seam probe that established this is recorded once, in `walking-skeleton-role-compilation/plan.md` § Grounding probe; this spec cites it there rather than repeating it.
- Technical: a deferred-approval history round-trips byte-identically and a fresh agent resumes from the bytes alone, established offline before this spec was written. AC-0226's residual risk is therefore the *combination* of a realistic shape with a pending approval, not the mechanism (source: `plan.md` § Approval probe).
- Technical: `walking-skeleton-role-compilation` ships the compiler whose output this spec executes, and pins the framework including the `[bedrock]` extra. This spec adds no framework dependency (source: `walking-skeleton-role-compilation/plan.md` § Dependencies & integration).
- Technical: `walking-skeleton-authority-containment` ships the containment predicate, and without it the decision point admits no call. AC-0227 needs an approved tool body to run, so that spec is a hard dependency rather than a peer (source: `walking-skeleton-role-compilation/spec.md` AC-0233; adversarial spec review, 2026-09-20).
- Technical: the foundation spec ships the schema, both append paths, the privilege split and the pool. This spec adds no column; it writes the Phase 1 runtime's first payload object, which is why object keys become scope-qualified here (source: `walking-skeleton-foundation/plan.md` § Data & schema).
- Technical: the IAM shape established by spike 1 admits the call — inference-profile ARN pinned to the calling region, foundation-model ARN region-wildcarded, no requested-region condition — and both plausible tightenings deny it outright (source: `spikes/README.md` § Spike 1).
- Process: this spec is one of three cut from `walking-skeleton-agent-runtime`, whose directory was deleted on 2026-09-20. AC-0223 through AC-0232 carry across with their wording unchanged (source: user decision 2026-09-20).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Product: the skeleton carries one analysis step over the recorded fixture rather than a live corpus — the thinnest construction that exercises every criterion (source: assumption stated 2026-09-18, to be confirmed at the approval gate).
- Governance: r7 and r4 are ratified as of 2026-09-18, r7 with its Known-at-ship gaps accepted open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
