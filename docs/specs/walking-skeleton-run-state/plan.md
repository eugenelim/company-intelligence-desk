# Plan: Walking skeleton — the run state machine

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8 § 3 Runtime Model (the state table, the approval gate) and § 4 Contracts and Invariants (the append paths and the fence); [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 3 Runtime Model. **The analogous production implementations are the three shipped append functions** in `migrations/versions/0002_append_paths_and_privilege_split.py` — `append_step_event`, `append_run_event` and `append_policy_decision` — with `tests/event_log/` and `tests/schema/` as their construction and registration path. The two functions this spec adds are written against those three, and the predicate sets they already carry are what AC-0320 and AC-0324 enumerate. **Named deviation:** none of the three is unfenced, and AC-0324's path must be, because the lease is released before the approver acts.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-run-state/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Open the paths first, then move the states through them, then bound the loop.

The order is forced rather than chosen. Every transition this spec commits ends
in an append, and two of the appends have no path — so the migration is not a
detail that follows the design, it is the thing the design was missing. Four
review rounds on the predecessor spec found the same defect three times, once
per criterion, because each criterion reached the privilege split on its own.

T0 comes first for the same reason it did there: two decisions here deviate
from a ratified document, and a record written after the build it justifies is
a rationalisation.

## Constraints

- `runtime-architecture.md` r8 and `worker-runtime.md` r5 — ratified. r8 disagrees with itself at § 4 line 460 against § 3 line 344; T0 records which reading is taken.
- **Hard dependencies:** the five shipped walking-skeleton specs. This spec adds no agent.
- **It adds schema.** Revision 0005 is expand-only and has four parts: the run-terminal definer function, the approval-decision definer function, `steps.approval_cycles`, and the `EXECUTE` grants. It also **closes the `append_step_event` denylist gap** for the two approval types, without which AC-0324's type-level exclusivity is unassertable.
- **It revokes nothing.** Both roles keep their table-level `UPDATE ON runs`; `0001_base_schema.py` records that grant as r7's identity table verbatim and declines to narrow it unilaterally.
- **Out of scope:** the browser, the Phase 1 measurements, the re-baseline and the Phase 1 record — all `walking-skeleton-evidence`'s, which depends on this spec.

## DR dispositions

| DR | Decision | Disposition |
| --- | --- | --- |
| DR1 | Publication is an executor transition, not a tool | **Lands**, T2 — the transition is the application's; the agent's only lever is the contentless tool |
| DR4 | The liveness probe is the out-of-loop watchdog | **Lands**, T2, as a worker-side command the container healthcheck runs — **not an HTTP route**, because the contract's growth is fixed at one operation and an out-of-process probe is what DR4 asks for |
| DR5 | Rejection resumes the conversation, capped at three cycles | **Lands**, T3, under AC-0321, at r5's three and unmeasured |
| DR6 | Three spend ceilings | **Partly here** — the per-run ceiling lands in T3 under AC-0325, paging rather than aborting. The per-step ceilings are the agent-runtime spec's; the per-account alarm is outside the application |
| DR2, DR3, DR7–DR13 | — | **Not this spec's** |

## Construction tests

**Schema tests (`substrate`):** AC-0320's and AC-0324's grant, predicate and atomicity assertions run against the applied revision, because a grant set is a property of the schema Postgres holds.

**Integration tests:** one clean-run end-to-end through local Compose, and one flagged-run end-to-end that suspends, releases its lease, and resumes on a grant issued through AC-0328's operation.

**Mutation proof is a deliverable.** Every criterion whose `Tests` entry names a mutation writes its proof to `notes/verification-ledger.md` — the break applied, and the check that went red. A proof filed where nobody looks is the same defect as a proof never run.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Schema — `migrations/versions/` | T1 | Revision 0005 applying on a clean volume with the grant set asserted disjoint | Expand-only, revokes nothing |
| Recorded decisions — `docs/adr/` | T0 | The gate-placement and append-path ADRs | Each cited from the criterion resting on it |
| Interface compatibility — `contracts/openapi/runs.yaml` | T2 | The approval-decision operation documented, route count three to four | Served and committed agree under AC-0009 |
| Current architecture — `docs/architecture/README.md` | T4 | The run-state row moved, with uncommitted transitions named | The map matches the repository |

## Design (LLD)

### The two new append paths

Both are `SECURITY DEFINER`, both lock `steps` before `runs`, and both carry
the predicate set their shipped siblings carry rather than only the grant that
names their caller. The terminal path is fenced through `fence_step` and writes
`step_id` null; the approval path cannot be fenced, because the lease is
released before the approver acts, and substitutes three structural predicates.
Traces to: AC-0320, AC-0324 · ADR written in T0.

### Where the gated tool sits

The shipped tree builds the approval tool as a run-time `FunctionToolset`
outside the compiled stack, deliberately, so the decision point never judges it
against the acting role's ceiling. r8 § 3 lines 400–403 describes the other
placement. The shipped one stands by owner decision; T0 records it, and AC-0302
reads the tool set the model is offered rather than the compiled one, which is
where conditionality is decidable on this design. Traces to: AC-0302.

### Dependencies & integration

No new dependencies. External: none — this spec issues no provider call of its
own, and the flagged-run check drives a model that calls `request_approval`
deterministically.

## Tasks

### T0: The records the build may not make silently

**Depends on:** none

**Touches:** docs/adr/**, docs/specs/walking-skeleton-run-state/spec.md, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- Goal-based: `python3 tools/hooks/pre-pr.py` passes its ADR shape lint over each new record.
- `no stub (mode)` — goal-based.

**Approach:** Two records. **The gate placement**: the shipped run-time injection stands against r8 § 3. **The append paths**: r8 § 4 line 460 and § 3 line 344 disagree, § 3's reading is kept, and the approval path's `app_api` grant and its unfenced commit are recorded with it.

**Done when:** both records exist and each criterion resting on a deviation cites the record that carries it.

### T1: The paths the transitions need

**Depends on:** T0

**Touches:** migrations/versions/**, src/**/domain/events.py, src/**/adapters/postgres/event_log.py, tests/schema/**, tests/event_log/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0320 and AC-0324, `substrate`. For each: the grant set stays disjoint and carries no direct `INSERT` on `events`; the path is granted to exactly the named role; each predicate is driven by a call that violates it and observed to refuse; and for AC-0320, with the append forced to fail, `runs.state` does not move. AC-0324 additionally asserts **at the type level** that no role other than `app_api` commits `approval.granted` or `approval.rejected` by any path, including `append_step_event`.
- `stub: true` — the exact red test code is written into this plan before EXECUTE begins, per `spec-and-plan-contract.md`.

**Approach:** Revision 0005's four parts, written against the three shipped append functions. The denylist gap is closed by adding the two approval types to `NON_STEP_EVENT_TYPES`, which is what makes AC-0324's exclusivity assertable.

**Done when:** AC-0320 and AC-0324 are green with their mutation proofs in the ledger.

### T2: The transitions, and the interface that releases one

**Depends on:** T1

**Touches:** src/**/domain/run_state.py, src/**/worker/prerelease.py, src/**/worker/executor.py, src/**/worker/persistence.py, src/**/worker/liveness.py, src/**/api/**, contracts/openapi/runs.yaml, deploy/compose.yaml, tests/api/**, tests/e2e/**, tests/suspension/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0301 end to end; AC-0302 on the offered tool set; AC-0303 on the flagged branch with the flag driven both ways; AC-0327 reading the snapshot between steps; AC-0328 driving the new operation and a foreign origin.
- **`tests/api/test_contract_agreement.py` moves from three routes to four** — its `test_the_contract_file_describes_three_routes` asserts the committed count and reds the moment the contract gains an operation, which is why that file is in this task's `Touches`.
- The liveness probe is asserted by stalling the poll loop without killing the process; a probe checking only process existence would pass.
- `stub: true` for AC-0302 and AC-0327; `no stub (mode)` for AC-0301, AC-0303 and AC-0328, which are end-to-end and manual-QA respectively.

**Done when:** AC-0301, AC-0302, AC-0303, AC-0327 and AC-0328 are green, the contract carries four operations, and the probe is observed failing on a stalled loop.

### T3: The loop and the spend are bounded

**Depends on:** T2

**Touches:** src/**/worker/pool.py, src/**/worker/executor.py, deploy/compose.yaml, tests/suspension/**, tests/usage_limits/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0321 drives the cycles **across a worker handoff** and asserts the cap fires with a recorded cause; a second case asserts a `PoolConfig` declaring no cap still bounds the loop.
- AC-0325 accumulates usage past the ceiling and asserts the pre-dispatch check appends the step-scoped page event and does not abort; a second case asserts a `PoolConfig` declaring no ceiling still gets a finite one.
- `stub: true` for both.

**Approach:** Both controls are configured rather than constant, and both carry a finite default, because a criterion that configures its own control in its fixture passes while a deployment declaring nothing has none. `step_deadline`'s `None` default is the same class and is the sibling spec's to set.

**Done when:** AC-0321 and AC-0325 are green with their mutation proofs, including the default-posture cases.

### T4: The record says what this did not establish

**Depends on:** T3

**Touches:** docs/architecture/README.md, docs/specs/walking-skeleton-run-state/spec.md, docs/specs/walking-skeleton-run-state/plan.md, workspace.toml

**Tests:**
- AC-0329 is checked by reading: the record must name all five residuals the criterion binds, including the five uncommitted r8 § 3 transitions and the safety constraints `awaiting_input` owes.
- `python3 .agents/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green across all seven specs.
- `no stub (mode)` — record review.

**Done when:** AC-0329 holds and the architecture map names the transitions this delivery did not commit.

## Rollout

- **Delivery:** five PRs — T0, T1, T2, T3, T4.
- **Review shape:** T1 is **MIXED** — a migration plus its assertions. T2 is **DEEP** and decomposes in dependency order: the transition table, the pre-release gate and publication, then the approval operation.
- **Reversible:** revision 0005 is expand-only with no downgrade path, so reversal is a forward revision that revokes the grants.

## Risks

- **The denylist change is a foundation-owned behaviour change.** Adding two types to `NON_STEP_EVENT_TYPES` narrows what `app_worker` may append, which is the safe direction, but it is a shipped rule this spec edits — and `tests/event_log/` asserts against it.
- **AC-0327's snapshot reads are timing-sensitive** between steps. Mitigated by asserting the sequence of observed states rather than a state at a wall-clock moment.

## Changelog

- 2026-09-27: split out of `walking-skeleton-evidence` by owner decision, after four pre-EXECUTE review rounds found this layer failing repeatedly while that spec's measurement and record tasks converged. Seven criteria moved across unchanged in substance — AC-0301, AC-0302, AC-0303, AC-0320, AC-0321, AC-0324, AC-0325 — and three were added for gaps round 4 surfaced: AC-0327 the transitions a reader can see, AC-0328 the approver's interface, AC-0329 this spec's own residual record.
