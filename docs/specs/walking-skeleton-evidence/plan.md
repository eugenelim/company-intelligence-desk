# Plan: Walking skeleton — evidence

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved <!-- Drafting | Approved | Executing | Done -->
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
| DR6 | Three spend ceilings | **Partly here** — the per-run ceiling checked by the executor before dispatching each step lands in T1. It **pages rather than aborts**, because for a single operator killing a legitimate long analysis is the worse error. The per-step ceilings are the agent-runtime spec's; the per-account budget alarm is outside the application |
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
| Schema — `migrations/versions/`, `docs/adr/` | T0, T1 | Revision 0005 applying on a clean volume, with the grant set asserted disjoint by AC-0320; the three ADRs T0 writes | The revision is expand-only, the ADRs are cited from the criteria resting on them, and the layout test is green against the widened recorded set |
| Operations — `docs/architecture/pydantic-ai-worker-runtime/operations.md` | T4 | Each recorded value with its sample size and platform | Values satisfy the ordering invariant and cite their sample size |
| Reusable learning — `spikes/README.md` | T6 | A Phase 1 section separating established, substituted and not-established | Hypothesis checks reported separately from setup |
| Current architecture — r8 header, `docs/architecture/README.md` | T6 | Markers moved off `PLANNED` for what exists | Headers match the repository |
| Interface compatibility — `contracts/openapi/runs.yaml` | T3 | The reconnect semantics documented and asserted | Contract and implementation agree under test |

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

The stream endpoint gains its reconnect semantics here: the server prefers
`Last-Event-ID` over the `after=` query parameter, because the browser's
`EventSource` re-requests the original URL with a now-stale cursor on
reconnect. The client persists its own cursor and reopens explicitly, and the
sink is idempotent on the run-and-sequence pair. Traces to: AC-0304, AC-0305 ·
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

**Touches:** docs/adr/**, tests/architecture/test_recorded_layout.py, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- Goal-based: `./.venv/bin/python -m pytest tests/architecture/test_recorded_layout.py` is green with `ui` in the recorded set and the directory not yet created — the layout record admits it before anything tracks a file under it, which is the order ADR-0003 D2 asks for.
- Goal-based: `python3 tools/hooks/pre-pr.py` passes its ADR shape lint over each new record.

**Approach:**
- Three decisions, three records, none of them resolvable by an implementer at the keyboard. **The layout amendment**: ADR-0003 D1's five directories become six, superseded rather than edited, with `ui/` named and the layout test's recorded set widened in the same change. **The gate-placement deviation**: r8 § 3 lines 400–403 compile the approval tool in conditionally; `walking-skeleton-step-lifecycle` ships run-time injection instead, and the ADR records that the shipped placement stands because it keeps approval outside the decision point's authority check. **The terminal-transition identity**: r8 § 4 line 460 and § 3 line 344 disagree about whether the worker may write a run-lifecycle type, and the ADR records that § 3's diagram is the reading kept, with the fence and the null `step_id` as what keeps § 4's disjointness intact.
- An ADR records a deviation from a ratified document; it does not amend one. The r9 consistency pass is named as owed in the spec's Follow-ons and is not attempted here.

**Done when:** the three records exist, the layout test is green against the widened set, and each criterion that rests on a deviation cites the record that carries it.

### T1: A clean run publishes with nobody watching

**Depends on:** T0

**Touches:** migrations/versions/**, src/**/domain/run_state.py, src/**/domain/events.py, src/**/worker/prerelease.py, src/**/worker/executor.py, src/**/worker/persistence.py, src/**/adapters/postgres/event_log.py, src/**/adapters/objectstore/**, src/**/api/health.py, src/**/api/main.py, contracts/openapi/runs.yaml, tests/e2e/**, tests/schema/**, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0301 reads the run's outcome end to end: terminal `run.completed`, an artifact published, no `approval.requested` appended.
- AC-0320 is the schema-level half and carries the `substrate` marker. Two assertions, and the second is the one that can fail for a real reason: the grant set after revision 0005 is still disjoint and still carries no direct `INSERT` on `events`; and with the append forced to fail, `runs.state` does not move. **Mutation proof is owed before this counts as coverage** — drop the single-transaction wrapper and the second assertion must red. A check that passes with the wrapper removed is asserting the happy path, which is the shape three of the last delivery's six dead checks had.
- AC-0302 inspects the tool set the model is offered at run time, which on the shipped placement is where conditionality is decidable at all. **Mutation proof is owed**: make the gate unconditional on a clean run and this must red. The criterion as previously written — over the compiled toolset — could not red under any mutation, because the shipped design never compiles the tool in.
- AC-0303 forces a pre-release failure and drives the suspension through to publication on a grant, which is what makes AC-0301's "clean" one branch of a real condition. It also reads back the appended grant and asserts it names the granting principal and carries the `require_distinct_approver` state — **read from the log, not from the value the test supplied**, which is the read-back-what-you-placed shape.
- AC-0321 drives a step past the cycle cap and asserts it fails with a recorded cause, then asserts a pool configuration declaring no cap still bounds the loop. The second half is what stops a configuration read satisfying the criterion.
- The liveness probe (DR4) is asserted by stalling the poll loop without killing the process and observing the probe fail — a probe that only checks process existence would pass, which is the failure mode it exists to catch.

**Approach:**
- Revision 0005 comes first and is expand-only: the run-terminal definer function granted to `app_worker`, the approval-grant path that works while `owner` is null, and their `EXECUTE` grants. Both are written against the lock ordering the existing functions use — `steps` before `runs` — because a third order is what the foundation's deadlock suite exists to catch.
- `awaiting_input` and its two events are authored into the transition table here, unexercised. No row carries the value, so `runs.state`'s CHECK is left alone; r8 § 10 line 1134 records that this needs no stored-state migration, and the CHECK is what would have to widen on the day something writes the state. The first spec to wire the input tool owes that, and owes r8 § 3's two safety constraints with it.
- The per-run spend ceiling pages rather than aborts.

**Done when:** AC-0301, AC-0302, AC-0303, AC-0320 and AC-0321 are green, each with its mutation proof written to `notes/verification-ledger.md`, and the liveness probe is observed failing on a stalled loop.

### T2: Real steps accumulate under a deadline that will not fire

**Depends on:** T1

**Touches:** deploy/compose.yaml, tests/e2e/**

**Tests:**
- Goal-based: a harness run produces at least the sample AC-0307 needs, and no step is failed by the deadline during it. A deadline that fires here would contaminate the p99 with truncated steps.

**Approach:**
- The deadline is set deliberately generous, with its only job being not to fire. It is replaced with the measured value in T4, which is why no criterion is demonstrated against it.
- This is the task that spends money. It is bounded by the spec's Ask-first threshold.

**Done when:** a sample of completed real steps exists in the event log, none truncated by the deadline.

### T3: A browser watches a run and survives losing the connection

**Depends on:** T1

**Touches:** src/**/api/stream.py, src/**/api/main.py, ui/**, ui/package.json, pyproject.toml, contracts/openapi/runs.yaml, AGENTS.md, tests/browser/**, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0304 and AC-0305 drive a real browser. AC-0305 forces ten disconnects with a writer active and sends a deliberately stale `after=0` on every reconnect. **The assertion is what the server sent**, captured from the wire: on each reconnect the first event emitted carries the sequence after the client's `Last-Event-ID`, and no reconnect re-emits an event the client already holds. Sequence completeness at the sink is asserted too, and is not sufficient on its own — the sink is idempotent on `(run_id, seq)`, so it would silently absorb a full replay from a server that ignored the header. **Mutation proof is owed**: delete the `Last-Event-ID` preference and AC-0305 must red. If it stays green the criterion is measuring the sink.
- AC-0322 drives a run whose agent-authored text carries markup and a link target and asserts the rendered page shows those characters literally, with no element created and no navigable anchor. **Mutation proof is owed**: render that text as HTML and this must red.
- AC-0323 sends a `Last-Event-ID` that is non-integer, negative, and far past the run's last sequence, and asserts each is refused rather than coerced or read as zero.
- The observed result is recorded in the verification ledger, because a rendered outcome is the evidence here.

**Approach:**
- Document the `Last-Event-ID` preference **and its bounds** in the contract file, so both are specified rather than emergent. The route is registered on the app in `src/ced/api/main.py`, because AC-0009 compares the *generated* OpenAPI document against the hand-authored contract and a served-but-unregistered route reds it.
- The client is deliberately small — an event list, a state badge, a cursor. Agent-authored text renders as text nodes only; typed domain artifacts render through the application's own components from structured fields, which is a different path and stays rich.

**Done when:** AC-0304, AC-0305 and AC-0322 are observed in a real browser and recorded with their mutation proofs, and AC-0323 is green.

### T4: The deadline is calibrated against a measurement, not a guess

**Depends on:** T2

**Touches:** src/**/ops/measure.py, src/**/adapters/aws/quotas.py, src/**/worker/pool.py, deploy/compose.yaml, pyproject.toml, AGENTS.md, docs/architecture/pydantic-ai-worker-runtime/operations.md, tests/ops/**, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0307 refuses to emit a p99 below the sample floor rather than reporting a figure the sample cannot support.
- AC-0308 recomputes the threshold from the same sample, so the two cannot be recorded from different runs.
- AC-0306 reads all three recorded values and asserts the ordering. This is the one measurement criterion that can red, and it reds if a later configuration change breaks the ordering.
- AC-0309 and AC-0310 cancel mid-stream. The distinguishing observation is named in the record, because from inside the coroutine an abandoned request and a terminated one look identical — the evidence has to come from the connection.
- AC-0311 reads the tokens-per-minute quota for the model in use through the Service Quotas API, capturing the Region from the resolved client rather than from configuration, because a quota recorded against the wrong Region is worse than none.

**Approach:**
- Set the real `step_deadline` from the measurement, in the same change that records it. **It is configured in two places and neither was named before**: `PoolConfig.step_deadline` in `src/ced/worker/pool.py` defaults to `None`, meaning no deadline at all, and no environment variable reaches it — `CED_STEP_BODY_SECONDS` is the offline stub's timer and is a different thing. T4 gives the field a real default and an environment surface, and sets it on both worker services in `deploy/compose.yaml`, or AC-0306 reads a configured value that does not exist.
- The Service Quotas call is sited under `src/ced/adapters/` because the AWS SDK import belongs there: `tests/architecture/dependency_direction.py` walks import statements, so the measurement command in `src/ced/ops/` reaches the quota through the adapter the way `src/ced/worker/executor.py` already reaches `boto3`. The Region is captured from the resolved client rather than from configuration, because a quota recorded against the wrong Region is worse than none.
- The measurement command ships as product code and gains a `[project.scripts]` entry, recorded in `AGENTS.md` § Build and test commands in the same change. ADR-0003 D3's "two deployables" governs distributions and services, not console scripts; an operator command that reads the log is neither, and the D3 comment in `pyproject.toml` is updated to say so rather than left to read as contradicted.
- If cancellation comes back *abandoned*, that is the recorded result.

**Done when:** AC-0307 through AC-0311 are recorded in the operations document with their sample sizes and platform, AC-0306 is green against the recorded values, and the configured `step_deadline` the criterion reads is the one the workers actually run with.

### T5: Analytical quality is re-baselined, whatever it says

**Depends on:** T2

**Touches:** src/**/eval/rebaseline.py, tests/eval/**, docs/specs/walking-skeleton-evidence/notes/rebaseline.md, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

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
- Name at least these substitutions: p99 measured on local containers rather than Fargate; lease reacquisition demonstrated with a second worker already running rather than a scheduler replacing a task; the Postgres results taken against a local container with a deliberately low deadlock timeout; the quarantine boundary verified against written cases rather than an adaptive adversary; and the browser criteria driven against a loopback API with no authentication, so nothing here establishes the stream's behaviour under an authenticated ingress. Name also what the new dependency tree costs: `ui/`'s packages are covered by no vulnerability scanner, which widens a gap `workspace.toml` already records.
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

- **Delivery:** five stacked PRs — T0, T1, T2+T3, T4+T5, T6. T0 is first and separate because its three records must exist before the code they govern, and a record written after the build it justifies is a rationalisation. T3 forks from T1 rather than following T2, so the browser work does not wait on a spend-bearing task.
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
- 2026-09-26: **spec and plan revised after the first pre-EXECUTE review round**, which ran the contract against the code its five siblings shipped between approval and execution. The contract had not been re-read against the tree and had drifted. Four owner decisions are baked in: a new definer function carries the run-terminal transition rather than widening `append_run_event` or granting it to a second role; the shipped run-time placement of the approval gate stands against r8 § 3, with AC-0302 re-sited onto the surface where conditionality is decidable; `ui/` is admitted by a superseding ADR; and the approver principal becomes a criterion rather than an accepted gap. Four criteria were added — AC-0320 the terminal-transition control, AC-0321 the cycle cap and its finite default, AC-0322 the plain-text rendering check, AC-0323 the `Last-Event-ID` bounds — and three amended: AC-0302's surface, AC-0303's attributability clause, AC-0305's wire-level observation. T0 was added ahead of T1. **Two claims were withdrawn as false**: that this spec adds no schema, in § Constraints and again in § Rollout's reversibility statement. **None widens authority and none relaxes a criterion**; AC-0302 and AC-0305 were each unfalsifiable as written and now can red.
