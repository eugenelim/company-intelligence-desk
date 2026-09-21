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

## Scope of the amendment

**One block, whitespace only.** The stub's imports, its function name, its
`compile_role` call arguments, its chain walk and its assertion are unchanged.
No acceptance criterion changes. No task's `Touches`, `Tests` obligation or
`Done when` changes. T1 is complete and its section is preserved untouched.

The amended text is exactly what `ruff format` produces, which is also
**byte-identical to the stub as materialized** in
`tests/compiler/test_stack_composition.py` during T2 layer (d). That file was
written from the pre-amendment plan text, byte identity verified, its red
observed as the plan records — `ModuleNotFoundError: No module named
'ced.agents.compiler'` at collection — and formatted only after it passed. So
the amendment moves the plan to agree with what shipped, and removes the
standing conflict between materializing the stub byte-identically and passing
the style gate.
