# ADR-0007: `.github/` is a non-application top-level directory

- **Status:** Accepted
- **Date:** 2026-09-23
- **Areas:** repository-layout
- **Reversibility:** high
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** ADR-0003 D2
- **Superseded by:** none
- **Superseded in part:** none

## Context

`.github/pull_request_template.md` entered history on 2026-09-22 in commit
`9e20d97`, an agent-pack upgrade. It is the pull-request body shape
[`AGENTS.md`](../../AGENTS.md) § Development workflow already requires, in the
one path GitHub reads it from.

[ADR-0003](0003-repository-layout.md) D2 makes a sixth top-level directory an
Ask-first boundary and says adding one means amending that record. Nothing
amended it, so `tests/architecture/test_recorded_layout.py::test_no_top_level_directory_is_unrecorded`
has been red since that commit — the only red in the suite across four
deliveries. The check is working exactly as ADR-0003 § Context designed it: a
structural change arrived, and the one mechanical gate standing in for the
waived RFC round noticed.

**The red is closed by recording the directory, not by widening the check.**
The alternative on offer was adding `.github` to the test's `PREDATING` set,
which is the set for entries that predate ADR-0003 and that its D2 leaves
ungoverned. `.github/` does not predate ADR-0003 — it postdates it by four
days — so putting it there would make the test's own comment false and turn
`PREDATING` into the pattern-match hole that comment refuses. Rejected by the
owner on 2026-09-23.

## Decision

- **D1:** The repository carries **non-application** top-level directories,
  recorded here and governed by this record rather than by ADR-0003 D1's
  five-directory table:

  | Directory | Holds | Why it is not application layout |
  | --- | --- | --- |
  | `.github/` | The pull-request template GitHub reads | Platform-mandated path for a convention `AGENTS.md` already states; ships no code, no schema and no test |

  The table is a narrowest set on the same grounds ADR-0003 D1 gives: a
  directory recorded and unused invites content the record never reasoned
  about.

- **D2:** Adding a non-application top-level directory amends **this** record,
  and stays an Ask-first boundary. ADR-0003 D2's amendment route is unchanged
  for a sixth *application* directory; what this record takes over is the
  narrower question of where a platform- or tooling-mandated path is written
  down. Splitting the two is what keeps ADR-0003 D1's table answering "what is
  the application made of" rather than accumulating whatever a hosting
  provider requires next.

- **D3:** The mechanical check reads both records. ADR-0003's table and this
  record's table are parsed out of the ADRs themselves and unioned with the
  test's `PREDATING` set. Restating either list inside the test would let the
  check verify the copy rather than the decision, which is the defect ADR-0003
  § Decision already names for its own table.

## Consequences

**Positive:**

- The suite is green, so the next red is a signal again rather than a known
  exception somebody has to remember is expected.
- A platform-mandated directory now has a place to be recorded that does not
  dilute ADR-0003 D1's answer to what the application is made of.

**Negative, and accepted:**

- **Two records now govern top-level layout**, so a reader asking "may I add a
  directory" has two places to look. Mitigated by D2 stating which question
  each record owns, and by the check reading both so neither can be forgotten
  silently.
- **This record was written after the directory landed**, not before. The
  Ask-first boundary was crossed by an agent-pack upgrade nobody reviewed as a
  structural change, and recording it now does not recover the review it
  should have had. What it recovers is the durable record, which is the half
  ADR-0003 § Context says the waiver never removed.

**Revisit if:** a non-application directory is proposed that ships code,
schema or tests, or the shaping-phase exception expires at Phase 2 and the RFC
route resumes.

## Confirmation

- **Mode:** test
- **Signal:** `tests/architecture/test_recorded_layout.py::test_no_top_level_directory_is_unrecorded`
  finds no tracked top-level directory that ADR-0003 D1, this record's D1, or
  the test's `PREDATING` set names. A new directory appearing without an
  amendment to one of the two records is the failure signal.
- **Owner:** eugenelim

## Alternatives considered

- **Add `.github` to the test's `PREDATING` set.** One line, no new record.
  Rejected on the ground § Context gives: the set means "predates ADR-0003 and
  D2 leaves ungoverned", and `.github/` predates nothing. The edit would have
  made the set's own comment false and left the next tooling directory with the
  same one-line precedent and no record.
- **Amend ADR-0003 D1's table in place.** Rejected because `docs/specs/README.md`
  and the ADR corpus both treat an accepted record's body as frozen, and
  because it would put a platform path in the table that answers what the
  application is made of.
- **Move the template out of `.github/`.** GitHub reads it from that path and
  no other, so the directory would come back the first time anyone wanted the
  template to work. Rejected as a fix that removes the record rather than the
  cause.
- **Delete the template.** It is the PR shape `AGENTS.md` already requires and
  the work-loop's finish checklist already fills. Rejected: the repository
  would lose a convention it states elsewhere to avoid writing down one
  directory.

## References

- Amended record: [ADR-0003](0003-repository-layout.md) D2
- Waived requirement: [`AGENTS.md`](../../AGENTS.md) § Development workflow
- Mechanical check: `tests/architecture/test_recorded_layout.py`
