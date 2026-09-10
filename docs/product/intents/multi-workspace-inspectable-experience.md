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
- Which views are MVP views and which are later extensions?
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

**Feeds:** nothing downstream.

This intent is the most downstream of the six — its presentation contracts
cannot be settled before the four it depends on.

Use `architect-design` to define the UI/API boundary, workspace shell,
presentation contracts, state ownership, and Storybook's role in testing and
documentation.

Inception context, not a decision: the workspace views anticipated during
inception were Overview, Research, Workflow, Evidence, Context, Compare,
Evaluations, Policy, and Settings. `architect-design` must pressure-test
whether each is a view, a panel within a view, or unnecessary — the list is a
starting point for the information-architecture question above, not an answer
to it.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r3 — post-shaping-review revision, 2026-09-09
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
