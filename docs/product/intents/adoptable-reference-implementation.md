# Adoptable Reference Implementation

- **Status:** Draft
- **Kind:** outcome

## Outcome

An engineer who has never seen this repository can, from the repository alone,
identify the governed-agent patterns it demonstrates, find where each one is
implemented, and carry a pattern into their own system without copying this
project's domain.

The project is meant to be two things at once: a useful demonstration
application, and a reference for teams building other governed agentic systems.
The failing state this guards against is a working application that nobody can
learn from — patterns legible only to the people who wrote it.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md).

### Confirmed constraints

- The project remains an open-source reference implementation with portable
  application-owned contracts.

### In scope

- The pedagogical shape of the repository: what a reader is meant to learn, in
  what order, and from which artifacts.
- Naming the demonstrated patterns explicitly, so a reader can find them rather
  than infer them.
- The separation between reusable pattern and domain-specific demonstration, so
  a reader can tell which is which.
- Whether the local-development path is sufficient for a reader to learn from.
  The path itself is owned by
  [`portable-identity-first-runtime.md`](portable-identity-first-runtime.md).

### Excluded

- Turning the project into a framework, library, or extractable SDK. It
  demonstrates patterns; it does not package them for import.
- Genericizing the domain to serve more use cases. The diligence domain is the
  demonstration, and its specificity is what makes the patterns legible.
- Documentation that describes intent rather than what actually shipped.

## Owner

eugenelim — decides what "reference implementation" obligates.

## Unresolved questions

- Which patterns is this project actually a reference *for*? Naming them is the
  first task; the list determines everything else in this intent.
- What must a reader be able to do after reading, and how would we know they
  can?
- Which artifacts carry the teaching load — README, guides, architecture
  documents, annotated code, or the worked example itself?
- What licence applies, and what contribution surface is offered?
- What output makes the reference persuasive while remaining bounded in effort?
- Does a reader need to run the system to learn from it, or should the recorded
  artifacts of a run be sufficient?
- How is documentation kept honest as the implementation changes?

## Projection

**Depends on:** all five other foundation intents. What is worth teaching
cannot be named before the architecture that would be taught exists.

**Feeds:** nothing. This intent is the reader-facing consequence of the other
five, and its obligations are discharged by them collectively.

This intent's role in the architecture run is a constraint on the others: a
design that is correct but unteachable does not satisfy the project's stated
purpose. Carry it as a review lens over the other five rather than as a separate
design surface.

Use `architect-design` to establish which architectural decisions are
load-bearing for the reference claim, and where the boundary between reusable
pattern and domain demonstration falls.

## Source

- Mode: chat-direct
- Locator: none — derived in-session from the inception mission statement and
  from an independent shaping review that found no intent owned this outcome
- Revision: r3 — post-shaping-review revision, 2026-09-09
- Authority: user-authorized; the sixth intent was explicitly approved in-session
  after the shaping review surfaced the gap
