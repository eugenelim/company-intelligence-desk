# Brief: Inspectable diligence MVP

- **Slug:** `inspectable-diligence-mvp`
- **Received:** 2026-09-09
- **Owner:** eugenelim
- **Status:** Draft
- **Next processor:** `architect-design`

## Source

- Mode: repo-origin — synthesized from six Draft foundation intents in this
  repository, plus in-session inception input authorizing this brief.
- Revision: b2 — constraint delta resolved, 2026-09-09
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
- at least one filing-language change finding
- positive and skeptical interpretations over the same evidence package
- claim-level provenance
- evidence verification before publication
- a small multi-view React experience
- a separate API boundary
- a real ADK-to-Bedrock invocation using workload identity in the deployed path
- a scoped context package
- a guarded user-visible result
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

Ratified by the project owner. Architecture chooses how to satisfy these; it
does not get to reverse them.

- The system is containerized.
- The React UI is a separate deployable container from the API.
- The React UI supports multiple workspace views.
- Storybook is used for the shared React component system and executable UI
  scenarios.
- The production agent runtime uses Google ADK.
- The production ADK runtime is deployed on AWS.
- Bedrock access uses AWS workload identity without a static model API key.
- A context service is an explicit application capability.
- Public-company evidence is initially based on official public sources,
  beginning with SEC filings.
- Application-owned contracts should minimize unnecessary provider coupling.
- AWS services are introduced only where justified.
- The installed `iac-terraform` pack will implement reviewed deployment
  decisions later; it does not choose them now.
- Production agents must not receive unrestricted shell, network, or
  infrastructure access.

All thirteen are ratified. Three of them — the SEC-filings source tier, the
deployment-tooling sequencing boundary, and the production-agent privilege floor
— were initially absent from the intents' closed set; the owner ratified them on
2026-09-09, taking that set to **fourteen** (the fourteenth, portable
application-owned contracts, is ratified in the intents but expressed here as
"minimize unnecessary provider coupling"). The authoritative record is
[`../intents/README.md`](../intents/README.md) § 1.

### Candidate technologies — not ratified decisions

Each requires architecture review. None may be treated as chosen.

ECS Fargate · Application Load Balancer · API Gateway · server-sent events ·
PostgreSQL · S3-compatible object storage · NVIDIA NeMo Guardrails · Langfuse ·
OpenTelemetry · LiteLLM versus an application-owned Bedrock Converse adapter ·
Claude Code headless as a local development harness · PostgreSQL-backed workflow
durability versus a dedicated queue · hosted versus self-hosted LLM operations
tooling.

## Assumptions and risks

- **Assumption:** the six foundation intents are a sufficient and non-conflicting
  statement of the MVP. Three independent shaping-review passes support this;
  they have not been ratified by promotion to `Accepted`.
- **Risk:** the demonstration domain absorbs effort that the reference-implementation
  purpose needs. `adoptable-reference-implementation` exists to hold that line,
  but it is the least-developed of the six intents.
- **Risk:** the confirmed-constraint set fixes enough of the stack that
  `architect-design` has less room than the candidate list implies. If
  architecture finds a confirmed constraint unworkable, that is an owner
  decision, not an architecture decision.
- **Risk:** "a real ADK-to-Bedrock invocation using workload identity in the
  deployed path" makes the walking skeleton depend on live AWS. Contributors
  without AWS access need a defined alternative before this is buildable.
- **Risk:** the repository is not under version control. No inception artifact
  is currently recoverable if lost.

## Traceability — foundation intents

This brief synthesizes six Draft intents. Each remains the normative owner of
its outcome; this brief coordinates them.

| Intent | Contributes to this brief |
| --- | --- |
| [`portable-identity-first-runtime`](../intents/portable-identity-first-runtime.md) | Containerization, ADK-on-AWS, Bedrock workload identity, event transport, tenancy |
| [`scoped-context-and-evidence`](../intents/scoped-context-and-evidence.md) | Scoped context package, claim-level provenance, evidence verification |
| [`evidence-backed-company-diligence`](../intents/evidence-backed-company-diligence.md) | Company + as-of date, SEC filings, deterministic calculation, filing-change finding, dual interpretation |
| [`governed-observable-and-evaluable-operation`](../intents/governed-observable-and-evaluable-operation.md) | Guarded result, observable execution, evaluation receipt, policy outcomes |
| [`multi-workspace-inspectable-experience`](../intents/multi-workspace-inspectable-experience.md) | Multi-view React experience, separate API boundary, inspection surfaces |
| [`adoptable-reference-implementation`](../intents/adoptable-reference-implementation.md) | The legibility bar the whole slice is judged against |

## Governance references

- [`RFC-0001`](../../rfc/0001-initial-project-charter.md) — initial project
  charter. `Draft`. The charter this brief's value statement should anchor to
  does not yet exist in ratified form.

## Spec map

<!-- Empty by construction. Slices are cut at `author-delivery-brief continue`,
after `architect-design`, and only on a second explicit human confirmation. -->

_No slices. This brief is not dispatchable._

## Ready gaps

A later `author-delivery-brief continue` review must resolve these before
`Status: Ready`:

1. **Charter not ratified.** RFC-0001 is `Draft`; `docs/CHARTER.md` is still a
   seed placeholder. This brief's business-value statement has no ratified
   charter to anchor to.
2. ~~**Confirmed-constraint delta.**~~ **Resolved 2026-09-09** — the owner
   ratified all three; the intents' closed set is now fourteen and this brief
   agrees with it.
3. **Architecture unresolved.** Every architecture question in the six intents
   is open. `architect-design` runs next.
4. **No offline contributor path.** The MVP requires a real Bedrock invocation;
   the fallback for contributors without AWS access is an open question in
   `portable-identity-first-runtime`.
5. **Success metrics absent.** No measure of whether the reference
   implementation actually teaches anyone anything. Owned by
   `adoptable-reference-implementation`'s first open question.
