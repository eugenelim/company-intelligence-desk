# Plan: Walking skeleton — evidence

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8 § 3 Runtime Model (the run state machine, the approval gate), § 4 Contracts and Invariants (the event log and stream mechanism) and § 9 Decisions, Alternatives, and Risks (the primary page threshold); [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 3 Runtime Model (the approval gate) and § 2 Structural Model (the pool). **Production implementations now exist for two of the three surfaces this plan once had none for**, because the five sibling specs shipped between this plan's approval and its execution: `src/ced/api/main.py` serves the cursor projection over committed events, and `src/ced/worker/executor.py` with `src/ced/worker/persistence.py` carries suspension, the payload-object write and resume from bytes. The spikes remain precedent only where the tree still has none: `spikes/phase-0/stream_resumption_spike.py` for the `Last-Event-ID` preference, which no shipped route implements, and `quarantine_quality_spike.py` for the A/B comparison AC-0312 re-runs. **Named deviation:** the resumption spike drove an HTTP client, not a browser, so it is precedent for the server's behaviour and not for the client's. **Named absence:** nothing in the tree writes a run-terminal event or moves `runs.state`, so AC-0320's append path has no analogue and is designed here.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Make the system finish a run, then watch it, then measure it.

The order is real rather than conventional. The run state machine has to exist
before a clean run can publish, publication has to work before there are
completed steps to take a p99 from, and the p99 has to exist before
`step_deadline` can be set to anything defensible. The browser sits beside that
chain rather than inside it — it depends on the state machine producing
terminal events and on nothing else — so it is the one place this plan forks.

**T0 sits in front of all of it, and was added on 2026-09-26.** Three decisions
turned out to be prerequisites rather than implementation details: which
identity may close a run, where the approval gate sits, and whether `ui/` may
exist. Each is a deviation from a ratified document or a recorded boundary, and
each was reachable by an implementer who would have settled it at the keyboard
and left no record. Writing the records first is what makes the rest of the
plan a build rather than a series of small architecture decisions taken under
delivery pressure.

The measurement tasks come last and are deliberately thin in code. The
measurement command reads the event log, because r8's primary page depends on
the same figure and an operator needs it recomputable rather than recorded once
by a script nobody kept.

**The riskiest part is not technical.** It is that two of this spec's outputs
are results the delivery would prefer not to get — a cancellation that only
abandons its request, and an analytical baseline falsified a second time. The
plan's job is to make recording those cheap and re-running them awkward, which
is why AC-0310 fixes a two-value vocabulary emitted by the command rather than
a sentence written afterwards.

## Constraints

- `runtime-architecture.md` r8 — ratified with its five accepted limits in § 9 accepted **open**. The `5–15%` escalation figure is a calibration target, explicitly not a release gate, and this spec does not turn it into one.
- `worker-runtime.md` r5 — see § DR dispositions below.
- **Hard dependencies:** `walking-skeleton-foundation` (schema, append paths, pool, API), `walking-skeleton-role-compilation` (the compiled agent and the quarantine boundary), `walking-skeleton-authority-containment` (the containment fragment), `walking-skeleton-policy-decision-point` (the decision point that installs it) and `walking-skeleton-step-lifecycle` (the provider call, the step deadline, persistence). **This spec adds no agent.**
- **It does add schema, and an earlier revision of this plan said twice that it did not.** Revision 0005 is expand-only and opens two append paths the shipped privilege split has no room for. The terminal path: `append_run_event` admits `run.requested` and `run.cancelled` only, `append_step_event` refuses the terminal namespace, and direct `INSERT` on `events` is revoked from every application role, so AC-0301 has no writer. The grant path: r5 line 604 releases the lease *before* the approver acts, which clears `owner`, so `fence_step`'s possession predicate fails and every fenced append raises `serialization_failure` — AC-0303's grant has no writer either, at the moment r5 places it. AC-0320 fixes what the new paths must satisfy; two new top-level directories are **not** implied, but one is (see `ui/` below).
- **`ui/` is a sixth top-level directory.** ADR-0003 D1 records five and D2 makes a sixth an Ask-first boundary needing a superseding record; `tests/architecture/test_recorded_layout.py::test_no_top_level_directory_is_unrecorded` reds on any tracked directory neither ADR-0003 nor ADR-0007 names. Owner decision 2026-09-26: an ADR amends the recorded layout, written in T0 before T3 tracks a file under it. The shaping-phase exception has not expired, so an ADR is the route and no RFC is owed.
- **Out of scope:** the AWS deployment, by the owner's decision of 2026-09-18; the assistant surface and `legible-refusal-and-readiness`, both Draft and unauthorised.

## DR dispositions

| DR | Decision | Disposition |
| --- | --- | --- |
| DR1 | Publication is an executor transition, not a tool | **Lands**, T1 — the transition is the application's; the agent's only lever is the contentless tool the agent-runtime spec built |
| DR4 | The liveness probe is the out-of-loop watchdog | **Lands**, T1 — the probe fails when no heartbeat has been *attempted* within twice the lease TTL, which is what makes it catch a starved event loop rather than merely a dead process |
| DR5 | Rejection resumes the conversation, capped at three cycles | **Lands**, T1, under AC-0321, at r5's three and unmeasured. An earlier revision of this row said "lands, unmeasured" while T1 carried no `Tests` entry, no `Done when` clause and no `Touches` path that could hold a cap — and nothing in `src/` implements one, so the row described a control that did not exist rather than one that existed uncalibrated. AC-0321 drives the transition the cap counts and requires the configuration to carry a finite default, so a deployment declaring nothing still gets a bounded loop. The *number* is still arbitrary: r5 asks Phase 1 to replace it with an observed one, this skeleton runs too few cycles to observe anything, and the spec's Follow-ons says so rather than implying the cap is now evidence-based |
| DR6 | Three spend ceilings | **Partly here** — the per-run ceiling checked by the executor before dispatching each step lands in T1, **under AC-0325**. It **pages rather than aborts**, because for a single operator killing a legitimate long analysis is the worse error, and the criterion asserts the page rather than a halt for that reason. An earlier revision dispositioned this as landing with no `Tests` entry, no `Done when` clause and no criterion — the identical defect round 1 found in DR5 and the first revision repaired for DR5 alone. The per-step ceilings are the agent-runtime spec's; the per-account budget alarm is outside the application |
| DR7 | Analytical quality is re-baselined at Phase 1 | **Lands**, T5 |
| DR13 | `trust_class` is a construction | **Agent-runtime's**, and AC-0313 measures what its narrowing costs |
| DR2, DR3, DR8, DR9, DR10, DR11, DR12 | — | **Not this spec's** — owned by the sibling specs, triggered at Phase 2, or already applied |

## Amendments asked of the parent architecture

| # | Change | Disposition |
| --- | --- | --- |
| 6 | The `awaiting_input` run state and its two events | **Lands**, T1, as an authored but unexercised state — in the Python transition table only. No role in this skeleton calls the input tool, so no criterion reads it and no row carries the value. `runs.state`'s CHECK enumerates eight states without it and is deliberately **left alone**: r8 § 10 line 1134 records that this change needs no stored-state migration, and widening the CHECK is owed on the day something first writes the state, not before |
| 12 | `api` gains the metric-publishing grant | **Not applicable at this scope** — it feeds queue-depth autoscaling, MVP runs a fixed worker count, and there is no AWS deployment here |
| 1–5, 7–11 | — | **The sibling specs'**, each with a disposition recorded there |

## Construction tests

**Integration tests:**
- One clean-run end-to-end through local Compose: requested, planned, quarantine classifies, analysis calls its tool, artifact published, stream closed, no human. This is the spine AC-0301 reads and the harness every measurement task reuses to generate steps.
- One flagged-run end-to-end that suspends, releases its lease, and resumes to publication on a grant, so the clean path is a branch rather than the only path.

**Schema tests (`substrate`):**
- AC-0320's grant-disjointness and single-transaction assertions run against the applied revision, because a grant set is a property of the schema Postgres holds and not of the migration's text.

**Manual verification:**
- AC-0304, AC-0305 and AC-0322 are driven by a real browser and the observed result recorded in the verification ledger. A rendered outcome is the evidence; a green assertion over a response body is not.

**Mutation proof is a deliverable of this plan, not a practice it hopes for.**
Every criterion whose `Tests` entry names a mutation writes its proof to
`docs/specs/walking-skeleton-evidence/notes/verification-ledger.md` — the
break applied, and the check that went red. The previous delivery in this
series found six checks that could not fail, three of them written by repairs
rather than original builds, and its evidence existed only in a session report:
one proof was run and never written down, one was written to a `notes/`
directory at the repository root where nothing reads it, and one was never
reached. A proof filed where nobody looks is the same defect as a proof never
run. The ledger path above is the one the spec names and the only one that
counts.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Schema — `migrations/versions/`, `docs/adr/` | T0, T1 | Revision 0005 applying on a clean volume, with the grant set asserted disjoint by AC-0320 and AC-0324; the append-path ADR T0 writes | The revision is expand-only and revokes nothing, and the ADR is cited from the criteria resting on it |
| Recorded decisions — `docs/adr/` | T0 | The layout record superseding ADR-0003 D1, and the gate-placement deviation record | Each is cited from the criterion or task that rests on it, and the layout test is green against the widened recorded set |
| Operations — `docs/architecture/pydantic-ai-worker-runtime/operations.md` | T4 | Each recorded value with its sample size and platform | Values satisfy the ordering invariant and cite their sample size |
| Reusable learning — `spikes/README.md` | T6 | A Phase 1 section separating established, substituted and not-established | Hypothesis checks reported separately from setup |
| Current architecture — r8 header, `docs/architecture/README.md` | T6 | Markers moved off `PLANNED` for what exists | Headers match the repository |
| Interface compatibility — `contracts/openapi/runs.yaml` | T3 | The fourth operation documented with its media type, cursor bounds, refusal status and close semantics, each asserted | Contract and implementation agree under test, and the generated document matches the hand-authored one |

## Design (LLD)

Shape is `mixed`; the sub-sections below are the pruned set.

### Design decisions

- **The measurement command is product code, not a script.** p99 and cancellation latency are read from the event log by a command that ships, because r8's primary page depends on the same figure and an operator needs it recomputable. Traces to: AC-0307, AC-0309.
- **The cancellation outcome is a value the command emits, never a sentence an author writes.** `terminated` and `abandoned` are distinguishable only by observing the connection, and a criterion satisfied by any prose is not a criterion. Traces to: AC-0310.
- **Rejected: setting `step_deadline` provisionally and correcting after measurement.** A placeholder would make AC-0306 pass against a number that means nothing. Instead T2 runs steps under a deliberately generous deadline whose only job is to not fire, T4 measures, and T4 sets the real value — so no criterion is ever demonstrated against a deadline that later changes.

### State & control flow

The run state machine is r8's, plus `awaiting_input` and its two events. Both
`expired` and `awaiting_input` are non-terminal: a timed-out approval is
recoverable and never silently discarded, and `approval_timeout` defaults to
none in MVP.

The approval gate is conditional and the condition is computed outside any
model. Pre-release checks run in the step executor **before** the agent run and
their result commits as an event. On a clean run the agent is offered no
callable approval-gated tool and no human is in the path, which is the ratified
charter amendment this spec must not reverse.

**Where the gated tool sits, and why this plan no longer says what r8 says.**
r8 § 3 lines 400–403 puts the tool in the *compiled* toolset, present only when
a check failed, and an earlier revision of this section repeated that. The
shipped tree does the opposite and does it deliberately:
`src/ced/agents/tools/approval.py` builds the tool as a run-time
`FunctionToolset` and `src/ced/worker/executor.py` passes it through
`toolsets=[…]` on the agent call, keeping it outside the compiled stack so the
policy decision point never judges it against the acting role's ceiling.
Building to r8 would move approval *inside* that authority check and change
behaviour a shipped spec already delivered. **Owner decision 2026-09-26: the
shipped placement stands**, T0 records the deviation in an ADR, and this
section describes what is built rather than what r8 describes. The consequence
for verification is AC-0302's: on this design the compiled toolset is empty of
gated tools in every possible world, so the criterion reads the tool set the
model is actually offered. Traces to: AC-0301, AC-0302, AC-0303.

**Who closes a run.** Nothing in the tree writes a run-terminal event or moves
`runs.state`; the column is read by `append_run_event`'s terminal guard and by
the pool's heartbeat, and written by no code at all. Revision 0005 adds a
definer function that commits the state change and its terminal event in one
transaction, granted to `app_worker` alone and fenced on the step that
completed the run while writing `step_id` null. The single-transaction shape is
load-bearing rather than tidy: `app_worker` already holds a table-level
`GRANT UPDATE ON runs` from revision 0001, so a state move with no event is
reachable today and would leave a run terminal with nothing in the log saying
so. Traces to: AC-0301, AC-0320 · ADR written in T0.

### Interfaces & contracts

The new stream operation carries its reconnect semantics here: the server
prefers `Last-Event-ID` over the `after=` query parameter, because the
browser's `EventSource` re-requests the original URL with a now-stale cursor on
reconnect and supplies the header itself.

**The client uses `EventSource`'s native automatic reconnect, and that choice
is what makes AC-0305 testable.** An earlier revision of this paragraph said
both that the browser re-requests the original URL *and* that "the client
persists its own cursor and reopens explicitly" — mutually exclusive, because a
freshly constructed `EventSource` sends no `Last-Event-ID` at all and the API
offers no way to set one. AC-0305 requires a stale `after=0` **and** a
`Last-Event-ID` on each of ten reconnects, which is exactly what the native
path produces: the URL carries `after=0` forever and the browser attaches the
header from the last `id:` field it saw. So the server emits `id:` on every
event, the client sets no cursor of its own, and the sink stays idempotent on
the run-and-sequence pair as a second line of defence rather than as the
mechanism under test. Traces to: AC-0304, AC-0305, AC-0323 ·
`contracts/openapi/runs.yaml`.

### Component / module decomposition

The browser client is deliberately small: an event list, a state badge, and a
cursor. Agent-authored text renders as plain text — never markdown, HTML, or a
link — because a model-authored link target must not become clickable. Typed
domain artifacts render through the application's own components from
structured fields, which is a different path and stays rich. Traces to:
AC-0304.

### Quality attributes (NFRs)

Every number in this spec except AC-0306's ordering is an *output*. The
ordering is the only thing that can red, and it reds by reading three recorded
values rather than by comparing against a literal — which is what makes a later
configuration change that breaks the ordering visible. Traces to: AC-0306,
AC-0307, AC-0308.

### Dependencies & integration

New dependencies, recorded before being added per `AGENTS.md`: `vite` and
`react` for the browser client, and **`playwright`** — named, because an
earlier revision recorded only "a browser-driving test dependency", which
identifies no package and so records no decision. It drives AC-0304, AC-0305
and AC-0322 as a `[project.optional-dependencies] dev` entry, pinned like every
other dev dependency in `pyproject.toml`; the Python binding is chosen over a
Node test runner so the browser criteria run under the same `pytest` invocation
and the same `substrate` marker discipline as everything else.

The browser client brings a second package ecosystem into a repository that has
none, so `ui/package.json` and its lockfile are the manifest of record for
`vite` and `react`, and `AGENTS.md` § Build and test commands gains the install
and build commands in the same change that introduces them. **No vulnerability
scanner covers that tree**, which is not a new gap — `workspace.toml`
`[backlog].open` already records that neither `pip-audit` nor any image or
secret scanner is wired — but it is a newly *larger* one, and T6 records it
among what Phase 1 did not establish.

Everything else is inherited.

External: Amazon Bedrock, reached under the scoped assumed role the
agent-runtime spec established, by the tasks that generate real steps.
Service Quotas is read once by T4. SEC EDGAR is not reached at all.

## Tasks

### T0: The records the build is not permitted to make silently

**Depends on:** none

**Touches:** docs/adr/**, docs/specs/walking-skeleton-evidence/spec.md, tests/architecture/test_recorded_layout.py, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- Goal-based: `./.venv/bin/python -m pytest tests/architecture/test_recorded_layout.py` is green with `ui` in the recorded set and the directory not yet created — the layout record admits it before anything tracks a file under it, which is the order ADR-0003 D2 asks for.
- Goal-based: `python3 tools/hooks/pre-pr.py` passes its ADR shape lint over each new record.

**Approach:**
- Three decisions, three records, none of them resolvable by an implementer at the keyboard. **The layout amendment**: ADR-0003 D1's five directories become six, superseded rather than edited, with `ui/` named and the layout test's recorded set widened in the same change. The same record settles two more layout questions this spec would otherwise decide in passing — that `src/ced` gains `ops/` and `eval/` beyond D3's five layers, which the layout test admits by a subset assertion and so records nowhere; and that D3's "two deployables" governs distributions and services rather than console scripts, so T4's measurement command may take a third `[project.scripts]` entry. Both were about to be settled in a task's Approach and a `pyproject.toml` comment, which is the class this task exists to prevent. **The gate-placement deviation**: r8 § 3 lines 400–403 compile the approval tool in conditionally; `walking-skeleton-step-lifecycle` ships run-time injection instead, and the ADR records that the shipped placement stands because it keeps approval outside the decision point's authority check. **The terminal-transition identity**: r8 § 4 line 460 and § 3 line 344 disagree about whether the worker may write a run-lifecycle type, and the ADR records that § 3's diagram is the reading kept, with the fence and the null `step_id` as what keeps § 4's disjointness intact. It also records the approval-grant path AC-0324 fixes, since that path crosses the same invariant for the same reason.
- An ADR records a deviation from a ratified document; it does not amend one. The r9 consistency pass is named as owed in the spec's Follow-ons and is not attempted here.

**Done when:** the three records exist, the layout test is green against the widened set, and each criterion that rests on a deviation cites the record that carries it.

### T1: A clean run publishes with nobody watching

**Depends on:** T0

**Touches:** migrations/versions/**, src/**/domain/run_state.py, src/**/domain/events.py, src/**/worker/prerelease.py, src/**/worker/executor.py, src/**/worker/persistence.py, src/**/worker/pool.py, src/**/adapters/postgres/event_log.py, src/**/adapters/objectstore/**, src/**/worker/liveness.py, src/**/api/main.py, deploy/compose.yaml, contracts/openapi/runs.yaml, tests/e2e/**, tests/schema/**, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0301 reads the run's outcome end to end: terminal `run.completed`, an artifact published, no `approval.requested` appended.
- AC-0320 and AC-0324 are the schema-level half and carry the `substrate` marker. For each: the grant set after revision 0005 is still disjoint and still carries no direct `INSERT` on `events`; the path is granted to exactly one role; each of its predicates is driven by a call that violates it and observed to refuse — for AC-0320 **lease possession**, the type allowlist, the step-belongs-to-run check, the already-terminal refusal and the null `step_id`, and for AC-0324 the type allowlist, the step-belongs-to-run check, the not-suspended refusal and the already-decided refusal; and with the append forced to fail, `runs.state` does not move.

  **Mutation proof is owed before either counts as coverage.** The named break for the atomicity assertion is to split the definer function's single body into two caller-issued statements — the update, then the append — which is the separable wrapper the criterion means; the assertion must then red. The named break for each predicate is to delete that predicate from the function body. A check that passes with a predicate removed is asserting the happy path, which is the shape three of the last delivery's six dead checks had.

  **AC-0320 does not assert that no path moves `runs.state` without an event**, and the test must not be written as though it does: `app_worker` keeps its table-level `UPDATE ON runs` by the owner decision of 2026-09-26, so that bypass stays open and AC-0314 records it. Nor does either criterion range over `run.cancelled`, which `app_api` already commits through `append_run_event` while moving no state — a shipped sibling's route, left alone.
- AC-0325 accumulates usage in the event log past the configured per-run ceiling and asserts the executor's pre-dispatch check appends the page event and does not abort the run — read from the appended event, not from the ceiling's configuration. A second case asserts that a `PoolConfig` declaring no ceiling still gets a finite one. **Mutation proofs owed**: remove the check and the first must red; remove the finite default and the second must red.
- The liveness probe (DR4) is asserted by stalling the poll loop without killing the process and observing the probe fail. **It is a worker-side command run by the container healthcheck, not an HTTP route** — `deploy/compose.yaml` invokes it, `src/ced/worker/liveness.py` implements it, and it reads heartbeat recency rather than process existence. Making it an API route would put a fifth operation on a surface the spec's Contract line fixes at four and `tests/api/test_contract_agreement.py` asserts is exactly the committed set. Out-of-process is also what DR4 asks for: a probe inside the loop it watches cannot see the loop starve.
- AC-0302 inspects the tool set the model is offered at run time, which on the shipped placement is where conditionality is decidable at all. **Mutation proof is owed**: make the gate unconditional on a clean run and this must red. The criterion as previously written — over the compiled toolset — could not red under any mutation, because the shipped design never compiles the tool in.
- AC-0303 forces a pre-release failure and drives the suspension through to publication on a grant, which is what makes AC-0301's "clean" one branch of a real condition. It also reads back the appended grant and asserts it names the granting principal and carries the `require_distinct_approver` state — **read from the log, not from the value the test supplied**, which is the read-back-what-you-placed shape.
- AC-0321 drives a step past the cycle cap and asserts it fails with a recorded cause, then asserts a pool configuration declaring no cap still bounds the loop. The second half is what stops a configuration read satisfying the criterion. **The cycles are driven across a worker handoff**, not inside one process, and this half is `substrate`: r5 releases the lease before each approval, so a counter in worker memory is reset by the handoff the loop performs every cycle and three rejections inside one process would pass against an unbounded loop. **Mutation proof is owed**: move the count into worker memory and the handoff assertion must red.
- AC-0303's two added clauses. The grant event is read back from the log and asserted to name the granting principal. The `require_distinct_approver` state is driven **both ways** — the flag configured true and false, two runs, two different appended values — because a single-value read-back is satisfied by a module constant written into the payload, which is the derive-the-input-from-the-constant shape. The flag's configuration surface is `PoolConfig`; it exists nowhere in `src/` today. Suspension is made deterministic by the role under test resolving to a model that calls `request_approval` on every flagged run, named here so the criterion is not resting on a real model's discretion.
  A probe that only checks process existence would pass on a stalled loop, which is the failure mode it exists to catch.

**Approach:**
- Revision 0005 comes first and is expand-only, and has **three** parts rather than two: the run-terminal definer function granted to `app_worker` (AC-0320); the approval-grant function granted to `app_api` (AC-0324); and **a `steps.approval_cycles` column**, `integer NOT NULL DEFAULT 0`, which is where AC-0321's cycle count durably lives. Plus their `EXECUTE` grants. An earlier revision described the count as living in "durable per-step state" and then enumerated the revision as two functions, which named no place for it — and the two candidates, a column versus deriving the count by scanning `approval.rejected` events, carry different migration, grant and concurrency consequences, so leaving it unnamed left a real choice to the keyboard. The column is chosen because the derived read would have the worker scan the event log on every resume to compute a bound. **It revokes nothing** — `app_worker` keeps its table-level `UPDATE ON runs`, by the owner decision of 2026-09-26 and for the reason `0001_base_schema.py` already records: that grant is r7's identity table verbatim and narrowing it unilaterally would deviate from ratified authority. Both functions are written against the lock ordering the existing functions use — `steps` before `runs` — because a third order is what the foundation's deadlock suite exists to catch, and both carry the predicate set their shipped siblings carry rather than only the grant that names their caller.
- The cycle cap's count lives in `steps.approval_cycles`, not in the worker, so it survives the lease release r5 performs before every approval.
- The per-run spend ceiling pages rather than aborts and now has AC-0325 reading it. DR5 and DR6 were dispositioned the same way and only DR5 was repaired in the first revision; both now carry a criterion, which is the level the defect sits at rather than the one it was reported on.
- `awaiting_input` and its two events are authored into the transition table here, unexercised. No row carries the value, so `runs.state`'s CHECK is left alone; r8 § 10 line 1134 records that this needs no stored-state migration, and the CHECK is what would have to widen on the day something writes the state. The first spec to wire the input tool owes that, and owes r8 § 3's two safety constraints with it.
- The per-run spend ceiling pages rather than aborts.

**Done when:** AC-0301, AC-0302, AC-0303, AC-0320, AC-0321, AC-0324 and AC-0325 are green, each with its mutation proof written to `notes/verification-ledger.md`, and the liveness probe is observed failing on a stalled loop.

### T2: Real steps accumulate under a deadline that will not fire

**Depends on:** T1

**Touches:** deploy/compose.yaml, tests/e2e/**

**Tests:**
- Goal-based: a harness run produces at least the sample AC-0307 needs, and no step is failed by the deadline during it. A deadline that fires here would contaminate the p99 with truncated steps.

**Approach:**
- **The sample runs with no `step_deadline` configured at all**, which is the honest description of what happens here. An earlier revision said the deadline "is set deliberately generous" — but `PoolConfig.step_deadline` defaults to `None`, no environment variable reaches it, and T4 is the task that builds that surface. A generous value was therefore unsettable at the moment T2 runs. `None` means no deadline, which satisfies this task's only requirement — that nothing truncates a step and contaminates the p99 — for a more direct reason than a large number would.
- The real value is set in T4 from the measurement, which is why no criterion is demonstrated against whatever is in force here.
- **This is the task that spends money, and no mechanism in this delivery halts it.** The spec's Ask-first `$5` threshold is an instruction to the operator, and the per-run ceiling AC-0325 asserts **pages rather than aborting** by r5's ratified decision — so a run past the ceiling keeps calling the provider and the page is a notification, not a brake. An earlier revision of this bullet called that ceiling "the mechanical bound in this delivery", which it is not. What bounds T2 in practice is the operator watching: the sample is 30 completed steps against a cheap model, the re-baseline cost $0.022 the first time, and the Ask-first threshold stops the task rather than the system stopping it.

**Done when:** a sample of completed real steps exists in the event log, none truncated by a deadline.

### T3: A browser watches a run and survives losing the connection

**Depends on:** T1

**Touches:** src/**/api/stream.py, src/**/api/main.py, ui/**, ui/package.json, pyproject.toml, contracts/openapi/runs.yaml, AGENTS.md, tests/browser/**, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0304 and AC-0305 drive a real browser. AC-0305 forces ten disconnects with a writer active and sends a deliberately stale `after=0` on every reconnect. **The assertion is what the server sent**, captured from the wire: on each reconnect the first event emitted carries the sequence after the client's `Last-Event-ID`, and no reconnect re-emits an event the client already holds. Sequence completeness at the sink is asserted too, and is not sufficient on its own — the sink is idempotent on `(run_id, seq)`, so it would silently absorb a full replay from a server that ignored the header. **Mutation proof is owed**: delete the `Last-Event-ID` preference and AC-0305 must red. If it stays green the criterion is measuring the sink.
- AC-0322 drives a run in which markup and a link target appear in **three places** — agent-authored text, a typed-artifact field value, and an envelope field such as `principal` — and asserts the rendered page shows those characters literally in all three, with no element created and no navigable anchor. The typed-artifact path is inside the assertion, not exempt from it. **Mutation proof is owed**: render any one of the three as HTML and this must red.
- AC-0323 sends a `Last-Event-ID` that is non-integer, negative, and greater than the run's highest committed sequence, and asserts each is refused with `422` rather than coerced or read as zero. A cursor *behind* the committed log is the ordinary reconnect and is asserted **not** refused, so the criterion cannot be satisfied by a server that refuses every unusual header.
- AC-0326 asserts the API serves the built `ui/` bundle, and that a state-changing request carrying a foreign `Origin` is refused. No CORS middleware is added.
- The observed result is recorded in the verification ledger, because a rendered outcome is the evidence here.

**Approach:**
- **The stream is a fourth operation, not an upgrade of `read_events`.** `/runs/{run_id}/events` is a paged JSON read and stays one; the new route serves `text/event-stream`, prefers `Last-Event-ID` over `after=` under AC-0323's bounds, and closes on a terminal event. Contract it with its media type, its parameters, its `422`, and its close semantics — all four, because AC-0304's "stream closed" and AC-0305's wire observation have no meaning without them. The route is registered on the app in `src/ced/api/main.py`, because AC-0009 compares the *generated* OpenAPI document against the hand-authored contract and a served-but-unregistered route reds it.
- **The API serves the built client**, so page and API share an origin and no CORS middleware exists to configure. The Vite dev server proxies to the API rather than calling it cross-origin. This is what makes AC-0322's threat argument true rather than assumed, and it is AC-0326.
- The client is deliberately small — an event list, a state badge, a cursor. **Every value the page did not author renders as a text node** — agent text, typed-artifact field values, and envelope fields alike. Typed artifacts render through the application's own components, which controls *layout and affordances* from structured fields; it does not make the field values trusted, and AC-0322 asserts over that path too.
- `playwright` provisions browser binaries by downloading them at install time. Record that command in `AGENTS.md` beside the `ui/` install and build commands, in this same change, so a clean clone can run the browser criteria.

**Done when:** AC-0304, AC-0305 and AC-0322 are observed in a real browser and recorded with their mutation proofs, AC-0323 and AC-0326 are green, the contract carries the new operation in full, and **`ui/`'s lockfile is committed with the install command recorded in `AGENTS.md` in its frozen, lockfile-respecting form** — so a clean clone resolves the same tree rather than a fresh one, which is the only pinning control either ecosystem has while no scanner covers them.

### T4: The deadline is calibrated against a measurement, not a guess

**Depends on:** T2

**Touches:** src/**/ops/**, src/**/adapters/aws/**, src/**/worker/pool.py, deploy/compose.yaml, pyproject.toml, AGENTS.md, docs/architecture/pydantic-ai-worker-runtime/operations.md, tests/ops/**, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0307 refuses to emit a p99 below the sample floor rather than reporting a figure the sample cannot support.
- AC-0308 recomputes the threshold from the same sample, so the two cannot be recorded from different runs.
- AC-0306 reads all three recorded values and asserts the ordering. This is the one measurement criterion that can red, and it reds if a later configuration change breaks the ordering.
- AC-0309 and AC-0310 cancel mid-stream. The distinguishing observation is named in the record, because from inside the coroutine an abandoned request and a terminated one look identical — the evidence has to come from the connection.
- AC-0311 reads the tokens-per-minute quota for the model in use through the Service Quotas API, capturing the Region from the resolved client rather than from configuration, because a quota recorded against the wrong Region is worse than none.

**Approach:**
- Set the real `step_deadline` from the measurement, in the same change that records it. **It is configured in two places and neither was named before**: `PoolConfig.step_deadline` in `src/ced/worker/pool.py` defaults to `None`, meaning no deadline at all, and no environment variable reaches it — `CED_STEP_BODY_SECONDS` is the offline stub's timer and is a different thing. T4 gives the field a real default and an environment surface, and sets it on both worker services in `deploy/compose.yaml`, or AC-0306 reads a configured value that does not exist.
- The Service Quotas call is sited under `src/ced/adapters/` because the AWS SDK import belongs there: `tests/architecture/dependency_direction.py` walks import statements, so the measurement command in `src/ced/ops/` reaches the quota through the adapter the way `src/ced/worker/executor.py` already reaches `boto3`. The Region is captured from the resolved client rather than from configuration, because a quota recorded against the wrong Region is worse than none.
- **The quota read runs under its own identity, not the worker's.** It needs `servicequotas:GetServiceQuota`, which the Bedrock-scoped assumed role does not carry — and that role's IAM shape is pinned by `walking-skeleton-step-lifecycle` as carried over from spike 1 and deliberately not re-derived. Widening it permanently for a measurement taken once is the reachable shortcut and is refused: the quota read uses the operator's own credentials, through the same `CED_AWS_ADMIN_PROFILE` seam `tests/provider/` uses, and the recorded value carries no ARN or account id because `tools/lint-no-identifiers.py` is a standing gate over everything staged.
- The measurement command ships as product code and gains a `[project.scripts]` entry, recorded in `AGENTS.md` § Build and test commands in the same change. That a console script is not one of ADR-0003 D3's "two deployables" is settled by T0's layout record rather than by a comment in `pyproject.toml`.
- If cancellation comes back *abandoned*, that is the recorded result.

**Done when:** AC-0307 through AC-0311 are recorded in the operations document with their sample sizes and platform, the quota read's identity and its single action `servicequotas:GetServiceQuota` are recorded beside the value — naming that it runs under the operator's own admin profile rather than the worker's Bedrock role, so the breadth of that credential is written down rather than implied, AC-0306 is green against the recorded values, and the configured `step_deadline` the criterion reads is the one the workers actually run with.

### T5: Analytical quality is re-baselined, whatever it says

**Depends on:** T2

**Touches:** src/**/eval/**, tests/eval/**, docs/specs/walking-skeleton-evidence/notes/rebaseline.md, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0312 re-runs the A/B against the same recorded 10-Q and reports against the same three loss categories, so the result is comparable to the original rather than merely new. The producer tuple labels the run; without it the comparison has no identity.
- AC-0313 separates two costs the original conflated: what the quarantine boundary costs, and what the narrowed admitted set costs under DR13.

**Approach:**
- Same filing, same section, same question. Changing the input would make the comparison meaningless.
- A falsified result is recorded as falsified. Spike 4 was falsified as run and that changed the design rather than the plan; the same standard applies.

**Done when:** AC-0312 and AC-0313 are recorded with their costs and their limits.

### T6: The record says what Phase 1 did not establish

**Depends on:** T3, T4, T5

**Touches:** spikes/README.md, docs/architecture/README.md, docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md, docs/specs/walking-skeleton-evidence/spec.md, docs/specs/walking-skeleton-evidence/plan.md, workspace.toml

**Tests:**
- AC-0314 is checked by reading: for each measurement, the record must name the substitution and the property a deployed fleet would establish that this one does not. A section that lists only results satisfies nothing.
- `python3 .agents/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green across **all six** walking-skeleton specs. The earlier "all three" was residue from before the single `walking-skeleton` spec was split, and `--all` was already sweeping every spec regardless — so the line described a narrower check than the command ran.

**Approach:**
- Report hypothesis checks separately from setup and teardown, per that file's own standard that a check which cannot fail is not evidence.
- Name at least these substitutions: p99 measured on local containers rather than Fargate; lease reacquisition demonstrated with a second worker already running rather than a scheduler replacing a task; the Postgres results taken against a local container with a deliberately low deadlock timeout; the quarantine boundary verified against written cases rather than an adaptive adversary; and the browser criteria driven against a loopback API with no authentication, so nothing here establishes the stream's behaviour under an authenticated ingress.
- Name also AC-0314's five residuals, which are controls this spec specified and did not fully close: the retained `UPDATE ON runs` grant; the unauthenticated approver principal; **the sample-size limit — at a floor of 30, the "p99" is the largest or second-largest observation rather than a tail estimate, and AC-0308 multiplies it by three**; the unscanned dependency trees, now two ecosystems rather than one; and the cycle cap shipping at r5's arbitrary three. The sample-size one is the limit most likely to be over-read, because it is the number Phase 2 plans capacity against.
- **Re-derive the r8 header from `docs/architecture/README.md` § What is built before reducing it**, rather than from the header's own text. The header still names the authorization boundary and the provider call as unbuilt and both shipped, so subtracting this spec's work from the list as written would name the wrong residue. Correct r8 § 10's schema table in the same pass: it marks the partial unique index, `pool_class` and `owner_scope` `Owed` though revision 0002 creates all three. § What is built also carries two clauses the step lifecycle falsified — "Nothing calls it yet" on the role compiler's refusal append, and "There is **no step executor** yet" under the authorization boundary.
- Move the `STATUS: PLANNED` markers only for what now exists. The r8 consistency pass that reconciles § 4 line 460 with § 3 line 344 stays a named follow-on; T0's ADR records the deviation and does not close it.

**Done when:** AC-0314 holds, the status lint is green across all six specs, Phase 1's exit criteria are recorded as met, and the r8 header names a residue derived from the repository rather than from its own previous text.

**`awaiting_input` is authored without its safety constraints.** r8 § 3 makes
operator-supplied text trusted *as instruction* and honest only because the
answer is admitted at the acting role's existing ceiling and cannot widen it,
and because the request and the answer are both recorded as events. This plan
authors the state and its two events deliberately and unexercised; neither
constraint is built, and no criterion reads them. The first spec to wire the
input tool owes both, and inherits a transition table that looks finished.

## Rollout

- **Delivery:** six PRs. T0, then T1; **T2 and T3 both branch from T1 and run in parallel** rather than stacking, because T3 depends only on T1 and a linear stack would put its merge behind the spend-bearing task exactly as bundling them did; then T4+T5, then T6. T0 is first and separate because its records must exist before the code they govern, and a record written after the build it justifies is a rationalisation. **T2 and T3 ship separately**, which an earlier revision did not do while claiming the benefit: it bundled them as one PR and justified the arrangement with "T3 forks from T1 rather than following T2, so the browser work does not wait on a spend-bearing task" — true of the dependency and false of the delivery unit, since a shared PR makes T3's merge wait on T2 anyway. Split, the rationale holds.
- **Review shape:** T1 is now **DEEP** rather than MIXED and is decomposed in dependency order — revision 0005 and its grants; the transition table and the terminal commit; the pre-release checks and the gate; the cycle cap and the liveness probe — each leaving the repository working. It grew when the append paths turned out to be missing rather than present, and an ambiguous shape is DEEP by the sizing rule. T4 and T5 are small in code and large in recorded output, which is the inverse of the usual shape and the reason their `Done when` names a document rather than a suite.
- **Reversible, but no longer entirely.** Nothing is deployed, and no key derivation is added. **Revision 0005 is a one-way door in the ordinary expand-only sense**: migrations here have no downgrade path by construction, so the reversal story is a forward revision that revokes the grants, not a rollback. An earlier revision of this line said "this spec adds no schema", which was the claim a reviewer would read to conclude no migration was in play — the most load-bearing place for it to be wrong.
- **Infrastructure:** the foundation spec's local Compose plus a browser for T3. Bedrock is reached under the scoped role for T2 and T5.
- **Deployment sequencing:** T4 must set `step_deadline` in the same change that records the measurement, or the recorded value and the configured one can diverge silently.

## Risks

- **Cancellation comes back "abandoned".** Plausible, given synchronous botocore. The step stays bounded by the hard timeout the agent-runtime spec provides, so no functional criterion fails; what degrades is the operational story, and AC-0310 exists to state it rather than hide it.
- **p99 on local containers is not p99 on Fargate.** The step is model-bound so the figure should mostly carry, but "mostly" is not measured. AC-0314 records it and the deployment follow-on re-measures.
- **The browser criteria are the flakiest tests in the delivery.** Ten forced disconnects against a live writer is inherently timing-sensitive. Mitigated by asserting sequence completeness at the sink rather than timing.
- **The re-baseline may be falsified again.** Not a delivery risk; a recorded result. Named so nobody treats a bad number as a task to retry.
- **This spec cannot start until both siblings ship.** It is the one place the three-spec split adds real serialisation, and it is unavoidable: there is nothing to measure until there is a system.

## Changelog

- 2026-09-18: initial plan. Split out of a single `walking-skeleton` spec after three review rounds did not converge and the findings clustered by subsystem. This spec took the measurement and presentation criteria; the two uncomfortable outputs — an abandoned cancellation and a second falsification — are written as recordable results rather than bars, which is the main thing the split let this plan say clearly.
- 2026-09-18: spec approved by eugenelim
- 2026-09-18: plan approved by eugenelim
- 2026-09-26: **the pair was hand-reset to `Draft` and `Drafting`, and re-approval is owed to the owner before EXECUTE.** Both revisions below add acceptance criteria to a contract that was `Approved` on 2026-09-18 with its baseline never sealed, and the plan's own contract block admits substantive change only while Status is `Drafting`. No documented lifecycle route covers that window: `delivery-contract-lifecycle.md` makes the controlled amendment unavailable outside `CODE-IMPLEMENTATION`, and its status reset is the recovery for a *rejected* gate, which is not what happened. The conflict is registered in `workspace.toml` `[backlog].open` as `no-lifecycle-route-for-widening-an-approved-unsealed-contract`, surfaced during the sibling spec's amendment on 2026-09-22, and the route taken there — hand reset, amend, re-approval left owed — is the precedent followed here. Recorded rather than resolved, per `AGENTS.md` § Scoped instructions; whichever skill reference owns the rule is where a remedy lands. **The first revision left both statuses at `Approved` and recorded none of this, which the round-2 review caught.**
- 2026-09-26: **second revision, after the second pre-EXECUTE review round** — 26 adjudicated findings across both reviewers, 9 at blocker tier. Three owner decisions: AC-0320's no-bypass claim is **narrowed to what the applied grant set can decide** rather than revoking `app_worker`'s table-level `UPDATE ON runs`, which `0001_base_schema.py` records as r7's identity table verbatim and declines to narrow unilaterally — the retained bypass becomes an AC-0314 residual; the API **serves the built browser client** so page and API share an origin and no CORS middleware exists at all; and AC-0306 is **restated as a regression guard** with § Testing Strategy's claim that it could red withdrawn, because the deadline it orders is derived from the p99 it orders against. Three criteria added — AC-0324 the approval-grant append path's identity, AC-0325 the per-run spend ceiling, AC-0326 the origin posture. Six amended: AC-0303 gained a two-state assertion and a determinism mechanism and dropped an overclaim, AC-0320 gained four predicates and lost a false universal, AC-0321 gained durability across a worker handoff, AC-0322 was restated at the class so the typed-artifact path is no longer exempt, AC-0323 gained an upper bound and a refusal status, AC-0314 gained five named residuals. **The contract line was corrected**: the stream is a fourth operation, not an extension — `/runs/{run_id}/events` serves paged JSON and no `text/event-stream` exists anywhere. **The DR6 defect was repaired at the class rather than on the reported path**: the first revision fixed DR5's empty disposition and left DR6's identical one, which is how the same defect returns.
- 2026-09-26: **spec and plan revised after the first pre-EXECUTE review round**, which ran the contract against the code its five siblings shipped between approval and execution. The contract had not been re-read against the tree and had drifted. Four owner decisions are baked in: a new definer function carries the run-terminal transition rather than widening `append_run_event` or granting it to a second role; the shipped run-time placement of the approval gate stands against r8 § 3, with AC-0302 re-sited onto the surface where conditionality is decidable; `ui/` is admitted by a superseding ADR; and the approver principal becomes a criterion rather than an accepted gap. Four criteria were added — AC-0320 the terminal-transition control, AC-0321 the cycle cap and its finite default, AC-0322 the plain-text rendering check, AC-0323 the `Last-Event-ID` bounds — and three amended: AC-0302's surface, AC-0303's attributability clause, AC-0305's wire-level observation. T0 was added ahead of T1. **Two claims were withdrawn as false**: that this spec adds no schema, in § Constraints and again in § Rollout's reversibility statement. **None widens authority and none relaxes a criterion**; AC-0302 and AC-0305 were each unfalsifiable as written and now can red.
