# Verification ledger — walking-skeleton-foundation

Execution observations for an approved spec and plan, per the plan contract.
The spec and plan are pinned; nothing here amends either. Every entry records
what a check established **and what it did not**.

## Resolve-vs-surface disposition record

Opened at PLAN, closed at DECIDE. One row per item a referent could resolve or
had to surface.

| # | Item | Disposition | Basis |
| --- | --- | --- | --- |
| 1 | `migrations/` is a top-level directory that T1's `Approach` omits while T3's pinned `Touches` requires it | **Resolved** | `Touches` is plan contract, `Approach` is working material by the plan's own contract note. ADR-0003 names five directories; the `Approach` line is corrected in place. No amendment. |
| 2 | Pre-EXECUTE spec/plan review gate (`SPEC-PLAN-REVIEW`) on a structural change | **Resolved from recorded state** | Both human gates are already taken and dated in the plan Changelog, and `spec.md` § Assumptions records the independent scrutiny these artifacts received: a two-round shaping review and an adversarial spec-mode review, by forked-context reviewer agents. Re-dispatching a spec/plan reviewer could only produce findings against a pinned, Approved contract the owner directed not to re-open. Implementation-stage reviewers are **not** covered by this and run in full against every diff. |
| 3 | `docker compose` (CLI plugin) is absent in this environment | **Resolved** | `docker-compose` 5.5.0 standalone is present and the Docker daemon is Colima 29.2.1. `AGENTS.md` records the command that actually works, per its own rule that commands are verified from the manifest or runner that owns them rather than guessed. |

## Observations

Appended per task as evidence lands.
