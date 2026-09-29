# Plan: Walking skeleton — the run state machine

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved <!-- Drafting | Approved | Executing | Done -->
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
- **It adds schema, and it is not purely expand-only.** Revision 0005 has **seven parts, enumerated here once and referenced elsewhere rather than restated**: the run-terminal definer function; the approval-decision definer function; `steps.approval_cycles` as `integer NOT NULL DEFAULT 0`; `steps.awaiting_decision` as `boolean NOT NULL DEFAULT false`; a partial unique index over the two decision types on `(run_id, idempotency_key)`, which is what makes AC-0334's replay refusal a database fact; their `EXECUTE` grants; and a `CREATE OR REPLACE FUNCTION public.append_step_event` carrying a widened refusal list. Both defaults are load-bearing rather than tidy — a nullable `awaiting_decision` makes the claim predicate three-valued and stalls the pool on every pre-existing row.

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
| Schema — `migrations/versions/` | T1 | Revision 0005's parts (see § Constraints) applying both on a clean volume and on a database upgraded from 0002, with the grant set asserted disjoint | The `append_step_event` replacement narrows what `app_worker` may append, stated rather than described as expand-only |
| Recorded decisions — `docs/adr/` | T0 | The gate-placement and append-path ADRs | Each cited from the criterion resting on it |
| Interface compatibility — `contracts/openapi/runs.yaml` | T2 | The approval-decision operation documented, the operation this spec adds; the total is the last-landing spec's | Served and committed agree under AC-0009 |
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

**AC-0333 and the cycle counter are T2's, and both are written by exactly two paths.** The worker's fenced suspension append sets `steps.awaiting_decision`; AC-0324's decision path clears it and advances `steps.approval_cycles`, in the same transaction as the decision append. Nothing else writes either, which is what lets AC-0324 read the cycle from the step instead of from the caller. The counter starts at `0` and the first suspension decides cycle `1`.

**Approach (what ships unchanged, stated because two earlier revisions got it wrong):** **the suspension path ships unchanged, and so does the `step.suspended` event.** `src/ced/worker/executor.py` already appends that event fenced on the lease epoch and then writes `state='runnable', owner=NULL`; an earlier revision of this plan described both as T2's additions, which would have had an implementer add a second append. What T2 adds beside them is the `awaiting_decision` write in that same fenced transaction. The first revision made suspension write `state='suspended'`, which strands the step and contradicts the shipped AC-0237; the second reverted it and left the step claimable within one poll, which AC-0330's refusal then turned into a guaranteed kill. AC-0333's column is neither.

**Approach:** Two records. **The gate placement**: the shipped run-time injection stands against r8 § 3. **The append paths**: r8 § 4 line 460 and § 3 line 344 disagree, § 3's reading is kept, and the approval path's `app_api` grant and its unfenced commit are recorded with it.

**Done when:** both records exist and each criterion resting on a deviation cites the record that carries it.

### T1: The paths the transitions need

**Depends on:** T0

**Touches:** migrations/versions/**, src/**/domain/events.py, src/**/adapters/postgres/event_log.py, tests/schema/**, tests/event_log/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0320 and AC-0324, `substrate`. For each: the grant set stays disjoint and carries no direct `INSERT` on `events`; the path is granted to exactly the named role; each predicate is driven by a call that violates it and observed to refuse; and for AC-0320, with the append forced to fail, `runs.state` does not move.
- AC-0334 drives a suspension carrying several pending calls and asserts a mixed decision yields different per-call outcomes, and that a replayed decision is refused by the partial unique index rather than by application code. `substrate`.
- AC-0324 additionally asserts **at the type level** that no role other than `app_api` commits `approval.granted` or `approval.rejected` by any path, including `append_step_event` — and asserts it **against a database upgraded from 0002 as well as a freshly built one**, because a clean-volume-only check is green exactly where the control exists.
- `stub: true` — `test_the_run_terminal_append_path_exists` (AC-0320), `test_the_approval_decision_append_path_exists` (AC-0324), `test_exactly_one_append_step_event_survives_the_replacement` (AC-0332), `test_a_decision_key_is_unique_per_suspension_and_call` (AC-0334). Both re-validated red against the running substrate on 2026-09-27 — **an isolation downgrade, recorded as one**: the intended-red pass reached a live database rather than a network-denying harness, so these are validated-with-downgrade rather than validated outright. **An earlier revision of this plan recorded blocks calling `_routine_exists` and `_column_exists`, helpers that exist nowhere** — they would have red with `NameError` whether or not revision 0005 shipped, and could never have gone green. Each block below is self-contained.

Each block below materializes into the module named beside it and carries its own imports, so the proven red comes from the absent production surface rather than a `NameError`. An earlier revision recorded blocks whose helpers existed nowhere, and the round-2 repair carried the helpers' bodies inline but still left `psycopg`, `database_url`, `pytest` and `PoolConfig` unimported.

**Into `tests/schema/test_run_state_paths.py`.** Each database-backed block carries the per-function `substrate` marker and the `require_substrate` fixture — per-function marking is the repository's own pattern in `tests/api/test_contract_agreement.py`. Without them these blocks are collected by the `pytest -m 'not substrate'` offline gate and error on `psycopg.OperationalError` rather than skip.

```python
import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url


@pytest.mark.substrate
# STUB: AC-0324
def test_the_approval_decision_append_path_exists(require_substrate: None) -> None:
    """Revision 0005 adds the path `app_api` alone may commit a decision through."""
    with psycopg.connect(database_url("worker")) as conn:
        found = conn.execute(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = 'append_approval_decision'"
        ).fetchone()
    assert found is not None


@pytest.mark.substrate
# STUB: AC-0320
def test_the_run_terminal_append_path_exists(require_substrate: None) -> None:
    """Revision 0005 adds the only path that may commit a run-terminal move."""
    with psycopg.connect(database_url("worker")) as conn:
        found = conn.execute(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = 'append_run_terminal'"
        ).fetchone()
    assert found is not None


@pytest.mark.substrate
# STUB: AC-0332
def test_exactly_one_append_step_event_survives_the_replacement(
    require_substrate: None,
) -> None:
    """A signature drift creates a second overload carrying EXECUTE TO PUBLIC."""
    with psycopg.connect(database_url("worker")) as conn:
        rows = conn.execute(
            "SELECT p.prosecdef, p.proconfig, p.prosrc FROM pg_proc p"
            " JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = 'append_step_event'"
        ).fetchall()
    assert len(rows) == 1
    secdef, proconfig, body = rows[0]
    assert secdef is True
    assert "pg_temp" in " ".join(proconfig or [])
    assert "approval.granted" in body and "approval.rejected" in body


@pytest.mark.substrate
# STUB: AC-0334
def test_a_decision_key_is_unique_per_suspension_and_call(require_substrate: None) -> None:
    """The replay refusal is a database fact, not application logic."""
    with psycopg.connect(database_url("worker")) as conn:
        found = conn.execute(
            "SELECT 1 FROM pg_indexes WHERE schemaname = 'public'"
            " AND tablename = 'events'"
            " AND indexdef ILIKE '%approval.granted%'"
            " AND indexdef ILIKE '%idempotency_key%'"
        ).fetchone()
    assert found is not None
```

  **AC-0332's preserved half cannot red on its own** — the shipped function already has one overload, `SECURITY DEFINER` and a pinned `search_path`, so a stub asserting only those passes today, as running it proved. The block therefore also asserts the refusal list revision 0005 *adds*, which is absent and reds.

**Approach:** Revision 0005's parts as § Constraints enumerates them — that enumeration is canonical and is not restated here — written against the three shipped append functions. The denylist gap is closed by re-issuing `append_step_event` through `CREATE OR REPLACE` under 0002's owner and definer preamble with the two approval types added to its refusal list — **not** by editing 0002's constant, which would reach no database that has already migrated.

**Done when:** AC-0320, AC-0324, AC-0332 and AC-0334 are green with their mutation proofs in the ledger.

### T2: The transitions, and the interface that releases one

**Depends on:** T1

**Touches:** src/**/domain/run_state.py, src/**/worker/prerelease.py, src/**/worker/executor.py, src/**/worker/persistence.py, src/**/worker/liveness.py, src/**/worker/pool.py, src/**/api/**, contracts/openapi/runs.yaml, deploy/compose.yaml, pyproject.toml, tests/api/**, tests/e2e/**, tests/suspension/**, tests/persistence/**, tests/quarantine_step/**, tests/schema/**, tests/worker/**, tests/thinking_reaches_the_model/test_no_path_re_enables_reasoning.py, tests/usage_limits/test_usage_limits_in_force.py, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md, AGENTS.md

**Tests:**
- AC-0301 end to end; AC-0302 on the offered tool set; AC-0303 on the flagged branch with the flag driven both ways; AC-0327 reading the snapshot between steps; AC-0328 driving the new operation and a foreign origin.
- **`tests/api/test_contract_agreement.py` moves from three routes to four** — its `test_the_contract_file_describes_three_routes` asserts the committed count and reds the moment the contract gains an operation, which is why that file is in this task's `Touches`.
- The liveness probe is asserted by stalling the poll loop without killing the process; a probe checking only process existence would pass.
- `stub: true` — `test_the_gated_tool_is_offered_only_when_a_check_failed` (AC-0302), `test_a_resume_with_no_committed_decision_refuses_to_run` (AC-0330). Both re-validated red on 2026-09-27 on absent imports.

**Into `tests/suspension/test_the_gate_is_conditional.py`:**

```python
import pytest


# STUB: AC-0302
def test_the_gated_tool_is_offered_only_when_a_check_failed() -> None:
    """Exclusion paired with its positive case, so returning [] cannot pass."""
    from ced.worker.executor import offered_approval_gated_tools

    assert offered_approval_gated_tools(prerelease_failed=False) == []
    assert offered_approval_gated_tools(prerelease_failed=True) != []


@pytest.mark.substrate
# STUB: AC-0330
def test_a_resume_with_no_committed_decision_refuses_to_run(require_substrate: None) -> None:
    """Absent decision for this cycle is a refusal, not an approval."""
    from ced.worker.persistence import approval_results_for_cycle

    with pytest.raises(LookupError):
        approval_results_for_cycle(
            step_id="11111111-2222-3333-4444-5555aaaabbbb", cycle=1, pending_call_ids=["c1"]
        )
```

  **AC-0302's stub pairs its exclusion with the positive case**, because `offered_approval_gated_tools(...) == []` alone is satisfied by an implementation that returns `[]` unconditionally — the gate never appearing at all would pass it. It also asserts the offered *tools*, not the toolset object. An earlier revision asserted `all(not ts.requires_approval for ts in offered)` — and `requires_approval` is a toolset-level flag that stays `False` when `add_function(..., requires_approval=True)` sets it on the tool, verified by executing it against the installed framework. That assertion passed in the failing world, which is the vacuity shape this criterion exists to catch.

  **AC-0327 has no stub and records `no stub (implementation-discovered)`.** *Discovery predicate:* its oracle is the ordered event projection, and the projection's callable seam — what reads the log and folds it into a state sequence — does not exist and is T2's to design; the column check an earlier revision filed under AC-0327 belonged to AC-0321 and is green by the time T2 runs, since T1 creates it. *Proof obligation:* before T2 closes, the projection is driven over a committed run and the ledger records the mutation that reds it — dropping the event append from any one committed transition must break the projection's agreement with the snapshot.

- `stub: true` — `test_a_step_awaiting_a_decision_is_not_claimed` (AC-0333), re-validated red on 2026-09-27 against the running substrate — an isolation downgrade, recorded as one: the column does not exist.

**Appended to `tests/schema/test_run_state_paths.py`, inheriting the imports T1's blocks establish there:**

```python
@pytest.mark.substrate
# STUB: AC-0333
def test_a_step_awaiting_a_decision_is_not_claimed(require_substrate: None) -> None:
    """The exclusion is a column the decision path clears, not a step state."""
    with psycopg.connect(database_url("worker")) as conn:
        found = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'steps'"
            " AND column_name = 'awaiting_decision'"
        ).fetchone()
    assert found is not None
```

- `stub: true` for **AC-0331** — `test_an_idle_worker_reports_healthy`, asserting the nearest in-process data contract with the out-of-process exit code deferred, which is what `tdd-stubs.md` prescribes for a hard out-of-process surface rather than `implementation-discovered`; T2's `Touches` already names the destination module.

**Into `tests/worker/test_liveness.py`:**

```python
# STUB: AC-0331
def test_an_idle_worker_reports_healthy() -> None:
    """The mark the poll loop refreshes, not the heartbeat a lease drives."""
    from ced.worker.liveness import liveness_state

    assert liveness_state(seconds_since_poll=1.0, lease_ttl_seconds=60).healthy is True
```

- `no stub (mode)` for AC-0301 and AC-0303 (end-to-end) and AC-0328 (end-to-end against the shipped route). AC-0328's mode is end-to-end in both documents; an earlier revision of this plan called it manual QA while the spec's Testing Strategy placed it in the TDD group, which is two gate-read fields disagreeing about what a third gate enforces.

**Done when:** AC-0301, AC-0302, AC-0303, AC-0327, AC-0328, AC-0330 and AC-0331 are green with their mutation proofs in the ledger, and the approval operation is contracted and served.

### T3: The loop and the spend are bounded

**Depends on:** T2

**Touches:** src/**/worker/pool.py, src/**/worker/executor.py, deploy/compose.yaml, tests/suspension/**, tests/usage_limits/**, tests/worker/**, docs/specs/walking-skeleton-run-state/notes/verification-ledger.md

**Tests:**
- AC-0321 drives the cycles **across a worker handoff** and asserts the cap fires with a recorded cause; a second case asserts a `PoolConfig` declaring no cap still bounds the loop.
- AC-0325 accumulates usage past the ceiling and asserts the pre-dispatch check appends the step-scoped page event and does not abort; a second case asserts a `PoolConfig` declaring no ceiling still gets a finite one.
- `stub: true` — `test_the_cycle_cap_configuration_carries_a_finite_default` (AC-0321), `test_the_per_run_spend_ceiling_carries_a_finite_default` (AC-0325). Both re-validated red on 2026-09-27: `PoolConfig` carries neither field.

**Into `tests/worker/test_pool_configuration.py`, which already exists:**

```python
from ced.worker.pool import PoolConfig


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
- AC-0329 is checked by reading: the record must name every residual AC-0329 enumerates, including the uncommitted transitions it lists and the safety constraints `awaiting_input` owes.
- `python3 .agents/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green across all seven specs.
- `no stub (mode)` — record review.

**Done when:** AC-0329 holds and the architecture map names the transitions this delivery did not commit.

## Rollout

- **Delivery:** five PRs — T0, T1, T2, T3, T4.
- **Review shape:** T1 is **MIXED** — a migration plus its assertions. T2 is **DEEP** and decomposes in dependency order: the transition table, the pre-release gate and publication, then the approval operation.
- **Reversible:** revision 0005 has no downgrade path, so reversal is a forward revision. It is **not** purely expand-only: its `append_step_event` replacement removes a capability `app_worker` holds today, so reversing it restores that capability rather than merely dropping something added.

## Risks

- **The denylist change is a foundation-owned behaviour change.** Re-issuing `append_step_event` through `CREATE OR REPLACE` with two more refused types narrows what `app_worker` may append — **not** by editing `NON_STEP_EVENT_TYPES`, which is rendered into the function body at creation time and would reach no already-migrated database, which is the safe direction, but it is a shipped rule this spec edits — and `tests/event_log/` asserts against it.
- **AC-0327's snapshot reads are timing-sensitive** between steps. Mitigated by asserting the sequence of observed states rather than a state at a wall-clock moment.

## Status transitions

Recorded because a reviewer reasonably asked where they land. All fifteen
acceptance criteria are `- [x]` and T4 is the last task, yet the spec reads
`Implementing` and this plan reads `Approved`. That is deliberate and not a
task's omission: **the flip is the work loop's closeout, not T4's work.** The
engine holds the run at `CODE-HUMAN-GATE` until the owner answers "are these
changes correct and ready to merge", and only a `done` transition from there
makes `Shipped` true. A task that marked its own spec `Shipped` would be
asserting the gate's answer before the gate ran.

`lint-spec-status --root . --all` does not catch the interim state, so nothing
mechanical distinguishes "every criterion met, awaiting the gate" from "in
flight". This paragraph is that distinction, written where the next reader of
this plan will look.

## Changelog

- 2026-09-27: **plan approved by eugenelim**, on the same basis and with the same qualification as the spec approval below. The build order is T0 through T4; T0's records must exist before the code they govern.
- 2026-09-27: **spec approved by eugenelim, without a confirming clean review round.** Five pre-EXECUTE rounds ran; every one returned findings and every sustained finding was applied, the last eighteen in `fdb1e8e`. **No reviewer has read the text as it now stands.** Rounds 2 and 3 were additionally applied without passing through finding adjudication, so parts of this contract rest on reviewer prose that was never independently tested — the claims load-bearing enough to matter were verified against the tree by hand, and that is a weaker guarantee than the gateway gives. The owner has the approval authority and exercised it; this entry exists so the record states what the approval did and did not rest on, rather than letting the engine's `reviewers-clean` transition imply a clean round that did not occur.

- 2026-09-27: split out of `walking-skeleton-evidence` by owner decision, after four pre-EXECUTE review rounds found this layer failing while that spec's measurement and record tasks converged. **Every criterion's origin, so no tally can drift from it:** seven moved across unchanged in substance — AC-0301, AC-0302, AC-0303, AC-0320, AC-0321, AC-0324, AC-0325. Three were added at the split for gaps round 4 of that spec surfaced — AC-0327 the transitions a reader can see, AC-0328 the approver's interface, AC-0329 this spec's residual record. Five more were added across this spec's own review rounds: AC-0330 binding the resume to the committed decision and AC-0331 contracting the DR4 probe, both round 1; AC-0332 bounding what the `CREATE OR REPLACE` preserves, round 2; AC-0333 the suspension hold, round 3; AC-0334 the decision's recorded form, round 4 and rebound to the suspension `seq` in round 5. Fifteen in total.