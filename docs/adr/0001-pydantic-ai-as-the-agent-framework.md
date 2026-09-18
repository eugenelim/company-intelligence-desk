# ADR-0001: Pydantic AI as the agent framework

- **Status:** Accepted
- **Date:** 2026-09-17
- **Areas:** framework, runtime, model-provider
- **Reversibility:** high
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** none
- **Superseded by:** none
- **Superseded in part:** ADR-0002 D5

## Context

The project ratified **Google ADK** as the agent runtime at inception, and
[`runtime-architecture.md`](../architecture/inspectable-multi-agent-diligence/runtime-architecture.md)
r7 built around it — as a *step-level reasoning library* behind a stable seam,
never as the system of record. That ownership split was chosen deliberately and
is not what this decision changes.

This decision supersedes the inception constraint *"The agent runtime uses
Google ADK"* (ratified 2026-09-09) — a constraint amendment, not an ADR
supersession, since no prior ADR recorded that constraint. The amendment is
authorized by
[`portable-identity-first-runtime`](../product/intents/portable-identity-first-runtime.md)
§ Constraint amendments.

Two of r7's own grounded facts made ADK the wrong library for that role, and
both were established by reading its published source tree rather than from its
documentation:

**ADK has no native Bedrock path.** There is no `bedrock_llm.py` in the model
registry, so the only route to the ratified model-access posture — Bedrock via
workload identity, no static API key — was `LiteLlm`. That put a third-party
package in the **model hot path**, and 1.82.7–8 shipped unauthorized code. r7
carried it in § Risks as a supply-chain surface *accepted* for provider
fan-out. It could not be mitigated away, because it was structural: the
dependency existed because ADK lacked a model class.

**ADK's session seam is not a public extension point.** `BaseSessionService` is
a four-method ABC that ADK does not present as extensible, and ADK 2.0 changed
the `Event` schema with release notes stating that custom session storage
requires updates. r7 responded by making the context service an application
capability rather than ADK's — that is, by routing *around* the framework. The
inspection surface is quality attribute 1 and is not retrofittable, so building
it against a seam the vendor may break is a standing cost.

A third fact emerged later: the project needs the worker to be a **generic
runtime** — nothing about any agent compiled in, with instructions,
configuration and integrations all arriving as data. That requirement is
independent of the vendor choice but raises the cost of a framework whose
extension points are unstable.

## Decision

We will use Pydantic AI as the agent framework, at the same position in the
architecture ADK occupied: a step-level reasoning library invoked inside a
leased step, never the system of record.

The ownership split is unchanged. The application continues to own the run
state machine, the durable event log, the lease protocol, checkpoints and
authorization decisions.

- **D1:** Pydantic AI is the agent framework, occupying the same
  step-level-reasoning-library position ADK occupied; the application keeps
  owning the run state machine, the durable event log, the lease protocol,
  checkpoints and authorization decisions.
- **D2:** `Model` replaces `BaseLlm` as the portability contract. Production is
  `BedrockConverseModel`, constructed with a model id and nothing else;
  fixture mode is a `ReplayModel` subclass. LiteLLM leaves the hot path.
- **D3:** `WrapperToolset.call_tool` is where the policy decision point
  performs argument-value authorization, with the `policy.decision` event
  committing before the invocation.
- **D4:** `DeferredToolRequests` / `deferred_tool_results` carries the human
  approval gate across a process boundary.
- **D5:** The pinned version is `pydantic-ai` 2.44.0.

## Evidence

Phase 0 spike 7 ran under a least-privilege assumed role — not as an
administrator, because an administrator can invoke any model and a green result
would say nothing about a scoped workload. 10/10 hypothesis checks, $0.006.

| Hypothesis | Result |
| --- | --- |
| Ambient workload identity, no static key; streaming and tool loop preserved; out-of-policy model refused | held 4/4 |
| PDP as a `WrapperToolset` refuses a well-typed call on argument **value** before the tool body runs | held 2/2 |
| Message history round-trips byte-identically; a fresh `Agent` resumes from the bytes alone | held 2/2 |
| Approval gate survives a process boundary — decision applied by a different `Agent` built only from serialized history | held 2/2 |

**What the evidence does not cover**, recorded because a decision record that
overstates its evidence is worse than one with none. The PDP check appended to
a Python list, so commit-before-action under a failing append is **not**
established. The history round-trip used two messages with no tool calls, so
byte-identity at the shape a real step produces is **not** established.
Streaming was two deltas on a short response. All three move to Phase 1 exit
criteria.

## Consequences

**Positive:**

- A named supply-chain risk is retired rather than mitigated — one fewer
  third-party package between our credentials and the model provider.
- The durable inspection record becomes a typed, serializable, documented
  structure instead of a schema behind a non-public extension point.
- OpenTelemetry instrumentation following the GenAI semantic conventions
  arrives with a content-exclusion switch, which is work the observability
  companion no longer has to build.
- The approval gate and the fixture-mode replay adapter both land on documented
  extension points rather than improvised ones.

**Negative, and accepted:**

- **The vendor's next major is permissible now.** V2.0 went stable 2026-06-23
  and the published three-month floor before a next major has passed. Mitigated
  by exact pinning and contract tests at both seams — a smaller bet than ADK's,
  not no bet.
- **A framework object now stands on a security boundary.** A change to
  `WrapperToolset.call_tool`'s contract is a change to the authorization
  boundary and could land in a minor release without being classed as breaking.
  Gated by the authorization suite, which asserts refusal *and* exception type
  on well-typed unauthorised calls, plus a structural assertion that the PDP is
  the agent's only toolset.
- **Durable step state is in a vendor serialization format.** Message-history
  JSON is readable only through `ModelMessagesTypeAdapter`, and the vendor
  makes no schema-versioning promise — only a policy that additive changes are
  not breaking. Accepted because reconstruction never reads it: the claim set,
  evidence locators and policy decisions the reconstruction script byte-matches
  on are typed application events in our own schema. **If that asymmetry stops
  holding, this consequence becomes a problem.**
- **Phase 0 spikes 1 and 2 are superseded.** They were passes about ADK and
  LiteLLM specifically. Spike 7 re-established them; spikes 3, 4, P1 and P2 are
  framework-independent and stand.
- **Analytical parity is not claimed.** The swap changes prompt assembly,
  structured-output mechanics and the retry model. Spike 4's quality baseline
  was measured under the old stack and does not transfer.

**Neutral:**

- No column change and no data migration. Two additive schema asks are carried
  in the design doc's § Changes this design asks of r7 — one expand-only
  partial unique index for idempotency, and a grant change on `policy-writer`.
  Until Phase 2 the rollback unit is a `git revert` plus re-pinning `google-adk`
  and `litellm` — cheap, which is why **Reversibility** above is rated `high`.
  After Phase 2, payload objects written by a Pydantic AI step are in a format
  an ADK runtime cannot read, so a rollback would strand replay of runs
  executed in between — which is an argument for doing this before Phase 2,
  not an argument that rollback is free, and it is the trigger named below.

**Revisit if:** the message-history/schema asymmetry stops holding (reconstruction
begins reading vendor-serialized payloads directly instead of typed application
events), or Phase 2 ships stateful runs before the rollback-strands-replay risk
above is otherwise retired, or the message-history schema asymmetry combines
with a vendor major-version bump to break the contract tests at either seam.

## Alternatives considered

- **Keep ADK and LiteLLM:** already spiked green, already ratified, zero cost
  today. Rejected because both recorded risks are structural rather than
  incidental: the LiteLLM dependency exists *because* ADK has no Bedrock model
  class, and the inspection surface would keep being built against a seam the
  vendor has already broken once.
- **Application-owned Bedrock Converse adapter behind ADK's `BaseLlm`:**
  removes LiteLLM without changing framework. Rejected because it removes only
  one of the two problems and creates a component we then own forever, while
  the session seam — the one that touches quality attribute 1 — is untouched.
- **Pydantic AI plus a durable-execution engine (DBOS):** Postgres-backed, and
  we already run Postgres. Rejected because it moves durable control-flow
  state into a vendor checkpoint format, which *is* reconstruction-critical,
  and because it trades machinery already exercised by spikes 3, P1 and P2 for
  machinery that is not. Recorded in the design doc with its three specific
  costs.

## References

- Design: [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
- Constraint authority:
  [`portable-identity-first-runtime.md`](../product/intents/portable-identity-first-runtime.md)
  § Constraint amendments
- Evidence: [`spikes/README.md`](../../spikes/README.md) § Spike 7 — 10/10
  hypothesis checks under a least-privilege role
- Prior runtime architecture:
  [`runtime-architecture.md`](../architecture/inspectable-multi-agent-diligence/runtime-architecture.md)
  r7

## Open

This ADR settles the framework. It does **not** settle:

- **Nothing in § Decisions required remains open.** All thirteen (DR1–DR13)
  were settled by 2026-09-18 — several by checking vendor behaviour rather
  than by preference — and the design doc records each with its date and
  grounds. This ADR is not the authority for any of them.
- **Nothing.** All four spec-readiness gaps recorded in
  [`portable-identity-first-runtime`](../product/intents/portable-identity-first-runtime.md)
  § Spec-readiness pressure test are closed as of 2026-09-18 — principal-scope
  isolation and authoring-time containment designed, human-interaction
  semantics routed to
  [`assistant-mediated-operation`](../product/intents/assistant-mediated-operation.md),
  and the architecture signed off. Specs may now cite these answers as settled.
  What remains is **evidence, not design**: the Phase 1 exit criteria.
- **One commissioned follow-on:** the credential broker (DR12), tracked in
  `workspace.toml` `[backlog].open`.

**Settled elsewhere since this ADR was written.** DR12 — per-integration
credential scoping is blast radius, not isolation — was accepted on 2026-09-18
with a **credential broker commissioned as a follow-on design**, tracked in
`workspace.toml` `[backlog].open`. DR13 — `trust_class` — was settled the same
day as a *construction*: admitted-type output is validated by a deterministic
parser the runtime owns, and an integration that cannot meet it is
quarantine-only. DR11 — whether the project may
be a general-purpose agent runtime at all — was settled on 2026-09-18 by a
direct owner amendment to [`CHARTER.md`](../CHARTER.md) § Amendments, under a
shaping-phase exception to the RFC route that expires at Phase 2. The project
is now chartered as an executable substrate with diligence as the proving use
case. That amendment does **not** close the three governance gaps a
multi-author substrate needs — tenancy isolation, authoring-time authority
containment, and the trust class of non-operator prompts — and the charter
says so.
