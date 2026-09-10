# Inspectable multi-agent diligence — design effort

**STATUS: PLANNED**

Nothing described in this folder is built. `docs/architecture/` otherwise holds
current state; this subtree is admitted under the designed-but-unbuilt rule in
[`docs/CONVENTIONS.md`](../../CONVENTIONS.md) § 5a, which requires this marker
and a link to the governing decision.

## What this design is

A governed multi-agent application, demonstrated through evidence-backed
public-company diligence. The engineering interest is not the diligence output —
it is that every part of how an answer was produced is open to inspection: the
workflow, the evidence, the context each step received, the policies applied,
the verification, and where a human retained authority.

If you are evaluating these patterns for your own system, the four grounded
facts in [`runtime-architecture.md`](runtime-architecture.md) § Context are the
place to start. They are load-bearing: the proposal does not make sense without
them, and one of them — structural injection defences holding at `[moderate]`,
self-evaluated confidence — is why the security posture is stated as an
empirical bet rather than a solved problem.

## Contents

| File | What it covers |
| --- | --- |
| [`runtime-architecture.md`](runtime-architecture.md) | Execution topology, data ownership, identity and authorization, injection defence, and the human approval gate. Defers four concerns to the two companions below. |
| [`observability-and-evaluation.md`](observability-and-evaluation.md) | The telemetry boundary, redaction on both egress paths, payload inlining, evaluation architecture, fixture versioning, and release gates. |
| [`experience-and-presentation.md`](experience-and-presentation.md) | The UI/API presentation contract, workspace information architecture, Storybook's role, and the approval surface. |

Evidence base:
[`prompt-injection-defence-survey.md`](../../product/research/prompt-injection-defence-survey.md),
an applied-mode survey with per-finding confidence ratings, and
[`otel-genai-conventions-fact-check.md`](../../product/research/otel-genai-conventions-fact-check.md)
for the instrumentation standard.

## Reading order

1. `runtime-architecture.md` — TL;DR, then Context. Read *Known at ship* before
   forming a view; it records five gaps the design ships with rather than
   resolves.
2. Either companion, depending on what you came for. They are independent of
   each other except at two seams: payload inlining, which is what lets the
   event stream be rendered directly, and the guarded/streamable split, which
   decides what the UI may show and when.

## What governs this design

- [`RFC-0001`](../../rfc/0001-initial-project-charter.md) — initial project
  charter. **Accepted 2026-09-10.** [`docs/CHARTER.md`](../../CHARTER.md)
  carries the ratified mission, scope, and principles this design is anchored
  to, including the two principles this design required amending.
- [`inspectable-diligence-mvp`](../../product/briefs/inspectable-diligence-mvp.md)
  — delivery brief. **Ready**, with a confirmed four-slice delivery shape and no
  specs cut.
- The six foundation intents in [`docs/product/intents/`](../../product/intents/),
  **all Accepted**. They are the normative statement of what the system must
  achieve; this design proposes how.

## Outstanding before ratification

- **Owner sign-off on all three documents.** None is ratified.
- **Phase 0 spikes**, in `runtime-architecture.md` § Rollout: four falsifiable
  hypotheses and two executable privilege tests. They produce evidence, not
  product, and they gate ratification.
- **Three edits to `runtime-architecture.md`** identified by the observability
  companion and recorded in its § Required parent edits — an adapter field in
  the producer tuple, the wording of the zero-unresolved-claims gate, and a
  statement of where never-served content is stored.
- **No ADRs exist yet.** This design produces several ADR-worthy decisions —
  the ownership split, structural injection defence, derived-and-attenuated
  authority, the rejection of detection, and Postgres over a dedicated queue.
  Until they are recorded and sign-off lands, treat this folder as a proposal
  under review.
