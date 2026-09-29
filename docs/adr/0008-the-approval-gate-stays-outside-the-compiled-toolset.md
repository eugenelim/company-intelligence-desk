# ADR-0008: The approval gate stays outside the compiled toolset

- **Status:** Accepted
- **Date:** 2026-09-27
- **Areas:** agents, authorization
- **Reversibility:** high
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** none
- **Superseded by:** none
- **Superseded in part:** none

## Context

`runtime-architecture.md` r8 § 3, lines 400–403, specifies the approval gate as
conditional *in the compiled toolset*: "the approval-gated tool exists in the
compiled toolset only when a check failed."

`walking-skeleton-step-lifecycle` shipped the opposite and recorded the reason
in the code. `src/ced/agents/tools/approval.py` builds `request_approval` as a
run-time `FunctionToolset`, and `src/ced/worker/executor.py` passes it through
`toolsets=[…]` on the agent call — deliberately outside the compiled stack, so
that the policy decision point never judges it against the acting role's
ceiling. The tool is contentless by DR1: the agent's only lever is to ask.

`walking-skeleton-run-state`'s AC-0302 has to assert that a clean run offers no
callable approval-gated tool. Written against r8's placement, the criterion
reads the compiled toolset — which on the shipped design contains no gated tool
**in every possible world**, so the assertion is true with or without the
control. That vacuity was found by the first pre-EXECUTE review round of the
spec this record serves.

## Decision

- **D1:** **The shipped run-time placement stands, and r8 § 3 lines 400–403 are deviated
from rather than implemented.**
- **D2:** AC-0302 is re-sited accordingly: it asserts over the tool set the model is actually offered at run time, which is where conditionality is decidable on this design.

## Consequences

**What this buys.** Approval stays outside the decision point's authority
check. A gate that the ceiling could refuse is a gate that a role
misconfiguration can silently remove; keeping it out of that path means the
human escalation lever cannot be revoked by a ceiling edit.

**What it costs.** A ratified document now describes a placement the tree does
not have. This record is the deviation's only home — an ADR records a
deviation, it does not amend r8. The r9 consistency pass that reconciles § 3
with the tree is owed and unowned, and is named in
`walking-skeleton-run-state` § Follow-ons.

**Revisit if:** a second tool is added to the run-time toolset seam, or the
policy decision point gains a way to judge a tool without being able to refuse
it — either would change the trade this record rests on.

**What it does not decide.** Whether the run-time toolset seam may carry
anything *other* than the approval tool. Nothing in this delivery adds a second
one, and no criterion bounds it; a spec that adds one inherits an unjudged lane
and owes the bound.

## References

- Deviated from: [`runtime-architecture.md`](../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8 § 3, lines 400–403
- Shipped placement: `src/ced/agents/tools/approval.py`, `src/ced/worker/executor.py`
- Resting criterion: [`walking-skeleton-run-state`](../specs/walking-skeleton-run-state/spec.md) AC-0302
- Framework decision: [ADR-0001](0001-pydantic-ai-as-the-agent-framework.md) D3
