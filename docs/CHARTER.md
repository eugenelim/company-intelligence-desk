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
