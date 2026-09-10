# Evidence-Backed Fund and ETF Diligence

- **Status:** Draft
- **Kind:** outcome

> **Not authorized to build.** This intent records a direction, not a
> commitment. Its outcome is outside the ratified charter, which states in
> § Mission, § Domain and § Scope that the demonstration domain is
> *public-company* diligence. Nothing here may be sliced, specified, or built
> until an RFC amends that. Recorded 2026-09-10 so the reasoning survives; see
> § Projection for the route.

## Outcome

A user can ask what materially changed about a managed fund or ETF as of a
specified date and receive a structured analysis, in the same evidence-backed
form the company domain already produces.

*Falsifying observation:* a request naming a fund in the covered tier and an
as-of date that yields no structured analysis. Producing nothing is a failure,
not a pass.

Two phases, ordered because they carry very different governance costs:

1. **Changes disclosed in the fund's own periodic filings are covered, and the
   result stated** — strategy and objective language, fees and expenses, and
   reported concentration and turnover. This is the entity-level phase.
   *Falsified by:* an analysis silent on the fund's own filed changes — neither
   describing a change, nor stating explicitly that the compared filings
   disclose none, nor stating that no comparable prior filing exists.
2. **The fund's reported holdings, and what changed in them between two
   reported dates, are covered and the result stated.** This is the
   look-through phase.
   *Falsified by:* a presented holdings claim that does not resolve to the
   filing disclosing it, or an analysis claiming look-through coverage while
   silent on change between the two reported dates.

Phase 1 is an entity-level analysis and does **not** engage
[`evidence-backed-company-diligence.md`](evidence-backed-company-diligence.md)
§ Excluded's bar on multi-company and portfolio-level analysis: one fund, one
analysis, one filer. Phase 2 does engage it directly, which is why the two are
separated here rather than stated as one outcome.

Coverage is required; a *finding* is not. A fund whose strategy language did not
change, and a newly launched fund with no comparable prior filing, must both
yield a passing analysis — manufacturing a change to satisfy the outcome would
violate [`docs/CHARTER.md`](../../CHARTER.md) principle 1.

## Boundary

Ratification rules, the candidate list, and the settle order for the six
foundation intents are stated once in [`README.md`](README.md). This intent is
not one of the six; it carries no ratified constraint of its own, and its scope
below is ordinary design surface with no owner ratification behind it.

### In scope

- The fund and ETF domain as a **second demonstration domain**, reusing the
  contracts the foundation intents already own rather than defining new ones.
- The source tier that fund evidence begins from, as an extension of the
  ratified company tier rather than a replacement for it.
- Whether a fund analysis reuses the company workflow or requires its own.

### Excluded

- Any change to what the six Accepted foundation intents own. This intent
  consumes their contracts; it does not redefine evidence, citation, context,
  policy, runtime, or presentation.
- Fund selection, ranking, comparison between funds, or recommendation. Those
  are advice-shaped, and [`docs/CHARTER.md`](../../CHARTER.md) § Scope excludes
  investment advice and price-target output.
- Displacing the company domain. The MVP ships company-only; this is additive
  and later.

## Owner

eugenelim — decides whether this domain is pursued at all, and by what route.

## Unresolved questions

- **Does the charter's own non-goal forbid this outright?** § Scope states the
  project "does not genericize its domain to serve more use cases. The
  specificity is what makes the patterns legible." A second demonstration
  domain is arguably what that clause refuses. The counter-argument is that a
  pattern demonstrated twice is better evidence of portability than one
  demonstrated once — which is
  [`adoptable-reference-implementation.md`](adoptable-reference-implementation.md)'s
  concern, not this intent's to settle. This question is prior to all others
  below: a *no* here ends the intent.
- Which SEC forms constitute the fund source tier? N-PORT, N-CSR, N-CEN and
  485BPOS prospectus amendments are the working assumption, **unverified** —
  no source has been checked, and the list must be confirmed before anything
  ratifies on it. The ratified company constraint names "domestic SEC periodic
  filings", which fund filings may already satisfy without amendment.
- Must the charter amendment be drafted wide enough for phase 2 at the time it
  is written, so look-through does not require a second RFC?
- Does phase 2 require amending
  [`evidence-backed-company-diligence.md`](evidence-backed-company-diligence.md)
  § Excluded, or is look-through a distinct outcome under a distinct owner?
  That intent is `Accepted`; either route returns it to `Draft`.
- Does the project name change? "Company Intelligence Desk" encodes the
  company domain in the repository name, the charter, and this directory's
  filenames.
- Is a fund analysis one entity or many, for the purposes of context scoping
  and the evidence manifest?
- How much of the company workflow is reusable, and what does the answer say
  about how portable the patterns actually are?

## Projection

**Depends on:** the six Accepted foundation intents, whose contracts this
consumes unchanged — evidence and citation, context scoping, runtime and
identity, policy and observability, presentation, and the legibility bar.

**Next step.** An RFC amending [`docs/CHARTER.md`](../../CHARTER.md) § Mission,
§ Domain and § Scope. `CONVENTIONS.md` § 1 reserves charter mission and scope to
the RFC route, and the charter's own header states that changes to it go through
an RFC. Until that RFC is `Accepted`, this intent is not buildable and no spec
may be cut against it.

Settling this intent is therefore not a shaping review in the first instance: it
is an owner decision on the first unresolved question above, then an RFC.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r1 — created to record the fund and ETF direction without reopening
  the ratified charter, the six Accepted intents, or the Ready delivery brief;
  two phases separated because only the second engages the portfolio-level
  exclusion, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination. The direction is authorized to be
  *recorded*; it is not authorized to be built.
