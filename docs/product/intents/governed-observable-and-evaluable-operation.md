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

## Boundary

Ratification rules, the candidate list, and the settle order are stated once
in [`README.md`](README.md). This intent carries no ratified constraint of its
own; its scope below is ordinary design surface.

### In scope

- An application-owned policy contract. No policy engine is adopted as an
  unquestioned transparent proxy around the system.
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
  simpler application-owned policy layer sufficient?
- Should Langfuse be the observability and evaluation plane, and if so should it
  be hosted, self-hosted, or optional? It is an inception candidate, not a
  selection.
- Which instrumentation standard should the system emit? OpenTelemetry is the
  inception candidate; confirm or replace it.
- What content may be recorded in traces?
- Which evaluations block a release versus provide diagnostics?
- How are evaluation datasets and source fixtures versioned?
- What events belong in the application event stream versus telemetry?
- What human approval points are necessary?

## Projection

**Depends on:** `portable-identity-first-runtime` (execution topology and
identity boundaries determine where policy can be enforced),
`scoped-context-and-evidence` (what an evidence-backed release check can
assert).

**Feeds:** `multi-workspace-inspectable-experience` (which run information is
releasable to its policy and evaluation surfaces).

Use `architect-design` to establish the policy plane and its enforcement
points, telemetry boundaries and redaction rules, the evaluation architecture
including fixture versioning, the human-intervention model, and the separation
between application workflow state and LLM operations tooling.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r3 — post-shaping-review revision, 2026-09-09
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
