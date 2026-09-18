# Plan: Walking skeleton — foundation

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r7 §§ Event log and stream mechanism, Step execution, Identity. **No analogous production implementation exists** — this is the repository's first application code. The substitute is `spikes/phase-0/`: `privilege_test.py` and `schema.sql` for the `SECURITY DEFINER` split, `concurrency_test.py` for lock ordering and sequence density, `stream_resumption_spike.py` for the cursor projection. **Named deviation:** spike code is throwaway by its directory's own rule, so it is precedent for *shape* and never copied.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-foundation/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Governance, then the database, then the two things that sit on it.

The order is forced rather than preferred. This repository has no home for
source, and although the owner waived the RFC route on 2026-09-18 the layout
still gets a decision record — so T1 stays first, and is now a write rather
than a wait. Every durability claim in this spec is a claim about Postgres, so
the schema and its two append paths precede anything that appends.
The API and the pool are then independent of each other and both depend only on
the schema, which is the one place this plan's task graph forks.

The riskiest part is the privilege split, because it is the one mechanism here
that cannot be verified from application code. Postgres has no row-value grant,
so the split is built from revoked table privileges plus two `SECURITY DEFINER`
functions with disjoint `EXECUTE` grants, and the only honest test opens a real
connection as each role. Spike P1 established the shape; what is unproven is
that shape against the schema this delivery actually ships, which is why
AC-0005 exists rather than being inherited.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — the framework decision. **D5's 2.44.0 pin is superseded in part by ADR-0002 in T1**, to 2.45.0, on the owner's decision of 2026-09-18. No code in this spec imports the framework; the pin is recorded here because T1 is where decision records are authored.
- `runtime-architecture.md` r7 — ratified with its Known-at-ship gaps accepted **open**. They are limits of the design, not work this spec closes.
- ADR-0003, authored in T1 — the top-level layout. `AGENTS.md` § Development workflow would require an RFC; the owner waived that on 2026-09-18 under the same shaping-phase exception the charter amendment used, so the layout is recorded as a decision rather than proposed as one.
- **Out of scope:** everything the sibling specs own — the agent layer, the authorization and quarantine boundaries, the provider call, the run state machine, the browser stream, and the Phase 1 measurements.

## Changes asked of r7

The spec makes changing any item in `worker-runtime.md` § Changes this design
asks of r7 an Ask-first boundary, enforceable only if each carries a stated
disposition. This spec owns the schema-shaped ones.

| # | Change | Disposition |
| --- | --- | --- |
| 1 | `policy.decision` append becomes fenced | **Lands**, T4, via a `SECURITY DEFINER` fence function — **owned by a third `NOLOGIN` role, not by `worker`**. r4's preferred option was worker ownership; review established that a function's owner can always `DROP` or `ALTER` it, so that let the role the split distrusts disable the control constraining it. [ADR-0004](../../adr/0004-fence-function-owner.md) narrows item 1 on the owner's decision of 2026-09-18, keeping the privilege narrowing r4 wanted. `policy-writer` still gains no table access |
| 2 | Partial unique index for the derived idempotency key | **Lands**, T4, asserted by AC-0006 at the SQL level. The *behavioural* half — a duplicate terminating the step — belongs to `walking-skeleton-agent-runtime`, which owns the toolset that appends |
| 3 | Nullable `steps.pool_class` | **Lands**, T4. Read by T5's claim predicate; one class in MVP |
| 4 | Nullable `owner_scope` columns | **Lands**, T4. Read by nothing; taken now because backfilling ownership onto executed runs is guesswork |
| 5 | Scope-qualified object keys | **Deferred to `walking-skeleton-agent-runtime`**, which writes the first payload object. Named here so the one-way door has an owner |
| 11 | "No runtime identity holds both" read as a database-role property | **Lands**, T4 — the worker process authenticates as two roles and AC-0005 asserts the database refuses the reserved type |
| 6, 7, 8, 9, 10, 12 | `awaiting_input`; fragment narrowing; `may_exist`; per-integration credentials; `CredentialProvider`; `api` metric grant | **Not this spec's** — 6 and 10 belong to the siblings, 7 to the agent runtime, 8 and 9 are deferred follow-ons recorded there, and 12 feeds autoscaling in an AWS deployment that is out of scope entirely |

## Construction tests

**Integration tests:**
- One Compose bring-up that applies migrations, opens a connection as each database role, and asserts each role can do its own job and not another's. A split that also blocks the legitimate path proves nothing.
- One fault-injection suite driving real container kills, shared by AC-0010 and AC-0011 and reused by the evidence spec's cancellation measurement. AC-0011's drain clause is additionally asserted in process against the injected step body, because a signal's effect on the worker is observable there without a container boundary absorbing the interval.

**Manual verification:** none. Every criterion here is machine-checkable, which is a property of having put the browser in a sibling spec.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Decision rationale — `docs/adr/0002-*.md`, `docs/adr/0003-*.md` | T1 | ADR recording the pin; ADR recording the layout and the waiver | Layout on disk matches ADR-0003 |
| Interface compatibility — `contracts/openapi/runs.yaml` | T6 | Route-versus-contract agreement test | Contract and implementation agree under test |
| Maintainer procedure — `AGENTS.md` § Build and test commands | T2 | Commands added with the manifest that introduces them | Commands run green from a clean clone |
| Current architecture — `docs/architecture/README.md` | T7 | README names the built subsystems | Names match the repository |

## Design (LLD)

Shape is `mixed`; the sub-sections below are the pruned set.

### Design decisions

- **One Python package, two entry points.** API and worker share the domain and adapter layers and differ only in what they start. Two deployables from one image is what `worker-runtime.md` § How workers are provisioned specifies, and it keeps the dependency-direction test meaningful across both. Traces to: AC-0007.
- **Raw SQL through psycopg3, not an ORM.** The claim query, the fenced append and the lock ordering are the load-bearing mechanisms and were proven by spike P2 as specific statements. An ORM would put a query planner between the plan and what was proven. Traces to: AC-0003, AC-0004.
- **Rejected: deferring the privilege split to a later spec.** It is cheaper to build with the schema than to retrofit onto a corpus, and the sibling spec's policy decision point depends on the second connection already existing.

### Data & schema

Tables are `runs`, `steps`, `events`, `agent_role`, `integration_registry`,
`entitlements`. The last three are created here and populated by the agent
runtime spec, because a schema split across two specs is worse than a table
that waits.

`next_seq` is a column on `runs` updated inside the append transaction, never a
`bigserial` — a rolled-back `bigserial` allocation survives and leaves a hole.
Lock order is `steps` before `runs` on every path, the fence function included.
Migrations are Alembic and expand-only. Traces to: AC-0002, AC-0003, AC-0004,
AC-0005, AC-0006.

### Interfaces & contracts

Three routes in `contracts/openapi/runs.yaml`: `POST /runs`,
`GET /runs/{id}/snapshot`, and `GET /runs/{id}/events`. The stream endpoint is
built here only far enough to serve a cursor projection over committed events;
the browser client, reconnect semantics and their criteria belong to
`walking-skeleton-evidence`. The contract file is hand-authored — no
`api-contract` skill is installed — so it carries no rule enforcement beyond
AC-0009. Traces to: AC-0001, AC-0009 · `contracts/openapi/runs.yaml`.

### State & control flow

The step lifecycle only: claim with `FOR UPDATE SKIP LOCKED` filtered on
`pool_class`, stamp owner, bump `lease_epoch`, commit immediately; execute
outside any transaction; heartbeat-renew at TTL/3 fenced on `lease_epoch`;
release on completion, failure or suspension. TTL 60 s, heartbeat 20 s, poll
30 s, worst case 150 s.

The heartbeat reads run state in the same statement that renews the lease, so a
cancelled run and a lost fence arrive as one signal. The *run* state machine
that produces a cancelled state belongs to the evidence spec; this spec ships
the read and a state column it can already observe. Traces to: AC-0010, AC-0011.

### Failure, edge cases & resilience

Two orderings carry the durability story. The `steps` row lock is taken before
the `runs` row lock everywhere, because the `runs` lock serialises appends per
run and must be held briefly. And `next_seq` is updated inside the append
transaction, which is what makes a rolled-back append leave no hole.

The idempotency key is derived — `hash(run_id, step_id, tool_call_id)` — never
minted per attempt. Its limit is recorded rather than designed around: stable
across resume from the same history, not across a re-planned retry, because a
new model turn mints a new `tool_call_id`. Traces to: AC-0004, AC-0006.

### Dependencies & integration

New dependencies, recorded here before being added per `AGENTS.md`: `fastapi`,
`uvicorn`, `psycopg[binary]` 3.x, `alembic`, `pytest`, `pytest-asyncio`,
`ruff`, `mypy`. Local infrastructure: `postgres:17-alpine` and a MinIO
container. `pydantic-ai` 2.45.0 is pinned in the manifest by T2 so the
dependency-direction test has something to forbid, and is imported by no code
in this spec.

No external service is reached. There is no cloud credential in this spec's
test path.

## Tasks

### T1: The layout and the pin are recorded

**Depends on:** none

**Touches:** docs/adr/0002-pydantic-ai-version-pin.md, docs/adr/0003-repository-layout.md, workspace.toml

**Tests:**
- `python3 tools/hooks/pre-pr.py` exits 0 — it carries the ADR shape lint, the only mechanical check either record has, and it now covers both.
- After T2 lands, `find . -maxdepth 1 -type d` introduces no directory ADR-0003 omits. With the RFC waived this check is the only thing keeping the layout reviewed, so it is a test rather than a note.

**Approach:**
- ADR-0003 records the narrowest set T2–T7 actually need: `src/`, `tests/`, `contracts/`, `deploy/`. A directory recorded and unused is worse than one added later. It also records the owner's waiver and its date, so the exception is attributable rather than folklore.
- ADR-0002 **supersedes ADR-0001 D5 in part**, recording 2.45.0, the owner's decision date, and the offline probe as evidence. ADR-0001's other decisions stand.
- Register all three walking-skeleton specs in `workspace.toml` with their hard dependencies, and add the follow-ons the spec names.

**Done when:** both ADRs exist, `pre-pr.py` is green, and T2's directory check finds nothing ADR-0003 omits.

### T2: The project builds, lints, and refuses a misplaced import

**Depends on:** T1

**Touches:** pyproject.toml, src/**, tests/architecture/**, tools/lint-no-identifiers.py, AGENTS.md

**Tests:**
- AC-0007 is demonstrated by *deliberate violation*, not by a passing suite on clean code: the fixture writes each forbidden import, asserts the check fails, and removes it. A dependency-direction test never shown failing is not evidence.
- AC-0008 plants an account identifier embedded in a larger identifier and asserts the lint fails, then asserts a twelve-digit run inside a hex content hash does not trip it. Both halves are needed — a pattern that catches everything is not a gate either.

**Approach:**
- Layers under `src/`: `domain/`, `agents/`, `adapters/`, `api/`, `worker/`. The agent layers are empty here and filled by the sibling spec.
- The import check walks the AST rather than grepping, because a grep misses `importlib` and matches comments.
- The identifier-lint fix is a boundary change, already written and regression-tested during shaping; this task adds the test that keeps it fixed.
- Add install, build and test commands to `AGENTS.md` here — the same change that introduces them, verified from the manifest, per that file's own rule.

**Done when:** AC-0007 and AC-0008 red on their injected violations and green without them, and the repository gates pass.

### T3: A migration applies to an empty database

**Depends on:** T2

**Touches:** migrations/**, deploy/compose.yaml

**Tests:**
- Goal-based: `alembic upgrade head` against a fresh container exits 0, and `alembic downgrade` is not offered, because migrations are expand-only.

**Approach:**
- Compose brings up Postgres and MinIO. `deadlock_timeout` is set to 200 ms in the test container, matching spike P2, and that qualification travels with every result from T4.

**Done when:** a clean `docker compose up` plus migration leaves a schema the next task can open connections against.

### T4: The event log appends densely, fenced, and refuses a forged decision

**Depends on:** T3

**Touches:** src/**/domain/events.py, src/**/adapters/postgres/**, migrations/**, tests/event_log/**

**Tests:**
- AC-0003 reuses spike P2's shape — eight concurrent writers, 25 appends each — against the shipped schema rather than the spike's.
- AC-0004 forces a stale `lease_epoch` and asserts the sequence after rollback is still dense. That the rolled-back attempt consumed no number is the whole reason `next_seq` is a row update.
- AC-0005 opens a real `worker`-role connection, so the refusal comes from the database. It also asserts each role *can* do its own job, because a split that blocks the legitimate path proves nothing.
- AC-0006 inserts two `tool.invoked` events carrying the same derived key and asserts the second raises a unique violation.
- AC-0002 forces the step insert to fail and asserts all three rows are absent.
- A mixed-order writer is expected to deadlock, asserting the lock-ordering rule by showing it failing. A rule that cannot be shown failing is not a rule.

**Approach:**
- Two append paths, worker-fenced and run-lifecycle unfenced, as r7 specifies. The `SECURITY DEFINER` functions use `session_user`, not `current_user` — inside a definer function `current_user` is the definer, and an audit trail built on it names the wrong principal every time.

**Done when:** AC-0002 through AC-0006 are green and the mixed-order case is observed deadlocking.

### T5: A killed worker loses at most 150 seconds

**Depends on:** T4

**Touches:** src/**/worker/pool.py, deploy/compose.yaml, tests/fault_injection/**

**Tests:**
- AC-0010 kills a real worker container mid-step and reads wall-clock to reacquisition from the event log, not from a log line.
- AC-0011 sends `SIGTERM` and asserts reacquisition inside one poll interval. Without this the two recovery paths are indistinguishable at 150 s.
- The step body under test is a sleep, not a model call, so this suite needs no credential and no spend.

**Approach:**
- The pool executes an injected step body. The agent runtime spec supplies the real one; here it is a stub, which is what keeps this spec's suite offline.
- A second worker is running throughout, and the criterion records that "no operator action" holds because the replacement already existed rather than because a scheduler created one.

**Done when:** AC-0010 and AC-0011 are green against real container kills.

### T6: A run starts over HTTP and is readable

**Depends on:** T4

**Touches:** src/**/api/**, contracts/openapi/runs.yaml, tests/api/**

**Tests:**
- AC-0001 drives the real ASGI app rather than a mocked router.
- AC-0009 compares the served OpenAPI document against the committed contract file, so the two cannot drift silently.

**Approach:**
- Three routes. The events route serves the cursor projection and closes on a terminal event; its reconnect semantics and browser criteria belong to the evidence spec.
- The `api` identity holds no model authority and no unqualified `events` insert, which T4's grant tests already cover.

**Done when:** AC-0001 and AC-0009 are green.

### T7: The record says what this spec established and what it did not

**Depends on:** T5, T6

**Touches:** docs/architecture/README.md, spikes/README.md

**Tests:**
- `python3 .agents/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green. The script is committed at that path, so a clean clone can run it; T2 adds it to `AGENTS.md` alongside the other gates.

**Approach:**
- State plainly that the Postgres results are against a local container with `deadlock_timeout` at 200 ms, not RDS or Aurora, and that AC-0010's "no operator action" rests on a second worker already running rather than on a scheduler replacing a task. Both are substitutions this spec makes and neither is what a deployed fleet would establish.

**Done when:** the status lint is green and the record distinguishes what was established from what was substituted.

## Rollout

- **Delivery:** four stacked PRs — T1, T2+T3, T4, T5+T6+T7. Each leaves the repository working and is independently reviewable. T4 is sized as its own PR deliberately: it carries the schema, both append paths, the privilege split and five suites, and the tail-triage rule puts a task of that shape on its own.
- **Review shape:** T4 is **DEEP** — the schema, the grant matrix, the definer functions and the append paths are dependency-ordered layers within one task, and it is the task most likely to exceed a reviewable diff. If it does, it splits at the seam between the schema and the append paths, which has no dependency running backwards. Every other task is well under the threshold.
- **Reversible:** entirely. Nothing is deployed; the rollback unit is a `git revert` of a layer. The one-way door is `owner_scope`, taken now because backfilling ownership onto executed runs is guesswork.
- **Infrastructure:** local Docker Compose only — Postgres and MinIO. No AWS, no cloud credential.
- **Deployment sequencing:** migrations precede the code that reads them within each PR; ADR-0003 precedes every directory it names.

## Risks

- **The privilege split is the one mechanism that cannot be verified from application code.** If the grant matrix is wrong, the failure is silent until an audit. Mitigated by AC-0005 asserting both the refusal and the legitimate path.
- **Local Postgres is not RDS.** Connection pooling, failover and `deadlock_timeout` defaults are untested, and the deliberately low timeout makes deadlocks surface faster than production would. Recorded with the result rather than mitigated.
- **T4 is the largest task here.** Named above with its split seam, so an oversized diff has a planned response rather than an improvised one.
- **The waived RFC removes a review the layout would otherwise have had.** Nothing now blocks a wrong directory set except ADR-0003 and T2's check, and the layout is the one decision every later task inherits. Mitigated by recording the narrowest set the plan uses and by making the check a test rather than a note.
- **The sibling specs depend on this one.** A schema change discovered while building the agent runtime is an amendment to a shipped spec, which is expensive. Mitigated by creating `agent_role`, `integration_registry` and `entitlements` here even though nothing in this spec populates them.

## Changelog

- 2026-09-18: amended spec approved by eugenelim; amended plan approved by eugenelim
- 2026-09-18: **AC-0011 amended** — the criterion named no origin for its poll interval, and measured from signal delivery the mechanism's worst case exceeded it. The amendment names the origin and splits the obligation into a drain bound and a poll bound. Owner decision 2026-09-18; grounds in `notes/verification-ledger.md` § Contract amendment. T5's `Tests` field updated for the second clause; no other task changes.
- 2026-09-18: initial plan. Split out of a single `walking-skeleton` spec after three review rounds did not converge and the findings clustered by subsystem — the agent and authorization work carried nearly every blocker, which is the seam this split follows.
- 2026-09-18: spec approved by eugenelim
- 2026-09-18: plan approved by eugenelim
