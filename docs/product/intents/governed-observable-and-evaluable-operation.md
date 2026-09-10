# Governed, Observable, and Evaluable Operation

- **Status:** Draft
- **Kind:** outcome

## Outcome

A completed run can be audited after the fact from recorded evidence alone,
without re-running it and without access to private model reasoning.

That single result decomposes into four sub-results, each independently
verifiable:

1. The sequence of steps a run took is recoverable.
2. The policy decisions applied to that run, and their outcomes, are recorded.
3. Change in quality between releases is measurable against versioned fixtures.
4. Points where a human intervened, or was required to, are identifiable.

Whether a claim was *supported* is a separate property, owned by
[`scoped-context-and-evidence.md`](scoped-context-and-evidence.md). This intent
consumes that contract to decide what a release check may assert.

## Second outcome — the untrusted-content boundary

Two threats, two sub-results, because they do not share a defence.

**1. Retrieved content is not placed in instruction position by construction.**
Content the system retrieved — filings, tool results — does not reach a component
holding tool authority in a form that can act as instruction.
*Falsifying observation:* retrieved free text reaches a component that can invoke
a tool. That is a defect regardless of whether anything downstream detected it.

**2. What an agent may be persuaded to attempt is bounded by what it is
permitted to do.** The user's prompt cannot be kept out of instruction position —
it legitimately *is* the instruction — so the control is authority, not
exclusion.
*Falsifying observation:* a tool invocation succeeds whose arguments exceed the
acting role's ceiling or the initiating user's entitlements. The authority model
itself is owned by
[`portable-identity-first-runtime.md`](portable-identity-first-runtime.md); this
intent depends on it and does not define it.

The charter ratifies the posture behind sub-result 1 in principle 1, and
declines in § Scope to warrant that any demonstrated pattern is effective
against a determined adaptive attacker. This intent does not warrant more than
the charter does: the boundary is a construction, not a guarantee of defeat.

Stated as outcomes rather than controls because the mechanism is an architecture
decision, and the boundary must stay falsifiable if that mechanism is replaced.

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md). This intent carries no ratified constraint of its
own; its scope below is ordinary design surface.

### In scope

- An application-owned policy contract. No policy engine is adopted as an
  unquestioned transparent proxy around the system.
- The untrusted-content boundary — what may reach a component holding tool
  authority, and in what form.
- Redaction or omission of sensitive content before telemetry leaves an
  application boundary.
- Deterministic evaluations, workflow-trajectory checks, regression fixtures,
  and human review.
- The release gate: which checks block a release and which only inform.

This intent owns **what may leave the backend during or after a run** — the
redaction rules and the split between guarded and streamable classes. It does
not own how those events are carried (see
[`portable-identity-first-runtime.md`](portable-identity-first-runtime.md)) or
what the user sees (see
[`multi-workspace-inspectable-experience.md`](multi-workspace-inspectable-experience.md)).

### Excluded

- LLM observability tooling as the workflow source of truth.
- Unredacted intermediate agent content leaving an application boundary.
- Final report text released before its guards have run. Safe workflow status
  events are not covered by this exclusion.

## Owner

eugenelim — decides the policy, telemetry, and evaluation contract.

## Unresolved questions

- At which boundaries is policy evaluated? Inception candidates: input,
  retrieved evidence, tool execution, and user-visible output.
- Which controls belong in deterministic code and which require semantic
  guardrails, and in what order are they applied?
- Is NVIDIA NeMo Guardrails operationally justified for the MVP, or is a
  simpler application-owned policy layer sufficient? *Proposed in `design-doc.md`
  § Alternatives Considered; open until owner sign-off.*
- By what mechanism is the untrusted-content boundary held, and what does it
  cost in analytical capability? *Proposed in `design-doc.md` § Injection
  defence; open until owner sign-off.*
- Should Langfuse be the observability and evaluation plane, and if so should it
  be hosted, self-hosted, or optional? It is an inception candidate, not a
  selection.
- Which instrumentation standard should the system emit? OpenTelemetry is the
  inception candidate; confirm or replace it.
- What content may be recorded in traces?
- Which evaluations block a release versus provide diagnostics?
- How are evaluation datasets and source fixtures versioned?
- What events belong in the application event stream versus telemetry?
- Which pre-release checks flag output, and what happens to flagged output?
  **Reserved carve-out:** the criteria that select output for *automatic*
  publication are ratified in `docs/CHARTER.md` principle 3 and reserved — any
  change to them, in either direction, takes the RFC route. This question owns
  the checks and the handling of flagged output, not the automatic-publication
  criteria.

## Projection

**Depends on:** `portable-identity-first-runtime` (execution topology and
identity boundaries determine where policy can be enforced; and the agent
authority ceiling that sub-result 2 rests on),
`scoped-context-and-evidence` (what an evidence-backed release check can
assert).

**Feeds:** `multi-workspace-inspectable-experience` (which run information is
releasable to its policy and evaluation surfaces).

**Next step.** Settled by the commissioned *Observability and evaluation*
companion document, which the architecture design deferred the telemetry
boundary, redaction rules, evaluation architecture, and fixture versioning to.
That companion does not yet exist.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r5 — untrusted-content outcome split into two sub-results with
  distinct falsifiers, after the single falsifier was found to fire on normal
  operation, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
