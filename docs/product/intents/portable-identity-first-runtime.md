# Portable Identity-First Runtime

- **Status:** Accepted
- **Kind:** outcome

## Outcome

The application runs anywhere a container runs, and neither a deployed component
nor the default branch's current tree holds a long-lived model credential.

**Seven** independently verifiable sub-results, each falsifier quantifying over
the same set as its headline. Sub-results 1 and 7 are positive requirements
whose falsifiers close their empty state; 2–6 are prohibitions, vacuously true
of an empty system. Sub-results 3, 4, 5 and 6 are given force by sub-result
1's positive requirement; sub-result 2 is not — sub-result 1 requires only a
*local* path and entails no deployed component — so its force comes from the
confirmed constraint that a production deployment exists. **Recorded gap:** "anywhere a container
runs" is broader than the conjunction of sub-results 1 and 4, which test a
documented local path and provider-specific coupling outside the seam set;
running on an arbitrary third host is not directly falsifiable here.

1. A contributor can run the whole application locally in containers without
   cloud access, with substitution confined to the seam set named under
   Excluded.
   *Falsified by:* no documented local path existing at all, or a documented
   local path that cannot run the whole application in containers without cloud
   access, or one that requires substituting a component outside the named seam
   set. Documenting no path is a failure, not a pass.
2. Any deployed component that holds model access obtains it through short-lived
   workload credentials scoped to that component; a component whose
   responsibility does not require model access holds none — least privilege,
   ratified in [`docs/CHARTER.md`](../../CHARTER.md) principle 5 rather than
   implied by this outcome's headline.
   *Falsified by:* a deployed component holding model access other than through
   short-lived workload credentials scoped to that component, or a deployed
   component holding model access its responsibility does not require.
3. No artifact in the default branch's current tree contains a long-lived model
   credential.
   *Falsified by:* an artifact in the default branch's current tree containing a
   long-lived model credential.
   Neither history nor non-default branches are in scope: a credential committed
   and later rotated out is a rotation incident, and an unmerged branch has not
   yet made a claim about the repository.
4. No component requires a cloud-provider-specific service from outside the seam
   set named under Excluded.
   *Falsified by:* a component that requires a provider-specific service and
   sits outside that seam set.
5. No credential held by the runtime grants access beyond the single
   integration or model boundary it was resolved for. The unit is the
   **integration**, which is finer than sub-result 2's component: one
   deployable now resolves several distinct authorities per step.
   *Falsified by:* a credential resolved for one integration that authenticates
   successfully against another integration's backend.
   **Scope limit, deliberate:** this quantifies over what a *credential grants*,
   not over what adapter code can *reach*. In one process, adapter code can
   obtain another integration's credential — recorded as blast-radius-only in
   [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
   DR12, with a credential broker commissioned as follow-on work. Writing the
   stronger falsifier here would make this intent fail on a limit it has
   already accepted.
6. No tool invocation succeeds whose arguments fall outside the acting role's
   ceiling, outside the initiating principal's entitlements, or whose role was
   authored beyond its author's own entitlement — where an argument its
   consumer parses is checked against its **canonical parsed form**, and that
   same canonical form is what the consumer receives.
   *Falsified by:* a well-typed invocation outside any of the three bounds
   that succeeds; or an argument whose checked form and consumed form differ.
   The second disjunct is the one that matters — it is the parser-differential
   bypass, and a containment check that omits it reports sound while admitting
   a host or path outside the ceiling.
7. Registering a new agent role, or a new integration of an already-registered
   kind, requires no new deployable and no image rebuild.
   *Falsified by:* an agent role or same-kind integration that cannot be added
   and executed against an unchanged image. Registering a new integration
   **kind** is out of scope for this sub-result — a new kind is a code change by
   construction, and § Excluded makes it an amendment to this intent.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md).

### Confirmed constraints

- The system is containerized.
- The browser UI and the API are separate deployable containers.
- The agent runtime uses Pydantic AI. **Owner-amended 2026-09-17**, superseding
  the inception wording *"The agent runtime uses Google ADK"* — see
  § Constraint amendments.
- The production deployment runs the agent runtime on AWS.
- Production model access uses Amazon Bedrock through workload identity,
  without a static model API key.
- AWS-specific services are introduced only where they have a clear operational
  or security justification.
- Production agents hold no unrestricted shell, network, or infrastructure
  access.
- Deployment tooling implements reviewed deployment decisions; it does not make
  them.

Portable application-owned contracts are a ratified constraint owned by
[`adoptable-reference-implementation.md`](adoptable-reference-implementation.md);
this intent is bound by it and does not restate it.

### Constraint amendments

The block above is otherwise a closed transcription of what the owner ratified
at inception (2026-09-09), per [`README.md`](README.md) § 1. A constraint leaves
that transcription only by an owner amendment, recorded here with its date and
its grounds. Architecture still does not get to reverse a constraint; this
section records the cases where the owner did.

**2026-09-17 — agent runtime: Google ADK → Pydantic AI.** Authorized in-session
by the owner (`eugenelim`). Grounds, all recorded in
[`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md):
ADK has no native Bedrock path, so satisfying the model-access constraint above
required LiteLLM in the model hot path — a dependency that shipped unauthorized
code in 1.82.7–8 and is carried as a live supply-chain risk; and ADK's session
seam is not a public extension point and was broken by ADK 2.0, which put the
inspectability outcome on an unstable dependency. Pydantic AI supplies a native
Bedrock path and a typed, serializable message history, retiring both. Verified
under a least-privilege role by Phase 0 spike 7 — see
[`spikes/README.md`](../../../spikes/README.md).

The companion line *"The production deployment runs the ADK runtime on AWS"* is
reworded to *"the agent runtime"* as a consequence of the same amendment, not as
a second one: the ratified content there is **AWS**, and naming the framework
twice only created a second place for it to drift.

**What this amendment does not change.** The seam set under *Excluded* was
untouched by *this* amendment — it was widened a day later by the substrate
amendment below, on separate grounds. The model-access and credential-posture
constraint is untouched —
the replacement is held to it, not excused from it. And the constraint still
names a *vendor* rather than a property, deliberately: portability is owned by
[`adoptable-reference-implementation.md`](adoptable-reference-implementation.md)
and is not silently annexed here by rewording this line into a capability.

**2026-09-18 — the seam set: two adapters → model-provider plus one per
integration kind.** Authorized by the owner as part of the same decision that
amended [`CHARTER.md`](../../CHARTER.md) to make the project a general-purpose
executable substrate. The substrate resolves integrations from a registry
rather than calling a single external-source fetch adapter, so "exactly two"
stopped being describable. Closure is preserved by a different mechanism:
adding a new integration `kind` is an amendment to this intent. The wording and
the reasoning are under *Excluded*.

**A note on the RFC route.** Both 2026-09-17 and 2026-09-18 amendments were
made directly by the owner rather than through an RFC, under the shaping-phase
exception recorded in [`CHARTER.md`](../../CHARTER.md). That exception expires
at Phase 2.

### In scope

- Per-component identity separation, so no two components share a cloud
  identity by default.
- A local development path that does not require AWS access. Its sufficiency
  *as a learning surface* belongs to
  [`adoptable-reference-implementation.md`](adoptable-reference-implementation.md).
- End-user authentication and authorization, and the isolation semantics of a
  workspace as a tenancy boundary.
- The delegated authority ceiling of an agent role, and its containment within
  the initiating principal's entitlements — non-amplification is ratified in
  [`docs/CHARTER.md`](../../CHARTER.md) principle 5; this intent owns how it is
  bounded and enforced.
- Transport and durability of run events, including survival across restart.

This intent owns **how run events are carried**. It does not own what may leave
the backend (see [`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md))
or what the user sees (see [`multi-workspace-inspectable-experience.md`](multi-workspace-inspectable-experience.md)).

### Excluded

- Domain logic — analysis, evidence handling, workflow orchestration — that
  cannot run against a non-AWS substitute.

**The seam set** — the permitted coupling points, which sub-results 1 and 4
quantify against — is the **model-provider adapter** plus the **integration
adapters**, one per registered integration `kind`. Naming the set still closes
it: a coupling point that is not one of these is a change to this intent, and
**adding a new `kind` is a change to this intent, not an implementation
detail.** The registered kinds are recorded in
[`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
§ Responsibility decomposition.

**Amended 2026-09-18**, following from the same owner authorization as the
charter's substrate amendment. This previously read *"is exactly two: the
model-provider adapter and the external-source fetch adapter."* The substrate
resolves integrations from a registry rather than calling one fetch adapter,
so a fixed count of two was no longer describable — but the *closure* property
the original wording existed to protect is preserved by making a new kind an
intent change. Recorded here rather than assumed, because a seam set that
grows silently is the failure the original wording was written against.

## Owner

eugenelim — decides runtime, deployment, and identity scope.

## Unresolved questions

- What is the minimum justified AWS deployment profile? *Proposed in
  `runtime-architecture.md` § Capacity; settled by the **2026-09-18 owner sign-off** recorded in `runtime-architecture.md` § Sign-off.*
- Is ECS Fargate the appropriate runtime boundary, or is another compute shape
  better justified? *Argued in `runtime-architecture.md` § Alternatives Considered, with
  the compute profile in § Capacity; settled by the **2026-09-18 owner sign-off** recorded in `runtime-architecture.md` § Sign-off.*
- What task and IAM-role separation is required between components?
- What bounds an agent role's authority at the tool-call layer, and how is
  containment within the initiating principal's entitlements enforced?
  *Proposed in `runtime-architecture.md` § Identity — two layers; open until owner
  sign-off.*
- **Settled 2026-09-17 — Bedrock adapter: neither an existing provider adapter
  nor an application-owned Converse adapter.** The
  agent-runtime amendment above makes the question moot — Pydantic AI ships a
  native `BedrockConverseModel`, so there is no third-party adapter in the hot
  path and no application-owned Converse adapter to write. Verified under a
  least-privilege role by Phase 0 spike 7. The `Model` abstract base class
  remains the seam, so an application-owned adapter stays available as the
  fallback it always was.
- How should local production-parity development authenticate to AWS?
- By what mechanism does a contributor without cloud access run the system?
  *Proposed in `runtime-architecture.md` § Local development; settled by the **2026-09-18 owner sign-off** recorded in `runtime-architecture.md` § Sign-off.*
- **What must a principal scope isolate, and by what mechanism?** *Restated
  2026-09-18* — this previously read *"Should a workspace become a hard
  isolation boundary?"*, which was malformed: a **workspace is a UI view**,
  owned by
  [`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md),
  and asking whether a view should be a security boundary is why the question
  sat open. The unit is a **principal scope** — who owns a run, an agent role,
  an integration — and is independent of the UI's pane count.

  **Partially answered 2026-09-18.** The *target* is settled: structural
  isolation in one database (Postgres RLS with `FORCE ROW LEVEL SECURITY`, an
  owner-scope column, scope-qualified object keys, per-principal quotas inside
  the shared rate and token buckets) — explicitly **not** API-level read
  filtering, which would be an application-layer control guarding a data
  boundary. The two irreversible pieces are **taken now**: object keys are
  `<owner_scope>/<content_hash>` with `public` as a named scope, and
  `owner_scope` columns exist unused. What stays open is the *trigger* — when
  a second principal is admitted — and the per-principal quota policy. See
  [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
  § Principal scope. `docs/CHARTER.md` § *What the system is today* records
  the current state as fact.
- What transport and durability mechanisms are required for long-running runs?
  *Proposed in `runtime-architecture.md` § Event log and stream mechanism; open until
  owner sign-off.*
- Should Claude Code headless be used as a development or repository-automation
  harness at all, and if so where does it add value without creating drift from
  the production runtime?

## Spec-readiness pressure test — 2026-09-18

Can implementable specs be authored from this intent as it stands? Tested by
walking the specs the substrate design implies and asking, for each, whether
this intent supplies a testable acceptance criterion or leaves the spec author
guessing.

**Verdict: partially. The walking skeleton is spec-ready. The substrate is
not, and four things are missing.**

| Candidate spec | Spec-ready? | Traces to |
| --- | --- | --- |
| Worker runtime + pool (claim, fence, heartbeat, deadline, provisioning) | **Yes** | sub-results 1, 4; r7 § Step execution |
| Model-provider seam + fixture replay | **Yes** | sub-results 1, 2, 3; DR3 |
| Event-log privilege model (`policy.decision` split) | **Yes** | r7 § Identity; spike P1 proved it executably |
| Agent-role + integration registry schema | **Partly** | sub-result 6 now covers genericity; nothing covers *who may author* |
| Policy decision point / containment algorithm | **No** | see gap 2 |
| Approval + input gates | **Partly** | see gap 3 |
| Multi-author / studio surface | **No** | see gap 1 |

### What is missing

**1. Tenancy — largely closed 2026-09-18, and what remains is gap 2 wearing a
disguise.** The question was malformed (workspace = UI view) and has been
restated as principal scope; the target shape is settled as structural
isolation in one database, and the two irreversible decisions — scope-qualified
object keys and `owner_scope` columns — are taken, so the corpus cannot
accumulate in a shape that forecloses them.

What this unblocks: specs for the runtime, the pool, provisioning, the
registry schema and the object-store contract can now all state acceptance
criteria, because none of them turns on *when* a second principal arrives.

What it does not unblock: any surface where a **second principal authors** an
agent role or integration. That is not tenancy — it is the containment gap
below. Read isolation and authoring authority are different problems and only
the first is now answered.

**2. Authority containment — algorithm resolved 2026-09-18; a sub-result now
exists.** The unsoundness r7 left open is closed by narrowing the fragment:
prefix predicates are expressible only on arguments their consumer does not
parse, interpreted arguments carry a domain type whose predicates range over
*parsed components*, and the runtime passes the **canonical** value to the
adapter so validator and callee cannot disagree. Containment is separated into
three gates at three times — `may_exist` at authoring, `may_run` at spawn,
`may_act` at call — which is what let the authoring-time gap be closed rather
than merely described. See
[`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
§ Authority containment.

A falsifier was withheld last revision because the algorithm was open. It is
open no longer, so **sub-result 6** now makes containment falsifiable at the
outcome level and a PDP spec has something to trace to.

**What is still missing is evidence, not design.** The fragment's soundness is
argued; no property test has run. Phase 1 exit criterion 8 is that test.

**3. Human-interaction ownership — routed 2026-09-18, and it needed a third
intent.** The seam was real and the answer was not a footnote: the owner
described the human surface as conversational control over the application and
its data, which is a capability rather than a clarification.
[`assistant-mediated-operation`](assistant-mediated-operation.md) now owns the
interactive plane, conversation lifetime, capability legibility, the
two-outcome trust boundary, consequence-before-commitment, and assumption
provenance. It depends on this intent for the runtime and the authority model
and adds no constraint to it.

**What that leaves here.** This intent still owns the `awaiting_input` state
itself as event transport and durability; the new intent owns what the
interaction *means*. The state-machine details that were unowned — approve and
reject cycle caps, timeout behaviour — are settled in
[`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
DR5 and are cited by both.

**4. The settling event — happened 2026-09-18.** § Projection makes owner
sign-off on `runtime-architecture.md` the event that settles this intent, and
that sign-off is now recorded there. Every question below that was marked
"open until owner sign-off" is settled, and **a spec may now cite those
answers as settled rather than as proposals** — which was the whole of this
gap. Ratification was explicitly *with* the five limits under r7 § Known at
ship still open; those remain accepted limits, not closed questions.

### What this means for sequencing

Specs for the **walking skeleton** (Phase 1) can be authored now — everything
it needs traces to sub-results 1–4 and to r7 sections whose Phase 0 evidence
already holds. With gap 1 closed, specs for the runtime, pool, provisioning,
registry schema and object-store contract can be authored too.

Specs for the **multi-author surface** still cannot, but the reason has
narrowed to one thing: the trust class of instruction text authored by a
non-operator, recorded as the third governance gap in
[`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
§ This is a platform. Gaps 1 and 2 are designed; gap 3 is not.

**All four gaps are closed as of 2026-09-18.** Specs may now be authored
against this intent and cite its answers as settled. What remains is not a gap
but ordinary owed work: the Phase 1 exit criteria, which are evidence rather
than design, and the assistant intent's two structural gaps, which are its
work and not a blocker on this one.

## Projection

**Depends on:** nothing — this is the single foundational intent; settle it
first.

**Feeds:** all five other intents. Execution topology and identity boundaries
constrain the context service, the diligence workflow's execution, the policy
plane, the event transport the UI consumes, and the deployment story a reader
reproduces.

**Next step.** `architect-design` has run: `runtime-architecture.md` proposes container
boundaries, execution topology, identity boundaries, Bedrock integration,
local-development modes, run-event transport and durability, the end-user
authorization model, and the minimum AWS service set. **It was signed off on
2026-09-18** — see `runtime-architecture.md` § Sign-off — and the Phase 0
spikes that gated ratification all ran. **This intent is settled.**

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r23 — owner sign-off recorded; every question marked "open until
  owner sign-off" settled, pressure-test gap 4 closed, and the intent itself
  settled per its Projection, 2026-09-18
- Revision: r22 — human-interaction ownership routed to the new
  `assistant-mediated-operation` capability intent, closing pressure-test
  gap 3 and leaving owner sign-off as the only open gap, 2026-09-18
- Revision: r21 — containment sub-result added (three gates, canonical-form
  checking) after the fragment's prefix unsoundness was resolved, and
  pressure-test gap 2 closed to design-complete-pending-evidence, 2026-09-18
- Revision: r20 — the tenancy question restated from workspace-as-boundary to
  principal-scope and partially answered (target T3; scope-qualified object
  keys and owner_scope columns taken now), and pressure-test gap 1 closed
  accordingly, 2026-09-18
- Revision: r19 — two sub-results added (per-integration credential scoping;
  registering a role or same-kind integration needs no deployable), the
  preamble's vacuity reasoning updated for six, and a spec-readiness pressure
  test recorded naming four gaps, 2026-09-18
- Revision: r18 — the seam set restated as the model-provider adapter plus
  one adapter per registered integration kind, with closure preserved by
  making a new kind an intent change; follows the charter's substrate
  amendment of the same date, 2026-09-18
- Revision: r17 — agent-runtime constraint amended from Google ADK to Pydantic
  AI on owner authority, a § Constraint amendments section added to carry the
  grounds, and the Bedrock-adapter question settled as moot by that amendment,
  2026-09-17
- Revision: r16 — the preamble's account of what gives each prohibition force
  corrected: sub-result 1 entails no deployed component, so sub-result 2 rests on
  the ratified production-deployment constraint instead, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
