# Charter

> The foundational document for this project. One page, read whole.
> Covers what [CNCF's charter guidance](https://contribute.cncf.io/maintainers/governance/charter/)
> describes as a charter's substance — mission, scope, values and principles.
> Keeping that substance on a single page and revising it rarely is this
> project's choice; CNCF notes it is often distributed across governance docs and
> READMEs, and expected to evolve.

Changes to this file go through an RFC. The rest of the docs in this repo
are scaffolding around it; this file is the why.

**Shaping-phase exception, owner-authorized 2026-09-18.** While the executable
substrate's building blocks are being shaped, the owner may amend this file
directly, with each amendment recorded in § Amendments. The exception is
scoped and it expires: **it ends at Phase 2**, when the first user-facing
deployment exists, after which the RFC route resumes for mission, scope and
principles. It exists because the substrate's shape is changing faster than an
RFC cycle can ratify it, not because the charter matters less.

---

## Mission

Provide an inspectable, general-purpose **executable substrate** for governed
multi-agent applications — a runtime that hosts agents defined as data — made
real by an evidence-backed public-company diligence application built on it.

The substrate and the use case are not in tension and neither is decoration.
A substrate with no use case cannot be shown to work; a use case with no
substrate teaches nothing transferable. The diligence application exists to
keep the substrate honest.

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

The engineering domain also includes the substrate concerns that follow from
hosting agents as data: agent and integration registries, compile-time binding
of instructions, tools and credentials, and the governance those require —
authoring-time authority containment, per-integration credential scoping, and
the trust classification of arbitrary integration outputs.

The demonstration domain is public-company diligence. It is the **proving** use
case, not the boundary of what the substrate may host; it does not make this an
investment-advice service. Additional use cases are admissible where they
exercise substrate capabilities that diligence alone leaves untested.

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
- Retains an inspection record of what ran, on what evidence, and under whose
  authority.
- Provides a generic worker runtime and pool that hardcode nothing about any
  agent: instructions, configuration and integrations arrive as versioned data
  and are resolved at step start.
- Keeps the set of *integration kinds* closed and code-reviewed while letting
  the set of *integrations* grow as data — so the catalogue expands without
  new executable behaviour entering the worker.
- Serves as both a useful demonstration application and an engineering
  reference for other governed agentic systems.

What this project does **not** do:

- It does not provide investment advice.
- It does not autonomously trade securities or manage portfolios.
- It does not generate authoritative buy, sell, or price-target decisions.
- It does not genericize *ahead of* a use case. The substrate is general
  purpose by construction, but a capability is built when a real application
  needs it and not because a platform might. **Amended 2026-09-18** — this
  previously read *"It does not become a framework, library, or extractable
  SDK, and it does not genericize its domain to serve more use cases. The
  specificity is what makes the patterns legible."* See § Amendments.
- It does not execute agent-supplied or registry-supplied code. Integrations
  are data that *select* a reviewed first-party adapter from a closed set of
  kinds; introducing a new kind is a code change.
- It does not warrant that the security patterns it demonstrates are effective
  against a determined adaptive attacker. Their evidence base and its limits
  are recorded in the architecture documentation.
- It does not redistribute private, licensed, or paid research data.

Two disclaimers, which are not scope boundaries: model-generated analysis is
not guaranteed complete or correct, and nothing here removes human
accountability for consequential conclusions.

**Silence is not permission.** This list bounds *purpose*. Technology and
delivery commitments are ratified in `product/intents/`; check there before
assuming a direction is open. If the project is being asked to do something on
neither list, that is a signal to refine this section rather than drift.

**What the system is today.** It is built for a single operator. Any workspace or
grouping it exposes is an organizational scope with no isolation behind it: every
authenticated principal can read every run and its evidence. Supporting a second
principal requires isolation work that does not exist. Whether a workspace
*should* become a hard boundary is an open question owned by
`product/intents/portable-identity-first-runtime.md`, and this charter does not
answer it — but the current state is a fact an adopter must not have to infer.

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
differ from the requester is configurable and recorded, and defaults to
permitting self-approval. Changing that setting is necessary for a
multi-principal deployment and nowhere near sufficient — see *What the system
is today*.

### 4. Inspectability over magic

Users and maintainers should be able to inspect workflow state, evidence,
context scope, policy outcomes, evaluation results, and uncertainty without
exposing private chain-of-thought.

*Applied:* a completed run is auditable afterwards from its recorded evidence
alone, without re-running it.

### 5. Identity and least privilege over secret sprawl

Ambient workload identity is the default: components use bounded identities and
short-lived credentials, and receive only the permissions and network access
their responsibility requires. Where a ratified constraint forbids a static
credential outright, that prohibition stands; where none does, a static
credential is admitted only with its owner and rotation procedure recorded
before it is issued into any environment holding real data.

No runtime or agent identity may create or widen authority — its own or
another's. Within a run, delegated agent and tool authority never amplifies: it
is bounded by the human who initiated the work and by whatever delegated it.

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
- **What belongs where in `docs/`** is mapped in [`README.md`](README.md).
- **How work is done** lives in [`../AGENTS.md`](../AGENTS.md) § Development
  workflow, with the loop's rationale in [`CONVENTIONS.md`](CONVENTIONS.md).
- **Governance** — roles, decision-making, voting — would live in a
  `GOVERNANCE.md` if the project ever needs one. It does not exist; most small
  projects never need it, and governance ceremony a project does not need
  produces theater rather than clarity.

## The shape of this charter

Two departures from the default charter shape are authorized for this
repository by [RFC-0001](rfc/0001-initial-project-charter.md):

- **§ Domain exists at all.** A charter normally carries mission, scope and
  principles only. This one adds a domain section because the project has two
  domains a reader would otherwise conflate — the domain it is *about*
  (governed multi-agent applications) and the domain it *demonstrates through*
  (public-company diligence).
- **A principle may carry a short normative body.** The default shape is one
  sentence plus a one-sentence elaboration with a concrete example. A principle
  here may carry a short normative body where the rule genuinely does not
  compress into one sentence — a reserved-change rule or a least-privilege
  invariant, for instance. Prefer the single sentence; the body is the
  exception, not the shape.

Mission, scope, and foundational-principle changes are reserved to the RFC
route, **subject to the shaping-phase exception recorded at the top of this
file and expiring at Phase 2**. Wording, clarification, examples, typos, broken
links, and recording an accepted decision are normal pull requests regardless
of this file's pathname.

## When to revise

Revise this charter when:

- The mission has actually changed — rare, and usually a fork.
- Scope has shifted enough that PRs routinely land for things it doesn't cover.
- A principle has stopped resolving ties: it is being ignored, or it
  contradicts another in ways we haven't acknowledged.

Revise via RFC, except under the shaping-phase exception above, where the
owner may amend directly and **must** record the amendment in § Amendments.
Editing the charter directly *without recording it* is the single fastest way
to lose the trust this document is meant to build — the discipline the RFC
route provides is the written trail, and that part is not suspended.

## Amendments

Direct owner amendments made under the shaping-phase exception. Each records
what changed, when, and why, so that the absence of an RFC does not mean the
absence of a reason.

### 2026-09-18 — the project is an executable substrate

**Authorized by:** eugenelim (owner), in session, explicitly declining the RFC
route for the shaping phase.

**What changed.** The Mission now names a general-purpose executable substrate
with diligence as the application that makes it real. The Domain records the
substrate concerns that follow. Scope gains the generic runtime and the
closed-kind/open-catalogue rule. The exclusion on becoming *"a framework,
library, or extractable SDK"* is **removed** and replaced by a narrower one:
no genericizing ahead of a use case, and no executing code that arrives as
data.

**Why.** The worker runtime and pool were being designed to hardcode nothing —
agent instructions, configuration and integrations all resolved from versioned
data at step start. That *is* a general-purpose agent platform, and the
previous exclusion forbade one. The design and the charter had to be made to
agree, and the owner's decision was that the substrate is the point.

**What the removed exclusion was protecting, and how it is still protected.**
The old wording defended *legibility* — the worry that a genericized system
teaches nothing because nothing in it is concrete. That concern is real and
survives in two places: the retained "does not genericize ahead of a use case"
exclusion, and the substrate's own design, where agent definitions are
inspectable data rather than dispersed code. Legibility remains a satisfaction
condition of the architecture, not a tradeable attribute.

**What this amendment does not do.** It does not grant tenancy isolation, which
still does not exist; it does not move authority containment from spawn time to
authoring time; and it does not settle the trust class of prompts authored by
someone other than the operator. Those are the three governance gaps a
multi-author substrate needs and none is closed by this wording. They are
tracked in
[`worker-runtime.md`](architecture/pydantic-ai-worker-runtime/worker-runtime.md)
§ Responsibility decomposition.
