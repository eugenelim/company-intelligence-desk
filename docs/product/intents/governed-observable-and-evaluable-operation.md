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

Content the system did not author — retrieved filings, tool results, and the
user's own prompt — never reaches a component holding tool authority in a form
that can act as instruction.

**Falsifying observation:** attacker-authored free text reaches a component that
can invoke a tool. That is a defect regardless of whether the tool call was
itself authorized, and regardless of whether anything downstream detected it.

This intent owns that boundary. It is stated as an outcome rather than a control
because the mechanism is an architecture decision, and because the boundary must
remain falsifiable if the chosen mechanism is later replaced.

Two threats sit behind it and do not share a defence. Retrieved content can be
kept out of instruction position. The user's prompt cannot — it legitimately *is*
the instruction — so what an agent may be persuaded to attempt has to be bounded
by what it is permitted to do. The charter ratifies the first half of this
posture in principle 1.

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
  simpler application-owned policy layer sufficient? *Proposed answer in
  `design-doc.md` r6 § Alternatives — detection-based defence rejected as a
  class on cited evidence; open until owner sign-off.*
- By what mechanism is the untrusted-content boundary held, and what does it
  cost in analytical capability? *Proposed answer in `design-doc.md` r6
  § Injection defence; open until owner sign-off.*
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
identity boundaries determine where policy can be enforced),
`scoped-context-and-evidence` (what an evidence-backed release check can
assert).

**Feeds:** `multi-workspace-inspectable-experience` (which run information is
releasable to its policy and evaluation surfaces).

**Next step.** `architect-design` has run: `design-doc.md` r6 settles the policy
plane's enforcement points and the untrusted-content boundary, and awaits owner
sign-off. The telemetry boundary, redaction rules, evaluation architecture, and
fixture versioning were **deferred by that design** to a commissioned
*Observability and evaluation* companion document, which does not yet exist. This
intent is settled by that companion, not by another architecture run.

## Source

- Mode: chat-direct
- Locator: none — content supplied inline in-session; no external locator
- Revision: r4 — gained the untrusted-content boundary outcome; approval question
  narrowed against the ratified charter's reserved criteria, 2026-09-10
- Authority: user-authorized inception input; authority explicitly transferred
  in-session to this repository destination
