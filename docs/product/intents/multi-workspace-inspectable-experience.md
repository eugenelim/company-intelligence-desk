# Multi-Workspace Inspectable Experience

- **Status:** Draft
- **Kind:** outcome

## Outcome

A user can, without reading server logs or raw model output, answer for any
completed run: which evidence supports a given claim, which policy decisions
were applied, what the workflow did and in what order, and where the run
required a human.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md).

### Confirmed constraints

- The UI is implemented with React.
- A shared React component system is developed and documented through
  Storybook.
- The UI supports multiple workspace views rather than being only a chat
  interface.

The separation of the browser UI and the API into distinct deployable
containers is a ratified constraint owned by
[`portable-identity-first-runtime.md`](portable-identity-first-runtime.md);
this intent is bound by it and does not restate it.

### In scope

- Rendering of typed domain artifacts.
- Presentation of progressive workflow updates during a run.

This intent owns **what the user sees**. It does not own what may leave the
backend (see [`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md))
or how run events are carried and survive restart (see
[`portable-identity-first-runtime.md`](portable-identity-first-runtime.md)).

### Excluded

- Arbitrary agent-generated HTML or executable UI code rendered in the browser.
- Exposure of private model reasoning.
- A separate frontend deployment or microfrontend for every workspace view.

## Owner

eugenelim — decides experience scope and the presentation contract.

## Unresolved questions

- What is the primary workspace information architecture, and which views exist
  at all?
- What is the smallest set of views that makes a run inspectable at all? The
  MVP-versus-later split is a slicing decision owned by
  [`inspectable-diligence-mvp`](../briefs/inspectable-diligence-mvp.md) and taken
  at `author-delivery-brief continue`, not here.
- How do analyst, builder, and operator role presets differ?
- How are evidence, context, and policy decisions represented visually?
- What accessibility, responsive, and browser-support requirements apply?
- Which Storybook scenarios become executable acceptance fixtures?
- What is the presentation contract between the API and each workspace view?

## Projection

**Depends on:** `scoped-context-and-evidence` (what context and evidence *are*,
before they can be presented), `governed-observable-and-evaluable-operation`
(which run information is releasable), `portable-identity-first-runtime`
(event transport), `evidence-backed-company-diligence` (the domain artifacts
being presented).

**Feeds:** `adoptable-reference-implementation` by construction (README § 3);
no other outgoing edge.

This intent is the most downstream of the six — its presentation contracts
cannot be settled before the four it depends on.

**Next step.** `architect-design` has run and **deferred this intent's surface
entirely**: `design-doc.md` r6 § Scope hands the UI/API presentation contract,
workspace information architecture, Storybook's role, and the approval UI to a
commissioned *Experience and presentation* companion document, naming the seams
it must respect — the event log as observability substrate, the run state
machine as intervention carrier, typed artifacts as the presentation contract.
That companion does not yet exist and is what settles this intent.

Inception context, not a decision: the workspace views anticipated during
inception were Overview, Research, Workflow, Evidence, Context, Compare,
Evaluations, Policy, and Settings. `architect-design` must pressure-test
whether each is a view, a panel within a view, or unnecessary — the list is a
starting point for the information-architecture question above, not an answer
to it.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r4 — Feeds corrected against the authoritative edge set; slicing
  question routed to the delivery brief, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
