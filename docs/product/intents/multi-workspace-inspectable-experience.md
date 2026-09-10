# Multi-Workspace Inspectable Experience

- **Status:** Accepted
- **Kind:** outcome

## Outcome

For any completed run, a user can reach from a rendered surface — without
reading server logs or raw model output — the **per-run** properties
[`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md)
§ Outcome makes auditable — as released under that intent's redaction rules,
which it owns and this one does not — together with what
[`scoped-context-and-evidence.md`](scoped-context-and-evidence.md) § In scope
makes versioned and inspectable, whatever its Outcome requires a material
output to resolve to, and the two user-facing deliverables
[`evidence-backed-company-diligence.md`](evidence-backed-company-diligence.md)
§ In scope commits to.

*Falsifying observation:* an item of any of the four sets above that no rendered
surface exposes for a completed run.

**Cross-release quality comparison is deliberately outside this outcome, because
it is not a per-run property.** That is the criterion, not a pointer: the
exclusion holds however the intent that owns cross-release evaluability is
numbered or structured. Which views exist at all is open under the
information-architecture question below and owned here; which of them land in
the MVP is the delivery brief's slicing decision. This outcome decides neither.
This intent does not define what is auditable; it owns whether the per-run set
is *reachable*.

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
- Surfacing of the per-run sets named in § Outcome.
- Presentation of progressive workflow updates during a run.

This intent owns **what the user sees**. It does not own what may leave the
backend (see [`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md))
or how run events are carried and survive restart (see
[`portable-identity-first-runtime.md`](portable-identity-first-runtime.md)).

### Excluded

- Arbitrary agent-generated HTML or executable UI code rendered in the browser.
- Exposure of private model reasoning, excluded by
  [`docs/CHARTER.md`](../../CHARTER.md) principle 4.
- A separate frontend deployment or microfrontend for every workspace view.

## Owner

eugenelim — decides experience scope and the presentation contract.

## Unresolved questions

- What is the primary workspace information architecture, and which views exist
  at all?
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
entirely**: `runtime-architecture.md` § Scope hands the UI/API presentation contract,
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
- Revision: r13 — the private-model-reasoning exclusion cited to charter
  principle 4 rather than restated by hand, matching how every other
  externally-owned bound in this file is handled, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
