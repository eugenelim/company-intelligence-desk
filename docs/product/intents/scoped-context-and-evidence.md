# Scoped Context and Evidence

- **Status:** Accepted
- **Kind:** outcome

## Outcome

Context supplied to any agent or workflow step is explicitly bounded and
reproducible, and every material output can be traced to immutable evidence, an
explicit temporal scope, and calculation lineage.

Two observations falsify this: a step that receives material not present in its
declared scope, and a declared scope that resolves to a different *set of
retrievable evidence* on re-resolution while its evidence snapshot is held fixed.

A differing per-step *selection* on re-run is **not** a falsifier. Reproducibility
meaning replay rather than re-execution is ratified in
[`docs/CHARTER.md`](../../CHARTER.md) principle 7; what this intent adds is the
refinement that the snapshot pins the *universe of retrievable evidence*, not
which of it a step chooses.

"Material" is defined by
[`evidence-backed-company-diligence.md`](evidence-backed-company-diligence.md)'s
open question on material claims. Until that resolves, read it as: any claim
surfaced in a published artifact. This is an assumption, not a settled scope.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md).

### Confirmed constraints

- A context service is an explicit system capability rather than merely a chat
  transcript or an unscoped vector store.

### In scope

- Primary evidence kept distinct from mutable interpretations and summaries.
- Versioned, inspectable source manifests and context packages.
- Prevention of later evidence silently entering historical as-of analyses.

This intent is the **single owner of the evidence and citation contract** —
what a citation is, how lineage is represented, and what makes a claim
supported. `evidence-backed-company-diligence` consumes that contract for its
deliverables; `governed-observable-and-evaluable-operation` consumes it for
release checks. Neither redefines it.

This intent is in turn bound by the **untrusted-content boundary** owned by
[`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md),
which constrains what a context package may hand a component holding tool
authority, and in what form. Context assembly conforms to it; it is not defined
here.

### Excluded

- Automatic exposure of one agent's scratch material to every other agent.
- Presentation decisions about how context appears on screen — those belong to
  [`multi-workspace-inspectable-experience.md`](multi-workspace-inspectable-experience.md).

## Owner

eugenelim — decides the context and evidence contract.

## Unresolved questions

- Which data model separates evidence, findings, calculations, memories, and
  workflow state?
- Which scoping dimensions are required? Inception candidates: workspace, run,
  agent, company, task, and as-of date. This list is a starting point, not a
  settled tuple.
- Which data should be immutable versus versioned? *Proposed in `runtime-architecture.md`
  § Context, evidence, and reproducibility; open until owner sign-off.*
- How does the context model relate to the chosen runtime's native session and
  memory primitives? *Proposed in `runtime-architecture.md` § Ownership split — the
  context service is an application capability, not ADK's SessionService; open
  until owner sign-off.*
- What retrieval model is required for the initial public filings?
- How are citation locators represented and verified, and do they survive
  evidence re-ingestion or re-indexing? *Proposed in `runtime-architecture.md` § Context,
  evidence, and reproducibility; open until owner sign-off.*
- What storage choices are sufficient without overbuilding? *Proposed in
  `runtime-architecture.md` § Structure and § Object store contract; open until owner
  sign-off.*
- How does the context model represent retention, and how does it conform to the
  tenancy boundary owned by
  [`portable-identity-first-runtime.md`](portable-identity-first-runtime.md) and
  the release and redaction rules owned by
  [`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md)?
  This intent conforms to those decisions; it does not make them.

## Projection

**Depends on:** `portable-identity-first-runtime` (runtime session and memory
primitives, tenancy boundary).

**Feeds:** `evidence-backed-company-diligence` (the citation contract its
deliverables rely on), `governed-observable-and-evaluable-operation` (what an
evidence check can assert), `multi-workspace-inspectable-experience` (what the
context and evidence surfaces have to render).

Settle this intent immediately after `portable-identity-first-runtime`; four
other intents inherit its contract.

**Next step.** Settled by owner sign-off on the architecture design, which
proposes context-service responsibilities, persistence boundaries, evidence
lineage, temporal rules, and retrieval contracts.

The retrieval model for the initial filing tier is not settled by that sign-off
and remains open here. Owner: eugenelim; settled by the delivery-brief slicing
pass at `author-delivery-brief continue`, which is where the first retrieval
workload is scoped.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r8 — replay scoping cited to its ratified origin in charter
  principle 7, keeping only this intent's refinement, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
