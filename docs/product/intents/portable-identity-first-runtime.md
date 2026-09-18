# Portable Identity-First Runtime

- **Status:** Accepted
- **Kind:** outcome

## Outcome

The application runs anywhere a container runs, and neither a deployed component
nor the default branch's current tree holds a long-lived model credential.

Four independently verifiable sub-results, each falsifier quantifying over the
same set as its headline. Sub-result 1's falsifier closes its empty state;
2–4 are prohibitions, vacuously true of an empty system. Sub-results 3 and 4
are given force by sub-result 1's positive requirement; sub-result 2 is not —
sub-result 1 requires only a *local* path and entails no deployed component — so
its force comes from the confirmed constraint that a production deployment
exists. **Recorded gap:** "anywhere a container
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
  `runtime-architecture.md` § Capacity; open until owner sign-off.*
- Is ECS Fargate the appropriate runtime boundary, or is another compute shape
  better justified? *Argued in `runtime-architecture.md` § Alternatives Considered, with
  the compute profile in § Capacity; open until owner sign-off.*
- What task and IAM-role separation is required between components?
- What bounds an agent role's authority at the tool-call layer, and how is
  containment within the initiating principal's entitlements enforced?
  *Proposed in `runtime-architecture.md` § Identity — two layers; open until owner
  sign-off.*
- ~~Should the Bedrock integration use an existing provider adapter or an
  application-owned Converse adapter?~~ **Settled 2026-09-17: neither.** The
  agent-runtime amendment above makes the question moot — Pydantic AI ships a
  native `BedrockConverseModel`, so there is no third-party adapter in the hot
  path and no application-owned Converse adapter to write. Verified under a
  least-privilege role by Phase 0 spike 7. The `Model` abstract base class
  remains the seam, so an application-owned adapter stays available as the
  fallback it always was.
- How should local production-parity development authenticate to AWS?
- By what mechanism does a contributor without cloud access run the system?
  *Proposed in `runtime-architecture.md` § Local development; open until owner sign-off.*
- Should a workspace become a hard isolation boundary? `docs/CHARTER.md`
  § *What the system is today* records the current state — single operator, no
  isolation — and delegates this question here. *Proposed answer for the
  end-user authentication and authorization model in `runtime-architecture.md`
  § Authentication and authorization; open until owner sign-off.*
- What transport and durability mechanisms are required for long-running runs?
  *Proposed in `runtime-architecture.md` § Event log and stream mechanism; open until
  owner sign-off.*
- Should Claude Code headless be used as a development or repository-automation
  harness at all, and if so where does it add value without creating drift from
  the production runtime?

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
authorization model, and the minimum AWS service set. It awaits owner sign-off,
and the Phase 0 spikes named in `runtime-architecture.md` § Rollout gate its ratification. This intent is settled by that
sign-off, not by another architecture run.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
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
