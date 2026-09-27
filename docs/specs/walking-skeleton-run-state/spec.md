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

- **TDD (AC-0302, AC-0320, AC-0321, AC-0324, AC-0325, AC-0327, AC-0330, AC-0331)** — the compressible invariants. AC-0320, AC-0324, AC-0327, AC-0330 and AC-0321's durability clause carry the `substrate` marker: a grant set and a transition are properties of the applied schema and of a real worker handoff, and an in-memory fixture would assert the migration's text rather than its effect.
- **End-to-end (AC-0301, AC-0303, AC-0328)** — a clean run reaching publication needs every layer beneath it, so neither can be written before the system it exercises.
- **Record review (AC-0329)** — checked by reading, because its subject is whether the record names what this delivery did not establish.

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

- [ ] **AC-0301.** A run whose pre-release checks all pass reaches `completed`, publishes its typed artifact, and appends no `approval.requested` event.
- [ ] **AC-0302.** A run whose pre-release checks all pass presents the agent with **no callable approval-gated tool**, asserted on the tool set the model is offered at run time rather than inferred from the run's outcome.

  The shipped placement builds the approval tool as a run-time `FunctionToolset` passed through `toolsets=[…]`, never compiling it in, so a criterion reading the *compiled* toolset is true in every possible world. r8 § 3 lines 400–403 describes the other placement; the shipped one stands by owner decision of 2026-09-26 because it keeps approval outside the decision point's ceiling check, and T0's ADR records the deviation.
- [ ] **AC-0303.** A run whose pre-release checks fail suspends for approval, releases its lease, and resumes to publication after a grant issued through AC-0328's interface. Suspension is deterministic because the role under test resolves to a model that calls `request_approval` on every flagged run. The grant event names the granting principal, and the `require_distinct_approver` state in force is recoverable from the log — asserted by configuring the flag **both ways** and reading back two different appended values, so a module constant cannot satisfy it.

  **What this does not establish.** `principal` is a caller-supplied string and this Phase authenticates nobody, so the read-back separates what the log stored from what the test asserted, and establishes nothing about who actually approved. AC-0329 records that.

**The transitions, and who may write them**

- [ ] **AC-0327.** Each run-state move this spec commits is **written together with its event, in one transaction**, and the ordered projection of those events reproduces the state sequence a reader saw. Asserted from the committed event log rather than from timed snapshot reads, and additionally that `GET /runs/{run_id}/snapshot` agrees with the projection at each committed point.

  **The committed set, enumerated rather than counted.** `requested→claimed`, `claimed→running`, `running→awaiting_approval`, `awaiting_approval→running`, and `running→completed`. Every one ends in an append, and no path in this spec writes a run state without one — which is what makes the projection an oracle instead of a second copy of the same guess.

  **Not committed, and why.** `awaiting_approval→completed`: a grant resumes *through* `running` under AC-0303, so nothing this spec builds writes that edge — AC-0324's decision path moves no run state and AC-0320's terminal path is the worker's. `awaiting_input→running` and `running→awaiting_input`: no role calls the input tool. `awaiting_approval→expired` and `expired→awaiting_approval`: `approval_timeout` defaults to none, so nothing expires. `any non-terminal→cancelled`: the cancel path has no caller until the sibling spec measures cancellation. `any non-terminal→failed` **is** committed, but only for the cause AC-0321 fires; other failure causes are not. AC-0329 names this list rather than a tally, because a count drifts from what it counts and an earlier revision of this criterion said "eleven" of a table with thirteen rows and "five" of a list with six.

  **Determinism.** Snapshot polling against a concurrent worker can miss a state that was genuinely entered, which would red a correct build. The projection is the oracle; the snapshot agreement is checked at points the projection already fixes.

- [ ] **AC-0320.** The append path that carries `run.completed` and `run.failed` is granted to **`app_worker` and to no other role**, and on that path the `runs.state` change and the terminal event commit together or not at all: with the append forced to fail, the state does not move. The path enforces six predicates, each asserted by a call that violates it — it proves lease possession **through the shipped `fence_step`**, not a hand-rolled epoch comparison; it admits only the two types named above; it refuses a `step_id` whose step does not belong to the run; it refuses a run already terminal; and it writes `step_id` null.

  **What it does not claim.** `0001_base_schema.py:228-229` grants a table-level `UPDATE ON runs` to `app_api` and `app_worker` alike, and both grants stay — that file records them as r7's identity table verbatim and declines to narrow them unilaterally. A direct `UPDATE` therefore still reaches a terminal run with nothing in the log saying so; this criterion establishes only that the intended path cannot. AC-0329 records it.
- [ ] **AC-0324.** The append path that carries `approval.granted` and `approval.rejected` is granted to **`app_api`**, and it commits while no worker holds the step. It enforces five predicates, each asserted by a call that violates it: it admits only those two types; it refuses a `step_id` whose step does not belong to the run being written; **it refuses a step that does not already carry a committed `step.suspended` event**, which only the worker's fenced path can append; it refuses a step whose `owner` is non-null, so a decision cannot land while a worker holds the lease; and it refuses a decision when `steps.approval_cycles` already records one for the current cycle, so a retried call is refused while the next legitimate cycle is admitted.

  **The suspended-event predicate replaces a dead one, and the reason matters.** An earlier revision of this criterion refused "a step that is not suspended" — a guard that could never fire, because **nothing in the tree ever writes `steps.state = 'suspended'`**: the shipped suspension path at `src/ced/worker/executor.py:402-413` sets `state = 'runnable'`, and `'suspended'` survives only as an admitted value of the CHECK. Worse, the structural predicates were self-satisfiable by the very role the path is granted to: `app_api` holds `INSERT ON steps` and `INSERT, UPDATE ON runs`, so it could manufacture a row satisfying every one of them and commit a grant into an arbitrary run's log. A committed `step.suspended` event is the one predicate `app_api` cannot construct, because it holds no `EXECUTE` on `append_step_event`.

  **T2 therefore changes the suspension path**, which is a correctness fix this spec owes and not a convenience: a step that suspends into `runnable` is immediately re-claimable by any worker *before the approver has acted at all*, so the gate does not merely fail to check a decision, it does not wait for one. Suspension writes `steps.state = 'suspended'` with its `step.suspended` event in one transaction, and AC-0330's resume is what returns it to `runnable`.

  **Why `app_api`, and what it costs.** The approver acts through the API and the lease is released before they do. That **deviates from r8 § 4 line 460**, which limits `api` to run-lifecycle types while these two are step-scoped; T0's ADR records it. Exclusivity is stated at the *type* and not the function, because `append_step_event` refuses types by **denylist** — so `approval.granted` is admitted on the path `app_worker` holds and a function-level claim would assert a property the grant set does not have. Revision 0005 closes that by replacing `append_step_event`, and the criterion asserts the refusal **against a database upgraded from 0002, not only a freshly built one**: the constant is rendered into the function body at creation time, so editing it would leave every existing database unchanged while the `substrate` suite went green on a clean volume.

  **What still stands in for possession.** Nothing proves it — by construction nobody holds the lease. The committed-`step.suspended` predicate plus the null-`owner` check are the substitute, and they are weaker than the fence r8 § 4 line 461 ratifies as *Built*. AC-0329 records it.

- [ ] **AC-0330.** A resume reads the step's committed approval decision from the event log and maps it to the framework's approval result, asserted by three cases whose outcomes differ: a committed `approval.granted` lets the deferred call proceed; a committed `approval.rejected` denies it and the call does not execute; and **a resume with no committed decision refuses to run at all**.

  The shipped resume path does none of this. `src/ced/worker/persistence.py:98` reads `approval_map = {call_id: True for call_id in pending_call_ids}` — every pending call approved, unconditionally — and a content search of `src/` finds no reader of `approval.granted` or `approval.rejected` anywhere. It is unreachable today only because `resume_step` has no caller outside a test harness, and **T2 is the task that wires it into the pool**, which is precisely when a decorative gate becomes a live bypass. Without this criterion AC-0302 and AC-0303 both stay green over a resume that rubber-stamps whatever the model asked for.

- [ ] **AC-0328.** A person grants or rejects a suspended step through a documented operation on the shipped API. The request body's decision is one of exactly two values and its principal is bounded at the repository's existing `ATTRIBUTION_MAX_LENGTH` seam, with an out-of-schema body refused before any append. A request whose `Origin` header names anything but the API's own origin is refused, **and so is one carrying no `Origin` at all**. The operation is documented in `contracts/openapi/runs.yaml` and the shipped contract-agreement check reads it.

  **On the route count.** This criterion does not assert a global total, because the sibling spec adds an operation too and whichever lands first would falsify the other's number. It asserts that *this* operation is contracted and served; the total and the `test_the_contract_file_describes_three_routes` value are the last-landing spec's to set.

  **On the origin refusal.** It is CSRF defence, not authorization: a non-browser caller forges `Origin` as easily as it omits it, and this Phase authenticates nobody by ratified deferral. It is stated here rather than borrowed from the sibling's AC-0326 because that spec *depends on this one* and so ships later — this operation would otherwise be the first state-changing verb on the API with no stated posture at all. AC-0329 records that it bounds a browser and not a process.

**Bounding the loop and the spend**

- [ ] **AC-0321.** A step sent back for revision more times than the cap allows fails with a recorded cause rather than looping, and the run moves to `failed` — the one non-terminal→`failed` edge AC-0327 commits, so a capped run does not sit reported as `running` forever. The count is read from `steps.approval_cycles` and **survives a worker handoff**, asserted by driving the cycles across one rather than within a single process. The cap's configuration is `PoolConfig` and carries a **finite default**, so a deployment setting no value still gets a bounded loop.

  r5 line 607 fixes the loop at three cycles and lines 619–622 call the number arbitrary, asking Phase 1 to replace it with an observed one. Too few cycles run here to observe anything, so the cap ships at three, bounded and uncalibrated, and AC-0329 says so.
- [ ] **AC-0325.** With usage already accumulated in the event log past the configured per-run ceiling, the executor's check before dispatching the next step **pages rather than aborting**, and the page is a step-scoped event appended through the worker's fenced path **on the step the worker currently holds a live lease on** — the one whose completion triggered the check — not on a step not yet claimed, which `fence_step` would refuse for want of an owner. The ceiling's configuration is `PoolConfig` and carries a **finite default**.

  r5 lines 1255–1257 ratify the paging behaviour, because for a single operator killing a legitimate long analysis is the worse error. The event is step-scoped deliberately: a run-scoped page would need a third new append path, and the worker holds a lease at pre-dispatch time, so the shipped fenced path already carries it.

- [ ] **AC-0331.** The worker's liveness probe fails when no heartbeat has been *attempted* within twice the lease TTL, asserted by stalling the poll loop without killing the process and observing the probe report unhealthy. A probe that only checks process existence passes that case, which is the failure mode DR4 exists to catch.

  It is a worker-side command the container healthcheck runs, **not an HTTP route**: an out-of-process probe is what DR4 asks for, since a probe inside the loop it watches cannot see that loop starve, and an API route would put a further operation on a surface AC-0328 already adds one to. T2 gated on this behaviour before this criterion existed, which is a plan asserting what no contract stated.

**Saying what this did not establish**

- [ ] **AC-0329.** The record names these residuals, each a control this spec specified and did not fully close:

  1. **Both `app_api` and `app_worker` retain a table-level `UPDATE ON runs`**, so a direct write still moves a run's state with nothing in the log. AC-0320 and AC-0327 establish only that the paths this spec builds cannot.
  2. **The approval-decision path is unfenced**, so r8 § 4 line 461's ratified "the fence proves possession" is untrue for `approval.granted` and `approval.rejected`. A committed `step.suspended` and a null `owner` are the substitute.
  3. **`app_api` retains `INSERT ON steps`**, so it can still create step rows; what it cannot do is make one carry a committed `step.suspended`, which is why AC-0324 rests on that event rather than on the row's own fields.
  4. **The recorded approver principal is unauthenticated**, and AC-0328's origin refusal bounds a browser rather than a process, so neither establishes who approved.
  5. **The cycle cap ships at r5's arbitrary three**, and **the per-run spend ceiling's finite default is equally unsourced** — r5 ratifies that it pages and fixes no number.
  6. **The transitions this spec does not commit**, named as the list AC-0327 enumerates rather than as a count: `awaiting_approval→completed`, both `awaiting_input` edges, both `expired` edges, cancel-from-non-terminal, and every `failed` cause but the cap's. The safety constraints r8 § 3 attaches to `awaiting_input` are owed with it.

  A record that lists results and drops any of the six fails this criterion.

## Follow-ons

- eugenelim: **the r9 consistency pass.** r8 § 4 line 460 and § 3 line 344 disagree about whether the worker may write a run-lifecycle type, and § 4 line 461's possession invariant is made untrue for two event types here. ADRs record the deviations; they do not amend r8.
- eugenelim: **`awaiting_input` and `expired` are authored and unexercised.** The first spec to wire the input tool owes r8 § 3's two safety constraints with it — the answer admitted at the acting role's existing ceiling, and the request and answer both recorded.
- eugenelim: **the cycle cap's number is still arbitrary**, owed to the first delivery that runs enough cycles to earn one. **The per-run spend ceiling's default is unsourced on the same terms** — r5 ratifies that it pages and fixes no value — and is owed to the first delivery with real spend data, which is the sibling spec's measurements.

## Assumptions

- Technical: nothing writes `runs.state` today and no identity can append `run.completed`; both were verified against `migrations/versions/0002_append_paths_and_privilege_split.py` and a content search of `src/` on 2026-09-27.
- Technical: `append_step_event` refuses types by denylist, so `approval.granted` is admitted on it today — verified by executing the migration module's `NON_STEP_EVENT_TYPES` on 2026-09-27.
- Governance: r8 disagrees with itself on which role may write a run-lifecycle type; ratified means implemented, not reconciled, and this spec takes § 3's reading under an ADR.
- Process: eugenelim approves both gates. **This is self-approval, labelled rather than presented as review**; what independent scrutiny these artifacts have came from forked-context reviewer agents.
