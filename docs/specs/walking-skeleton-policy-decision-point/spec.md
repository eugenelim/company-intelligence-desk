# Spec: Walking skeleton — the policy decision point

- **Status:** Shipped <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md), ADR-0002 (version pin, created by the foundation spec)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § 10 Rollout, Phase 1
- **Discovery:** none
- **Contract:** none — this spec exposes no interface surface; it is reached through the foundation spec's API and the evidence spec's state machine
- **Shape:** service

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Agent Rules`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Outcome`, `What Changes`, `Durable Outputs`, `Follow-ons` and
> `Assumptions` are working material, corrected in place as the work teaches,
> without an amendment and without a review round. A review finding against
> working material is advisory — it cannot block, because nothing gates the text
> it cites. Marking the tiers is the spec's job; honouring them when a finding
> is adjudicated is the reviewing surface's.
>
> **A recorded threat, fail direction, or residual gap may sit in any section,
> but removing one always takes an amendment.** § Follow-ons exists to record a
> known gap, so restricting where such a statement may live would forbid that
> section its purpose; what needs gating is deletion, not placement. A control's
> *operative* definition is different and belongs in `Agent Rules` or
> `Acceptance Criteria`.

## Outcome

An engineer can watch an unauthorised tool call be refused at the gate in front
of every tool, with the refusal committed as an event naming the acting role and
the initiating principal before anything runs. Success is that every way the
recording can fail — a lost lease, a dead connection, a predicate that raises, a
ceiling with no entry — has a decided direction, and that none of them turns a
denial into a retry.

## What Changes

- The policy decision point gains its predicate and its denial path — `src/ced/agents/toolsets/policy.py`.
- The `policy.decision` append and its fencing — `src/ced/agents/toolsets/policy.py`, writing through the foundation's append path.
- The duplicate-invocation failure — `src/ced/agents/toolsets/step_events.py`, whose append behaviour this spec supplies.
- The trust-class layer's tool-return path — `src/ced/agents/toolsets/trust_class.py`.
- The stored ceiling's predicate encoding, decoded into the containment fragment's entries — `src/ced/agents/ceilings.py`, new. Revision 0003 put that encoding out of scope and `walking-skeleton-authority-containment` shipped without it, so the predicate has no route from a registry row to `evaluate` until this module exists.
- The compiled stack now carries the real resolver — `src/ced/agents/compiler.py`.
- The fenced step termination the failed-append criteria require, and the read of the initiating principal from the run's `run.requested` event — `src/ced/adapters/postgres/event_log.py`. Both sit beside the `Fenced` mapping they share a fence with; `steps` and `runs` carry no principal column, so that event row is the only durable source AC-0319 can read one from.
- The `entitlements` read the conjunct rests on — `src/ced/adapters/postgres/roles.py`. Nothing in `src/` reads that table today, and it is granted `SELECT` in the same statement as the two tables this adapter already reads.
- A ceiling entry that fails the containment fragment's authoring-time refusals is refused at compile time rather than evaluated, and a `url`-typed argument is refused outright while the public-suffix snapshot is stale — both in `src/ced/agents/ceilings.py`, both beyond any criterion, both ratified and recorded in § Follow-ons.
- `walking-skeleton-role-compilation`'s AC-0234 suite loses one case — the one that drives an admitting resolver through a decision point with no step context and asserts the tool body runs. AC-0209 retires it: an admitted call commits a `policy.decision` first, so an unbound decision point refuses. That criterion's own assertions are untouched.
- The authorization suite, including the grant assertion over the shipped migration — `tests/authorization/`.
- `walking-skeleton-role-compilation`'s AC-0233 suite is removed, because the no-predicate configuration it enumerates stops shipping.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Current architecture | Applicable — `docs/architecture/README.md` § What is built is the current map and this spec changes it | `docs/architecture/README.md` § What is built | work-loop | The decision point moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Current architecture — the `worker-runtime.md` marker | Applicable — r5's STATUS header names the authorization boundary as unbuilt, and this spec is the half that completes it | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` header | work-loop | The authorization boundary moved from unbuilt to built, the other clauses untouched | The header's built and unbuilt lists match the repository |
| Reusable learning | Applicable — this spec produces the authorization evidence Phase 2 plans against | `spikes/README.md` | work-loop | A section stating what was established **and what was not** | Hypothesis checks reported separately from setup |
| Decision rationale | Not applicable — the r5 containment table this Phase 1 work amends is `walking-skeleton-authority-containment`'s, and no ratified rationale changes here | — | — | — | — |
| Interface compatibility | Not applicable — no interface surface; the API belongs to the foundation spec | — | — | — | — |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Agent Rules

The three-tier guard that keeps an implementing agent inside the lines.
*Always do* applies without asking; *Ask first* requires human sign-off
before proceeding; *Never do* is a hard rule, even under time pressure.

### Always do

- Treat r8 and r5 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision. The plan gives every DR decision this spec constructs a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No test-only bypass surface inside a shipped security control.** Fault evidence is produced by patching in the test process, never by a switch the shipped decision point or predicate carries.
- **No widening of the fail-closed default.** Replacing "nothing admits" with a real lookup must not turn a lookup miss into a fall-through. AC-0235 is the guard, and `walking-skeleton-role-compilation`'s AC-0234 — a refusal is never `ModelRetry` nor a subclass — stays green across this spec's work.
- **No decision point that re-reads the current epoch.** The fenced append is only a control if the epoch passed is the one the caller already holds; re-reading it from the database defeats the fence while leaving every other criterion green. AC-0239 is the guard.
- **No `pydantic_ai` import outside `agents/` and `adapters/`.**

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0207, AC-0208, AC-0209, AC-0210, AC-0211, AC-0212, AC-0235, AC-0236, AC-0239, AC-0243, AC-0247, AC-0249, AC-0252, AC-0318, AC-0319)** — all of it, because all of it is a compressible invariant with a cheap oracle and no provider in the loop. The framework ships `TestModel` and `FunctionModel`, so the decision point is exercised without a model call.

No criterion here calls a provider, so this spec needs no cloud credential and
carries no spend.

**Every criterion in this spec reaches the database, and all fifteen carry the
`substrate` marker.** That follows from AC-0209: a call the predicate decides
commits a `policy.decision` before the body runs or the refusal is raised, so
every criterion that drives a call through the decision point reaches Postgres
— including AC-0207 and AC-0208, whose subject is the refusal rather than the
append. AC-0247 runs a tool body, and AC-0249 opens connections directly. The
consequence is stated rather than worked around: **`pytest -m 'not substrate'`
runs none of this spec's suite**, so the offline gate gives no signal here and
the Compose substrate is a precondition for any verification of this contract.

## Acceptance Criteria

Obligations come from `runtime-architecture.md` § 10 Rollout, Phase 1 criterion 6 —
"attempt a well-typed unauthorised tool call and observe refusal" — and from
`worker-runtime.md` § 10 Rollout criterion 5, commit-before-action under
failure. Those two sources cover AC-0207 and AC-0211. AC-0209 is source-derived
too, from r5 § 4's gate block — `may_act(call)` is "recorded as the
`policy.decision`" at call time, on both the admit and the refuse path — rather
than from a § 10 Rollout criterion, which is why it is not tabled below.
Obligations **beyond** them are tabled below, and the approval gate rules on
each rather than inheriting it.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Make a denial catchable without swallowing bugs | AC-0208 | r5 § 2 Structural Model, the toolset stack makes the denial terminal, but no § Rollout criterion asserts how a caller tells a denial apart from a defect. That the refusal is not `ModelRetry` is `walking-skeleton-role-compilation`'s AC-0234, which holds from the first refusal; this criterion asserts a different property, that the denial handler is narrow enough not to catch a tool-body bug | A denial handler swallows genuine defects, and the boundary reports a clean refusal where the system is actually broken |
| Fence the decision append on the caller's own epoch | AC-0239 | r5 § 4 Contracts and Invariants makes the fenced append the control, and the foundation spec built it correctly. Its efficacy rests entirely on the decision point passing the epoch it holds: one that re-reads the current epoch from the database defeats the fence and passes AC-0209, AC-0211 and the foundation's AC-0004 alike. r5 § 4 gives the failure semantics as the fenced worker's decision rolling back, and § 7 prices the consequence as a report published twice | The fence is present, bypassable from the one call site that matters, and green everywhere |
| Force the append failure on a call that would otherwise run | AC-0243 | AC-0211 does not say the call under test is one the predicate admits. Forcing the append to fail on a call that was going to be refused anyway leaves the spy unmoved whatever the ordering, so commit-before-action can be unimplemented with AC-0211 green. `walking-skeleton-authority-containment`'s AC-0218 is the only other admit-path criterion in Phase 1 and carries no append-failure case | The ratified ordering is asserted by a test that cannot observe it |
| Decide the undecidable append failure | AC-0252 | AC-0211 and AC-0243 terminate the step, AC-0239 abandons it on an attributable fence loss, and the discriminator is whether the fence was held. That is knowable from the serialization failure `append_policy_decision` raises and not from a connection-level failure, where the worker cannot tell whether the transaction reached the fence at all. Without a stated direction the exception handler picks one by accident. Terminate rather than abandon, because abandoning turns an authorization decision that could not be recorded into a lease-expiry reclaim and a silent re-execution — the denial-becomes-a-retry shape the design forbids everywhere else | The three criteria partition the space they name and leave a real state outside it, decided by catch order |
| Deny an evaluation that raises | AC-0236 | Three states can reach the decision point: no entry, an entry whose value is outside, and an entry whose evaluation raises — a malformed ceiling row, an unparseable value, a public-suffix dataset that fails to load, an unknown domain type. AC-0235 and AC-0207 cover the first two. Nothing covers the third, and whichever `except` an implementer writes around the predicate silently decides the boundary. The raise is not only an injected fault: [`walking-skeleton-authority-containment`](../walking-skeleton-authority-containment/spec.md)'s AC-0315 fixes the fragment's answer on an input it cannot decide as a raise, so this criterion is the receiving half of that cross-spec seam rather than an assumption about one | The fail direction on an error path is chosen by accident, and no test can go red on the wrong choice |
| Deny a lookup that finds nothing | AC-0235 | `walking-skeleton-role-compilation`'s AC-0233 covers the interval before any predicate exists and cannot be decided once one does. This is the permanent guard: replacing "nothing admits" with a real lookup is exactly where a miss becomes a fall-through, and no other criterion here reaches it — AC-0207 needs a ceiling entry to fall outside of | The split's cheapest regression ships unobserved: a role with no entry for a tool runs it |
| Enforce the entitlements conjunct | AC-0210 | `may_act` is a conjunction of ceiling **and** initiating-user entitlements; a criterion covering only the ceiling half leaves the other unbuilt | Half the authorization predicate ships unverified |
| Assert the grant the split rests on | AC-0249 | r5 § 6 says the privilege split's strength "rests on the database grant rather than on credential separation", and § 4 states the invariant over every runtime identity: no runtime identity holds write on `agent_role` or the integration registry. **AC-0249 deliberately exceeds r5 § 4 by naming `entitlements` as a third object**, because it is the conjunct AC-0210 rests on; aligning the criterion back to r5's two objects would remove half the escalation guard while looking like a correction. `0001_base_schema.py` grants the same SELECT to `app_api` as to `app_worker`, so a criterion naming only one identity covers half the invariant. Every authorization criterion here presumes the identity being constrained cannot rewrite the constraint. That presumption is one `GRANT SELECT` line in `migrations/versions/0001_base_schema.py` that no test would notice losing; the foundation's AC-0005 asserts the adjacent event-type case and not this one. *Subject owner: `walking-skeleton-foundation`, Shipped and frozen, which cannot execute the observation because the identity under test is only exercised once a decision point appends.* | The elevation-of-privilege case the whole design is built against is unasserted, and a migration edit silently removes it |
| Fail a duplicate invocation loudly | AC-0212 | r5 identifies the derived key plus the index as the sole mechanism making the double-publication hazard fail rather than execute twice | The at-most-once control ships with its behaviour untested |
| Admit the positive path | AC-0318 | Every other criterion here is a refusal or a failed append, so a decision point that denies unconditionally satisfies all of them — the same trap `walking-skeleton-authority-containment`'s AC-0218 closes for the fragment. That criterion used to carry this clause and could not observe it, because no tool body runs in a pure domain library; it is rehomed here, where one does | The boundary ships correct by admitting nothing, and the suite agrees |
| Fix where the two identities come from | AC-0319 | `append_policy_decision` takes `principal` and `agent_role` as **caller-supplied parameters** (`migrations/versions/0002_append_paths_and_privilege_split.py`), and AC-0209 requires only that the event *name* them while AC-0210 evaluates entitlements against the initiating user. Neither says where either value is read from. An implementation sourcing either from model-reachable state — a tool argument, model-authored content — passes both criteria while making half the authorization predicate self-asserted, which is the identity-propagation boundary the LLM/agent control asks be named | The agent supplies the identity it is authorized against, and two criteria certify it |
| Exercise the trust-class layer, not just its position | AC-0247 | r5 § 2 makes that layer's innermost position a security property because it must parse an integration's result *before* any layer above observes the return value. `walking-skeleton-role-compilation` AC-0202 asserts the layer is in the chain, and its AC-0220 — met and shipped — covers the same parser on the *retrieval* path. Nothing asserts the layer parses a **tool return**, and this is the first spec where a tool body runs at all. (`walking-skeleton-step-lifecycle`'s AC-0242 also concerns the retrieval path and is still open, so it carries no weight here). *Subject owner: `walking-skeleton-role-compilation`, Shipped and frozen, which composes the layer but runs no tool body against it.* | The layer is composed by one criterion and exercised by none, and free text reaches the attribution record by the one path r5 positions it to block |

**Authorizing a call**

- [x] **AC-0207.** A well-typed tool call whose argument *value* falls outside the acting role's ceiling is refused, and the tool body does not execute.
- [x] **AC-0235.** A tool call for which the acting role holds no ceiling entry at all is refused and the tool body does not execute, asserted with the containment predicate installed, so a lookup that finds nothing denies rather than falling through.
- [x] **AC-0239.** A decision point whose step lease has been taken by **a real second worker holding a later epoch** — not by an injected serialization failure, because a decision point that re-reads the current epoch passes an injected one and fails a real takeover — refuses the call, does not execute the tool body, and leaves no committed `policy.decision`. The evicted worker abandons the step to its new owner rather than failing it.
- [x] **AC-0252.** An append failure the worker cannot attribute to fence loss is treated as fence-held: the worker attempts to terminate the step, as AC-0211 and AC-0243 require. Where the worker had in fact been evicted, that termination is itself a fenced write and the database refuses it, leaving the true owner untouched.
- [x] **AC-0243.** With the `policy.decision` append forced to fail on its own connection inside the decision point while the fence is still held, on a call the installed predicate **admits**, the tool body does not execute and the step terminates.
- [x] **AC-0236.** A predicate evaluation that raises — driven by a fault patched into the predicate **in the test process**, not by a malformed argument and not by a switch the shipped predicate carries — refuses the call, commits the `policy.decision` denial, and does not execute the tool body.
- [x] **AC-0208.** A refusal by the decision point raises a domain exception a caller can catch without also catching a programming error, demonstrated by a case in which a genuine bug raised inside a tool body is not caught by the denial handler.
- [x] **AC-0209.** A call the containment predicate decides — admitted or refused — commits a `policy.decision` event naming the acting agent role and the initiating principal, on the step the call belongs to, before the tool body runs or the refusal is raised. Those are the fields `append_policy_decision` carries; § Follow-ons records that the decision *outcome* and the *identity of the decided call* have no column and are therefore not asserted here. AC-0211, AC-0239, AC-0243 and AC-0252 govern the cases where that append does not succeed.
- [x] **AC-0210.** A call whose arguments fall inside the acting role's ceiling but outside the initiating user's entitlements is refused.
- [x] **AC-0211.** With the `policy.decision` append forced to fail on its own connection inside the decision point while the fence is still held, the tool body does not execute and the step terminates.
- [x] **AC-0212.** A second invocation deriving an idempotency key already recorded for the run terminates the step as a duplicate-detected failure, and the tool body executes at most once across both attempts.

- [x] **AC-0318.** A call the containment predicate admits, whose `policy.decision` append succeeds, executes the tool body exactly once. This is the positive path: every other criterion here is a refusal or a failed append, and a decision point that refuses everything satisfies all of them.
- [x] **AC-0319.** The acting agent role and the initiating principal — both as recorded in the `policy.decision` event and as used to evaluate the entitlements conjunct — are read from the claimed step and its run. A call whose tool arguments or model-authored content carry a different role or principal produces the same decision and the same recorded event.

**Holding the layers and grants the boundary rests on**

- [x] **AC-0247.** A tool return from an integration declared `admitted-types` that carries free text is refused by the trust-class layer before any layer above it observes the value, so neither the step-event toolset's attribution record nor the agent ever sees it.
- [x] **AC-0249.** For every runtime login identity the deployment creates, enumerated at test time from the database rather than from a list written here, a connection on that identity attempting to write `agent_role`, `integration_registry` or `entitlements` is refused by the database. A login role added later is covered without editing this criterion.

## Follow-ons

- `walking-skeleton-step-lifecycle`: **a `policy.decision` cannot say which way it went, or which call it decided.** `append_policy_decision` (`migrations/versions/0002_append_paths_and_privilege_split.py`) inserts `run_id, seq, type, step_id, agent_role, principal, payload_ref`, with `type` pinned to the reserved constant. There is no column for the admit/refuse outcome and none identifying the decided tool call, so two decisions on one step are indistinguishable in the log and a denial cannot be attributed to an action — the repudiation case r5 § 7 prices. AC-0209 is scoped to the fields that do exist. The only carrier is `payload_ref`, whose object-store write path ADR-0006 D2 suspends and assigns to `walking-skeleton-step-lifecycle`; that spec adds the criterion when it opens the path. Chosen on 2026-09-23 over a foundation erratum adding the columns, and over pulling the object write into this spec, because both reopen settled work to close a gap Phase 1's single analysis step cannot yet exercise. Owner eugenelim.
- eugenelim: `src/ced/agents/ceilings.py` — **the public-suffix dataset has no refresh path, and the refusal that bounds it fires at compile time.** `publicsuffix2` bundles a snapshot published 2019-12-21 and has shipped no release since, so every suffix delegated after that date answers "not a public suffix" and is authorable against `walking-skeleton-authority-containment`'s AC-0215. That spec named this spec's ceiling-compile path as the only place enforcement can sit, because integrations are data and registering one is an operator insert that opens no pull request. **Ratified by eugenelim on 2026-09-23**: `src/ced/agents/ceilings.py` refuses to compile a ceiling entry declaring a `url`-typed argument while the bundled dataset is that snapshot. It carries no criterion, on the same precedent and the same grounds as the containment spec's three ratified refusals — the refusal closes a default-allow, and it fails where an operator sees it rather than as an admitted call in production. **What it does not do**: it does not refuse a stale-suffix `host_in_domain` on a non-`url` argument, because no other domain type resolves a host, and it does not make the dataset fresh. Replacing the dataset remains owed and remains an Ask-first dependency change; `workspace.toml` `[backlog].open` carries it as `public-suffix-dataset-has-no-refresh-path`, now with this spec as the enforcement owner.
- eugenelim: this spec § Acceptance Criteria — **the entitlements conjunct trusts an ingress-supplied principal, and nothing in this spec binds that field to an authenticated subject.** `StartRunRequest.principal` (`src/ced/api/models.py`) is a caller-chosen string validated only for length and passed through unchanged (`src/ced/api/main.py`); before this spec it was an attribution label, and AC-0210 promotes it to the key into `entitlements`, which is keyed on `principal` alone. So whoever can reach `POST /runs` selects the entitlements ceiling they are judged against by typing a different name. AC-0319 spends its whole depth stopping the *model* from self-asserting either identity and leaves the *HTTP caller* asserting one freely — that is the half of the identity boundary still open. **The binding control is ratified and outside this spec**: r7 puts OIDC at the ingress, and `CED_API_HOST` defaults to loopback because nothing here is authenticated. Recorded rather than closed, because adding an authentication criterion would build the ingress this Phase deliberately defers; what is owed is that the trust root is named where AC-0210 lives rather than assumed. Found by the implementation security review of 2026-09-23.
- eugenelim: `src/ced/agents/ceilings.py` — **there is no declaration shape that admits a genuinely optional argument, and this spec does not add one.** `evaluate` denies in both directions: an argument the entry constrains and the call omits, and an argument the call supplies that the entry attaches no predicate to. `walking-skeleton-authority-containment` § Follow-ons hands the explicit optional marker here. **Not built, by owner decision of 2026-09-23**, because nothing in Phase 1 declares an optional argument — the skeleton carries one analysis role with one registered tool — so a marker built now would ship with no caller to exercise it and no criterion to red. The trigger is named rather than left to be noticed: the marker is owed when a registry row first declares an argument a call may omit. **What that trigger is not is a refusal that fires.** An earlier wording said the compile path makes the gap visible by refusing an entry the fragment cannot express; it cannot. `declare` iterates only the arguments handed to it and holds no refusal for an entry naming a proper subset of a tool's parameters, and `evaluate` guards omission only for arguments the entry *names* — so an operator who encodes "this argument is optional" by leaving it out of the entry gets a call admitted with the callee's default outside the ceiling entirely, silently, which is the hazard `evaluate`'s own docstring names. The trigger is therefore a registry row a human reads, not a control. Untraced rather than asserted as exposure today: Phase 1 binds every tool to `unresolved_tool`, which takes `**arguments` and binds no default, so no callee supplies one. A coverage refusal — comparing an entry's constrained arguments against the tool's declared parameters — would be a new control beyond every criterion here and is not built. **The refusal and the remedy are different changes in different places, and this entry is filed against the refusal.** The marker itself belongs on the declaration — `declare` and `CeilingArgument` in `src/ced/domain/containment/ceiling.py` — which is `walking-skeleton-authority-containment`'s surface and Shipped, so building it costs an amendment to that spec and a widening of a fragment whose whole value is that every input terminates in one of three outcomes. The compile path can only refuse what it cannot express; it cannot admit an optional argument on the fragment's behalf.
- eugenelim: `src/ced/agents/ceilings.py` — **`fs-path` confinement is still decided against a `realpath` snapshot the callee later re-resolves.** `realpath` runs non-strict, so a component absent at decision time resolves lexically and, if later created as a symlink out of the root, the admitted path points elsewhere when the callee opens it. `walking-skeleton-authority-containment` § Follow-ons hands the close here, and closing it needs an open-then-verify at the callee. **Not built, by owner decision of 2026-09-23**, because Phase 1 has no callee that opens a path: every bound tool resolves to `unresolved_tool`, so there is no `open` to verify after and a guard written now would be dead code no criterion could red. The trigger is the first real tool body that opens a filesystem path, and the obligation travels with `walking-skeleton-step-lifecycle`, which builds the adapter path a body reaches through.
- eugenelim: `src/ced/agents/ceilings.py` — **the admitted call's canonical values reach no layer below, and r5 § 4 rule 3's receiving half lands here.** `evaluate` returns `Admitted(canonical=...)`; `CompiledCeiling.entries_admitting` returns the entry and drops the mapping, and the decision point delegates the original `tool_args`. `walking-skeleton-authority-containment`'s own suite says so in terms — `tests/containment/test_adapter_observes_the_canonical_value.py` establishes that the fragment *emits* the canonical value and states that "the real consumer declines to re-parse the original ... is asserted one spec over", meaning this one. **Not built, and the adjudication of 2026-09-23 split on why.** The security pass ruled it an advisory to be recorded; the adversarial pass refuted it as unreachable, because `_check_public_suffix_dataset` refuses every `url`-typed argument while the bundled snapshot is stale — and `url` is the only domain type whose canonical form differs in the way rule 3 describes — while every tool binds to `unresolved_tool`, which parses nothing. **Recorded rather than built on the narrower ground both agree on**: piping canonical values through would change `CeilingResolver`, which T1's `Tests` pins unchanged so `walking-skeleton-role-compilation`'s AC-0234 stays green, to feed a callee that does not exist. The trigger is the first tool body that parses an argument, and the obligation travels with `walking-skeleton-step-lifecycle`, which builds the adapter path a body reaches through. The one reachable residue today is the `fs-path` window two entries above, which is recorded separately and for the same reason.
- eugenelim: this spec § Acceptance Criteria — **the `policy.decision` cannot carry the denial's reason either, which the first § Follow-ons entry understated.** That entry names two fields the shipped envelope has no column for: the admit/refuse outcome, and the identity of the decided call. There is a third. `_decide` composes a reason, `_record` never receives it, and one layer earlier `entries_admitting` already drops the fragment's own `Denied` text — which `src/ced/domain/containment/ceiling.py` bounds expressly *because* "this text is recorded", truncating a set-valued predicate so an `in_minted_set` denial does not write every minted reference into the log. So a shipped component is authored against a log write that does not happen. Same owner, same carrier and same trigger as that entry: `payload_ref`, whose object-store path ADR-0006 D2 suspends and assigns to `walking-skeleton-step-lifecycle`. Found by the implementation security review of 2026-09-23.
- eugenelim: `worker-runtime.md` r5 § 4 — **`may_run`, the spawn-time containment gate**, the third of the three gates whose call-time member (`may_act`) this spec builds. Recording `role.ceiling ⊆ parent_role.ceiling` as an event at spawn needs a coordinator that spawns children, which this skeleton's single analysis step does not exercise. Named rather than absent. The authoring-time gate, `may_exist`, is `walking-skeleton-authority-containment`'s follow-on for the same reason: that spec owns the authoring surface.

## Assumptions

- Product: the skeleton carries one analysis role with a single registered tool, over the recorded fixture rather than a live corpus — the thinnest agent set that exercises every criterion — and nobody has confirmed it (settled by: the approval gate).
- Process: thirteen of this spec's fifteen criteria descend from `walking-skeleton-agent-runtime`, whose directory was deleted on 2026-09-20, by way of `walking-skeleton-authority-containment`, from which they were cut on 2026-09-22. **The enumeration is recorded here because the parent is gone and cannot be re-derived.** Carried across with wording unchanged: AC-0207, AC-0210, AC-0212. Reworded by owner ruling of 2026-09-20: AC-0208, AC-0209, AC-0211 — AC-0209 was scoped to a call the containment predicate **decides**, and AC-0211 to an append forced to fail **while the fence is still held**, after an adversarial review found both universally quantified over refusals while AC-0239 names a refusal that records nothing; AC-0208 dropped the "not `ModelRetry` nor any subclass" negative, which moved to `walking-skeleton-role-compilation`'s AC-0234. Neither scoping widens authority. Authored new on 2026-09-20: AC-0235, AC-0236, AC-0239, AC-0243, AC-0247, AC-0249, AC-0252. Authored new on 2026-09-23: AC-0318, rehoming the positive path from `walking-skeleton-authority-containment`'s AC-0218, and AC-0319, fixing where the two identities are read from. Beyond the three rewordings, the carried text has not been re-derived against the parent, and with the parent deleted it no longer can be.
- Process: eugenelim approves both the spec and the plan gates. **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
