# ADR-0009: The run-terminal and approval-decision append paths, and who holds them

- **Status:** Accepted
- **Date:** 2026-09-27
- **Areas:** schema, identity
- **Reversibility:** low
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** none
- **Superseded by:** none
- **Superseded in part:** none

## Context

`walking-skeleton-run-state` has to move a run to `completed` and has to let a
person release a suspension. The shipped privilege split has room for neither.

**No identity can append a run-terminal event.** `append_run_event` admits
exactly `run.requested` and `run.cancelled` and is granted to `app_api` alone;
`append_step_event` refuses the whole terminal namespace and is granted to
`app_worker` alone; direct `INSERT` on `events` is revoked from all three
application roles. Nothing writes `runs.state` at all — the column is read by
`append_run_event`'s terminal guard and by the pool's heartbeat, and written by
no code.

**No identity can append the approval decision either, at the moment r5 places
it.** r5 § 3 releases the lease *before* the approver acts, which clears
`owner`, so `fence_step`'s possession predicate fails and every fenced append
raises.

**r8 disagrees with itself about who may write a run-lifecycle type.** § 4 line
460 limits `api` to run-lifecycle types and `worker` to step-scoped ones; § 3's
sequence diagram at line 344 has the worker append `run.completed`. Both are
ratified. The privilege split § 4 calls "the whole control" is the disjointness
of the three `EXECUTE` grants, not the role/type table alone.

Separately, `append_step_event` refuses types by **denylist**, so
`approval.granted` is already an admitted step-scoped type on the path
`app_worker` holds — an exclusivity claim at the function level would assert a
property the grant set does not have.

## Decision

- **D1:** Revision 0005 adds a **run-terminal** definer function granted to
  `app_worker` alone, fenced through the shipped `fence_step` on the step that
  completed the run, writing `step_id` null, and committing the `runs.state`
  change and the terminal event in one transaction. § 3's diagram is the
  reading kept; § 4 line 460 is deviated from.
- **D2:** Revision 0005 adds an **approval-decision** definer function granted
  to `app_api` alone, committing while no worker holds the step. It cannot be
  fenced, because by construction nobody holds the lease; a committed
  `step.suspended` event — which only the worker's fenced path can append — and
  the step's `awaiting_decision` hold stand in for possession.
- **D3:** Revision 0005 re-issues `append_step_event` through
  `CREATE OR REPLACE`, adding the two approval types to its refusal list, so
  the decision types are exclusive at the **type** level rather than merely at
  the function level. Editing revision 0002's constant is refused: it is
  rendered into the function body at `CREATE FUNCTION` time and would reach no
  already-migrated database.

## Consequences

**What this buys.** Both new paths carry the predicate sets their shipped
siblings carry, not merely the grant that names their caller, and the grants
stay disjoint — no role gains `EXECUTE` on a function another already holds.
The decision path's exclusivity becomes assertable against the applied schema.

**What it costs.** r8 § 4 line 461 ratifies "the fence proves possession" as
*Built*; D2 makes that untrue for `approval.granted` and `approval.rejected`.
D3 narrows a foundation-owned function, which is the safe direction and still a
contracting change to another spec's artifact. Both are recorded as residuals
under `walking-skeleton-run-state` AC-0329 rather than left for a reader to
infer.

**What it does not close.** `app_api` retains `INSERT ON steps`, so it can
create a step, let a worker claim and suspend it, and then decide against a step
it caused to exist. The exclusivity is over the event type, not over causation.

**Revisit if:** r8 gains a consistency pass that settles § 4 line 460 against
§ 3 line 344, or an ingress supplies an authenticated subject — the second
would change what the decision path's identity is actually protecting.

## Alternatives considered

**Widen `append_run_event`'s allowlist and grant it to `app_worker` too.**
Rejected: the function is unfenced, so the worker could append `run.cancelled`
against any `run_id`, and two roles would share one function — breaking the
disjointness § 4 calls the whole control.

**Let the API write the terminal state on the worker's behalf.** Rejected: it
reintroduces the first alternative through a different door, and gives the
internet-facing role the power to close any run's stream.

**Grant the decision path to `app_worker`.** Rejected: the process that
suspends a step would hold the path that commits its own grant.

**A fourth database role holding only the decision path.** Rejected on cost:
it adds a role, a DSN and boot wiring to a delivery that adds no deployment,
for a separation `app_api` already supplies.

## References

- Deviated from: [`runtime-architecture.md`](../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8 § 4 lines 460–461, against § 3 line 344
- Lease release before the approver acts: [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 3, line 604
- Shipped split: `migrations/versions/0002_append_paths_and_privilege_split.py`
- Resting criteria: [`walking-skeleton-run-state`](../specs/walking-skeleton-run-state/spec.md) AC-0320, AC-0324, AC-0332, AC-0334
- Fence owner and possession: [ADR-0004](0004-fence-function-owner.md), [ADR-0005](0005-the-fence-proves-lease-possession.md)
