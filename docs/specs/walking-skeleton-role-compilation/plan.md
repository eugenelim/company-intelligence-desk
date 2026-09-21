# Plan: Walking skeleton — role compilation and the quarantine boundary

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5 § 2 Structural Model ("An agent role compiles to an agent", "The toolset stack, innermost to outermost", the three responsibility catalogues) and § 4 Contracts and Invariants ("The integration registry", "Inputs, outputs, and tool reach"). **No analogous production implementation exists.** The substitute is `spikes/phase-0/pydantic_ai_bedrock_spike.py`, which holds executable precedent for the `WrapperToolset` authorization hook. **Named deviation:** that spike's hook appended to a Python list — no database, no second connection — so it is precedent for the *seam*, not for any persistence mechanism.

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-role-compilation/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads and are pinned. `Design`, `Approach`, `Grounding` and
> `Risks` are working material.

## Approach

Build the guards before the thing they guard, and keep the provider out of the
loop entirely — no task here reaches one.

The compiler comes first because it is where every other guarantee in the Phase 1
runtime is asserted: the structural invariant, the four compile-time role
refusals, the usage-limit narrowing. The stack it composes is the full four
layers, including the policy decision point, because the decision point's
*position* is the security property and it cannot be asserted against a chain
that is missing it. Its *predicate* arrives in
`walking-skeleton-authority-containment`; until then the decision point has
nothing that can decide a ceiling entry, so it refuses every call. AC-0233 pins
that with no predicate installed the whole tool surface refuses, and AC-0234
that a refusal is terminal. AC-0233 is deliberately scoped to that
configuration: phrased to also cover the predicate being present, it would read
"refused unless the predicate admits it", which no oracle outside the
implementation can decide — a lookup miss that falls through would satisfy it.
The fall-through guard therefore lives where a real lookup exists, as
`walking-skeleton-authority-containment`'s AC-0235. AC-0234 carries across
unscoped, because a refusal is terminal in every configuration.

The quarantine boundary follows and is the largest single piece of new thinking,
because the ratified design moved reference production *out* of the model: a
deterministic pipeline mints the candidate set before the quarantined agent
runs, so forgery is unrepresentable rather than detected. That is a different
construction from the one spike 4 tested and falsified, and building the weaker
one by accident is the most likely way to get this wrong.

**The riskiest part is the quarantine boundary**, and the risk is not that it
fails a test. It is that the boundary can be built so that its tests pass while
the guarantee is weaker than the criteria read — a parser that validates shape
without a minting authority admits an attacker-chosen value inside a well-formed
reference. AC-0221 exists to catch precisely that, and it is the criterion to
write first and trust least.

## Constraints

- [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md) — the framework at step-level-reasoning-library position; `Model` as the portability contract; `WrapperToolset.call_tool` as the decision point. ADR-0002 pins 2.45.0.
- `runtime-architecture.md` r8 — ratified with its five accepted limits in § 9 accepted **open**. The first of those limits in particular narrows the quarantine guarantee's *scope*; it does not license leaving the guarantee unverified, which is why this spec adds criteria for it.
- `worker-runtime.md` r5 — see § DR dispositions below. The amendments it once asked of its parent are folded into r8; see § Amendments the worker runtime asked of its parent.
- **Hard dependency:** `walking-skeleton-foundation` ships both append paths, the privilege split and the pool.
- **Designed by:** [`role-configuration-seams`](../../architecture/role-configuration-seams/role-configuration-seams.md). Its § 5 gives the migration, § 2 the seams, § 6 the operator surfaces. This plan builds that delta and invents nothing beyond it.
- **Placement and re-cut rules:** [`docs/specs/README.md`](../README.md) § Cutting one outcome into several specs.
- **Out of scope:** the containment fragment and the decision point's predicate, owned by `walking-skeleton-authority-containment`, which follows this spec; the provider call, suspension and persistence, owned by `walking-skeleton-step-lifecycle`, which follows that one; the run state machine, publication, the browser stream and the Phase 1 measurements, all owned by `walking-skeleton-evidence`; the AWS deployment, out by the owner's decision of 2026-09-18.

## DR dispositions

The spec makes changing any DR decision an Ask-first boundary, enforceable only
if each carries a disposition. **This table lists only the DRs this spec
constructs.** A DR absent from it is not this spec's; the Phase 1 routing is the
union of this table, the two sibling plans' and the foundation plan's, and no
plan restates another's rows — a negative row is a sentence about a document
this one does not own, and three copies of it go wrong the next time one moves.

| DR | Decision | Disposition |
| --- | --- | --- |
| DR6 | Three spend ceilings; the step one is pre-call | **Partly here, and partly suspended** — `request_limit` and `tool_calls_limit` land in T2 under AC-0206, token-denominated. `cost_limit` is excluded from `model_settings.limits` entirely, and the pre-request bound is suspended by [ADR-0006](../../adr/0006-four-r5-deviations-for-phase-1.md) D1, so AC-0246 exercises it against a counting stub and no criterion here bounds spend in production. The per-run ceiling is the evidence spec's, and the per-account AWS Budgets alarm is outside the application entirely |
| DR8 | Thinking off, and reasoning parts stripped before persisting | **Partly here** — AC-0204 is the primary control and lands in T2. The storage backstop is `walking-skeleton-step-lifecycle`'s |
| DR9 | Zero tool and output retries on the quarantined role | **Lands**, T2, AC-0205 |
| DR13 | `trust_class` is a construction, not a declaration | **Lands** — AC-0203 is the compile-time refusal and AC-0219 the compiled-agent assertion in T2, AC-0220 the parser and AC-0221 the minting authority in T3 |

## Amendments the worker runtime asked of its parent

r5 § 10 Rollout records that every amendment this subsystem required is now
folded into `runtime-architecture.md` r8 and is no longer asked for from here,
so there is nothing left for a spec to disposition. r5 names three as
load-bearing for its § 4 invariants: the fenced policy append, the narrowed
decidable fragment, and scope-qualified object keys.

**None of the three is this spec's.** The first two are `walking-skeleton-authority-containment`'s and the third is `walking-skeleton-step-lifecycle`'s.

## Grounding probe

Run before this plan was written, against the pinned version, to disconfirm the
API claims the ratified design rests on. **It disconfirmed none on
`pydantic-ai` 2.45.0**, which is what licenses treating the pin move off
ADR-0001 D5's 2.44.0 as cheap. Some rows carry more than one assertion.

**This table is the single home for the framework-seam probe.** The two sibling
specs cite it here rather than repeating rows.

| Claim under test | Source of the claim | Result |
| --- | --- | --- |
| `Agent.run` accepts `cancellation_token` | r5 § 2 Structural Model, the pool | present in signature |
| `UsageLimits` has `cost_limit`, `count_tokens_before_request`, `request_limit`, `tool_calls_limit` | DR6 | all present |
| Tool and output retries budget separately, both zeroable | DR9 | the retry type carries exactly those two budgets |
| `ModelSettings.thinking` exists; a reasoning part is the thing to strip | DR8 | both present |
| `WrapperToolset.call_tool` is an overridable seam | ADR-0001 D3 | `(self, name, tool_args, ctx, tool)` |
| `DeferredToolRequests` carries `calls` as well as `approvals` | r5 § 3 Runtime Model, the approval gate | both present |
| `BedrockConverseModel` takes a model id and nothing else | ADR-0001 D2 | only the model name is required |
| A realistic history round-trips byte-identically | r5 § 10 Rollout criterion 6 | identical on second dump, over tool call, tool return and retry parts |
| A reasoning-stripped history round-trips and leaks nothing | DR8 | identical, no reasoning in the bytes |
| `result.usage` is a property; `stream_text` debounces by default | probe-established; no upstream document states either | both confirmed |

`DeferredToolRequests` resolves from a private module re-exported at the package
root. T1 imports it from the root and the framework-seam contract test pins
that, because a re-export moving is exactly the additive-minor drift r5's risk
register names.

That probe also surfaced the closure gotcha: a tool registered on a nested
function raises a context-parameter error, because the framework infers a
context parameter it cannot resolve. The compiler builds toolsets inside a
function, so it resolves module-level callables from the registry.

No probe is committed. Their content becomes the framework-seam contract suite
in T1, which is the ratified mitigation for version drift — exact pins plus
contract tests at the framework seam — and a throwaway script is not that. The
provider seam is `walking-skeleton-step-lifecycle`'s; no task here reaches one.

## Construction tests

**Integration tests:**
- One quarantine end-to-end: the deterministic pipeline mints a reference set from the recorded filing, the quarantined agent selects among them, the parser admits, and a planning step receives references and scalars only. This is the spine AC-0219, AC-0220, AC-0221, AC-0238 and AC-0250 read; the onward crossing into a planning step is `walking-skeleton-step-lifecycle`'s.
- One framework-seam contract suite (T1) asserting every check in § Grounding probe, so a version bump fails the build rather than a runtime.

**Manual verification:** none. Every criterion here is machine-checkable.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Current architecture — the `worker-runtime.md` marker | T4 | This spec's clause moved from unbuilt to built | The header's built and unbuilt lists match the repository |
| Current architecture — `docs/architecture/README.md` § What is built | T4 | The compiler, the toolset stack and the quarantined agent moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Reusable learning — `spikes/README.md` | T4 | A section stating what was and was not established | Hypothesis checks separated from setup |

## Design (LLD)

Shape is `service`; the sub-sections below are the set that shape selects.

### Design decisions

- **The compiler is the only constructor of the agent.** It asserts the agent holds exactly one toolset, that it is the decision point, and that the chain beneath it is the specified order. Nesting order only governs tools reached *through* the wrapped stack, so a sibling tool has no ceiling entry to violate and no behavioural test can catch it. Traces to: AC-0201, AC-0202.
- **The structural check is a function over a constructed chain, not a parameter on the compiler.** Asserting order by making the compiler accept an ordered layer list would widen a production contract to make a test possible, and would put stack order in a caller's hands. Instead the compiler builds the chain and calls a checker; the checker is unit-tested against hand-built wrong chains, and the compiled agent is asserted by walking it. Traces to: AC-0202.
- **The decision point ships with its position, not its predicate, and refuses everything in between.** Splitting the stack's composition from its containment logic is what makes two reviewable specs out of one; making the interval admit anything would turn the split into a security regression. The interval's rule is not "a lookup miss denies" — there is no lookup to miss, and a criterion phrased around one would pass while every entered tool ran unchecked. Nor is it "refused unless a predicate admits it", which is circular once a predicate exists: the implementation's own verdict becomes the oracle, and a fall-through satisfies it. So AC-0233 is scoped to the no-predicate configuration, where an enumeration over the tool surface decides it outright, and the permanent fall-through guard is `walking-skeleton-authority-containment`'s AC-0235, which a real lookup can fail. AC-0234 keeps the refusal terminal from the first refusal this repository raises; AC-0208 asserts a different property once the real denial path exists — that the denial handler does not also swallow a tool-body bug. Traces to: AC-0202, AC-0233, AC-0234.
- **Rejected: typed output as the quarantine boundary.** It would delete the parser and a reviewer will ask. It makes the boundary depend on the framework's serializer and the model's cooperation — the same class of argument r8 uses to reject detection-based defence. Typed output stays as a layer.

### Interfaces & contracts

No external interface. The internal seams are the compiler's input (an
`agent_role` version plus a resolved integration set) and its output (an agent
with one toolset), and the parser's admitted-type contract. Each is exercised
directly by its own suite. Traces to: AC-0201, AC-0220.

### Data & schema

One expand-only migration, specified in [`role-configuration-seams`](../../architecture/role-configuration-seams/role-configuration-seams.md) § 5: `agent_role` gains
`model_settings`, `output_schema_ref` and `display_name`; `integration_registry`
gains the r5 fields plus `tools` and `pool_classes`, with its key widened to
`(integration_name, version)`. Both tables already carry the `SELECT` grants
migration 0001 gives `app_api` and `app_worker`, so the revision adds none. It
reads `entitlements` unchanged. It writes no payload object;
the first one is `walking-skeleton-step-lifecycle`'s, which is where object keys
become scope-qualified.

### Failure, edge cases & resilience

One ordering carries the story and it is not negotiable: with no predicate
installed, the decision point refuses, and the refusal is terminal. That is the
same failure direction the containment predicate uses when it arrives, which is
why installing it now costs nothing and closes the interval between the two
specs. What it does **not** close is a lookup miss falling through once a real
predicate exists; that is `walking-skeleton-authority-containment`'s AC-0235,
because it cannot be decided here. Traces to: AC-0233, AC-0234.

The quarantine boundary's resilience story is structural rather than
recovery-shaped: the candidate reference set is minted before the quarantined
agent runs, so an agent cannot produce an identifier the runtime must then
decide about. Traces to: AC-0221.

### Quality attributes (NFRs)

Inspectability is the attribute this spec carries, and the compiler is where it
lands: a compiled agent's role version, ceiling and stack are readable from the
constructed object rather than inferred from configuration.

### Dependencies & integration

New dependencies, recorded before being added per `AGENTS.md`:
`pydantic-ai-slim[bedrock]` 2.45.0. The `[bedrock]` extra is pinned here rather
than in `walking-skeleton-step-lifecycle` because T1's contract suite asserts
the `BedrockConverseModel` row of § Grounding probe, and a seam contract that
cannot import the seam is not one. Everything else is inherited from the
foundation spec's manifest.

External: none. SEC EDGAR is **not** a dependency — the corpus is the recorded
fixture. No task here reaches a provider.

## Tasks

### T1: The framework seam is pinned

**Depends on:** none

**Touches:** src/**/adapters/framework_contract.py, tests/contract/**

`pyproject.toml` is untouched: `pydantic-ai-slim[bedrock]` 2.45.0 is already pinned there under ADR-0002 D1.

**Tests:**
- The contract suite asserts every check in § Grounding probe, including the package-root import path for the deferred-requests type. A re-export moving is additive-minor drift the vendor does not class as breaking, so it must red here rather than in a runtime.
- **`no stub (goal-based)`.** This task carries no acceptance criterion; its verification is the `Done when` gate plus the recorded downgrade transcript.
- A deliberate downgrade of the pin reds the suite. **Mode: manual verification** — no test can install a different version of its own dependency. The artifact is a transcript in `notes/verification-ledger.md` showing the pin moved, the suite run, the failure, and the pin restored.
- Three probe rows this task pins, none covered before and all load-bearing: the toolset observation surfaces AC-0202 must not root on; `Model.count_tokens` raising `NotImplementedError` with no override on `TestModel` or `FunctionModel`; and `UsageLimits.per_request_input_tokens_limit` as the per-request bound AC-0246 reads, distinct from the cumulative `input_tokens_limit`.
- The original second check, restated: Without this the suite proves the current version behaves as documented and nothing about its ability to notice a change, which is the only thing it exists for.

**Approach:**
- The manifest already carries the pin under ADR-0002 D1, so `pyproject.toml` is untouched; this task writes the contract suite and the three probe rows above.

**Done when:** all five checks above hold — the contract suite green under `pytest -m 'not substrate'`, every § Grounding probe row asserted including the three this task adds, and the downgrade transcript recorded in `notes/verification-ledger.md`.

### T2: A role compiles, bad roles refuse to, and the stack denies

**Depends on:** T1

**Touches:** migrations/versions/**, src/**/adapters/postgres/roles.py, src/**/agents/compiler.py, src/**/agents/models.py, src/**/agents/toolsets/**, src/**/worker/pool.py, AGENTS.md, deploy/compose.yaml, tests/compiler/**, tests/fixtures/registry_seed.py, tests/schema/**, tests/worker/test_pool_paths.py

**Tests:**
- **Stub** (`stub: true`) — the compiler seam is `compile_role(role, integrations, pool) -> CompiledRole`, named in the design's § 2:

  ```python
  # STUB: AC-0202
  # tests/compiler/test_stack_composition.py
  from pydantic_ai.toolsets import FunctionToolset

  from ced.agents.compiler import compile_role
  from ced.agents.toolsets import (
      PolicyDecisionPoint,
      StepEventToolset,
      TrustClassToolset,
  )


  def test_the_compiled_stack_is_exactly_four_layers_in_order() -> None:
      compiled = compile_role(
          role={"role_name": "analysis", "version": 1, "ceiling": [], "pool_class": None,
                "model_settings": {"model_id": "stub:counting", "settings": {}, "limits": {}},
                "output_schema_ref": "reference-selection"},
          integrations=(),
          pool={"default_limits": {}, "allowed_model_ids": ["stub:counting"]},
      )

      chain = []
      node = compiled.stack
      while node is not None:
          chain.append(type(node))
          node = getattr(node, "wrapped", None)

      assert chain == [
          PolicyDecisionPoint,
          StepEventToolset,
          TrustClassToolset,
          FunctionToolset,
      ]
  ```

  Validation: **fails at collection** with `ModuleNotFoundError: No module named 'ced.agents.compiler'` — an import-time failure is a collection error, not a test failure. The role literal is inline rather than a fixture, because `tdd-stubs.md` forbids inventing a helper to manufacture a stub, and it carries an **empty ceiling** so AC-0260's unresolved-binding case does not fire against `integrations=()`. The chain compares imported classes, not name strings, so a rename reds only on behaviour. The seam is `role-configuration-seams` § 3; the walk roots at `CompiledRole.stack` and traverses `.wrapped`.
- AC-0260 has two cases, each a compile error rather than a call-time denial: a `ceiling` entry naming an integration the compiler was not given, and a `tool_name` absent from that integration's `tools`.
- AC-0201's two cases are a different defect and are asserted **against the constructed `Agent`**: a tool registered through the framework's decorator, and a second entry in `toolsets=[…]`. Each must fail the build. AC-0202's walk roots at `CompiledRole.stack` and so never reaches the `Agent`, which carries its own `_AgentFunctionToolset` alongside anything passed — that is precisely where a sibling tool hides, and it is why AC-0202 cannot absorb these two.
- AC-0202 walks the constructed chain and asserts the type order; the checker is separately unit-tested against hand-built wrong chains, which is what lets the ordering be asserted without the compiler accepting a layer list.
- AC-0203, AC-0204, AC-0205, AC-0219 and AC-0251 are each a role record the compiler must reject or constrain. AC-0203's case set covers every non-quarantined role the skeleton carries, not just the planning one, because that is the scope r5's R2 states. AC-0205 asserts the compiled budgets are zero rather than that the role record requested zero — the record is the input, the compiled agent is the fact.
- AC-0246 uses a stub model that records whether its request method ran, with a ceiling below the counted tokens. A settings read would pass on a flag that is set and never consulted; the stub is what makes "before the request" observable. AC-0206 cannot see this either way.
- AC-0206 needs all three of its clauses: a role wider than the pool default fails the build, a narrower one compiles to its own value, and **a key the role omits inherits the pool's, asserted on the compiled value rather than on the role record**. Only the widening case protects the operator's reviewable deploy, and it fails rather than clamps so the role file and the limit in force cannot disagree. The omitted-key case is the one whose failure is silent: a compiler that drops an omitted key yields the unset default, which 2.45.0 treats as unlimited, and AC-0265 cannot catch it because it only ever compares the pool against itself.
- AC-0269 feeds a role a `model_settings.settings` key outside the declared set and asserts the compile fails. The admitted set is the design's three keys; the case to write is a key `ModelSettings` itself accepts, such as `extra_headers`, so the test distinguishes the compiler's allowlist from the framework's TypedDict.
- AC-0267 feeds a non-quarantined role an `output_schema_ref` outside the declared set and asserts the compile fails. **The value must be one no named successor adds to the set** — `not-a-contract` rather than `free-form`. `walking-skeleton-step-lifecycle`'s AC-0255 adds `free-form` as the set's third member, so a case pinned to it stops testing membership at exactly the moment the set grows, and reds in that spec's PR for the wrong reason. Refusing a *permissive member* on a non-quarantined role is a different rule from refusing a non-member, and AC-0255's guard is scoped to quarantined roles only; the criterion that carries it belongs to the spec that adds the member, and AC-0267 names that hand-off.
- AC-0273 feeds the loader an `integration_registry` row for each of the four refusal shapes its criterion names — `tools` absent, `null`, a non-array, and `[]` — and asserts each fails to load naming the row. The empty-array case is the one worth writing first: it is the shape that otherwise reaches `list_integration_tools()` and silently shrinks AC-0233's enumeration rather than failing anywhere.
- AC-0266 feeds the loader an `integration_registry` row whose `trust_class` is a near-miss of a real member, not an obviously foreign string, so a membership test passes and a substring or case-insensitive test reds.
- `verify_boot` refuses a missing or malformed `CED_POOL_DEFAULT_LIMITS` or `CED_POOL_ALLOWED_MODEL_IDS`, naming the variable. Both are required with no in-code default on a `restart: "no"` fleet, so the failure must be legible at startup rather than at first claim; `src/ced/worker/pool.py:167` is the existing seam.
- **AC-0265 is a distinct case from that one and needs its own artifact:** a present, well-formed `CED_POOL_DEFAULT_LIMITS` object that omits or nulls one of the four integer keys is neither missing nor malformed, so the variable-level check passes it. The case supplies exactly such an object and asserts `verify_boot` fails **naming the key**, once per key, because three of the four `UsageLimits` fields default to `None` and a pool that ships one unset is unlimited on that axis.
- AC-0270 supplies a `CED_POOL_DEFAULT_LIMITS` carrying `count_tokens_before_request` as `true` and asserts `verify_boot` fails; the `false` case is admitted. ADR-0006 § Confirmation assigns this predicate to this spec by name. An omitted key passes, which is the decided third case: 2.45.0 defaults the flag to `False`, so omission is already the state D1 wants.
- **Pool-configuration validation runs before `verify_boot` opens either connection**, and that ordering is what keeps AC-0265 and AC-0270 in the offline gate. `verify_boot` (`src/ced/worker/pool.py:167`) currently opens the worker and policy `psycopg` connections unconditionally and does nothing else, so a configuration case that had to reach a successful boot would need Postgres. Validating the environment first means both criteria are decided on the refusal path and on the admitted-configuration return, with no connection attempted — a malformed pool configuration should fail before the process reaches for a database in any case.
- **One substrate check joins the migration to the loader**, because nothing else does: it inserts a role row and its pinned registry rows, reads them back through the real `load_role`, and asserts the model id, the four declarable limits, the output-contract name, the ceiling, and the registry columns the compiler reads — `tools` and `pool_classes` in particular, since `pool_classes` is otherwise read only by AC-0258, which runs offline against a record and so cannot catch a name the migration and the loader spell differently. **The same check drives one malformed record through the real `load_role` and asserts it is refused**, because AC-0251's omitted-`model_id` clause, AC-0262 and AC-0266 all say *fails to load* and are otherwise decided only on the decode seam: a `load_role` that parses inline and never calls that seam ships with all three green. The `tests/schema/` check names columns and the offline loader criteria are fed a record, so a column the migration spells one way and the loader reads another way is green on both sides and first observed as a step failing at compile time in production. This is the design's own inspectability verification, "a loader test asserting all four from one row".
- The offline loader criteria call `decode_role_record(role_record, integration_records)` directly. `load_role(role_name, version)` opens its own query and cannot be fed a record, so it queries and then calls the decode seam; the record-shape refusals AC-0262 and AC-0266 live in the decode seam, which is what makes them offline criteria rather than substrate ones.
- AC-0233 enumerates the skeleton's roles and registered tools, drives a call through each with a spy the tool body increments, and asserts no spy moved. The spy is what makes "did not execute" observable rather than inferred, and the enumeration is what stops the criterion passing on a miss path alone. **It also carries the criterion's last clause, which the spy alone does not:** at least one pair must be recorded as refused *at the decision point*, distinguished from a pair refused earlier at resolution. Without that distinction an implementation in which every pair dies at resolution, with the decision point never wired, satisfies every other clause. The suite runs in the no-predicate configuration the criterion names, so it retires with that configuration rather than being carried forward by the successor.
- AC-0234 asserts the raised type is not the framework's retry type nor a subclass. A bare "raises" assertion passes on the wrong one, and the wrong one degrades the boundary into a negotiation with no visible failure.
- Tools resolve as module-level callables from the registry; a closure trips the framework's context-parameter inference, which the probe hit directly.

**Approach:**
- The refusal seam is the compiler's return path, not the agent's: a role record that violates a guard never produces an agent, so there is no object a caller could hold and invoke. That is what makes AC-0201 through AC-0205 compile errors rather than call-time denials.
- The usage-limit narrowing is applied where the pool default is known, so the compiled agent carries the resolved value and the role record keeps the requested one. Resolving it at call time would make AC-0206's widening case unobservable on the compiled agent.
- **`PoolConfig.model_factory` is typed by a `Protocol` declared in `worker/`, not by `Callable[[str], Model]`.** `PoolConfig` lives in `src/ced/worker/pool.py`; `tests/architecture/dependency_direction.py` admits a `pydantic_ai` name only in `agents/` and `adapters/`, and its AST walk reaches a `TYPE_CHECKING`-guarded import, so the design's literal annotation would red the offline gate and break this spec's own `Never do`. `pydantic_ai.models.Model` is named only in `ced.agents.models`, which supplies the factory. The seam's shape is unchanged; the design records the indirection as of its 2026-09-21 ratification.
- The decision point is installed as the outermost layer with no predicate bound to it. It holds a reference to a resolver that has no entries, which is what makes the interval refuse by construction rather than by a branch someone can delete.

**Done when:** AC-0201 through AC-0206, AC-0219, AC-0234, AC-0246, AC-0251, AC-0258, AC-0259, AC-0260, AC-0262, AC-0265, AC-0266, AC-0267, AC-0269, AC-0270 and AC-0273 are green under `pytest -m 'not substrate'`, with `tests/architecture/test_dependency_direction.py` still green in that same run — it is what holds the `Never do` the `model_factory` seam bends around; AC-0233, AC-0261, a `tests/schema/` check and the migration-to-loader round-trip check are green under the full `pytest` run against the Compose substrate. That `tests/schema/` check must name each added column, the widened `(integration_name, version)` key and the retained `SELECT` grants: its existing `EXPECTED_TABLES` assertions pass verbatim against a revision that adds nothing, so the new surface has to be named to be gated. The round-trip check is separate and is not satisfied by it — naming a column proves the migration wrote it, not that the loader reads that name.

### T3: The parser admits only what the boundary allows

**Depends on:** T2

**Touches:** src/**/domain/quarantine/**, src/**/agents/toolsets/trust_class.py, tests/quarantine/**, tests/fixtures/candidate_set_expected.json

**Tests:**
- **Stub** (`stub: true`) — the parser seam is `ced.domain.quarantine.parser.admit(value)`:

  ```python
  # STUB: AC-0220
  # tests/quarantine/test_parser_admits.py
  import pytest

  from ced.domain.quarantine.parser import AdmittedTypeRefused, admit


  def test_free_text_is_refused() -> None:
      with pytest.raises(AdmittedTypeRefused):
          admit("Apple reported record revenue this quarter.")


  def test_a_closed_vocabulary_label_is_admitted() -> None:
      assert admit("revenue-recognition") == "revenue-recognition"
  ```

  Validation: **fails at collection** with `ModuleNotFoundError: No module named 'ced.domain.quarantine'` — the missing package, not the module. The admitted case is paired with the refusal because a rejection-only stub is satisfied by an `admit` that raises on everything. The mint interface AC-0238 and AC-0250 read is **`no stub (implementation-discovered)`**: the candidate set is per-step in-process state by the owner's ruling of 2026-09-20, and its holder is chosen while building the minting pipeline under `src/**/domain/quarantine/**` — this task's own `Touches`, so the predicate resolves inside T3 rather than waiting on a step path no task in this plan defines. Proof obligation: write the red assertion against the mint interface as discovered, prove the red, and record the seam in `notes/verification-ledger.md` before production code.
- AC-0220 feeds the parser output that is neither a closed-vocabulary label nor a typed scalar and asserts the step fails. The parser is the runtime's, outside the agent — a test that drives the agent's structured output instead is testing the layer, not the boundary.
- AC-0268 feeds the parser a well-formed label the declared vocabulary does not contain and asserts refusal. The vocabulary is a module-level constant of the runtime under `src/**/domain/quarantine/**`, and the suite reads that constant rather than restating its members, so widening it is a reviewable diff and cannot be done silently by the implementation the suite is meant to catch. A second case pins that the vocabulary is not read from a role record, a registry row or model output.
- AC-0238's expected set is `tests/fixtures/candidate_set_expected.json`, committed beside the recorded filing and compared literally. Deriving the expectation by calling the mint pipeline would make the assertion unfailable for a pipeline that derives the wrong set; a committed file makes every change to that set show up in review, which is the update path.
- AC-0274 feeds the parser a value of a type outside the declared admitted-scalar set, and a second case whose type is an admitted enumeration but whose value is not a member of it. Both assert refusal. The declared set is r8 § 4's and lives beside the label vocabulary as a module-level constant; the suite reads the constant for the same reason AC-0268's does. The negative case must not be free prose — AC-0220 already covers that, and a scalar-shaped value is the only thing that distinguishes this criterion from it.
- AC-0221 is the criterion to write first and trust least: a well-formed reference that resolves in *another* step's set must still fail. Shape validity is not provenance, and a parser that checks only shape admits an attacker-chosen value inside a well-formed reference.
- AC-0238 asserts non-emptiness, an ordering and an equality: the pre-turn set equals the committed baseline named above, which is what stops a mint producing nothing from satisfying both snapshots. It also asserts the recorded mint precedes the agent's first model turn, and the before and after snapshots match. AC-0250 is separate because a set nothing tries to mutate satisfies AC-0238 with no enforcement built at all. A post-run probe alone cannot see a resolver that consults a second source while the agent runs, which is the "agent emits, resolver accommodates" shape this criterion exists to catch.

**Approach:**
- The integration result the parser judges arrives through the runtime's own retrieval path, not as a tool-body return value, so AC-0220, AC-0242 and AC-0233's blanket refusal are consistent. This is the same construction AC-0219 forces: a quarantined role resolves no integrations, so it has no tool to call.
- The quarantine spine reaches no registered tool: the quarantined role resolves no integrations (AC-0219), so the spine and AC-0233's blanket refusal are satisfiable together. The planning-step half of that spine is `walking-skeleton-step-lifecycle`'s T5, under AC-0222.
- The deterministic pipeline mints the candidate reference set *before* the quarantined agent runs. The agent selects and labels among candidates that already resolve and cannot mint an identifier. Building the weaker construction — agent emits, parser rejects — is the failure mode here, and it is the one spike 4 measured and the design explicitly moved away from.

**Done when:** AC-0220, AC-0221, AC-0238, AC-0250, AC-0268 and AC-0274 are green under `pytest -m 'not substrate'`. AC-0222 and AC-0242 moved to `walking-skeleton-step-lifecycle`, which owns the step path they fail through.

### T4: The record says what this spec established and what it did not

**Depends on:** T3

**Touches:** spikes/README.md, docs/architecture/README.md, docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md

**Tests:**
- `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` is green.
- **`no stub (goal-based)`.** This task carries no acceptance criterion; its verification is the lint above plus a reader check that the record separates what was established from what was not.

**Approach:**
- State plainly that the quarantine criteria establish the boundary holds against the cases written, and establish nothing about an adaptive adversary — r8 records that no structural defence has been tested under an unlimited budget, and that gap stays open.
- Update `docs/architecture/README.md` § What is built, which is the map where partial progress is expressible. r5's STATUS header lists the agent layer, the authorization boundary and the provider call as unbuilt. Move the first clause only; the other two are the siblings'.

**Done when:** the status lint is green and the record separates what was established from what was not.

## Rollout

- **Delivery:** three stacked PRs — T1+T2, T3, T4. Each leaves the repository working and is independently reviewable.
- **Review shape:** T3 is **DEEP** and is sized as its own PR for that reason: it is security-boundary work that attracts a mandatory security review, and it carries a failure mode that is invisible in a passing suite. T2 is **MIXED** — the compiler plus its refusal cases — and splits at the seam between construction and the structural checker if the diff outgrows one reviewable unit. No task here is WIDE.

## Risks

- **The quarantine boundary can be built weak and still pass a shape test.** The pipeline-first construction is the whole guarantee, and a parser that validates shape without a minting authority looks identical in a green suite. AC-0221 is the specific guard; it is named here because it is the criterion most worth an adversarial read.
- **The decision point stands on a framework object.** A change to the wrapper's `call_tool` contract is a change to the authorization boundary and could land in a minor release without being classed as breaking. Mitigated by the T1 contract suite.
- **The blanket refusal can be quietly widened when the predicate lands.** `walking-skeleton-authority-containment` replaces "nothing admits" with a real lookup, and the cheapest way to make its own positive-path criterion pass is to let a miss fall through. AC-0233 cannot catch that — it is scoped to the configuration being replaced — which is why the guard is a criterion in that spec, AC-0235, rather than a re-run of this one.
- **A schema need discovered here is an amendment to a shipped sibling spec.** Mitigated by the foundation spec creating the three agent tables up front, but not eliminated.

## Changelog

- 2026-09-20: initial plan. Cut from `walking-skeleton-agent-runtime`, whose single contract carried AC-0201 through AC-0232 across nine tasks and six stacked PRs — roughly two and a half times either Phase 1 sibling. This spec takes the compiler, the toolset stack and the quarantine boundary; the containment fragment and decision point go to `walking-skeleton-authority-containment`, and the step lifecycle to `walking-skeleton-step-lifecycle` after it. AC-0233 and AC-0234 are the criteria the split creates: the parent spec never needed either, because the decision point's position and its predicate landed in the same contract. The three form a chain: an earlier draft claimed the last two were parallel, which an adversarial spec review falsified, because `walking-skeleton-step-lifecycle`'s AC-0227 requires an approved tool body to run and nothing can admit a call until the predicate exists.
- 2026-09-20: spec approved by eugenelim
- 2026-09-20: plan approved by eugenelim
- 2026-09-21: amendment closing the sustained findings of the round-4 pre-EXECUTE review. Two blockers were defects the round-3 amendment itself introduced: the pinned `Tests` list carried both the new committed-baseline oracle for AC-0238 and the pipeline-derived one it replaced, and naming `decode_role_record` as the offline seam left AC-0251's omitted-`model_id` clause, AC-0262 and AC-0266 asserted only on that seam while each says *fails to load*, so the substrate round-trip now drives one malformed record through the real `load_role` and also covers `tools` and `pool_classes`. AC-0267's case value moves off `free-form`, which a named successor adds to the set. AC-0233's bullet gains the refusal-site distinction its criterion's last clause states. Pool-configuration validation is stated to run before `verify_boot` opens either connection, which is what keeps AC-0265 and AC-0270 offline. AC-0273 and AC-0274 are new.
- 2026-09-21: amendment closing the sustained findings of the round-3 pre-EXECUTE review — adversarial, quality-engineer and security-reviewer, each adjudicated independently. T2's `Tests` gains AC-0201's own two cases (the bullet filed under it restated AC-0260's contract verbatim, leaving AC-0201 with no artifact and AC-0260 with two), AC-0206's omitted-key clause, a per-key AC-0265 case distinct from the variable-level `verify_boot` check, and cases for the four criteria added to the spec. Two verification gaps close: a substrate round-trip check joins the migration to the loader, since naming a column and feeding the loader a record both pass when the two spell it differently; and AC-0238's expectation becomes a committed baseline rather than a second call to the pipeline under test. `decode_role_record` is named as the seam the offline loader criteria call, because `load_role` opens its own query and cannot be fed a record. T2's `Approach` records that `PoolConfig.model_factory` is typed by a `Protocol` in `worker/`, since the design's literal `Callable[[str], Model]` would red `tests/architecture/test_dependency_direction.py` and break this spec's own `Never do`; the owner chose that indirection over widening the gate, and the ratified design now records it.
