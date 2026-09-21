# ADR-0006: Four r5 deviations for Phase 1, three with named return conditions

- **Status:** Accepted
- **Date:** 2026-09-20 (D3 contingency discharged 2026-09-21)
- **Areas:** schema, cost, configuration
- **Reversibility:** high
- **Decision-makers:** eugenelim (owner)
- **Supersedes:** none
- **Supersedes in part:** none
- **Superseded by:** none
- **Superseded in part:** none

## Context

[`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
r5 was ratified on 2026-09-18. Designing the role-compilation subsystem's
configuration seams found four places where Phase 1 cannot honour it as written:
two invariants blocked on components a later spec introduces, one capability
that a design choice makes unreachable, and one formula the owner has ruled
against. None is a disagreement with r5's intent.

**The pre-request spend bound.** r5 states it in three places: § 1 Goals
("Token spend per step is bounded before the call"), § 4's Spend-ceiling row,
and § 7's Cost scenario, whose consequence if missed is denial of wallet. The
framework supplies the mechanism — `UsageLimits.per_request_input_tokens_limit`
enforced ahead of the request when `count_tokens_before_request` is set. Setting
that flag makes `BedrockConverseModel` issue a separate `bedrock:CountTokens`
call against a geo-prefix-stripped model id, and
[`spikes/README.md`](../../spikes/README.md) establishes those models are not
invocable by raw model id. Enabling the bound in production therefore depends on
an IAM shape nobody has exercised, which
[`walking-skeleton-step-lifecycle`](../specs/walking-skeleton-step-lifecycle/spec.md)
owns because it owns the provider call.

**Content-addressed instruction text.** r5 states it in three places: § 4
"Where instructions live", § 5's object-store row, and § 6's `instruction_ref`
record shape. Its first stated reason is not size — it makes "which exact prompt
did this step receive" answerable from the event log alone. Honouring it needs
the object-store write path
[`walking-skeleton-step-lifecycle`](../specs/walking-skeleton-step-lifecycle/spec.md)
introduces, and converting a populated `instructions text` column to a hash
reference is a narrowing change rather than an expand-only one. The shipped
foundation schema stores the text inline.

**The free-text narrowing (D3).** r5 § 4 admits a `free-text` integration bound
to a quarantined role and to no other. Deriving role class from an empty ceiling
— a role is quarantined exactly when its `ceiling` is empty — makes that
exemption unreachable, because an empty ceiling binds nothing at all. The
capability is not removed from r5; it becomes unexercisable while the derivation
stands, and the trust-class parser's free-text branch ships untested. The live
`walking-skeleton-role-compilation` spec reaches the same conclusion from a
different route, its § Testing Strategy arguing it from AC-0203 and AC-0219;
this record supersedes that paragraph as the home of the reasoning.

**The limits formula (D4).** r5 § 4 states `Effective limits = min(pool default,
role value)`, the permissive reading, while the same row's violated-consequence
is compile failure, the strict one. The owner ruled for the strict reading on
2026-09-20: a role file disagreeing with the limit in force is worse than a loud
failure. That is a replacement of a ratified formula, not an implementation of
it.

A design document cannot suspend, narrow or replace an invariant on its own
authority. r5 is Accepted, a reader of r5 alone would see none of these, and
[`AGENTS.md`](../../AGENTS.md) § Documentation routes why a past choice was made
to `docs/adr/`.

D1 and D2 are decided independently of
[`role-configuration-seams.md`](../architecture/role-configuration-seams/role-configuration-seams.md):
their grounds are framework and provider facts. D4's ground is the owner's
ruling. **D3 alone was contingent** on that document's empty-ceiling derivation
being ratified. That document was ratified on 2026-09-21, so the contingency is
discharged and D3 is accepted outright; if the derivation later changes, D3 is
reopened on its own return condition below.

## Decision

Four deviations are recorded for Phase 1, each with a named owner. D1, D2 and
D3 carry return conditions; D4 stands until the owner reverses the ruling. r5's
revision is unchanged; an erratum line points here.

| ID | Invariant | Change | Returns when | Owner |
| --- | --- | --- | --- | --- |
| **D1** | Token spend per step is bounded before the call (r5 § 1, § 4, § 7) | suspended | The Bedrock IAM shape for `bedrock:CountTokens` against a geo-prefixed model id is re-derived and `count_tokens_before_request` can be enabled in production | `walking-skeleton-step-lifecycle` |
| **D2** | Instruction text is content-addressed and referenced by hash (r5 § 4, § 5, § 6) | suspended | The object-store write path exists, so a hash can be written as well as read | `walking-skeleton-step-lifecycle` |
| **D3** | A `free-text` integration is bindable, to a quarantined role only (r5 § 4) | narrowed to unreachable | Role class stops being derived from an empty ceiling, or a quarantined role gains a way to hold an integration | `walking-skeleton-role-compilation` |
| **D4** | `Effective limits = min(pool default, role value)` (r5 § 4) | replaced by the strict reading | Never, unless the owner reverses the 2026-09-20 ruling | `walking-skeleton-role-compilation` |

Until each returns:

- The per-request token ceiling is **declared** in the role record and enforced
  wherever a counting model is wired. `count_tokens_before_request` stays
  `false` wherever `BedrockConverseModel` is wired — a predicate on the
  deployment, not on the model's capability, because `BedrockConverseModel`
  does implement `count_tokens` and would therefore pass a capability test.
  A runaway loop is bounded in Phase 1 by `request_limit` and
  `tool_calls_limit`, which act after the tokens are spent.
- `agent_role.instructions` holds text inline, and `output_schema_ref` holds a
  closed-set name rather than a hash, for the same reason.
- **D3's ground is the empty-ceiling derivation** § Context states. The
  trust-class parser's free-text branch ships unexercised as a result.

## Evidence

- `pydantic_ai.usage.UsageLimits.per_request_input_tokens_limit` is documented
  on the pinned 2.45.0 as "checked against each request's input token count
  independently — ahead of the request when `count_tokens_before_request`",
  distinguishing it from `input_tokens_limit`, which is cumulative across a run
  and cannot bound a single request.
- `BedrockConverseModel.count_tokens` issues a separate count call whose request
  names the geo-prefix-stripped model id, while `request` uses the inference
  profile or the full name.
- [`spikes/README.md`](../../spikes/README.md) records that these models are not
  invocable by raw model id and that a region-pinned foundation-model ARN is
  denied.

## Consequences

A reader of r5 sees an erratum line naming this record, so neither suspension is
discoverable only from a downstream document. The cost is that r5's § 7 Cost
scenario does not hold in production for Phase 1, and the walking skeleton ships
with a spend bound that acts after the spend rather than before it — acceptable
only because Phase 1 makes no provider call outside
`walking-skeleton-step-lifecycle`'s single criterion and carries no autonomous
loop.

The second suspension costs inspectability, which
[`runtime-architecture.md`](../architecture/inspectable-multi-agent-diligence/runtime-architecture.md)
r8 ranks first of four quality attributes: "which exact prompt did this step
receive" stays answerable by joining mutable state rather than from the event
log alone.

The free-text narrowing costs an untested branch in the trust-class parser, and
the limits replacement costs nothing beyond r5's own text disagreeing with
itself until the erratum is read.

**Residual output- and total-token exposure, recorded here because D1 is why it
matters.** The pool's declarable limit set is the four integer keys
`role-configuration-seams.md` § 4 names; `output_tokens_limit` and
`total_tokens_limit` are not among them. On the pinned 2.45.0 both are
enforceable — `UsageLimits.check_before_request` raises on `total_tokens_limit`
against run-to-date usage, and `check_tokens` enforces both after every
response — so excluding them declines two real run-level bounds rather than two
unavailable ones. With D1 suspending the pre-request input bound, `request_limit`
is the only ceiling left between a looping step and unbounded output spend. That
is acceptable on the same ground as D1 itself and no other: Phase 1 makes no
provider call outside `walking-skeleton-step-lifecycle`'s single criterion. The
Revisit trigger below therefore governs this exposure too.

**Revisit if:** Phase 1 gains a provider call outside
`walking-skeleton-step-lifecycle`'s single criterion, or an autonomous loop that
can spend without a person in the path — either removes the ground on which the
spend suspension is acceptable. Also revisit if the object-store write path
lands before that spec's instruction work, which would make the second
suspension free to lift early.

## Confirmation

- **Mode:** test for D1 and D2; design change for D3; none for D4
- **Signal:** D1 and D2 each **became** a criterion in
  [`walking-skeleton-step-lifecycle`](../specs/walking-skeleton-step-lifecycle/spec.md)
  on 2026-09-21, through the amendment this record obliges. **AC-0271** asserts
  a per-request token bound refuses a request under production wiring;
  **AC-0272** asserts an instruction hash resolves from the event log alone.
  Either going green lifts its row; either staying absent when that spec ships
  is the failure signal. Both are recorded there as return-condition criteria
  excluded from that spec's ship gate, because neither can be green while its
  deviation stands. D1's deployment half — `count_tokens_before_request`
  staying `false` wherever `BedrockConverseModel` is wired — is a separate
  obligation and is asserted where the pool configuration is validated, as
  [`walking-skeleton-role-compilation`](../specs/walking-skeleton-role-compilation/spec.md)'s
  **AC-0270** on its `verify_boot` check, so the mitigation is checked rather
  than remembered.
  D3 is lifted by a design change rather than a criterion, and
  its own signal is the trust-class parser's free-text branch gaining a test.
  D4 has no return condition and no signal; it stands until reversed.
- **Owner:** eugenelim

## Alternatives considered

**Enable `count_tokens_before_request` now and re-derive the IAM shape here.**
Rejected: the provider call belongs to `walking-skeleton-step-lifecycle`, and
`walking-skeleton-role-compilation` makes none, so the spec that would carry the
work has no way to verify it.

**Ship `instruction_ref` against an object store this spec writes.** Rejected:
that spec's § Data and schema records that it writes no payload object, and the
first one is `walking-skeleton-step-lifecycle`'s, which is where object keys
become scope-qualified.

**Leave the deviations recorded only in the design document.** Rejected: r5 is
the Accepted authority, and a deviation visible only to a reader who finds the
downstream design is a trap for the reader who does not.

**Keep `trust_class` declared so the free-text exemption stays reachable (D3).**
Rejected: r5 § 4 refuses a label trusted to be telling the truth, and a declared
role class would reintroduce exactly that.

**Implement the `min()` clamp as r5 § 4 states it (D4).** Rejected by the owner's
ruling of 2026-09-20: under a clamp, lowering the pool default silently tightens
every role, where a build failure is loud.

## References

- [`worker-runtime.md`](../architecture/pydantic-ai-worker-runtime/worker-runtime.md)
  r5 § 1, § 4, § 5, § 6, § 7
- [`role-configuration-seams.md`](../architecture/role-configuration-seams/role-configuration-seams.md)
  § 4, which cites this record rather than carrying the suspensions
- [`spikes/README.md`](../../spikes/README.md)
