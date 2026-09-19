# ADR-0004: The fence function has its own owner, not the worker's

- **Status:** Accepted
- **Date:** 2026-09-18
- **Areas:** identity, schema
- **Reversibility:** high
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** none
- **Superseded by:** none
- **Superseded in part:** none

## Context

The `policy.decision` append is fenced on the step's lease epoch, and the role
that performs it —`policy-writer` — must gain no table access. `worker-runtime.md`
§ Changes this design asks of r7 item 1 names two ways to achieve that:

1. grant `policy-writer` `SELECT` and a row lock on `steps`, nothing more; or
2. expose a `SECURITY DEFINER` fence function **owned by `worker`**, so
   `policy-writer` gains no table access at all.

It prefers the second, on the ground that it "preserves r7's narrowness at the
cost of one more definer function". `walking-skeleton-foundation` implemented
it, and the plan's § Changes asked of r7 disposition table records that choice.

**Review round 1 established that the preferred option is unsafe, and the
reason is not about privilege width.** In Postgres, a function's owner may
always `ALTER` or `DROP` it; that authority follows from ownership and is not
removed by revoking `CREATE` on the schema, which only blocks
`CREATE OR REPLACE`. Owning the fence therefore gives `app_worker` — the role
the split exists to distrust — two capabilities the design never intended:

- **`DROP FUNCTION fence_step`** breaks `append_step_event` *and*
  `append_policy_decision` for every role, so the distrusted role can disable
  the authorization-audit write path it is specifically forbidden to write to.
- **`ALTER FUNCTION fence_step SET search_path`** lets it point the fence's own
  name resolution at a schema it controls.

Both were confirmed as `InsufficientPrivilege`-free under the original
ownership and both are refused under this decision. Two independent reviewers
raised it; adjudication ruled it an owner question rather than an
implementation defect, precisely because the implementation had followed the
ratified text.

## Decision

- **D1:** `fence_step` is owned by `ced_fence`, a role created solely to own
  it. `ced_fence` is `NOLOGIN` and is granted to no application role, so no
  runtime identity can authenticate as it and none can therefore `ALTER` or
  `DROP` the fence. `ced_owner` is a member of it only so a migration can
  assign ownership.
- **D2:** `ced_fence` holds exactly `USAGE` on the schema and `SELECT` plus
  `UPDATE` on `steps` — what `SELECT … FOR UPDATE` requires and nothing else.
  The privilege narrowing r4 item 1's second option was chosen for is therefore
  preserved in full: the fence still runs at a privilege far below the schema
  owner's, and `policy-writer` still gains no table access.
- **D3:** This **narrows `worker-runtime.md` item 1's second option** rather
  than reverting to its first. It is not a reversal: item 1's stated goal —
  the fence exists, and `policy-writer` gains no table access — is met
  unchanged. What changes is which identity owns the function. r4's own text is
  amended by reference here rather than edited, because r4 is ratified and its
  outstanding r8 consistency pass is where the edit belongs.
- **D4:** The negative property is a test, not a note: the suite asserts that
  `app_worker` is refused `DROP FUNCTION`, `ALTER FUNCTION … SET search_path`
  and `ALTER FUNCTION … OWNER TO` on the fence. A control whose defeat nobody
  has attempted is not a control.

## Evidence

Probed against the running local substrate, 2026-09-18, every mutating
statement rolled back:

| Statement, as `app_worker` | Under r4's preferred ownership | Under D1 |
| --- | --- | --- |
| `DROP FUNCTION fence_step` | succeeded | `InsufficientPrivilege` |
| `ALTER FUNCTION fence_step SET search_path` | succeeded | `InsufficientPrivilege` |
| `ALTER FUNCTION fence_step OWNER TO app_worker` | n/a (already owner) | `InsufficientPrivilege` |

**What this evidence does not cover.** It is a local container, not a managed
service, and nothing here tests whether a cloud provider's superuser surrogate
role behaves the same way. The grant matrix is core Postgres and should carry.

## Consequences

**Positive:**

- The role the privilege split distrusts can no longer disable the control that
  constrains it, which is the property r4 item 1 was reaching for and did not
  reach.
- The fence still runs far below the schema owner's authority, so the
  narrowing that motivated item 1's second option is kept rather than traded.

**Negative, and accepted:**

- **One more role to provision.** A deployed system must create `ced_fence`
  and grant it to whichever identity runs migrations. That is a line in the
  provisioning path, and it is the cost of the fence not being owned by a
  process identity.
- **This document, not r4, now carries the mechanism.** A reader of
  `worker-runtime.md` item 1 alone will read the superseded choice. Mitigated
  only by this record and by the migration's docstring naming it; properly
  resolved when the r8 pass folds it in.

**Revisit if:** the r8 consistency pass restates item 1, or a deployment finds
that its migration identity cannot be granted membership of a role it does not
own, or `policy-writer` acquires a legitimate need for direct `steps` access
that would make item 1's first option simpler.

## Confirmation

- **Mode:** test
- **Signal:** the suite's three refusal assertions on `fence_step` pass, and
  `pg_proc` reports its owner as `ced_fence`. Either the ownership changing or
  any of the three statements succeeding is the failure signal.
- **Owner:** eugenelim

## Alternatives considered

- **`worker-runtime.md` item 1's first option — grant `policy-writer` `SELECT`
  and a row lock on `steps`.** Ratified as the non-preferred choice, and it
  needs no new role. Rejected because it widens the most deliberately narrow
  role in the system, which is the cost item 1 itself names; the new role is
  cheaper than widening `policy-writer`.
- **Keep `app_worker` as owner and accept the exposure**, recording it as a
  limit. Rejected by the owner: the exposure defeats the split's own purpose
  for the one role it distrusts, and recording a control that the distrusted
  party can switch off is not a control.
- **Own the fence as `ced_owner`.** Simplest, and safe against the worker.
  Rejected because it runs the fence at the schema owner's full authority,
  discarding the narrowing that made item 1's second option preferable to its
  first — it would answer this finding by giving up what the design wanted.

## References

- Narrowed design: [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
  § Changes this design asks of r7, item 1
- Invariant: [`runtime-architecture.md`](../architecture/inspectable-multi-agent-diligence/runtime-architecture.md)
  § Identity — two layers
- Implementing spec: [`walking-skeleton-foundation`](../specs/walking-skeleton-foundation/spec.md)
- Evidence: [`notes/verification-ledger.md`](../specs/walking-skeleton-foundation/notes/verification-ledger.md)
  § Review round 1
