# Evidence-Backed Company Diligence

- **Status:** Accepted
- **Kind:** outcome

## Outcome

A user can ask what materially changed at a public company in the covered tier
as of a specified date and receive a structured analysis.

*Falsifying observation:* a request naming a company in the covered tier and an
as-of date that yields no structured analysis. Producing nothing is a failure,
not a pass.

Four sub-results, each independently verifiable:

1. **At least one deterministic financial calculation is reported.** The initial
   demonstration uses the quarterly net-sales year-over-year percentage from the
   canonical filing named under § In scope. The broader covered-tier assumption —
   every periodic filing in the selected source hierarchy carries computable
   figures — remains unproved; a filing without the required facts fails rather
   than manufacturing a calculation or falling back to another source. On that
   assumption, and unlike its siblings, this sub-result needs no
   coverage-without-finding escape.
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
   not from that rule. A *material claim* is any factual claim published in a
   user-facing memo or evidence manifest. Schema labels, field names,
   identifiers, and fixed headings are structural rather than claims. This is
   the owner-set reading consumed by
   [`scoped-context-and-evidence.md`](scoped-context-and-evidence.md) § Outcome.
   This intent narrows the evidence target to
   *public* sources — its own scope decision for the initial tier, not an owner
   ratification: the confirmed constraint says evidence *begins with* official
   public sources, which is a starting point rather than a ceiling. *Falsified by:* a published claim with no link
   resolving to public evidence or to deterministic calculation lineage.

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

**Covered tier**, as § Outcome uses it, means the set of issuers filing in that
source tier. The ratified constraint names a tier of *sources*; deriving the
corresponding set of *companies* from it is this intent's own definition, not
part of what the owner ratified.

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

The initial demonstration is deliberately narrower than the whole covered tier:

- Apple Inc. Form 10-Q filed 2026-07-31, accession
  `0000320193-26-000020`, is the canonical company and filing set; the as-of
  date is 2026-07-31.
- Quarterly consolidated net-sales year-over-year percentage is the initial
  deterministic calculation.
- SEC submission metadata plus the selected archived primary Inline XBRL filing
  is the minimum public-source hierarchy. Missing, conflicting, or ambiguous
  required facts fail closed; no fallback source is admitted.

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

- How should a restatement be surfaced to a reader comparing periods? This is
  the domain question; its storage counterpart is the next bullet.
- How are amended filings represented in storage? *Proposed in `runtime-architecture.md`
  § Context, evidence, and reproducibility; settled by the **2026-09-18 owner sign-off** recorded in `runtime-architecture.md` § Sign-off.*

## Projection

**Depends on:** `scoped-context-and-evidence` (evidence and citation contract),
`portable-identity-first-runtime` (execution topology).

**Feeds:** `multi-workspace-inspectable-experience` (the domain artifacts its
surfaces present).

**Settled projection to `scoped-context-and-evidence`** — not a settle-order
edge, and deliberately not a `Feeds:` entry, because asserting one in both
directions would contradict README § 3's ordering of scoped before this intent.
That intent's labelled interim reading now cites the material-claim definition
owned here. No material-claim decision remains open between the two intents.

**Next step.** The accepted architecture owns the system responsibilities,
deterministic-versus-agentic split, source pipeline, and unsupported-claim
enforcement. The first MVP calculation slice materializes the initial
deterministic calculation and publication; later domain outcomes remain with
the MVP brief's unmaterialized slices.

The candidate agent roles named during inception — research coordinator,
filing-change analyst, fundamentals analyst, positive-case analyst,
skeptical-case analyst, evidence auditor, report composer — remain inception
context. Slice 2 assigns ingestion, its calculation, claim linking, and memo
composition to deterministic code and creates none of those agent roles.
Whether later slices need any named role remains open and is settled when the
slice that needs it is cut.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r16 — the initial fixture, calculation, public-source hierarchy,
  and material-claim reading settled for the first published-analysis slice;
  the broader covered-tier computability assumption remains explicit,
  2026-10-02
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
