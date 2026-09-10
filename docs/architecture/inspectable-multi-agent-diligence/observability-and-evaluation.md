# Observability and evaluation — companion to the diligence design

**Author(s):** eugenelim
**Status:** Draft — revision c3, after two independent reviews
**Last updated:** 2026-09-10
**Parent:** [`design-doc.md`](design-doc.md), whose § Scope commissions this
document and fixes its lane.
**Settles:** [`governed-observable-and-evaluable-operation`](../../product/intents/governed-observable-and-evaluable-operation.md)
second outcome (cross-release evaluability), and the egress half of its § In
scope. Its first and third outcomes are settled by owner sign-off on the parent.

## Revision note

c1 returned MAJOR REWRITE (four blockers); c2 returned SHIP WITH CHANGES (two
blockers, both introduced by c2's own repairs). c3 applies both sets. Two
retractions are kept in the body because the rejected reading is itself
instructive: the security argument for non-blocking judgement evaluations
(§ Three classes) and the invented carve-out asymmetry (§ Reserved). Everything
else is stated as current design.

## TL;DR

Two planes, and only one is evidence: the **event log is the source of truth**,
telemetry is disposable, and a release gate proves it by deleting the telemetry
backend and re-checking an enumerated claim list. **No free text crosses the
telemetry boundary at all; free text reaches a user surface only through the
guarded class, after its guards have run or under adjudication.** Judgement
evaluations do not block releases, for reliability reasons rather than security
ones. Cross-release comparability rests on a content-addressed fixture set, and
a release cannot ship without recording one.

## Scope

**This document owns**, per the parent's § Scope deferral table and the intent's
§ In scope:

| Concern | Settled in |
| --- | --- |
| Telemetry boundary | § The two planes |
| Redaction — telemetry egress | § What may cross the telemetry boundary |
| Redaction — backend to user surface | § What may leave the backend to a user surface |
| Payload inlining | § Payload inlining |
| Evaluation architecture | § Three classes of evaluation |
| Fixture versioning | § Fixture sets and comparability |
| Release gates | § Per-run checks and release gates |

The intent assigns this document "what may leave the backend during or after a
run — the redaction rules and the split between guarded and streamable
classes." That is broader than telemetry, and c1 covered only telemetry;
§ What may leave the backend to a user surface closes the half that
[`experience-and-presentation.md`](experience-and-presentation.md) depends on.

**This document does not own** the event envelope, the policy decision point,
the injection defence, or what the user sees.

**Reserved.** The criteria selecting output for *automatic publication* are
ratified in [`docs/CHARTER.md`](../../CHARTER.md) principle 3, which states that
"any change to them, in either direction, takes the route this charter takes".

The three per-run checks in § Per-run pre-release checks restate criteria the
parent's § The approval gate already carries; they are not new criteria. **Any
change to the check set, in either direction, takes the RFC route.**

c2 proposed an asymmetry here — additions admitted, removals by RFC — on the
grounds that the carve-out otherwise has no operational content. That was
reading around ratified text: principle 3 forecloses the asymmetry in the words
"in either direction", and the parent's own precedent was to *amend* principle 3
rather than reinterpret it. If the asymmetry is wanted it is an RFC against
principle 3, recorded in § Open questions.

## The two planes

The intent excludes "LLM observability tooling as the workflow source of truth."
That exclusion is the whole design of this section.

**Plane 1 — the event log.** Append-only, in Postgres, per-run sequenced. Every
claim in the intent's first outcome is answered from this plane plus the
evidence store, and from nothing else.

**Plane 2 — telemetry.** OpenTelemetry spans, metrics and logs over OTLP. Lossy
by construction: sampled, subject to backpressure, safe to drop.

| Plane | Carries |
| --- | --- |
| Event log | Step boundaries; policy decisions and outcomes; approval events; run lifecycle; evidence `snapshot_id`; the producer tuple; human intervention points; **every recorded quality measurement** |
| Telemetry | Latency; token counts; retry and deadlock-retry counts; claim contention; span structure; error class names; cache behaviour |

Quality measurements sit in plane 1 deliberately. A measurement written only to
telemetry would satisfy the deletion test below — which enumerates first-outcome
claims — while destroying the second outcome, which is the precise shape of a
split that has eroded while still passing its own check.

A signal may appear in both only when the telemetry copy is a *measure* and the
event-log copy is the *fact*: duration in telemetry, completion in the log.

## What may leave the backend to a user surface

Three classes. The split is by **content class and run state**, not by
principal — the charter records that "every authenticated principal can read
every run and its evidence", so per-principal redaction would be inventing a
control the MVP does not have.

| Class | Contents | Served |
| --- | --- | --- |
| **Never served** | Private model reasoning — chain-of-thought, deliberation traces | Never. Charter principle 4 bounds inspection to exclude it, so it is not stored in a servable location at all |
| **Guarded** | Final report text and any published claim | Only after its guards have run: the run reached `completed`; or an approver granted publication on a flagged run; **or the requester is acting on the approval surface for a run in `awaiting_approval`, where guarded content is served for adjudication and not for publication — adjudication access is itself recorded as an event** |
| **Streamable** | Everything else the event log holds — step boundaries, policy decision outcomes, approval events, run lifecycle, context package manifests, evidence references | At any time, including mid-run |

The intent excludes "Final report text released before its guards have run" and
adds that "Safe workflow status events are not covered by this exclusion." The
guarded/streamable split is that exclusion made into an API rule.

**The adjudication carve-out is a run-state exit, not a per-principal rule.**
Without it, a run in `awaiting_approval` would withhold the flagged claim from
the approver deciding on it, and charter principle 3's "flagged output is held
for a named human" could not be executed —
[`experience-and-presentation.md`](experience-and-presentation.md) § The
approval surface requires exactly this content. Adjudication is not
publication: the carve-out serves the content for a decision and records the
read, and it does not release the claim to any other surface. The split remains
by content class and run state, with no principal test.

**Withheld is a value, not an absence.** When the API withholds a guarded field
it returns an explicit marker carrying the reason (`guards_pending`,
`awaiting_approval`), never a null or an omitted key. A consumer cannot
otherwise distinguish "withheld" from "absent", and
[`experience-and-presentation.md`](experience-and-presentation.md) requires that
distinction to render its `withheld` state honestly.

## What may cross the telemetry boundary

Telemetry leaves the application boundary entirely, so its rule is stricter.

**The admitted list is closed.** Exactly these forms cross; anything else is
refused, whether or not it looks sensitive:

1. Bounded stable identifiers — `run_id`, `step_id`, `agent_role`, and an
   **opaque principal identifier**, never the OIDC subject or email. The mapping
   from opaque id to principal lives in the event log.
2. Content hashes.
3. Members of a **registered, versioned enumeration**.
4. Numeric measures.
5. Exception **type** names — never exception messages, which routinely carry
   the content that produced them.
6. Tool names — never argument values. A tool call is recorded as its name plus
   the hash of its arguments.

Closing the list matters because the intent closes its own quarantine set the
same way, "so that an untrusted payload which is neither prose nor an admitted
form cannot escape the falsifier." An open list here would have been the weaker
of two rules that are supposed to be the same rule.

**Enumerations are the loophole, so they are bounded.** An enumeration with
enough cardinality is free text wearing a costume. Every enum crossing the
boundary is registered with a member list and a version; the exporter checks
emitted values against the manifest and drops unregistered ones; cardinality is
recorded so growth is visible.

**The boundary test is specified, not gestured at.** *No contiguous span of
≥ 32 characters, after whitespace and case normalisation, drawn from an
evaluation run's pinned evidence, its assembled prompts, or its model-output
text, appears in the serialised OTLP payload.* The 32-character span is a judgement: short enough to catch a leaked
sentence fragment, long enough that legitimate identifiers and enum members do
not collide. It is recorded here so it can be argued with rather than
rediscovered.

## Payload inlining

The parent's envelope carries `payload_ref`. This document sets when a payload
may be carried inline instead.

**Inlinable:** typed scalars, closed-vocabulary classifications, bounded
identifiers, and counts. **Free prose is always a reference**, never inlined, at
any size.

This set is *related to* but not identical with the parent's quarantine set
(references, closed-vocabulary labels, typed scalars): a reference is what an
inline payload would otherwise be, so it appears here as the fallback rather
than as an admitted inline form, and identifiers and counts are added. The two
sets are neighbours, not the same set.

Two consequences earn the constraint. Events stay bounded, so the stream cannot
be made to carry a filing. And the stream can be rendered without a per-payload
redaction pass, which is what lets the sibling companion treat it as directly
renderable and fetch prose separately through the API, where the guarded class
applies.

## Three classes of evaluation

| Class | Example | Blocks a release? |
| --- | --- | --- |
| **Deterministic** | The arithmetic recomputes; a claim's locator resolves | **Yes** |
| **Structural / trajectory** | A `policy.decision` precedes every tool invocation; the step sequence is recoverable | **Yes** |
| **Judgement** | Are the opposed readings genuinely opposed? Is the filing-language finding substantive? | **No** |

**Why judgement evaluations do not block — the reliability argument.** c1 argued
this on security grounds, claiming a model-graded gate is "a detector standing
between an adversary and publication". That was wrong, and the review was right
to reject it: a release gate stands between a *developer* and *shipping*,
evaluated offline against a content-addressed fixture set that no adversary
authored. The parent's grounded facts about detector failure measure adaptive,
attacker-in-the-loop, per-request conditions the release gate does not
instantiate. Spending the strongest evidence in the design on a claim it does
not support would have weakened both.

The real reasons are duller and hold:

- **Goodhart pressure.** A model-graded blocking gate becomes the development
  loop's objective. Optimising analysis prose to satisfy a grader is easier than
  improving the analysis, and the improvement is unobservable from the gate.
- **Nondeterminism makes blocks flaky.** The parent records that sampling is
  non-deterministic; a grader that blocks intermittently on unchanged input
  trains people to re-run until green, which is a gate that has stopped
  functioning while still reporting.
- **Grader drift silently re-baselines.** Changing the grading model or prompt
  moves every historical score with no signal, so a regression and a grader
  change are indistinguishable after the fact.

**The condition under which this flips:** if fixture content ever becomes
externally contributed, an adversary can author what the grader sees, the
adaptive-attack evidence starts to apply, and this section must be revisited.
Today the fixture set is curated in-repo.

**Discharging charter principle 7.** That principle — the one the second outcome
extends — requires that "quality regressions … are visible rather than hidden".
Not blocking is not the same as not visible, and a trend with no owner and no
cadence is indistinguishable from hidden. The trend
is reviewed by the owner (`eugenelim`) at every release, alongside the
deterministic metrics, and the review is recorded **in the event-log plane as a
`release.quality_review` event referencing the measurements reviewed** — a
document whose central rule is which plane a record lives in should not say
"recorded" without a location. A *comparative* blocking
form — blocking on a judgement regression against the pinned fixture set, rather
than on an absolute grade — is a genuinely different design that avoids the
Goodhart objection less clearly than it appears to; it is deferred until a
baseline exists to regress against, and recorded in § Open questions rather than
dismissed.

## Fixture sets and comparability

**A fixture set is an immutable, content-addressed manifest**, constructed
exactly as the parent constructs an evidence snapshot:
`fixture_set_id = hash(sorted set of fixture content hashes)`. Amending a
fixture creates a new set; historical measurements never see it. The
construction is deliberately identical, so a reader who understands one
understands the other.

**The corpus already has a source.** The parent's § Local development builds a
recorded-fixture corpus for offline contributors — a `BaseLlm` adapter replaying
recorded model responses and a fetch adapter replaying recorded filings — and
states that corpus "is the substrate the **evaluation companion** needs for
regression fixtures". This document is that companion, and it does not build a
second corpus.

**But an evaluation run uses only one of the two adapters.** Fetch replay is
**on**: the filings must be pinned, or the measurement is not of the system.
Model replay is **off**: replaying recorded model responses would make a release
that changes `model_id` measure nothing at all. A fixture-mode run and an
evaluation run are therefore different configurations of the same seam, and the
configuration must be recorded: an evaluation run carries
`fetch_adapter=replay, model_adapter=live` in the producer tuple. **The parent's
enumerated tuple has no such field** — see § Required parent edits — and until it
does, the parent's own claim in § Local development that "a fixture run is
stamped as such in the run header's producer tuple" is unsupported by its
enumeration.

**A measurement is a distribution, not a number.** Sampling is
non-deterministic and specialists interleave, so two runs of the same release on
the same fixture set differ. A single measurement per release confounds the
release delta with sampling variance. Each measurement therefore records:

```
{fixture_set_id, metric_definition_version, producer_tuple, app_image_digest,
 n_runs, point_estimate, dispersion}
```

with `n_runs ≥ 5` for the MVP. **Dispersion is the sample standard deviation
over `n_runs`, and a difference between releases is reportable only when it
exceeds 2σ of the earlier measurement.** Naming the statistic matters: standard
deviation, IQR and range give materially different thresholds, and this rule is
the document's whole answer to release-delta-versus-noise. The value of `n` is a cost
trade-off and is recorded in the measurement so a reader can judge it.

**Divergent is not incomparable.** The parent labels a re-run whose producer
tuple differs from the original **divergent**. A cross-release comparison
necessarily differs — `app_image_digest` changes at minimum, which is what makes
it a different release. Divergence disqualifies a run as a *replay*; it does not
disqualify it as a *comparison*. Two measurements are comparable when
`fixture_set_id`, `metric_definition_version`, and the adapter configuration all
match; the rest of the producer delta is the independent variable, recorded
rather than eliminated. The adapter fields join the comparability key because a
measurement taken with fetch replay off is not measuring the same thing. Charter principle 7
supports this directly, ratifying comparison between runs "because both recorded
the evidence, the context, and the producing configuration".

## Per-run checks and release gates

These fire at different times, over different subjects, with different
consequences. Every gate below is stated as a **requirement**; a release ships
only when all hold.

### Per-run pre-release checks — flag, do not fail

Evaluated on a real run before publication. A failure moves the run to
`awaiting_approval`; it does not fail the run and does not block a release.

1. Every published claim resolves to public evidence or to deterministic
   calculation lineage. This **narrows** charter principle 1's *Applied:* rule
   from "blocks publication" to *blocks automatic publication*, consistent with
   the parent's approval gate, which an approver may then adjudicate.
2. Every tool invocation has a prior covering `policy.decision`.
3. The step sequence is recoverable from the event log alone.

Holding for approval rather than failing is deliberate: it neither publishes a
silently weakened analysis nor discards a sound run over one unresolved claim.

### Release gates — block the release

Evaluated over the pinned fixture set, not over user runs.

1. **A non-empty fixture set, a metric definition, and a stored measurement all
   exist.** The release records a `fixture_set_id` over a set containing at
   least one fixture, at least one `metric_definition_version`, and a
   measurement keyed to both with `n_runs ≥ 5`. The non-emptiness matters:
   `hash(sorted set of …)` over the empty set is well-defined, so without it a
   vacuous set with a vacuous measurement would pass the gate the falsifier
   motivated. This gate is testable at the *first* release, long before any
   comparison is possible, which is where the falsifier's "no fixture set is
   versioned at all" case actually bites. Owner of the first fixture set:
   `eugenelim`.
2. **No deterministic metric regresses** beyond its recorded threshold *and*
   outside the recorded dispersion, per § Fixture sets and comparability. Both
   conditions are required: with model replay off, deterministic metrics are
   computed over non-deterministically sampled runs, so a threshold alone would
   make this gate intermittently fail on unchanged input — the same flakiness
   used in § Three classes to argue against blocking on judgement.
3. **No fixture text appears in exported telemetry**, per the boundary test in
   § What may cross the telemetry boundary.
4. **The deletion test passes.** With the telemetry backend removed, every claim
   in this enumerated list still holds from the event log and evidence store
   alone: first-outcome sub-results 1, 2 and 3; third-outcome sub-result 2's
   coverage property; every recorded quality measurement; the producer tuple;
   and `snapshot_id`. The enumeration is hand-maintained, and that is a known
   weakness — an intent that adds a claim without adding a row here leaves the
   gate passing while the split has eroded.
5. **The authorization test suite passes**, including well-typed unauthorised
   calls. Adopted from the parent's § Risks, which names it as a release gate
   under *Policy misconfiguration*.
6. **The API-surface test passes.** For a run in each of `running`,
   `awaiting_approval`, and `completed`, every guarded field is either served
   under its stated condition or returns an explicit withheld marker, and no
   never-served content is reachable from any endpoint. Without this gate the
   telemetry path has a blocking boundary test and the API path — the half the
   sibling depends on — has none.

**On the parent's "zero unresolved claims" gate.** The parent's § Goals states
"Zero unresolved claims is the release gate." This document reclassifies that as
a **per-run flag** (check 1 above) rather than a release gate, because it
quantifies over user runs rather than over the fixture set, and because the
parent's own approval gate holds such a run for a human rather than failing it.
The parent's § Goals wording needs the matching edit — see § Required parent
edits.

**Informational.** Recorded and trended, never blocking: judgement evaluations
(§ Three classes); escalation rate against the parent's 5–15% target, which the
parent itself rates `[moderate]` and "too thin to gate a release on"; latency
and cost.

## Required parent edits

Three edits to [`design-doc.md`](design-doc.md) are needed before this companion
is consistent with it. They are recorded rather than made, because the parent
has its own review history and is the owner's to sign off.

1. **Add the adapter configuration to the producer tuple.** The enumerated tuple
   in § Context, evidence, and reproducibility has no adapter field, yet
   § Local development claims "a fixture run is stamped as such in the run
   header's producer tuple". Add `fetch_adapter` and `model_adapter`.
2. **Reword the "zero unresolved claims" gate** in § Goals from a release gate
   to a per-run pre-release check, consistent with § The approval gate.
3. **State where never-served content is stored, or that it is not stored.**
   This document asserts private model reasoning "is not stored in a servable
   location at all". That is a constraint this companion places on the parent's
   event log and evidence store; the parent, which owns both, does not currently
   state it.

## Alternatives considered

**Langfuse as the observability plane.** Rejected as *the plane*, admitted as a
*viewer*. The intent excludes LLM observability tooling as the workflow source
of truth, so it cannot hold plane 1. As an OTLP consumer it is a reasonable
optional deployment, self-hosted so agent content does not reach a third party —
but nothing may require it and no audit claim may depend on it.

**A vendor-native tracing stack (X-Ray, Cloud Trace).** Rejected.
**Portability is ratified** — the parent is explicit that this means "portable,
not *simultaneously multi-cloud*" — and instrumentation is where provider
lock-in is cheapest to avoid. Every candidate backend ingests OTLP, so a native
stack buys nothing the neutral path does not.

**Model-graded release gates, in three forms.** *Absolute grade blocks* —
rejected, § Three classes. *Comparative regression blocks* — deferred, not
rejected: it avoids the absolute-threshold objection but not grader drift, and
there is no baseline yet to regress against. *Block with override* — rejected:
an override that is always exercised is a gate that has been removed while still
appearing in the list, and a single-operator project has no second party to make
the override meaningful.

**NVIDIA NeMo Guardrails.** *Not resolved here.* The intent records it as an
open question, and c1 answered it — deciding a policy-plane question this
document's own § Scope disclaims, and against a configuration nobody proposed
(NeMo replacing the PDP, rather than a flow framework sitting above an
application-owned PDP that still writes `policy.decision`). The question **remains open in the intent**, owner `eugenelim`; the venue is an
ADR, because the parent does not carry a NeMo section and reopening a Draft
parent to add one is not warranted.

## Risks

- **The two-plane split decays under delivery pressure.** The cheapest place to
  put a new signal is a log line. Gate 4 is the control, and its enumeration is
  hand-maintained, so the control decays the same way.
- **The telemetry-boundary test bounds verbatim leakage only.** A 32-character
  span search catches a leaked fragment, not paraphrase, and not disclosure
  through structure — which is why enumerations are registered and their
  cardinality recorded, and why that mitigation is itself only partial.
- **Fixture sets rot.** A pinned filing is stable; a metric definition that
  changes without a version bump makes two measurements look comparable when
  they are not. `metric_definition_version` makes that visible; nothing forces
  it to be bumped honestly.
- **`n_runs ≥ 5` is a guess.** It is enough to expose gross variance and not
  enough to resolve a small regression. The dispersion is recorded so the
  guess is visible, but a real power calculation has not been done.
- **The guarded/streamable split assumes guards are the only reason to
  withhold.** If tenancy isolation ever arrives, per-principal redaction becomes
  a second axis and this table becomes insufficient rather than merely
  incomplete.

## Known at ship

1. **No second release exists**, so cross-release comparison is untestable at
   ship. Gate 1 is what stops that from becoming an excuse: the fixture set,
   metric definition, and first measurement must exist at release one.
2. **The telemetry-boundary test bounds verbatim leakage only** (§ Risks).
3. **The fixture corpus is inherited, not designed.** The parent's local-
   development corpus supplies it; its composition and refresh policy are
   unspecified, and this document fixes only how a set is identified.
4. **Metric thresholds are unset**, so gate 2 is inert until the first release
   establishes a baseline. Gate 1 is not inert, which is the point.

## Open questions

- What is in the first fixture set, and what is its refresh policy? Owner:
  `eugenelim`; needed before gate 2 has meaning.
- Does comparative judgement-regression blocking earn its place once a baseline
  exists? Revisit at the second release.
- What is the retention and sampling policy for telemetry? Owner: `eugenelim`;
  answered by Phase 1, because the deletion test's premise is that telemetry is
  safe to drop and sampling is how that becomes true in practice.
- Is `n_runs ≥ 5` defensible after the first release's observed dispersion?
- Should the automatic-publication carve-out become asymmetric — additions to
  the flagging check set admitted without an RFC, removals not? That is an RFC
  against charter principle 3, not a reading of it (§ Scope).
