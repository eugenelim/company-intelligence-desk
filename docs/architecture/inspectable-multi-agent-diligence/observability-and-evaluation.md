# Observability and evaluation — companion to the diligence design

**Author(s):** eugenelim
**Status:** Draft — revision c1
**Last updated:** 2026-09-10
**Parent:** [`design-doc.md`](design-doc.md), whose § Scope commissions this
document and fixes its lane.
**Settles:** [`governed-observable-and-evaluable-operation`](../../product/intents/governed-observable-and-evaluable-operation.md)
second outcome (cross-release evaluability). Its first and third outcomes are
settled by owner sign-off on the parent, not here.

## TL;DR

Two planes, and only one of them is evidence. The **event log is the source of
truth**; **telemetry is diagnostic and disposable**. No free text crosses the
telemetry boundary — the same rule the parent applies at the quarantine
boundary, for the same reason. Release gates block on deterministic and
structural checks only; model-graded judgement never blocks, because the
evidence says graders lose under adaptive pressure. Cross-release comparability
rests on a content-addressed fixture set, constructed exactly like the parent's
evidence snapshot.

## Scope

**This document owns**, per the parent's § Scope deferral table:

| Concern | Settled in |
| --- | --- |
| Telemetry boundary | § The two planes |
| Redaction | § What may cross the telemetry boundary |
| Payload inlining | § Payload inlining |
| Evaluation architecture | § Three classes of evaluation |
| Fixture versioning | § Fixture sets and comparability |
| Release gates | § The release gate |

**This document does not own** the event envelope (specified in the parent,
because the stream is the parent's own interface), the policy decision point,
the injection defence, or what the user sees. The last is
[`experience-and-presentation.md`](experience-and-presentation.md).

**Reserved.** The criteria selecting output for *automatic publication* are
ratified in [`docs/CHARTER.md`](../../CHARTER.md) principle 3. This document
owns which checks flag output and what happens to flagged output. It does not
own, and must not change, the criteria for publishing without a human. Any
change to those takes the RFC route.

## The two planes

The intent excludes "LLM observability tooling as the workflow source of truth."
That exclusion is the whole design of this section.

**Plane 1 — the event log.** Append-only, in Postgres, per-run sequenced. It is
the substrate the parent names for observability. Every claim in the intent's
first outcome is answered from this plane plus the evidence store, and from
nothing else.

**Plane 2 — telemetry.** OpenTelemetry spans, metrics and logs, exported over
OTLP. Lossy by construction: sampled, subject to backpressure, and safe to drop.

**The falsifiable test that keeps them apart:** *delete the entire telemetry
backend and every audit claim in the intent's first outcome must still hold.* If
deleting it breaks reconstruction, something that belonged in the event log was
written only to telemetry, and the split has failed. This is a release check
(§ The release gate), not a principle to be remembered.

What goes where is decided by that test, not by convenience:

| Plane | Carries |
| --- | --- |
| Event log | Step boundaries, policy decisions and their outcomes, approval events, run lifecycle, evidence `snapshot_id`, the producer tuple, human intervention points |
| Telemetry | Latency, token counts, retry and deadlock-retry counts, claim contention, span structure, error class names, cache behaviour |

A signal may appear in both only if the telemetry copy is a *measure* and the
event-log copy is the *fact* — duration in telemetry, completion in the log.

## What may cross the telemetry boundary

Telemetry leaves the application boundary. The intent excludes "unredacted
intermediate agent content leaving an application boundary," and
[`docs/CHARTER.md`](../../CHARTER.md) principle 4 bounds inspection to exclude
private chain-of-thought.

**The rule: no free text crosses the telemetry boundary.**

Admitted: identifiers (`run_id`, `step_id`, `agent_role`, principal id),
content hashes, closed-vocabulary enumerations, numeric measures, error class
names, and tool *names*.

Refused: the user's prompt text, filing text, model output text, tool-call
argument *values*, evidence content, and report text. A tool call is recorded as
its name plus the hash of its arguments, never the arguments.

This is deliberately the same shape as the parent's quarantine rule — admitted
forms enumerated, everything else refused, decided by form rather than by reading
for sensitivity. A redactor that inspects content for sensitivity is a detector,
and § Three classes of evaluation records why this design does not trust
detectors with a boundary.

**It is enforced, not documented.** A test asserts that the OTLP exporter's
serialised output for a fixture run contains no string from the fixture's
evidence, prompt, or output text. That test blocks release.

## Payload inlining

The parent's envelope carries `payload_ref` — a reference to an immutable
object. This document sets when a payload may be carried inline instead.

**Inlining is admitted for exactly the forms that cross the quarantine
boundary**, plus identifiers and counts: typed scalars, closed-vocabulary
classifications, bounded identifiers. **Free prose is always a reference**,
never inlined, at any size.

Two consequences make this worth the constraint. Events stay bounded, so the
stream cannot be made to carry a filing. And the event stream can be rendered
without a per-payload redaction pass, because nothing inline can contain
content — which is what lets
[`experience-and-presentation.md`](experience-and-presentation.md) treat the
stream as directly renderable and fetch prose separately through the API.

## Three classes of evaluation

| Class | Example | Blocks release? |
| --- | --- | --- |
| **Deterministic** | Every published claim resolves to public evidence or calculation lineage; the arithmetic recomputes | **Yes** |
| **Structural / trajectory** | A `policy.decision` precedes every tool invocation; the step sequence is recoverable; required steps were visited | **Yes** |
| **Judgement** | Are the opposed readings genuinely opposed? Is the filing-language finding substantive? | **No — informational only** |

**Judgement evaluations never block a release, and that is a security position
rather than a quality compromise.** The parent's § Four grounded facts records
that detection-based defences were bypassed at above 50% attack success rate,
and that in-band detection "collapsed from near-zero to >90% success" under
adaptive pressure. A model-graded release gate is a detector standing between an
adversary and publication; making it blocking invites optimisation against it
and produces false confidence when it passes. Judgement evaluations are recorded,
trended, and read by a human — they are evidence about the system, not a control
on it.

This preserves the intent's own separation: whether a claim is *supported* is
owned by [`scoped-context-and-evidence`](../../product/intents/scoped-context-and-evidence.md),
and this document consumes that contract to decide what a release check may
assert. A deterministic check can assert resolution; only a human can assert
that an analysis is good.

## Fixture sets and comparability

**A fixture set is an immutable, content-addressed manifest**, constructed
exactly as the parent constructs an evidence snapshot:
`fixture_set_id = hash(sorted set of fixture content hashes)`. Amending a
fixture creates a *new* set; historical measurements never see it. The
construction is deliberately identical so a reader who has understood one
understands the other.

A quality measurement records
`{fixture_set_id, metric_definition_version, producer_tuple, app_image_digest}`.

**Divergent is not the same as incomparable, and conflating them would make the
cross-release outcome unsatisfiable.** The parent labels a re-run whose producer
tuple differs from the original **divergent**. A cross-release comparison
necessarily differs — `app_image_digest` changes at minimum, which is what makes
it a different release. Divergence disqualifies a run as a *replay*; it does not
disqualify it as a *comparison*. Two measurements are comparable when
`fixture_set_id` and `metric_definition_version` match; the producer delta is
then the independent variable being studied, and is recorded rather than
eliminated.

This is what satisfies the intent's second-outcome falsifier — "two releases for
which no versioned fixture set yields a comparable quality measurement,
including the case where no fixture set is versioned at all." Before a second
release exists the outcome is untestable, and the intent already records that it
is not thereby satisfied.

## The release gate

**Blocking.** A release does not ship if any fails:

1. A published claim does not resolve to public evidence or to deterministic
   calculation lineage.
2. A tool invocation in the fixture runs has no prior covering `policy.decision`.
3. A step sequence is not recoverable from the event log alone.
4. The telemetry-boundary test finds fixture text in exported telemetry.
5. A deterministic metric regresses against the pinned fixture set beyond its
   recorded threshold.

**Informational.** Recorded, trended, never blocking: judgement evaluations;
escalation rate against the parent's 5–15% target, which the parent already
marks `[moderate]` and "too thin to gate a release on"; latency and cost.

**Flagged output.** A failed *pre-release* check on a run holds that run for
approval — the parent's `awaiting_approval` state — rather than publishing a
weakened analysis or discarding a sound run over one unresolved claim. Which
checks flag is owned here; the criteria for publishing automatically are
reserved to the charter (§ Scope).

## Alternatives considered

**Langfuse as the observability plane.** Rejected as *the plane*, admitted as a
*viewer*. The intent excludes LLM observability tooling as the workflow source
of truth, so a Langfuse-shaped store cannot hold plane 1. As an OTLP consumer it
is a reasonable optional deployment, self-hosted to avoid sending agent content
to a third party — but nothing in the system may require it, and no audit claim
may depend on it. This is the cheap-at-a-seam form of the parent's fourth
quality attribute.

**A vendor-native tracing stack (X-Ray, Cloud Trace).** Rejected. The
multi-cloud constraint is ratified, and instrumentation is precisely where
provider lock-in is cheapest to avoid: OpenTelemetry is vendor-neutral and every
candidate backend ingests OTLP. Choosing a native stack would buy nothing the
OTLP path does not already give.

**NVIDIA NeMo Guardrails as a policy-flow framework.** Rejected for the MVP.
The parent's § Alternatives Considered rejects the *detector* class on cited
evidence but does not evaluate NeMo as a flow framework, which is the gap the
intent recorded. The reason it still fails here is structural rather than
evidential: the parent requires the `policy.decision` event to **commit before**
the authorised invocation is issued, in the same transaction discipline as the
event log, with a `policy-writer` role that holds no other insert. An external
policy-flow framework sits outside that transaction and cannot provide
commit-before-action; adopting it would demote a transactional invariant to a
convention. Recorded here so the intent's question resolves to an argument
rather than to silence.

**Model-graded release gates.** Rejected; see § Three classes of evaluation.

## Risks

- **The two-plane split decays under delivery pressure.** The cheapest place to
  put a new signal is a log line, and the boundary erodes one signal at a time.
  The deletion test is the control, and it is a release gate rather than a
  review habit for exactly that reason.
- **The telemetry-boundary test is a string search, and string searches are
  weak.** It catches verbatim leakage, not paraphrase or partial disclosure
  through structure — an enumeration with enough cardinality is free text
  wearing a costume. Recorded as residual.
- **Fixture sets rot.** A pinned SEC filing is stable, but a metric definition
  that changes silently makes two measurements look comparable when they are
  not. `metric_definition_version` is in the measurement record to make that
  visible; nothing forces it to be bumped honestly.
- **Judgement evaluations are informational, so nobody reads them.** An
  informational signal with no owner is a signal that does not exist. The
  escalation-rate window (30 days, minimum 50 runs) is the only one with a
  stated cadence; the others do not yet have one.

## Known at ship

1. **No second release exists**, so cross-release evaluability is untestable at
   ship. The mechanism is specified and the fixture construction is testable in
   isolation, but the outcome it serves cannot be demonstrated until a second
   release exists.
2. **The telemetry-boundary test bounds verbatim leakage only** (see § Risks).
3. **No fixture corpus exists yet.** The size, composition, and refresh policy
   of the fixture set are unspecified; this document fixes how a set is
   *identified*, not what is in it.
4. **Metric thresholds are unset.** Gate 5 above blocks on regression "beyond
   its recorded threshold", and no threshold is recorded. Until the first
   release establishes a baseline, gate 5 is inert.

## Open questions

- What is in the first fixture set, and who curates it? Gate 5 is inert until
  this is answered.
- What is the retention and sampling policy for telemetry? The event log's
  retention is settled by the parent (life of the published report, no expiry);
  telemetry's is not, and the two must not be confused.
- Does the escalation-rate target survive contact with real runs, given the
  parent rates its 5–15% source `[moderate]` on 125 hand-labelled actions?
- Who reads the informational evaluations, and on what cadence?
