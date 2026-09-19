# ADR-0002: The `pydantic-ai` pin is 2.45.0

- **Status:** Accepted
- **Date:** 2026-09-18
- **Areas:** framework, dependencies
- **Reversibility:** high
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** ADR-0001 D5
- **Superseded by:** none
- **Superseded in part:** none

## Context

[ADR-0001](0001-pydantic-ai-as-the-agent-framework.md) D5 pinned
`pydantic-ai` at 2.44.0 — the version Phase 0 spike 7 ran under. Phase 1 adds
the version to a manifest for the first time, which is the moment the pin stops
being a sentence in a decision record and starts being a resolved dependency.

Two facts make 2.44.0 the wrong number to write into that manifest.

**2.45.0 is what was probed.** The behavioural findings Phase 1 depends on were
established against 2.45.0, offline, by importing the package and reading what
it actually exposes rather than what its documentation says. Five of them
matter enough to name, because each one would otherwise be discovered as a bug:

| Probed behaviour | Why it matters |
| --- | --- |
| `result.usage` is a property, not a method | A `usage()` call raises; spend accounting is where that lands |
| `stream_text()` debounces at 0.1 s unless `debounce_by=None` | A streaming test sees one chunk and reads as a collapsed channel |
| `UsageLimits` is a dataclass, not a Pydantic model | `model_fields` does not exist; `dataclasses.fields` does |
| `DeferredToolRequests` re-exports from the package root, but lives in the private `pydantic_ai._deferred` | The approval gate imports from the root, and a contract test pins that import |
| `AgentRetries` carries exactly `tools` and `output`, both zeroable | Retry policy has a known surface rather than an assumed one |

Pinning 2.44.0 while every probe result describes 2.45.0 would mean the
manifest and the evidence disagree, which is the condition ADR-0001's own
mitigation — "exact pinning and contract tests at both seams" — exists to
prevent.

**The delta is additive.** 2.45.0 is a minor release over 2.44.0 under the
vendor's stated policy that additive changes are not breaking. Spike 7's 10/10
hypothesis checks were run under 2.44.0 and are not re-run here; what carries
them forward is that none of the four seams they exercised changed shape.

No code in the walking-skeleton foundation spec imports the framework. The pin
is recorded now because the foundation's dependency-direction gate needs a real
pinned import to forbid, and because a version written into a manifest without
a decision record behind it is exactly the drift this directory exists to stop.

## Decision

- **D1:** The pinned version is `pydantic-ai` 2.45.0, exactly — not a range and
  not a compatible-release specifier. The manifest names the distribution Phase 0
  actually installed, `pydantic-ai-slim[bedrock]==2.45.0`: Bedrock is the only
  provider this design reaches, and the batteries-included `pydantic-ai`
  meta-package pulls every provider extra and pins `starlette` against FastAPI,
  so it does not resolve alongside the API. This supersedes
  [ADR-0001](0001-pydantic-ai-as-the-agent-framework.md) D5 **in part**: D5's
  cardinality (one exact pin) stands and only its value changes. ADR-0001's
  D1–D4 are untouched.
- **D2:** The five probed behaviours in § Context are pinned by contract tests
  owned by `walking-skeleton-agent-runtime`, which is the spec that imports the
  framework. The `DeferredToolRequests` import is pinned **at the package
  root**, because a re-export moving out from under us is additive-minor drift
  the vendor does not class as breaking, and a test that imports the private
  module would pass while the supported path broke.
- **D3:** A version bump is a decision, not a maintenance task: it needs a
  superseding record here and a re-run of the contract tests D2 names, because
  the framework stands on a security boundary that ADR-0001 § Consequences
  already records as the accepted cost of this choice.

## Evidence

Offline probe against `pydantic-ai-slim[bedrock]==2.45.0` in a throwaway
virtualenv, 2026-09-18. No model call, no credential, no spend. Each row of the
§ Context table is one probe result.

**What this evidence does not cover.** The probe read the package's surface; it
did not exercise Bedrock, streaming under a real multi-minute step, or a
message history carrying tool-call parts. Spike 7's limits therefore still
stand as written in [`spikes/README.md`](../../spikes/README.md), and they were
established under 2.44.0 rather than 2.45.0. Nothing here re-establishes them.

## Consequences

**Positive:**

- The manifest and the probe evidence name the same version, so a behavioural
  surprise is a real finding rather than a version mismatch.
- The five probed behaviours become contract tests instead of folklore.

**Negative, and accepted:**

- **Spike 7's green run was under 2.44.0.** Carrying it forward rests on the
  vendor's additive-minor policy rather than on a re-run. Cheap to retire —
  re-running spike 7 costs about $0.006 — and deliberately not done here,
  because `walking-skeleton-agent-runtime` exercises those same four seams
  under 2.45.0 against the real provider and is the stronger evidence.

**Revisit if:** the vendor ships a major version, or any of the five probed
behaviours changes under a minor release, or a contract test from D2 fails for
a reason other than our own code.

## Confirmation

- **Mode:** contract test
- **Signal:** the pin resolves to 2.45.0 in the manifest, and the D2 contract
  tests pass in `walking-skeleton-agent-runtime`. A resolved version other than
  2.45.0, or a failing import pin, is the failure signal.
- **Owner:** eugenelim

## Alternatives considered

- **Keep 2.44.0, the version spike 7 ran under.** Rejected because the Phase 1
  probe findings all describe 2.45.0, so the manifest would contradict the
  evidence the implementation is built from, and the first behavioural
  difference would be debugged as a code defect.
- **Pin a compatible range, `>=2.45,<3`.** Rejected because the framework sits
  on the authorization boundary: ADR-0001 § Consequences records that a change
  to `WrapperToolset.call_tool`'s contract could land in a minor release
  without being classed as breaking, and a range makes that change arrive
  without a decision.
- **Defer the pin until the framework is first imported.** Rejected because the
  foundation spec's dependency-direction gate needs a pinned, installed import
  to forbid — a gate that forbids an absent package cannot be shown failing.

## References

- Framework decision: [ADR-0001](0001-pydantic-ai-as-the-agent-framework.md) D5
- Design: [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
- Prior evidence: [`spikes/README.md`](../../spikes/README.md) § Spike 7
- Consuming spec: [`walking-skeleton-foundation`](../specs/walking-skeleton-foundation/spec.md)
