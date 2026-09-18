# Architecture

How the code is *currently* organized. Not why (that's in
[`../adr/`](../adr/)) and not what we want (that's in
[`../rfc/`](../rfc/)) — **what is**.

- [`overview.md`](overview.md) — the map of the repository. What lives where,
  and how the parts relate. Read this first. **Still the unfilled seed
  template**, which is a defect in this directory rather than a statement about
  the code; § What is built below is the current map until it is filled.
- `<subsystem>.md` — one file per non-trivial subsystem (add as the repo
  grows). Each describes the structure, the entry points, and links to the
  ADRs that explain why.

## What is built

The first application code landed with
[`walking-skeleton-foundation`](../specs/walking-skeleton-foundation/spec.md).
The layout is [ADR-0003](../adr/0003-repository-layout.md); the framework
decision is [ADR-0001](../adr/0001-pydantic-ai-as-the-agent-framework.md) and
its version pin is [ADR-0002](../adr/0002-pydantic-ai-version-pin.md).

One package, `src/ced`, in five layers, built into one image with two entry
points — `ced-api` and `ced-worker`.

| Subsystem | Where | What it is | Governing design |
| --- | --- | --- | --- |
| Event log and its two append paths | `src/ced/domain/events.py`, `src/ced/adapters/postgres/event_log.py`, `migrations/versions/0002_*` | Per-run `seq` allocated by a row UPDATE inside the append transaction, never a `bigserial`. A fenced worker path and an unfenced run-lifecycle path, `steps` locked before `runs` on both | r7 § Event log and stream mechanism |
| The privilege split | `migrations/versions/0002_*` | No application role holds `INSERT` on `events`. Three `SECURITY DEFINER` functions with disjoint `EXECUTE` grants, each schema-qualified and naming `pg_temp`; a fourth, `fence_step`, owned by the `NOLOGIN` `ced_fence` so the role the split distrusts cannot drop the control that constrains it; and every fenced append checks the step belongs to the run | r7 § Identity — two layers; `worker-runtime.md` change 1 as narrowed by [ADR-0004](../adr/0004-fence-function-owner.md) |
| The HTTP surface | `src/ced/api/` | `POST /runs`, `GET /runs/{id}/snapshot`, `GET /runs/{id}/events`. Holds no model authority and reaches the log only through the two run-lifecycle types | r7 § Event log; `contracts/openapi/runs.yaml` |
| The worker pool | `src/ced/worker/pool.py` | Claim under a lease with `SKIP LOCKED`, execute outside any transaction, heartbeat-renew fenced on epoch and owner. TTL 60 s, heartbeat 20 s, poll 30 s | r7 § Step execution; `worker-runtime.md` § The pool |
| The dependency-direction gate | `tests/architecture/dependency_direction.py` | An AST walk refusing `pydantic_ai` outside `agents/` and `adapters/`, and the AWS SDK outside `adapters/` | The spec's Never-do |
| The local substrate | `deploy/` | Postgres 17 with `deadlock_timeout` at 200 ms, MinIO, and two worker containers | `worker-runtime.md` § How workers are provisioned |

**What is designed and not built.** The agent layer (`src/ced/agents/` is
empty), the authorization and quarantine boundaries, the provider call, the run
state machine's transitions, the browser stream, and the Phase 1 measurements.
Those belong to `walking-skeleton-agent-runtime` and
`walking-skeleton-evidence`. The two design subtrees keep their
`STATUS: PLANNED` markers because what they specify is still mostly unbuilt;
[`spikes/README.md`](../../spikes/README.md) § Phase 1 records exactly which of
their claims now have evidence and which do not.

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
