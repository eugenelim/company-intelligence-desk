# Experience and presentation — companion to the diligence design

**Author(s):** eugenelim
**Status:** Draft — revision c1
**Last updated:** 2026-09-10
**Parent:** [`design-doc.md`](design-doc.md), whose § Scope commissions this
document and names the seam it must respect: **typed artifacts are the
presentation contract**.
**Settles:** [`multi-workspace-inspectable-experience`](../../product/intents/multi-workspace-inspectable-experience.md)
in full.

## TL;DR

Four views, not nine. Renderers are **code registered against artifact types**,
never markup produced by an agent. A role preset rearranges panels and never
hides data, because hiding in the client is not a control. The document's centre
is § Reachability, which maps every item the intent requires to be reachable to
the surface that exposes it — that mapping is what the intent's falsifier tests.

## Scope

**This document owns** the four concerns the parent defers: the UI/API
presentation contract, workspace information architecture, Storybook's role, and
the approval UI surface.

**This document does not own** what may leave the backend — redaction is
[`governed-observable-and-evaluable-operation`](../../product/intents/governed-observable-and-evaluable-operation.md)'s,
elaborated in [`observability-and-evaluation.md`](observability-and-evaluation.md) —
nor how run events are carried, which is
[`portable-identity-first-runtime`](../../product/intents/portable-identity-first-runtime.md)'s.
The UI renders what it is given and decides nothing about what it is given.

**Ratified and not reopened:** React; a shared component system documented
through Storybook; multiple workspace views; the browser UI and the API as
separate deployable containers.

## Reachability

The intent's outcome requires that, for any completed run, a user can reach four
sets from a rendered surface without reading server logs or raw model output.
Its falsifier is an item of any set that no surface exposes. This table is the
answer, and it is the part of this document most worth attacking.

| Required item | Source | Surface |
| --- | --- | --- |
| Step sequence a run took | `governed` 1st outcome, sub-result 1 | **Run** — step timeline |
| Policy decisions and their outcomes | sub-result 2 | **Run** — policy panel |
| Human intervention points | sub-result 3 | **Run** — timeline markers, and **Approval** |
| Primary evidence, distinct from interpretation | `scoped` § In scope | **Evidence** |
| Versioned source manifests and context packages | `scoped` § In scope | **Evidence** (manifest), **Run** — context panel per step |
| Immutable evidence a material claim resolves to | `scoped` § Outcome | **Report** — claim → evidence |
| Explicit temporal scope | `scoped` § Outcome | **Run** header (`snapshot_id`, as-of date) |
| Calculation lineage | `scoped` § Outcome | **Report** — claim → lineage |
| Human-readable research memo | `evidence-backed` § In scope | **Report** |
| Machine-readable evidence manifest | `evidence-backed` § In scope | **Evidence**, downloadable |

Everything above is exposed **as released under `governed`'s redaction rules**.
The UI cannot widen that: it renders what the API returns, and the API applies
the boundary. A surface showing something the redaction rules withhold is a
backend defect, not a UI defect.

**Deliberately absent:** cross-release quality comparison. It is not a per-run
property and the intent places it outside this outcome.

## Information architecture — four views

The nine views named at inception were Overview, Research, Workflow, Evidence,
Context, Compare, Evaluations, Policy, and Settings. The intent required each to
be pressure-tested as a view, a panel, or unnecessary. Result:

| View | Contains | Was |
| --- | --- | --- |
| **Runs** | The run index: status, company, as-of date, flagged state | — |
| **Run** | Progressive workflow updates; step timeline; per-step **context** panel; **policy** panel; run header carrying the producer tuple and `snapshot_id` | Workflow + Overview + Context + Policy |
| **Report** | The memo, with every claim resolving to evidence or calculation lineage | Research |
| **Evidence** | Source manifest, primary evidence, the downloadable machine-readable manifest | Evidence |

Demoted to panels: **Overview** (a run header, not a destination), **Context**
and **Policy** (both per-step, and meaningless away from the step that produced
them). Dropped: **Compare** — cross-period comparison is *content of the memo*,
which `evidence-backed` § In scope commits to, and cross-release comparison is
outside this intent. **Evaluations** — per-run evaluation output is a panel on
Run; the trended view belongs to cross-release evaluability, which is not here.
**Settings** — real but not a workspace view.

Four views satisfy the ratified "multiple workspace views" constraint. The
count is a consequence of the reachability table, not a target: a view exists
when something in that table has nowhere else to live.

## The presentation contract

**Typed artifacts, rendered by registered code.**

The API exposes an artifact as `{artifact_type, artifact_version, ref, ...typed
fields}`. The client holds a **renderer registry** keyed by
`(artifact_type, artifact_version)`. Rendering is a pure function from typed
data to React elements.

**An unknown type falls back**, and the fallback is part of the contract: it
shows the type name, the reference, and a download, and never attempts to
interpret the payload. Adding an artifact type is therefore additive — an
unrecognised one degrades visibly rather than breaking a view.

**No agent-generated markup, ever.** The intent excludes "arbitrary
agent-generated HTML or executable UI code rendered in the browser". Renderers
are reviewed code in the repository; agent output is *data* passed to them. There
is no path by which model output becomes markup, which is the property that makes
the exclusion enforceable rather than aspirational.

**Prose is fetched, not streamed.** The event stream carries only inlinable
forms — typed scalars, closed-vocabulary classifications, identifiers — under
[`observability-and-evaluation.md`](observability-and-evaluation.md) § Payload
inlining. So the stream is directly renderable with no per-payload redaction
pass, and prose (memo text, filing extracts) is fetched by reference through the
API, where redaction applies. This is why the inlining rule is worth its
constraint.

**Progressive updates** consume the parent's SSE stream. The client owns its
cursor and reopens explicitly, per the parent's § Event log and stream mechanism;
this document adds no transport behaviour.

## Role presets

Analyst, builder, and operator presets differ in **landing view and default
panel arrangement, and in nothing else**. Same view set, same API contract, same
data.

**A preset is never an authorization boundary.** Entitlements are owned by
`portable-identity-first-runtime`, enforced in the API. If a preset were allowed
to hide data, the hiding would be client-side and therefore not a control — an
operator preset that omits the policy panel must not be mistaken for a user who
may not see policy decisions. Stated here because the failure is attractive:
"just hide it in the UI" is the cheapest-looking answer and the wrong one.

## The approval surface

A run enters `awaiting_approval` when a pre-release check flags it. The surface
must answer, without the approver reading logs:

- **which check flagged, and on what** — the specific claim or step, not a
  status;
- the claim's evidence and lineage, or their absence, which is usually the
  reason it flagged;
- the actions: publish, return for revision, or leave pending.

The approver principal and the flag state are recorded as events by the backend;
the UI displays them and records nothing itself. `require_distinct_approver`
defaults to `false` for the single-operator MVP, and the surface shows which
principal approved even when it is the initiator — a single-operator system that
hides self-approval teaches the wrong pattern to a reader.

Publication on a clean run is automatic, per charter principle 3 as amended. The
approval surface is for *flagged* output only.

## Storybook, and which scenarios are acceptance fixtures

Storybook documents the shared component system — ratified — and additionally
carries the executable acceptance fixtures the intent asks this document to
identify.

**Every renderer ships stories for the full state set:** empty, loading, partial
(a run still streaming), error, **redacted** (a field the backend withheld), and
**unknown type** (the fallback). These six are the acceptance fixtures. The
redacted and unknown-type states are the load-bearing ones — they are where a
renderer either degrades honestly or leaks an assumption that the data is always
present and always known.

The approval surface additionally ships stories for each state of the parent's
run state machine that a user can act on: `awaiting_approval`, `expired`, and
`expired` reopened.

A renderer without its six stories is incomplete, which is a reviewable
condition rather than a matter of taste.

## Accessibility, responsiveness, browser support

Proposed, not ratified:

- **WCAG 2.2 AA** as the target. Every view keyboard-operable end to end; the
  run timeline and the approval surface are the two that most easily fail this,
  because both invite bespoke interaction.
- **`prefers-reduced-motion` respected** by the progressive-update surface,
  which is the only animated one.
- **Responsive to tablet width.** The workbench is a desk tool; phone layouts
  are not a goal and pretending otherwise costs more than it returns.
- **Evergreen browsers**, current and one prior major version.

These are the least-evidenced claims in this document. They are proposals for
the owner, not findings.

## Alternatives considered

**A microfrontend or separate deployment per workspace view.** Excluded by the
intent, and the exclusion is right: four views sharing one component system have
no independent release pressure, and per-view deployment would multiply the
build and identity surface for no delivered benefit.

**Agent-authored UI — model-generated markup or component code.** Excluded by
the intent. Worth recording *why* it is attractive: it appears to solve the
unknown-artifact problem for free. It solves it by making model output
executable in the user's browser, which converts an injection into code
execution on the client. The renderer registry with a visible fallback is the
same flexibility without that.

**Rendering the raw event stream as the primary surface.** Rejected. It is the
most faithful view of what happened and the least usable, and the intent requires
reachability "without reading server logs or raw model output". The timeline is a
projection of the stream; the stream remains available beneath it.

**A generic table-driven UI over the artifact JSON.** Rejected. It would satisfy
reachability mechanically while defeating the project's purpose: a reader
learning from this repository should see how a typed artifact is deliberately
presented, and `adoptable-reference-implementation` makes legibility a
satisfaction condition rather than a tradeable attribute.

## Risks

- **The reachability table is the whole outcome, and it is hand-maintained.** If
  an intent adds a required item and the table is not updated, the falsifier
  fires and nothing mechanical catches it. A test that asserts one rendered
  route per row is the obvious control and does not yet exist.
- **Four views is a floor, not a finding.** It follows from today's reachability
  set. A fifth becomes necessary the moment something in that set has nowhere to
  live, and the pressure will be to bolt it onto Run instead.
- **The redacted state is easy to ship wrong.** A renderer that shows an empty
  cell where the backend withheld a field is indistinguishable from one showing
  a field that was genuinely absent. The two must render differently, and the
  Storybook fixture is where that is enforced.
- **Progressive updates invite a second source of truth.** A client accumulating
  its own state from the stream will eventually disagree with the backend. The
  parent's snapshot endpoint is the reconciliation path; a client that never
  calls it will drift silently.

## Known at ship

1. **No usability evidence.** The four-view IA is derived from the reachability
   requirement, not from watching anyone use it. It is a defensible starting
   structure, not a validated one.
2. **The accessibility targets are unverified proposals** (§ Accessibility).
3. **No reachability test exists** (§ Risks), so the intent's falsifier is
   checked by reading rather than by running.
4. **Role presets are specified but unmotivated.** Three presets are named
   because the intent asked how they differ; no evidence says three is the right
   number or that operators want a different landing view.

## Open questions

- Does the analyst preset need a different landing view at all, or is Runs
  correct for everyone until evidence says otherwise?
- What does the Report view do with a claim whose evidence resolves but whose
  lineage is a calculation the reader cannot follow? Showing the lineage is not
  the same as making it legible.
- Should the Evidence view expose the full filing text, or only the extracts a
  claim resolves to? Full text is more inspectable and is also the largest
  untrusted payload in the system.
- What is the empty state of the Runs view for a first-time reader — the moment
  that most determines whether the repository teaches anything?
