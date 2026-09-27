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
| Schema | Applicable — the state machine needs two append paths and a durable counter the shipped privilege split has no room for | `migrations/versions/` | work-loop | One expand-only revision adding the run-terminal path, the approval-decision path, `steps.approval_cycles`, and their `EXECUTE` grants | The revision applies on a clean volume, revokes nothing, and the grant set stays disjoint under AC-0320 and AC-0324 |
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

- **TDD (AC-0302, AC-0320, AC-0321, AC-0324, AC-0325, AC-0327, AC-0328)** — the compressible invariants. AC-0320, AC-0324, AC-0327 and AC-0321's durability clause carry the `substrate` marker: a grant set and a transition are properties of the applied schema and of a real worker handoff, and an in-memory fixture would assert the migration's text rather than its effect.
- **End-to-end (AC-0301, AC-0303)** — a clean run reaching publication needs every layer beneath it, so neither can be written before the system it exercises.
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

- [ ] **AC-0327.** A run's state moves through `claimed`, `running` and — on the flagged branch — `awaiting_approval` and back, and each move is readable from `GET /runs/{run_id}/snapshot` at the moment it happens. Asserted by reading the snapshot between steps, not by reading the transition table.

  **Which transitions this spec commits, and which it does not.** r8 § 3's table has eleven rows. This spec commits `requested→claimed`, `claimed→running`, `running→awaiting_approval`, `awaiting_approval→running`, `awaiting_approval→completed` and `running→completed`. It does **not** commit `awaiting_input` and its two events, `expired` and its two, or `failed`/`cancelled` from a non-terminal state: no role calls the input tool, `approval_timeout` defaults to none so nothing expires, and the cancel path has no caller until the sibling spec measures it. Those five rows are authored in the transition table and unexercised, and AC-0329 names them.
- [ ] **AC-0320.** The append path that carries `run.completed` and `run.failed` is granted to **`app_worker` and to no other role**, and on that path the `runs.state` change and the terminal event commit together or not at all: with the append forced to fail, the state does not move. The path enforces five predicates, each asserted by a call that violates it — it proves lease possession **through the shipped `fence_step`**, not a hand-rolled epoch comparison; it admits only the two types named above; it refuses a `step_id` whose step does not belong to the run; it refuses a run already terminal; and it writes `step_id` null.

  **What it does not claim.** `0001_base_schema.py:228-229` grants a table-level `UPDATE ON runs` to `app_api` and `app_worker` alike, and both grants stay — that file records them as r7's identity table verbatim and declines to narrow them unilaterally. A direct `UPDATE` therefore still reaches a terminal run with nothing in the log saying so; this criterion establishes only that the intended path cannot. AC-0329 records it.
- [ ] **AC-0324.** The append path that carries `approval.granted` and `approval.rejected` is granted to **`app_api`**, and it commits while the step's `owner` is null. It enforces four predicates, each asserted by a call that violates it: it admits only those two types; it refuses a `step_id` whose step does not belong to the run; it refuses a step that is not suspended; and it refuses a decision when `steps.approval_cycles` already records one for the current cycle — so a retried call is refused while the next legitimate cycle is admitted.

  **The exclusivity is stated at the type, not the function, because the function level is not where it is decided.** `append_step_event` refuses types by a **denylist** — `policy.decision` and the four run-lifecycle and terminal types — so `approval.granted` is already an admitted step-scoped type on the path `app_worker` holds, and a function-level claim would assert a property the grant set does not have. The criterion therefore asserts that **no role other than `app_api` may commit these two types by any path**, which requires revision 0005 to close the denylist gap as well as add the new path. **Owner decision 2026-09-27: `app_api` holds it**, because the approver acts through the API and the lease is released before they do; T0's ADR records the deviation from r8 § 4 line 460, which limits `api` to run-lifecycle types.

  **What stands in for possession.** Nothing proves it, because by construction nobody holds the lease. The structural predicates are the substitute, and that is weaker than the fence r8 § 4 line 461 ratifies as *Built*. AC-0329 records it.
- [ ] **AC-0328.** A person grants or rejects a suspended step through a documented operation on the shipped API, and a caller that is not the API's own origin is refused. The operation appears in `contracts/openapi/runs.yaml` and the committed route count moves from three to four, so the shipped contract-agreement check reads it.

**Bounding the loop and the spend**

- [ ] **AC-0321.** A step sent back for revision more times than the cap allows fails with a recorded cause rather than looping. The count is read from `steps.approval_cycles` and **survives a worker handoff**, asserted by driving the cycles across one rather than within a single process. The cap's configuration is `PoolConfig` and carries a **finite default**, so a deployment setting no value still gets a bounded loop.

  r5 line 607 fixes the loop at three cycles and lines 619–622 call the number arbitrary, asking Phase 1 to replace it with an observed one. Too few cycles run here to observe anything, so the cap ships at three, bounded and uncalibrated, and AC-0329 says so.
- [ ] **AC-0325.** With usage already accumulated in the event log past the configured per-run ceiling, the executor's check before dispatching the next step **pages rather than aborting**, and the page is a step-scoped event appended through the path the worker already holds, on the step it is about to dispatch. The ceiling's configuration is `PoolConfig` and carries a **finite default**.

  r5 lines 1255–1257 ratify the paging behaviour, because for a single operator killing a legitimate long analysis is the worse error. The event is step-scoped deliberately: a run-scoped page would need a third new append path, and the worker holds a lease at pre-dispatch time, so the shipped fenced path already carries it.

**Saying what this did not establish**

- [ ] **AC-0329.** The record names these residuals, each a control this spec specified and did not fully close: both roles' retained table-level `UPDATE ON runs`; the unfenced approval-decision path; the unauthenticated approver principal; the cycle cap's arbitrary three; and the five r8 § 3 transitions authored but unexercised, with the safety constraints `awaiting_input` owes named alongside.

## Follow-ons

- eugenelim: **the r9 consistency pass.** r8 § 4 line 460 and § 3 line 344 disagree about whether the worker may write a run-lifecycle type, and § 4 line 461's possession invariant is made untrue for two event types here. ADRs record the deviations; they do not amend r8.
- eugenelim: **`awaiting_input` and `expired` are authored and unexercised.** The first spec to wire the input tool owes r8 § 3's two safety constraints with it — the answer admitted at the acting role's existing ceiling, and the request and answer both recorded.
- eugenelim: **the cycle cap's number is still arbitrary**, owed to the first delivery that runs enough cycles to earn one.

## Assumptions

- Technical: nothing writes `runs.state` today and no identity can append `run.completed`; both were verified against `migrations/versions/0002_append_paths_and_privilege_split.py` and a content search of `src/` on 2026-09-27.
- Technical: `append_step_event` refuses types by denylist, so `approval.granted` is admitted on it today — verified by executing the migration module's `NON_STEP_EVENT_TYPES` on 2026-09-27.
- Governance: r8 disagrees with itself on which role may write a run-lifecycle type; ratified means implemented, not reconciled, and this spec takes § 3's reading under an ADR.
- Process: eugenelim approves both gates. **This is self-approval, labelled rather than presented as review**; what independent scrutiny these artifacts have came from forked-context reviewer agents.
