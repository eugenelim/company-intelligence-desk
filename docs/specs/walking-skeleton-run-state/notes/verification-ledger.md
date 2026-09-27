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
