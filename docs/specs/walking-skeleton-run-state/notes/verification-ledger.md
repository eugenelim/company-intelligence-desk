# Verification ledger — walking-skeleton-run-state

Execution observations. Mutation proofs live here, not in a session report: a
proof filed where nobody looks is the same defect as a proof never run.

## T0 — the records the build may not make silently

**Date:** 2026-09-27. **Mode:** goal-based, `no stub (mode)`.

**What was produced.** Two decision records, both passing the `new-adr` shape
lint through `tools/hooks/pre-pr.py`:

- [ADR-0008](../../../adr/0008-the-approval-gate-stays-outside-the-compiled-toolset.md)
  — the approval gate's shipped run-time placement stands against r8 § 3 lines
  400–403, and AC-0302 is re-sited onto the offered tool set.
- [ADR-0009](../../../adr/0009-the-two-new-append-paths-and-who-holds-them.md)
  — the run-terminal path to `app_worker` (D1), the approval-decision path to
  `app_api` (D2), and the `CREATE OR REPLACE` of `append_step_event` (D3).

**`Done when` clause two, checked rather than assumed.** Every criterion
resting on a deviation now cites the record carrying it: AC-0302 → ADR-0008;
AC-0320 → ADR-0009 D1; AC-0324 → ADR-0009 D2 and D3. Verified by grepping each
citation individually rather than by an aggregate count.

**A content gap this task surfaced and closed.** AC-0320 carried its lease-
possession predicate but had never carried the paragraph explaining *why* a
worker may write a run-lifecycle type — the justification ADR-0009 D1 now
holds. The paragraph was drafted during round 3 in a script that raised before
writing, and the re-run covered only its sibling criteria. Restored here, with
the citation, because T0's own `Done when` is what caught it.

**Shape-lint findings, fixed rather than worked around.** ADR-0008 first failed
`ADR-S006` (`Reversibility: medium` is not in `{high, low}`) and `ADR-S012` (no
`**Revisit if:**` line in Consequences). Both corrected; the lint then passed
on both records.

**What this task did not establish.** Nothing about the code the records
govern — no migration, no path, no criterion is implemented by T0. The records
exist so the decisions are not taken at the keyboard during T1 and T2.

### Two defects T0 surfaced in the sealed contract itself

**The pinned AC-0332 stub could not be materialized.** `ruff format --check .`
is a repository gate and it reads fenced Python inside markdown, so the stub
blocks in `plan.md` are gate-visible. Adding the `require_substrate` fixture in
round 5 pushed one signature past the line limit, and `tdd-stubs.md` requires
EXECUTE to materialize a block byte-identically — so the plan pinned a stub
whose faithful materialization fails a gate. Reformatted; `ruff format --check`
now exits 0. No reviewer caught this across five rounds, and it is not visible
from reading the block.

**The plan seals its baseline before the task that edits the spec.** T0's
`Touches` names `spec.md` and its `Done when` requires each deviation criterion
to cite its record — so T0 must edit the spec — while `approve-plan` pins the
spec hash before wave 1 runs. Any correct T0 therefore drifts the baseline it
was approved under. Recovered by the cohort-only path `plan check-current`
prescribes: both statuses restored to `Approved`, `loop-cohort reset`, `init`,
`approve-plan`, `schedule`, status restored to `Implementing`. The engine was
**not** reset — `plan-locked` is legal only from `SPEC-PLAN-APPROVED` and
resetting it strands the run.

The re-pin is a re-approval in substance: it records the post-T0 text as the
baseline. That is the mechanical consequence of a plan the owner approved with
T0's `Touches` as written, not a new scope decision — but the ordering is a
real defect. A task that edits the spec cannot run under a baseline sealed
before it, and a later spec in this series should either keep record-writing
tasks out of the spec file or seal after wave 1.

Baselines: approved at spec `41c7f5c4fb93` / plan `69634eb7f06b`; re-pinned
after T0 at spec `841d0959a731` / plan `1e8cd06feefd`.

## T1 — the paths the transitions need

**Date:** 2026-09-27. **Mode:** TDD (construction-test first, then make green).

**What was produced.**

- `migrations/versions/0005_run_state_paths.py` — seven-part revision: two new
  `steps` columns (`awaiting_decision NOT NULL DEFAULT false`,
  `approval_cycles NOT NULL DEFAULT 0`), `append_run_terminal` (fenced,
  `app_worker` only, writes step_id null), `append_approval_decision`
  (unfenced, `app_api` only, suspension-keyed), the partial unique index
  `events_decision_idempotency_idx`, disjoint EXECUTE grants, and `CREATE OR
  REPLACE` of `append_step_event` adding decision types to its refusal list.
- `src/ced/domain/events.py` — `STEP_SUSPENDED`, `APPROVAL_GRANTED`,
  `APPROVAL_REJECTED`, `DECISION_TYPES` constants added.
- `src/ced/adapters/postgres/event_log.py` — `RunNotRunning`, `DecisionRefused`
  exceptions; `append_run_terminal` and `append_approval_decision` Python
  wrappers added.
- `tests/schema/test_run_state_paths.py` — 28 `@pytest.mark.substrate` tests
  covering AC-0320, AC-0324, AC-0332, and AC-0334 with the four plan stubs
  materialized byte-identically.
- `tests/event_log/test_definer_hardening.py` — definer count updated 4 → 6;
  `DECISION_TYPES` added to the refused-set comparison; `approval.granted` and
  `approval.rejected` added to the step-path parametrize.

**Gates (901 passed, 3 skipped, 0 failures):** `ruff format --check`, `ruff
check`, `mypy`, `pytest -m 'not substrate'` (640 passed), `pytest` (901 passed).

### Mutation proofs

Each mutant was installed via `CREATE OR REPLACE FUNCTION`, the targeted test
was observed to fail (red), and the original was then restored by re-executing
the migration's SQL generator. Proofs ran on 2026-09-27 against the live
substrate at revision 0005.

**AC-0320 — M1: `WHERE state = 'running'` dropped from `UPDATE runs` in
`append_run_terminal`.**
Target: `test_run_terminal_refuses_a_run_at_requested_state`.
Result: FAILED — `RunNotRunning` was not raised (run at `requested` state was
accepted and committed). Confirms the guard is pinned.

**AC-0320 — M2: `fence_step` call removed from `append_run_terminal`.**
Target: `test_run_terminal_refuses_a_fenced_call`.
Result: FAILED — `Fenced` was not raised (wrong epoch was accepted). Confirms
the fence is pinned.

**AC-0324 — M1: `awaiting_decision` check removed from
`append_approval_decision`.**
Target: `test_approval_decision_refuses_when_not_awaiting`.
Result: FAILED — `DecisionRefused` was not raised (decision committed against a
step with `awaiting_decision = false`). Confirms the hold is pinned.

**AC-0324 — M2: latest-suspension seq check removed from
`append_approval_decision`.**
Target: `test_approval_decision_refuses_a_stale_suspension_seq`.
Result: FAILED — `DecisionRefused` was not raised (stale suspension seq
accepted). Confirms the staleness guard is pinned.

**AC-0332 — M: `approval.granted` and `approval.rejected` removed from
`append_step_event`'s refusal list (pre-0005 body restored).**
Target: `test_approval_decision_from_append_step_event_is_refused`.
Result: FAILED — `InsufficientPrivilege` was not raised (decision type was
accepted by the step path). Confirms the D3 widening is pinned.

**AC-0334 — the index, mutation-proved rather than deferred.** The implementer
deferred this one, reasoning that `DROP INDEX` "is not idempotent to restore
(requires re-running the migration)". That reason does not hold: the index
definition is a single statement in revision 0005 and `pg_indexes` returns it
verbatim, so the drop is restorable without touching alembic. Deferring it
would have left the criterion's whole point — that a replayed decision is
refused by the *database* and not by application code — resting on two checks
neither of which had been shown able to fail.

*Break applied.* `DROP INDEX public.events_decision_idempotency_idx` as the
`migration` role, confirmed absent from `pg_indexes`.

*Result.* Both checks went red — `test_a_replayed_decision_is_refused_by_the_unique_index`
and `test_the_decision_index_covers_the_declared_types`. So the behavioural
check is genuinely decided by the index and not by an application-level guard
that would have kept it green.

*Restored.* Index recreated from the `pg_indexes` definition; the full module
returns 28 passed.

**One false start, recorded because it is the trap this proof exists to avoid.**
The first attempt connected as a `owner` role that does not exist, so the drop
raised, the index was never removed, and the replay test passed. That pass was
evidence of nothing. A mutation proof whose break silently fails to apply looks
exactly like a proof that succeeded.

### Round 6 repairs

Round 6 redesigned `append_approval_decision` to set-valued parallel arrays,
added two new fence-path tests, tightened the happy-path seq assertion, and
redesigned the index-coverage test to use set equality. Each new or redesigned
check is mutation-proved below. Mutants were installed via `CREATE OR REPLACE
FUNCTION` (or `DROP/CREATE INDEX`), the targeted test was observed to fail, and
the original was restored and confirmed green. Proofs ran on 2026-09-27 against
the live substrate at revision 0005.

**AC-0320 — M (fence tests, never-leased and expired-lease): `fence_step` call
removed from `append_run_terminal`.**
Targets: `test_run_terminal_refuses_a_never_leased_step` and
`test_run_terminal_refuses_an_expired_lease`.
Result: BOTH FAILED — the function accepted a step with `owner = NULL` and a
step with `lease_expires_at` in the past, committing the terminal event in each
case. Confirms both new fence-path tests are genuinely decided by the fence
call.

**AC-0324 — M (concurrent decisions): `FOR UPDATE` removed from the steps lock
in `append_approval_decision`.**
Target: `test_concurrent_decisions_against_one_suspension_exactly_one_commits`.
Result: FAILED — both concurrent callers committed (`committed=[2, 3]`,
`refused=[]`; assertion expected `len(committed) == 1`). Confirms the `FOR
UPDATE` is what serialises concurrent decisions and enforces the exactly-one
property.

**AC-0324 — M (seq tightening): `append_approval_decision` modified to
`RETURN p_suspension_seq` instead of `RETURN v_seq`.**
Target: `test_approval_decision_happy_path_clears_hold_and_advances_cycle`.
Result: FAILED — returned `1` (the suspension seq) instead of `2` (the decision
event's seq); the `assert seq == 2` assertion caught it. Confirms the tightening
from `seq >= 1` to `seq == 2` is not decorative and pins the actual returned
value.

**AC-0334 — M (index coverage redesign): `approval.rejected` dropped from
`events_decision_idempotency_idx` WHERE clause.**
Target: `test_the_decision_index_covers_the_declared_types`.
Result: FAILED — index WHERE clause covered only `{'approval.granted'}`;
set equality against `{'approval.granted', 'approval.rejected'}` failed with
`Extra items in the right set: 'approval.rejected'`. Confirms the redesigned
set-equality assertion catches a partial index.

### Round 6 supplemental proofs (addressing coordinator gaps)

Three missing refusal tests added and five additional proofs run on 2026-09-27.

**New tests (AC-0324 refusal predicates, violating call per predicate):**
`test_approval_decision_refuses_an_empty_decision_set` (empty arrays →
`StepRunMismatch`), `test_approval_decision_refuses_an_empty_call_id` (empty
string in `call_ids` → `MalformedEventType`), and
`test_approval_decision_refuses_mismatched_array_lengths` (two call_ids, one
decision → `StepRunMismatch`). All three pass green against the live database.

**AC-0320 — M (atomicity rewrite): `append_run_terminal` modified to use a
PL/pgSQL sub-transaction (`BEGIN … EXCEPTION WHEN unique_violation THEN NULL;
END`) that swallows `UniqueViolation` so the `UPDATE public.runs` commits even
when the `INSERT INTO events` fails.**
Target: `test_run_terminal_atomicity_state_does_not_move_on_failure`.
Result: FAILED — `pytest.raises(psycopg.errors.UniqueViolation)` reported
`Failed: DID NOT RAISE UniqueViolation`, proving the mutant committed the state
change without raising. The test was the deciding layer: the sub-transaction
exception handler is exactly the class of non-atomicity this check exists to
catch. Restored, PASSED.

**AC-0334 — M (index drop, new test forms): `events_decision_idempotency_idx`
dropped as the `migration` role; absence confirmed in `pg_indexes` before
trusting the red.**
Targets: `test_a_replayed_decision_is_refused_by_the_unique_index` (primary
target) and `test_different_call_ids_produce_different_keys_in_one_suspension`
(observed).
Result: `test_a_replayed_decision_is_refused_by_the_unique_index` FAILED —
the function no longer raised `UniqueViolation` for the duplicate call_id pair,
confirming the redesigned test is genuinely decided by the index.
`test_different_call_ids_produce_different_keys_in_one_suspension` PASSED —
this is the correct outcome: two distinct call_ids do not hit the unique
constraint, so that test's correctness is independent of the index. Both
outcomes recorded rather than the green one omitted. Restored, both PASSED.

**Lock-order generalisation — M: `append_approval_decision` body reordered so
`UPDATE public.runs SET next_seq = next_seq + 0` (acquiring the runs lock)
precedes `SELECT … FROM public.steps … FOR UPDATE`.**
Target: `test_both_append_paths_take_the_steps_lock_first`.
Caveat and resolution: the first mutant included a comment containing the
substring "FOR UPDATE", which caused `body.index("FOR UPDATE")` to find the
comment text before the actual SQL, making the check pass despite the inverted
order. A second mutant was installed with the comment rewritten to remove that
substring. With the comment corrected, `body.index("UPDATE public.runs")` = 1770
and `body.index("FOR UPDATE")` = 2061; `steps_lock_at < allocate_at` was False.
Result: FAILED — `append_approval_decision acquires a runs lock before the steps
lock, inverting the ratified lock order` (assert 2061 < 1770). The check names
the function correctly. The comment-substring trap is recorded because a body.index
fallback on a function with "FOR UPDATE" in a comment would silently pass; this
proof shows the check is correct when comments are neutral. Restored, PASSED.

*Incidental finding: the `try/except ValueError` fallback in the structural
check can be fooled by a comment containing "FOR UPDATE" appearing before
"UPDATE public.runs" in the function body. The check passes for the right reason
on the actual shipped functions because they carry no such comment. This is noted
as a known fragility of string-position checks on SQL bodies, not fixed here.*

**AC-0332 — `proowner` assertion: test temporarily mutated to `assert owner ==
"not_ced_owner"`.**
Target: `test_the_replaced_step_function_retains_security_definer_and_search_path`.
Result: FAILED — `assert 'ced_owner' == 'not_ced_owner'` at the exact assertion
line, proving the `pg_get_userbyid(p.proowner)` fetch and the equality check are
the deciding layer. Restored to `"ced_owner"`, PASSED.

**Gate count after supplemental proofs: 907 passed, 3 skipped (full substrate
suite, 2026-09-27). Offline suite: 640 passed, 270 deselected.**

### Round 6 second-pass proofs (addressing second-pass coordinator gaps)

Two defects found on re-read, fixed, and proved on 2026-09-27.

**Defect 1: three new refusal tests pinned wrong exceptions.**
The empty-set and mismatched-lengths predicates raised `invalid_parameter_value`
in SQL, which the wrapper at `:479` maps to `StepRunMismatch` — documented as
"the fenced step does not belong to the run being appended to". The empty
call_id predicate raised `CED01`, mapped to `MalformedEventType` — documented as
"the event type is not a dotted run of lowercase ASCII alphanumerics". Neither
class says what actually went wrong; both contradict the docstring at `:150–158`
that requires the mapping to be one no other failure on the same call can
produce.

*Fix.* All four pre-lock validation predicates (empty set, mismatched lengths,
null/empty call_id, null decision) now raise `serialization_failure`. The wrapper
maps `serialization_failure` to `DecisionRefused`, whose docstring is extended to
cover the "malformed submission" category alongside the structural predicates.
`serialization_failure` is the only SQLSTATE these sites can produce before any
database lock is taken, satisfying the exact-mapping requirement. The three test
assertions updated from `StepRunMismatch`/`MalformedEventType` to `DecisionRefused`,
and all three pass green against the fixed live function. Migration file updated
to match.

**Defect 2: lock-order anchor measured a comment, not the lock.**
The shipped `append_approval_decision` body carries the comment
`-- The FOR UPDATE serialises concurrent decisions on the same step:` at an
early position in `prosrc`. `body.index("FOR UPDATE")` found this comment text
(position 2268 raw) before `"UPDATE public.runs"` (position 4332 raw), making
the structural check pass for the wrong reason. An inversion of the real SQL
while the comment stayed in place would not have been caught.

*Fix.* `test_both_append_paths_take_the_steps_lock_first` now strips `--[^\n]*`
from `prosrc` via `re.sub` before any `index()` call. Comments are thereby
excluded from both anchor searches.

*Proof.* A mutant was installed with the SQL order inverted (runs UPDATE before
steps FOR UPDATE) and the original comment `-- The FOR UPDATE serialises...`
left exactly as shipped at its early position. Raw positions: `FOR UPDATE` at
1745 (comment), `UPDATE public.runs` at 2062 — naive check passes (for wrong
reason, comment wins). Stripped positions: `FOR UPDATE` at 1910 (actual SQL),
`UPDATE public.runs` at 1701 — stripped check FAILED with:
`append_approval_decision acquires a runs lock before the steps lock,
inverting the ratified lock order (assert 1910 < 1701)`. The check now names
the function correctly regardless of comment placement. Restored, PASSED.

### A defect T1 surfaced in the gate suite

**`test_migration_applies.py` hardcoded `"0004"` as the expected HEAD
revision.** Two assertions — one in `test_a_migration_blocked_by_a_reader_aborts_rather_than_queueing`
and one in `test_the_lock_timeout_override_reaches_the_migration_session` —
used the literal string `"0004"` rather than the current HEAD. Both updated to
`"0005"` as in-scope T1 work: `tests/schema/**` is in T1's `Touches` (plan.md
line 117) and the change is forced by T1's own revision 0005, so it is not an
unrelated discovery carried along.
