# Adoptable Reference Implementation

- **Status:** Draft
- **Kind:** outcome

## Outcome

An engineer who has never seen this repository can, from the repository alone,
identify the governed-agent patterns it demonstrates, find where each one is
implemented, and carry a pattern into their own system without copying this
project's domain.

**Falsifying observation:** the repository demonstrates a pattern with no
findable implementation site — a reader can be told the pattern exists but
cannot get from the claim to the code that embodies it. A second: a named reader
task the repository claims to support cannot be completed end to end from the
repository alone.

The pattern list itself is open — naming it is this intent's first task — but
the *form* of the failing state does not depend on which patterns are chosen.

**Legibility is a satisfaction condition, not a tradeable attribute.** A design
that is correct but unteachable does not satisfy the project's purpose. The
owner ruled on this on 2026-09-10, and `design-doc.md` was corrected to match:
an earlier revision ranked legibility fifth among quality attributes and called
it tradeable.

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

**Next step.** `architect-design` has run. Its result is not a design surface
for this intent — as intended, this intent acts as a **review lens over the
other five**, and that role continues through owner sign-off and into the two
commissioned companion documents. What remains genuinely open here is naming the
patterns, which no architecture run settles.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r4 — outcome given a falsifying observation; legibility stated as a
  satisfaction condition per owner ruling, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
