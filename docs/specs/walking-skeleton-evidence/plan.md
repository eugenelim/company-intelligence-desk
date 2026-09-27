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
- **It adds no schema.** The two append paths and the `steps.approval_cycles` column this work once carried moved to `walking-skeleton-run-state` on 2026-09-27, with the migration. What remains here reads the log and renders it. **That claim was false twice before** — in this same field and in § Rollout — while publication and the approval grant were still in scope, and it is true now only because those left.
- **Hard dependency on a sibling that is not yet built:** `walking-skeleton-run-state` ships the transitions, publication, the approval gate and its interface. T1's sample needs completed steps that only publication produces; T2's browser criteria need the terminal event that closes a stream.
- **`ui/` is a sixth top-level directory.** ADR-0003 D1 records five and D2 makes a sixth an Ask-first boundary needing a superseding record; `tests/architecture/test_recorded_layout.py::test_no_top_level_directory_is_unrecorded` reds on any tracked directory neither ADR-0003 nor ADR-0007 names. Owner decision 2026-09-26: an ADR amends the recorded layout, written in T0 before T3 tracks a file under it. The shaping-phase exception has not expired, so an ADR is the route and no RFC is owed.
- **Out of scope:** the AWS deployment, by the owner's decision of 2026-09-18; the assistant surface and `legible-refusal-and-readiness`, both Draft and unauthorised.

## DR dispositions

| DR | Decision | Disposition |
| --- | --- | --- |
| DR1 | Publication is an executor transition, not a tool | **`walking-skeleton-run-state`'s**, T2 there |
| DR4 | The liveness probe is the out-of-loop watchdog | **`walking-skeleton-run-state`'s**, T2 there |
| DR5 | Rejection resumes the conversation, capped at three cycles | **`walking-skeleton-run-state`'s**, T3 there, under its AC-0321 |
| DR6 | Three spend ceilings | **`walking-skeleton-run-state`'s** per-run half, T3 there under its AC-0325. The per-step ceilings are the agent-runtime spec's; the per-account alarm is outside the application |
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
- One clean-run end-to-end through local Compose, driven against the publication path `walking-skeleton-run-state` ships. It is not this spec's criterion — it is the harness every measurement task reuses to generate real steps.

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
| Recorded decisions — `docs/adr/` | T0 | The layout record superseding ADR-0003 D1 | Cited from the task that rests on it, and the layout test is green against the widened recorded set |
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

The run state machine and the approval gate are `walking-skeleton-run-state`'s. This spec reads what they commit.

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
- One decision, one record, not resolvable by an implementer at the keyboard. **The layout amendment**: ADR-0003 D1's five directories become six, superseded rather than edited, with `ui/` named and the layout test's recorded set widened in the same change. The same record settles two more layout questions this spec would otherwise decide in passing — that `src/ced` gains `ops/` and `eval/` beyond D3's five layers, which the layout test admits by a subset assertion and so records nowhere; and that D3's "two deployables" governs distributions and services rather than console scripts, so T4's measurement command may take a third `[project.scripts]` entry. Both were about to be settled in a task's Approach and a `pyproject.toml` comment, which is the class this task exists to prevent. The gate-placement and append-path records moved to `walking-skeleton-run-state`'s T0 with the criteria that rest on them.

### T1: Real steps accumulate under a deadline that will not fire

**Depends on:** T0, and `walking-skeleton-run-state` shipped

**Touches:** deploy/compose.yaml, tests/e2e/**

**Tests:**
- Goal-based: a harness run produces at least the sample AC-0307 needs, and no step is failed by the deadline during it. A deadline that fires here would contaminate the p99 with truncated steps.

**Approach:**
- **The sample runs with no `step_deadline` configured at all**, which is the honest description of what happens here. An earlier revision said the deadline "is set deliberately generous" — but `PoolConfig.step_deadline` defaults to `None`, no environment variable reaches it, and T4 is the task that builds that surface. A generous value was therefore unsettable at the moment T2 runs. `None` means no deadline, which satisfies this task's only requirement — that nothing truncates a step and contaminates the p99 — for a more direct reason than a large number would.
- The real value is set in T4 from the measurement, which is why no criterion is demonstrated against whatever is in force here.
- **This is the task that spends money, and no mechanism in this delivery halts it.** The spec's Ask-first `$5` threshold is an instruction to the operator, and the per-run ceiling AC-0325 asserts **pages rather than aborting** by r5's ratified decision — so a run past the ceiling keeps calling the provider and the page is a notification, not a brake. An earlier revision of this bullet called that ceiling "the mechanical bound in this delivery", which it is not. What bounds T2 in practice is the operator watching: the sample is 30 completed steps against a cheap model, the re-baseline cost $0.022 the first time, and the Ask-first threshold stops the task rather than the system stopping it.

**Done when:** a sample of completed real steps exists in the event log, none truncated by a deadline.

### T2: A browser watches a run and survives losing the connection

**Depends on:** T0, and `walking-skeleton-run-state` shipped

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

### T3: The deadline is calibrated against a measurement, not a guess

**Depends on:** T1

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

### T4: Analytical quality is re-baselined, whatever it says

**Depends on:** T1

**Touches:** src/**/eval/**, tests/eval/**, docs/specs/walking-skeleton-evidence/notes/rebaseline.md, docs/specs/walking-skeleton-evidence/notes/verification-ledger.md

**Tests:**
- AC-0312 re-runs the A/B against the same recorded 10-Q and reports against the same three loss categories, so the result is comparable to the original rather than merely new. The producer tuple labels the run; without it the comparison has no identity.
- AC-0313 separates two costs the original conflated: what the quarantine boundary costs, and what the narrowed admitted set costs under DR13.

**Approach:**
- Same filing, same section, same question. Changing the input would make the comparison meaningless.
- A falsified result is recorded as falsified. Spike 4 was falsified as run and that changed the design rather than the plan; the same standard applies.

**Done when:** AC-0312 and AC-0313 are recorded with their costs and their limits.

### T5: The record says what Phase 1 did not establish

**Depends on:** T2, T3, T4

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

- **Delivery:** five PRs — T0, then T1 and T2 branching from it in parallel, then T3+T4, then T5. T2 does not wait on the spend-bearing T1, and branching rather than stacking is what makes that true of the merge as well as the dependency. T0 is first and separate because its records must exist before the code they govern, and a record written after the build it justifies is a rationalisation. **T2 and T3 ship separately**, which an earlier revision did not do while claiming the benefit: it bundled them as one PR and justified the arrangement with "T3 forks from T1 rather than following T2, so the browser work does not wait on a spend-bearing task" — true of the dependency and false of the delivery unit, since a shared PR makes T3's merge wait on T2 anyway. Split, the rationale holds.
- **Review shape:** T1 is now **DEEP** rather than MIXED and is decomposed in dependency order — revision 0005 and its grants; the transition table and the terminal commit; the pre-release checks and the gate; the cycle cap and the liveness probe — each leaving the repository working. It grew when the append paths turned out to be missing rather than present, and an ambiguous shape is DEEP by the sizing rule. T4 and T5 are small in code and large in recorded output, which is the inverse of the usual shape and the reason their `Done when` names a document rather than a suite.
- **Reversible:** entirely. Nothing is deployed, this spec adds no schema and no key derivation, and the one-way door that made an earlier revision qualify this line went with the state machine.
- **Infrastructure:** the foundation spec's local Compose plus a browser for T3. Bedrock is reached under the scoped role for T2 and T5.
- **Deployment sequencing:** T4 must set `step_deadline` in the same change that records the measurement, or the recorded value and the configured one can diverge silently.

## Risks

- **Cancellation comes back "abandoned".** Plausible, given synchronous botocore. The step stays bounded by the hard timeout the agent-runtime spec provides, so no functional criterion fails; what degrades is the operational story, and AC-0310 exists to state it rather than hide it.
- **p99 on local containers is not p99 on Fargate.** The step is model-bound so the figure should mostly carry, but "mostly" is not measured. AC-0314 records it and the deployment follow-on re-measures.
- **The browser criteria are the flakiest tests in the delivery.** Ten forced disconnects against a live writer is inherently timing-sensitive. Mitigated by asserting sequence completeness at the sink rather than timing.
- **The re-baseline may be falsified again.** Not a delivery risk; a recorded result. Named so nobody treats a bad number as a task to retry.
- **This spec cannot start until both siblings ship.** It is the one place the three-spec split adds real serialisation, and it is unavoidable: there is nothing to measure until there is a system.

## Changelog

- 2026-09-27: **the run state machine was split out into `walking-skeleton-run-state`** by owner decision, after a fourth pre-EXECUTE review round found this layer failing in a shape more criteria could not fix: publication, the approval grant and the spend-ceiling page each needed an append path no shipped identity could use, discovered one criterion at a time; the approval grant had no interface a person could reach; and ten of r8 § 3's eleven transitions were unowned, so the browser's state badge would have read `requested` for a whole run. Seven criteria moved unchanged in substance — AC-0301, AC-0302, AC-0303, AC-0320, AC-0321, AC-0324, AC-0325 — taking the migration, the two ADRs about append identity and gate placement, and the old T1 with them. What stays is what four rounds found converging: the browser stream, the four measurements, the re-baseline and the Phase 1 record.

- 2026-09-18: initial plan. Split out of a single `walking-skeleton` spec after three review rounds did not converge and the findings clustered by subsystem. This spec took the measurement and presentation criteria; the two uncomfortable outputs — an abandoned cancellation and a second falsification — are written as recordable results rather than bars, which is the main thing the split let this plan say clearly.
- 2026-09-18: spec approved by eugenelim
- 2026-09-18: plan approved by eugenelim
- 2026-09-26: **the pair was hand-reset to `Draft` and `Drafting`, and re-approval is owed to the owner before EXECUTE.** Both revisions below add acceptance criteria to a contract that was `Approved` on 2026-09-18 with its baseline never sealed, and the plan's own contract block admits substantive change only while Status is `Drafting`. No documented lifecycle route covers that window: `delivery-contract-lifecycle.md` makes the controlled amendment unavailable outside `CODE-IMPLEMENTATION`, and its status reset is the recovery for a *rejected* gate, which is not what happened. The conflict is registered in `workspace.toml` `[backlog].open` as `no-lifecycle-route-for-widening-an-approved-unsealed-contract`, surfaced during the sibling spec's amendment on 2026-09-22, and the route taken there — hand reset, amend, re-approval left owed — is the precedent followed here. Recorded rather than resolved, per `AGENTS.md` § Scoped instructions; whichever skill reference owns the rule is where a remedy lands. **The first revision left both statuses at `Approved` and recorded none of this, which the round-2 review caught.**
- 2026-09-26: **second revision, after the second pre-EXECUTE review round** — 26 adjudicated findings across both reviewers, 9 at blocker tier. Three owner decisions: AC-0320's no-bypass claim is **narrowed to what the applied grant set can decide** rather than revoking `app_worker`'s table-level `UPDATE ON runs`, which `0001_base_schema.py` records as r7's identity table verbatim and declines to narrow unilaterally — the retained bypass becomes an AC-0314 residual; the API **serves the built browser client** so page and API share an origin and no CORS middleware exists at all; and AC-0306 is **restated as a regression guard** with § Testing Strategy's claim that it could red withdrawn, because the deadline it orders is derived from the p99 it orders against. Three criteria added — AC-0324 the approval-grant append path's identity, AC-0325 the per-run spend ceiling, AC-0326 the origin posture. Six amended: AC-0303 gained a two-state assertion and a determinism mechanism and dropped an overclaim, AC-0320 gained four predicates and lost a false universal, AC-0321 gained durability across a worker handoff, AC-0322 was restated at the class so the typed-artifact path is no longer exempt, AC-0323 gained an upper bound and a refusal status, AC-0314 gained five named residuals. **The contract line was corrected**: the stream is a fourth operation, not an extension — `/runs/{run_id}/events` serves paged JSON and no `text/event-stream` exists anywhere. **The DR6 defect was repaired at the class rather than on the reported path**: the first revision fixed DR5's empty disposition and left DR6's identical one, which is how the same defect returns.
- 2026-09-26: **spec and plan revised after the first pre-EXECUTE review round**, which ran the contract against the code its five siblings shipped between approval and execution. The contract had not been re-read against the tree and had drifted. Four owner decisions are baked in: a new definer function carries the run-terminal transition rather than widening `append_run_event` or granting it to a second role; the shipped run-time placement of the approval gate stands against r8 § 3, with AC-0302 re-sited onto the surface where conditionality is decidable; `ui/` is admitted by a superseding ADR; and the approver principal becomes a criterion rather than an accepted gap. Four criteria were added — AC-0320 the terminal-transition control, AC-0321 the cycle cap and its finite default, AC-0322 the plain-text rendering check, AC-0323 the `Last-Event-ID` bounds — and three amended: AC-0302's surface, AC-0303's attributability clause, AC-0305's wire-level observation. T0 was added ahead of T1. **Two claims were withdrawn as false**: that this spec adds no schema, in § Constraints and again in § Rollout's reversibility statement. **None widens authority and none relaxes a criterion**; AC-0302 and AC-0305 were each unfalsifiable as written and now can red.
