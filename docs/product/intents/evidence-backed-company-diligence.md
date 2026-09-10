# Evidence-Backed Company Diligence

- **Status:** Draft
- **Kind:** outcome

## Outcome

A user can ask what materially changed at a public company as of a specified
date and receive a structured analysis in which no published claim lacks a
resolvable link to public evidence or to deterministic calculation lineage.

The result is a research aid, not an assurance product.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md).

### Confirmed constraints

- Evidence begins with official public sources, with domestic SEC periodic
  filings as the initial source tier.

### In scope

- One company and one analysis at a time.
- Comparison of a current reporting period against prior periods.
- Filing-language change analysis.
- Deterministic financial calculations.
- A memo that presents both a supporting and a challenging reading of the same
  evidence set.
- Explicitly identified unresolved questions.
- Two user-facing deliverables: a human-readable research memo and a
  machine-readable evidence manifest.

The *definition* of a citation, of evidence lineage, and of what makes a claim
supported is owned by [`scoped-context-and-evidence.md`](scoped-context-and-evidence.md).
This intent consumes that contract and does not define it.

### Excluded

- Investment advice, trading actions, portfolio construction, and price
  targets.
- Real-time or intraday market data and price series.
- Foreign private issuers and private companies.
- Redistribution of private, licensed, or paid research data.
- Multi-company and portfolio-level analysis.

## Owner

eugenelim — decides domain scope for the diligence surface.

## Unresolved questions

- Which company and filing set should be the canonical demonstration fixture?
- What constitutes a "material claim" requiring evidence? This definition is
  load-bearing for the traceability guarantee in
  [`scoped-context-and-evidence.md`](scoped-context-and-evidence.md); it is
  resolved here and cited there.
- Which financial calculations belong in the initial demonstration?
- What is the minimum viable public-source hierarchy?
- How should amended or restated filings be represented?

## Projection

**Depends on:** `scoped-context-and-evidence` (evidence and citation contract),
`portable-identity-first-runtime` (execution topology).

**Feeds:** `multi-workspace-inspectable-experience` (the domain artifacts its
surfaces present).

Use `architect-design` to determine the system responsibilities, deterministic
versus agentic boundaries, agent patterns, source pipeline, and publication
workflow — including where the "no unsupported published claim" property is
enforced.

The candidate agent roles named during inception — research coordinator,
filing-change analyst, fundamentals analyst, positive-case analyst,
skeptical-case analyst, evidence auditor, report composer — are inception
context only. `architect-design` must pressure-test whether each should be an
agent, a tool, a workflow node, or a deterministic service.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r4 — constraint set ratified to 14, 2026-09-09
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
