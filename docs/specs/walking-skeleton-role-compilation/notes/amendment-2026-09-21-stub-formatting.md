# Amendment record — the AC-0202 stub's formatting, 2026-09-21

This note is the stable reference the `contract-amendment` transition cites for
its owner authority and its reason. It is a governance record, not an execution
observation; execution observations for this spec live in
[`verification-ledger.md`](verification-ledger.md).

## The defect

`ruff format --check .` is the first gate in
[`AGENTS.md`](../../../../AGENTS.md) § Build and test commands. It exits 1 on
one file and one block:

```
docs/specs/walking-skeleton-role-compilation/plan.md:250
```

That block is the validated red stub for AC-0202, in T2's `Tests` field. Ruff
0.16.8 formats Python inside Markdown fences, and the stub's inline `role={...}`
literal is not in the form ruff produces. The whole difference is whitespace:
the dict is spread over three lines and ruff writes one key per line.

## The evidence, checked rather than assumed

- `origin/main` is clean — 102 files, exit 0. This branch introduced the only
  failure the gate reports anywhere in the repository.
- The failure was present at HEAD before any implementation code, reproduced by
  running the gate against `git show HEAD:…/plan.md` in a scratch copy.
- **`docs/specs/walking-skeleton-step-lifecycle/plan.md` also carries a Python
  fence, and it passes.** So the gate covering fenced Python in `docs/` is the
  established repository behaviour and a sibling plan already complies. The
  defect is this plan's stub, not the gate's reach — which is why the repair is
  an amendment here rather than a change to `pyproject.toml`.

## Why it could not be repaired without this transition

`plan.md` is hash-pinned by the sealed baseline, and § Rule lookups in
`AGENTS.md` plus this run's own contract make any non-bookkeeping edit refuse
the next `CODE-*` transition. The two candidate repairs were both above an
implementer's authority: reformatting the block edits a pinned artifact, and
excluding `docs/` from the formatter edits the gate to pass it and touches a
manifest no task's `Touches` names.

The defect was surfaced to the owner rather than worked around, and recorded in
`workspace.toml [backlog].open` so it could not be lost while it waited.

## Authorization

The scope owner authorized the amendment on 2026-09-21, choosing to reformat the
stub over the two alternatives (leaving the gate red with the defect recorded,
or narrowing the formatter's reach). Owner: eugenelim.

**Widened on the same day, by the same owner.** T2 execution found that
AC-0204's stated observation point does not exist on the pinned framework
version, and the owner directed that the criterion be reworded inside this
amendment rather than carried as a Follow-on. That is a change to an
acceptance criterion, so this amendment is no longer whitespace-only.

**Widened a second time, by the review it triggered.** Rewording a guarding
control fired the security lens, which found that AC-0204's disable does not
reach the model on several paths and that an earlier deferral record stated a
framework fact that was false. Closing those sustained findings added a
`§ Follow-ons` bullet and its register entry, and moved two register
memberships. The scope below enumerates the whole footprint, because this note
is what the `contract-amendment` transition cites as `owner_authority_ref` and
what a reader uses at the human gate to confirm nothing crept in.

## Scope of the amendment

**Four kinds of change. The second is a criterion; the rest follow from it.**

*The stub*: one fenced block, whitespace only. Its imports, function name,
`compile_role` call arguments, chain walk and assertion are unchanged.

*AC-0204*: reworded to name the surface the pinned version actually exposes.
`Model.prepare_request` resolves the unified `thinking` setting into
`ModelRequestParameters.thinking` and strips the key from the settings the
model's `request` receives, so the criterion's original observation point did
not exist. The rewording is strictly not weaker — it keeps the compile-time
refusal of any other declared value, and keeps the clause that omitting the
key is insufficient, which survives because the resolved field's default is
`None` and the compiler must produce `False`. The always-thinking carve-out
the rewritten text names is recorded as a Follow-on with a register entry,
because refusing a role bound to such a profile is a new control rather than
a wording fix.

*`§ Follow-ons`*: one bullet added, deferring to
`walking-skeleton-step-lifecycle` the obligation that the `thinking` value the
model reads on the executor's run path is `False`. It is stated as that
property rather than as a list of mechanisms because three downstream drops
and one upstream override each defeat it, and a guard scoped to any one leaves
the rest open. An interim version of this amendment carried the defect as two
bullets and a misfiled third; those were merged and removed.

*`workspace.toml`*: against the baseline the delta carries two register
movements — the stub-formatting entry retired to `closed`, and the deferral
above opened. An interim override entry was opened and merged away inside this
amendment and so does not appear in the delta.

**One duplicate membership remains, and is accepted here rather than
elsewhere.** `docs/specs/walking-skeleton-step-lifecycle/plan.md` now carries
two `[backlog].open` memberships, so the workspace engine reports
`duplicate_membership` on both. The register's one-membership-per-path model
cannot avoid it: four deferred obligations route to a successor spec that owns
two artifacts, and removing the collision would mean collapsing unrelated
deferrals into one record. The amendment reduced the collision from three
memberships to two by merging its own two entries into one, and stops there.
No gate in `AGENTS.md` § Repository checks runs that engine. **This sentence is
where that acceptance is recorded** — the closed entry carries a different
question, namely that `backlog.closed` cannot mechanically represent a defect
whose artifact is a plan file, and it says nothing about duplicate
membership.

**No task's `Touches`, `Tests` obligation or `Done when` changes**, and no
criterion other than AC-0204 changes. T1 is complete and its section is
preserved untouched.

The amended text is exactly what `ruff format` produces, which is also
**byte-identical to the stub as materialized** in
`tests/compiler/test_stack_composition.py` during T2 layer (d). That file was
written from the pre-amendment plan text, byte identity verified, its red
observed as the plan records — `ModuleNotFoundError: No module named
'ced.agents.compiler'` at collection — and formatted only after it passed. So
the amendment moves the plan to agree with what shipped, and removes the
standing conflict between materializing the stub byte-identically and passing
the style gate.
