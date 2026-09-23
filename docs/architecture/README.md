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
| Event log and its two append paths | `src/ced/domain/events.py`, `src/ced/adapters/postgres/event_log.py`, `migrations/versions/0002_*` | Per-run `seq` allocated by a row UPDATE inside the append transaction, never a `bigserial`. A fenced worker path and an unfenced run-lifecycle path, `steps` locked before `runs` on both | r7 § Event log and stream mechanism |
| The privilege split | `migrations/versions/0002_*` | No application role holds `INSERT` on `events`. Three `SECURITY DEFINER` functions with disjoint `EXECUTE` grants, each schema-qualified and naming `pg_temp`; a fourth, `fence_step`, owned by the `NOLOGIN` `ced_fence` so the role the split distrusts cannot drop the control that constrains it. The fence proves **possession**, not knowledge: it requires a live, owned lease (`owner IS NOT NULL AND lease_expires_at > clock_timestamp()`, never `now()`, which is the caller's transaction start), so a never-claimed, released, drained or expired step is unappendable at any epoch. Every fenced append also checks the step belongs to the run. `events.type` carries a CHECK requiring a dotted run of lowercase ASCII alphanumerics, which is what makes the reserved-type refusal exhaustive by construction rather than by a denylist of invisible characters — two review rounds closed that denylist and both were walked through, the second by a homoglyph | r8 § 4 Contracts and Invariants; `worker-runtime.md` r4 change 1 as narrowed by [ADR-0004](../adr/0004-fence-function-owner.md); the possession predicate by [ADR-0005](../adr/0005-the-fence-proves-lease-possession.md), which is the one shipped deviation from r7 § Event log |
| The HTTP surface | `src/ced/api/` | `POST /runs`, `GET /runs/{id}/snapshot`, `GET /runs/{id}/events`. Holds no model authority and reaches the log only through the two run-lifecycle types | r8 § 4 Contracts and Invariants; `contracts/openapi/runs.yaml` |
| The worker pool | `src/ced/worker/pool.py` | Claim under a lease with `SKIP LOCKED`, execute outside any transaction, heartbeat-renew fenced on epoch and owner. TTL 60 s, heartbeat 20 s, poll 30 s. `validate_pool_config` refuses at boot, with no database, a deployment that leaves any of the four token ceilings unset or names no allowed model id — the pool's own spend bound is checked rather than assumed | r8 § 3 Runtime Model; `worker-runtime.md` § 6 Deployment and Operations; [ADR-0006](../adr/0006-four-r5-deviations-for-phase-1.md) D1 |
| The role compiler | `src/ced/agents/compiler.py`, `src/ced/agents/models.py`, `src/ced/adapters/postgres/roles.py`, `migrations/versions/0003_*` | An `agent_role` record becomes an `Agent` here and nowhere else. Revision 0003 closes `agent_role` and `integration_registry` to r5's record shapes; `load_role` reads them and `decode_role_record` refuses a malformed one. The compile-time guards refuse a role that widens a pool limit, declares a model id outside the pool's allowed set, carries a settings key outside the declared set, binds an integration its pool class may not reach, binds a tool that does not resolve, or declares an output contract the compiler does not know. The append path for a refusal exists and names its event type from the raised type rather than from a caller — `role.load.failed` at the loader stage, `role.compile.refused` at the compiler's. **Nothing calls it yet:** the step executor that appends is `walking-skeleton-step-lifecycle`'s, so no refusal reaches the log today and this row claims the seam, not the behaviour | `worker-runtime.md` r5 § 2 and § 4; `role-configuration-seams.md` § 5 and § 6; [ADR-0006](../adr/0006-four-r5-deviations-for-phase-1.md) |
| The toolset stack | `src/ced/agents/toolsets/` | One toolset on the agent besides the framework's own, and it is the policy decision point wrapping the step-event toolset wrapping the trust-class toolset wrapping the function toolset. The compiler builds the chain and a separate checker asserts the order, so order is never a caller's parameter. **The decision point ships with its position and not its predicate: it refuses every call.** The fragment it will decide with now exists; installing it is `walking-skeleton-policy-decision-point`'s, so until then no tool body executes | ADR-0001 D3; `worker-runtime.md` r5 § 2 Structural Model |
| The quarantine boundary | `src/ced/agents/toolsets/trust_class.py`, `src/ced/domain/quarantine/` | A role is quarantined exactly when its `ceiling` is empty — a construction, not a declaration — and it compiles to no domain tools, the `reference-selection` output contract, and zero tool-retry and output-validation-retry budgets. A deterministic pipeline mints the candidate reference set from the recorded filing **before** the agent runs and seals it, so the agent selects among references it cannot mint. The parser admits a closed set of scalar types, a closed label vocabulary, and only minted references | `runtime-architecture.md` r8 § 4 Contracts and Invariants; `worker-runtime.md` r5 § 4 |
| The containment fragment | `src/ced/domain/containment/` | Decides whether an argument *value* falls inside a role's ceiling over parsed components rather than over the string. Arguments carry a domain type, a string prefix is expressible only on `opaque-string`, and the caller receives a parsed `CanonicalUrl` it cannot recover the original from. A canonicaliser of ten named rules runs first, each recording the r5 clause it implements; percent-decoding runs before dot-segment removal and a pinned case holds that order. Authoring refuses a prefix on an interpreted type, a `host_in_domain` over a public suffix **as the bundled 2019-12-21 dataset knows one** — a suffix delegated since is authorable, and that dependency has shipped no refresh — a `url` argument with no host-constraining predicate, and one whose scheme predicate is missing **or names anything but `https`** — the one place the fragment bounds a predicate's value rather than only its presence, because a scheme the egress path cannot carry makes the host predicate beside it decide nothing — a `within` root that is relative or the whole filesystem, and an argument with no predicate at all. Evaluation has three outcomes and no fourth: it admits, carrying the canonical value; it denies, including for an argument no predicate ranges over and one the call omits; or it raises `ContainmentUndecidable` on an input it cannot decide. **Nothing installs it yet:** the decision point that consumes it is [`walking-skeleton-policy-decision-point`](../specs/walking-skeleton-policy-decision-point/spec.md)'s, so no call is decided by it today and this row claims the library, not the boundary | `worker-runtime.md` r5 § 4, "Why a prefix predicate is not safe on an interpreted argument" |
| The dependency-direction gate | `tests/architecture/dependency_direction.py` | An AST walk refusing `pydantic_ai` outside `agents/` and `adapters/`, and the AWS SDK outside `adapters/` | The spec's Never-do |
| The local substrate | `deploy/` | Postgres 17 with `deadlock_timeout` at 200 ms, MinIO, and two worker containers | `worker-runtime.md` § 6 Deployment and Operations |

**What is designed and not built.** The authorization boundary — the decision
point's predicate, which installs the containment fragment above — the provider
call, the run state machine's transitions, the browser stream, and the Phase 1
measurements. Those belong to `walking-skeleton-policy-decision-point`,
`walking-skeleton-step-lifecycle` and `walking-skeleton-evidence`. The fragment
that decides containment exists; the gate that asks it does not.

**One consequence is worth stating plainly: no tool body executes anywhere in
this repository.** The decision point has its position and no predicate, so it
refuses every call. That is deliberate, and it means the stack above is
asserted by walking the constructed chain rather than demonstrated by a call
that got through.

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

## Reading the frozen foundation spec

`walking-skeleton-foundation` shipped before `walking-skeleton-agent-runtime`
was cut into three and that directory deleted on 2026-09-20. A shipped spec
freezes, so its stale text stays as written and is corrected here. **This
section is not part of § What is built, and a spec-completion update to that
map does not clear it.**

What the three frozen files still say:

- `spec.md` line 23 calls itself "the first of three specs" delivering the
  Phase 1 walking skeleton. Phase 1 is five specs.
- `spec.md` line 37 names `walking-skeleton-agent-runtime` as the sibling
  building the reasoning step, the authorization boundary and the quarantine
  boundary; line 84 gives it every provider-touching claim.
- `spec.md` line 136 says Phase 1's exit criteria are met when
  `walking-skeleton-agent-runtime` and `walking-skeleton-evidence` ship, "all
  three". The four specs queued in `workspace.toml` carry them.
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
| The authorization boundary | [`walking-skeleton-authority-containment`](../specs/walking-skeleton-authority-containment/spec.md) | § Durable Outputs: "names the authorization boundary as unbuilt, and this spec builds it" |
| The idempotency behaviour | `walking-skeleton-authority-containment` | AC-0212 |
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
