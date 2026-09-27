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
- **It adds schema, and it is not purely expand-only.** Revision 0005 has five parts: the run-terminal definer function, the approval-decision definer function, the `steps.approval_cycles` column, their `EXECUTE` grants, and a **`CREATE OR REPLACE FUNCTION public.append_step_event`** carrying a widened refusal list. That fifth part **narrows** what `app_worker` may append, which is the safe direction and still a contracting change to a foundation-owned function.
- **The narrowing must be a `CREATE OR REPLACE`, not an edit to revision 0002.** `NON_STEP_EVENT_TYPES` is a module constant rendered into `append_step_event`'s body at `CREATE FUNCTION` time, so editing the tuple changes only what a *fresh* volume builds: every already-migrated database keeps the old body and `app_worker` keeps the capability. Since the `substrate` suite rebuilds from a clean volume, that edit would go green precisely where the control exists and blind where it does not. 0002's text stays untouched.
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
| Schema — `migrations/versions/` | T1 | Revision 0005's five parts applying both on a clean volume and on a database upgraded from 0002, with the grant set asserted disjoint | The `append_step_event` replacement narrows what `app_worker` may append, stated rather than described as expand-only |
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

**Approach (T2's correctness fix, stated because it is not obvious from the criteria alone):** the suspension path today sets `steps.state = 'runnable'`, so a flagged step is re-claimable by any worker before the approver acts at all. T2 changes it to write `'suspended'` with its `step.suspended` event in one transaction, and the resume returns it to `runnable` only after reading a committed decision. That is what makes AC-0324's predicate live and AC-0330's refusal reachable.

**Approach:** Two records. **The gate placement**: the shipped run-time injection stands against r8 § 3. **The append paths**: r8 § 4 line 460 and § 3 line 344 disagree, § 3's reading is kept, and the approval path's `app_api` grant and its unfenced commit are recorded with it.

**Done when:** both records exist and each criterion resting on a deviation cites the record that carries it.

### T1: The paths the transitions need

**Depends on:** T0

**Touches:** migrations/versions/**, src/**/domain/events.py, src/**/adapters/postgres/event_log.py, tests/schema/**, tests/event_log/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0320 and AC-0324, `substrate`. For each: the grant set stays disjoint and carries no direct `INSERT` on `events`; the path is granted to exactly the named role; each predicate is driven by a call that violates it and observed to refuse; and for AC-0320, with the append forced to fail, `runs.state` does not move. AC-0324 additionally asserts **at the type level** that no role other than `app_api` commits `approval.granted` or `approval.rejected` by any path, including `append_step_event` — and asserts it **against a database upgraded from 0002 as well as a freshly built one**, because a clean-volume-only check is green exactly where the control exists.
- `stub: true` — `test_the_run_terminal_append_path_exists` (AC-0320), `test_the_approval_decision_append_path_exists` (AC-0324). Both validated red against the running substrate on 2026-09-27: the routines do not exist.

```python
# STUB: AC-0320
def test_the_run_terminal_append_path_exists() -> None:
    """Revision 0005 adds the only path that may commit a run-terminal move."""
    assert _routine_exists("append_run_terminal")


# STUB: AC-0324
def test_the_approval_decision_append_path_exists() -> None:
    """Revision 0005 adds the path `app_api` alone may commit a decision through."""
    assert _routine_exists("append_approval_decision")
```

**Approach:** Revision 0005's five parts, written against the three shipped append functions. The denylist gap is closed by re-issuing `append_step_event` through `CREATE OR REPLACE` under 0002's owner and definer preamble with the two approval types added to its refusal list — **not** by editing 0002's constant, which would reach no database that has already migrated.

**Done when:** AC-0320 and AC-0324 are green with their mutation proofs in the ledger.

### T2: The transitions, and the interface that releases one

**Depends on:** T1

**Touches:** src/**/domain/run_state.py, src/**/worker/prerelease.py, src/**/worker/executor.py, src/**/worker/persistence.py, src/**/worker/liveness.py, src/**/api/**, contracts/openapi/runs.yaml, deploy/compose.yaml, tests/api/**, tests/e2e/**, tests/suspension/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0301 end to end; AC-0302 on the offered tool set; AC-0303 on the flagged branch with the flag driven both ways; AC-0327 reading the snapshot between steps; AC-0328 driving the new operation and a foreign origin.
- **`tests/api/test_contract_agreement.py` moves from three routes to four** — its `test_the_contract_file_describes_three_routes` asserts the committed count and reds the moment the contract gains an operation, which is why that file is in this task's `Touches`.
- The liveness probe is asserted by stalling the poll loop without killing the process; a probe checking only process existence would pass.
- `stub: true` — `test_a_clean_run_offers_the_model_no_approval_gated_tool` (AC-0302), `test_steps_carries_the_durable_cycle_counter` (AC-0327, the durable seam its projection reads), `test_a_resume_with_no_committed_decision_refuses_to_run` (AC-0330). All validated red on 2026-09-27 against absent symbols and an absent column.

```python
# STUB: AC-0302
def test_a_clean_run_offers_the_model_no_approval_gated_tool() -> None:
    """Conditionality is decidable on the offered set, not the compiled one."""
    from ced.worker.executor import offered_toolsets

    offered = offered_toolsets(prerelease_failed=False)
    assert all(not ts.requires_approval for ts in offered)


# STUB: AC-0330
def test_a_resume_with_no_committed_decision_refuses_to_run() -> None:
    """The gate must not rubber-stamp: absent decision is a refusal."""
    from ced.worker.persistence import approval_results_from_log

    with pytest.raises(LookupError):
        approval_results_from_log(step_id=_ABSENT, pending_call_ids=["c1"])


# STUB: AC-0327
def test_steps_carries_the_durable_cycle_counter() -> None:
    """AC-0321's count must survive a worker handoff, so it is a column."""
    assert _column_exists("steps", "approval_cycles")
```

- `no stub (implementation-discovered)` for **AC-0331**. *Discovery predicate:* the probe's callable seam is a worker-side command whose invocation shape the container healthcheck fixes, and neither the module nor its entry point exists; inventing one now would manufacture a symbol the rule forbids. *Proof obligation:* before T2 closes, the probe is driven by stalling the poll loop without killing the process, and the observed unhealthy result is written to the verification ledger with the mutation that reds it — replacing the heartbeat-recency check with a process-existence check must make it pass.
- `no stub (mode)` for AC-0301 and AC-0303 (end-to-end) and AC-0328 (end-to-end against the shipped route). AC-0328's mode is end-to-end in both documents; an earlier revision of this plan called it manual QA while the spec's Testing Strategy placed it in the TDD group, which is two gate-read fields disagreeing about what a third gate enforces.

**Done when:** AC-0301, AC-0302, AC-0303, AC-0327, AC-0328, AC-0330 and AC-0331 are green with their mutation proofs in the ledger, and the approval operation is contracted and served.

### T3: The loop and the spend are bounded

**Depends on:** T2

**Touches:** src/**/worker/pool.py, src/**/worker/executor.py, deploy/compose.yaml, tests/suspension/**, tests/usage_limits/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0321 drives the cycles **across a worker handoff** and asserts the cap fires with a recorded cause; a second case asserts a `PoolConfig` declaring no cap still bounds the loop.
- AC-0325 accumulates usage past the ceiling and asserts the pre-dispatch check appends the step-scoped page event and does not abort; a second case asserts a `PoolConfig` declaring no ceiling still gets a finite one.
- `stub: true` — `test_the_cycle_cap_configuration_carries_a_finite_default` (AC-0321), `test_the_per_run_spend_ceiling_carries_a_finite_default` (AC-0325). Both validated red on 2026-09-27: `PoolConfig` carries neither field.

```python
# STUB: AC-0321
def test_the_cycle_cap_configuration_carries_a_finite_default() -> None:
    """A deployment that declares no cap still gets a bounded loop."""
    cap = PoolConfig.approval_cycle_cap
    assert cap is not None and cap > 0


# STUB: AC-0325
def test_the_per_run_spend_ceiling_carries_a_finite_default() -> None:
    """A deployment that declares no ceiling still gets one."""
    ceiling = PoolConfig.per_run_token_ceiling
    assert ceiling is not None and ceiling > 0
```

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
- **Reversible:** revision 0005 has no downgrade path, so reversal is a forward revision. It is **not** purely expand-only: its `append_step_event` replacement removes a capability `app_worker` holds today, so reversing it restores that capability rather than merely dropping something added.

## Risks

- **The denylist change is a foundation-owned behaviour change.** Adding two types to `NON_STEP_EVENT_TYPES` narrows what `app_worker` may append, which is the safe direction, but it is a shipped rule this spec edits — and `tests/event_log/` asserts against it.
- **AC-0327's snapshot reads are timing-sensitive** between steps. Mitigated by asserting the sequence of observed states rather than a state at a wall-clock moment.

## Changelog

- 2026-09-27: split out of `walking-skeleton-evidence` by owner decision, after four pre-EXECUTE review rounds found this layer failing repeatedly while that spec's measurement and record tasks converged. Seven criteria moved across unchanged in substance — AC-0301, AC-0302, AC-0303, AC-0320, AC-0321, AC-0324, AC-0325 — and three were added for gaps round 4 surfaced: AC-0327 the transitions a reader can see, AC-0328 the approver's interface, AC-0329 this spec's own residual record.
