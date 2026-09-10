# Inspectable multi-agent diligence — design effort

**STATUS: PLANNED**

Nothing described in this folder is built. `docs/architecture/` otherwise holds
current state; this subtree is admitted under the designed-but-unbuilt rule in
[`docs/CONVENTIONS.md`](../../CONVENTIONS.md) § 5a, which requires this marker
and a link to the governing decision.

## Governing decision

No ratified decision governs this design yet. The decisions it depends on are:

- [`RFC-0001`](../../rfc/0001-initial-project-charter.md) — initial project
  charter. **Draft.** The mission, scope, and principles this design is
  anchored to are proposed, not ratified.
- [`inspectable-diligence-mvp`](../../product/briefs/inspectable-diligence-mvp.md)
  — delivery brief. **Draft.**
- The six foundation intents in [`docs/product/intents/`](../../product/intents/).
  All **Draft**.

This design produces ADR-worthy decisions; none has been recorded yet. Until
those ADRs exist and the charter is ratified, treat this folder as a proposal
under review.

## Contents

| File | What it is |
| --- | --- |
| [`design-doc.md`](design-doc.md) | The design proposal — ownership split, execution planes, injection defence, identity and authorization, trust boundaries, alternatives, risks, rollout. Revision `r4`. |

Its evidence base is
[`docs/product/research/prompt-injection-defence-survey.md`](../../product/research/prompt-injection-defence-survey.md),
an applied-mode survey with per-finding confidence ratings.

## Reading order

Start with the design doc's TL;DR and Context. The **four grounded facts** in
Context are load-bearing — the proposal does not make sense without them, and one
of them (structural defences at `[moderate]`, author-evaluated) is the reason the
security posture is stated as an empirical bet rather than a solved problem.

## Outstanding before ratification

- **Two RFC-0001 principles need amendment.** Principle 7 (reproducibility →
  auditable replay) and principle 3 (publication → approval of flagged output).
  Both overclaim relative to what this design delivers. Owner: eugenelim.
- **Four Phase 0 spikes** gate ratification; they produce evidence, not code.
- **Round 4 of independent architecture review** is pending on `r4`.
