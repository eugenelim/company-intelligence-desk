# Inspectable multi-agent diligence — design effort

**STATUS: PARTIALLY BUILT.** The runtime design is Accepted and its Phase 1
walking skeleton is built. The Phase 2 MVP and later phases are not built; the
observability/evaluation and experience/presentation companions remain Draft.

[`../README.md`](../README.md) § What is built is the current
map. This index records the mixed lifecycle inside the design set; each design
document remains the source for its own status.

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
  — delivery brief. **Executing**, with the walking-skeleton specs shipped and
  mapped to slice 1; later slices remain unmaterialized.
- The six foundation intents in [`docs/product/intents/`](../../product/intents/),
  **all Accepted**. They are the normative statement of what the system must
  achieve; this design proposes how.

## Ratification state

- [`runtime-architecture.md`](runtime-architecture.md) is **Accepted**, ratified
  2026-09-18 with its *Accepted limits* open. Its Phase 0 spikes are complete,
  and [`docs/adr/`](../../adr/) holds the accepted decisions produced while the
  design and walking skeleton were built.
- [`observability-and-evaluation.md`](observability-and-evaluation.md) and
  [`experience-and-presentation.md`](experience-and-presentation.md) remain
  **Draft**, revision c3. Their contracts are not ratified.
- The observability companion's producer-tuple edit is present in the runtime
  design as `fetch_adapter` and `model_adapter`. Its never-served-content edit
  is present as the no-reasoning-storage invariant. The requested
  zero-unresolved-claims wording edit remains open: the runtime Goals section
  still calls it a release gate rather than a per-run pre-release check.
