# Erratum 2026-09-23 — AC-0233's retirement trigger names a task that no longer fires it

**Status:** recorded, not applied. The spec body is frozen and is not edited.

## What the frozen text says

`spec.md` § Acceptance Criteria, the AC-0233 obligation row:

> **Retirement trigger:** that spec's T2 removes this criterion's suite in the
> same task that installs the predicate

"That spec" is `walking-skeleton-authority-containment`, and the same row names
that spec's AC-0235 as the fall-through guard and its AC-0236 as the error-path
guard.

## Why it is now wrong

On 2026-09-23 the owner cut `walking-skeleton-authority-containment` in two.
The containment fragment stayed; the decision point moved to
[`walking-skeleton-policy-decision-point`](../../walking-skeleton-policy-decision-point/spec.md),
taking AC-0235 and AC-0236 with it.

Two clauses of the row are therefore stale:

- **The guards.** AC-0235 and AC-0236 are now
  `walking-skeleton-policy-decision-point`'s, not authority-containment's.
- **The retirement trigger.** Authority-containment's T2 is now a documentation
  task that removes no suite. The task that installs the predicate and removes
  this criterion's suite — `tests/compiler/test_whole_tool_surface_refuses.py`
  — is **`walking-skeleton-policy-decision-point`'s T1**, which carries that
  file in its `Touches` and the removal in its `Done when`.

Nothing about AC-0233's obligation changes. It still covers the interval in
which the decision point holds a position and no predicate, it is still retired
by the task that ends that interval, and the guards that replace it still exist
under the same identifiers. Only the spec names moved.

## The same cut left other references in this frozen spec

The AC-0233 row above is the one the retirement trigger turns on, and it is not
the only sentence the cut of 2026-09-23 invalidated. These are the rest, in the
same frozen body, each attributing a moved criterion or the decision point's
predicate to `walking-skeleton-authority-containment`:

| Where | What it says | What is now true |
| --- | --- | --- |
| `spec.md` § Agent Rules, *No decision point that admits by default* | "Until `walking-skeleton-authority-containment` supplies the predicate, every tool call is refused" | The fragment is that spec's; the predicate is installed by `walking-skeleton-policy-decision-point`, whose AC-0235 is the permanent guard |
| `spec.md` § Acceptance Criteria, the AC-0233 obligation row | "`walking-skeleton-authority-containment` ships its predicate" | Same split |
| `spec.md` § Acceptance Criteria, the AC-0234 obligation row | "`walking-skeleton-authority-containment`'s AC-0208" | AC-0208 moved to `walking-skeleton-policy-decision-point` |
| `plan.md` § Approach and § Tasks | AC-0235 and the decision point's predicate attributed to that spec | Both are `walking-skeleton-policy-decision-point`'s |

**None of them is edited, and the reason is the one this note already gives**:
the body is frozen, `docs/specs/README.md` forbids editing it, and a
`[backlog].open` entry on that path raises `duplicate_membership`. They are
listed here so the record is the same shape as the trigger's — a reader who
greps that spec and finds a stale name has one place that says which name is
right.

**This is what `walking-skeleton-policy-decision-point`'s T2 gate leaves
standing.** That gate reads `src/ tests/ docs/` and refuses a hit attributing a
moved criterion or the decision point to the containment spec. Every hit outside
this frozen spec was repaired in that task. The hits inside it cannot be, so the
exception is recorded here rather than in that spec's verification ledger —
which is the same routing the trigger above takes, and which keeps the gate's
residual in the file a reader of the *frozen* spec will find.

## Why this is an erratum and not an amendment

`spec.md` is `Shipped`. Its § Acceptance Criteria is amendment-governed, the
controlled-amendment transition is available only inside `CODE-IMPLEMENTATION`,
which this delivery has left, and `docs/specs/README.md` forbids editing a
frozen body. The two pointers a frozen `Status` line accepts are a supersession
naming an ADR and a closed-register-anchor pointer; this is neither — no
decision was reversed and no backlog anchor closed.

A `[backlog].open` entry was considered and rejected on a mechanical ground:
`docs/specs/walking-skeleton-role-compilation/spec.md` is in `[work].shipped`,
so a second membership on that path raises `duplicate_membership`.

The precise effect, measured rather than assumed: with such an entry present,
the reconciler reports `duplicate_membership` on that path and an added
`unsatisfied_dependency` on the decision point, step-lifecycle and evidence.
`walking-skeleton-authority-containment`, the next spec to dispatch, is
unaffected. So this does not block the whole initiative — it blocks the three
specs downstream of this one, which is still reason enough not to add the entry.

The entry this replaces was `ac-0261-names-a-type-nothing-appends`, **added** on
2026-09-22 and removed on 2026-09-23 in the same change as this note, because it
collided with moving this spec from `[work].queue` to `[work].shipped`. An
earlier draft of this note said that entry was removed on 2026-09-22; it was
not, and the removal is this change's own act rather than prior history.

The same pattern is live elsewhere and is not being treated as impossible:
`docs/specs/walking-skeleton-step-lifecycle/spec.md` currently holds both a
`[backlog].open` defect and a `[work].queue` entry, and the reconciler reports
`duplicate_membership` on it. That is pre-existing and left standing.

This note is therefore the record, and
`walking-skeleton-policy-decision-point`'s T2 owns creating it.

## If that spec is ever reopened

Correct the row to name `walking-skeleton-policy-decision-point` for both the
guards and the retirement trigger, and delete this note.
