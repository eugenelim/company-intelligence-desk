# Spec: Walking skeleton — evidence

- **Status:** Approved <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § 10 Rollout, Phase 1
- **Discovery:** none
- **Contract:** [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml) — extended here with the stream's reconnect semantics; created by the foundation spec
- **Shape:** mixed

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Boundaries`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Objective`, `Durable Outputs`, `Follow-ons` and `Assumptions`
> are working material, corrected in place without an amendment.

## Objective

The last of five specs delivering the Phase 1 walking skeleton, and the one
that turns a working system into recorded evidence.

A run moves through its state machine and publishes without a human touching
it. A browser watches it live and survives losing the connection. And the four
numbers Phase 1 exists to produce get measured rather than guessed: p99 step
duration, the `step_deadline` derived from it, how long cancellation actually
takes on an in-flight stream, and the account's token-per-minute budget.

Two of these outputs are uncomfortable by design. The cancellation measurement
may report that the provider call was merely *abandoned* rather than
terminated, which is a worse operational story than the design hopes for. And
the analytical re-baseline may be falsified a second time, as spike 4 was. Both
are results to record, not bars to clear, and this spec is written so that a
bad number is a successful outcome.

Success is that Phase 1's exit criteria are met and that the record says
plainly what was established, what was substituted, and what was not
established at all.

**Its siblings.** `walking-skeleton-foundation`,
`walking-skeleton-role-compilation`, `walking-skeleton-authority-containment`
and `walking-skeleton-step-lifecycle` are all hard dependencies: this spec
measures a system they build.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Operations | Applicable — `step_deadline`, the page threshold and the token budget are operator-owned and derive from measurements taken here | `docs/architecture/pydantic-ai-worker-runtime/operations.md` | work-loop | Each recorded value with the sample size behind it and the platform it was measured on | Values satisfy the ordering invariant and cite their sample size |
| Reusable learning | Applicable — Phase 1's whole purpose is the evidence Phase 2 plans against | `spikes/README.md` | work-loop | A Phase 1 section stating what was established, what was substituted, and what was not | Hypothesis checks reported separately from setup and teardown |
| Current architecture | Applicable — r8's STATUS header reads `PARTIALLY BUILT` and names the agent layer, the authorization boundary and the provider call as unbuilt; this spec is the last of the five and is where the remaining clauses clear | `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md`, `docs/architecture/README.md` | work-loop | The header's unbuilt list reduced to what is still unbuilt after this spec, with the residue named rather than dropped | Status header matches the repository, and names what the document still specifies that nobody has built |
| Interface compatibility | Applicable — the stream's reconnect semantics extend the contract the foundation spec created | `contracts/openapi/runs.yaml` | work-loop | The `Last-Event-ID` behaviour documented in the contract and asserted by test | Contract and implementation agree under test |
| User-facing promise | Not applicable — the browser client here is a test harness, not a product surface; the real experience belongs to the experience companion | — | — | — | — |

## Boundaries

### Always do

- Treat r8 and r5 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Record what a check does **not** establish alongside what it does. This spec is the one where that rule does the most work, because it is the one making claims from measurements taken on a substituted platform.
- Record a measurement's sample size and the platform it was taken on, beside the value.

### Ask first

- Any change to a ratified decision. The plan gives each DR decision this spec constructs a disposition.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Any spend above the Phase 0 order of magnitude. The re-baseline cost $0.022 the first time; a task that would cost more than $5 stops and asks.
- Relaxing a criterion because its number came back unflattering.

### Never do

- **No unconditional approval gate.** Making publication statically approval-gated silently reverses a ratified charter amendment, and a clean run must reach publication with no human in the path.
- **No re-running a measurement until it looks better.** A recorded figure is the first honest one, with its sample size.
- **No agent-authored text rendered as markdown, HTML, or a link.** A model-authored link target must not become clickable; typed domain artifacts render through the application's own components from structured fields.
- **No token deltas in the event log.** The log records semantic events; the stream is a cursor-served projection over it, and appending token deltas would make the reconstruction goal's byte-matching meaningless.
- **No live SEC fetch.** The re-baseline runs against the recorded fixture.

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0302, AC-0306)** — the two compressible invariants. AC-0306 is the only measurement-adjacent criterion that can red, and it does so by reading three recorded values rather than comparing against a literal.
- **End-to-end (AC-0301, AC-0303)** — a clean run reaching publication needs every layer beneath it, so neither can be written before the system it exercises.
- **Visual / manual QA (AC-0304, AC-0305)** — the browser. An assertion over an HTTP response body does not establish that the client reconnected with `Last-Event-ID` and that the page did not double-render. Driven by a real browser, with the observed result recorded.
- **Measurement (AC-0307, AC-0308, AC-0309, AC-0310, AC-0311, AC-0312, AC-0313)** — the criteria whose outcome is a number nobody yet knows. A measurement is not a pass/fail test, so each names the sample size that makes the number mean something and where it is recorded. The ordering those numbers must satisfy is AC-0306, in the TDD group, which is the part that can fail.
- **Record review (AC-0314)** — checked by reading, because its subject is whether the record names what the delivery did *not* establish. No machine can decide that a stated limitation is the right one. It is a criterion rather than working material because its failure state is concrete: a Phase 1 record that lists results and names no substitution fails it.

## Acceptance Criteria

Obligations come from `runtime-architecture.md` § 10 Rollout, Phase 1 criterion 4
and its three named exit criteria, and from `worker-runtime.md` § 10 Rollout, Migration, and Reversal
criteria 1, 2, 4 and 7. Obligations **beyond** those sources are tabled below,
and the approval gate rules on each.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Assert the compiled toolset, not just the run outcome | AC-0302 | A run can complete cleanly while an approval-gated tool it never triggered still sits in the stack, so the outcome alone cannot see the gate being made unconditional | The check that protects a ratified charter amendment is satisfied by a run that happened not to trigger it |
| Record the producer tuple on the re-baseline run | AC-0312 | The comparison has no identity without it, and a figure nobody can reproduce is not a baseline | The re-baseline produces a number that cannot be compared to a later one |

**Running to publication**

- [ ] **AC-0301.** A run whose pre-release checks all pass reaches `completed`, publishes its typed artifact, and appends no `approval.requested` event.
- [ ] **AC-0302.** A run whose pre-release checks all pass compiles a toolset containing no approval-gated tool, asserted on the compiled toolset rather than inferred from the run's outcome.
- [ ] **AC-0303.** A run whose pre-release checks fail suspends for approval, releases its lease, and resumes to publication after a grant — so the clean path of AC-0301 is one branch of a real condition rather than the only branch.

**Watching from a browser**

- [ ] **AC-0304.** A browser at the run's page renders each event as it commits, and reaches the terminal event with the stream closed.
- [ ] **AC-0305.** Across ten forced disconnects with a writer active, the browser applies every event exactly once, with the client sending a deliberately stale `after=0` on each reconnect — so a server trusting the query parameter would replay from the beginning and the duplicate would be visible on the page.

**Calibrating the deadline**

- [ ] **AC-0307.** p99 step duration is recorded from at least 30 completed real steps, an owner-chosen minimum enforced by the measurement command refusing to emit a figure below it, with the sample size and the platform stated beside the value.
- [ ] **AC-0308.** The page threshold is recorded as `p99 × 3` — the factor `runtime-architecture.md` § Risks fixes for the primary page — computed from the same sample as AC-0307.
- [ ] **AC-0306.** The configured `step_deadline`, the measured p99 and the recorded page threshold satisfy `p99 < step_deadline < page_threshold`, asserted by a test reading all three recorded values.

**Measuring cancellation**

- [ ] **AC-0309.** Cancellation latency on an in-flight model stream is measured and recorded as a wall-clock figure.
- [ ] **AC-0310.** The measurement command emits, from the fixed vocabulary `terminated` or `abandoned`, which of the two occurred, derived from an observation of the connection rather than written by hand.

**Recording the account's token budget**

- [ ] **AC-0311.** The account's Bedrock tokens-per-minute quota is read from Service Quotas and recorded with its Region.

**Re-baselining analytical quality**

- [ ] **AC-0312.** Spike 4's A/B comparison is re-run under the new stack against the recorded 10-Q fixture, labelled with its producer tuple, and recorded against the same three loss categories the original reported.
- [ ] **AC-0313.** The re-run records what the narrowed admitted set costs separately from what the quarantine boundary costs.

**Saying what Phase 1 did not establish**

- [ ] **AC-0314.** The Phase 1 record names, for each measurement, the platform substitution behind it and the property a deployed fleet would establish that this one does not.

## Follow-ons

- eugenelim: `runtime-architecture.md` § 6 Deployment and Operations — AWS deployment to ECS Fargate. § 6 sizes the services; the load balancer and OIDC authentication at the ingress are § 2 and § 4. Its IaC and the mandatory infra security review are recorded nowhere upstream and rest on the owner's decision of 2026-09-18, which put the deployment out of scope. AC-0314 is the record of what that deployment would establish and this delivery does not.
- eugenelim: this spec § Acceptance Criteria — **no criterion records who approved a publication.** AC-0209 asserts a machine denial names the acting role and the initiating principal, and r8 holds attributable action at 100%, but the one decision a *person* makes has no attributability criterion in any of the five Phase 1 specs; AC-0303 resumes after a grant without asserting the grant event names the grantor. With `require_distinct_approver` defaulting to false for a single operator, the recorded principal is the only control left. A repudiation gap, not an access-control one. This spec owns the transition, so closing it is an amendment here.
- eugenelim: the approve/reject cycle cap, currently three and arbitrary by r5's own admission (DR5). r5 says Phase 1 should replace it with an observed number; this skeleton runs too few approval cycles to observe one, so the cap ships unchanged and unmeasured.

## Assumptions

- Technical: p99 step duration is unknowable before real steps run, so `step_deadline` cannot be set before the measurement exists. The criterion is the measurement (source: `worker-runtime.md` § 11 Open Questions).
- Technical: whether cancellation aborts an in-flight Bedrock stream promptly is unverified, and measuring it is AC-0309 itself. `botocore` is synchronous, so asyncio cancellation may unwind the coroutine while the socket lives; `walking-skeleton-step-lifecycle` supplies the hard timeout that bounds the step regardless, under its own criterion for bounding a hung step (source: `worker-runtime.md` § 9 Decisions, Alternatives, and Risks; `walking-skeleton-step-lifecycle` § Bounding a hung step).
- Technical: measurements are taken on local containers, not on Fargate. The step is model-bound so p99 should mostly carry, but "mostly" is not measured, which is what AC-0314 records (source: user decision 2026-09-18).
- Technical: a recorded Apple 10-Q fixture exists under `spikes/phase-0/fixtures/`, so AC-0312 needs no live SEC fetch — which matters because EDGAR returns 403 to this network (source: `spikes/README.md` § Spike 4).
- Technical: spike 4 cost $0.022 and was **falsified as run**. A second falsification is an acceptable outcome of AC-0312 (source: `spikes/README.md` § Spike 4).
- Technical: the browser client is Vite and React, deliberately minimal — an event list and a state badge. The real experience surface belongs to the experience companion (source: user decision 2026-09-18).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents — a shaping review over two rounds and an adversarial spec-mode review — and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Governance: r8 and r5 are ratified, r8 with its five accepted limits in § 9 open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
