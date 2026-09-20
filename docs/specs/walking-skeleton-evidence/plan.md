# Plan: Walking skeleton — evidence

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8 § 3 Runtime Model (the run state machine, the approval gate), § 4 Contracts and Invariants (the event log and stream mechanism) and § 9 Decisions, Alternatives, and Risks (the primary page threshold); [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 3 Runtime Model (the approval gate) and § 2 Structural Model (the pool). **No analogous production implementation exists.** The substitute is `spikes/phase-0/stream_resumption_spike.py` for the cursor projection and `Last-Event-ID` preference, and `quarantine_quality_spike.py` for the A/B comparison AC-0312 re-runs. **Named deviation:** the resumption spike drove an HTTP client, not a browser, so it is precedent for the server's behaviour and not for the client's.

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
- **Hard dependencies:** `walking-skeleton-foundation` (schema, append paths, pool, API), `walking-skeleton-role-compilation` (the compiled agent and the quarantine boundary), `walking-skeleton-authority-containment` (the decision point) and `walking-skeleton-step-lifecycle` (the provider call, the step deadline, persistence). This spec adds no schema and no agent.
- **Out of scope:** the AWS deployment, by the owner's decision of 2026-09-18; the assistant surface and `legible-refusal-and-readiness`, both Draft and unauthorised.

## DR dispositions

| DR | Decision | Disposition |
| --- | --- | --- |
| DR1 | Publication is an executor transition, not a tool | **Lands**, T1 — the transition is the application's; the agent's only lever is the contentless tool the agent-runtime spec built |
| DR4 | The liveness probe is the out-of-loop watchdog | **Lands**, T1 — the probe fails when no heartbeat has been *attempted* within twice the lease TTL, which is what makes it catch a starved event loop rather than merely a dead process |
| DR5 | Rejection resumes the conversation, capped at three cycles | **Lands**, T1, unmeasured. r5 calls the cap arbitrary and asks Phase 1 to replace it with an observed number; this skeleton runs too few cycles to observe one, and the spec's Follow-ons records that plainly rather than implying the cap is now evidence-based |
| DR6 | Three spend ceilings | **Partly here** — the per-run ceiling checked by the executor before dispatching each step lands in T1. It **pages rather than aborts**, because for a single operator killing a legitimate long analysis is the worse error. The per-step ceilings are the agent-runtime spec's; the per-account budget alarm is outside the application |
| DR7 | Analytical quality is re-baselined at Phase 1 | **Lands**, T5 |
| DR13 | `trust_class` is a construction | **Agent-runtime's**, and AC-0313 measures what its narrowing costs |
| DR2, DR3, DR8, DR9, DR10, DR11, DR12 | — | **Not this spec's** — owned by the sibling specs, triggered at Phase 2, or already applied |

## Amendments asked of the parent architecture

| # | Change | Disposition |
| --- | --- | --- |
| 6 | The `awaiting_input` run state and its two events | **Lands**, T1, as an authored but unexercised state. No role in this skeleton calls the input tool, so no criterion reads it; the state exists because adding one later is a migration and the transition table is authored once |
| 12 | `api` gains the metric-publishing grant | **Not applicable at this scope** — it feeds queue-depth autoscaling, MVP runs a fixed worker count, and there is no AWS deployment here |
| 1–5, 7–11 | — | **The sibling specs'**, each with a disposition recorded there |

## Construction tests

**Integration tests:**
- One clean-run end-to-end through local Compose: requested, planned, quarantine classifies, analysis calls its tool, artifact published, stream closed, no human. This is the spine AC-0301 reads and the harness every measurement task reuses to generate steps.
- One flagged-run end-to-end that suspends, releases its lease, and resumes to publication on a grant, so the clean path is a branch rather than the only path.

**Manual verification:**
- AC-0304 and AC-0305 are driven by a real browser and the observed result recorded in the verification ledger. A rendered outcome is the evidence; a green assertion over a response body is not.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
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
their result commits as an event; the approval-gated tool is present in the
compiled toolset only when a check failed. On a clean run there is no gated
tool and no human in the path, which is the ratified charter amendment this
spec must not reverse. Traces to: AC-0301, AC-0302, AC-0303.

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

New dependencies, recorded before being added per `AGENTS.md`: `vite`, `react`
for the browser client, and a browser-driving test dependency for AC-0304 and
AC-0305. Everything else is inherited.

External: Amazon Bedrock, reached under the scoped assumed role the
agent-runtime spec established, by the tasks that generate real steps.
Service Quotas is read once by T4. SEC EDGAR is not reached at all.

## Tasks

### T1: A clean run publishes with nobody watching

**Depends on:** none (within this spec; the sibling specs are hard dependencies)

**Touches:** src/**/domain/run_state.py, src/**/worker/prerelease.py, src/**/api/health.py, tests/e2e/**

**Tests:**
- AC-0301 reads the run's outcome end to end: terminal `run.completed`, an artifact published, no `approval.requested` appended.
- AC-0302 inspects the compiled toolset directly. This is the assertion that catches the gate being made unconditional — a clean run can complete while a gated tool it never triggered still sits in the stack, so the outcome alone cannot see it.
- AC-0303 forces a pre-release failure and drives the suspension through to publication on a grant, which is what makes AC-0301's "clean" one branch of a real condition.
- The liveness probe (DR4) is asserted by stalling the poll loop without killing the process and observing the probe fail — a probe that only checks process existence would pass, which is the failure mode it exists to catch.

**Approach:**
- `awaiting_input` and its two events are authored into the transition table here, unexercised. Adding a run state later is a migration; authoring the table once is not.
- The per-run spend ceiling pages rather than aborts.

**Done when:** AC-0301, AC-0302 and AC-0303 are green and the liveness probe is observed failing on a stalled loop.

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

**Touches:** src/**/api/stream.py, ui/**, contracts/openapi/runs.yaml, tests/browser/**

**Tests:**
- AC-0304 and AC-0305 drive a real browser. AC-0305 forces ten disconnects with a writer active and sends a deliberately stale `after=0` on every reconnect, so a server trusting the query parameter would replay from the beginning and the duplicate would be visible on the page. The assertion is sequence completeness at the sink rather than timing, which is what spike 3 used and what keeps a timing-sensitive test from being flaky.
- The observed result is recorded in the verification ledger, because a rendered outcome is the evidence here.

**Approach:**
- Document the `Last-Event-ID` preference in the contract file, so the behaviour is specified rather than emergent.

**Done when:** AC-0304 and AC-0305 are observed in a real browser and recorded.

### T4: The deadline is calibrated against a measurement, not a guess

**Depends on:** T2

**Touches:** src/**/ops/measure.py, docs/architecture/pydantic-ai-worker-runtime/operations.md

**Tests:**
- AC-0307 refuses to emit a p99 below the sample floor rather than reporting a figure the sample cannot support.
- AC-0308 recomputes the threshold from the same sample, so the two cannot be recorded from different runs.
- AC-0306 reads all three recorded values and asserts the ordering. This is the one measurement criterion that can red, and it reds if a later configuration change breaks the ordering.
- AC-0309 and AC-0310 cancel mid-stream. The distinguishing observation is named in the record, because from inside the coroutine an abandoned request and a terminated one look identical — the evidence has to come from the connection.
- AC-0311 reads the tokens-per-minute quota for the model in use through the Service Quotas API, capturing the Region from the resolved client rather than from configuration, because a quota recorded against the wrong Region is worse than none.

**Approach:**
- Set the real `step_deadline` from the measurement, in the same change that records it.
- If cancellation comes back *abandoned*, that is the recorded result.

**Done when:** AC-0307 through AC-0311 are recorded in the operations document with their sample sizes and platform, and AC-0306 is green against the recorded values.

### T5: Analytical quality is re-baselined, whatever it says

**Depends on:** T2

**Touches:** src/**/eval/rebaseline.py, docs/specs/walking-skeleton-evidence/notes/rebaseline.md

**Tests:**
- AC-0312 re-runs the A/B against the same recorded 10-Q and reports against the same three loss categories, so the result is comparable to the original rather than merely new. The producer tuple labels the run; without it the comparison has no identity.
- AC-0313 separates two costs the original conflated: what the quarantine boundary costs, and what the narrowed admitted set costs under DR13.

**Approach:**
- Same filing, same section, same question. Changing the input would make the comparison meaningless.
- A falsified result is recorded as falsified. Spike 4 was falsified as run and that changed the design rather than the plan; the same standard applies.

**Done when:** AC-0312 and AC-0313 are recorded with their costs and their limits.

### T6: The record says what Phase 1 did not establish

**Depends on:** T3, T4, T5

**Touches:** spikes/README.md, docs/architecture/README.md, docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md

**Tests:**
- AC-0314 is checked by reading: for each measurement, the record must name the substitution and the property a deployed fleet would establish that this one does not. A section that lists only results satisfies nothing.
- `python3 .agents/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green across all three walking-skeleton specs, which is where the three-spec split gets checked as a whole rather than one at a time.

**Approach:**
- Report hypothesis checks separately from setup and teardown, per that file's own standard that a check which cannot fail is not evidence.
- Name at least these substitutions: p99 measured on local containers rather than Fargate; lease reacquisition demonstrated with a second worker already running rather than a scheduler replacing a task; the Postgres results taken against a local container with a deliberately low deadlock timeout; and the quarantine boundary verified against written cases rather than an adaptive adversary.
- Move the `STATUS: PLANNED` markers only for what now exists. The r8 consistency pass stays a named follow-on.

**Done when:** AC-0314 holds, the status lint is green across all three specs, and Phase 1's exit criteria are recorded as met.

**`awaiting_input` is authored without its safety constraints.** r8 § 3 makes
operator-supplied text trusted *as instruction* and honest only because the
answer is admitted at the acting role's existing ceiling and cannot widen it,
and because the request and the answer are both recorded as events. This plan
authors the state and its two events deliberately and unexercised; neither
constraint is built, and no criterion reads them. The first spec to wire the
input tool owes both, and inherits a transition table that looks finished.

## Rollout

- **Delivery:** four stacked PRs — T1, T2+T3, T4+T5, T6. T3 forks from T1 rather than following T2, so the browser work does not wait on a spend-bearing task.
- **Review shape:** no task here is DEEP. T1 is the largest and is **MIXED** — the state machine, the pre-release checks and the liveness probe — and splits at the seam between the transition table and the gate if it outgrows one reviewable unit. T4 and T5 are small in code and large in recorded output, which is the inverse of the usual shape and the reason their `Done when` names a document rather than a suite.
- **Reversible:** entirely. Nothing is deployed. No one-way door: this spec adds no schema and no key derivation.
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
