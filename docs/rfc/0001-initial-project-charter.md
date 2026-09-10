# RFC-0001: Initial Project Charter — Company Intelligence Desk

- **Status:** Draft
- **Author:** eugenelim
- **Approver:** eugenelim
- **Date opened:** 2026-09-09
- **Date closed:**
- **Decision weight:** standard
- **Revision:** r3 — 2026-09-09. r2 refined the charter text from the
  owner-supplied seed during the `init-project` pass. r3 amends two principles in
  response to architecture findings: principle 7's heading now reads *auditable
  replay* (the design delivers replay, not deterministic re-execution), and
  principle 3 narrows *publication* to *approval of flagged output* (a run passing
  all verification publishes automatically). Both amended in place rather than
  opening a second RFC, per `new-rfc` step 0. The RFC has never been circulated,
  so no `## Amendments` log applies yet.
- **Related:** the six Draft foundation intents under `docs/product/intents/`;
  the Draft delivery brief `docs/product/briefs/inspectable-diligence-mvp.md`,
  whose business-value statement anchors to this charter

## Reviewer brief

- **Decision:** Adopt the initial project charter for Company Intelligence Desk.
- **Recommended outcome:** accept
- **Change if accepted:**
  - Replace the seed placeholder in `docs/CHARTER.md` with the mission, domain,
    scope, and principles reproduced in full under *Proposal*.
  - No other file changes. No ADR, no architecture document, no code.
- **Affected surface:** `docs/CHARTER.md` only. That file is what contributors
  and agent sessions read to decide whether a request is in bounds, so its
  content changes behavior across every future session in this repository.
- **Stakes:** Reversible by a later RFC, but not cheaply — a charter that
  contributors have relied on for months costs trust to rewrite. Treat it as
  costly rather than one-way.
- **Review focus:** Does the "what this project does not do" list actually
  bound agent and contributor behavior, or does it leave the obvious
  over-reaches unnamed? Do the seven principles resolve a real disagreement, or
  are they slogans?
- **Not in scope:** Framework selection, agent roster, AWS service list,
  database choice, endpoint design, deployment topology. Those are
  `architect-design` outputs and become ADRs; putting them here would pre-empt
  an architecture pass that has not yet run.

## The ask

**Recommendation.** Adopt the charter exactly as reproduced below.

**Why now.** The repository has just taken the `core` and `governance-extras`
packs and is about to enter architecture shaping. `docs/CHARTER.md` is still the
unmodified seed placeholder: its mission reads `<replace with one sentence>` and
its scope bullets read `<bullet>`. Six foundation intents were drafted in the
same session and are registered as non-dispatchable pointers awaiting
`architect-design`. Those intents state what the project should achieve; nothing
yet states what the project *is*, or — more importantly — what it refuses to be.
An architecture pass that begins without a scope boundary will produce decisions
nobody can later test for fit.

| ID | Question | Recommendation | Why | Decide by | Reviewer action |
| --- | --- | --- | --- | --- | --- |
| D1 | Replace the placeholder `docs/CHARTER.md` with the proposed mission, domain, scope, and seven principles? | Yes — adopt as proposed | It is the only option that bounds scope without ratifying decisions `architect-design` has not made yet. | At RFC acceptance | Accept, or propose amendments to the text below |

## Problem & goals

`docs/CHARTER.md` currently contains the pack seed and no project-specific
content. Every contributor and every agent session therefore starts with no
statement of mission, no scope boundary, and no principles to resolve a tie.
The practical failure mode is not that someone writes the wrong code — it is
that nobody can say a request is out of bounds, because nothing is written down
that would make it so. A reference implementation whose scope drifts stops being
a reference for anything.

**Goals.**

- Give contributors and agents one short page that says what this project is,
  what it refuses to do, and which values break ties.
- Bound the scope *before* architecture shaping, so architectural options can be
  tested against a stated purpose rather than an implied one.
- Keep the page stable enough that it is rarely revised.

**Non-goals** — plausible things deliberately excluded, not merely bad outcomes:

- **Ratifying the technology stack.** The agent runtime, cloud services,
  storage engines, policy engine, and observability platform are genuine open
  questions carried by the foundation intents. A charter that named them would
  freeze decisions before the evidence to make them exists.
- **Describing current architecture.** None exists. `docs/architecture/` is the
  home for that when it does.
- **Naming agent roles or topology.** Whether the inception-named roles should
  be agents, tools, workflow nodes, or deterministic services is precisely what
  `architect-design` must pressure-test.
- **Establishing a governance process.** `docs/CONVENTIONS.md` and the RFC
  lifecycle already cover this repository's size. A `GOVERNANCE.md` is warranted
  only when roles and voting need writing down.

## Proposal

Replace `docs/CHARTER.md` in full with the following. The seed's structural
sections — *What's NOT in this charter* and *When to revise* — are preserved
because they are navigation, not project-specific content, and they route
readers to decisions, product state, architecture, and conventions.

The replacement happens **only after this RFC is accepted**. It has not been
applied.

---

```markdown
# Charter

> The foundational document for this project. One page, read whole.
> Modeled on the [CNCF project charter pattern](https://contribute.cncf.io/maintainers/governance/charter/):
> mission, scope, and principles in a single place, kept stable and short.

Changes to this file go through an RFC. The rest of the docs in this repo
are scaffolding around it; this file is the why.

---

## Mission

Provide an open-source, inspectable reference implementation of a governed
multi-agent application, demonstrated through evidence-backed public-company
diligence.

The project exists to make the important parts of an agentic system visible and
reviewable: what work was requested, which evidence and context were supplied,
which tools and policies applied, what conclusions were produced, how those
conclusions were verified, and where humans retained authority.

## Domain

Agentic application engineering and evidence-backed public-company research
using public sources.

The engineering domain includes:

- bounded multi-agent workflows
- human-agent interaction
- context and evidence management
- deterministic and agentic responsibility boundaries
- policy enforcement
- observability
- evaluation
- containerized development and deployment

The demonstration domain is public-company diligence. It is a reference use
case, not authorization to provide investment advice.

## Scope

What this project does:

- Provides a functioning research workbench demonstrating a governed
  multi-agent workflow.
- Produces public-company analysis scoped to an explicit as-of date.
- Makes workflow progress, evidence, context scope, interpretations,
  verification, policy outcomes, and evaluations inspectable.
- Combines deterministic software with agents where bounded interpretation,
  planning, or synthesis adds value.
- Preserves meaningful human review and intervention points.
- Provides a containerized local-development path and a production-shaped
  deployment path.
- Uses explicit application-owned contracts so infrastructure, model,
  guardrail, storage, and observability implementations can be replaced where
  practical.
- Serves as both a useful demonstration application and an engineering
  reference for other governed agentic systems.

What this project does **not** do:

- It does not provide investment advice.
- It does not autonomously trade securities or manage portfolios.
- It does not generate authoritative buy, sell, or price-target decisions.
- It does not guarantee that model-generated analysis is complete or correct.
- It does not remove human accountability for consequential conclusions.
- It does not provide unrestricted network browsing, shell execution, or
  infrastructure control to production agents.
- It does not redistribute private, paid, licensed, or restricted research
  data.
- It does not attempt to be a universal agent platform for every use case.
- It does not make core application behavior inseparable from one cloud, model
  provider, policy engine, or observability product.

## Principles

### 1. Evidence before assertion

Material claims must be traceable to identifiable evidence or deterministic
calculation lineage. Unsupported confidence is a defect.

### 2. Deterministic before agentic

Parsing, arithmetic, validation, authorization, policy invariants, and other
reliably computable behavior belong in deterministic code. Agents are used
where interpretation, planning, synthesis, or bounded choice adds value.

### 3. Human authority at consequential boundaries

The system may research, compare, explain, and recommend further inquiry.
Humans retain control over approval of flagged output, policy exceptions, and
consequential use.

### 4. Inspectability over magic

Users and maintainers should be able to inspect workflow state, evidence,
context scope, policy outcomes, evaluation results, and uncertainty without
exposing private chain-of-thought.

### 5. Identity and least privilege over secret sprawl

Workloads use bounded identities and short-lived credentials. Each component
receives only the permissions and network access required for its
responsibility.

### 6. Portability through explicit contracts

Application-owned interfaces separate domain behavior from model providers,
cloud services, policy engines, storage systems, observability products, and
deployment platforms.

### 7. Auditable replay and evaluation by construction

Runs are temporally scoped, versioned, observable, and testable. Provenance,
quality regressions, policy decisions, and unresolved uncertainty are visible
rather than hidden.

## What's NOT in this charter

To keep this file from becoming everything-and-the-kitchen-sink:

- **Decision history** lives in [`adr/`](adr/). The charter is what we
  believe; ADRs are the choices we made because of those beliefs.
- **Current product state** lives in [`product/`](product/). The charter
  is direction; product/ is where we are.
- **Current architecture state** lives in [`architecture/`](architecture/).
- **Conventions for how we work** live in [`CONVENTIONS.md`](CONVENTIONS.md).
- **Governance** (roles, decision-making processes, voting) lives in
  [`GOVERNANCE.md`](GOVERNANCE.md) if and when the project is large
  enough to need it. Most small/medium projects don't — a single
  maintainer or small group operating by consensus is fine, and forcing
  governance ceremony on a project that doesn't need it produces theater,
  not clarity.

## When to revise

Revise this charter when:

- The mission has actually changed (rare — usually means a fork).
- The scope has shifted enough that PRs are routinely landing for things
  the current scope doesn't cover.
- A principle has stopped resolving ties — it's being ignored, or it
  contradicts another principle in ways we haven't acknowledged.

Revise via RFC. Editing the charter directly without discussion is the
single fastest way to lose the trust this document is meant to build.
```

---

### Note on the added `## Domain` section

The seed template carries Mission, Scope, and Principles. This proposal adds a
short `## Domain` section between Mission and Scope. The reason is that this
project has *two* domains that a reader will otherwise conflate: the engineering
domain it is a reference for, and the demonstration domain it happens to use.
Without naming both, a reader reasonably concludes the project is a finance tool
that happens to use agents, when it is an agent-engineering reference that
happens to analyze filings. Reviewers who find the section redundant with Scope
should say so — merging it is a reasonable amendment.

## Options considered

The axis is *how much doctrine the charter carries*.

| Option | Trade-off | Assessment |
| --- | --- | --- |
| **Do nothing** — leave the seed placeholder | Zero effort; zero boundary. Nothing tells a contributor or agent that a request is out of scope, and architecture shaping proceeds against an implied purpose. | Rejected. Actively harmful in a repository about to take architecture work. |
| **Adopt as proposed** — mission, domain, scope in/out, seven principles, no technology | Bounds behavior and survives architecture shaping unchanged, because it commits to no technology an architecture pass could contradict. Costs one RFC cycle. | **Recommended.** |
| **Adopt an expanded charter** that also ratifies the stack (ADK, Bedrock, ECS Fargate, PostgreSQL, NeMo Guardrails, Langfuse) | Gives immediate clarity on the stack, at the price of settling by charter what has not been evaluated. Contradicts the CNCF pattern the template cites, and pre-empts `architect-design`. | Rejected. Those belong in ADRs after evaluation; the foundation intents deliberately hold them open as questions. |

## Risks & what would make this wrong

- **The "does not do" list is incomplete, and drift lands in the gap.**
  Likelihood: moderate — exclusion lists are always discovered, never designed.
  Mitigation: `docs/CONVENTIONS.md` §1 already frames the "does not" list as the
  signal to refine rather than drift, and the *When to revise* section names
  routine out-of-scope PRs as the trigger.
- **A principle fails to resolve a real tie.** Principles 1 and 2 could conflict
  in practice: an agent's interpretation may be the only available route to a
  claim that principle 1 wants evidence-linked. The charter does not rank them.
  Mitigation: the conflict surfaces in a specific ADR or spec review, which is
  the right altitude to resolve it; a charter that pre-resolves every tie is
  over-specified.
- **`Domain` reads as redundant with `Scope`.** Named above with a suggested
  amendment.
- **What would make this wrong:** if `architect-design` produces a design that
  the charter's scope excludes, one of the two is wrong. The proposal is built
  so that this can only happen at the level of *purpose*, not technology —
  which is the level at which the charter should win.

## Evidence & prior art

- `docs/CHARTER.md` (current) — seed placeholder; mission line 19 reads
  `<replace with one sentence>`, scope bullets read `<bullet>`. Confirms there
  is no adopter-authored content to overwrite.
- `docs/CHARTER.md` lines 7-8 — "Changes to this file go through an RFC."
- `docs/CONVENTIONS.md` §1 — charter mission, scope, and foundational-principle
  changes are reserved and take the strongest route the repository has. The file
  documents no initial-seed exception, which is why initial population takes the
  RFC route rather than a normal PR.
- [CNCF project charter pattern](https://contribute.cncf.io/maintainers/governance/charter/)
  — cited by the repository's own template; mission, scope, and principles in a
  single short page kept stable.
- The six Draft foundation intents under `docs/product/intents/` — each carries
  its technology questions as *unresolved questions* rather than settled
  choices, which is what makes a technology-free charter coherent with them.

## Open questions

| Question | Recommended default | Owner | Decide by |
| --- | --- | --- | --- |
| Should `## Domain` remain a separate section, or merge into `## Scope`? | Keep it separate; the two-domain confusion is real and cheap to prevent. | eugenelim | At RFC acceptance |

## Follow-on artifacts

Acceptance calls for exactly two edits, and no more:

- **`docs/CHARTER.md`** — replace the placeholder with the text under
  *Proposal*, through the repository's governed process. This is the RFC's whole
  substance.
- **`AGENTS.md` § Project overview** — replace the `<project-name>` and
  one-line-description placeholders with "Company Intelligence Desk" and the
  charter's mission sentence. A normal PR; it is derived from the charter, not
  reserved by it.

No ADR follows from this RFC. A charter records what the project believes; ADRs
record choices made because of those beliefs, and no such choice has been made
yet. Architecture decisions arrive after `architect-design` runs against the
six foundation intents.
