# Evidence-Backed Company Diligence

- **Status:** Draft
- **Kind:** outcome

## Outcome

A user can ask what materially changed at a public company as of a specified
date and receive a structured analysis.

*Falsifying observation:* a request naming a company in the covered tier and an
as-of date that yields no structured analysis. Producing nothing is a failure,
not a pass.

Four sub-results, each independently verifiable:

1. **At least one deterministic financial calculation is reported.** Every
   periodic filing in the covered tier carries computable figures, so unlike its
   siblings this sub-result needs no coverage-without-finding escape.
   *Falsified by:* an analysis reporting no deterministic financial
   calculation.
2. **Filing-language comparison is covered, and its result stated.** The result
   may be a described change, an explicit finding of no material change, or an
   explicit statement that no comparable prior period exists.
   *Falsified by:* an analysis that is silent on filing-language comparison.
3. **Opposed readings of the same evidence set are covered, and the result
   stated.** The result may be a presented supporting-and-challenging pair, or
   an explicit statement that the evidence set supports no challenging reading,
   with its reason.
   *Falsified by:* an analysis that is silent on opposed readings — neither
   presenting a pair standing in supporting-versus-challenging opposition on a
   single evidence set, nor stating that the evidence supports none.
4. **No published claim lacks a resolvable link** to public evidence or to
   deterministic calculation lineage. The publication-blocking rule and both
   resolution targets are ratified in [`docs/CHARTER.md`](../../CHARTER.md)
   principle 1. Its *Applied:* rule states the block without qualification; the
   scoping to *material* claims comes from the principle's normative sentence,
   not from that rule. pending the
   material-claim question below, *published claim* is the standing interim
   reading. This intent narrows the evidence target to
   *public* sources — its own scope decision for the initial tier, not an owner
   ratification: the confirmed constraint says evidence *begins with* official
   public sources, which is a starting point rather than a ceiling. *Falsified by:* a published claim with no resolvable
   link.

Coverage is required; a *finding* is not. A company whose filing language did
not materially change, and a first-time filer with no prior period, must both
yield a passing analysis — manufacturing a change to satisfy the outcome would
violate charter principle 1.

The result is a research aid, not an assurance product.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md).

### Confirmed constraints

- Evidence begins with official public sources, with domestic SEC periodic
  filings as the initial source tier.

### In scope

- One company and one analysis at a time, including a first-time filer with no
  prior periodic filing in the covered tier.
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
  the domain question; its storage counterpart is the next bullet.
- How are amended filings represented in storage? *Proposed in `design-doc.md`
  § Context, evidence, and reproducibility; open until owner sign-off.*

## Projection

**Depends on:** `scoped-context-and-evidence` (evidence and citation contract),
`portable-identity-first-runtime` (execution topology).

**Feeds:** `multi-workspace-inspectable-experience` (the domain artifacts its
surfaces present).

**Outstanding obligation to `scoped-context-and-evidence`** — not a settle-order
edge, and deliberately not a `Feeds:` entry, because asserting one in both
directions would contradict README § 3's ordering of scoped before this intent.
That intent was accepted on a labelled interim reading standing in for the
material-claim definition owned here. Discharging it is a documentation act, not
a design or slicing product: this intent states the definition, and
`scoped-context-and-evidence` replaces its interim reading with a citation to
it. Owner: eugenelim; settled when the material-claim question below is answered
and both files are updated in the same change.

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
roles. Owner: eugenelim; settled by the slicing pass at
`author-delivery-brief continue`.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r13 — the outcome headline given the falsifying observation it
  lacked, so a system that produces no analysis at all is no longer unfalsified
  by every criterion in the section; sub-result 1's absent escape grounded rather
  than left unexplained; the material-claim scoping attributed to principle 1's
  normative sentence rather than to its unqualified *Applied:* rule, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
