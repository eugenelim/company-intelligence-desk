# Brief: Inspectable diligence MVP

- **Slug:** `inspectable-diligence-mvp`
- **Received:** 2026-09-09
- **Owner:** eugenelim
- **Status:** Draft
- **Next processor:** `author-delivery-brief continue` — architecture has run

## Source

- Mode: repo-origin — synthesized from the six foundation intents in this
  repository, plus in-session inception input authorizing this brief.
- Revision: b5 — the hand-transcribed constraint block replaced by a citation to
  the index that owns it, after review found the copy had dropped *open-source*,
  hedged ratified *portable* contracts into "should minimize", scoped a
  constraint to a named pack, and mis-stated its own count; the filing-language
  scope item restated in the coverage-not-finding form its Accepted intent
  ratifies; the untrusted-content boundary added to scope and traceability;
  two wrong-owner attributions corrected, 2026-09-10
- Authority: user-authorized; the intents remain the normative statement of each
  outcome. This brief coordinates them and does not restate or supersede them.

## Outcome

Engineers evaluating how to build a governed multi-agent system have no
inspectable, production-shaped example to reason from. Published references are
either toy demonstrations that skip governance, or production systems whose
internals nobody outside the team can see.

This project answers that with a working research workbench: a user analyses one
public company as of an explicit date, and every part of how that answer was
produced — the workflow, the evidence, the context each step received, the
policies applied, the verification, the evaluation — is open to inspection.

The demonstration domain is public-company diligence, chosen because it forces
the hard parts to be real rather than simulated: mixed structured and
unstructured evidence, deterministic calculation alongside interpretation,
parallel specialist work, provenance and citation obligations, as-of-date
reproducibility, and consequences serious enough that human authority must be
preserved.

## Business value

An open-source, inspectable reference implementation showing engineers how to
build, operate, govern, and evaluate a production-shaped multi-agent
application.

The value is the *legibility* of the patterns, not the diligence output. A
correct system nobody can learn from does not satisfy this brief.

## Initial user outcome

A user can analyse one public company as of an explicit date, and then:

- observe a bounded multi-agent workflow as it runs
- review material financial and filing-language changes
- compare positive and skeptical interpretations of the same evidence
- inspect the evidence behind any material claim
- inspect the bounded context supplied to a given agent
- see verification and policy outcomes
- compare runs or reporting periods
- review evaluation results
- retain authority over consequential conclusions

## Scope / Non-goals

**In scope — the first usable vertical slice should eventually demonstrate:**

- one company or ticker, one explicit as-of date
- official public sources, beginning with SEC filings
- one current 10-Q or 10-K plus relevant prior-period evidence
- at least one deterministic financial calculation
- filing-language comparison covered and its result stated, in the
  coverage-not-finding form `evidence-backed-company-diligence` sub-result 2
  ratifies
- positive and skeptical interpretations over the same evidence package
- claim-level provenance
- evidence verification before publication
- a small multi-view React experience
- a separate API boundary
- a real ADK-to-Bedrock invocation using workload identity in the deployed path
- a scoped context package
- a guarded user-visible result
- the untrusted-content boundary, and adjudication of every user-authored prompt
  by a recorded policy decision before it causes a tool invocation, per
  `governed-observable-and-evaluable-operation`'s third outcome
- observable execution and a minimal evaluation receipt

**Non-goals:**

- Investment advice, autonomous trading, portfolio management, and buy/sell or
  price-target output.
- Any guarantee that model-generated analysis is complete or correct.
- Removing human accountability for consequential conclusions.
- Unrestricted browsing, shell execution, or infrastructure control for
  production agents.
- Redistribution of private, paid, licensed, or restricted research data.
- Becoming a universal agent platform.
- Core behaviour inseparable from one cloud, model provider, policy engine, or
  observability product.
- Multi-company or portfolio-level analysis in this slice.

## Appetite

This brief coordinates the whole MVP; it is not itself a delivery unit. The
appetite for the *first* slice is a walking skeleton that exercises real wiring
end to end, not a feature-complete workbench. Breadth is deliberately deferred:
if a capability can be demonstrated once rather than generally, demonstrate it
once.

Cutting the slice is not authorized by this brief. It happens at
`author-delivery-brief continue`, after architecture.

## Constraints

### Confirmed constraints

Fourteen constraints are ratified. The normative wording of each lives in its
owning intent's `### Confirmed constraints` block and nowhere else;
[`../intents/README.md`](../intents/README.md) § 1 indexes them and names the
owner. This brief cites that index rather than transcribing it — a hand-copy
drifts, and a drifted copy of an owner ratification is indistinguishable from an
author preference, which is what § 1 exists to prevent.

The handles, for orientation only — **not the constraints themselves**:

containerization · UI / API container separation · agent runtime · production
runtime host · model access and credential posture · AWS service justification
bar · UI framework · shared component system and its documentation · multiple
workspace views · context service as an explicit capability · open-source
reference implementation with portable contracts · production-agent privilege
floor · deployment tooling implements, does not decide · evidence source tier.

### Candidate technologies — not ratified decisions

Each requires architecture review. None may be treated as chosen. The
authoritative list is [`../intents/README.md`](../intents/README.md) § 1; it is
not restated here.

## Assumptions and risks

- **Assumption:** the six foundation intents are a sufficient and non-conflicting
  statement of the MVP. **All six are now `Accepted`**, each bound to a clean
  independent shaping review at a named revision. They remain living until the
  work under them ships.
- **Risk:** the demonstration domain absorbs effort that the reference-implementation
  purpose needs. `adoptable-reference-implementation` exists to hold that line,
  and it carries seven open questions — including which patterns this is a
  reference *for*, which its own outcome calls the first task.
- **Risk:** the confirmed-constraint set fixes enough of the stack that
  `architect-design` has less room than the candidate list implies. If
  architecture finds a confirmed constraint unworkable, that is an owner
  decision, not an architecture decision.
- **Risk:** two companion documents the architecture commissioned — *Observability
  and evaluation* and *Experience and presentation* — do not exist. They settle
  `governed-observable-and-evaluable-operation`'s cross-release outcome and
  `multi-workspace-inspectable-experience` entirely, so any slice depending on
  either is unbuildable until they are written.

## Traceability — foundation intents

This brief synthesizes six intents, all `Accepted`. Each remains the normative
owner of its outcome; this brief coordinates them.

| Intent | Contributes to this brief |
| --- | --- |
| [`portable-identity-first-runtime`](../intents/portable-identity-first-runtime.md) | Containerization, the separate API boundary, ADK-on-AWS, Bedrock workload identity, event transport, tenancy |
| [`scoped-context-and-evidence`](../intents/scoped-context-and-evidence.md) | Scoped context package, claim-level provenance, the evidence and citation contract |
| [`evidence-backed-company-diligence`](../intents/evidence-backed-company-diligence.md) | Company + as-of date, SEC filings, deterministic calculation, filing-language comparison, opposed readings |
| [`governed-observable-and-evaluable-operation`](../intents/governed-observable-and-evaluable-operation.md) | Guarded result, observable execution, evaluation receipt, policy outcomes, the untrusted-content boundary |
| [`multi-workspace-inspectable-experience`](../intents/multi-workspace-inspectable-experience.md) | Multi-view React experience, inspection surfaces |
| [`adoptable-reference-implementation`](../intents/adoptable-reference-implementation.md) | The legibility bar the whole slice is judged against |

## Governance references

- [`RFC-0001`](../../rfc/0001-initial-project-charter.md) — initial project
  charter. **Accepted 2026-09-10**; `docs/CHARTER.md` carries the ratified text
  this brief's business-value statement anchors to.

## Spec map

<!-- Empty by construction. Slices are cut at `author-delivery-brief continue`,
after `architect-design`, and only on a second explicit human confirmation. -->

_No slices. This brief is not dispatchable._

## Ready gaps

A later `author-delivery-brief continue` review must resolve these before
`Status: Ready`:

1. ~~**Charter not ratified.**~~ **Resolved 2026-09-10** — RFC-0001 accepted and
   `docs/CHARTER.md` ratified. The business-value statement now anchors to it.
2. ~~**Confirmed-constraint delta.**~~ **Resolved 2026-09-09** — the owner
   ratified all three; the closed set is fourteen, and this brief now cites the
   index that owns it rather than transcribing it.
3. **Architecture proposed, not signed off.** `architect-design` has run and
   produced a reviewed design at Draft; owner sign-off is outstanding, and four
   Phase 0 spikes gate its ratification.
4. **No offline contributor path — proposed, not settled.** The MVP requires a
   real Bedrock invocation. `design-doc.md` § Local development proposes
   recorded-fixture replay, substituting exactly the model adapter and the fetch
   adapter, which is the seam set `portable-identity-first-runtime` § Excluded
   names and closes. That intent's question stays open until owner sign-off.
5. **Success metrics absent.** No measure of whether the reference
   implementation actually teaches anyone anything. Owned by
   `adoptable-reference-implementation`'s second open question — "What must a
   reader be able to do after reading, and how would we know they can?"
