# Multi-Workspace Inspectable Experience

- **Status:** Draft
- **Kind:** outcome

## Outcome

For any completed run, a user can reach from a rendered surface — without
reading server logs or raw model output — the **per-run** properties
[`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md)
§ Outcome makes auditable (its sub-results 1, 2 and 4: the sequence of steps,
the policy decisions and their outcomes, and where a human intervened), together
with the artifact classes
[`scoped-context-and-evidence.md`](scoped-context-and-evidence.md) makes
versioned and inspectable, and the evidence, temporal scope, and calculation
lineage its Outcome requires a material output to resolve to.

*Falsifying observation:* one of those properties, artifact classes, or
resolution targets that no rendered surface exposes for a completed run.

**Cross-release quality comparison — `governed` sub-result 3 — is deliberately
outside this outcome.** It is not a per-run property, and which views exist at
all is deferred to the delivery brief. Whether a surface for it exists remains
open under the information-architecture question below; this outcome does not
decide it, and does not leave that governed sub-result permanently unrendered. This intent does not define what is auditable; it owns whether the
per-run set is *reachable*.

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

**Feeds:** nothing beyond the by-construction edge recorded in README § 3.

This intent is the most downstream of the six — its presentation contracts
cannot be settled before the four it depends on.

**Next step.** `architect-design` has run and **deferred this intent's surface
entirely**: `design-doc.md` § Scope hands the UI/API presentation contract,
workspace information architecture, Storybook's role, and the approval UI to a
commissioned *Experience and presentation* companion document, naming the seams
it must respect — the event log as observability substrate, the run state
machine as intervention carrier, typed artifacts as the presentation contract.
That companion does not yet exist and is what settles this intent.

Inception context, not a decision: the workspace views anticipated during
inception were Overview, Research, Workflow, Evidence, Context, Compare,
Evaluations, Policy, and Settings. The *Experience and presentation* companion
must pressure-test whether each is a view, a panel within a view, or
unnecessary — the list is a starting point for the information-architecture
question above, not an answer to it.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r9 — second citation restated as a criterion after the enumeration
  proved already incomplete; the cross-release exclusion's reach determined,
  2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
