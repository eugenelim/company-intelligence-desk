# Portable Identity-First Runtime

- **Status:** Draft
- **Kind:** outcome

## Outcome

The application runs anywhere a container runs, and holds no long-lived model
credential anywhere in the system.

Two independently verifiable sub-results:

1. A contributor can run the whole application locally in containers without
   cloud access.
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
- Production model access uses Amazon Bedrock through workload identity — for
  example an ECS task IAM role — without a static model API key.
- AWS-specific services are introduced only where they have a clear operational
  or security justification.
- Production agents hold no unrestricted shell, network, or infrastructure
  access.
- Deployment tooling — the installed `iac-terraform` pack — implements reviewed
  deployment decisions; it does not make them.

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

- What is the minimum justified AWS deployment profile?
- Is ECS Fargate the appropriate runtime boundary, or is another compute shape
  better justified?
- What task and IAM-role separation is required between components?
- Should the Bedrock integration use an existing provider adapter or an
  application-owned Converse adapter?
- How should local production-parity development authenticate to AWS?
- What offline or fixture-backed mode should contributors without AWS access
  use?
- What end-user authentication and authorization model applies, and is a
  workspace a hard isolation boundary or an organizational convenience? If the
  initial deployment is single-tenant and single-operator, say so explicitly
  rather than leaving it unstated.
- What transport and durability mechanisms are required for long-running runs?
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

Use `architect-design` to decide container boundaries, execution topology,
identity boundaries, Bedrock integration, local-development modes, run-event
transport and durability, the end-user authorization model, and the minimum AWS
service set.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r4 — constraint set ratified to 14, 2026-09-09
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
