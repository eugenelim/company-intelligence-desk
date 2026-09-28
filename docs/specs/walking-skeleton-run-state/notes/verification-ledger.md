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
- `src/ced/domain/events.py` — `APPROVAL_GRANTED`,
  `APPROVAL_REJECTED`, `DECISION_TYPES` constants added.
- `src/ced/adapters/postgres/event_log.py` — `RunNotRunning`, `DecisionRefused`
  exceptions; `append_run_terminal` and `append_approval_decision` Python
  wrappers added.
- `tests/schema/test_run_state_paths.py` — `@pytest.mark.substrate` tests
  covering AC-0320, AC-0324, AC-0332, and AC-0334 with the four plan stubs
  materialized byte-identically.
- `tests/event_log/test_definer_hardening.py` — definer count updated 4 → 6;
  `DECISION_TYPES` added to the refused-set comparison; `approval.granted` and
  `approval.rejected` added to the step-path parametrize
  Round 8 then replaced the flattened-string `search_path` substring check with
  exact `proconfig` list membership; the Round 9 proof below is what shows that
  tightening is load-bearing.

**Gates:** `ruff format --check`, `ruff check`, `mypy`, `pytest -m 'not substrate'`,
`pytest` (full substrate suite). Canonical full-suite result after all rounds:
**910 passed, 3 skipped** (2026-09-27).

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

*Restored.* Index recreated from the `pg_indexes` definition; the targeted tests
returned green. That restore predates the rule below, which forbids restoring
from the live catalogue — the rule is scoped to what the hazard needs, so read
it as covering function bodies. A body is seventy lines of hand-replicated SQL
and a pasted copy is how this task shipped a guard the migration never wrote; a
`CREATE UNIQUE INDEX` is one statement, and the Round 9 diff below re-derives it
from the rendered revision rather than trusting this line.

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

*Note: the `try/except ValueError` fallback concern (a comment containing "FOR
UPDATE" before the actual SQL) was raised during this round. It is resolved in
the Round 6 second-pass section below: `re.sub` strips all `--` comments from
`prosrc` before any `index()` call, removing the fragility entirely.*

**AC-0332 — `proowner` assertion: test temporarily mutated to `assert owner ==
"not_ced_owner"`.**
Target: `test_the_replaced_step_function_retains_security_definer_and_search_path`.
Result: FAILED — `assert 'ced_owner' == 'not_ced_owner'` at the exact assertion
line, proving the `pg_get_userbyid(p.proowner)` fetch and the equality check are
the deciding layer. Restored to `"ced_owner"`, PASSED.

All supplemental tests passed green.

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

### Round 7: the evidence was about the wrong database

Round 7 sustained nine findings. Two were blockers and the second one is the
reason this section exists rather than being another list of repairs.

**The guard that was never a guard.** Revision 0005 rendered the empty-`call_id`
predicate as `p_call_ids[v_i] = ''''` inside a dollar-quoted `AS $$ … $$` body.
No quote-doubling applies there, so Postgres lexes `''''` as the one-character
literal `'`: on this substrate `('''' = '')` is false, `length('''')` is 1 and
`ascii('''')` is 39. The guard asked whether the call id was a single
apostrophe. An empty one passed, took the hold, cleared `awaiting_decision`,
advanced the counter and committed an event keyed `<seq>:`. Revision 0002
contains no occurrence of `''''`, so the precedent was available and unread.

**Why three rounds of green said nothing.** The running database carried
`= ''` while the file carried `''''` — a body that existed in no file and was
never produced by this migration. It got there because a mutation proof
restored its original by pasting a body rather than by re-executing the
revision. From that moment the suite measured a database nobody was shipping,
and `test_approval_decision_refuses_an_empty_call_id` — added specifically to
close a predicate that had no asserting call — passed on a function that did
not contain the predicate.

**The rule this establishes, which costs nothing to follow.** Restore a mutant
by re-executing the migration's generator, never by pasting a body. Before
recording any `substrate` result as evidence, diff `pg_proc.prosrc` against the
**rendered** migration (f-string sites substituted), diff index definitions
against `pg_indexes`, and diff the `EXECUTE` grantee sets of every function
revision 0005 creates or replaces against the applied schema. Say in the record
that they matched. A green suite is a claim about whatever schema is loaded;
without that diff it is not a claim about the tree.

**Evidence retaken.** `docker-compose down -v`, fresh volume, `alembic upgrade
head`, workers. Every earlier proof was re-run against that database, restoring
by generator.

*Rendered-vs-`prosrc` diff (2026-09-27).* Migration SQL was rendered by
capturing `op.execute` calls (substituting `{_DEFINER_SEARCH_PATH}` and
`{_DECISION_SQL_LIST}`); the body between `AS $$` and `$$` was extracted for
each function and compared line-by-line against `pg_proc.prosrc`. Result:
**zero-diff** for `append_approval_decision`, `append_run_terminal`, and
`append_step_event`. The rendered body and `prosrc` are identical.

*EXECUTE grantee sets (from `information_schema.routine_privileges`, scoped by
`specific_name`):*
- `append_approval_decision`: `{'ced_owner', 'app_api'}`
- `append_run_terminal`: `{'ced_owner', 'app_worker'}`
- `append_step_event`: `{'ced_owner', 'app_worker'}`

All three match the disjoint grant structure ADR-0009 D1/D2/D3 requires.

**AC-0324 — M (the empty-`call_id` guard), proved rather than assumed.** This
check had never been shown able to fail. The migration's SQL was rendered by
capturing `op.execute`, the single occurrence of `= ''` was replaced by `= ''''`
and installed, and the mutant was confirmed present in `prosrc` before the run.
Result: `test_approval_decision_refuses_an_empty_call_id` FAILED with
`Failed: DID NOT RAISE DecisionRefused`, and the two sibling refusal checks
stayed green — so the break is located, not diffuse. Restored by re-executing
the rendered original, confirmed absent from `prosrc`, module green again.

### Round 7 addition: AC-0334 cross-call replay

**The ruling.** AC-0334 left "replayed decision" undefined as to layer. Settled
as **both** cases — intra-call (duplicate `call_id` within one array call) and
cross-call (same suspension seq, same `call_ids`, same decisions resubmitted as
a separate request). No spec amendment: AC-0324 already states the ranking:
"AC-0334's unique index is the second line of defence and not the first, because
it keys on the call id rather than on the suspension." The criterion is satisfied
by the refusal, not by a particular layer performing it.

**New test added.** `test_a_cross_call_replay_is_refused_by_the_awaiting_hold`
in `tests/schema/test_run_state_paths.py`. Commits a decision through the
`app_api` grant; resubmits the identical set (same seq, same `call_ids`, same
decisions) as a second separate call; asserts `DecisionRefused` carrying "is not
awaiting a decision" — not `UniqueViolation`. No out-of-band state writes; both
calls go through `app_api`. The docstring names AC-0324's second-line-of-defence
sentence and explains why the index is not the refusing layer here.

**The two assertions after the refusal are not alike, and an earlier revision of
this paragraph said they were.** `count_after == count_before` does record the
transaction boundary: the wrapper calls the function inside
`with conn.transaction()`, `count_before` is read after the *first* call
commits, so once `pytest.raises(DecisionRefused)` is satisfied that assertion
holds for every implementation that raises there. It is kept because it states
something true, not because it decides anything.

`approval_cycles == 1` is a different matter. It constrains the **first** call's
counter write, which no rollback touches, and it is live — see the Round 9 proof
below. Round 8 labelled both as recording the transaction boundary; that was
right for the first and wrong for the second. A label saying a live check
decides nothing is worse than no label, because the next reader deletes the
check on the strength of it.

**Mutation proof.** Migration SQL rendered by capturing `op.execute`; guard block
`IF NOT v_awaiting THEN RAISE … END IF;` replaced by a comment and installed via
the migration role. `pg_proc.prosrc` confirmed guard absent before running
anything. Results:
- `test_a_cross_call_replay_is_refused_by_the_awaiting_hold` FAILED — second
  call raised `UniqueViolation` (index caught the replay instead of the hold),
  not `DecisionRefused` as the test required. Confirms the guard is the deciding
  layer.
- `test_a_replayed_decision_is_refused_by_the_unique_index` PASSED — the
  intra-call test is decided by the index, not the `awaiting_decision` guard.
  The two tests pin different layers and do not duplicate each other.

Restored by re-executing the rendered original SQL; `pg_proc.prosrc` confirmed
guard present and mutant comment absent, and the suite green. The one
canonical suite count for this task is in § Gates above; it is not restated
here, because a figure repeated per section is how this file disagreed with
itself across three rounds.

### Round 8 repairs

This section records round 8's repairs and their proofs. It carries no tally of
what the round found: the adjudications in `.context/reviews/` are the record of
that, and a count here promised entries this section did not hold.

**AC-0334 — mixed-decision pairing mutation proof (Blocker 1).** The
`test_different_call_ids_produce_different_keys_in_one_suspension` test was
previously asserting only that both types and both keys were present as
independent sets, discarding the `(call_id, type)` association. An
implementation that stamped the reversed decisions on the call ids would have
passed every assertion. Fixed by asserting the exact pair set:
`{(f"{seq}:call-a", "approval.granted"), (f"{seq}:call-b", "approval.rejected")}`.

*Mutation proof.* Migration SQL rendered by capturing `op.execute`; the INSERT
line `lower(p_decisions[v_i])` replaced with `lower(p_decisions[v_n - v_i + 1])`
(one occurrence in the INSERT statement; the type-check occurrence left intact).
`pg_proc.prosrc` confirmed `v_n - v_i + 1` present before running.
Result: `test_different_call_ids_produce_different_keys_in_one_suspension` FAILED
with `expected exact (idempotency_key, type) pairs, got [('1:call-a',
'approval.rejected'), ('1:call-b', 'approval.granted')]` — the reversed
implementation stamped call-a with `approval.rejected` and call-b with
`approval.granted`, exactly the mispairing the new assertion catches.
Restored by re-executing the rendered original SQL; `pg_proc.prosrc` confirmed
`v_n - v_i + 1` absent.

**AC-0324 — grantee equality (Blocker 2).** `test_the_approval_decision_path_is_granted_to_app_api_only`
was asserting named exclusions, leaving a fourth grantee silent. `plan.md:120`
pins "exactly the named role"; ADR-0009 D2 grants to "app_api alone". Fixed by
replacing with `assert grantees == {"ced_owner", "app_api"}`, matching the
AC-0320 twin.

**AC-0332 — grantee equality (Concern).** No test read the grantee set for
`append_step_event`. Added `test_append_step_event_execute_is_granted_to_app_worker_only`
asserting `grantees == {"ced_owner", "app_worker"}`, `specific_name`-scoped.
`CREATE OR REPLACE` does not reset ACLs, so the behavioural privilege tests
cannot see an added fourth role; the equality assertion closes that gap.

**Coalesce asserting call.** `test_approval_decision_refuses_null_decisions_against_nonempty_call_ids`
added: passes `call_ids=["call-1"], decisions=[]` and asserts `DecisionRefused`
carrying "same length". The coalesce on `array_length(p_decisions, 1)` is what
catches a null/empty array; the per-element null check fires for a null element,
not for a missing array, and would produce a different message.

**Rendered-vs-`prosrc` diff retaken.** Previous wording described a diff against
the migration's source text (with f-string sites unsubstituted) while claiming it
was a diff against the rendered SQL. Re-run with f-string sites substituted:
zero-diff for all three functions (recorded in the round-7 section above under
"Rendered-vs-`prosrc` diff"). The pre-evidence rule was also extended to cover
EXECUTE grantee sets.

### Round 9: the proofs the record was missing

Round 9 sustained seven findings. One was a blocker against this file: round 8
had labelled a live check as deciding nothing. The rest were claims made here
without evidence. Every proof below was run by the controller, not transcribed
from the reviewer that reported it — a reviewer's run is a pointer to run, not a
result to copy, which is the same lesson § Round 7 records one level up.

**Pre-evidence diffs, all three surfaces this time.** The rule above names
`prosrc`, index definitions and grantee sets; the round-7 record covered only
two of them, so the third is taken here. Rendering revision 0005 by capturing
`op.execute` gives, for `events_decision_idempotency_idx`:

```
CREATE UNIQUE INDEX events_decision_idempotency_idx
    ON public.events (run_id, idempotency_key)
 WHERE type IN ('approval.granted', 'approval.rejected') AND idempotency_key IS NOT NULL
```

and `pg_indexes` gives:

```
CREATE UNIQUE INDEX events_decision_idempotency_idx ON public.events USING btree
(run_id, idempotency_key) WHERE ((type = ANY (ARRAY['approval.granted'::text,
'approval.rejected'::text])) AND (idempotency_key IS NOT NULL))
```

Same index. Postgres normalises `IN (...)` to `= ANY (ARRAY[...])`, spells the
default access method, adds the casts and parenthesises the predicate. A reader
comparing the two by eye should expect those five differences and no others.
Grantee sets read at the same time: `append_run_terminal` and
`append_step_event` are `{ced_owner, app_worker}`, `append_approval_decision` is
`{ced_owner, app_api}`.

**AC-0334 — M (the cycle counter): `approval_cycles + 1` rendered as
`approval_cycles + 2`.**
Target: `test_a_cross_call_replay_is_refused_by_the_awaiting_hold`.
Result: FAILED, with `test_approval_decision_happy_path_clears_hold_and_advances_cycle`
and `test_different_call_ids_produce_different_keys_in_one_suspension` red
beside it. The mutant still clears the hold and still raises at the hold, so
`pytest.raises(DecisionRefused)` was satisfied and the counter assertion is what
reds. This is the proof that round 8's label was false: the assertion decides
something. Restored through the rendered generator; `approval_cycles + 2`
confirmed absent.

**AC-0320, AC-0324 and AC-0332 — M (the grantee equalities): `EXECUTE` granted
to a fourth role.**
Targets: the three grantee-set assertions.
Result: run first with `app_policy`, which reds **four** tests — the three
equalities plus `test_the_policy_role_cannot_reach_the_general_append_path`,
because a behavioural check names that role by hand. Re-run with `ced_fence`,
which no behavioural check names, and exactly the three equalities red. The
second run is the one that states the claim correctly: the equality assertions
are the only layer that detects a grantee no behavioural test happens to name,
which is narrower than "the only layer that detects an added grantee" and is
what they actually buy. Grants revoked; `proacl` re-read clean on all three.

**AC-0332 — M (the definer pin): `ALTER FUNCTION append_step_event SET
search_path = pg_catalog, pg_temp, public`.**
Targets: `test_the_definer_functions_are_configured_to_resist_temp_capture` and
`test_the_replaced_step_function_retains_security_definer_and_search_path`.
Result: both FAILED, while `test_exactly_one_append_step_event_survives_the_replacement`
stayed green on its weaker `"pg_temp" in ...` substring — which is precisely the
gap the round-8 tightening closes, demonstrated rather than argued. `proconfig`
read back before the run to confirm the break applied. Restored on all six
definer functions and re-read.

**AC-0324 — M (the coalesce): `coalesce(array_length(p_decisions, 1), 0) <> v_n`
rendered as `array_length(p_decisions, 1) <> v_n`.**
Target: `test_approval_decision_refuses_null_decisions_against_nonempty_call_ids`.
Result: FAILED, and alone — the sibling length-mismatch test stayed green, so
the new test is the only check that pins the `coalesce`, and its assertion on the
message text is what makes it so.

**A trap inside this proof, recorded because it nearly passed.** The first
break-verification predicate was `prosrc LIKE '%coalesce(array_length%'`, which
returned true *after* the break applied — the body carries a second, untouched
`coalesce(array_length(p_call_ids, 1), 0)` that the pattern also matches.
Checking the exact mutated expression showed the break had landed. Had it not,
that predicate would have reported success either way. A break-verification
predicate has to name the break, not a substring a neighbour satisfies; this is
§ Round 7's lesson one level down, inside the proof rather than around it.

**After all of it**, the two touched modules return 142 passed and the substrate
is in the state it started: bodies matching the rendered migration, grantee sets
and `proconfig` restored, index unchanged.

### A defect T1 surfaced in the gate suite

**`test_migration_applies.py` hardcoded `"0004"` as the expected HEAD
revision.** Two assertions — one in `test_a_migration_blocked_by_a_reader_aborts_rather_than_queueing`
and one in `test_the_lock_timeout_override_reaches_the_migration_session` —
used the literal string `"0004"` rather than the current HEAD. Both updated to
`"0005"` as in-scope T1 work: `tests/schema/**` is in T1's `Touches` (plan.md
line 117) and the change is forced by T1's own revision 0005, so it is not an
unrelated discovery carried along.

## T2 — the transitions, and the interface that releases one

**Date:** 2026-09-27. **Mode:** TDD (four pinned stubs confirmed red before green).

**What was produced.**

- `src/ced/domain/run_state.py` — `apply_event`, `project_run_state` (pure
  projection over the three committed edges).
- `src/ced/worker/prerelease.py` — `check_prerelease_failed` (reads
  `model_settings.needs_approval`; absent or falsy → check passes).
- `src/ced/worker/liveness.py` — `LivenessState`, `liveness_state`,
  `refresh_mark`, `probe`, `run`.
- `src/ced/worker/executor.py` — `offered_approval_gated_tools`, outer
  transaction wrapping `runs.state='running'` UPDATE with `step.started`,
  `awaiting_decision=true` on suspension, `append_run_terminal` calls on
  completion and failure.
- `src/ced/worker/persistence.py` — `approval_results_for_cycle`, and
  `resume_step` uses it instead of approving blindly.
- `src/ced/worker/pool.py` — `AND NOT awaiting_decision` in claim predicate,
  `refresh_mark` on idle and heartbeat paths.
- `src/ced/api/main.py` — `POST /runs/{run_id}/steps/{step_id}/decision` route
  with Origin CSRF check.
- `src/ced/api/models.py` — `DecisionPair`, `ApprovalDecisionRequest`,
  `DecisionResult`.
- `contracts/openapi/runs.yaml` — 4th route and three new schemas.
- `tests/suspension/test_the_gate_is_conditional.py` — AC-0302 and AC-0330
  stubs, materialized byte-identically and confirmed red before green.
- `tests/worker/test_liveness.py` — AC-0331 stub, materialized byte-identically
  and confirmed red before green.
- `tests/schema/test_run_state_paths.py` — AC-0333 stub appended.
- `tests/api/test_contract_agreement.py` — renamed to `four_routes`, count 4.
- Several existing test files updated for the `_run_compiled_agent` signature
  change (`toolsets: list[...]`) and for the new `awaiting_decision` flow.

**Gates:** `ruff format --check`, `ruff check`, `mypy`, `pytest -m 'not substrate'`
(642 passed, 275 deselected), `pytest` excluding `fault_injection`
(268 passed, 3 skipped, 642 deselected). All repository checks clean.

### Mutation proofs

**AC-0302 — M: `offered_approval_gated_tools` mutated to always return `[]`.**
Target: `test_the_gated_tool_is_offered_only_when_a_check_failed`.
Result: FAILED — `assert [] != []` at the positive arm
(`offered_approval_gated_tools(prerelease_failed=True) != []`). Confirms the
positive arm is the deciding check; the exclusion arm alone cannot pass this test.
Restored (reverted the mutant line); targeted test PASSED.

**AC-0331 — M: `liveness_state` mutated to always return
`LivenessState(healthy=False)`.**
Target: `test_an_idle_worker_reports_healthy`.
Result: FAILED — `assert False is True` at
`liveness_state(seconds_since_poll=1.0, lease_ttl_seconds=60).healthy is True`.
Confirms the `healthy` field is the deciding predicate.
Restored; targeted test PASSED.

**AC-0330 — M: `suspension_row is None` guard replaced by `if False`.**
Target: `test_a_resume_with_no_committed_decision_refuses_to_run`.
Result: FAILED — `TypeError: 'NoneType' object is not subscriptable` at
`suspension_seq = int(suspension_row[0])`; `pytest.raises(LookupError)` was
not satisfied. The no-suspension guard is the deciding layer for the test's
nonexistent step id. Restored; targeted test PASSED.

**AC-0333 — schema check only.** The stub
`test_a_step_awaiting_a_decision_is_not_claimed` checks the column exists in
the schema. The column was created in T1 (revision 0005) and proved present
there; AC-0333's behavioral guard is exercised by the extended
`test_a_step_suspends_releases_its_lease_and_is_claimable` assertion (Assertion
3: `claim_one` returns `None` while `awaiting_decision=true`; Assertion 4: after
`append_approval_decision` clears the hold, the step is claimable).

### Post-submission fix: real principal on AC-0330 terminal events

**2026-09-27.** The initial submission wrote `principal=""` on the `step.failed`
and `run.failed` appends in the `LookupError` handler (`:209`, `:218`), with the
comment "principal not yet read; failure is pre-principal". The coordinator ruled
this a defect: `read_run_principal` runs against a run record that already exists
when the refusal fires, and an empty principal on a terminal event in an
append-only log is not a style point.

Fix: moved the `read_run_principal` call above the `approval_results_for_cycle`
call so the real principal is available to both the refusal path and the main
path. Both appends in the `LookupError` handler now receive `principal=principal`.
Full suite re-run after the fix: **914 passed, 3 skipped** (2026-09-27,
231.80 s including `tests/fault_injection`).

### Design decision: `needs_approval` lives inside `model_settings`

The role record's JSONB `model_settings` column — not a dedicated top-level
column — carries the `needs_approval` flag. Revision 0005 adds no
`needs_approval` column, and `_ROLE_COLUMNS` in `roles.py` does not enumerate
one. Placing the flag inside `model_settings` (alongside `model_id`, `settings`,
and `limits`) keeps the flag co-located with the model configuration it governs.
Any substrate test whose role must trigger suspension sets
`"needs_approval": True` inside `model_settings`. The
`check_prerelease_failed` docstring records the rationale.
