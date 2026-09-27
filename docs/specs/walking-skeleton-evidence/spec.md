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

The last of the six specs delivering the Phase 1 walking skeleton, and the one
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
`walking-skeleton-role-compilation`, `walking-skeleton-authority-containment`,
`walking-skeleton-policy-decision-point` and `walking-skeleton-step-lifecycle`
are all hard dependencies: this spec measures a system they build.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Operations | Applicable — `step_deadline`, the page threshold and the token budget are operator-owned and derive from measurements taken here | `docs/architecture/pydantic-ai-worker-runtime/operations.md` | work-loop | Each recorded value with the sample size behind it and the platform it was measured on | Values satisfy the ordering invariant and cite their sample size |
| Reusable learning | Applicable — Phase 1's whole purpose is the evidence Phase 2 plans against | `spikes/README.md` | work-loop | A Phase 1 section stating what was established, what was substituted, and what was not | Hypothesis checks reported separately from setup and teardown |
| Current architecture | Applicable — r8's STATUS header still names the authorization boundary and the provider call as unbuilt, and `docs/architecture/README.md` § What is built records both as shipped, so the header is already stale before this spec changes anything. This spec is the last of the six and is where the remaining clauses clear | `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md`, `docs/architecture/README.md` | work-loop | The header's unbuilt list re-derived from § What is built as it stands, then reduced to what is still unbuilt after this spec, with the residue named rather than dropped. r8 § 10's schema table is corrected in the same pass: it marks the partial unique index, `pool_class` and `owner_scope` `Owed` though revision 0002 creates all three | Status header matches the repository, and names what the document still specifies that nobody has built |
| Schema | Applicable — this spec opens two append paths that do not exist, so it is not the no-migration delivery the plan first assumed | `migrations/versions/`, `docs/adr/` | work-loop | One expand-only revision adding the run-terminal and approval-grant append paths with their `EXECUTE` grants, and the ADR recording why the acting identity deviates from r8 § 4's step-scoped-only row | The revision applies on a clean volume, grants stay disjoint, and the ADR is referenced from the criterion that rests on it |
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

- **TDD (AC-0302, AC-0306, AC-0320, AC-0321, AC-0323)** — the compressible invariants. AC-0306 is the only measurement-adjacent criterion that can red, and it does so by reading three recorded values rather than comparing against a literal. AC-0320 and AC-0323 are decided against the database and the stream surface respectively; **AC-0320 carries the `substrate` marker**, because a grant set is a property of the applied schema and an in-memory fixture would assert the migration's text rather than its effect.
- **End-to-end (AC-0301, AC-0303)** — a clean run reaching publication needs every layer beneath it, so neither can be written before the system it exercises.
- **Visual / manual QA (AC-0304, AC-0305, AC-0322)** — the browser. An assertion over an HTTP response body does not establish that the client reconnected with `Last-Event-ID`, that the page did not double-render, or that agent-authored markup reached the reader as characters rather than as elements. Driven by a real browser, with the observed result recorded. **AC-0305 is the exception within this group**: its distinguishing observation is what the server sent, which is read from the wire rather than from the page, for the reason the criterion itself states.
- **Measurement (AC-0307, AC-0308, AC-0309, AC-0310, AC-0311, AC-0312, AC-0313)** — the criteria whose outcome is a number nobody yet knows. A measurement is not a pass/fail test, so each names the sample size that makes the number mean something and where it is recorded. The ordering those numbers must satisfy is AC-0306, in the TDD group, which is the part that can fail.
- **Record review (AC-0314)** — checked by reading, because its subject is whether the record names what the delivery did *not* establish. No machine can decide that a stated limitation is the right one. It is a criterion rather than working material because its failure state is concrete: a Phase 1 record that lists results and names no substitution fails it.

## Acceptance Criteria

**The sources, cited as they actually read.** `runtime-architecture.md` § 10
Rollout numbers nothing: its Phase 1 entry sentence is an unnumbered
semicolon list, and the exit-criteria paragraph after it names nine items. Of
those, **this spec sources five** — calibrate the p99 page threshold and
`step_deadline`; record the account token-per-minute quota; measure
cancellation latency on an in-flight stream; confirm a clean run publishes
with zero human interaction; re-baseline analytical quality under the current
stack. From the entry sentence it sources **one**: stream to a browser. The
other four exit criteria and the remaining entry clauses belong to the sibling
specs. `worker-runtime.md` § 10 Rollout, Migration, and Reversal **does**
number its eight criteria, and this spec sources 1, 2, 4 and 7.

An earlier revision of this line cited "Phase 1 criterion 4 and its three named
exit criteria", which resolves to nothing in § 10 and made AC-0305 and AC-0314
read as sourced when neither appears in either list. Every criterion **beyond**
those sources is tabled below, and the approval gate rules on each.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Assert the surface the approval gate is actually decidable on | AC-0302 | A run can complete cleanly while an approval-gated tool it never triggered still sits in the stack, so the outcome alone cannot see the gate being made unconditional. The shipped placement decides *where* that is observable, not whether it must be | The check that protects a ratified charter amendment is satisfied by a run that happened not to trigger it |
| Ten forced disconnects, and an observation that separates preference from de-duplication | AC-0305 | § 10 names "stream to a browser" and stops there; surviving reconnection is the property that makes a stream usable, and the idempotent sink hides the failure unless the criterion looks at the wire | The reconnect semantics this spec adds to the published contract are never established |
| Record the producer tuple on the re-baseline run | AC-0312 | The comparison has no identity without it, and a figure nobody can reproduce is not a baseline | The re-baseline produces a number that cannot be compared to a later one |
| Say what the delivery did not establish | AC-0314 | Phase 1's whole output is evidence, and evidence whose limits are unstated overclaims. No § 10 item asks for it | Phase 2 plans against measurements it believes carry further than they do |
| Fix the identity that may commit a run-terminal transition | AC-0320 | AC-0301 needs an append path that does not exist, and r8 § 4 line 460 and § 3 line 344 disagree about which role writes it. Building it without a criterion settles a ratified contradiction at the keyboard | The privilege split — which r8 § 4 calls the whole control — is widened by whichever shortcut the implementer reaches first |
| Observe the approve/reject cycle cap, and require its configuration to be finite | AC-0321 | r5 line 607 fixes the loop at three cycles and line 620 calls the number arbitrary, asking Phase 1 to replace it. Nothing in `src/` implements a cap at all, so the disposition "lands, unmeasured" describes something that does not exist | An unbounded reject loop ships while the record says a cap is merely unmeasured |
| Check the plain-text rendering rule rather than stating it | AC-0322 | § Never do forbids agent-authored text rendered as markdown, HTML or a link, and AC-0304 is satisfied by a client that interpolates markup. A boundary with no criterion is not verifiable from this document, which § Spec contract requires | Filing text authored by the entity under analysis reaches the operator's browser as live markup |
| Bound the cursor the server is told to prefer | AC-0323 | The contract extension makes `Last-Event-ID` outrank `after=`, and `after` carries a type and a lower bound while the header carries neither. Validation is not cuttable at a trust boundary | The one input the server prefers is the one nothing validates |

**Running to publication**

- [ ] **AC-0301.** A run whose pre-release checks all pass reaches `completed`, publishes its typed artifact, and appends no `approval.requested` event.
- [ ] **AC-0302.** A run whose pre-release checks all pass presents the agent with **no callable approval-gated tool**, asserted on the tool set the model is offered at the moment of the run rather than inferred from the run's outcome.

  **Why this is not asserted on the *compiled* toolset.** `walking-skeleton-step-lifecycle` sites the approval tool outside the compiled stack deliberately: `src/ced/agents/tools/approval.py` builds it as a run-time `FunctionToolset` that `src/ced/worker/executor.py` passes through `toolsets=[…]` on the agent call, so the policy decision point never judges it against the acting role's ceiling. On that design the compiled toolset contains no approval-gated tool **in every possible world**, and a criterion reading it is true with or without the control — the vacuity shape this spec's predecessors were caught by three times. r8 § 3 lines 400–403 describes the other placement, compiling the tool in only when a check failed, so the shipped code deviates from a ratified document. **Owner decision 2026-09-26: the shipped placement stands**, because keeping approval outside the decision point's authority check is a property worth more than the agreement, and moving it would reopen a shipped spec. The deviation is recorded in an ADR this spec writes, and this criterion moves to the surface where conditionality is decidable on that design.
- [ ] **AC-0303.** A run whose pre-release checks fail suspends for approval, releases its lease, and resumes to publication after a grant — so the clean path of AC-0301 is one branch of a real condition rather than the only branch. **The grant event names the granting principal**, and the `require_distinct_approver` state in force at the moment of the grant is recoverable from the log, asserted by reading back what was appended rather than what the test supplied.

  r8 lines 406–407 ratify that both are recorded, and no criterion in any of the six Phase 1 specs asserted either. `events.principal` already carries the first. The second has no column in the shipped envelope, so its carrier is the payload object AC-0320's append path writes.

**Who may close a run, and how often it may be sent back**

- [ ] **AC-0320.** A run-terminal transition is committed by **exactly one** identity, and the `runs.state` change and its terminal event commit together or not at all: with the append forced to fail, the state does not move, and no path exists by which the state moves without the event. Asserted against the applied schema, which also holds that no application role gains `EXECUTE` on an append function another already holds, and that no role gains a direct `INSERT` on `events`.

  **This criterion exists because r8 disagrees with itself and the code admits neither reading.** § 4 line 460 limits the worker to step-scoped types; § 3's sequence diagram at line 344 has the worker append `run.completed`. In the shipped schema no identity can append it at all: `append_run_event` admits `run.requested` and `run.cancelled` only and is granted to `app_api` alone, and `append_step_event` refuses the terminal namespace outright. Meanwhile `app_worker` holds a table-level `GRANT UPDATE ON runs` from revision 0001, so the shortest implementation — set `runs.state = 'completed'` and move on — **works**, and produces a run that reached a terminal state with nothing in the log that says so, in a system whose product claim is that the log is the record. That is the failure this criterion's second clause exists to make impossible. **Owner decision 2026-09-26:** a new definer function carries the transition, granted to `app_worker` alone and fenced on the step that completed the run while writing `step_id` null; the ADR this spec writes records the deviation from § 4's step-scoped-only row and why § 3's diagram is the reading kept.

- [ ] **AC-0321.** The approve/reject cycle cap is observed: a step sent back for revision more times than the cap allows fails with a recorded cause rather than looping, and the cap's configuration carries a **finite default** — a deployment that sets no value gets a bounded loop, not an unbounded one. Asserted by driving the transition the cap counts, not by reading a configuration value back.

  r5 line 607 fixes the loop at three cycles per step and line 620 records the number as arbitrary, asking Phase 1 to replace it with an observed one. **This skeleton runs too few approval cycles to observe one, so the number is not replaced here** and § Follow-ons says so. What changes is that the cap now exists: nothing in `src/` implements one today, so the plan's disposition "lands, unmeasured" described a control that was absent rather than merely uncalibrated. The finite-default clause is what stops this being a criterion that a configuration read satisfies — without it, a deployment that declares nothing has no cap and the assertion still passes.

**Watching from a browser**

- [ ] **AC-0304.** A browser at the run's page renders each event as it commits, and reaches the terminal event with the stream closed.
- [ ] **AC-0305.** Across ten forced disconnects with a writer active, the browser applies every event exactly once, with the client sending a deliberately stale `after=0` on each reconnect. **The check is what the server sent, not only what the page shows:** on each reconnect the first event the server emits has the sequence after the client's `Last-Event-ID`, and no reconnect re-emits an event the client already holds.

  **The page-level assertion alone cannot fail.** The client sink is idempotent on the run-and-sequence pair, so a server that ignored `Last-Event-ID` entirely and replayed from sequence 1 on every reconnect would have its whole replay dropped by the sink, leaving "applies every event exactly once" green and the `Last-Event-ID` preference — the interface-compatibility output this spec adds to `contracts/openapi/runs.yaml` — never established. Reading the wire is what separates *preference honoured* from *replay de-duplicated*, and the two are indistinguishable from the page by construction.

- [ ] **AC-0322.** A run whose agent-authored text contains markup and a link target renders in the browser with those characters shown literally: no element is created from them, and the page holds no navigable anchor the model authored. Asserted against the rendered page, not the response body.

  § Never do forbids agent-authored text rendered as markdown, HTML or a link, and AC-0304 is satisfied exactly by a client that interpolates markup — so the rule was contract with nothing that checks it. The reachable path is r8's own indirect-injection boundary: filing text is authored by the entity under analysis, crosses the quarantine boundary, and lands in a page that is same-origin with an API this Phase deliberately leaves unauthenticated. Typed domain artifacts render through the application's own components from structured fields and stay rich; that is a different path and this criterion does not narrow it.

- [ ] **AC-0323.** `Last-Event-ID` is parsed under the same type and lower bound the contract already fixes for `after=`, and a header failing them is refused rather than coerced or silently treated as zero.

  The reconnect semantics make the header outrank the query parameter, so the input the server is told to *prefer* is the one carrying no schema while the one it overrides carries `type: integer` and `minimum: 0`. A criterion that only asserts the preference would ship the preference and not the validation, and `AGENTS.md` § Coding conventions does not admit cutting validation at a trust boundary.

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
- **Closed in this spec, 2026-09-26: who approved a publication.** This entry previously recorded that no criterion in any Phase 1 spec asserted the attributability of a human grant, and that closing it was an amendment here. AC-0303 now carries it — the grant event names the granting principal and the `require_distinct_approver` state is recoverable from the log. Kept as a record rather than deleted, because the reason the gap existed is part of the delivery's history: AC-0209 asserts a *machine* denial names the acting role and the initiating principal, r8 holds attributable action at 100%, and the one decision a person makes had no criterion at all.
- eugenelim: **the cycle cap's number is still arbitrary.** AC-0321 now requires the cap to exist and its configuration to carry a finite default, which it did not before — nothing in `src/` implemented a cap at any value. What AC-0321 does *not* do is replace the number: r5 line 620 asks Phase 1 to substitute an observed one, and this skeleton runs too few approval cycles to observe anything. The cap ships at r5's three, bounded and unmeasured, and the number is owed to the first delivery that runs enough cycles to earn one.
- eugenelim: **the deviations this spec records rather than resolves.** Two ratified statements are left standing and contradicted, each under an ADR this spec writes: r8 § 3 lines 400–403 on the approval gate's placement, against the run-time injection `walking-skeleton-step-lifecycle` shipped (AC-0302); and r8 § 4 line 460 on the worker being limited to step-scoped types, against § 3 line 344's own diagram and the append path AC-0320 builds. An ADR records a deviation; it does not amend r8. The r9 consistency pass that reconciles the document with itself is owed and unowned.

## Assumptions

- Technical: p99 step duration is unknowable before real steps run, so `step_deadline` cannot be set before the measurement exists. The criterion is the measurement (source: `worker-runtime.md` § 11 Open Questions).
- Technical: whether cancellation aborts an in-flight Bedrock stream promptly is unverified, and measuring it is AC-0309 itself. `botocore` is synchronous, so asyncio cancellation may unwind the coroutine while the socket lives; `walking-skeleton-step-lifecycle` supplies the hard timeout that bounds the step regardless, under its own criterion for bounding a hung step (source: `worker-runtime.md` § 9 Decisions, Alternatives, and Risks; `walking-skeleton-step-lifecycle` § Bounding a hung step).
- Technical: measurements are taken on local containers, not on Fargate. The step is model-bound so p99 should mostly carry, but "mostly" is not measured, which is what AC-0314 records (source: user decision 2026-09-18).
- Technical: a recorded Apple 10-Q fixture exists under `spikes/phase-0/fixtures/`, so AC-0312 needs no live SEC fetch — which matters because EDGAR returns 403 to this network (source: `spikes/README.md` § Spike 4).
- Technical: spike 4 cost $0.022 and was **falsified as run**. A second falsification is an acceptable outcome of AC-0312 (source: `spikes/README.md` § Spike 4).
- Technical: the browser client is Vite and React, deliberately minimal — an event list and a state badge. The real experience surface belongs to the experience companion (source: user decision 2026-09-18).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents — a shaping review over two rounds and an adversarial spec-mode review — and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Governance: r8 and r5 are ratified, r8 with its five accepted limits in § 9 open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
- Governance: **r8 disagrees with itself in one place this spec must act on.** § 4 line 460 limits the worker to step-scoped event types; § 3's sequence diagram at line 344 has the worker append `run.completed`, a run-lifecycle type. Ratified means implemented, not reconciled, so this spec takes § 3's reading under an ADR and leaves the contradiction standing for the r9 consistency pass. AC-0320 is what keeps the choice from widening the privilege split (source: owner decision 2026-09-26).
- Technical: **the contract was written before any of its five dependencies existed and has been re-derived from the tree.** The first pre-EXECUTE review found two criteria that could not fail, two append paths the shipped privilege split has no room for, and a sixth top-level directory nothing had admitted. Statements here about what exists are as of 2026-09-26 and were checked against the code rather than against the previous revision of this document.
