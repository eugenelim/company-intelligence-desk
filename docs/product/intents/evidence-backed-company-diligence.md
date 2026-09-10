# Evidence-Backed Company Diligence

- **Status:** Draft
- **Kind:** outcome

## Outcome

A user can ask what materially changed at a public company as of a specified
date and receive a structured analysis that reports at least one deterministic
financial calculation, performs a filing-language comparison and states its
result — including an explicit finding of no material change — and presents both
a supporting and a challenging reading of the same evidence, in which no
published claim lacks a resolvable link to public evidence or to deterministic
calculation lineage.

Coverage is required; a *finding* is not. A company whose filing language did
not materially change must still yield a passing analysis, and manufacturing a
change to satisfy the outcome would violate charter principle 1.

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

- Real-time or intraday market data and price series.
- Foreign private issuers and private companies.
- Multi-company and portfolio-level analysis.

Investment advice, trading actions, price targets, and redistribution of
restricted research data are excluded by [`docs/CHARTER.md`](../../CHARTER.md)
§ Scope and are not restated here.

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
- How should a restatement be surfaced to a reader comparing periods? This is
  the domain half and remains open here.
- How are amended filings represented in storage? *Proposed in `design-doc.md`
  § Context, evidence, and reproducibility; open until owner sign-off.*

## Projection

**Depends on:** `scoped-context-and-evidence` (evidence and citation contract),
`portable-identity-first-runtime` (execution topology).

**Feeds:** `multi-workspace-inspectable-experience` (the domain artifacts its
surfaces present).

**Next step.** `architect-design` has run: `design-doc.md` proposes the system
responsibilities, the deterministic-versus-agentic split, the source pipeline,
and where the no-unsupported-claim property is enforced. It awaits owner
sign-off. Slicing this outcome into buildable work happens at
`author-delivery-brief continue`, not in another architecture run.

The candidate agent roles named during inception — research coordinator,
filing-change analyst, fundamentals analyst, positive-case analyst,
skeptical-case analyst, evidence auditor, report composer — remain inception
context. Whether each should be an agent, a tool, a workflow node, or a
deterministic service is **still open**: the design settles the
deterministic-versus-agentic boundary in principle but does not assign these
roles. Owner: eugenelim.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r6 — positive requirement restated as coverage rather than finding,
  after the earlier wording proved unsatisfiable for a company whose filing
  language did not change, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
