# RFC-0001: Initial Project Charter — Company Intelligence Desk

- **Status:** Draft
- **Author:** eugenelim
- **Approver:** eugenelim. This repository has a single maintainer, so
  self-approval is the available route.
- **Date opened:** 2026-09-09
- **Decision weight:** standard — the middle of `light | standard | heavy`. It
  sets how much verification this RFC owes before circulation, not who approves
  it.
- **Related:** the six Draft foundation intents —
  [`portable-identity-first-runtime`](../product/intents/portable-identity-first-runtime.md),
  [`scoped-context-and-evidence`](../product/intents/scoped-context-and-evidence.md),
  [`evidence-backed-company-diligence`](../product/intents/evidence-backed-company-diligence.md),
  [`governed-observable-and-evaluable-operation`](../product/intents/governed-observable-and-evaluable-operation.md),
  [`multi-workspace-inspectable-experience`](../product/intents/multi-workspace-inspectable-experience.md),
  [`adoptable-reference-implementation`](../product/intents/adoptable-reference-implementation.md)
  — their [`README`](../product/intents/README.md), the Draft delivery brief
  [`inspectable-diligence-mvp`](../product/briefs/inspectable-diligence-mvp.md),
  and the Draft architecture design
  [`inspectable-multi-agent-diligence`](../architecture/inspectable-multi-agent-diligence/design-doc.md)
- **Notes:** [`0001-notes/review-record.md`](0001-notes/review-record.md) — the
  independent reviews this RFC relies on

## Reviewer brief

- **Decision:** Adopt an initial charter for Company Intelligence Desk.
- **Recommended outcome:** accept
- **Change if accepted:** two file edits, listed under *Follow-on artifacts*.
- **Affected surface:** `docs/CHARTER.md` and `AGENTS.md`, both read by every
  agent session and every new contributor.
- **Stakes:** reversible by a later RFC, but a charter relied on for months costs
  trust to rewrite. Costly, not one-way.
- **Review focus:** does the "does not do" list let you *reject* a concrete
  request, and do the principles decide anything?

## The ask

**Recommendation.** Adopt the charter reproduced below.

**Why now.** `docs/CHARTER.md` is still the unmodified seed — its mission reads
`<replace with one sentence>` and its scope bullets (lines 25, 26, 30, 31) read
`<bullet>`. Six foundation intents, a delivery brief, and a reviewed architecture
design all exist. The project has substance in every artifact except the one a
contributor opens first.

| ID | Question | Recommendation | Decide by |
| --- | --- | --- | --- |
| D1 | Replace the placeholder with the proposed mission, domain, scope, and principles? | Yes — adopt as proposed | At acceptance |
| D2 | Keep `## Domain` as a section distinct from `## Scope`? | Yes. `CONVENTIONS.md` § 1 enumerates Mission/Scope/Principles, so this is an addition this RFC authorizes rather than a silent departure. It earns its place because the project has two domains a reader will otherwise conflate — the engineering domain it is a reference for, and the demonstration domain it happens to use. Without it a reader concludes this is a finance tool. | At acceptance |

## Problem & goals

`docs/CHARTER.md` has no project-specific content. That does not mean the project
has no boundaries — it has many, distributed across six intents that carry a
ratified constraint set and their own exclusion blocks, plus `CONVENTIONS.md`
routing reserved changes. What is missing is a single document stating *what the
project is for*, and none of the six intents is what a contributor opens first.

**Goal:** one short page stating purpose — mission, domain, what the project does
and refuses to do, and the principles that break ties.

**What the charter deliberately leaves to other documents.** The intents carry a
ratified constraint set covering runtime, host, model access, UI framework,
evidence tier, and deployment process. The charter does not restate any of them.
A charter is amended more slowly than an intent, so a second copy would drift
from the first, and the intents' README already declares its set closed. The
charter therefore states purpose and points at the intents for commitments.

The corollary matters and is stated in the charter itself: **the charter's
silence on a technology direction is not permission.** A contributor reading only
the charter would find portability invited and could accept work the ratified
constraints forbid.

## Proposal

Replace `docs/CHARTER.md` in full with the following.

---

```markdown
# Charter

> The foundational document for this project. One page, read whole.
> Covers what [CNCF's charter guidance](https://contribute.cncf.io/maintainers/governance/charter/)
> describes as a charter's substance — mission, scope, values and principles.
> Keeping that substance on a single page and revising it rarely is this
> project's choice; CNCF notes it is often distributed across governance docs and
> READMEs, and expected to evolve.

Changes to this file go through an RFC. The rest of the docs in this repo
are scaffolding around it; this file is the why.

---

## Mission

Provide an inspectable reference implementation of a governed multi-agent
application, demonstrated through evidence-backed public-company diligence.

The project exists to make the important parts of an agentic system visible and
reviewable: what work was requested, which evidence and context were supplied,
which tools and policies applied, what conclusions were produced, how those
conclusions were verified, and where humans retained authority.

## Domain

Agentic application engineering, demonstrated through evidence-backed
public-company research using public sources.

The engineering domain includes bounded multi-agent workflows, human-agent
interaction, context and evidence management, deterministic and agentic
responsibility boundaries, policy enforcement, observability, evaluation, and
portable deployment.

The demonstration domain is public-company diligence. It is a reference use
case; it does not make this an investment-advice service.

## Scope

What this project does:

- Provides a functioning research workbench demonstrating a governed
  multi-agent workflow.
- Produces public-company analysis scoped to an explicit as-of date.
- Makes workflow progress, evidence, context scope, interpretations,
  verification, policy outcomes, and evaluations inspectable.
- Combines deterministic software with agents where bounded interpretation,
  planning, or synthesis adds value.
- Preserves human authority where verification flags output, and records every
  human intervention.
- Uses explicit application-owned contracts so infrastructure, model, policy,
  storage, and observability implementations can be replaced where practical.
- Retains an inspection record of what ran, on what evidence, and under whose
  authority.
- Serves as both a useful demonstration application and an engineering
  reference for other governed agentic systems.

What this project does **not** do:

- It does not provide investment advice.
- It does not autonomously trade securities or manage portfolios.
- It does not generate authoritative buy, sell, or price-target decisions.
- It does not become a framework, library, or extractable SDK, and it does not
  genericize its domain to serve more use cases. The specificity is what makes
  the patterns legible.
- It does not warrant that the security patterns it demonstrates are effective
  against a determined adaptive attacker. Their evidence base and its limits
  are recorded in the architecture documentation.
- It does not redistribute private, paid, licensed, or restricted research
  data.
- It does not make core application behavior inseparable from one cloud, model
  provider, policy engine, or observability product.

Two disclaimers, which are not scope boundaries: model-generated analysis is
not guaranteed complete or correct, and nothing here removes human
accountability for consequential conclusions.

**Silence is not permission.** This list bounds *purpose*. Technology and
delivery commitments are ratified in `product/intents/`; check there before
assuming a direction is open. If the project is being asked to do something on
neither list, that is a signal to refine this section rather than drift.

## Principles

### 1. Evidence before assertion

Material claims must be traceable to identifiable evidence or deterministic
calculation lineage. Unsupported confidence is a defect.

Retrieved third-party content is treated as adversarial input authored by a
party with an interest in the analysis. Verification establishes *provenance* —
that a claim resolves to real evidence — and does not detect an adversary who
selects which real evidence is shown.

*Applied:* a claim with no resolvable evidence locator blocks publication.

### 2. Deterministic before agentic

Parsing, arithmetic, validation, authorization, policy invariants, and other
reliably computable behavior belong in deterministic code. Agents are used
where interpretation, planning, synthesis, or bounded choice adds value.

*Applied:* financial figures are computed, never inferred; an agent may
interpret a computed figure but may not produce one.

### 3. Human authority at consequential boundaries

The system may research, compare, explain, and recommend further inquiry.
Humans retain control over approval of flagged output, policy exceptions, and
consequential use.

Output passing every check publishes without human review. Such output has not
been examined for adversarial evidence selection — see principle 1 — so the
criteria that select output for automatic publication are themselves reserved:
any change to them, in either direction, takes the route this charter takes.

*Applied:* flagged output is held for a named human. Whether that human must
differ from the requester is configurable and recorded; it defaults to
permitting self-approval, which any deployment with more than one principal
must change.

### 4. Inspectability over magic

Users and maintainers should be able to inspect workflow state, evidence,
context scope, policy outcomes, evaluation results, and uncertainty without
exposing private chain-of-thought.

*Applied:* a completed run is auditable afterwards from its recorded evidence
alone, without re-running it.

### 5. Identity and least privilege over secret sprawl

Ambient workload identity is the default: components use bounded identities and
short-lived credentials, and receive only the permissions and network access
their responsibility requires. A static credential is admitted only where its
owner and rotation procedure are recorded before the credential is created.

No runtime or agent identity may create or widen its own authority, and no
delegation amplifies it: authority is bounded by the human who initiated the
work and by whatever delegated it.

*Applied:* the internet-facing component holds no model-invocation permission
at all.

### 6. Portability through explicit contracts

Application-owned interfaces separate domain behavior from model providers,
cloud services, policy engines, storage systems, observability products, and
deployment platforms.

*Applied:* changing model provider changes one adapter and no domain code.

### 7. Auditable replay and evaluation by construction

Runs are temporally scoped, versioned, observable, and testable. Provenance,
quality regressions, policy decisions, and unresolved uncertainty are visible
rather than hidden.

*Applied:* a past run's quality can be compared against a later one because
both recorded the evidence, the context, and the producing configuration.
Reproducibility here means the record can be re-read, not that re-execution
returns the same result.

## What's NOT in this charter

- **Technology and delivery commitments** live in [`product/intents/`](product/intents/),
  where architecture is bound by them.
- **Decision history** lives in [`adr/`](adr/).
- **Current product state** lives in [`product/`](product/).
- **Current architecture state** lives in [`architecture/`](architecture/).
- **Conventions for how we work** live in [`CONVENTIONS.md`](CONVENTIONS.md).
- **Governance** — roles, decision-making, voting — would live in a
  `GOVERNANCE.md` if the project ever needs one. It does not exist; most small
  projects never need it, and governance ceremony a project does not need
  produces theater rather than clarity.

## When to revise

Revise this charter when:

- The mission has actually changed — rare, and usually a fork.
- Scope has shifted enough that PRs routinely land for things it doesn't cover.
- A principle has stopped resolving ties: it is being ignored, or it
  contradicts another in ways we haven't acknowledged.

Revise via RFC. Editing the charter directly without discussion is the
single fastest way to lose the trust this document is meant to build.
```

---

## Alternatives

The only serious alternative is a charter that also records the ratified
constraints, so a reader finds everything in one place. It is rejected because
the charter is the slower artifact to amend and the intents' README declares its
constraint set closed: two closed records of the same facts eventually disagree,
and the charter would be the stale one. Leaving the placeholder is not a live
option — the project already has boundaries, and no document states its purpose.

## Risks

- **The "does not do" list is incomplete.** Exclusion lists get discovered, not
  designed. The charter carries its own refine-don't-drift instruction, and the
  *silence is not permission* clause covers the specific case where a reader
  finds the charter permissive and the intents restrictive.
- **Principles 1 and 2 can conflict.** An agent's interpretation may be the only
  route to a claim principle 1 wants evidence-linked. The charter does not rank
  them; the conflict belongs in a specific design or spec review, and a charter
  that pre-resolves every tie is over-specified.
- **Several clauses derive from a Draft, unsigned architecture design** — the two
  amended principles, principle 3's approver-independence and reserved-criteria
  clauses, principle 4's and 5's and 7's examples, and the security-pattern
  fitness exclusion. If that design changes materially before owner sign-off,
  each must be re-derived rather than assumed.
- **What would make this wrong:** if the stated purpose conflicts with what the
  project does. Because the charter asserts no technology, such a conflict could
  only arise at the level of purpose, which is where a charter should win.

## Evidence

- **`docs/CHARTER.md` (current)** — verified: line 19 is
  `<replace with one sentence>`; lines 25, 26, 30, 31 are `<bullet>`; lines 7–8
  read "Changes to this file go through an RFC."
- **`docs/CONVENTIONS.md` § 1** — verified: charter mission, scope, and
  foundational-principle changes are reserved; § 1 enumerates the charter's
  contents as Mission, Scope, Principles, each principle carrying "a
  one-sentence elaboration with a concrete example"; and it documents no
  initial-seed exception, which is why initial population takes the RFC route.
- **The six foundation intents.** Their [`README`](../product/intents/README.md)
  § 1 indexes a closed ratified constraint set and separately lists candidate
  technologies still under evaluation. That README is an index: the normative
  wording of each constraint lives in its owning intent's `### Confirmed
  constraints` block, which is where this RFC's claims about specific
  constraints should be checked.
- **[The architecture design](../architecture/inspectable-multi-agent-diligence/design-doc.md)**
  — its *Charter amendments required before ratification* section is the sole
  source of the two principle amendments, stating that principle 7's heading
  should read *auditable replay* and that principle 3 should narrow
  *publication* to *approval of flagged output*. Draft, r6, four review rounds,
  owner sign-off outstanding.
- **[Review record](0001-notes/review-record.md)** — two rounds of adversarial,
  security, and fresh-reader review, including which security findings were
  applied to the charter and which were routed elsewhere.
- **[CNCF charter guidance](https://contribute.cncf.io/maintainers/governance/charter/)**
  — supports a charter's *substance* but not the seed template's claim that it
  belongs "in a single place, kept stable": the page says charters "take many
  different forms", that this content is "often found within the governance
  documents or project READMEs", and that they are "living documents that should
  be expected to change over time". It gives no guidance on governing charter
  changes. The single-page, rarely-revised form is this project's own choice.

## Open questions

| Question | Recommended default | Owner | Decide by |
| --- | --- | --- | --- |
| Which open-source licence applies? | The charter states no licence. Selection is tracked in `adoptable-reference-implementation`. | eugenelim | Before any public release |

## Follow-on artifacts

- **`docs/CHARTER.md`** — replace the placeholder with the text under *Proposal*.
- **`AGENTS.md` § Project overview** — replace `<project-name>` and the
  one-line-description placeholder.

No ADR follows. A charter records what the project believes; the architecture
decisions it enables are captured once that design is signed off.
