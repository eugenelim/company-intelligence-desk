# Foundation intents

Six foundation intents recording what Company Intelligence Desk must achieve,
written before any architecture existed. Each is registered in `workspace.toml`
`[backlog].open`, which tracks them as open work carrying `Draft` artifacts.

This file states the three rules that apply to all six, so they are not restated
six times and cannot drift apart.

## 1. Ratified constraints

Each intent may carry a `### Confirmed constraints` block. That block is a
**closed transcription** of what the project owner ratified at inception
(2026-09-09). Architecture chooses how to satisfy a ratified constraint; it does
not get to reverse one.

Nothing else belongs in that block. An author's design position, however
reasonable, goes in `### In scope` or in an unresolved question — putting it
under ratified authority would make an owner's commitment indistinguishable from
a preference, which is the exact confusion the block exists to prevent.

The table below is an **index, not a transcript**. Each row is a short handle
plus its owning intent; the normative wording of every constraint lives in that
intent's `### Confirmed constraints` block and nowhere else. Do not quote this
table as the constraint.

| Constraint (handle) | Owning intent |
| --- | --- |
| Containerization | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| UI / API container separation | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| Agent runtime | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| Production runtime host | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| Model access and credential posture | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| AWS service justification bar | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| UI framework | [`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md) |
| Shared component system and its documentation | [`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md) |
| Multiple workspace views | [`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md) |
| Context service as an explicit capability | [`scoped-context-and-evidence`](scoped-context-and-evidence.md) |
| Open-source reference implementation with portable contracts | [`adoptable-reference-implementation`](adoptable-reference-implementation.md) |
| Production-agent privilege floor | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| Deployment tooling implements, does not decide | [`portable-identity-first-runtime`](portable-identity-first-runtime.md) |
| Evidence source tier | [`evidence-backed-company-diligence`](evidence-backed-company-diligence.md) |

An intent subject to a constraint it does not own cites the owner rather than
restating it.

Named at inception as **candidates to evaluate, not decisions** — this list is
authoritative and the delivery brief cites it rather than restating it:

NVIDIA NeMo Guardrails · Langfuse · OpenTelemetry · Claude Code headless ·
ECS Fargate · Application Load Balancer with server-sent events · API Gateway ·
PostgreSQL · S3-compatible object storage · LiteLLM versus an application-owned
Bedrock Converse adapter · PostgreSQL-backed workflow durability versus a
dedicated queue · hosted versus self-hosted LLM operations tooling.

Each belongs in an unresolved question, never in a boundary.

## 2. Handoff shape

One `architect-design` run consumed all six intents together, producing
[`inspectable-multi-agent-diligence`](../../architecture/inspectable-multi-agent-diligence/design-doc.md).
That document is the single home for its own status; this file does not restate
it.

Each intent's `Projection` names what settles that intent. None of them is
another architecture run.

## 3. Settle order

This is a **sequencing aid, not the edge set**. The authoritative dependencies
are the `Depends on:` lines in each intent, which assert more edges than this
sketch draws.

```
portable-identity-first-runtime          settle first — foundational
        │
        ▼
scoped-context-and-evidence              settle second — four intents inherit it
        │
        ├──────────────┐
        ▼              ▼
evidence-backed-   governed-observable-
company-diligence  and-evaluable-operation
        │              │
        └──────┬───────┘
               ▼
multi-workspace-inspectable-experience   settle last of the five
```

**Every intent feeds [`adoptable-reference-implementation`](adoptable-reference-implementation.md)
by construction.** It is the reader-facing consequence of the other five and
carries no outgoing edge. This is that edge's single home; no intent's `Feeds:`
line restates it.

## The six intents

| Intent | Owns |
| --- | --- |
| [`portable-identity-first-runtime`](portable-identity-first-runtime.md) | Execution topology, identity, and how run events are carried and survive restart |
| [`scoped-context-and-evidence`](scoped-context-and-evidence.md) | The context model and the evidence/citation contract |
| [`evidence-backed-company-diligence`](evidence-backed-company-diligence.md) | The diligence domain and its user-facing deliverables |
| [`governed-observable-and-evaluable-operation`](governed-observable-and-evaluable-operation.md) | Policy, telemetry, evaluation, what may leave the backend, and the untrusted-content boundary |
| [`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md) | What the user sees |
| [`adoptable-reference-implementation`](adoptable-reference-implementation.md) | Whether the result is legible and learnable as a reference |

## Status

Each file's `Status:` and `Source: Revision:` lines are the single home for its
own status and revision — an aggregate claim here decays on every material edit
and on every promotion.

None moves to `Accepted` without a revision-bound clean shaping review and
explicit human confirmation. Intents stay **living until all work under them
ships**: when a downstream artifact answers an open question, the intent records
the resolution in place and names where the answer lives. `Accepted` ratifies the
outcome and boundary; questions and projection keep tracking reality.
