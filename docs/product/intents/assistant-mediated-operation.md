# Assistant-Mediated Operation

- **Status:** Draft
- **Kind:** outcome
- **Level:** capability
- **Scale:** app
- **Framed:** 2026-09-18, after the six foundation intents rather than with them

## Outcome

An analyst operates the desk and interrogates its evidence **by conversation**,
and every conversational answer and action is bounded, attributable and
provenanced in exactly the way a run's is.

The second clause is the whole bet. Adding a chat surface to a governed system
is easy; adding one that does not become the way around the governance is the
hard part, and it is what this intent exists to hold. An assistant that can
"do anything the app can do" is, by construction, the widest authority surface
in the product and the one most exposed to injected instructions — so the
outcome is *not* conversational reach. It is conversational reach **that costs
nothing in authority, attribution or provenance**.

**The steerable input** is the share of an analyst's questions that resolve
without leaving the conversation. **The lagging outcome** is judgements reached
per analyst-hour that survive challenge. **The guardrail that must not get
worse** is the proportion of actions carrying a committed policy decision and
the proportion of claims resolving to evidence — both currently required to be
total, and neither may soften because the request arrived as prose.

Six sub-results. Sub-result 1 is a positive requirement; 2, 3, 5 and 6 are
prohibitions, vacuously true of an empty system and given force by 1; 4 is a
paired requirement whose two halves fail in opposite directions.

1. An analyst reaches a defensible judgement through conversation: every claim
   the assistant presents resolves to an evidence item with a locator, or to a
   deterministic calculation with its inputs recorded.
   *Falsified by:* a claim presented in a conversation that resolves to
   neither.
2. No conversational tool invocation succeeds outside the acting role's
   ceiling, outside the initiating principal's entitlements, or without a
   committed policy decision recorded before the action.
   *Falsified by:* a conversational tool invocation succeeding outside either
   bound, or one whose policy decision is absent or committed after the fact.
3. An inadmissible answer is legible as a boundary rather than as a failure:
   where content cannot cross the trust boundary, the analyst receives a typed
   non-answer naming the reason and pointing at the underlying material.
   *Falsified by:* a boundary refusal reaching the analyst as a generic error,
   a silence, or an unexplained omission.
4. A consequential action states its consequence — cost, reversibility and what
   it touches — before it is taken; a cheap, reversible, non-spending action
   does not interrupt.
   *Falsified by:* an action that spends or mutates shared state taken with no
   prior statement of its consequence, **or** a cheap reversible action that
   demands confirmation. Both halves matter: confirming everything and
   confirming nothing fail the same sub-result, because an analyst who stops
   reading prompts is the same outcome as one who was never asked.
5. A hypothetical is never mistakable for a finding: a scenario output carries
   its assumption set wherever it travels.
   *Falsified by:* a scenario output travelling — rendered, copied or exported
   — without the assumption set that produced it.
6. The assistant grants no authority the analyst does not already hold.
   *Falsified by:* the assistant holding authority the analyst does not already
   hold, observed as a conversational action that succeeds where the same
   principal acting directly would be refused.

## Opportunity

Solution-independent, from the job the analyst is doing rather than from the
chat box we are tempted to build. Grounded in
[`agentic-assistant`](../../ux/journeys/agentic-assistant.md), whose
evidence level is **assumption-based** — no interviews or usage data exist, so
every line below is a hypothesis this intent exists to test.

- **Functional job:** reach a judgement about a company as of a date that will
  survive someone else challenging it, without having to learn how the system
  is operated.
- **Emotional job:** to feel *defensible* rather than merely finished. The
  analyst's fear is not being slow; it is being confidently wrong in front of
  someone who checks.
- **Social job:** to be the person whose numbers hold up — able to answer
  "where did that come from" instantly, in front of a reviewer.
- **Struggling moment:** the analyst has a question, the evidence exists in the
  system, and getting from one to the other means knowing which view to open
  and which control to operate. The struggle is not missing data; it is the
  distance between a question and the system's shape.

## Boundary

### Confirmed constraints

**None.** The closed transcription in [`README.md`](README.md) § 1 records
what the owner ratified at inception on 2026-09-09; this intent was framed on
2026-09-18 and carries no inception constraints. It is bound by constraints
owned elsewhere — the agent runtime and identity posture in
[`portable-identity-first-runtime`](portable-identity-first-runtime.md), the
UI framework and workspace views in
[`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md)
— and cites them rather than restating them. Recording an absence here is
deliberate: an empty constraints block and a missing one read the same way
later, and only one of them is a fact.

### In scope

- The **interactive execution plane** and the lifetime of a conversation: how a
  chat turn is dispatched, how a conversation persists across sessions, and how
  it stays distinguishable from a diligence run.
- **Capability legibility** — the analyst's ability to know what an assistant
  may do, derived from stored authority rather than from documentation.
- The **two-outcome trust boundary**: the distinction between output that is
  hostile or malformed and output that is merely inadmissible, and the response
  shape each produces.
- **Consequence before commitment** — what an action costs, whether it reverses,
  and what it touches, established before the analyst is asked.
- **Assumption provenance** for scenario and what-if output.
- The authority relationship between a **module-scoped assistant and the overall
  one**, and how routing between them preserves non-amplification.

### Excluded

- **The chat surface itself** — composer, message rendering, where an assistant
  appears in each module, how a confirmation is presented. Owned by
  [`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md).
  This intent says a consequence must be stated before commitment; it does not
  say what that looks like.
- **The authorization mechanism.** Ceilings, containment and the policy decision
  point belong to
  [`portable-identity-first-runtime`](portable-identity-first-runtime.md). This
  intent requires that conversation be held to them, and adds none of its own.
- **What evidence exists and how it is acquired** — owned by
  [`scoped-context-and-evidence`](scoped-context-and-evidence.md) and
  [`evidence-backed-company-diligence`](evidence-backed-company-diligence.md).
- **Measuring assistant quality** — refusal rates, answer evaluation, telemetry.
  Owned by
  [`governed-observable-and-evaluable-operation`](governed-observable-and-evaluable-operation.md),
  which this intent hands a new thing to measure rather than measuring it here.
- **Analysts authoring their own assistants.** A second *author* is blocked on
  authoring-time containment and on the trust class of non-operator prompts;
  see `portable-identity-first-runtime` § Spec-readiness pressure test. This
  intent assumes assistants are authored by the operator and consumed by the
  analyst, who are currently the same person.

## Assumptions

What must be true for the bet to pay off. Not tested here — `de-risk-intent`
picks the riskiest and predeclares a kill condition.

1. An analyst prefers asking to operating — the distance between a question and
   the system's shape is a real cost, not a designer's assumption. **Weakest
   link:** the journey is `assumption-based`, so this is unevidenced.
2. A boundary refusal, explained well, reads as care rather than incompetence.
   If it does not, sub-result 3 is satisfiable and the product is still
   unpleasant to use.
3. The admitted-type boundary leaves enough signal for conversation to be
   useful. Phase 0 measured causal attribution and untagged narrative failing
   to cross for *reports*; nobody has measured what that costs a *dialogue*,
   which asks "why" far more often.
4. Reusing the run runtime for chat turns is cheaper than a second path, and
   the latency gap closes with a dispatch change rather than an architecture
   change.
5. Graduated confirmation can be derived from declared integration properties
   rather than requiring per-action judgement.
6. The analyst and the operator remain the same person for the life of this
   intent. If they separate, sub-result 6 stops being sufficient and the
   excluded multi-author work becomes a precondition.

**Knowledge surface consulted:** in-repo doc set only — the charter, the six
foundation intents, the runtime architecture and the Phase 0 spike record. No
enterprise knowledge tool or internal CLI was detected, and no user research
exists in this repository, so every opportunity and assumption above is
hypothesis rather than finding and is marked accordingly.

## Owner

eugenelim — decides the assistant's reach, its confirmation posture, and
whether scenario modelling is in the MVP at all.

## Unresolved questions

- Is the analysis frame — company plus as-of date — a property of the
  conversation or of the turn? An as-of analysis with an ambiguous frame is the
  one output the product must not produce, so this is load-bearing rather than
  a detail. *Named as G9 in
  [`agentic-assistant`](../../ux/blueprints/agentic-assistant.md).*
- Does a conversation reuse the run state machine, or does it need different
  terminal semantics? A conversation is mostly idle and may never complete,
  while the run machine's terminal states close the stream.
- Does scenario modelling exist in the MVP? Cutting it removes an entire
  journey stage and one of only two positive moments in the emotional arc.
- What is an acceptable refusal rate, and how would we know it had been
  exceeded? Nothing currently counts boundary refusals, so sub-result 3 can be
  satisfied while the product is unusable.
- Where does a module-scoped assistant's ceiling come from — the module, the
  principal, or their intersection — and does the overall assistant hold the
  union? *Proposed answer in
  [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
  § Authority containment: the root's ceiling is bounded by the initiating
  principal and children narrow from there. **Settled** — that document was
  ratified 2026-09-18. What stays open here is only whether a *module* scope
  narrows further than the principal does.*
- Is the interactive plane a third execution plane, or a pool class of the
  reasoning plane? *Proposed as a pool class; open until owner sign-off.*

## Projection

**Depends on:**
[`portable-identity-first-runtime`](portable-identity-first-runtime.md) for the
runtime, the authority model and the execution plane, and on
[`multi-workspace-inspectable-experience`](multi-workspace-inspectable-experience.md)
for the surface this outcome is delivered through. Both are Accepted; this
intent adds no constraint to either.

**Feeds:**
[`governed-observable-and-evaluable-operation`](governed-observable-and-evaluable-operation.md),
which gains a new thing to evaluate — conversational answer quality and refusal
rate — and
[`adoptable-reference-implementation`](adoptable-reference-implementation.md),
for which a governed assistant is the most transferable pattern in the product.

**Next step.** The experience is mapped
([`agentic-assistant`](../../ux/journeys/agentic-assistant.md)) and blueprinted
([`agentic-assistant`](../../ux/blueprints/agentic-assistant.md)), which named
**nine gaps** between this outcome and the runtime as designed. Two are
structural and need architecture rather than construction: a boundary refusal
is currently a step failure rather than an answer, and readiness is computed
once where the analyst needs it continuously. Those two are the next design
effort. This intent is settled by owner sign-off on that effort, not by another
framing pass.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r1 — framed 2026-09-18 from the agentic-assistant journey map and
  service blueprint, after the owner described the assistant surface as control
  over the application and its data
- Authority: user-authorized in-session; the owner named the capability and
  directed that it be designed as an intent
