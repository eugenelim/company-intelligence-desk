# Spec: Walking skeleton — the run state machine

- **Status:** Draft <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0003](../../adr/0003-repository-layout.md)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § 3 Runtime Model, § 10 Rollout Phase 1
- **Discovery:** none
- **Contract:** [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml) — gains the approval-decision operation; created by the foundation spec
- **Shape:** mixed

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Boundaries`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Objective`, `Durable Outputs`, `Follow-ons` and `Assumptions`
> are working material, corrected in place without an amendment.

## Objective

A run moves through its states and reaches publication, and the log says so at
every step.

Five specs built the pieces a run is made of — the event log, the compiled
agent, the containment fragment, the decision point, the provider call and
persistence. **Nothing moves a run between states.** `runs.state` is read by
`append_run_event`'s terminal guard and by the pool's heartbeat, and written by
no code at all; `run.completed` cannot be appended by any identity; and the
approval grant r5 places between the lease release and the re-claim has no
writer, because the fence it would need proves a possession nobody holds by
then.

This spec builds that layer: the transitions, the two append paths they need,
the interface a person releases a suspension through, and the two spend and
loop controls that bound it.

**Why it is separate.** This work and the Phase 1 measurements were one spec
until 2026-09-27. Four pre-EXECUTE review rounds found the measurement,
re-baseline and record tasks converging and this layer failing repeatedly, in
the same shape each time: a criterion asserting an outcome no shipped path can
produce. Three separate criteria had to grow a new append path once the review
reached them. Splitting lets this layer be specified against the privilege
split it actually has to cross, instead of rediscovering that boundary one
criterion at a time.

**Its sibling.** [`walking-skeleton-evidence`](../walking-skeleton-evidence/spec.md)
depends on this spec: its p99 needs completed steps that only publication
produces, and its browser criteria need the terminal event that closes a stream.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Schema | Applicable — the state machine needs two append paths, a durable counter and one narrowing the shipped privilege split has no room for | `migrations/versions/` | work-loop | One revision with five parts: the run-terminal path, the approval-decision path, `steps.approval_cycles`, their `EXECUTE` grants, and a `CREATE OR REPLACE` of `append_step_event` carrying a widened refusal list | The revision applies both on a clean volume and on a database upgraded from 0002, the grant set stays disjoint under AC-0320 and AC-0324, and the `append_step_event` narrowing is stated rather than described as expand-only — **it removes a capability `app_worker` has today**, which is the safe direction and still a foundation-owned behaviour change |
| Recorded decisions | Applicable — two of this spec's choices deviate from a ratified document, and each is settled before the code it governs | `docs/adr/` | work-loop | An ADR for the approval gate's shipped run-time placement against r8 § 3, and one for the two append paths' acting identities against r8 § 4 | Each is cited from the criterion that rests on it, and neither is written after the build it justifies |
| Interface compatibility | Applicable — a person needs a way to grant or reject, and `contracts/openapi/runs.yaml` contracts three routes today | `contracts/openapi/runs.yaml` | work-loop | The approval-decision operation documented, and the committed route count moved from three to four | Contract and served routes agree under the shipped AC-0009 check |
| Current architecture | Applicable — `docs/architecture/README.md` § What is built records the run state machine as designed and not built | `docs/architecture/README.md` | work-loop | The row moved for what now exists, with the transitions this spec does **not** commit named rather than implied | The map matches the repository |
| User-facing promise | Not applicable — no surface ships here; the browser belongs to the sibling spec | — | — | — | — |

## Boundaries

### Always do

- Treat r8 and r5 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Record what a check does **not** establish alongside what it does.
- Before asserting that a path is the only one that can do something, check the shipped grant set and the shipped type rules. Three criteria in this spec's predecessor claimed exclusivity the schema did not have.

### Ask first

- Any change to a ratified decision, including which identity holds a new append path.
- Revoking or narrowing a grant revision 0001 records as taken verbatim from r7's identity table.
- Adding a dependency beyond those in the plan's § Dependencies & integration.

### Never do

- **No unconditional approval gate.** A clean run must reach publication with no human in the path.
- **No state change without its event.** A run that reached a terminal state with nothing in the log saying so is the failure this spec exists to make unreachable on the paths it builds.
- **No append path whose acting identity is chosen at the keyboard.**

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0302, AC-0320, AC-0321, AC-0324, AC-0325, AC-0327, AC-0330, AC-0331, AC-0332, AC-0333)** — the compressible invariants. AC-0320, AC-0324, AC-0327, AC-0330, AC-0332, AC-0333 and AC-0321's durability clause carry the `substrate` marker: a grant set and a transition are properties of the applied schema and of a real worker handoff, and an in-memory fixture would assert the migration's text rather than its effect.
- **End-to-end (AC-0301, AC-0303, AC-0328)** — a clean run reaching publication needs every layer beneath it, so neither can be written before the system it exercises.
- **Record review (AC-0329)** — checked by reading, because its subject is whether the record names what this delivery did not establish.

**Coverage signal.** Fourteen criteria. **Eight carry a validated red stub** — AC-0302, AC-0320, AC-0321, AC-0324, AC-0325, AC-0330, AC-0332, AC-0333. **Two record `no stub (implementation-discovered)`** with a discovery predicate and proof obligation — AC-0327, whose projection seam T2 designs, and AC-0331, whose probe invocation the healthcheck fixes. **Four record `no stub (mode)`** — AC-0301, AC-0303 and AC-0328 are end-to-end, AC-0329 is record review. Every TDD-group criterion carries one of the two dispositions `tdd-stubs.md` admits; an earlier revision filed AC-0324 under `no stub (mode)` with a reason that is neither.

## Acceptance Criteria

Obligations come from `runtime-architecture.md` § 3 Runtime Model (the state
table and the approval gate) and § 10 Rollout's Phase 1 exit criterion "confirm
a clean run publishes with zero human interaction", and from
`worker-runtime.md` § 10 criteria 1 and 4. Criteria **beyond** those sources
are tabled below.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Assert the surface the approval gate is decidable on | AC-0302 | A run can complete cleanly while a gated tool it never triggered still sits in the stack | The check protecting a ratified charter amendment is satisfied by a run that happened not to trigger it |
| Drive the flagged branch, and record who released it | AC-0303 | No named source covers the branch where a check fails and a person releases it; r8 lines 406–407 require the approver principal be recorded and no Phase 1 spec asserted it | The approval gate ships exercised only in the branch that never reaches it |
| Fix the identity on each new append path | AC-0320, AC-0324 | r8 § 4 line 460 and § 3 line 344 disagree about which role may write a run-lifecycle type, and a function-level disjointness check stays green whichever role gets a new path | The privilege split widens by whichever shortcut the implementer reaches first |
| Observe the cycle cap and the spend ceiling | AC-0321, AC-0325 | Both are ratified controls that nothing in `src/` implements, and both were dispositioned "lands" with no criterion reading them | Two spend and loop controls ship recorded as delivered while nothing reads them |
| Commit the transitions a reader can see | AC-0327 | `read_snapshot` returns `runs.state` verbatim, so a run that never leaves `requested` until it reaches `completed` is what every reader sees | The state column stays a field nothing writes, which is what this spec exists to change |
| Give the approver a way to act | AC-0328 | AC-0303's grant is otherwise issued from a test connection, satisfying the criterion by a path no operator can reach | The approval gate is demonstrated against a caller that does not exist |
| Say what this delivery did not establish | AC-0329 | Three controls here are narrower than the invariant they touch, and a record that lists results and names no residual overclaims | The next spec inherits a state machine that looks finished |

**Running to publication**

- [ ] **AC-0301.** A run whose pre-release checks all pass reaches `completed` and publishes its typed artifact — asserted as the artifact's `payload_ref` resolving to a readable object in the store, not as `run.completed` alone — and **appends no `step.suspended` event**, which is the type this system actually writes when a run suspends.

  An earlier revision asserted the absence of `approval.requested`. That type exists nowhere in the repository and no task creates it, so the clause was true for every possible implementation including one whose gate was unconditional — the vacuity shape AC-0302 exists to catch, sitting undetected in the criterion beside it.
- [ ] **AC-0302.** A run whose pre-release checks all pass presents the agent with **no callable approval-gated tool**, asserted on the tool set the model is offered at run time rather than inferred from the run's outcome.

  The shipped placement builds the approval tool as a run-time `FunctionToolset` passed through `toolsets=[…]`, never compiling it in, so a criterion reading the *compiled* toolset is true in every possible world. r8 § 3 lines 400–403 describes the other placement; the shipped one stands by owner decision of 2026-09-26 because it keeps approval outside the decision point's ceiling check, and T0's ADR records the deviation.
- [ ] **AC-0303.** A run whose pre-release checks fail suspends for approval, releases its lease, and resumes to publication after a grant issued through AC-0328's interface. Suspension is deterministic because the role under test resolves to a model that calls `request_approval` on every flagged run. The grant event names the granting principal, and the `require_distinct_approver` state in force is recoverable from the log — asserted by configuring the flag **both ways** and reading back two different appended values, so a module constant cannot satisfy it.

  **What this does not establish.** `principal` is a caller-supplied string and this Phase authenticates nobody, so the read-back separates what the log stored from what the test asserted, and establishes nothing about who actually approved. AC-0329 records that.

**The transitions, and who may write them**

- [ ] **AC-0327.** Each run-state move this spec commits is **written together with its event, in one transaction**, and the ordered projection of those events reproduces the state sequence a reader saw. Asserted from the committed event log, and additionally that `GET /runs/{run_id}/snapshot` agrees with the projection at each committed point.

  **The committed set is exactly the edges the tree has an event for.** `claimed→running` on `step.started`; `awaiting_approval→running` on `step.resumed`; `running→completed` on `run.completed` through AC-0320's path; and `any non-terminal→failed` on `run.failed` through the same path, for the two causes this spec produces — AC-0321's cap and AC-0330's refused resume.

  **Two edges r8 names are deliberately not committed, and the reason is not scope.** r8 § 3 maps `requested→claimed` to `run.claimed` and `running→awaiting_approval` to `approval.requested`. **Neither event type exists anywhere in this repository** — not in `src/`, `tests/`, `migrations/` or `contracts/` — no shipped path appends one, and `append_run_event` admits only `run.requested` and `run.cancelled`. Committing those edges would mean inventing two event types and a path to append them, which is an event-vocabulary decision above this spec's authority. **Owner decision 2026-09-27: this spec commits only what the tree can express**, and AC-0329 records r8's vocabulary gap as owed rather than silently papering over it. The consequence a reader sees is stated rather than hidden: a run stays reported `requested` until its first step starts, and a suspended run's `awaiting_approval` is inferred from `step.suspended` rather than from a run-state move.

  **Determinism.** The projection is the oracle; snapshot polling against a concurrent worker can miss a state a correct build genuinely entered, so the snapshot agreement is checked only at points the projection already fixes.

- [ ] **AC-0320.** The append path that carries `run.completed` and `run.failed` is granted to **`app_worker` and to no other role**, and on that path the `runs.state` change and the terminal event commit together or not at all: with the append forced to fail, the state does not move. The path enforces these predicates, each asserted by a call that violates it: it proves lease possession **through the shipped `fence_step`**, not a hand-rolled epoch comparison; it admits only the two types named above; it refuses a `step_id` whose step does not belong to the run; it refuses a run already terminal; and **it refuses a source state outside the set AC-0327 commits**, so a run still at `requested` cannot jump to `completed`. It also writes `step_id` null — an output the append carries, not a predicate a call can violate, and named separately for that reason. An earlier revision said "six predicates" over a list of five, which is why this one enumerates and does not tally.

  **What it does not claim.** `0001_base_schema.py:228-229` grants a table-level `UPDATE ON runs` to `app_api` and `app_worker` alike, and both grants stay — that file records them as r7's identity table verbatim and declines to narrow them unilaterally. A direct `UPDATE` therefore still reaches a terminal run with nothing in the log saying so; this criterion establishes only that the intended path cannot. AC-0329 records it.
- [ ] **AC-0324.** The append path that carries `approval.granted` and `approval.rejected` is granted to **`app_api`**, and it enforces five predicates, each asserted by a call that violates it: it admits only those two types; it refuses a `step_id` whose step does not belong to the run being written; **it refuses a step that does not already carry a committed `step.suspended` event**, which only the worker's fenced path can append; and it refuses a step whose suspension is not currently awaiting a decision — AC-0333's exclusion cleared, or never set — which is what makes a replayed or pre-emptive decision refusable without the request having to name a cycle at all. The cycle is read from the step, never from the caller.

  **The predicate is the event, not the step's state — and the step's state does not change.** An earlier revision refused "a step that is not suspended", a guard that could never fire because nothing writes `steps.state = 'suspended'`. The repair for *that* was worse: it had T2 write the state, which **contradicts the shipped AC-0237** — `walking-skeleton-step-lifecycle` releases the lease on suspension precisely so a *different* worker resumes — and strands the step, because the claim predicate at `src/ced/worker/pool.py:429-431` admits only `runnable` or an expired `leased` row and nothing would move it back. The suspension path keeps writing `runnable`, unchanged. What it gains is the `step.suspended` event, appended on the worker's own fenced path while it still holds the lease, which is the one fact `app_api` cannot manufacture: it holds no `EXECUTE` on `append_step_event`.

  **What that leaves open.** `app_api` holds `INSERT ON steps`, so it can still insert a step into any run and let a worker claim, suspend and stamp it, then commit a decision against it. The exclusivity is over the *type*, not over causation, and AC-0329 records the deputy path rather than the criterion claiming a reach it does not have.

  **Why `app_api`, and the denylist.** The approver acts through the API and the lease is released before they do; that **deviates from r8 § 4 line 460**, and T0's ADR records it. Exclusivity is stated at the type because `append_step_event` refuses types by **denylist**, so `approval.granted` is admitted on the path `app_worker` holds. Revision 0005 closes that with a `CREATE OR REPLACE`, guarded by AC-0332, and AC-0324's refusal is asserted **against a database upgraded from 0002**, not only a freshly built one.

- [ ] **AC-0332.** After revision 0005, exactly one `append_step_event` exists, carrying the owner, the `SECURITY DEFINER` attribute and the pinned `SET search_path` revision 0002 gave it, with an `EXECUTE` grant set unchanged from 0002 and excluding `PUBLIC`. **The replaced body still refuses what it refused before**: an unfenced call, each type in the pre-existing refusal list, and a non-canonical type — each driven by a call that violates it. Asserted on a database upgraded from 0002.

  The preservation half matters more than the addition. `CREATE OR REPLACE` re-specifies the entire definition, so a replacement that silently drops the `fence_step` call would let `app_worker` append step events for steps it does not hold — falsifying r8 § 4 line 461 across the whole shipped step vocabulary, not merely the two types this spec touches — and AC-0320 and AC-0324 would not see it, because they exercise the two *new* functions.

  `CREATE OR REPLACE` re-specifies the whole definition, so a replacement dropping the search-path clause reintroduces a definer-function search-path hazard, and any drift in the eight-argument signature creates a **second overload** rather than replacing — a newly created function carrying the default `EXECUTE TO PUBLIC` that revision 0002 had to revoke explicitly. Either would hand `app_api` the ability to commit a `step.suspended` and collapse the one predicate AC-0324 rests on, so the criterion guarding the guard is not optional.

- [ ] **AC-0330.** A resume reads the step's committed approval decision **for the step's current cycle** and maps it **per deferred call** to the framework's approval result, asserted by cases whose outcomes differ: a committed grant for this cycle lets that call proceed; a committed rejection denies it and the call does not execute; and a resume whose step is no longer awaiting a decision, yet carries none for this cycle, **refuses to run** — a state reachable only through data loss or a defect, because AC-0333 keeps an undecided step unclaimed.

  **What a refusal leaves behind.** The step fails with a recorded cause and the run moves to `failed` through AC-0320's path — one of the two causes AC-0327 commits that edge for — so a reader never sees a live run whose only step is dead. It does **not** release the step back to `runnable`, because that would loop.

  **The refusal is terminal for the attempt and recorded.** A refused resume fails the step with a recorded cause rather than releasing it back to `runnable`, so a poll loop cannot re-claim, refuse and release indefinitely — a churn that would write events and consume leases forever. Asserted by a repeated-poll case that does not loop.

  The shipped resume path does none of this: `src/ced/worker/persistence.py:98` reads `approval_map = {call_id: True for call_id in pending_call_ids}`, and no reader of `approval.granted` or `approval.rejected` exists anywhere in `src/`. **The per-call clause matters as much as the per-cycle one**: a suspension can carry several pending call ids and AC-0328's request authorizes one decision, so without it a single human action approves every deferred call in the payload, including ones never shown to the approver. It is unreachable today only because `resume_step` has no caller outside a test harness, and T2 is the task that wires it into the pool.

- [ ] **AC-0333.** A step whose latest suspension has no committed decision is **not claimed**: the claim predicate excludes it, and the decision path clears the exclusion in the same transaction that appends the decision. Asserted by three cases — a suspended, undecided step is not returned by a claim while an ordinary runnable step beside it is; the same step is claimable once a decision commits; and a worker polling repeatedly against the undecided step appends nothing and consumes no lease.

  **The exclusion is a column, not a step state, and that is the whole point.** Writing `steps.state = 'suspended'` strands the step — the claim predicate admits only `runnable` or an expired `leased`, so nothing would ever move it back — and it contradicts the shipped AC-0237, which makes lease release how a *different* worker resumes. Leaving the step plainly `runnable` is the opposite failure: the next poll re-claims it within `POLL_SECONDS`, long before a human acts, and AC-0330's refusal then kills the run. **Both were tried in earlier revisions of this spec and both were wrong.** A boolean the decision path clears keeps the row `runnable`, keeps AC-0237 true, and makes AC-0330's refusal reachable only when a decision is genuinely absent rather than merely not yet made.

  `steps.approval_cycles` and this exclusion are written by the same two paths and nowhere else: the worker's fenced suspension append sets the exclusion and leaves the counter, and AC-0324's decision path clears the exclusion and advances the counter. AC-0324's predicates read both.

- [ ] **AC-0328.** A person grants or rejects a suspended step through a documented operation on the shipped API. The request body carries a decision from a two-value set **per pending call id**, and a principal bounded at the repository's existing `ATTRIBUTION_MAX_LENGTH` seam; a body naming a call id the step does not currently have pending, or omitting one it does, is refused before any append. It carries **no cycle** — AC-0324 reads that from the step, so a caller cannot name one. A request whose `Origin` header names anything but the API's own origin is refused, **and so is one carrying no `Origin` at all**. The operation is documented in `contracts/openapi/runs.yaml` and the shipped contract-agreement check reads it.

  **On the route count.** This criterion does not assert a global total, because the sibling spec adds an operation too and whichever lands first would falsify the other's number. It asserts that *this* operation is contracted and served; the total and the `test_the_contract_file_describes_three_routes` value are the last-landing spec's to set.

  **On the origin refusal.** It is CSRF defence, not authorization: a non-browser caller forges `Origin` as easily as it omits it, and this Phase authenticates nobody by ratified deferral. It is stated here rather than borrowed from the sibling's AC-0326 because that spec *depends on this one* and so ships later — this operation would otherwise be the first state-changing verb on the API with no stated posture at all. AC-0329 records that it bounds a browser and not a process.

**Bounding the loop and the spend**



- [ ] **AC-0321.** A step sent back for revision more times than the cap allows fails with a recorded cause rather than looping, and the run moves to `failed` — the one non-terminal→`failed` edge AC-0327 commits, so a capped run does not sit reported as `running` forever. The count is read from `steps.approval_cycles` and **survives a worker handoff**, asserted by driving the cycles across one rather than within a single process. The cap's configuration is `PoolConfig` and carries a **finite default**, so a deployment setting no value still gets a bounded loop.

  r5 line 607 fixes the loop at three cycles and lines 619–622 call the number arbitrary, asking Phase 1 to replace it with an observed one. Too few cycles run here to observe anything, so the cap ships at three, bounded and uncalibrated, and AC-0329 says so.
- [ ] **AC-0325.** With usage already accumulated in the event log past the configured per-run ceiling, the executor's check before dispatching the next step **pages rather than aborting**, and the page is a step-scoped event appended through the worker's fenced path on the step the worker holds when the check runs.

  **This criterion is exercised against a fabricated multi-step run, and that is recorded rather than hidden.** A run in this system gets exactly one step — `src/ced/adapters/postgres/event_log.py` inserts the run, its single coordinator step and `run.requested` together, and nothing under `src/` inserts a second — so "before dispatching the next step" names a moment no producible run reaches today. The control is built and asserted because r5 ratifies it and the planner that creates child steps is a later spec's; AC-0329 records that it ships unexercised by any real run. The ceiling's configuration is `PoolConfig` and carries a **finite default**.

  r5 lines 1255–1257 ratify the paging behaviour, because for a single operator killing a legitimate long analysis is the worse error. The event is step-scoped deliberately: a run-scoped page would need a third new append path, and the worker holds a lease at pre-dispatch time, so the shipped fenced path already carries it.

- [ ] **AC-0331.** The worker's liveness probe fails when no heartbeat has been *attempted* within twice the lease TTL, asserted by stalling the poll loop without killing the process and observing the probe report unhealthy. A probe that only checks process existence passes that case, which is the failure mode DR4 exists to catch.

  It is a worker-side command the container healthcheck runs, **not an HTTP route**: an out-of-process probe is what DR4 asks for, since a probe inside the loop it watches cannot see that loop starve, and an API route would put a further operation on a surface AC-0328 already adds one to. T2 gated on this behaviour before this criterion existed, which is a plan asserting what no contract stated.

**Saying what this did not establish**

- [ ] **AC-0329.** The record names each of these, every one a control this spec specified and did not fully close. The gate is the list, not its length:

  - **r8 § 3 names two events this system has never emitted.** `run.claimed` and `approval.requested` exist nowhere in the repository, so AC-0327 commits neither `requested→claimed` nor `running→awaiting_approval`. A reader therefore sees `requested` until the first step starts, and infers a suspension from `step.suspended` rather than from a run-state move. Settling that vocabulary is owed to an architecture revision, not to a spec.
  - **Both `app_api` and `app_worker` retain a table-level `UPDATE ON runs`**, so a direct write still moves a run's state with nothing in the log.
  - **The approval-decision path is unfenced.** r8 § 4 line 461's ratified "the fence proves possession" is untrue for `approval.granted` and `approval.rejected`; the committed `step.suspended` and AC-0333's exclusion are the substitute.
  - **AC-0324's exclusivity is over the event type, not over causation.** `app_api` retains `INSERT ON steps`, so it can insert a step into any run, let a worker claim and suspend it, and decide against a step it caused to exist.
  - **The recorded approver principal is unauthenticated**, AC-0328's origin refusal bounds a browser and not a process, and the attribution is retained for the life of the event log with no erasure path.
  - **The approver decides blind.** No surface in this delivery shows them the pending calls; `step.suspended` carries a `payload_ref` and the arguments live in the object store behind it.
  - **The per-run spend ceiling is exercised against a fabricated multi-step run**, because a real run has exactly one step, and its finite default is unsourced — as is the cycle cap's three.
  - **Revision 0005 re-issues a foundation-owned function.** The `append_step_event` replacement narrows what `app_worker` may append; AC-0332 guards what it preserves.

## Follow-ons

- eugenelim: **the r9 consistency pass.** r8 § 4 line 460 and § 3 line 344 disagree about whether the worker may write a run-lifecycle type, and § 4 line 461's possession invariant is made untrue for two event types here. ADRs record the deviations; they do not amend r8.
- eugenelim: **`awaiting_input` and `expired` are authored and unexercised.** The first spec to wire the input tool owes r8 § 3's two safety constraints with it — the answer admitted at the acting role's existing ceiling, and the request and answer both recorded.
- eugenelim: **the cycle cap's number is still arbitrary**, owed to the first delivery that runs enough cycles to earn one. **The per-run spend ceiling's default is unsourced on the same terms** — r5 ratifies that it pages and fixes no value — and is owed to the first delivery with real spend data, which is the sibling spec's measurements.

## Assumptions

- Technical: nothing writes `runs.state` today and no identity can append `run.completed`; both were verified against `migrations/versions/0002_append_paths_and_privilege_split.py` and a content search of `src/` on 2026-09-27.
- Technical: `append_step_event` refuses types by denylist, so `approval.granted` is admitted on it today — verified by executing the migration module's `NON_STEP_EVENT_TYPES` on 2026-09-27.
- Governance: r8 disagrees with itself on which role may write a run-lifecycle type; ratified means implemented, not reconciled, and this spec takes § 3's reading under an ADR.
- Process: eugenelim approves both gates. **This is self-approval, labelled rather than presented as review**; what independent scrutiny these artifacts have came from forked-context reviewer agents.
