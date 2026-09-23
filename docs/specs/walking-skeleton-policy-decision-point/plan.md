# Plan: Walking skeleton — the policy decision point

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 2 Structural Model ("The toolset stack, innermost to outermost") and § 4 Contracts and Invariants ("The three gates, and why one formula was not enough"). The production seam already exists: `src/ced/agents/toolsets/policy.py`, shipped by `walking-skeleton-role-compilation`, holds the layer's position, its refusal type and a resolver that admits nothing; `src/ced/agents/toolsets/step_events.py` and `trust_class.py` are composed and inert. **No analogous production implementation exists for the mechanism.** The substitute is `spikes/phase-0/pydantic_ai_bedrock_spike.py`, which holds executable precedent for the `WrapperToolset` authorization hook. **Named deviation:** that spike's hook appended to a Python list — no database, no second connection, no failed-append path — so it is precedent for the *seam*, not for the mechanism AC-0211 asserts.

> **Plan contract:** this is the implementation strategy. It may change
> substantively only while its Status is `Drafting`, before approval records its
> baseline. After approval, `spec.md` and `plan.md` are pinned in substance;
> only lifecycle bookkeeping is permitted, and execution observations belong in
> `docs/specs/walking-skeleton-policy-decision-point/notes/verification-ledger.md`.
> A genuine artifact error follows the controlled-amendment path.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads, and they are pinned. `Design`, `Approach`, `Grounding`
> and `Risks` are working material that an implementer corrects in place only
> before approval: approval hashes the whole plan. After approval, grounding for
> a seam recorded as `no stub (implementation-discovered)` goes to the
> verification ledger; a settled design decision that execution falsified is a
> plan error that follows the controlled-amendment procedure. Treating them as
> contract is how a review spends a round on prose no gate consumes.
> `Grounding` stays *recorded*, because a per-task resolution nobody wrote is
> not grounding; what it stops being is a claim a reviewer holds the plan to.

## Approach

Everything here lands on a seam that already exists and refuses everything.

`walking-skeleton-role-compilation` shipped the decision point's *position* —
outermost in the toolset stack, with a resolver holding no entries, so nothing
admits. This spec supplies the predicate, the denial's exception type, the
denial's event, and the ordering properties that make a failed append a denial
rather than a retry. Its module docstring names the *containment* spec as the
place the predicate arrives — true before the 2026-09-23 cut and wrong after it,
since AC-0235 and AC-0236 moved here. T2 owns repairing that docstring and every
other reference the cut invalidated.

**The riskiest part is that a denial degrades quietly into advice.** The
difference between a terminal denial and a retryable hint is which exception a
future contributor raises, and a green suite looks the same either way.
`walking-skeleton-role-compilation`'s AC-0234 asserts the type and that it is
not the retry type nor a subclass of it, and it runs in this spec's suite.

**The second risk is the fence.** The fenced append is only a control if the
epoch passed is the one the caller already holds. A decision point that re-reads
the current epoch from the database defeats the fence and still passes AC-0209,
AC-0211 and the foundation's AC-0004. AC-0239 is the only criterion that can
see the difference, which is why its test asserts four outcomes and not one.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — `WrapperToolset.call_tool` as the decision point. ADR-0002 pins `pydantic-ai` to 2.45.0.
- `runtime-architecture.md` r8 — ratified with its five accepted limits in § 9 accepted **open**.
- `worker-runtime.md` r5 — see § DR dispositions and § Amendments the worker runtime asked of its parent below.
- **Hard dependency:** [`walking-skeleton-authority-containment`](../walking-skeleton-authority-containment/spec.md) ships the containment fragment and the canonicaliser. This spec installs that predicate and builds no part of it; the authoring-time refusals, the domain types and the canonicalisation rules are all that spec's.
- **Hard dependency:** `walking-skeleton-role-compilation` ships the compiler, the four-layer stack and the fail-closed default. Its AC-0234 must stay green across this work; its AC-0233 is scoped to the no-predicate configuration and AC-0235 replaces it here.
- **Hard dependency:** `walking-skeleton-foundation` ships the schema, both append paths, the privilege split and the pool. Nothing here adds a column.
- **Placement and re-cut rules:** [`docs/specs/README.md`](../README.md) § Cutting one outcome into several specs.
- **Out of scope:** the containment fragment, the canonicaliser and every authoring-time refusal, owned by `walking-skeleton-authority-containment`, which precedes this spec; the compiler and the quarantine boundary, owned by `walking-skeleton-role-compilation`; the provider call, suspension and persistence, owned by `walking-skeleton-step-lifecycle`, which follows it; the run state machine, publication, the browser stream and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

## DR dispositions

The spec makes changing any DR decision an Ask-first boundary, enforceable only
if each carries a disposition. **This table lists only the DRs this spec
constructs.** A DR absent from it is not this spec's; the Phase 1 routing is the
union of this table, the sibling plans' and the foundation plan's, and no plan
restates another's rows.

| DR | Decision | Disposition |
| --- | --- | --- |
| DR2 | Two database roles, one process | **Consumed here** — the decision point appends through the `policy-writer` identity the foundation spec created. The decision itself is the foundation's, asserted there against real roles |

## Amendments the worker runtime asked of its parent

r5 § 10 Rollout records that every amendment this subsystem required is now
folded into `runtime-architecture.md` r8 and is no longer asked for from here,
so there is nothing left for a spec to disposition. r5 names three as
load-bearing for its § 4 invariants: the fenced policy append, the narrowed
decidable fragment, and scope-qualified object keys.

**One of the three is this spec's.** The fenced policy append is the ordering T1
preserves, asserted by AC-0209, AC-0211 and AC-0239. The narrowed decidable
fragment is `walking-skeleton-authority-containment`'s.

## Grounding

The framework-seam probe is recorded once, in
[`walking-skeleton-role-compilation/plan.md`](../walking-skeleton-role-compilation/plan.md)
§ Grounding probe, and is not repeated here. The row this spec rests on is
`WrapperToolset.call_tool` as an overridable seam with signature
`(self, name, tool_args, ctx, tool)`; that spec's T1 contract suite pins it, so
a version bump reds there rather than in this spec's authorization suite.

The seam this spec extends is in the repository rather than in a probe.
`src/ced/agents/toolsets/policy.py` holds `PolicyDecisionPoint`, `CeilingResolver`,
`NoCeilingEntries` and `ToolCallDenied` today, and its docstring states what it
deliberately leaves undecidable — that a lookup *miss* denies is AC-0235, which
is this spec's, because there is no lookup to miss until this spec installs one.
That docstring still attributes AC-0235 to `walking-skeleton-authority-containment`;
T2 corrects it.

## Construction tests

**Integration tests:**
- One denial end-to-end: a call outside the ceiling reaches the decision point, the `policy.decision` event commits on the `policy-writer` connection, the domain exception raises, and the tool body's spy has not moved. This is the spine AC-0207 through AC-0211 read.

**Manual verification:** none. Every criterion here is machine-checkable.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Current architecture — the `worker-runtime.md` marker | T2 | This spec's clause moved from unbuilt to built | The header's built and unbuilt lists match the repository |
| Current architecture — `docs/architecture/README.md` § What is built | T2 | The decision point moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Reusable learning — `spikes/README.md` | T2 | A section stating what was and was not established | Hypothesis checks separated from setup |

## Design (LLD)

Shape is `service`; the sub-sections below are the set that shape selects.

### Design decisions

- **The epoch is passed, never re-read.** The decision point appends on the epoch it already holds from its own claim. Re-reading the current epoch inside the append would make the fence a no-op that every other criterion still passes. Traces to: AC-0239.
- **Fault evidence is produced by patching in the test process.** The decision point ships no disable switch and no injected-failure flag: a security control carrying runtime bypasses to make its own tests expressible is a worse trade than a slightly more awkward test. Traces to: AC-0236, AC-0211, AC-0243, AC-0252.
- **An unattributable append failure is treated as fence-held.** Terminating a step we may not own is safe, because that termination is itself a fenced write the database refuses; abandoning a step we do own turns an unrecorded authorization decision into a silent re-execution. The asymmetry is what picks the direction. Traces to: AC-0252.
- **Both identities are read from the claimed step, never from the call.** `append_policy_decision` takes `principal` and `agent_role` as parameters, so the seam is caller-trusting by construction and the only place that can be closed is the caller. Traces to: AC-0319.
- **The denial handler is narrow by type, not by position.** Catching around the predicate rather than around the tool body is what stops a genuine defect reading as a clean refusal. Traces to: AC-0208.
- *Owned by:* T1.

### Interfaces & contracts

No external interface. The internal seams are the decision point's `call_tool`
override, the `CeilingResolver` protocol the containment spec's predicate
satisfies, the foundation's `append_policy_decision` path on the `policy-writer`
identity, and the step-event toolset's append behaviour. Each is exercised
directly by its own suite. Traces to: AC-0207, AC-0209, AC-0212, AC-0235.
*Owned by:* T1.

### Data & schema

No schema change. AC-0249 *reads* a grant rather than changing one: a red result
stops the task and **escalates to the owner**; no repair is made here, and
`Touches` excludes `migrations/` so none can be. The expand-only erratum route
the foundation spec carries cannot perform this repair: AC-0249 reds when an
identity *holds* a write it should not, and removing that is a `REVOKE`, which
contracts rather than expands. Which route a real red takes — a contracting
migration against a Shipped spec, or a deployment-time role fix — is the
owner's call at the time, and writing one here would pre-empt it. This
spec reads `agent_role` and `entitlements`, and writes `events` through the
append path the foundation spec owns, on the `policy-writer` identity that spec
created. Traces to: AC-0249, AC-0209. *Owned by:* T1.

### Failure, edge cases & resilience

Two orderings carry the story, both ratified and neither negotiable. The
`policy.decision` event commits **before** the invocation it authorises, on a
second connection, and a failed append is a denial rather than a retry. The
failure space is partitioned and every part has a decided direction: fence lost
and attributable — abandon (AC-0239); fence held — terminate (AC-0211, AC-0243);
unattributable — treat as fence-held and terminate (AC-0252); predicate raises —
deny, and record the denial (AC-0236); no ceiling entry — deny (AC-0235).
**And the termination itself can fail**, which the partition above did not
decide and which AC-0252's own trigger reaches: a connection-level fault takes
the `policy.decision` append on the policy connection, and a database outage or
an exhausted pool takes the worker connection beside it, so the fenced write
raises inside the handler that was already handling a failure. The direction is
that it **propagates, chained onto the append failure that caused it, and is
never swallowed** — the natural `try`/`except` around a cleanup is the shape
that continues into the tool body, and continuing is the one outcome every
criterion here forbids. The tool body is already unreachable on this path
because the raise precedes delegation, so what the propagation costs is only
that the step falls to lease-expiry reclaim rather than terminating promptly.
That is the reclaim § Quality attributes would otherwise reject, accepted here
because with no write path open there is nothing to reject it in favour of.
**Not** because the derived idempotency key makes the re-execution benign: an
earlier wording said that and it is false on this path. The key is carried only
by `tool.invoked`, the body never ran, so no row bearing it exists and the
partial unique index has nothing to collide with — and the key is not stable
across the re-planned retry a reclaim produces. What makes the propagation safe
is the sentence above it: the tool body is unreachable because the raise
precedes delegation. The
derived idempotency key plus the foundation's partial unique index make a
duplicate invocation fail loudly: the second append raises, the step-event
toolset does not delegate, and the step terminates as duplicate-detected. The
action executes at most once **per logical invocation** — a duplicate carrying
the same `tool_call_id`, which is the granularity `derived_idempotency_key`
provides — and that is the property the double-publication hazard needs. It is
not at-most-once per action: a reclaim that re-plans mints a fresh
`tool_call_id` and the index admits it, which is the exception the paragraph
above turns on. Traces to: AC-0211, AC-0212, AC-0235, AC-0236, AC-0239, AC-0243,
AC-0252. *Owned by:* T1.

### Quality attributes (NFRs)

Attributability is the ratified goal this spec carries, and it holds over the
calls whose decision was **recorded**: for those, a `policy.decision` event
names the acting role and the initiating principal, and that event is the only
place the decision is recorded. It is deliberately not 100% of refusals. Four
criteria define a denial that commits no `policy.decision` — AC-0239 requires
leaving none, and AC-0211, AC-0243 and AC-0252 terminate the step after the
append fails. Those denials are **not** attributable through the event log at
all, and an earlier wording of this paragraph claimed they were — "through the
step's terminal event and its lease history". There is no step-terminal event
type. `ced.domain.events` names `run.requested`, `run.cancelled`,
`tool.invoked`, `tool.completed`, `role.load.failed`, `role.compile.refused`
and `policy.decision` as constants, and `TERMINAL_EVENT_TYPES` holds
`run.completed`, `run.failed` and `run.cancelled` — all three run-scoped, which
is why none of them closes a step. `release`
appends nothing, and `terminate_step` is a fenced state write on `steps` like
it. What a reader can recover is the `steps` row — its state, its owner and its
epoch — and not a `tool.invoked` row either, because the decision point refuses
above the layer that would append one. So on the paths where the `policy.decision` append
failed **and rolled back**, the event log holds nothing about the authorization
decision. AC-0252's own trigger admits the other direction too, and stating only
the first would understate it: a connection-level fault is indeterminate-commit,
so the append may have committed before the connection dropped and the log may
hold a `policy.decision` for a call that then never executed. The reclaimed
re-execution appends a second one, and § Follow-ons already records that two
decisions on one step are indistinguishable and that neither names its outcome.
So a recorded decision does not imply the call proceeded — which is the harder
half to reconstruct later, and the half a one-directional reading hides. That is the repudiation case r5 § 7 prices, reached by
this design's own failure path, and it is recorded here rather than closed:
adding a step-terminal type is a schema and vocabulary change against a Shipped
sibling, which `walking-skeleton-step-lifecycle` owns along with the
`payload_ref` object write that AC-0209's own § Follow-ons gap waits on. No
criterion here claims otherwise; the claim that did was this paragraph's. Traces to: AC-0209, AC-0211, AC-0239, AC-0243, AC-0252.
*Owned by:* T1.

### Dependencies & integration

**No new dependency.** `hypothesis` and `publicsuffix2` belong to
`walking-skeleton-authority-containment` — the property test and the
public-suffix dataset are both that spec's. The framework is pinned by
`walking-skeleton-role-compilation`; everything else is inherited from the
foundation spec's manifest.

External: none. No task here reaches a provider. *Owned by:* T1.

## Tasks

### T1: The decision point is the only way a tool is reached

**Depends on:** `spec:walking-skeleton-authority-containment/T1`, whose containment predicate this task installs, and `spec:walking-skeleton-role-compilation/T2`, whose no-predicate configuration this task both replaces and retires

**Touches:** src/ced/agents/toolsets/policy.py, src/ced/agents/toolsets/step_events.py, src/ced/agents/toolsets/trust_class.py, src/ced/agents/ceilings.py, src/ced/agents/compiler.py, src/ced/adapters/postgres/event_log.py, src/ced/adapters/postgres/roles.py, tests/authorization/**, tests/compiler/test_whole_tool_surface_refuses.py, tests/compiler/test_decision_point_refuses.py

**Tests:**
- AC-0207 and AC-0208 are the authorization suite. AC-0208 asserts the denial handler is narrow enough not to catch a genuine tool-body bug; a bare "raises" assertion passes on a handler that swallows defects, and the boundary then reports a clean refusal where the system is broken.
- AC-0209 asserts the decision is *recorded* on both paths, which is the attributability claim. The admit path is the one that matters most and the one no other criterion reaches: AC-0243 shows an admit-path append exists by forcing it to fail, and never that it commits when it succeeds.
- AC-0210 uses a call inside the role ceiling and outside the initiating user's entitlements, which is the conjunct no ceiling-only test reaches.
- AC-0211 forces the decision append to fail on its own connection **with the fence still held**, arranged by keeping the lease live and injecting a serialization failure rather than a connection-level one, and asserts the tool body did not run using a spy the body increments. The spy is what makes "did not run" observable rather than inferred.
- AC-0212 drives two invocations deriving the same key and asserts the body ran once and the step terminated duplicate-detected.
- AC-0239 runs a decision point whose lease was taken by another worker and asserts all four outcomes: refusal, no committed decision, unmoved spy, and the step still claimable by its new owner rather than carrying a terminal event. AC-0211 carries the fence-held qualifier, so the two do not disagree; the fourth outcome is what distinguishes them and a test that skips it leaves the discriminator unobserved.
- AC-0239 additionally asserts the epoch the append receives is the one the caller held, not one re-read inside the append. Without that assertion a re-reading implementation passes every other criterion in this task.
- AC-0252 injects a connection-level failure rather than a serialization failure, with the lease intact, so the worker cannot attribute it, and asserts the worker attempts termination.
- AC-0243 is AC-0211's admit-path twin and must be written as its own case: same forced append failure, but on a call the predicate admits, so the spy would move but for the ordering.
- AC-0247 drives a tool body whose return is free text and asserts the step-event toolset's attribution record never held it. Asserting only that the step fails would pass on a layer that parses too late.
- AC-0249 opens a connection as each runtime identity in turn and attempts a write to each of the three tables, asserting the database refuses. The application cannot be the thing that refuses, or the criterion tests the caller rather than the grant.
- AC-0236 injects a fault inside the predicate itself, so the error path is exercised rather than a malformed argument that the predicate handles normally. It asserts all three outcomes together — refusal, the committed denial, the unmoved spy — because an error path that denies without recording is the failure this criterion exists to catch.
- AC-0235 drives a call to a tool the acting role has no ceiling entry for, with the real predicate installed and the same spy AC-0211 uses. It is the only check here that a lookup finding nothing denies: AC-0207 needs an entry to fall outside of, and `walking-skeleton-role-compilation`'s AC-0233 was scoped to a configuration this task removes.
- `walking-skeleton-role-compilation` AC-0234 runs unchanged in this task's suite. It asserts a refusal is not the retry type, in every configuration; AC-0208 asserts the handler that catches a denial does not also catch a programming error. The two texts do not overlap, so neither restates the other.
- AC-0318 drives a call the installed predicate admits with the append succeeding, and asserts the same spy every refusal case uses moved exactly once. Every other case in this task asserts the spy did **not** move, so without this one the whole suite passes on a decision point that denies unconditionally.
- AC-0319 drives a call whose tool arguments carry a different `agent_role` and `principal` from the ones on the claimed step, and asserts both the decision and the committed event match the step's values. Asserting only that the event is well-formed would pass on an implementation reading either value from the call.
- AC-0212's mechanism is in the step-event toolset, which `walking-skeleton-role-compilation` composes as a layer but leaves inert. This task gives it the append behaviour, which is why its file is in Touches.
- The files added to `Touches` by the amendments of 2026-09-23 carry no criterion of their own. The property that forces each, rather than a list that reads as exhaustive: **every criterion needing a call the installed predicate *decides* needs a decoded ceiling entry, and every criterion needing a *recorded* decision needs somewhere to record and somewhere to terminate.** `src/ced/agents/ceilings.py` decodes a stored `ceiling` entry's `predicates` into the containment fragment's `CeilingEntry`, which is the encoding revision 0003 left out of scope and `walking-skeleton-authority-containment` shipped without — AC-0207, AC-0210, AC-0235, AC-0236, AC-0243 and AC-0318 all rest on it. `src/ced/adapters/postgres/roles.py` gains the `entitlements` read: the table is created and granted `SELECT` in the same statements as `agent_role` and `integration_registry`, which that adapter already reads, and nothing anywhere in `src/` reads it today, so AC-0210 and AC-0319's entitlements conjunct has no source without it. `src/ced/agents/compiler.py` installs the resolver those two build, because a predicate nothing wires in is a predicate no compiled stack holds. `src/ced/adapters/postgres/event_log.py` gains `terminate_step`, the fenced write AC-0211, AC-0243 and AC-0252 require, and is also where AC-0319's principal is read — `events.principal` on the run's `run.requested` row is the only durable home for it, `steps` and `runs` carry no such column, and `app_worker` holds `SELECT` on `events`. Both live in the adapter rather than as raw SQL in the agents layer. `tests/compiler/test_decision_point_refuses.py` loses one case: it builds a decision point with an admitting resolver and **no step context** and asserts the tool body runs, which AC-0209 retires — an admitted call now commits a `policy.decision` first, so an unbound decision point must refuse. AC-0234's own assertions in that file are untouched and stay green.
- **Every ceiling entry `src/ced/agents/ceilings.py` builds is built through `declare`**, the containment fragment's authoring surface, and an entry `declare` refuses is refused at compile time rather than handed to `evaluate`. This holds for every stored ceiling the spec decodes — `agent_role.ceiling` and `entitlements.ceiling` alike, which are the same decidable fragment — and `ceilings.py` is the only decoder. It is not an implementation preference. `evaluate` re-checks only a missing argument, an argument no predicate ranges over, and an unrecognised domain type, and the first of those has no `declare` counterpart at all; every other refusal `declare` holds is unrepeated. `CeilingEntry` is a directly constructible frozen dataclass and both columns are bare `jsonb` with no CHECK, populated by operator insert, so a decoder that built the dataclass itself would admit a stored row encoding `scheme_in{file}` beside a host prefix — or `within("")`, which a bypassing decoder leaves un-canonicalised so that `admits` compares with `startswith("/")` and admits every canonical path, `declare` refusing it on the absolute-root check before any canonicalisation runs — with AC-0207, AC-0210, AC-0235, AC-0236, AC-0243 and AC-0318 all green. That is the fail-closed widening this spec's second `Never do` forbids, reached through the one path § Follow-ons names as the only enforcement point there is. **The obligation is the property, not a tally**: a check drives a stored row violating *each* refusal `declare` holds that `evaluate` does not repeat, read off `src/ced/domain/containment/ceiling.py` as it stands rather than off a count written here, so the obligation tracks the fragment rather than a number. **Each check asserts the refusal it names, not merely that compilation refused.** Four of those refusals are reachable only through a `url`-typed argument — `host_in_domain` over a public suffix, no host-constraining predicate, no `scheme_in`, and `scheme_in` outside `RESOLVABLE_SCHEMES` — and the ratified dataset refusal below rejects *every* `url` entry while the snapshot is stale, so a check asserting only "compilation refused" is green on an implementation that never routes a `url` entry through `declare` at all. Each check therefore names the refusal under test and must go red when `declare` routing is removed; the four `url`-family checks reach `declare` by suppressing the dataset refusal in the test process, the same way every other fault here is injected. **What the checks do not establish**, recorded because two of them cannot be made to: the drift claim is only as good as somebody re-reading the fragment, since nothing mechanical notices a refusal added to a Shipped sibling's module, and the no-canonical-form site is a union over every `ContainmentUndecidable` the canonicaliser can raise, so a check on one cause discharges the site rather than the cause set. An earlier wording of this bullet enumerated six and quoted guard counts the code contradicts; the one it omitted was the no-canonical-form refusal. Any guard or criterion counts that round-2 entry quotes were the wording then held, and the code contradicts them.
- **The `predicates` decode is total and refusing.** `declare` takes already-constructed `Predicate` objects, so it cannot refuse a conjunct it never received: a decoder that skipped an unrecognised predicate kind, an unrecognised key or a malformed element would hand `declare` a strictly *weaker* conjunction than the stored row expresses, `declare` would accept it because every surviving predicate is well-formed, and the ceiling would silently widen with the whole suite green. Routing through `declare` does not reach this, and neither does `evaluate`. So a stored element must match the recognised shape **exactly** — every required key present and its value carried from the row — and any element, key or predicate kind `ceilings.py` does not recognise, **or any required key the row omits**, refuses the whole entry at compile time rather than being dropped, narrowed, defaulted or coerced. **Absent is as dangerous as unrecognised, and more quietly so**: a decoder that supplied a constructor default for a missing payload key would build a well-formed, expressible predicate `declare` has no refusal for. Measured against the installed fragment, `declare` accepts an argument constrained by `Prefix(value="")` and `evaluate` then admits every string — so `{"kind": "prefix"}` with no payload becomes an unconditional admit on an argument that reads as constrained. Nothing may be synthesised that the row does not contain — the rule `src/ced/adapters/postgres/roles.py` already states for the role record, "Refuse, never coerce, and name what failed", applied to elements. Two checks: one drives a stored entry carrying an unrecognised predicate kind beside a valid one, the other an entry whose recognised kind omits a required payload key, and both assert compilation refuses. **No element is exempt on the strength of a denial path that does not exist.** An earlier wording carved out "an entry that declares no predicates at all" as denied by lookup miss; neither reading of that phrase is true. An argument carrying an empty predicate tuple is refused by `declare` itself, so it is a compile-time refusal; and an entry naming *no arguments* is accepted by `declare`, is found by lookup, and `evaluate` returns `Admitted` for a call supplying none — so it admits rather than contributing nothing. A ceiling row carrying no predicate encoding therefore contributes no entry to the resolver **because `ceilings.py` installs none for it**, which is what makes AC-0235's lookup miss the outcome; it is not something the fragment does on its own.
- **The offline gate loses its only admit-path discriminator, and AC-0318 becomes the sole guard.** The retired case above is the one check in the repository that drives an admitting resolver through the layer and asserts delegation, and it runs offline. Its replacement carries the `substrate` marker like everything else here, so after T1 `pytest -m 'not substrate'` is green on a decision point that denies unconditionally. Recorded rather than repaired: binding a step context needs a database, so an offline admit-path case cannot exist once AC-0209 requires the append. § Testing Strategy already states the offline gate gives no signal on this spec's own criteria; what is new is that an inherited offline check is lost too.
- The public-suffix refusal is beyond every criterion here and is **ratified by the owner on 2026-09-23**, on the containment spec's own precedent for a fail-closed refusal with its grounds in § Follow-ons. `src/ced/agents/ceilings.py` refuses to compile a ceiling entry declaring a `url`-typed argument while the bundled suffix dataset is the stale snapshot `PUBLIC_SUFFIX_DATASET_AS_OF` names. Registering a URL-taking tool then fails loudly at compile time, which is the first moment the AC-0215 gap becomes reachable; today nothing registers one, so the refusal fires nowhere and the check that proves it can fire drives a registry row of its own.

**Approach:**
- The decision point appends through the `policy-writer` identity on a second connection, taking the `steps` fence first so the ordering the foundation spec proved is preserved rather than extended.
- The epoch travels from the worker's claim into the append as a parameter. No code path inside the decision point reads the current epoch from the database.

**Done when:** AC-0207 through AC-0212, AC-0235, AC-0236, AC-0239, AC-0243, AC-0247, AC-0249, AC-0252, AC-0318 and AC-0319 are green; `walking-skeleton-role-compilation` AC-0234 is still green; and that spec's AC-0233 suite is removed in this task, because the no-predicate configuration it enumerates no longer ships.

### T2: Every reference names the spec that now owns it

**Depends on:** T1

**Touches:** src/ced/agents/toolsets/policy.py, src/ced/agents/toolsets/step_events.py, src/ced/domain/events.py, tests/compiler/test_decision_point_refuses.py, tests/event_log/test_idempotency_index.py, docs/architecture/README.md, docs/specs/walking-skeleton-step-lifecycle/spec.md, docs/specs/walking-skeleton-step-lifecycle/plan.md, docs/specs/walking-skeleton-evidence/spec.md, docs/specs/walking-skeleton-evidence/plan.md, docs/specs/walking-skeleton-role-compilation/notes/erratum-2026-09-23-ac-0233-retirement-trigger.md, docs/specs/walking-skeleton-authority-containment/spec.md, workspace.toml

**Tests:**
- `grep -rn "walking-skeleton-authority-containment" src/ tests/ docs/` returns no hit that attributes a moved criterion — AC-0207 through AC-0212, AC-0235, AC-0236, AC-0239, AC-0243, AC-0247, AC-0249, AC-0252 — or the decision point itself to that spec. A hit that legitimately concerns the containment fragment stays. This is the task's own gate and it is why `Touches` is wide and shallow.
- The two downstream specs' hard-dependency lists name `walking-skeleton-policy-decision-point`, matching the `needs` edges `workspace.toml` already declares. A dependency list that disagrees with the index is the drift this check exists to catch.
- The `public-suffix-dataset-has-no-refresh-path` entry in `workspace.toml` `[backlog].open` states that this spec owns enforcement, and stops saying "unowned until that spec takes it". `spec.md` § Follow-ons claims the register carries that ownership; until this task edits the entry, the register contradicts the claim. The same stale sentence is mirrored in `walking-skeleton-authority-containment`'s § Follow-ons and is corrected in the same task. **The grep gate does not reach it and this bullet no longer claims it does**: that gate greps for the literal `walking-skeleton-authority-containment`, and the mirrored sentence does not contain it — the sentence names *this* spec as the enforcement owner and only trails off with "unowned until that spec takes it", so it attributes nothing and produces no hit. It is a separate obligation for that reason, and `Done when` carries it.
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green, including its dangling-reference invariant.

**Approach:**
- `walking-skeleton-role-compilation` is Shipped and its § Acceptance Criteria is amendment-governed, so AC-0233's row — whose **Retirement trigger** names containment's T2 — cannot be edited, and `docs/specs/README.md` forbids editing a frozen body. Record the correction as an erratum note in that spec's `notes/`, beside the existing `amendment-2026-09-21-stub-formatting.md`, naming this spec's T1 as the task that actually retires the suite.
- Do **not** open a `[backlog].open` entry on `docs/specs/walking-skeleton-role-compilation/spec.md`. That path is in `[work].shipped`, and a second membership raises `duplicate_membership` on that path plus `unsatisfied_dependency` on the three specs downstream of it. The colliding entry was removed on 2026-09-23 in this same change; the erratum note records the measured effect and the history.
- The `workspace.toml` initiative comment still describes three runtime specs and a four-spec dependency chain. Rewrite it to match the `needs` edges below it, including the 2026-09-23 cut.

**Done when:** the grep gate returns no misattributed hit, the erratum note exists and names T1, the two downstream dependency lists match the index, the public-suffix backlog entry names this spec as the enforcement owner, neither that entry nor `walking-skeleton-authority-containment`'s § Follow-ons still says the enforcement is unowned, and the status lint is green.

### T3: The record says what this spec established and what it did not

**Depends on:** T2

**Touches:** spikes/README.md, docs/architecture/README.md, docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md

**Tests:**
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.

**Approach:**
- State plainly that the authorization criteria establish the decision point refuses, records and orders correctly against injected faults, and establish nothing about a failure mode nobody has injected.
- Update `docs/architecture/README.md` § What is built, which is the map where partial progress is expressible. r5's STATUS header lists the authorization boundary as unbuilt; this spec is the half that completes it, so the clause moves here and not in the containment spec. Move that clause only.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** three stacked PRs — T1, T2, T3. Each leaves the repository working and is independently reviewable. T2 is wide and shallow — a rename sweep with a grep gate — and is deliberately not folded into T1, whose diff is the security-boundary change a reviewer must read closely.
- **Review shape:** T1 is **DEEP** and is sized as its own PR for that reason: it is security-boundary work that attracts a mandatory security review, and it carries a failure mode that is invisible in a passing suite. If its diff outgrows one reviewable unit it splits at the seam between the decision point proper and the step-event toolset's append behaviour, which are independent mechanisms sharing only the suite. No task here is WIDE.

## Risks

- **Denial-as-retry is a one-line footgun.** The difference between a terminal denial and a retryable hint is which exception a future contributor raises. `walking-skeleton-role-compilation`'s AC-0234 asserts the negative; the risk is named because it is the regression reviews miss.
- **The fail-closed default can be quietly widened here.** This is the spec that replaces "nothing admits" with a real lookup, and the cheapest way to make the containment spec's positive path pass is to let a lookup miss fall through. AC-0235 exists for that reason, and AC-0234 runs in T1's suite alongside it.
- **The fence can be defeated from inside.** Re-reading the epoch is a natural-looking refactor that leaves the fence syntactically present and semantically absent. AC-0239 catches it because its text requires a real second worker holding a later epoch rather than an injected serialization failure; against an injected failure a re-reading implementation passes every outcome the criterion names. T1's epoch-parameter assertion is a second, redundant guard on the same property.
- **The decision point stands on a framework object.** A change to the wrapper's `call_tool` contract is a change to the authorization boundary and could land in a minor release without being classed as breaking. Mitigated by the contract suite `walking-skeleton-role-compilation` T1 ships and by the authorization suite running on every build.
- **A schema need discovered here is an amendment to a shipped sibling spec.** Mitigated by the foundation spec creating the three agent tables up front, but not eliminated.

## Changelog

- 2026-09-22: initial plan. Cut from `walking-skeleton-authority-containment` by owner decision, taking that spec's decision-point lobe — its T2 — as a spec of its own. The containment fragment stays there and ships first; this spec declares a hard dependency on it. The two lobes were already sized as separate PRs, and the cut makes the dependency edge and the two review surfaces explicit rather than implied.
- 2026-09-23: round-2 spec-stage adversarial and security findings applied before first approval. **AC-0209 narrowed** to the fields `append_policy_decision` actually carries: the shipped events envelope has no column for the decision outcome and none identifying the decided call, and ADR-0006 D2 suspends the `payload_ref` object-store path until `walking-skeleton-step-lifecycle` opens it. The owner chose narrowing on 2026-09-23 over a foundation erratum and over pulling the object write forward; § Follow-ons carries the gap with that spec as owner. **AC-0249** now quantifies over every runtime login identity the deployment creates rather than naming two, because `deploy/postgres-init/01-roles.sql` creates a third, `app_policy`, which this spec puts to work. **AC-0239** now requires a real second worker holding a later epoch rather than an injected serialization failure, which is what makes it the guard its `Never do` rule claims. **T2 was added** to own the reference repair the cut created. All three criterion changes were authorized by the owner on 2026-09-23.
- 2026-09-23, round 3: the review loop was stopped rather than run to clean, on the diverging-loop condition recorded in the sibling plan's Changelog — findings rose 19 → 21 → 29 across three rounds with about half of round 3 introduced by round-2 repairs. Two criteria were added from that round's findings. **AC-0318** is the positive path, rehomed from `walking-skeleton-authority-containment`'s AC-0218, which asserted a tool body executes in a spec where none runs; without it every criterion here is a refusal or a failed append and a decision point that denies unconditionally passes the suite. **AC-0319** fixes where the acting role and initiating principal are read from, because `append_policy_decision` takes both as caller-supplied parameters and nothing said they come from the claimed step rather than from model-reachable state. § Testing Strategy now states plainly that all fifteen criteria carry the `substrate` marker and that `pytest -m 'not substrate'` gives no signal on this spec. Left open and recorded rather than repaired: the exception type crossing the AC-0315 / AC-0236 seam, which T1 settles in code.
- 2026-09-23, amendment: **T1's `Touches` was short of four files it cannot avoid editing, and its `Tests` was short of one refusal.** Authorized by eugenelim on 2026-09-23 as a single consolidated amendment, taken on the hand-reset route — Approved to Drafting, amend, re-approve — the same shape `walking-skeleton-authority-containment`'s AC-0216 amendment took on 2026-09-23 and for the same reason: `no-lifecycle-route-for-widening-an-approved-unsealed-contract` in `[backlog].open` records that no documented transition covers it, and the engine's `contract-amendment` event is reachable only from `CODE-IMPLEMENTATION`, which this run cannot enter without the amended `Touches`. **That is a second precedent, not a sanctioned route**, and it is recorded as one. Added: `src/ced/agents/ceilings.py`, `src/ced/agents/compiler.py`, `src/ced/adapters/postgres/event_log.py` and `tests/compiler/test_decision_point_refuses.py`, each with the criterion that forces it in the `Tests` bullet above. **Declined:** amending after the fact and recording the four files in the verification ledger, because `Touches` is a pinned field a completion gate reads and the ledger is for observations, not for obligations; and working inside the unamended `Touches`, which leaves `tests/compiler/test_decision_point_refuses.py` red at T1's boundary and so fails T1's own `Done when` and the Rollout statement that each task leaves the repository working. The acceptance-criterion set is **unchanged**: the public-suffix refusal ships as a ratified fail-closed refusal recorded in `spec.md` § Follow-ons, on the containment spec's precedent, rather than as a new criterion — which is what keeps this amendment inside `Touches` and `Tests` and out of the widening route the backlog entry describes.
- 2026-09-23, amendment round 2: the pre-EXECUTE adversarial and security reviews of the first amendment each sustained one Blocker through adjudication, and both were defects in that amendment rather than in the approved contract. **The `entitlements` read had no home in `Touches`** — nothing under `src/` reads that table, and AC-0210 and AC-0319 both rest on the conjunct; `src/ced/adapters/postgres/roles.py` is added, the adapter that already reads the two tables granted `SELECT` in the same statement. **The stored-ceiling decoder was not required to apply the authoring-time refusal set** — `evaluate` re-checks three of `declare`'s nine guards, `CeilingEntry` is directly constructible and `agent_role.ceiling` is bare `jsonb` populated by operator insert, so a decoder building the dataclass itself would admit a stored `scheme_in{file}` beside a host prefix with five criteria green; T1's `Tests` now requires every entry to be built through `declare`, with a check driving a violating stored row per refusal. Both fixes stayed inside `Touches` and `Tests`; the criterion set is still unchanged. Also taken, all advisory: the `ceilings.py` justification now states the property that forces each added file rather than a list that read as exhaustive; `Tests` records that the offline gate loses its only admit-path discriminator and that AC-0318 becomes the sole guard; § Quality attributes stops claiming these denials are attributable through a step-terminal event, because no such event type exists; § Failure decides the direction for a termination that cannot be performed; § What Changes and § Follow-ons gained what the amendments ship, including the entitlements conjunct's unnamed trust root; and T2 now has to make the `workspace.toml` public-suffix entry state the ownership § Follow-ons claims. **Declined:** four security findings and four adversarial findings were refuted on adjudication and are not acted on — among them that AC-0319's principal is unreachable inside `Touches` (it is: `events.principal` on the `run.requested` row, read through a file already listed), that AC-0252 fails to assert the unmoved spy (it carries the obligation by reference to AC-0211 and AC-0243), that a missing `entitlements` row needs its own criterion (§ Never do already forbids any lookup miss falling through), and that terminating in the expiry-before-reclaim window is a defect (it is the ratified direction, chosen so an unrecorded decision does not become a silent re-execution). The paired audits are retained under `.context/reviews/`.
- 2026-09-23, amendment round 3: round 2 of the pre-EXECUTE reviews sustained **one** Blocker, down from two, and it was again a defect in the previous round's repair rather than in the approved contract. **The `predicates` decode had no stated refusal for an element it does not recognise.** Routing entries through `declare` does not reach it: `declare` takes already-constructed `Predicate` objects, so a decoder that dropped an unrecognised kind or key would hand it a strictly weaker conjunction, `declare` would accept it because every surviving predicate is well-formed, and the ceiling would silently widen with the authorization criteria green. T1's `Tests` now requires the decode to be total and refusing, on the "Refuse, never coerce" rule `src/ced/adapters/postgres/roles.py` already states for the role record, with a check driving a stored entry carrying an unrecognised kind beside a valid one. Also taken, all advisory: the declare-routing bullet now states the property — a check per refusal `declare` holds that `evaluate` does not repeat — instead of enumerating six and quoting guard counts the code contradicts, because the refusal the six omitted is the no-canonical-form one, and `within("")` canonicalises to `/` and admits the whole filesystem, which is wider than the `scheme_in{file}` case the bullet cited as its own grounds; the bullet now also says explicitly that it covers `entitlements.ceiling` as well as `agent_role.ceiling`. § Failure drops the claim that the derived idempotency key makes the post-termination reclaim benign — the key is carried only by `tool.invoked`, the body never ran, so no row bearing it exists and the index has nothing to collide with; the real reason is the one the preceding sentence already gave, that the raise precedes delegation. § Quality attributes now states both directions of the unattributable path, since an indeterminate commit can leave a `policy.decision` for a call that never executed. The event-type enumeration is corrected. T2 stops claiming its grep gate covers the mirrored stale sentence in the containment spec — that gate greps for a literal the sentence does not contain — and carries it as its own `Done when` obligation instead. § Follow-ons stops crediting the compile path with a refusal it does not hold: `declare` has no coverage check over a tool's parameters, so an operator encoding optionality by omission is silently narrowed, and the optional-argument trigger is a registry row a human reads rather than a control that fires. **Declined:** two security findings and one adversarial finding were refuted — that the entitlements ceiling fell outside the declare-routing sentence (the adjacent bullet already assigns every stored-ceiling decode to one module), that an unperformable termination reaches the tool body (the raise precedes delegation), and that T1's `Done when` must restate obligations its `Tests` already pins (all three fields are pinned, so restating would duplicate rather than gate).
- 2026-09-23, amendment round 4, and **the pre-EXECUTE review loop was stopped here by owner decision rather than run to clean** — the same diverging-loop condition on which the owner stopped `walking-skeleton-authority-containment`'s third round on 2026-09-23. The diagnosis differs from that one and is recorded because it changes what the stop costs. Sustained Blockers ran 2, then 1, then 2, and **every one was a defect in the previous round's repair prose, not in the approved contract**: the criterion set has been unchanged and unchallenged across all three rounds. What kept failing review was plan text describing an implementation that does not exist, and each round's more elaborate description introduced fresh surface for the next. The questions now outstanding — can this check go red, what does `declare` do with an empty tuple — are settled by code and mutation proof in minutes and by prose only provisionally, so the remainder moves to T1 and to the verification ledger. Repaired before stopping, because each was determinate: **the decode must match the recognised shape exactly**, every required key present and carried from the row, with nothing synthesised — absent is as dangerous as unrecognised, since `declare` accepts `Prefix(value="")` and `evaluate` then admits every string, so `{"kind": "prefix"}` with no payload would be an unconditional admit on an argument that reads as constrained (measured). **The no-predicate carve-out was deleted**: it claimed a lookup-miss denial on two readings the fragment contradicts — an argument with an empty predicate tuple is refused by `declare`, and an entry naming no arguments is accepted and admits a no-argument call — so it exempted an element on a denial path that does not exist. **Each declare-refusal check now asserts the refusal it names**, because the ratified dataset refusal rejects every `url` entry and would have made four of the checks green on an implementation that never routed a `url` entry through `declare` — a check that cannot fail. The `within("")` mechanism is corrected: it does not canonicalise to `/`, it resolves to the worker's working directory, and the admission comes from a bypassing decoder leaving the root un-canonicalised so `admits` compares with `startswith("/")`. Two claims were scoped rather than repaired: at-most-once holds per logical invocation and not per action, and the drift-inheritance and union-refusal-site limits of the check obligation are now recorded as what the checks do not establish. **Declined:** one adversarial finding was refuted — that declare routing leaves the unrecognised-domain-type behaviour checked on neither side, which `walking-skeleton-authority-containment`'s shipped AC-0315 already covers at the evaluation entry point.
- 2026-09-23: spec approved by eugenelim
- 2026-09-23: plan approved by eugenelim
- 2026-09-23: plan re-approved by eugenelim after the amendment above
- 2026-09-23: plan re-approved by eugenelim after amendment round 2
- 2026-09-23: plan re-approved by eugenelim after amendment round 3
- 2026-09-23: plan re-approved by eugenelim after amendment round 4; pre-EXECUTE review stopped on the diverging-loop condition
