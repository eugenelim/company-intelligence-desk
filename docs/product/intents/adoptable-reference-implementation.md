# Adoptable Reference Implementation

- **Status:** Draft
- **Kind:** outcome

## Outcome

An engineer who has never seen this repository can, from the repository alone,
identify the governed-agent patterns it demonstrates, find where each one is
implemented, and carry a pattern into their own system without copying this
project's domain.

The repository names a non-empty set of demonstrated patterns, each with a
findable implementation site, and at least one reader task.

**Three falsifying observations**, the first of which closes the empty state:

1. The repository names no pattern set, or no reader task. Claiming nothing is a
   failure, not a pass.
2. A named pattern has no findable implementation site — a reader is told it
   exists but cannot get from the claim to the code that embodies it.
3. A named reader task cannot be completed end to end from the repository alone.

Which patterns are named is open — that is this intent's first task — but the
form of the failing state does not depend on the choice.

**Legibility is a satisfaction condition, not a tradeable attribute.** A design
that is correct but unteachable does not satisfy the project's purpose.

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

- Documentation that describes intent rather than what actually shipped.

Becoming a framework, library, or extractable SDK, and genericizing the domain
to serve more use cases, are excluded by
[`docs/CHARTER.md`](../../CHARTER.md) § Scope and are not restated here.

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

**Next step.** This intent acts as a **review lens over the other five** rather
than having a design surface of its own, and that role continues into the two
commissioned companion documents.

Settled by an owner-authored pass that names the pattern set and at least one
reader task, and locates each. No architecture run produces that list; it is a
documentation obligation this intent owns.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r6 — positive minimum reworded so implementation sites attach to
  patterns rather than reader tasks, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
