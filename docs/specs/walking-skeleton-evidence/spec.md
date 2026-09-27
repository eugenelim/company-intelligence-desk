# Spec: Walking skeleton — evidence

- **Status:** Draft <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § 10 Rollout, Phase 1
- **Discovery:** none
- **Contract:** [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml) — created by the foundation spec, and gaining **a fourth operation** here. The three routes it contracts today are the whole Phase 1 surface, and `/runs/{run_id}/events` is a paged JSON `EventPage` read, not a stream: there is no `text/event-stream` anywhere in the file or in `src/ced/api/`. An earlier revision of this line called the change "the stream's reconnect semantics", which described an upgrade to something that does not exist. The new operation serves `text/event-stream`, prefers `Last-Event-ID` over `after=` under AC-0323's bounds, and closes the connection on a terminal event — which is what AC-0304 means by reaching the terminal event with the stream closed, and has no meaning on the paging route. The paged read stays as it is
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
| Interface compatibility | Applicable — a fourth operation joins the three the foundation spec contracted, because no stream exists to extend | `contracts/openapi/runs.yaml` | work-loop | The new operation documented with its media type (`text/event-stream`), its `Last-Event-ID` preference and bounds, its refusal status, and its terminal-close semantics — each asserted by test | Contract and implementation agree under test, and the generated document matches the hand-authored one |
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

- **TDD (AC-0302, AC-0306, AC-0320, AC-0321, AC-0323, AC-0324, AC-0325, AC-0326)** — the compressible invariants. **AC-0320 and AC-0324 carry the `substrate` marker**, because a grant set is a property of the applied schema and an in-memory fixture would assert the migration's text rather than its effect. AC-0321 is substrate too: its durability clause is driven across a real worker handoff. AC-0323 and AC-0326 are decided against the stream and HTTP surfaces.

  **No criterion in this group is the delivery's measurement failure surface, and an earlier revision claimed one was.** AC-0306 was described as "the only measurement-adjacent criterion that can red"; it cannot red here at all, because the deadline it orders is derived from the p99 it orders against. Its own entry now says so. What this group does carry is every control whose absence a mutation can demonstrate — which is the property that matters and is not the same claim.
- **End-to-end (AC-0301, AC-0303)** — a clean run reaching publication needs every layer beneath it, so neither can be written before the system it exercises.
- **Visual / manual QA (AC-0304, AC-0305, AC-0322)** — the browser. An assertion over an HTTP response body does not establish that the client reconnected with `Last-Event-ID`, that the page did not double-render, or that untrusted markup reached the reader as characters rather than as elements. Driven by a real browser, with the observed result recorded. **AC-0305 is the exception within this group**: its distinguishing observation is what the server sent, which is read from the wire rather than from the page, for the reason the criterion itself states.
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
| Drive the flagged branch, and record who released it | AC-0303 | r5 § 10 criterion 4 is the *clean* run; no named source covers the branch where a check fails, suspends, and is released by a person. Without it AC-0301's "clean" is the only path anything exercises, and the three clauses this criterion adds — determinism, the two-state flag, the principal read-back — rest on nothing the gate ruled on | The approval gate ships exercised only in the branch that never reaches it |
| Assert the surface the approval gate is actually decidable on | AC-0302 | A run can complete cleanly while an approval-gated tool it never triggered still sits in the stack, so the outcome alone cannot see the gate being made unconditional. The shipped placement decides *where* that is observable, not whether it must be | The check that protects a ratified charter amendment is satisfied by a run that happened not to trigger it |
| Ten forced disconnects, and an observation that separates preference from de-duplication | AC-0305 | § 10 names "stream to a browser" and stops there; surviving reconnection is the property that makes a stream usable, and the idempotent sink hides the failure unless the criterion looks at the wire | The reconnect semantics this spec adds to the published contract are never established |
| Record the producer tuple on the re-baseline run | AC-0312 | The comparison has no identity without it, and a figure nobody can reproduce is not a baseline | The re-baseline produces a number that cannot be compared to a later one |
| Say what the delivery did not establish | AC-0314 | Phase 1's whole output is evidence, and evidence whose limits are unstated overclaims. No § 10 item asks for it | Phase 2 plans against measurements it believes carry further than they do |
| Fix the identity that may commit a run-terminal transition | AC-0320 | AC-0301 needs an append path that does not exist, and r8 § 4 line 460 and § 3 line 344 disagree about which role writes it. Building it without a criterion settles a ratified contradiction at the keyboard | The privilege split — which r8 § 4 calls the whole control — is widened by whichever shortcut the implementer reaches first |
| Observe the approve/reject cycle cap, and require its configuration to be finite | AC-0321 | r5 line 607 fixes the loop at three cycles and lines 619–622 call the number arbitrary, asking Phase 1 to replace it. Nothing in `src/` implements a cap at all, so the disposition "lands, unmeasured" describes something that does not exist | An unbounded reject loop ships while the record says a cap is merely unmeasured |
| Check the plain-text rendering rule rather than stating it | AC-0322 | § Never do forbids agent-authored text rendered as markdown, HTML or a link, and AC-0304 is satisfied by a client that interpolates markup. A boundary with no criterion is not verifiable from this document, which § Spec contract requires | Filing text authored by the entity under analysis reaches the operator's browser as live markup |
| Bound the cursor the server is told to prefer | AC-0323 | The contract extension makes `Last-Event-ID` outrank `after=`, and `after` carries a type and a lower bound while the header carries neither. Validation is not cuttable at a trust boundary | The one input the server prefers is the one nothing validates |
| Fix the identity on the approval-grant append path too | AC-0324 | AC-0320 fixes the terminal path's identity, and its function-level disjointness assertion stays green whichever role gets the *grant* path. The grant needs its own path because r5 releases the lease before the approver acts, so the fence refuses it | A second new append path lands with its granting role chosen at the keyboard, and the privilege split widens with nothing recording it |
| Observe the per-run spend ceiling | AC-0325 | DR6 was dispositioned "lands in T1" with no task field and no criterion reaching it — the identical shape AC-0321 repairs for DR5. Fixing one sibling and not the other is how the same defect returns | A ratified spend control is recorded as delivered while nothing reads it |
| Fix the browser client's origin | AC-0326 | T3 introduces a browser origin against an API that authenticates nobody, and AC-0322's threat argument already assumes same-origin without the contract taking that decision | A permissive cross-origin allowance is added at the keyboard to make the dev server work, and every run becomes readable from any page the operator visits |

**Running to publication**

- [ ] **AC-0301.** A run whose pre-release checks all pass reaches `completed`, publishes its typed artifact, and appends no `approval.requested` event.
- [ ] **AC-0302.** A run whose pre-release checks all pass presents the agent with **no callable approval-gated tool**, asserted on the tool set the model is offered at the moment of the run rather than inferred from the run's outcome.

  **Why this is not asserted on the *compiled* toolset.** `walking-skeleton-step-lifecycle` sites the approval tool outside the compiled stack deliberately: `src/ced/agents/tools/approval.py` builds it as a run-time `FunctionToolset` that `src/ced/worker/executor.py` passes through `toolsets=[…]` on the agent call, so the policy decision point never judges it against the acting role's ceiling. On that design the compiled toolset contains no approval-gated tool **in every possible world**, and a criterion reading it is true with or without the control — the vacuity shape this spec's predecessors were caught by three times. r8 § 3 lines 400–403 describes the other placement, compiling the tool in only when a check failed, so the shipped code deviates from a ratified document. **Owner decision 2026-09-26: the shipped placement stands**, because keeping approval outside the decision point's authority check is a property worth more than the agreement, and moving it would reopen a shipped spec. The deviation is recorded in an ADR this spec writes, and this criterion moves to the surface where conditionality is decidable on that design.
- [ ] **AC-0303.** A run whose pre-release checks fail suspends for approval, releases its lease, and resumes to publication after a grant — so the clean path of AC-0301 is one branch of a real condition rather than the only branch. **Suspension is deterministic** because the role under test resolves to a model that calls `request_approval` on every flagged run; the criterion asserts the suspension, not the model's discretion. **The grant event names the granting principal**, and the `require_distinct_approver` state in force at the moment of the grant is recoverable from the log — asserted by configuring the flag **both ways** and reading back two different appended values, so the check distinguishes the flag being in force from a constant written into the payload.

  **What this does not establish, and the reason it cannot.** `principal` is a caller-supplied `text` parameter on every append function, and this Phase authenticates nobody — `POST /runs` takes the initiating principal as a string and r8 puts OIDC at the ingress, deferred by owner decision. So the read-back separates *what the log stored* from *what the test asserted*, and establishes nothing about who actually approved. **The recorded approver attribution is unauthenticated**, and AC-0314 records that beside the measurement limits. r8 lines 406–407 ratify that the flag state and the approver principal are recorded, and no criterion in any of the six Phase 1 specs asserted either; this criterion closes the *recording* gap, which is the half that was owed and the only half reachable while the ingress is deferred. `events.principal` carries the principal; the flag's configuration surface is `PoolConfig`, and the payload object AC-0320's path writes is its carrier in the log.

**Who may close a run, and how often it may be sent back**

- [ ] **AC-0320.** The append path that carries `run.completed` and `run.failed` is granted to **`app_worker` and to no other role**, and on that path the `runs.state` change and the terminal event commit together or not at all: with the append forced to fail, the state does not move. The path enforces five predicates, each asserted by a call that violates it — it **proves lease possession on the step that completed the run**, refusing a caller whose lease does not match; it admits only the terminal types named above; it refuses a `step_id` whose step does not belong to the run being written; it refuses a run already in a terminal state; and it writes `step_id` null. Asserted against the applied schema, which also holds that no application role gains `EXECUTE` on an append function another already holds, and that no role gains a direct `INSERT` on `events`.

  **Possession is first in that list because the whole deviation rests on it.** T0's ADR justifies letting a worker write a run-lifecycle type by arguing that the fence plus the null `step_id` keep r8 § 4's disjointness intact — so a predicate list omitting the fence would leave the justification asserting something no check reaches, and any worker in the pool could close any run whose step it does not hold, including one another worker is mid-flight on.

  **Two things this criterion deliberately does not claim.** It does not say `run.cancelled` is on this path: `run.cancelled` is in both the run-lifecycle and the terminal sets, `app_api` already holds `EXECUTE` on `append_run_event`, and that path appends the event while moving no state at all. That asymmetry is a shipped sibling's route, is left alone here, and is why this criterion names its two types rather than saying "terminal". And it does not claim that no path exists by which the state moves without the event — **`0001_base_schema.py:228-229` grants a table-level `UPDATE ON runs` to `app_api` and to `app_worker` alike, and both grants stay.** That file records them as taken verbatim from r7's identity table and narrowed by nobody, "because narrowing it unilaterally would deviate from ratified authority"; revoking either here would be exactly that. **Owner decision 2026-09-26: the claim is narrowed to what the applied grant set can decide, and the retained bypass is a residual AC-0314 records** — over both roles, including the one that serves the unauthenticated HTTP surface. A direct `UPDATE runs SET state='completed'` therefore still reaches a terminal run with nothing in the log saying so; what this criterion establishes is that the *intended* path cannot do it, not that no path can.

  **Why the path exists at all.** r8 disagrees with itself: § 4 line 460 limits the worker to step-scoped types; § 3's sequence diagram at line 344 has the worker append `run.completed`. In the shipped schema no identity can append it either way — `append_run_event` admits `run.requested` and `run.cancelled` only and is granted to `app_api` alone, and `append_step_event` refuses the terminal namespace outright. **Owner decision 2026-09-26:** a new definer function carries the transition, granted to `app_worker` alone and fenced on the step that completed the run; the ADR this spec writes records the deviation from § 4's step-scoped-only row and why § 3's diagram is the reading kept.

- [ ] **AC-0324.** The append path that carries `approval.granted` and `approval.rejected` is granted to **`app_api` and to no other role**, and it commits while the step's `owner` is null without widening what any role may write. It enforces four predicates, each asserted by a call that violates it: it admits only those two types; it refuses a `step_id` whose step does not belong to the run being written; it refuses a step that is not suspended; and it refuses a step that already carries a committed approval decision for the current suspension. Asserted against the applied schema on the same terms as AC-0320.

  **Why `app_api`, and what that costs.** The approver is a human acting through the API, and the worker is not holding the step — r5 line 604 releases the lease *before* the approver acts, which clears `owner`, so `fence_step`'s possession predicate fails and every fenced append raises. Granting this path to `app_worker` instead would let the process that suspended a step commit its own grant, which is the one thing an approval gate exists to prevent. So `app_api` holds it, and that **deviates from r8 § 4 line 460**, which limits `api` to run-lifecycle types while `approval.granted` is step-scoped. T0's ADR records the deviation alongside AC-0320's.

  **What stands in for possession, and what does not.** Nothing proves possession on this path, because by construction nobody holds the lease. The three structural predicates above are the substitute: the step must belong to the run, must be suspended, and must carry no decision yet for this suspension. **That is weaker than the fence**, and r8 § 4 line 461 ratifies "the fence proves possession — a never-claimed, released, drained or expired step is unappendable at any epoch" as *Built*. This path makes that invariant untrue for two event types, deliberately, and AC-0314 records it as a residual rather than leaving the reader to infer it from a migration.

- [ ] **AC-0321.** The approve/reject cycle cap is observed: a step sent back for revision more times than the cap allows fails with a recorded cause rather than looping, and the cap's configuration carries a **finite default** — a deployment that sets no value gets a bounded loop, not an unbounded one. Asserted by driving the transition the cap counts, not by reading a configuration value back.

  **The count is read from durable per-step state and survives losing the lease**, asserted by driving the cycles across a worker handoff rather than within one process. r5 lines 604–610 release the lease before the approver acts and have *a different worker* claim the step and resume from serialized bytes, so a counter in worker memory is reset by exactly the handoff this loop performs every cycle — and a criterion driving three rejections inside one process would pass against an unbounded loop.

  r5 line 607 fixes the loop at three cycles per step and lines 619–622 record the number as arbitrary, asking Phase 1 to replace it with an observed one. **This skeleton runs too few approval cycles to observe one, so the number is not replaced here** and § Follow-ons says so. What changes is that the cap now exists: nothing in `src/` implements one today, so the plan's disposition "lands, unmeasured" described a control that was absent rather than merely uncalibrated. The finite-default clause is what stops this being a criterion that a configuration read satisfies — without it, a deployment that declares nothing has no cap and the assertion still passes.

- [ ] **AC-0325.** The per-run spend ceiling fires: with usage already accumulated in the event log past the configured ceiling, the executor's check before dispatching the next step **pages rather than aborting** the run, and **the page is an appended event** — a named type on the run, readable from the log by an operator who was not watching, not a log line that vanishes with the container. The ceiling's configuration surface is `PoolConfig` and it **carries a finite default**, so a deployment that sets no value still gets a ceiling. Asserted by accumulating usage to the threshold and reading the appended event, not by reading the ceiling's configuration back.

  r5 lines 1255–1257 ratify this as an executor check before each step dispatch that pages rather than aborts, because for a single operator killing a legitimate long analysis is the worse error. DR6 was dispositioned "lands in T1" with no task field and no criterion reaching it — the same shape AC-0321 was added to repair for DR5, left unrepaired on its sibling.

  **The finite-default and named-observable clauses are the class fix, not this criterion's alone.** Three controls in this spec are configured rather than constant, and each fails the same way if a deployment declares nothing: the cycle cap (AC-0321), this ceiling, and `step_deadline`, whose `PoolConfig` field defaults to `None` meaning *no deadline at all* — so after T4 sets a measured value, the **default** must be finite too, or a deployment that configures nothing runs unbounded steps and AC-0306 reads three recorded numbers that describe no deployment. An earlier revision gave the clause to AC-0321 only, which is repairing the reported instance and leaving the class.

**Watching from a browser**

- [ ] **AC-0304.** A browser at the run's page renders each event as it commits, and reaches the terminal event with the stream closed.
- [ ] **AC-0305.** Across ten forced disconnects with a writer active, the browser applies every event exactly once, with the client sending a deliberately stale `after=0` on each reconnect. **The check is what the server sent, not only what the page shows:** on each reconnect the first event the server emits has the sequence after the client's `Last-Event-ID`, and no reconnect re-emits an event the client already holds.

  **The page-level assertion alone cannot fail.** The client sink is idempotent on the run-and-sequence pair, so a server that ignored `Last-Event-ID` entirely and replayed from sequence 1 on every reconnect would have its whole replay dropped by the sink, leaving "applies every event exactly once" green and the `Last-Event-ID` preference — the interface-compatibility output this spec adds to `contracts/openapi/runs.yaml` — never established. Reading the wire is what separates *preference honoured* from *replay de-duplicated*, and the two are indistinguishable from the page by construction.

- [ ] **AC-0322.** **No value originating outside the application reaches an HTML-interpreting or link-constructing sink anywhere in `ui/`.** Driven by a run whose agent-authored text, typed-artifact field values, and envelope fields each contain markup and a link target, and asserted against the rendered page: those characters are shown literally, no element is created from them, and the page holds no navigable anchor the model or a caller authored.

  **The class, not the instance.** An earlier revision of this criterion covered agent-authored text and then exempted the typed-artifact path — "that is a different path and this criterion does not narrow it". That carve-out exempted the path the model's strings actually travel: r5 makes the typed artifact the vehicle for published output, and *structured* does not mean *trusted* when the field values are strings the model wrote over filing text. Uncovered with it were `principal`, `agent_role` and `payload_ref`, which are caller-supplied free text on every append path. § Never do forbids the rendering with no path exception, so the criterion states no exception either.

  The reachable path is r8's own indirect-injection boundary: filing text is authored by the entity under analysis, crosses the quarantine boundary, and lands in a page that AC-0326 makes same-origin with an API this Phase deliberately leaves unauthenticated.

- [ ] **AC-0323.** `Last-Event-ID` is parsed under the same type and lower bound the contract fixes for `after=`, **and an upper bound the contract does not give `after=`: a cursor greater than the run's highest committed sequence is refused.** A header failing any of the three is refused with the `422` the contract already documents for a cursor outside its bounds, not coerced and not silently treated as zero.

  The reconnect semantics make the header outrank the query parameter, so the input the server is told to *prefer* is the one carrying no schema while the one it overrides carries `type: integer` and `minimum: 0`. The upper bound is the clause `after=` has no equivalent for and needs one here: a stream is long-lived where a page read is not, so a cursor past the committed log yields a connection that never emits and never closes, held open per caller. A cursor *behind* the log is the ordinary reconnect and is never refused — the distinction is ahead-of-the-log versus stale, and only the first is nonsense.

- [ ] **AC-0326.** The page and the API share an origin: the API serves the built browser client, a request carrying an `Origin` header naming any other origin is refused on the state-changing routes, and no permissive cross-origin allowance is configured. **Every path the static route resolves stays under the built bundle root** — a traversal request, its percent-encoded equivalent, and a symlink inside the bundle pointing outside it are each refused, and the single-page fallback serves `index.html` and never a file resolved outside the root.

  T3 introduces a browser origin for the first time against an API that authenticates nobody, and the shortest path to a working Vite dev server is a permissive `Access-Control-Allow-Origin` — which would make any page the operator visits a client of every run. **Owner decision 2026-09-26: the API serves the built bundle, so same origin by construction and no CORS middleware at all**; the dev server proxies to the API rather than calling it cross-origin. This is also what makes AC-0322's threat argument true rather than assumed.

  **The confinement clause is here because the origin decision created the boundary it guards.** Nothing under `src/ced/` serves a file today — there is no `StaticFiles` mount or equivalent anywhere — so this delivery opens the filesystem path rather than inheriting a confined one, and the reachable implementation shape is joining a request path onto a bundle root with a single-page fallback. The API process holds the `app_api` DSN, so an unconfined join is a credential read. Closing the cross-origin hole by opening a traversal one would be a poor trade, and the criterion states both halves so it cannot be made.

**Calibrating the deadline**

- [ ] **AC-0307.** p99 step duration is recorded from at least 30 completed real steps, an owner-chosen minimum enforced by the measurement command refusing to emit a figure below it, with the sample size and the platform stated beside the value.
- [ ] **AC-0308.** The page threshold is recorded as `p99 × 3` — the factor `runtime-architecture.md` § Risks fixes for the primary page — computed from the same sample as AC-0307.
- [ ] **AC-0306.** The configured `step_deadline`, the measured p99 and the recorded page threshold satisfy `p99 < step_deadline < page_threshold`, asserted by a test reading all three recorded values.

  **This criterion cannot fail within this delivery, and that is stated rather than implied.** AC-0308 fixes the page threshold at `p99 × 3` and T4 sets `step_deadline` from the same measurement, so any derivation of the form `p99 × k` with `1 < k < 3` makes the ordering hold by construction — the check derives its input from the constant it tests. **Owner decision 2026-09-26: AC-0306 is a regression guard, not this delivery's failure surface.** Its value is that a later configuration change breaking the ordering goes red. The alternative — deriving the deadline from something other than the measured p99 — would make the criterion falsifiable by abandoning the calibration T4 exists to perform, which is the worse trade.

**Measuring cancellation**

- [ ] **AC-0309.** Cancellation latency on an in-flight model stream is measured and recorded as a wall-clock figure.
- [ ] **AC-0310.** The measurement command emits, from the fixed vocabulary `terminated` or `abandoned`, which of the two occurred, derived from an observation of the connection rather than written by hand.

**Recording the account's token budget**

- [ ] **AC-0311.** The account's Bedrock tokens-per-minute quota is read from Service Quotas and recorded with its Region.

**Re-baselining analytical quality**

- [ ] **AC-0312.** Spike 4's A/B comparison is re-run under the new stack against the recorded 10-Q fixture, labelled with its producer tuple, and recorded against the same three loss categories the original reported.
- [ ] **AC-0313.** The re-run records what the narrowed admitted set costs separately from what the quarantine boundary costs.

**Saying what Phase 1 did not establish**

- [ ] **AC-0314.** The Phase 1 record names, for each measurement, the platform substitution behind it and the property a deployed fleet would establish that this one does not. It also names these five residuals, each of which is a control this delivery specified and did not fully close:

  1. **Both `app_api` and `app_worker` retain a table-level `UPDATE ON runs`** — `0001_base_schema.py:228-229` grants it to each, and its own comment says so — so a direct write from either still reaches a terminal run with nothing in the log saying so. AC-0320 establishes only that the intended path cannot do it. **`app_api` is the role serving the unauthenticated HTTP surface**, so recording only the worker's copy of this bypass, as an earlier revision did, understates it in the one place Phase 2 will read.
  2. **The approval-grant path is unfenced.** AC-0324 substitutes three structural predicates for possession because no one holds the lease while a human decides, which makes r8 § 4 line 461's ratified "fence proves possession" invariant untrue for `approval.granted` and `approval.rejected`.
  3. **The recorded approver principal is unauthenticated.** AC-0303 establishes what the log stored, not who approved.
  4. **p99 rests on a floor of 30 samples**, at which the 99th percentile is the largest or second-largest observation rather than a tail estimate — and AC-0308 multiplies it by three.
  5. **No vulnerability scanner covers either dependency tree.** `ui/`'s packages join a Python tree that already had none.
  6. **The approve/reject cycle cap ships at r5's arbitrary three**, bounded but not calibrated.

  A record that lists results and names no substitution fails this criterion; so does one that names the platform substitutions and drops the six above.

## Follow-ons

- eugenelim: `runtime-architecture.md` § 6 Deployment and Operations — AWS deployment to ECS Fargate. § 6 sizes the services; the load balancer and OIDC authentication at the ingress are § 2 and § 4. Its IaC and the mandatory infra security review are recorded nowhere upstream and rest on the owner's decision of 2026-09-18, which put the deployment out of scope. AC-0314 is the record of what that deployment would establish and this delivery does not.
- eugenelim: **who approved a publication — the recording is closed, the attribution is not.** AC-0303 now asserts the grant event names the granting principal and that the `require_distinct_approver` state is recoverable, which was the half no criterion in any Phase 1 spec carried. It does not establish *who approved*: `principal` is a caller-supplied string, this Phase authenticates nobody, and r8 puts OIDC at the ingress by a deferral recorded in `walking-skeleton-policy-decision-point` § Follow-ons. **An earlier revision of this entry said the gap was closed, which overclaimed** — § Always do requires recording what a check does not establish alongside what it does, and that correction is why AC-0314 now names the unauthenticated attribution among its residuals. What remains owed is an authenticated subject at the ingress, which closes this and the sibling entry together.
- eugenelim: **the cycle cap's number is still arbitrary.** AC-0321 now requires the cap to exist and its configuration to carry a finite default, which it did not before — nothing in `src/` implemented a cap at any value. What AC-0321 does *not* do is replace the number: r5 lines 619–622 ask Phase 1 to substitute an observed one, and this skeleton runs too few approval cycles to observe anything. The cap ships at r5's three, bounded and unmeasured, and the number is owed to the first delivery that runs enough cycles to earn one.
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
