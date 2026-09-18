# ADR-0005: The append fence proves lease possession, not epoch knowledge

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

`runtime-architecture.md` r7 § Event log specifies the worker append path's
fence as:

```
SELECT 1 FROM steps WHERE step_id = $1 AND lease_epoch = $2 FOR UPDATE;
-- zero rows ⇒ fenced ⇒ ROLLBACK, abort with no ADDITIONAL side effects
```

Epoch only. The same document's § Step execution fences lease *renewal* on
epoch **and** `owner`. `walking-skeleton-foundation` implemented r7 literally,
and review round 3 established what that costs.

**The epoch is not a secret, and an unclaimed step has one anyway.**
`steps.lease_epoch` is `NOT NULL DEFAULT 0`, so a step no worker has ever
leased is fenced at `0`. Reproduced against the running substrate as
`app_policy` — the narrowest role in the system, whose only capability is one
`EXECUTE` grant:

```
append_policy_decision(run, unleased_step, 0, 'attacker-chosen-principal', 'forged-role')
  → seq 1, written
```

A forged authorization-audit record, with a caller-chosen principal and agent
role, on the one write path the r7 identity split exists to isolate. The
round-2 run/step coherence check does not help: the never-claimed step belongs
to the run, so the check passes.

Two separate facts made it reachable, and they need different remedies.
`app_policy` held `SELECT` on `runs`, `steps` and `events`, which let it *read*
a live step's epoch — and those grants exceeded r7's Layer-1 identity table,
which gives `policy-writer` "`runs.next_seq` bump + insert `policy.decision`
events **only**" with no read column at all. Removing them is an alignment, not
a decision. But it does not close the path, because epoch `0` on an unclaimed
step needs no read.

## Decision

- **D1:** `fence_step`'s predicate additionally requires `owner IS NOT NULL`
  and `lease_expires_at > now()`. The fence therefore proves that the named
  step **holds a live lease**, not merely that the caller restated its current
  epoch. A never-claimed step has `owner IS NULL` and is unappendable; a
  released step has `lease_expires_at IS NULL`; a drained one has it set to
  `now()`. None satisfies the predicate.
- **D2:** This **goes beyond r7 § Event log's stated fence for the append
  path**, and is taken on the owner's decision of 2026-09-18 rather than read
  out of r7. The ground is that r7 § Step execution already fences renewal on
  epoch and owner, so what D1 closes is an asymmetry internal to r7; and that
  r7 § Identity's own invariant — the split "defends against a bug or partial
  compromise in any single write path forging a decision" — is not delivered by
  a predicate over a value the forging party can read or guess.
- **D3:** The fence is **not** bound to the calling identity. Requiring
  `owner = <caller>` would disable the policy path outright: `app_policy` holds
  no `UPDATE ON steps`, and `claim_one` writes only the *worker's* id into
  `steps.owner`, so the policy role can never be a step's owner. Adjudication
  ruled that half of the proposed remedy over-broad, and it is not taken.
- **D4:** `app_policy` holds **no `SELECT` on any table**. Its sole capability
  is `EXECUTE` on `append_policy_decision`. This restores r7's Layer-1 table
  and r4 item 1's stated aim that "`policy-writer` gains no table access at
  all".

## Evidence

Probed against the running local substrate, 2026-09-18, every mutating
statement rolled back. As `app_policy`:

| Call | Before D1/D4 | After |
| --- | --- | --- |
| never-claimed step, epoch 0 | accepted, seq 1 | `serialization_failure` |
| live lease, correct epoch | accepted | accepted |
| live lease, wrong epoch | refused | refused |
| expired lease, correct epoch | accepted | `serialization_failure` |
| `SELECT` on `steps` / `runs` / `events` | allowed | refused |

**What this evidence does not cover.** A step that genuinely holds a live lease
at a low, guessable epoch is still appendable by any caller that can name its
`step_id`. `app_policy` can no longer enumerate step ids, so reaching that
state requires being handed the pair — which is the legitimate call path. That
residual is not closable without changing r7's policy-role identity, and it is
the same defence-in-depth class as the `app_worker` instance recorded in the
verification ledger.

## Consequences

**Positive:**

- The fence delivers the property r7 § Identity claims for the split, rather
  than a weaker property that happens to be written down.
- Two adjacent states — released and drained — become unappendable for free,
  which the epoch-only predicate admitted.

**Negative, and accepted:**

- **A worker whose lease expired mid-step can no longer append.** That is
  correct behaviour and it is also a behaviour change: before D1, a worker
  holding the right epoch on an expired lease could still write. Any caller
  now discovers lease loss at its next append rather than at its next renewal.
- **r7's § Event log text is now wrong for this path**, and this record is the
  only place that says so until the outstanding r8 consistency pass folds it in
  — the same standing cost ADR-0004 carries.

**Revisit if:** the r8 pass restates the append fence, or a legitimate caller
is found that must append without holding a live lease, or `policy-writer`
acquires an identity that can own a step.

## Confirmation

- **Mode:** test
- **Signal:** the suite refuses an append against a never-claimed step, an
  expired lease and a released step, and admits one against a live lease.
  `app_policy` is refused `SELECT` on every table. Any of those inverting is
  the failure signal.
- **Owner:** eugenelim

## Alternatives considered

- **Revoke `app_policy`'s reads and stop there.** In-authority, and the
  alignment is required either way. Rejected as insufficient: adjudication
  established that epoch `0` on a never-claimed step needs no read, so the
  reproduced forgery survives it.
- **Bind the fence to the calling identity.** The reviewer's proposal, and the
  strongest property available. Rejected under D3 — it cannot be satisfied by
  the policy path at all, so it would close the forgery by removing the
  feature.
- **A composite `events (run_id, step_id)` foreign key to `steps`.** Would make
  run/step coherence structural rather than procedural. Rejected as orthogonal:
  it constrains which run an event names, not whether a lease is held, so it
  does not reach this finding. Recorded in the ledger as a residual instead.
- **Leave it and record the exposure.** Rejected by the owner: a control the
  distrusted party can satisfy by guessing a default is not a control, and the
  sibling spec's policy decision point is about to be built on it.

## References

- Narrowed design: [`runtime-architecture.md`](../architecture/inspectable-multi-agent-diligence/runtime-architecture.md)
  § Event log and stream mechanism (the fence), § Step execution (renewal),
  § Identity — two layers (the invariant and the Layer-1 grant table)
- Related narrowing: [ADR-0004](0004-fence-function-owner.md)
- r4 item 1: [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
  § Changes this design asks of r7
- Implementing spec: [`walking-skeleton-foundation`](../specs/walking-skeleton-foundation/spec.md)
- Evidence: [`notes/verification-ledger.md`](../specs/walking-skeleton-foundation/notes/verification-ledger.md)
  § Review round 3
