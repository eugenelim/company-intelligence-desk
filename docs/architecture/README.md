# Architecture

How the code is *currently* organized. Not why (that's in
[`../adr/`](../adr/)) and not what we want (that's in
[`../rfc/`](../rfc/)) — **what is**.

- [`overview.md`](overview.md) — the map of the repository. What lives where,
  and how the parts relate. Read this first. **Still the unfilled seed
  template**, which is a defect in this directory rather than a statement about
  the code; § What is built below is the current map until it is filled.
- `<subsystem>.md` — one file per non-trivial subsystem (add as the repo
  grows). Each describes the structure, the entry points, and links to the
  ADRs that explain why.

## What is built

The first application code landed with
[`walking-skeleton-foundation`](../specs/walking-skeleton-foundation/spec.md).
The layout is [ADR-0003](../adr/0003-repository-layout.md); the framework
decision is [ADR-0001](../adr/0001-pydantic-ai-as-the-agent-framework.md) and
its version pin is [ADR-0002](../adr/0002-pydantic-ai-version-pin.md).

One package, `src/ced`, in five layers, built into one image with two entry
points — `ced-api` and `ced-worker`.

| Subsystem | Where | What it is | Governing design |
| --- | --- | --- | --- |
| Event log and its append paths | `src/ced/domain/events.py`, `src/ced/adapters/postgres/event_log.py`, `migrations/versions/0002_*` | Per-run `seq` allocated by a row UPDATE inside the append transaction, never a `bigserial`. Revision 0002 shipped a fenced worker path and an unfenced run-lifecycle path, `steps` locked before `runs` on both. Every append in `src/ced/adapters/postgres/event_log.py` goes through a `SECURITY DEFINER` function of the same name — no wrapper writes `events` directly — and the privilege-split row below carries the current function and grant set | r7 § Event log and stream mechanism |
| The privilege split | `migrations/versions/0002_*`, `migrations/versions/0005_*` | No application role holds `INSERT` on `events`. Five `SECURITY DEFINER` append functions — `append_step_event`, `append_run_event`, `append_policy_decision`, `append_run_terminal`, `append_approval_decision` — plus `fence_step`, which is owned by the `NOLOGIN` `ced_fence` so the role the split distrusts cannot drop the control that constrains it. **Every one pins `SET search_path = pg_catalog, pg_temp` and schema-qualifies every relation reference.** The control is disjointness between *roles*, not one function per role: `app_worker` holds `append_step_event` and `append_run_terminal`, `app_api` holds `append_run_event` and `append_approval_decision`, `app_policy` holds `append_policy_decision`, and `PUBLIC` holds none. The fence proves **possession**, not knowledge: it requires a live, owned lease (`owner IS NOT NULL AND lease_expires_at > clock_timestamp()`, never `now()`, which is the caller's transaction start), so a never-claimed, released, drained or expired step is unappendable at any epoch. Every fenced append also checks the step belongs to the run. `events.type` carries a CHECK requiring a dotted run of lowercase ASCII alphanumerics, which is what makes the reserved-type refusal exhaustive by construction rather than by a denylist of invisible characters. Revision 0005 re-issues `append_step_event` through `CREATE OR REPLACE` with the two decision types added to its refusal list, so they cannot reach the worker's path | r8 § 4 Contracts and Invariants; `worker-runtime.md` r4 change 1 as narrowed by [ADR-0004](../adr/0004-fence-function-owner.md); the possession predicate by [ADR-0005](../adr/0005-the-fence-proves-lease-possession.md); the two new paths by [ADR-0009](../adr/0009-the-two-new-append-paths-and-who-holds-them.md) |
| The HTTP surface | `src/ced/api/` | `POST /runs`, `GET /runs/{id}/snapshot`, `GET /runs/{id}/events`, and `POST /runs/{run_id}/steps/{step_id}/decision` — the approval operation `walking-skeleton-run-state` added. Holds no model authority. It reaches the log through the two run-lifecycle types **and**, since that spec, through the two step-scoped decision types on `app_api`'s own append path; an earlier version of this row said "only through the two run-lifecycle types", which stopped being true when AC-0324 granted that path. The decision route validates shape, cardinality and origin, and deliberately validates **no call ids** — the pending set lives in the object store and nothing under `src/ced/api/` reaches it | r8 § 4 Contracts and Invariants; `contracts/openapi/runs.yaml` |
| The worker pool | `src/ced/worker/pool.py` | Claim under a lease with `SKIP LOCKED`, execute outside any transaction, heartbeat-renew fenced on epoch and owner. TTL 60 s, heartbeat 20 s, poll 30 s. `validate_pool_config` refuses at boot, with no database, a deployment that leaves any of the four token ceilings unset or names no allowed model id — the pool's own spend bound is checked rather than assumed | r8 § 3 Runtime Model; `worker-runtime.md` § 6 Deployment and Operations; [ADR-0006](../adr/0006-four-r5-deviations-for-phase-1.md) D1 |
| The role compiler | `src/ced/agents/compiler.py`, `src/ced/agents/models.py`, `src/ced/adapters/postgres/roles.py`, `migrations/versions/0003_*` | An `agent_role` record becomes an `Agent` here and nowhere else. Revision 0003 closes `agent_role` and `integration_registry` to r5's record shapes; `load_role` reads them and `decode_role_record` refuses a malformed one. The compile-time guards refuse a role that widens a pool limit, declares a model id outside the pool's allowed set, carries a settings key outside the declared set, binds an integration its pool class may not reach, binds a tool that does not resolve, or declares an output contract the compiler does not know. The append path for a refusal exists and names its event type from the raised type rather than from a caller — `role.load.failed` at the loader stage, `role.compile.refused` at the compiler's. **Nothing calls it yet:** the step executor that appends is `walking-skeleton-step-lifecycle`'s, so no refusal reaches the log today and this row claims the seam, not the behaviour | `worker-runtime.md` r5 § 2 and § 4; `role-configuration-seams.md` § 5 and § 6; [ADR-0006](../adr/0006-four-r5-deviations-for-phase-1.md) |
| The toolset stack | `src/ced/agents/toolsets/`, `src/ced/worker/executor.py` | The compiled stack is one toolset besides the framework's own, and it is the policy decision point wrapping the step-event toolset wrapping the trust-class toolset wrapping the function toolset. The compiler builds the chain and a separate checker asserts the order, so order is never a caller's parameter. **The decision point now holds its predicate as well as its position.** It decodes a stored ceiling into the containment fragment, denies a lookup that finds nothing, and commits a `policy.decision` before the tool body runs or the refusal is raised; the step-event layer below it appends the invocation pair and turns a duplicate derived key into a terminated step. **A flagged run carries a second toolset outside that stack:** when a pre-release check fails, `offered_approval_gated_tools` returns an approval-gated `FunctionToolset` that the executor passes to `run_sync` beside the compiled one — the run-time placement [ADR-0008](../adr/0008-the-approval-gate-stays-outside-the-compiled-toolset.md) records and AC-0302 reads. A clean run is offered none | ADR-0001 D3; `worker-runtime.md` r5 § 2 Structural Model |
| The quarantine boundary | `src/ced/agents/toolsets/trust_class.py`, `src/ced/domain/quarantine/` | A role is quarantined exactly when its `ceiling` is empty — a construction, not a declaration — and it compiles to no domain tools, the `reference-selection` output contract, and zero tool-retry and output-validation-retry budgets. A deterministic pipeline mints the candidate reference set from the recorded filing **before** the agent runs and seals it, so the agent selects among references it cannot mint. The parser admits a closed set of scalar types, a closed label vocabulary, and only minted references | `runtime-architecture.md` r8 § 4 Contracts and Invariants; `worker-runtime.md` r5 § 4 |
| The containment fragment | `src/ced/domain/containment/` | Decides whether an argument *value* falls inside a role's ceiling over parsed components rather than over the string. Arguments carry a domain type, a string prefix is expressible only on `opaque-string`, and the caller receives a parsed `CanonicalUrl` it cannot recover the original from. A canonicaliser of ten named rules runs first, each recording the r5 clause it implements; percent-decoding runs before dot-segment removal and a pinned case holds that order. Authoring refuses a prefix on an interpreted type, a `host_in_domain` over a public suffix **as the bundled 2019-12-21 dataset knows one** — a suffix delegated since is authorable, and that dependency has shipped no refresh — a `url` argument with no host-constraining predicate, and one whose scheme predicate is missing **or names anything but `https`** — the one place the fragment bounds a predicate's value rather than only its presence, because a scheme the egress path cannot carry makes the host predicate beside it decide nothing — a `within` root that is relative or the whole filesystem, and an argument with no predicate at all. Evaluation has three outcomes and no fourth: it admits, carrying the canonical value; it denies, including for an argument no predicate ranges over and one the call omits; or it raises `ContainmentUndecidable` on an input it cannot decide. **It is installed:** [`walking-skeleton-policy-decision-point`](../specs/walking-skeleton-policy-decision-point/spec.md) decodes `agent_role.ceiling` and `entitlements.ceiling` into it on the compile path, routing every entry through this fragment's own authoring surface so a stored row the fragment could not have been written with is refused at compile time rather than evaluated | `worker-runtime.md` r5 § 4, "Why a prefix predicate is not safe on an interpreted argument" |
| The authorization boundary | `src/ced/agents/ceilings.py`, `src/ced/agents/toolsets/policy.py`, `src/ced/adapters/postgres/event_log.py` | `may_act` as a conjunction: a call is admitted only when the acting role's ceiling admits it **and** the initiating user's entitlements do. Both identities are read from the claimed step and its run — `events.principal` on the run's `run.requested` row — never from the call, so an agent cannot select the ceiling it is judged against. The decision is committed before the body runs or the refusal is raised. On **any** append failure the worker attempts a fenced step termination and raises: where the fence was held the step terminates, and where the worker was genuinely evicted the write matches zero rows and the step stays with its new owner. The database is the discriminator, because an injected serialization failure and a real takeover both surface as the same exception. A `url`-typed argument is refused at compile time while the bundled public-suffix dataset is its 2019-12-21 snapshot | `worker-runtime.md` r5 § 2 and § 4; r8 § 4 Contracts and Invariants |
| The run state machine | `src/ced/domain/run_state.py`, `src/ced/worker/executor.py`, `src/ced/worker/persistence.py`, `src/ced/worker/pool.py`, `src/ced/adapters/postgres/event_log.py`, `src/ced/api/main.py`, `migrations/versions/0005_*` | Three committed transitions — `requested→running` on `step.started`, and `running→completed` / `running→failed` on the two terminal types — each written with its event in one transaction. `append_run_terminal` is fenced and granted to `app_worker` alone; `append_approval_decision` is unfenced and granted to `app_api` alone, keyed `<suspension_seq>:<call_id>` under a partial unique index. A suspended step is held out of the claim predicate by `steps.awaiting_decision` rather than by a step state, which keeps the lease released as AC-0237 requires while stopping a re-claim before the approver acts. `project_run_state` is the pure projection the snapshot is checked against. Two bounding controls on `PoolConfig`, both with finite defaults: an approval cycle cap, and a ceiling named for tokens that is in fact compared against the run's event count — no token count is persisted in this delivery, so at its default a run emitting roughly four events is measured against 200 000. The residuals subsection below records that mismatch rather than the table implying a working spend bound. **What it does not commit, and why, is enumerated in § `walking-skeleton-run-state` residuals below** — that subsection is the point, not a footnote | r8 § 3 Runtime Model; `worker-runtime.md` r5 § 3; [ADR-0008](../adr/0008-the-approval-gate-stays-outside-the-compiled-toolset.md) and [ADR-0009](../adr/0009-the-two-new-append-paths-and-who-holds-them.md) |
| The dependency-direction gate | `tests/architecture/dependency_direction.py` | An AST walk refusing `pydantic_ai` outside `agents/` and `adapters/`, and the AWS SDK outside `adapters/` | The spec's Never-do |
| The local substrate | `deploy/` | Postgres 17 with `deadlock_timeout` at 200 ms, MinIO, and two worker containers | `worker-runtime.md` § 6 Deployment and Operations |

**What the step lifecycle added.** `walking-skeleton-step-lifecycle` built the
model seam, the approval gate and persistence. A step reaches a real provider
under a scoped assumed role; a step that asks for approval writes its history,
releases its lease and is resumed from those bytes by a different process; a
step whose model call hangs is bounded; and a role cannot compile, nor a call
be issued, against a model that would reason at the provider.

**What is designed and not built.** The browser stream and the Phase 1
measurements, which belong to `walking-skeleton-evidence`; and the run state
machine's **remaining** transitions, which have different owners and in three
cases none. `requested→claimed` and `running→awaiting_approval` need event
types — `run.claimed` and `approval.requested` — that exist nowhere in the
tree, which is a vocabulary decision no spec currently owns.
`any non-terminal→cancelled` is expressible today and needs a cancel caller,
which no spec currently owns either. Only what `awaiting_input` owes belongs to
the spec that first wires the input tool.  The run
state machine itself is **built**: it was split out into
`walking-skeleton-run-state` and shipped, and § `walking-skeleton-run-state`
residuals below enumerates every edge r8 § 3 names, marking the three this
delivery commits and the seven it does not, each with the reason it is stuck. 

**What the step lifecycle established, and what it did not.** The credential
scan reads a locally running container and shows it holds no static key; on a
deployed fleet the task role supplies credentials with no session key in the
process environment at all, and that stronger property is not demonstrated
here. No image scanner is wired, so a secret in a discarded layer is invisible
to a scan of a running filesystem. The reasoning-disable guard admits a model
the deployment declares non-provider-backed, and identification is by class —
a subclass of an in-process double that delegates to a provider inherits the
admit. A fallback chain is refused rather than read, because `FallbackModel`
is not a wrapper on the pinned framework version. Each of these is stated in
the spec's own criteria rather than left for a reader to discover.

**What the authorization boundary establishes, and what it does not.** Fifteen
criteria hold that the boundary refuses a value outside the ceiling, refuses a
tool with no entry at all, refuses a call outside the initiating user's
entitlements, denies rather than crashes when the fragment cannot decide,
records every decision it makes before the call proceeds, and orders and fences
correctly against injected append failures and a real second worker's takeover.
A tool body does execute, for a call both halves admit.

They establish nothing about a failure mode nobody injected. **At that
delivery's date there was no step executor**, so the spec supplied the reads that source the acting role and the
initiating principal, and the suite's fixture assembles the step context from
them, because the path that will do so in production is
`walking-skeleton-step-lifecycle`'s. And nothing binds `principal` to an
authenticated subject — `POST /runs` takes it as a caller-chosen string, so
whoever reaches the ingress selects the entitlements ceiling they are judged
against. r7 puts OIDC at the ingress and this Phase deliberately defers it;
`walking-skeleton-policy-decision-point`'s § Follow-ons carries that gap where
the criterion that rests on it lives.

The design subtrees keep their markers, and a document that carries a
build-state split states it in its own header rather than as a second copy of
this section. This section stays the current map: where a marker and this map
could drift apart, read this one.

`walking-skeleton-role-compilation`'s verification ledger reports statements
in ratified records that it observed falsified and could not correct:
`role-configuration-seams.md`'s marker, `runtime-architecture.md`'s header
clause and its § 8 rows, and the
[`inspectable-multi-agent-diligence/`](inspectable-multi-agent-diligence/README.md)
index's "Nothing described in this folder is built". **Each of those was
corrected on 2026-09-22.** That ledger keeps its text as written, because a
shipped spec's ledger records what one delivery observed on its own date;
this paragraph is the successor its pointers land on.
[`spikes/README.md`](../../spikes/README.md) § Phase 1 records, per delivery,
which of their claims now have evidence and which do not.

Decision records accumulate, and reconstructing current state from them means
reading every one in order. This directory is the rolled-up snapshot instead —
the answer to "what does this codebase look like today" without replaying ADR
history. Lifecycle: living. Update whenever the layout or major dependencies
change.

### `walking-skeleton-run-state` residuals

The run state machine, the approval interface and the two bounding controls
shipped with this delivery. AC-0329 requires this subsection, and requires it to
name each residual rather than count them, so that the next spec inherits a
state machine that does **not** look finished. Each entry names what a reader can
check.

**Which entries were contracted and which were discovered, because the
difference bears on how much this list is worth.** Ten were enumerated in
AC-0329 before the build and so were checkable against an independent list.
Six — marked **(discovered)** below — were found during T2 and T3 and added to
that enumeration by the same task that satisfies it, so for those the criterion
and the record were authored together and the gate cannot red on them by
construction. They were each verified against the tree, but a later reader
should know which entries a separate list ever checked.

**What the state machine does not commit.**

- **Of the edges r8 § 3 names, this delivery commits three and leaves seven.**
  Committed: `requested→running` on `step.started`, and `running→completed` /
  `running→failed` on the two terminal types. Not committed, with the reason
  each is stuck:
  - `requested→claimed` and `running→awaiting_approval` need `run.claimed` and
    `approval.requested`, which exist nowhere in `src/`, `migrations/`,
    `contracts/` or `tests/`. Inventing an event type is a vocabulary decision
    no spec currently owns.
  - `awaiting_approval→running` on `approval.rejected` and
    `awaiting_approval→completed` on `approval.granted` have their event types —
    revision 0005 ships both and `app_api` appends them — but **nothing ever
    writes `runs.state = 'awaiting_approval'`**, so the source state is
    unreachable and the edges are dead. This is the one a reader is most likely
    to get wrong: the approval *decision* path shipped, the approval *states* did
    not.
  - `awaiting_approval→expired` on `approval.expired` and
    `expired→awaiting_approval` on `approval.reopened` need both the source state
    and two more event types that exist nowhere.
  - `any non-terminal → cancelled` is declined rather than overlooked, for a
    different reason — see the next bullet.

  A reader therefore cannot distinguish a suspended run from a working one by
  `runs.state` at all: a suspension is visible only as the `step.suspended`
  event.
- `any non-terminal → cancelled` is declined rather than overlooked. `run.cancelled`
  ships and `append_run_event` admits it, so the tree can express the edge;
  nothing appends it, and committing it would mean building a cancel caller this
  spec does not own.
- **(discovered) Five failure paths leave a run reported `running` for ever.** In
  `src/ced/worker/executor.py`, the missing-suspension-`payload_ref` path, the
  raised-resume path, the non-boolean `needs_approval` path, the agent-error
  path and the quarantine refusal each append only `step.failed` and return, so
  `runs.state` never leaves `running` while the run's only step is finished.
  **Two paths do commit the terminal edge** — AC-0321's cycle cap and AC-0330's
  refused resume — which is the set AC-0327 enumerates. An earlier revision of
  this bullet named two of the five and then said "only AC-0330's refused
  resume commits the terminal edge", which was true before T3 gave the cap its
  terminal append and false after.

**What the privilege split does not reach.**

- Both `app_api` and `app_worker` retain a table-level `UPDATE ON runs`, so a
  direct write still moves a run's state with nothing in the log.
- The approval-decision path is unfenced, so r8 § 4's "the fence proves
  possession" is untrue for `approval.granted` and `approval.rejected`; the
  committed `step.suspended` and its `seq` are the substitute.
- AC-0324's exclusivity is over the event type, not over causation. `app_api`
  retains `INSERT ON steps`, so it can insert a step into any run, let a worker
  claim and suspend it, and decide against a step it caused to exist.
- The exclusion column and the cycle counter are writable outside the two paths
  this spec builds. The grants are not symmetric: revision 0001 gives
  `app_worker` `INSERT, UPDATE` on `steps` and `app_api` `INSERT` only, so
  `app_api` can set `awaiting_decision` and `approval_cycles` at insert time and
  never afterwards, while `app_worker` can change them on any existing row.

**What the approval interface does not establish.**

- The API validates no call ids, and that makes one failure unrecoverable: a
  committed decision naming none of the step's pending calls still consumes the
  suspension, so the resume refuses and the run ends `failed` with the
  approver's single opportunity spent.
- The recorded approver principal is unauthenticated, the origin refusal bounds
  a browser rather than a process, the approver decides blind because no surface
  shows them the pending calls, and the attribution is retained for the life of
  the event log with no erasure path.
- **(discovered)** The decision-set bound is a string-length seam reused as a list count —
  `ATTRIBUTION_MAX_LENGTH`, rendered `maxItems: 256`. It is finite, so the
  safety purpose holds, but nothing defines how many pending calls a suspension
  can carry, so the bound has no value to bind to.
- **(discovered) A resumed run publishes an object carrying no output.** The resume
  completion path writes `{"schema_version": 1}` as its `payload_ref`, because
  quarantine validation is a fresh-run property. AC-0303 contracts "resumes to
  publication", and nothing asserts that `payload_ref` today.
- **(discovered) AC-0330's refusal carries no distinguishing event type.** It appends `step.failed` **and**
  `run.failed`, so the terminal edge is committed — what is missing is a
  distinguishing type, not a terminal append. It shares `step.failed` with the
  five `src/ced/worker/executor.py` paths above, so a reader cannot tell a
  refused resume from an ordinary agent failure. The cycle cap was given
  `step.approval.cap.exceeded`; the refusal path was not.
- **(discovered) The `needs_approval` flag fails open on an absent key.** It lives in the
  free-form `model_settings` JSONB. An absent key legitimately means no gate and
  a malformed `model_settings` refuses — but a key present under a misspelling
  reads as absent, which disables the control silently.

**What the bounding controls do not measure.**

- The per-run spend ceiling is exercised against a fabricated multi-step run,
  because a real run has exactly one step.
- **(discovered) It is also configured in tokens and enforced on event count.**
  `per_run_token_ceiling` is compared against `runs.next_seq`; no migration adds
  a token column and the executor reads no `RunUsage`, so there is no persisted
  token count. At the default a producible run emits roughly four events against
  a ceiling of 200 000.
- The ceiling's finite default is unsourced, as is the cycle cap's three.

**What the next spec inherits, from § Follow-ons.**

- **`expired` and `awaiting_input` are owed on different terms, and conflating
  them misleads.** `expired` *is* authored: `migrations/versions/0001_base_schema.py`
  lists it in the `runs.state` CHECK and `contracts/openapi/runs.yaml` in the
  `state` enum. Nothing writes it. **`awaiting_input` is authored nowhere in
  this repository** — not in the CHECK, not in the enum, not in
  `src/ced/domain/run_state.py` — and exists only in the two ratified design tables, r8 § 3's and r5's. Both must be satisfied: r5 names the same `input.requested` / `input.supplied` pair and adds a row for `awaiting_input → cancelled / failed` whose own trigger is "the existing any-non-terminal transitions" — r8 already carries those edges and declares `awaiting_input` non-terminal, so r5 restates them for this state rather than adding one. A write
  of that value is refused by the CHECK constraint today, so the spec that
  first wires the input tool owes the CHECK and enum widening as well as the
  two safety constraints both tables state: the answer admitted at the acting role's
  existing ceiling, and both request and answer recorded. A transition table
  that looks complete is the reason this is written here rather than left to
  that spec to discover.
- r8 § 4 line 460 and § 3 line 344 disagree about whether a worker may write a
  run-lifecycle type, and § 4 line 461's possession invariant is made untrue for
  two event types by this delivery. ADR-0009 records the deviations; it does not
  amend r8, so the r9 consistency pass still owes that.

**What this delivery changed in a foundation-owned surface.**

- Revision 0005 re-issues `append_step_event` through `CREATE OR REPLACE`,
  narrowing what `app_worker` may append. AC-0332 guards what the replacement
  preserves — the owner, the definer flag, the pinned `search_path`, the
  signature and the grant set.

## Reading the frozen foundation spec

`walking-skeleton-foundation` shipped before `walking-skeleton-agent-runtime`
was cut into three and that directory deleted on 2026-09-20. A shipped spec
freezes, so its stale text stays as written and is corrected here. **This
section is not part of § What is built, and a spec-completion update to that
map does not clear it.**

What the three frozen files still say:

- `spec.md` line 23 calls itself "the first of three specs" delivering the
  Phase 1 walking skeleton. Phase 1's spec set is whatever `workspace.toml` registers — it has changed at every cut and split so far. The register is the source; a number written here goes stale at the next split.
- `spec.md` line 37 names `walking-skeleton-agent-runtime` as the sibling
  building the reasoning step, the authorization boundary and the quarantine
  boundary; line 84 gives it every provider-touching claim.
- `spec.md` line 136 says Phase 1's exit criteria are met when
  `walking-skeleton-agent-runtime` and `walking-skeleton-evidence` ship, "all
  three". The specs registered in `workspace.toml` carry them; the count is the register's, not this page's, for the reason given above.
- `plan.md` hands that directory the behavioural half of the derived
  idempotency key (line 52), the scope-qualified object keys (line 55), and r4
  changes 7, 8 and 9 (line 57).
- `notes/verification-ledger.md` names it three times. Line 277, "owns the
  real body", has a successor in the table below. Lines 443 and 477 narrate a
  reconciliation that happened while that directory existed; they are
  historically true and stay as written.

**Which successor builds each part.** Line 37's "reasoning step" is two parts
with two owners, and r5's STATUS header already separates them as the agent
layer and the provider call:

| Part | Built by | Where that spec claims it |
| --- | --- | --- |
| The agent layer — the compiler, the toolset stack, the compile-time refusals — and the quarantine boundary | [`walking-skeleton-role-compilation`](../specs/walking-skeleton-role-compilation/spec.md) | § Durable Outputs: "names three things as unbuilt: the agent layer, the authorization boundary and the provider call. This spec builds the first" |
| The authorization boundary — the decidable fragment | [`walking-skeleton-authority-containment`](../specs/walking-skeleton-authority-containment/spec.md) | § Durable Outputs: "names the authorization boundary as unbuilt, and this spec builds it" |
| The authorization boundary — the decision point that installs the fragment | [`walking-skeleton-policy-decision-point`](../specs/walking-skeleton-policy-decision-point/spec.md) | § Durable Outputs: the r5 marker row. The cut of 2026-09-23 split the fragment from the decision point, so the boundary takes two rows |
| The idempotency behaviour | `walking-skeleton-policy-decision-point` | AC-0212 |
| Fragment narrowing, r4 change 7 | `walking-skeleton-authority-containment` | AC-0217 |
| The provider call, and with it every provider-touching claim | [`walking-skeleton-step-lifecycle`](../specs/walking-skeleton-step-lifecycle/spec.md) | § Durable Outputs: "names the provider call as unbuilt, and this spec builds it" |
| The scope-qualified object keys | `walking-skeleton-step-lifecycle` | AC-0231 |

`walking-skeleton-role-compilation` builds no part of the model call: its spec
disclaims the authorization boundary and the provider call, and its whole suite
runs with no provider in the loop.

**Two of line 57's changes are deferred, not reassigned.** r4 change 8,
`may_exist`, and change 9, per-integration credentials, are recorded as
Follow-ons and no Phase 1 spec builds either: `may_exist` in
[`walking-skeleton-authority-containment`](../specs/walking-skeleton-authority-containment/spec.md)
§ Follow-ons, and the credential broker that carries the per-integration scopes
in [`walking-skeleton-step-lifecycle`](../specs/walking-skeleton-step-lifecycle/spec.md)
§ Follow-ons. The frozen row classed them as deferred too, so what changed is
where the record lives, not its status.

## Two documents, two jobs

`overview.md` is **descriptive** — the map, read to find things.
`reference.md` is **normative** — the golden path (stack, building blocks,
component stereotypes, cross-cutting standards) that new work conforms to, and
the target a feature's low-level design steers by. A thin repository has only
the map; the golden path appears once there are real architecture decisions to
hold work to.

Getting these the wrong way round is the common mistake: a map written as a
standard goes stale the moment the code moves, and a standard written as a map
never gets enforced.

## Designed but unbuilt

This directory holds current state. A designed-but-unbuilt subtree is admitted
only when its index carries a `STATUS: PLANNED` marker and links to the
decision governing it. [`inspectable-multi-agent-diligence/`](inspectable-multi-agent-diligence/)
is admitted under that rule.

## Verification markers

When a page carries a `Last verified against commit` marker, it records a
deliberate whole-page re-verification against that commit, not merely an edit.
Update it only after re-reading the whole page against the tree at that commit.
An unchanged marker means the page has not had that audit; it is provenance,
not a freshness requirement.
