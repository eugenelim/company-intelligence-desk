# ADR-0003: Five top-level directories for the application

- **Status:** Accepted
- **Date:** 2026-09-18
- **Areas:** repository-layout, build
- **Reversibility:** high
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** none
- **Superseded by:** none
- **Superseded in part:** none

## Context

This repository has held documentation and throwaway spikes and no application
code. The walking skeleton is the first code that ships, so it needs a home,
and [`AGENTS.md`](../../AGENTS.md) § Development workflow says to *"propose a
new top-level directory through an RFC rather than creating one"*.

**The owner waived that requirement for this delivery on 2026-09-18**, under the
same shaping-phase exception used for the charter amendment recorded in
[`CHARTER.md`](../CHARTER.md) § Amendments. The waiver removes the *proposal
process*, not the *durable record* — a directory nobody wrote down is still an
unreviewed structural change — so the layout is recorded here as a decision
instead of proposed as one.

That trade has a named cost. The RFC route would have given the layout an
acceptance round; nothing now stands between a wrong directory set and the code
that inherits it except this record and one mechanical check. The check is
therefore written as a test rather than as a note: the foundation spec's T2
asserts that no top-level directory exists which this record does not name.

## Decision

- **D1:** The application occupies exactly five top-level directories:

  | Directory | Holds | First written by |
  | --- | --- | --- |
  | `src/` | The one Python package, in five layers — `domain/`, `agents/`, `adapters/`, `api/`, `worker/` | foundation T2 |
  | `tests/` | Every test, grouped by the claim it verifies, not by the module it imports | foundation T2 |
  | `migrations/` | Alembic revisions, expand-only | foundation T3 |
  | `contracts/` | Published interface contracts, starting with `openapi/runs.yaml` | foundation T6 |
  | `deploy/` | Local Docker Compose substrate — Postgres and MinIO | foundation T3 |

  This is the narrowest set the foundation spec's tasks T2–T7 actually need. A
  directory recorded and unused is worse than one added later, because it
  invites content the record never reasoned about.

- **D2:** A sixth top-level directory is an **Ask-first** boundary, and adding
  one means amending this record — a superseding ADR, or an RFC once the
  shaping-phase exception expires at Phase 2. The existing top-level entries
  this record does not govern (`docs/`, `spikes/`, `tools/`, `governance/`, and
  the agent-tooling directories) predate it and are unaffected.

- **D3:** `src/` holds **one** package with five layers, not five packages. Two
  deployables — the API and the worker — are built from one image and differ
  only in their entry point, which is what
  [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
  § How workers are provisioned specifies. Splitting the layers into
  distributions would make the dependency-direction gate a packaging
  constraint enforced at install time, when what is wanted is a test that can
  be shown failing on a deliberately misplaced import.

- **D4:** `tests/` is grouped by claim — `architecture/`, `event_log/`,
  `api/`, `fault_injection/` — rather than mirroring `src/`. The foundation
  spec's acceptance criteria are the index into this tree, and a criterion that
  spans three modules has one obvious home under this grouping and no home
  under a mirror.

## Consequences

**Positive:**

- The layout has a durable record and a mechanical check, which is more than
  the RFC route would have left behind once its acceptance round closed.
- Five named directories make the dependency-direction gate expressible as a
  path rule, which is what lets it be tested rather than reviewed.

**Negative, and accepted:**

- **The waiver removed a review this layout would otherwise have had.** The
  layout is the one decision every later task inherits, and it was not
  independently accepted. Mitigated by recording the narrowest set the plan
  uses and by making the directory check a test.
- **`migrations/` at the top level rather than inside `src/`** follows
  Alembic's own convention, which expects `alembic.ini` beside the revision
  directory. It costs one top-level entry to avoid fighting the tool.

**Revisit if:** a sixth top-level directory is needed, or the two deployables
stop being one image with two entry points, or the claim-grouped test tree
starts leaving a criterion without an obvious home.

## Confirmation

- **Mode:** test
- **Signal:** the foundation spec's T2 directory check finds no top-level
  directory that D1 or D2 does not name. A new directory appearing without an
  amendment here is the failure signal.
- **Owner:** eugenelim

## Alternatives considered

- **A single `app/` directory holding source, tests and migrations.** One
  top-level entry instead of five. Rejected because Alembic and the test runner
  both expect their own roots, and because the dependency-direction rule is
  stated over paths — collapsing the layers into one subtree makes the rule
  harder to express and harder to show failing.
- **Mirror `src/` in `tests/`.** The conventional choice, and cheap. Rejected
  by D4's reasoning: acceptance criteria, not modules, are how this suite is
  navigated, and AC-0010 alone spans the pool, the schema and Compose.
- **Wait for the RFC.** The process the waiver removed. Rejected by the owner's
  decision of 2026-09-18, on the ground that the shaping phase already carries
  this exception and the layout blocks every subsequent task.
- **Five distributions under `src/`, one per layer.** Would make the
  dependency direction a packaging fact. Rejected by D3 — it converts a gate
  that can be shown failing into an install-time constraint, and the spec's
  Never-do is specifically about a gate that is never shown failing.

## References

- Waived requirement: [`AGENTS.md`](../../AGENTS.md) § Development workflow
- Exception precedent: [`CHARTER.md`](../CHARTER.md) § Amendments
- Layer rationale: [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
  § How workers are provisioned, § Three layers, and a hard line between the middle two
- Consuming spec: [`walking-skeleton-foundation`](../specs/walking-skeleton-foundation/spec.md)
