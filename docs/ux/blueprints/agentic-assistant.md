---
type: service-blueprint
journey: "The diligence analyst and the assistant"
slug: "agentic-assistant"
date: "2026-09-18"
---

# Service Blueprint: the diligence analyst and the assistant

## Summary

**Journey:** An analyst converses with module-scoped assistants and an overall
assistant to reach a defensible judgement about one company as of an explicit
date — querying evidence, modelling scenarios, and taking actions such as
refreshing or adding a ticker.
**Scope:** Arriving → Acting and confirming
([`agentic-assistant`](../journeys/agentic-assistant.md), six stages).
**Surfaces / channels:** Responsive web. One channel; no email, no mobile push.

**What this blueprint is for.** The runtime behind these actions is already
designed in
[`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md).
Mapping the journey onto it is how we find out what that design does *not*
cover — and it covers less of this than it looks. **Nine gaps, two of them
structural.**

---

## Blueprint

Split into two tables to stay readable; the line of visibility runs through
both.

### Stages 1–3

| Row | 1: Arriving | 2: Framing the question | 3: Interrogating the evidence |
| --- | --- | --- | --- |
| **Evidence of service** | Re-entry view showing what is in flight; persistent as-of frame; last conversation reopened | Chat composer; a visible difference between the module assistant and the overall one; an answer to "what can you do here" | The answer itself; provenance shown inline; **an explicit, readable refusal when something cannot cross the boundary** |
| **Frontstage** | `resume-prior-context`, `set-analysis-frame` | `ask-module-assistant`, `ask-overall-assistant` | `request-provenance`, `inspect-evidence-item`, `challenge-an-answer` |
| ·········· LINE OF VISIBILITY ·········· | | | |
| **Backstage** | Snapshot read; stream resumed at the recorded cursor; list of the analyst's conversations and runs | Agent role resolved and compiled for the module; ceiling read and rendered for a human; turn dispatched to the interactive plane | Quarantined reader step; trust-class parse of every integration result; locator dereference; evidence read |
| **Support** | Event log; SSE cursor; OIDC session | Agent-role registry; integration registry; entitlements | Object store (scope-qualified keys); runtime-minted reference set; egress proxy |

### Stages 4–6

| Row | 4: Modelling the scenario | 5: Deciding | 6: Acting and confirming |
| --- | --- | --- | --- |
| **Evidence of service** | A scenario shown as an object carrying its assumptions, visually unmistakable from an evidence-backed claim | A readiness indicator that moves while the work forms; the claim set with each claim's resolution state | A consequence preview *before* the prompt; the confirmation itself; a landed-confirmation afterwards |
| **Frontstage** | `vary-assumption`, `compare-to-base-case` | `review-claim-set` | `refresh-ticker`, `add-ticker`, `launch-run`, `confirm-consequential-action`, `publish-judgement`, `verify-action-landed` |
| ·········· LINE OF VISIBILITY ·········· | | | |
| **Backstage** | Deterministic scenario calculation; assumption set persisted as the calculation's recorded inputs; typed scalars returned | Pre-release checks; each claim resolved against an evidence item or a recorded calculation | Argument-value authorization; decision committed before the action; suspension for confirmation; ingestion triggered; run enqueued; publication transition |
| **Support** | Integration registry (`pure-function` kind) | Event log; evidence store | Egress proxy and its shared rate budget; approval and input events; object store |

---

## Column gaps

Nine. Each is a frontstage action the runtime does not currently back, or
backs in a shape the journey cannot use. **G3 and G6 are structural** — they
are not missing endpoints, they are missing *concepts*.

**G1 — No conversation as a listable thing (Stage 1).** Re-entry needs "what
was I doing", and the runtime has runs, not conversations. A conversation is
naturally a long-lived run that sits in `awaiting_input` between turns, but no
run *kind* distinguishes an interactive conversation from a diligence run, and
nothing lists them. Without the kind, the goals also misapply: reconstruction
("rebuild the published report from the event log") is meaningful for a
diligence run and meaningless for a chat.

**G2 — No capability introspection (Stage 2).** "What can you do here" is
answerable from `agent_role.tool_allowlist` — the authority is already data —
but no read path renders it for a human. This is the cheapest gap on the list
and the one with the best ratio: it exists, it just isn't exposed.

**G3 — A boundary refusal is a step failure, not an answer. (Structural.)**
Trust-class enforcement fails the step when output is not admissible. That is
correct for an attack and *wrong for the journey's most common case*: the
analyst asked a reasonable question whose answer is untagged narrative or a
causal claim, and the system must say so. The runtime currently has one
outcome where the experience needs two — **malformed or hostile output fails
the step; legitimately inadmissible content returns a typed non-answer
carrying the passage and the reason.** This is the direct cause of the
journey's deepest emotional dip, and it cannot be fixed in the UI.

**G4 — Provenance has no read path for conversational answers (Stage 3).**
Locators resolve for published artifacts. An answer in a chat turn needs the
same resolution inline and on every claim, which is a different access
pattern and volume.

**G5 — No scenario capability, and no home for assumptions (Stage 4).** The
registry admits a `pure-function` kind, so a scenario engine *could* be
registered, but none is designed. The harder half: claim provenance requires a
calculation to carry *recorded inputs*, and a scenario's assumptions are those
inputs. Nothing persists an assumption set as a first-class object, so a
scenario figure that reaches a report arrives unprovenanced.

**G6 — Readiness is computed once, and the journey needs it continuously.
(Structural.)** Pre-release checks run in the step executor before the agent
run, once. The analyst wants to watch publishability approach while composing.
That is a different invocation model — incremental evaluation over a forming
claim set — not a re-run of the same check.

**G7 — Nothing computes an action's consequence (Stage 6).** Approval
suspension exists and carries the pending call and its arguments; it does not
carry *what the action costs, whether it is reversible, or what it touches*.
The journey needs blast radius shown before the prompt. The registry is the
natural home — integrations would declare a reversibility and a cost class,
and the suspension payload would carry them — but neither field exists.

**G8 — No closing of the loop on asynchronous actions (Stage 6).** The
assistant can trigger ingestion, which runs on a different plane on its own
schedule. Nothing notifies the conversation when it lands, so
`verify-action-landed` is currently the analyst going to look.

**G9 — The analysis frame's scope is undefined (Stage 2).** Company and as-of
date are run-level properties. A conversation may span companies and dates, so
it is unspecified whether the frame is per conversation or per turn — and an
as-of analysis with an ambiguous frame is the one thing the product must not
produce.

---

## Fail-points

Distinct from gaps: these services exist (or are designed) and are at risk.

**Critical — Trust-class enforcement (Stage 3).** Failing open removes the
injection boundary the project exists to demonstrate. Failing closed without a
designed message makes the product look broken, which is G3. *Failure
evidence-of-service:* the analyst must receive the typed non-answer with the
underlying passage — never a generic error, and never silence.

**Critical — Policy decision point (Stage 6).** A failed decision append is a
denial by design, so an unavailable policy path means the assistant can answer
but cannot act. *Failure evidence-of-service:* an explicit "I can't take
actions right now" that distinguishes a *policy outage* from a *refusal* —
conflating them teaches the analyst that refusals are glitches to retry.

**High — Interactive dispatch latency.** Notification-driven dispatch with a
short poll as the safety net; a missed notification degrades a chat turn to
poll latency. Noticeable, not blocking.

**High — Model provider throttling.** The token budget is shared with
diligence runs, so a heavy run degrades chat. *Fallback:* the turn queues with
a visible waiting state rather than failing.

**Medium — Stream reconnection.** Already designed and spike-proven; a
reconnect costs a cursor round-trip.

**Medium — Egress rate budget (Stage 6).** The SEC limit is an aggregate
obligation that does not divide, so a refresh may wait behind ingestion.

---

## Named backstage services

`architect` is present in this session, so services are named by-reference.
**Bold = does not exist yet.**

| Service name | Role | Hand-off target |
| --- | --- | --- |
| Interactive Dispatch | Low-latency delivery of a chat turn to a worker, distinct from the run poll loop | `architect` |
| **Conversation Store** | A conversation as a listable, resumable long-lived run with its own kind | `architect` |
| Agent Compiler | Resolves a role version to instructions, toolset, ceiling, model settings | `architect` |
| **Capability Introspection** | Renders a role's ceiling as a human-readable capability list | `architect` |
| Policy Decision Point | Argument-value authorization; commits the decision before the action | `architect` |
| Trust-Class Enforcer | Parses and resolves integration output before anything else observes it | `architect` |
| **Inadmissibility Responder** | Turns a legitimate boundary refusal into a typed non-answer rather than a failure | `architect` |
| **Evidence Resolver** | Resolves locators to evidence items on the conversational read path | `contracts` |
| **Scenario Engine** | Deterministic what-if calculation over evidence, with its assumption set as recorded inputs | `architect` |
| **Release Gate (incremental)** | Evaluates publishability continuously over a forming claim set | `architect` |
| **Action Consequence Service** | Computes cost, reversibility and reach for a pending action, before confirmation | `architect` |
| Approval & Input Suspension | Suspends a step for a human decision and resumes it across a process boundary | spec LLD |
| Ingestion Trigger | Requests corpus refresh or a new ticker on the ingestion plane | `contracts` |
| **Action Completion Notifier** | Reports an asynchronous action's landing back into the conversation | `architect` |
| Event Log & Stream | The system of record and its cursor-served projection | spec LLD |
| Integration Registry | Versioned integrations, their credential scopes, trust class and ceiling fragment | `contracts` |

- **Service:** interactive-dispatch
- **Service:** conversation-store
- **Service:** agent-compiler
- **Service:** capability-introspection
- **Service:** policy-decision-point
- **Service:** trust-class-enforcer
- **Service:** inadmissibility-responder
- **Service:** evidence-resolver
- **Service:** scenario-engine
- **Service:** release-gate-incremental
- **Service:** action-consequence-service
- **Service:** approval-and-input-suspension
- **Service:** ingestion-trigger
- **Service:** action-completion-notifier
- **Service:** event-log-and-stream
- **Service:** integration-registry

---

## Hand-off

- **Interactive Dispatch**, **Conversation Store** → `architect` — the
  interactive execution plane and the run kind that carries it.
- **Inadmissibility Responder** → `architect` — the two-outcome split in
  trust-class enforcement. Highest priority: it is the journey's deepest dip
  and a runtime change, not a UI one.
- **Action Consequence Service** → `architect` — plus two new registry fields
  (reversibility, cost class) → `contracts`.
- **Capability Introspection**, **Evidence Resolver** → `architect` /
  `contracts` — both read paths over data that already exists.
- **Scenario Engine**, **Release Gate (incremental)**, **Action Completion
  Notifier** → `architect` — genuinely new capability.
- **Policy Decision Point**, **Trust-Class Enforcer**, **Agent Compiler**,
  **Integration Registry**, **Event Log & Stream**, **Approval & Input
  Suspension** → already designed; no new work, cited so the blueprint is
  complete rather than only listing deltas.

---

## Open questions

- [ ] Is the analysis frame (company + as-of date) a property of the
      conversation or of the turn? G9 — and an ambiguous frame invalidates the
      product's core promise, so this is not a detail.
- [ ] Does an assistant turn reuse the diligence run's event log and state
      machine, or does an interactive run need different terminal semantics?
      A conversation is mostly idle in `awaiting_input` and may never
      "complete".
- [ ] Which of the sixteen services above belong to the runtime intent, the
      experience intent, or a new one? The blueprint deliberately does not
      decide this; it is the ownership question the intent must answer.
- [ ] Does scenario modelling exist in MVP at all? The journey assumes it "if
      available"; G5 says it is absent. Cutting it removes Stage 4 and one of
      only two positive moments in the arc.
- [ ] How does an inadmissible answer get *measured*? If the boundary refuses
      too often the product is useless, and nothing currently counts refusals.
