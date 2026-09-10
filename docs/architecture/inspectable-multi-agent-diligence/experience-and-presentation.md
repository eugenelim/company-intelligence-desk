# Experience and presentation — companion to the diligence design

**Author(s):** eugenelim
**Status:** Draft — revision c3
**Last updated:** 2026-09-10
**Parent:** [`runtime-architecture.md`](runtime-architecture.md), whose § Scope commissions this
document and names the seam it must respect: **typed artifacts are the
presentation contract**.
**Settles:** most of
[`multi-workspace-inspectable-experience`](../../product/intents/multi-workspace-inspectable-experience.md).
Not all of it — see § Disposition of the intent's questions.

## TL;DR

Four views plus a run-initiation action, derived from a **reachability table**
that maps every item the intent requires to the surface exposing it. Renderers
are code registered against artifact types, and **model-authored prose is
rendered as text through a sanitizing path** — the memo is the largest untrusted
payload in the system, and a renderer contract written only for typed fields
exempts it by accident. A role preset rearranges panels and never hides data.

## Scope

**This document owns** the four concerns the parent defers: the UI/API
presentation contract, workspace information architecture, Storybook's role, and
the approval UI surface.

**This document does not own** what may leave the backend — that is
[`governed-observable-and-evaluable-operation`](../../product/intents/governed-observable-and-evaluable-operation.md)'s,
elaborated in
[`observability-and-evaluation.md`](observability-and-evaluation.md)
§ What may leave the backend to a user surface — nor how run events are carried,
which is `portable-identity-first-runtime`'s.

**Ratified and not reopened:** React; a shared component system documented
through Storybook; multiple workspace views; the browser UI and the API as
separate deployable containers.

**Excluded by the intent and not reopened:** arbitrary agent-generated HTML or
executable UI code rendered in the browser; exposure of private model reasoning;
a separate frontend deployment or microfrontend per workspace view. The first
two are load-bearing enough to be argued (§ Rendering model-authored prose,
§ What the inspection surfaces may never show); the third is simply not
available, so it is not argued as an alternative.

## Disposition of the intent's questions

| Intent § Unresolved question | Disposition |
| --- | --- |
| Primary workspace IA, and which views exist at all | **Settled** — § Information architecture |
| How analyst, builder, operator presets differ | **Settled** — § Role presets |
| Which Storybook scenarios become executable acceptance fixtures | **Settled** — § Storybook |
| The presentation contract between API and each view | **Settled** — § The presentation contract |
| How evidence, context, and policy decisions are represented *visually* | **Open.** This document names the surfaces that expose them; it does not specify their visual representation, and naming a panel is not designing one |
| What accessibility, responsive, and browser-support requirements apply | **Proposed for owner ratification** — § Accessibility. These are the least-evidenced claims here |

## Reachability

The intent requires that, for any completed run, a user can reach four sets from
a rendered surface without reading server logs or raw model output. Its
falsifier is an item of any set that no surface exposes. This table is the
answer and the thing most worth attacking.

**Reading note.** "`governed` § Outcome" in the intent means that intent's
*first* outcome. Its second outcome is expressly not a property of a completed
run. Its third is a separately headed outcome the intent does not cite here, so
it is outside this set **by reference rather than by per-run-ness** — the
sibling's deletion test does treat its coverage property as recoverable from one
run's event log. That property is nonetheless visible on the Run policy panel,
so nothing is unreachable either way.

| Required item | Source | Surface |
| --- | --- | --- |
| Step sequence a run took | `governed` 1st outcome, sub-result 1 | **Run** — step timeline |
| Policy decisions and their outcomes | `governed` 1st outcome, sub-result 2 | **Run** — policy panel |
| Human intervention points | `governed` 1st outcome, sub-result 3 | **Run** — timeline markers; **Approval** |
| Primary evidence, distinct from interpretation | `scoped` § In scope | **Evidence** |
| Versioned source manifests and context packages | `scoped` § In scope | **Evidence** (manifest, with its content-addressed `snapshot_id`); **Run** — context panel per step, showing the package's content hash and `context_assembler_version` from the producer tuple |
| No later evidence entered a historical as-of analysis | `scoped` § In scope | **Run** header — immutable `snapshot_id` with as-of date; **Evidence** — manifest pinned to that snapshot |
| Immutable evidence a material claim resolves to | `scoped` § Outcome | **Report** — claim → evidence |
| Explicit temporal scope | `scoped` § Outcome | **Run** header (run-level); **Report** — per-claim period, since cross-period comparison means claims legitimately carry different periods |
| Calculation lineage | `scoped` § Outcome | **Report** — claim → lineage |
| Human-readable research memo | `evidence-backed` § In scope | **Report** |
| Machine-readable evidence manifest | `evidence-backed` § In scope | **Evidence**, downloadable |

Everything above is exposed **as released under the guarded/streamable split**
in [`observability-and-evaluation.md`](observability-and-evaluation.md). The UI
cannot widen that: the API is the enforcement point by construction. In the MVP
that boundary is coarse — the parent records that authorization is coarse and
tenancy isolation does not exist, and the charter records that every
authenticated principal can read every run — so the split withholds by *guard
state*, not by principal.

**Deliberately absent, with reasons:**

- **Cross-release quality comparison** — not a per-run property; the intent
  places it outside this outcome.
- **Run-pair comparison.** Charter principle 7 ratifies that "a past run's
  quality can be compared against a later one", and `governed`'s second outcome
  frames release-pairs as the *extension* of it — so run-pair comparison is real
  and sits below the cross-release line. It is still not a *per-run* property,
  so it is outside this intent's outcome. Recorded here so its absence is a
  decision rather than an oversight.

## Information architecture — four views and one action

The nine views named at inception were Overview, Research, Workflow, Evidence,
Context, Compare, Evaluations, Policy, and Settings. The intent required each to
be pressure-tested as a view, a panel, or unnecessary.

| View | Contains |
| --- | --- |
| **Runs** | The run index: status, company, as-of date, flagged state. Carries the **New run** action |
| **Run** | Progressive workflow updates; step timeline; per-step **context** panel; **policy** panel; **evaluation** panel (this run's checks and their outcomes); run header with producer tuple, `snapshot_id`, as-of date |
| **Report** | The memo, every claim resolving to evidence or calculation lineage, with per-claim temporal scope |
| **Evidence** | Source manifest, primary evidence, the downloadable machine-readable manifest |

**Run initiation is an action on Runs, not a view.** `evidence-backed`'s outcome
begins "A user can ask what materially changed…", so a surface for asking must
exist. It is a form — company or ticker, plus an explicit as-of date — because
the ratified constraint requires the UI to be more than "only a chat interface",
and a two-field form is the honest shape for a two-parameter request. Making it
a view would give a modal-sized interaction a permanent home in the IA.

**The approval surface is a panel on Run**, present only while the run is in
`awaiting_approval` or `expired`. It is not a view because it exists for a
minority of runs and has no meaning away from the run it gates. § Reachability
cites it as **Approval**, and this is where it lives.

**Demoted to panels:** Overview (a run header, not a destination); Context and
Policy (per-step, meaningless away from the step that produced them);
Evaluations (this run's check outcomes; the *trend* belongs to cross-release
evaluability, which is elsewhere).

**Dropped:** Compare — cross-period comparison is content of the memo, which
`evidence-backed` § In scope commits to; run-pair and cross-release comparison
are outside this outcome per § Reachability. Settings — real, but not a
workspace view.

Four views satisfy the ratified "multiple workspace views" constraint in
substance: each is a distinct destination with its own address and its own
content, not a tab strip over one page. The count is a consequence of the
reachability table, not a target — a view exists when something in that table
has nowhere else to live.

## The presentation contract

**Typed artifacts, rendered by registered code.**

The API exposes an artifact as `{artifact_type, artifact_version, ref, ...typed
fields}`. The client holds a **renderer registry** keyed by
`(artifact_type, artifact_version)`; rendering is a pure function from typed data
to React elements.

**An unknown type falls back**, and the fallback is part of the contract: it
shows the type name, the reference, and a download, and never attempts to
interpret the payload. Adding an artifact type is additive; an unrecognised one
degrades visibly rather than breaking a view.

### Rendering model-authored prose

The intent excludes "arbitrary agent-generated HTML or executable UI code
rendered in the browser."

**A renderer registry alone does not deliver that exclusion.** The registry
covers *typed fields*; the **Report view renders a model-authored memo**, and a
memo rendered as Markdown permits raw HTML and `javascript:` or `data:` URIs. A
contract written only for typed fields exempts the largest untrusted payload in
the system by omission.

The exclusion is enforced by five mechanisms, and the claim is bounded by them
rather than asserted absolutely:

1. **Any text the initiating human did not author** — model-authored prose and
   retrieved evidence text alike — renders as plain text, or through a
   sanitizing renderer with a closed allowlist of inline elements and **no
   raw-HTML passthrough**. The scope is deliberately wider than model output:
   charter principle 1 treats retrieved third-party content as adversarial, and
   the Evidence view renders filing text.
2. **`dangerouslySetInnerHTML` is prohibited repo-wide**, enforced by lint
   rather than by review.
3. **URL-bearing fields are scheme-allowlisted to `https:`** before becoming an
   `href`.
4. **A Content-Security-Policy with no `unsafe-inline` and no `unsafe-eval`.**
5. **Artifact downloads are served from a distinct origin** with
   `Content-Disposition: attachment` and a fixed, non-sniffable `Content-Type`.
   This covers the fallback's download and the Evidence manifest: a same-origin
   HTML download is stored XSS.

Agent output is data passed to reviewed renderers. With these five in place
there is no path from untrusted text to executing code in the browser — **a
construction under these five mechanisms, not a guarantee against a determined
adaptive attacker.** The charter § Scope declines that warranty and this
document does not extend it. Without the five, the claim was decoration.

**Prose is fetched, not streamed.** The event stream carries only inlinable
forms — typed scalars, closed-vocabulary classifications, bounded identifiers,
counts — under
[`observability-and-evaluation.md`](observability-and-evaluation.md) § Payload
inlining. So the stream is directly renderable with no per-payload redaction
pass, and prose is fetched by reference through the API, where the guarded class
applies.

**Withheld renders as withheld.** The API returns an explicit marker with a
reason for a guarded field, never a null. A renderer must display "withheld,
guards pending" differently from an absent value; conflating them tells the user
a claim does not exist when it is merely not yet released.

### What the inspection surfaces may never show

The intent excludes "Exposure of private model reasoning", citing charter
principle 4. The step timeline, the per-step context panel, and the raw event
stream are exactly where chain-of-thought would surface if anything did.

The rule: these surfaces show **recorded inputs, decisions, and outcomes** — the
context package a step received, the policy decision and its outcome, the
artifacts a step produced. They do not show model deliberation. This holds
because such content is in the sibling's *never served* class and is not stored
in a servable location, so the UI cannot expose it even by mistake. The same
bound applies to the raw stream where it is available beneath the timeline.

## Role presets

Analyst, builder, and operator presets differ in **landing view and default
panel arrangement, and in nothing else**. Same view set, same API contract, same
data.

**A preset is never an authorization boundary.** Entitlements are owned by
`portable-identity-first-runtime` and enforced in the API. If a preset could
hide data, the hiding would be client-side and therefore not a control — an
operator preset that omits the policy panel must not be mistaken for a user who
may not see policy decisions. This is stated because the failure is attractive:
"just hide it in the UI" is the cheapest-looking answer and the wrong one.

**No preset may make any § Reachability row unreachable.** A default arrangement
is a starting position, not a subset: a collapsed panel is one interaction away,
a removed one is a falsified outcome.

## The approval surface

A run enters `awaiting_approval` when a pre-release check flags it. The surface
answers, without the approver reading logs:

- **which check flagged, and on what** — the specific claim or step, not a
  status;
- the claim's evidence and lineage, or their absence, which is usually why it
  flagged;
- the actions: **publish**, **return for revision**, **cancel the run**, or
  leave pending. Cancel is available because the parent's state table permits
  `any non-terminal → cancelled`.

**The approval surface reads guarded content under the sibling's adjudication
carve-out** — [`observability-and-evaluation.md`](observability-and-evaluation.md)
§ What may leave the backend to a user surface. Adjudication is not publication:
the flagged claim, its evidence and its lineage are served so the decision can be
made, and the read is itself recorded as an event. Without that carve-out the
guarded class would withhold precisely the content the approver must see, and
charter principle 3's "flagged output is held for a named human" could not be
executed.

The approver principal and the flag state are recorded as events by the backend;
the UI displays them and records nothing itself. `require_distinct_approver`
defaults to `false` for the single-operator MVP, and the surface shows which
principal approved even when it is the initiator — a single-operator system that
hides self-approval teaches the wrong pattern to a reader.

**`expired` is unreachable in the MVP.** The parent sets `approval_timeout` to
none by default, so no run times out. The state exists in the machine and the
surface handles it, but nothing exercises it until a timeout is configured.

Publication on a clean run is automatic per charter principle 3. The approval
surface is for *flagged* output only.

## Storybook

Storybook documents the shared component system — ratified — and carries the
executable acceptance fixtures the intent asks this document to identify.

**Every renderer ships five stories:** empty, loading, partial (a run still
streaming), error, and **withheld** (a guarded field the backend did not
release). **The registry ships a sixth**, its unknown-type fallback — that is a
property of the registry, not a state any single renderer can be in.

The withheld and fallback stories are the load-bearing ones. They are where a
renderer either degrades honestly or leaks an assumption that data is always
present and always known.

The approval surface additionally ships stories for `awaiting_approval` and
`expired`; reopening an expired approval returns to `awaiting_approval` and is
not a third state.

A renderer without its five stories is incomplete, which is a reviewable
condition rather than a matter of taste.

## Accessibility, responsiveness, browser support

**Proposed for owner ratification, not settled.** The intent asks what
requirements apply; this document proposes:

- **WCAG 2.2 AA.** Every view keyboard-operable end to end. The run timeline and
  the approval surface are the two most likely to fail, because both invite
  bespoke interaction.
- **`prefers-reduced-motion` respected** by the progressive-update surface, the
  only animated one.
- **Responsive to tablet width.** The workbench is a desk tool; phone layouts
  are not a goal.
- **Evergreen browsers**, current and one prior major version.

These are the least-evidenced claims in this document — no user research, no
stated regulatory obligation.

## Alternatives considered

**Agent-authored UI — model-generated markup or component code.** Excluded by
the intent, and worth recording *why it is attractive*: it appears to solve the
unknown-artifact problem for free. It solves it by making model output
executable in the user's browser, converting an injection into client-side code
execution. The renderer registry with a visible fallback is the same flexibility
without that.

**Server-rendered artifact HTML from reviewed templates.** A genuine
alternative: the API returns rendered HTML produced by reviewed server-side
templates rather than typed data, and the client displays it. It centralises
rendering, guarantees one implementation, and makes the redaction boundary and
the markup boundary the same boundary. Rejected because it collapses the parent's
seam — typed artifacts as the presentation contract — into an HTML contract, so
every presentation change becomes a backend deployment, and because a reference
implementation teaching typed-artifact rendering should show it rather than route
around it. Closer than it first appears, and reconsiderable if renderer
duplication becomes the dominant cost.

**Rendering the raw event stream as the primary surface.** Rejected. It is the
most faithful view of what happened and the least usable, and the intent requires
reachability "without reading server logs or raw model output". The timeline is a
projection of the stream; the stream remains available beneath it, under the same
never-served bound.

**A generic table-driven UI over the artifact JSON.** Rejected. It would satisfy
reachability mechanically while defeating the purpose: a reader should see how a
typed artifact is deliberately presented, and
`adoptable-reference-implementation` makes legibility a satisfaction condition
rather than a tradeable attribute.

*A microfrontend per view is excluded by the intent and is noted in § Scope
rather than argued here; an option that was never available is not an
alternative.*

## Risks

- **The reachability table is the whole outcome and is hand-maintained.** If an
  intent adds a required item and the table is not updated, the falsifier fires
  and nothing mechanical catches it. A test asserting one rendered route per row
  is the obvious control and does not exist.
- **Four views is a floor, not a finding.** It follows from today's reachability
  set, and the pressure will be to bolt the fifth onto Run.
- **The five prose-rendering mechanisms are independent, and any one lapsing is
  sufficient.** The lint rule is the most likely to be disabled locally "just
  this once"; the CSP is the most likely to be loosened by a dependency that
  wants inline styles.
- **The withheld state is easy to ship wrong.** An empty cell for a withheld
  field is indistinguishable from an absent one. The Storybook fixture is where
  that is enforced, and a fixture can be written to pass without being looked at.
- **Progressive updates invite a second source of truth.** A client accumulating
  state from the stream will eventually disagree with the backend; the parent's
  snapshot endpoint is the reconciliation path, and a client that never calls it
  drifts silently.

## Known at ship

1. **No usability evidence.** The four-view IA is derived from the reachability
   requirement, not from watching anyone use it.
2. **The accessibility targets are unverified proposals.**
3. **No reachability test exists**, so the intent's falsifier is checked by
   reading rather than by running.
4. **Role presets are specified but unmotivated.** Three are named because the
   intent asked how they differ; no evidence says three is right.
5. **Visual representation of evidence, context, and policy decisions is
   unsettled** — the intent's question is open, and naming a panel is not
   designing one.
6. **The intent's § Next step overclaims this companion.** It says the companion
   "is what settles this intent", without qualification, which § Disposition now
   contradicts. The intent needs a one-line amendment to "settles all but the
   visual-representation question" — carried in the sign-off packet, not fixed
   here, because amending an Accepted intent is a material edit.

## Open questions

- How are evidence, context, and policy decisions represented *visually*? Open
  from the intent and not settled here.
- Does the analyst preset need a different landing view at all, or is Runs
  correct for everyone until evidence says otherwise?
- What does Report do with a claim whose evidence resolves but whose lineage the
  reader cannot follow? Showing lineage is not the same as making it legible.
- Should Evidence expose full filing text, or only the extracts a claim resolves
  to? Full text is more inspectable and is also the largest untrusted payload.
- What is the empty state of Runs for a first-time reader — the moment that most
  determines whether the repository teaches anything?
