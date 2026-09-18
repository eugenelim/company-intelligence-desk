# Spec: Walking skeleton — foundation

- **Status:** Approved <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r7, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r4, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md), ADR-0003 (repository layout — a forward reference, created by T1 of this spec)
- **Brief:** none — descends from `runtime-architecture.md` § Rollout Phase 1
- **Discovery:** none
- **Contract:** [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml) — a forward reference, created by T6 of this spec
- **Shape:** mixed

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Boundaries`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Objective`, `Durable Outputs`, `Follow-ons` and `Assumptions`
> are working material, corrected in place without an amendment.

## Objective

The first of three specs that together deliver the Phase 1 walking skeleton.
This one builds everything the agent layer stands on and nothing that reasons.

A run starts over HTTP and is readable. Its events append densely and in order
under concurrent writers, on two paths whose lock ordering is the ratified one,
with a database that refuses the worker role the reserved event type rather
than trusting the application not to write it. A pool of workers claims steps
under leases, renews them fenced on an epoch, and gives a step back within
150 seconds when its worker is killed. Nothing here calls a model.

Success is that the durability and identity claims the architecture rests on
stop being prose. The reader who benefits is the engineer the charter names,
who can run this and watch a lease survive a `docker kill`.

**Its siblings.** `walking-skeleton-agent-runtime` builds the reasoning step,
the authorization boundary and the quarantine boundary on top of this.
`walking-skeleton-evidence` adds the run state machine, the browser stream and
the Phase 1 measurements. All three are needed before Phase 1's exit criteria
are met; this one is the hard dependency of the other two.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Decision rationale | Applicable — repository layout is a new decision, and the framework version pin moves off ADR-0001 D5 | `docs/adr/0002-*.md`, `docs/adr/0003-*.md` | work-loop | ADR recording the pin with its grounds; ADR recording the layout and the owner's waiver of the RFC route | Both exist and the layout on disk matches ADR-0003 |
| Interface compatibility | Applicable — the API surface is the first published contract, consumed by the sibling specs | `contracts/openapi/runs.yaml` | work-loop | A test asserting served routes match the contract | Contract and implementation agree under test |
| Maintainer procedure | Applicable — no install, build, or test command exists in the repository today | `AGENTS.md` § Build and test commands | work-loop | Commands added in the change that introduces them, verified from the manifest | Commands run green from a clean clone |
| Current architecture | Applicable — this is the first code the architecture describes | `docs/architecture/README.md` | work-loop | README names the built subsystems | Names match what the repository contains |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Boundaries

### Always do

- Treat `runtime-architecture.md` r7 and `worker-runtime.md` r4 as ratified. Implement what they specify; where implementation shows one of them is wrong, stop and say so rather than designing around it.
- Honour the ordering and identity rules of `worker-runtime.md` § Changes this design asks of r7 item 1 as binding: lock order, write order, and definer identity. The mechanism is the plan's; the obligation is here by reference so it has one home.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision — the DR decisions, ADR-0001's decisions, or the changes `worker-runtime.md` asks of r7. The plan gives each change asked of r7 a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Creating a top-level directory ADR-0003 does not name. The RFC route is waived, not the record: a directory nobody wrote down is still an unreviewed structural change.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No top-level directory that ADR-0003 does not name.** The owner waived `AGENTS.md`'s RFC requirement for this delivery on 2026-09-18, under the same shaping-phase exception the charter amendment used. The waiver removes the proposal process, not the durable record.
- **No AWS SDK import outside `adapters/`, and no `pydantic_ai` import outside `agents/` and `adapters/`.** Weakening the test to pass the build is the failure this gate exists to catch.
- **No real personal identifier, account id, ARN, or absolute home path in any committed file** — including one embedded inside a larger identifier, which is the shape that reached a draft of this spec before the gate was fixed.
- **No `bigserial` for the per-run event sequence.** A rolled-back allocation survives and leaves a hole, which is the defect the row-update counter exists to avoid.

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0002, AC-0003, AC-0004, AC-0005, AC-0006)** — the compressible invariants of the event log and its privilege split. Each has a statable property and a cheap oracle, so the test is written before the code. AC-0003 and AC-0004 carry a *property test* rather than examples, because density under concurrency is a property of interleavings no fixed case covers.
- **Goal-based check (AC-0001, AC-0007, AC-0008, AC-0009)** — the wiring and the gates. A one-liner is the verdict: served routes against the committed contract, and each import or identifier rule against a deliberately introduced violation.
- **End-to-end, including fault injection (AC-0010, AC-0011)** — lease recovery is only observable with real containers and a worker actually killed. Neither can be written before the pool it exercises.

No criterion in this spec calls a model provider. That is deliberate: the
sibling `walking-skeleton-agent-runtime` owns every provider-touching claim, so
this spec's suite runs with no cloud credential and no spend.

## Acceptance Criteria

Obligations here come from `runtime-architecture.md` § Rollout Phase 1
criteria 1, 3 and 5, and from `worker-runtime.md` § Rollout criterion 3. Two
obligations go beyond those sources, and the approval gate rules on each:

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Assert the privilege split on the shipped schema | AC-0005 | Spike P1 proved the split against the spike's own schema, not the one this delivery runs | The split is proven for a schema that is not the one running |
| Assert graceful drain distinctly from host loss | AC-0011 | `runtime-architecture.md` § Step execution specifies `SIGTERM` setting the lease expiry | A rolling deploy silently costs as much as an unplanned host loss |

**Starting a run**

- [ ] **AC-0001.** `POST /runs` returns a run identifier and the run is readable at `GET /runs/{id}/snapshot` in state `requested`.
- [ ] **AC-0002.** The `run.requested` event and the coordinator step row commit in one transaction: with the step insert forced to fail, no run row, no step row, and no event exists.

**Appending events**

- [ ] **AC-0003.** Under eight concurrent writers appending to one run — the concurrency spike P2 used, carried forward — every event's `seq` is dense from 1 with no duplicates and no gaps.
- [ ] **AC-0004.** An append attempted with a stale `lease_epoch` rolls back, and the run's `seq` sequence after it is still dense: the rolled-back attempt consumed no number.
- [ ] **AC-0005.** A `worker`-role connection attempting to append a `policy.decision` event is refused by the database rather than by application code.
- [ ] **AC-0006.** A second `tool.invoked` event carrying an idempotency key already recorded for its run is refused by the partial unique index, so a duplicate append fails rather than succeeding twice.

**Containing dependencies and identifiers**

- [ ] **AC-0007.** The dependency-direction test fails on a deliberately introduced `pydantic_ai` import outside `agents/` and `adapters/`, and on a deliberately introduced AWS SDK import outside `adapters/`, and passes once both are removed.
- [ ] **AC-0008.** `tools/lint-no-identifiers.py` fails on an account identifier embedded inside a larger identifier, and does not fail on a twelve-digit run inside a content hash.
- [ ] **AC-0009.** The served routes match `contracts/openapi/runs.yaml`, asserted against the generated document rather than by inspection.

**Surviving host loss**

- [ ] **AC-0010.** A worker killed mid-step has its step reacquired by another worker within 150 seconds, with no operator action.
- [ ] **AC-0011.** A worker sent `SIGTERM` has its step reacquired within one poll interval, which is what distinguishes graceful drain from waiting out the lease TTL.

## Follow-ons

- eugenelim: `workspace.toml` — `walking-skeleton-agent-runtime` and `walking-skeleton-evidence` complete Phase 1. This spec is their hard dependency; Phase 1's exit criteria are met only when all three ship.
- eugenelim: `workspace.toml` `[backlog].open` — AWS deployment to ECS Fargate with ALB and OIDC, including its IaC and mandatory infra security review. Out of scope by the owner's decision of 2026-09-18.

## Assumptions

- Technical: the stack is Python 3.13 with FastAPI, psycopg3 and Alembic; MinIO for the S3-API subset; local Docker Compose for everything (source: user decision 2026-09-18).
- Technical: the repository is greenfield — no manifest, no application code, no Compose file (source: directory listing 2026-09-18).
- Technical: Python 3.13.13 and Docker 29.7.2 are available locally (source: `python3 --version`, `docker --version`).
- Technical: `tools/lint-no-identifiers.py` had a word-boundary gap that let an account id embedded in an identifier pass. AC-0008 exists because that gap was found by walking through it, and the fix ships in this spec (source: probe against the pattern, 2026-09-18).
- Technical: spike P2's lock-ordering and sequence-density results were obtained against a local Postgres container with `deadlock_timeout` at 200 ms, not against RDS or Aurora. That qualification travels with AC-0003 and AC-0004 (source: `spikes/README.md` § What these results do not establish).
- Process: `AGENTS.md` § Development workflow requires an RFC before a top-level directory is created. **The owner waived that requirement for this delivery on 2026-09-18**, under the same shaping-phase exception used for the charter amendment, so the layout is recorded in ADR-0003 instead and T1 no longer blocks on an acceptance round (source: user decision 2026-09-18).
- Process: every change goes on a branch and through a PR; there is no CI, so the repository lints are the whole gate (source: `AGENTS.md`).
- Process: eugenelim approves both the spec and the plan gates (source: user confirmation 2026-09-18). **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents — a shaping review over two rounds and an adversarial spec-mode review — and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
- Governance: r7 and r4 are ratified as of 2026-09-18, r7 with its Known-at-ship gaps accepted open, and the DR decisions settled (source: both documents' Sign-off and Status headers).
