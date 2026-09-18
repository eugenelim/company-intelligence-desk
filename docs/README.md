# docs/

What belongs where in this repository's documentation, and which parts must
match current reality.

Read this before adding a document. Putting a fact in the wrong layer is the
most common source of documentation rot: a decision recorded as current state
goes stale, and current state recorded as a decision never gets updated.

## The map

| Area | What belongs there | Lifecycle |
| --- | --- | --- |
| [`CHARTER.md`](CHARTER.md) | Mission, domain, scope, principles — the why. Stable for years | living, changed only by RFC |
| [`architecture/`](architecture/) | How the code is organized today — the map you read to find things, and the golden path new work conforms to | living |
| [`product/`](product/) | What the product is doing today: direction, release history, the intents and briefs behind in-flight work, and answered research | living |
| [`specs/`](specs/) | The engineering contract for one feature, with its implementation plan | living while building, frozen once shipped |
| [`knowledge/`](knowledge/) | Practitioner residue — patterns, gotchas and antipatterns scoped to a file glob | living |
| [`adr/`](adr/) | Why we chose X over Y, one decision per record | frozen |
| [`rfc/`](rfc/) | Proposals to change the charter or a convention | governance |

Add a row when you install a pack that seeds a new area, or when you create
one. Each area's own README says what belongs in it and what does not.

The bottom layers cite the upper layers; upper layers do not know about lower
layers. That is the whole point of the hierarchy.

### Two architecture documents, two jobs

`architecture/overview.md` is **descriptive** — the map of how the code is
organized today, read to find things. `architecture/reference.md` is
**normative** — the golden path (stack, building blocks, cross-cutting
standards) that new work conforms to. A thin repository has only the map; the
golden path appears once there are real architecture decisions to hold work to.

Getting these the wrong way round is the common mistake: a map written as a
standard goes stale the moment the code moves, and a standard written as a map
never gets enforced.

### The delivery-brief altitude

A delivery brief (`product/briefs/<slug>.md`) sits between the roadmap and the
specs — where a multi-feature delivery handoff lands when it is too big to be
one spec. The altitude reads `roadmap → intent → delivery brief → spec → AC`: the
roadmap names themes, an intent records one admitted outcome, a delivery brief
records the specs that deliver it, a spec is the engineering contract for one
feature, and an acceptance criterion is the testable unit.

A delivery brief owns only this repository's slice; an optional `Epic:` field
points up to an external coordinator when the work spans repositories. A derived
spec links back with a `Brief:` field, and the brief's coverage map rolls up from
those specs' `Status:` fields.

## The three lifecycle classes

Every document belongs to exactly one, and the maintenance rule differs:

- **living** — must match current reality, and is updated in the same change as
  anything that affects it. Drift is a bug, not debt. `CHARTER.md`,
  `architecture/*`, `product/*`, `knowledge/*` and active `specs/*`.
- **frozen** — an immutable record of what was decided or delivered. Status
  fields may still change (Accepted → Superseded); bodies may not. Never edited
  to reflect a later change; superseded by a new record that cites it. `adr/*`,
  shipped `specs/*`, and accepted or rejected `rfc/*`.
- **governance** — an in-flight proposal, open until it is accepted, rejected or
  withdrawn. It describes what someone wants, not what is. Open `rfc/*`.

The most important property of this scheme is that the frozen layer gives you
decision history *without* the burden of keeping it in sync. Living docs can be
honest about the present because they do not also have to record how we got
here. That is what ADRs are for.

### A spec directory freezes as a unit, when the spec ships

Shipped `specs/*` above means the whole directory — `spec.md` **and**
`plan.md`. The plan template's line "Unlike the spec, this document is allowed
to change as you learn" is phase-scoped, not a standing exemption: it holds
only while the plan is `Drafting`.

The two stages, the bookkeeping still permitted after the pair is pinned, and
how to supersede a frozen document are specified in the `new-spec` skill's
`references/spec-and-plan-contract.md` § A spec directory freezes as a unit.

## When a rule here is wrong

If a convention in this repository is causing friction, **say so in an RFC**.
Do not quietly deviate. The whole point of writing it down is that the rules
are visible and contestable.

Rules about *how work is done* — the loop, its gates, and the rationalizations
it refuses — live in [`CONVENTIONS.md`](CONVENTIONS.md). Rules an agent must
load before acting live in [`../AGENTS.md`](../AGENTS.md).
