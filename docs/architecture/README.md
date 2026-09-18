# Architecture

How the code is *currently* organized. Not why (that's in
[`../adr/`](../adr/)) and not what we want (that's in
[`../rfc/`](../rfc/)) — **what is**.

- [`overview.md`](overview.md) — the map of the repository. What lives where,
  and how the parts relate. Read this first.
- `<subsystem>.md` — one file per non-trivial subsystem (add as the repo
  grows). Each describes the structure, the entry points, and links to the
  ADRs that explain why.

Decision records accumulate, and reconstructing current state from them means
reading every one in order. This directory is the rolled-up snapshot instead —
the answer to "what does this codebase look like today" without replaying ADR
history. Lifecycle: living. Update whenever the layout or major dependencies
change.

## Two documents, two jobs

`overview.md` is **descriptive** — the map, read to find things.
`reference.md` is **normative** — the golden path (stack, building blocks,
component stereotypes, cross-cutting standards) that new work conforms to, and
the target a feature's low-level design steers by. A thin repository has only
the map; the golden path appears once there are real architecture decisions to
hold work to.

Getting these the wrong way round is the common mistake: a map written as a
standard goes stale the moment the code moves, and a standard written as a map
never gets enforced.

## Designed but unbuilt

This directory holds current state. A designed-but-unbuilt subtree is admitted
only when its index carries a `STATUS: PLANNED` marker and links to the
decision governing it. [`inspectable-multi-agent-diligence/`](inspectable-multi-agent-diligence/)
is admitted under that rule.

## Verification markers

When a page carries a `Last verified against commit` marker, it records a
deliberate whole-page re-verification against that commit, not merely an edit.
Update it only after re-reading the whole page against the tree at that commit.
An unchanged marker means the page has not had that audit; it is provenance,
not a freshness requirement.
