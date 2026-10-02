---
type: creative-direction
slug: walking-skeleton-evidence
surface: responsive-web
date: 2026-09-29
status: selected
---

# Aesthetic direction: Walking skeleton evidence

## Audience and job

**Primary:** An engineer evaluating whether the reference implementation is
inspectable and safe to own.

**Job:** When a governed run is in progress, I want to follow its committed
events and connection state so that I can tell what happened without trusting
an opaque activity animation.

**Secondary:** A senior engineering lead scanning for operational risk. The
surface favors the primary reader's event-level detail; the run header and
state labels preserve the secondary reader's fast risk signal.

## Named goals (ranked)

1. Inspectable momentum
2. Dense calm
3. Trustworthy restraint

## What each goal means

- **Inspectable momentum** — means: sequence, connection state, and terminal
  state make progress legible as committed facts. Violated by: animation or
  optimistic status that implies work the event log has not committed.
  - *Persona:* The engineer validating the reference implementation.
  - *Precedent:* Raycast's compact command feedback, taking its immediate state
    legibility and leaving its launcher interactions; analytical-workspace
    precedents, taking status clarity and leaving multi-pane complexity.
  - *Standards:* Nielsen heuristic 1, Visibility of System Status.
  - *Platform conventions:* Responsive-web status changes remain semantic,
    keyboard-stable, and independent of viewport width.
- **Dense calm** — means: a long event history stays scannable without making
  the surface feel crowded or noisy. Violated by: oversized cards, decorative
  whitespace, or equal emphasis on every metadata field.
  - *Persona:* The engineer reading events sequentially during a live run.
  - *Precedent:* Raycast's compact rows, taking density and hierarchy while
    leaving command-palette chrome; technical logs, taking monotonic sequence
    and leaving terminal-like visual noise.
  - *Standards:* Bringhurst's line-length discipline and progressive
    disclosure.
  - *Platform conventions:* One responsive column reflows before it introduces
    horizontal page scrolling.
- **Trustworthy restraint** — means: the surface shows only recorded facts and
  keeps untrusted values visibly inert. Violated by: model-authored links,
  markup, decorative gradients, or motion with no state meaning.
  - *Persona:* The evaluator looking for boundary failures rather than polish.
  - *Precedent:* Raycast's restrained accents, taking focus and leaving branded
    flourish; MDN reference pages, taking literal technical presentation and
    leaving documentation navigation.
  - *Standards:* WCAG 2.2, Nielsen heuristic 8, and the repository's
    plain-text rendering boundary.
  - *Platform conventions:* Native semantics, visible focus, non-color labels,
    and reduced-motion behavior take priority over a distinctive effect.

## Direction sheet

| Axis | This direction commits to |
| --- | --- |
| Grid grammar | `[hierarchical]` `[rigid]` — one content column with a stable run header and ordered event spine |
| Alignment and equilibrium | `[edge]` `[asymmetric]` — metadata aligns to a common leading edge; content weight follows the event sequence |
| Spatial density | `[dense]` — multiple event rows remain visible without hiding their type or sequence |
| Whitespace distribution | `[compact]` — small internal gaps, with stronger separation only between header, status, and history |
| Hierarchy and scale contrast | `[moderate]` — state and event type lead; envelope detail recedes without becoming illegible |
| Containment and boundary strength | `[ruled]` — rows use shared dividers and grouping rather than isolated cards |
| Section and scroll rhythm | `[continuous]` `[regular]` — one chronological stream with a repeatable row cadence |
| Type voice | `[mixed]` — clear sans text with monospace reserved for ids, sequence values, and event types |
| Type hierarchy | `[moderate]` — a small set of levels distinguishes page, state, event, and metadata |
| Chromatic intensity | `[restrained]` — neutral surfaces with accent reserved for focus and state, never as the only signal |
| Form | `[softened]` — restrained corner treatment on controls and status surfaces; rows stay rectilinear |
| Material and depth | `[layered]` — the run header sits above the event plane without deep elevation effects |
| Ornament and texture | `[none]` — no decorative texture, gradient, or illustration competes with evidence |
| Image treatment | `[none]` — the surface is evidence and text, not imagery |
| Motion character | `[productive]` — only state transitions may move, and reduced motion replaces them with immediate updates |

## Signature device

**Signature device:** A visible sequence spine pairs each committed sequence
number with its event type, so progress reads as an inspectable ledger rather
than a generic activity feed.

## Counterfactual check

**Comparator brief:** A consumer social-product activity feed.

| Axis or goal | What the comparator produced | What it became | Why |
| --- | --- | --- | --- |
| Containment | Independent, expressive cards | Shared ruled rows | The source is one ordered log, not unrelated posts |
| Density | Comfortable browsing density | Dense scanning density | The primary job is comparison across adjacent events |
| Motion | Expressive entry animation | Productive state-only motion | Motion cannot outrank committed evidence |
| Signature | Avatar and content preview | Sequence spine | Identity and order matter more than personality |

## Dominant goal for arbitration

**Dominant goal:** Inspectable momentum

Resolved trade-offs:

- When **inspectable momentum** and **dense calm** conflict on hidden detail,
  **inspectable momentum** wins — the evidence required to explain state must
  remain visible.
- When **dense calm** and **trustworthy restraint** conflict on compact link-like
  metadata, **trustworthy restraint** wins — external strings remain inert even
  if a link would save space.

## Open questions

- Automated checks establish the accessibility floor named in the spec; the
  evidence manifest must record any part of WCAG 2.2 that remains manual.
- The primary persona is an inline engineering-evaluator sketch, not a full
  research-backed persona.

## Borrowed discipline

**Donor candidate:** Generic operations console

**Discipline taken:** Keep connection state persistently visible while the
event history scrolls; leave the console's multi-pane density and alarm-heavy
chrome.

## Compositional commitments

The page is one responsive column. A compact run header establishes identity
and terminal state, a persistent text status names the connection condition,
and the event history follows as one uninterrupted ordered list. Each row puts
sequence and event type first, then wraps secondary envelope fields beneath
them at narrow widths. The retry control appears beside the status that needs
it; it does not displace the history or move keyboard focus.
