# Portable Identity-First Runtime

- **Status:** Draft
- **Kind:** outcome

## Outcome

The application runs anywhere a container runs, and no deployed component or
anything in the repository holds a long-lived model credential.

Two independently verifiable sub-results:

1. A contributor can run the whole application locally in containers without
   cloud access, with only its external boundaries replaced.
2. Every production component obtains model access through short-lived
   workload credentials scoped to that component.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md).

### Confirmed constraints

- The system is containerized.
- The browser UI and the API are separate deployable containers.
- The agent runtime uses Google ADK.
- The production deployment runs the ADK runtime on AWS.
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

### In scope

- Per-component identity separation, so no two components share a cloud
  identity by default.
- A local development path that does not require AWS access. Its sufficiency
  *as a learning surface* belongs to
  [`adoptable-reference-implementation.md`](adoptable-reference-implementation.md).
- End-user authentication and authorization, and the isolation semantics of a
  workspace as a tenancy boundary.
- Transport and durability of run events, including survival across restart.

This intent owns **how run events are carried**. It does not own what may leave
the backend (see [`governed-observable-and-evaluable-operation.md`](governed-observable-and-evaluable-operation.md))
or what the user sees (see [`multi-workspace-inspectable-experience.md`](multi-workspace-inspectable-experience.md)).

### Excluded

- Domain logic — analysis, evidence handling, workflow orchestration — that
  cannot run against a non-AWS substitute. Provider adapters are the permitted
  coupling point.

## Owner

eugenelim — decides runtime, deployment, and identity scope.

## Unresolved questions

- What is the minimum justified AWS deployment profile? *Proposed in
  `design-doc.md` § Capacity; open until owner sign-off.*
- Is ECS Fargate the appropriate runtime boundary, or is another compute shape
  better justified? *Proposed in `design-doc.md` § Capacity; open until owner
  sign-off.*
- What task and IAM-role separation is required between components? *Proposed
  in `design-doc.md` § Identity — two layers; open until owner sign-off.*
- Should the Bedrock integration use an existing provider adapter or an
  application-owned Converse adapter? *Proposed in `design-doc.md` § The
  model-provider seam, pending a Phase 0 spike; open until owner sign-off.*
- How should local production-parity development authenticate to AWS?
- By what mechanism does a contributor without cloud access run the system?
  *Proposed in `design-doc.md` § Local development; open until owner sign-off.*
- Should a workspace become a hard isolation boundary? `docs/CHARTER.md`
  § *What the system is today* records the current state — single operator, no
  isolation — and delegates this question here. *Proposed answer for the
  end-user authentication and authorization model in `design-doc.md`
  § Authentication and authorization; open until owner sign-off.*
- What transport and durability mechanisms are required for long-running runs?
  *Proposed in `design-doc.md` § Event log and stream mechanism; open until
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

**Next step.** `architect-design` has run: `design-doc.md` proposes container
boundaries, execution topology, identity boundaries, Bedrock integration,
local-development modes, run-event transport and durability, the end-user
authorization model, and the minimum AWS service set. It awaits owner sign-off,
and four Phase 0 spikes gate its ratification. This intent is settled by that
sign-off, not by another architecture run.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r6 — inception candidate removed from the ratified block; offline
  resolution reduced to an outcome; tenancy question narrowed against the
  ratified charter, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
