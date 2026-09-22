# Verification ledger — walking-skeleton-role-compilation

Execution observations for this spec. The spec and plan are pinned; anything
learned while building goes here.

## T1 — the downgrade transcript (manual verification)

**Date:** 2026-09-21. **Machine:** the project virtualenv at `.venv`, Python
3.13.13, `pydantic-ai-slim` pinned to 2.45.0 by `pyproject.toml` under
ADR-0002 D1.

T1's second check cannot be a test: no test can install a different version of
its own dependency. This is the hand-run record.

### 1. The suite is green on the pin

```
$ ./.venv/bin/python -m pytest tests/contract -q
...........................                                              [100%]
27 passed in 3.40s
```

### 2. The pin is moved down one minor release

```
$ ./.venv/bin/pip install 'pydantic-ai-slim[bedrock]==2.44.0'
...
Successfully installed pydantic-ai-slim-2.44.0 pydantic-graph-2.44.0
ERROR: pip's dependency resolver does not currently take into account all the
packages that are installed. ... company-intelligence-desk 0.1.0 requires
pydantic-ai-slim[bedrock]==2.45.0, but you have pydantic-ai-slim 2.44.0 which
is incompatible.
```

2.44.0 resolved, so no substitute release was needed. `pip` reports the
manifest conflict and installs anyway — which is the point: the manifest pin
alone does not stop an environment drifting, so something has to fail loudly.

### 3. The suite reds

```
$ ./.venv/bin/python -m pytest tests/contract -q
.........................F.                                              [100%]
____________ test_the_installed_distribution_is_the_pinned_version _____________

    def test_the_installed_distribution_is_the_pinned_version() -> None:
>       assert version(FRAMEWORK_DISTRIBUTION) == PINNED_FRAMEWORK_VERSION
E       AssertionError: assert '2.44.0' == '2.45.0'

1 failed, 26 passed in 3.29s
```

### 4. The pin is restored and the suite is green again

```
$ ./.venv/bin/pip install -e '.[dev]'
Successfully installed company-intelligence-desk-0.1.0 pydantic-ai-slim-2.45.0
  pydantic-graph-2.45.0

$ ./.venv/bin/pip show pydantic-ai-slim
Name: pydantic-ai-slim
Version: 2.45.0

$ ./.venv/bin/python -m pytest tests/contract -q
...........................                                              [100%]
27 passed in 3.40s
```

### What this establishes, and what it does not

**Established:** an environment that does not carry the pinned release fails
the offline gate, at collection-adjacent speed and with the two versions named
in the failure message. A drifted virtualenv cannot reach a runtime.

**Not established:** that any *seam* row notices this particular downgrade.
Exactly one assertion reded, and it is the version identity itself; the other
twenty-six passed on 2.44.0. That is the expected result and not a weakness in
the rows — plan.md § Grounding probe records that the probe disconfirmed none
of its claims on 2.45.0, which is precisely the statement that 2.44.0 and
2.45.0 agree on every seam this design rests on, and is what licensed the pin
move. A downgrade that *did* move a seam would red the row that covers it; no
such downgrade is available one release back, and reaching for a release far
enough back to break a seam would be choosing the evidence.

The seam rows are therefore verified by construction rather than by this
transcript: each is asserted against inspected signatures, declared dataclass
fields, declared `TypedDict` keys, or observed behaviour, never against
`hasattr`. `tests/contract/test_seam_module.py` additionally pins that every
name `ced.adapters.framework_contract` exports is the framework's own object.

## T1 — probe facts learned while writing the suite

Two facts the pinned release carries that plan.md § Grounding probe does not
state, both found by reading the installed package rather than inferred:

- `UsageLimits.request_limit` defaults to **50**, not to `None`. The other
  three declarable ceilings default to `None`, which is unlimited. The suite
  pins all four defaults, because "the field exists" and "the field bounds
  anything when a role omits it" are different facts and AC-0265 reads the
  second.
- `BedrockConverseModel('<model-id>')` needs an ambient AWS region — the
  constructor resolves a provider, which raises `UserError: You must provide a
  region_name or a boto3 client for Bedrock Runtime.` without one. The
  signature claim in the probe row holds exactly as written: `model_name` is
  the only parameter without a default. The region is a deployment input, not
  a second constructor argument, and `walking-skeleton-step-lifecycle` owns
  where it comes from. No network call is made either way.

## T2a — the migration and the loader

T2 is MIXED and was split at dependency-ordered layers. Layer (a) is revision
0003, `ced.adapters.postgres.roles`, the `tests/schema/` delta check, the
offline loader suite and the substrate round-trip. The compiler, the toolsets,
the pool configuration and the parser are later layers.

**`trust_class`'s closed set is `{"admitted-types", "free-text"}`, and that is
a reading of r5 § 4 rather than a transcription of its table.** That table's
Declared column has four rows: `admitted-types`, `admitted-types` + reference
output, `free-text`, and `absent → Not registrable`. Only two are values a
`text NOT NULL` column holds. The second row is r5's split of the admitted set
by whether a minting authority exists — a rule that applies when
admitted-types output carries references — and not a third string anyone would
write into the column; the fourth is the table's own name for not being
registrable. The set is declared as a module-level frozenset with that reading
recorded beside it, and `tests/compiler/test_role_loader.py` pins the set
itself so widening it is a reviewable diff. One AC-0266 case feeds the second
row verbatim as a string, because a loader that admitted it would widen a set
the migration adds no CHECK on. (Controller ruling, implemented as given.)

**Revision 0001's `ceiling` column comment was edited, by controller ruling.**
The ratified design § 8 assigns this spec the job of amending it to name
`walking-skeleton-authority-containment`, because the predicate half moved
there. The implementer carried the correction as a superseding comment in
revision 0003 instead, on the ground that rewriting an applied revision makes
the file disagree with every database it ran against. The controller overruled
that and made the one-line edit as well, for two reasons. The text is a SQL
comment inside a `CREATE TABLE` string, discarded by Postgres and read by no
test, so editing it changes nothing about what ran. And leaving the corrected
statement in 0003 beside the superseded one in 0001 is the precise failure this
spec's review found five times: a literal search for the new wording does not
find the old claim in different words. 0003's paragraph was rewritten in the
same edit so the two files do not now disagree about which was amended.

**Observed against the migrated database, not inferred from the DDL.**
`alembic upgrade head` from 0002 produced exactly the § 5 delta:
`information_schema.columns` reports `integration_registry.tools` as
`jsonb / YES / NULL` — nullable with no default, which is the choice nothing
else pinned — and `pg_get_constraintdef` reports
`PRIMARY KEY (integration_name, version)` under the name
`integration_registry_pkey`, which Postgres reuses after the drop.
`information_schema.table_privileges` reports exactly four rows for the two
tables and the two reading roles, all `SELECT`, confirming 0001's grants
survive and that revision 0003 needs none: a column inherits its table's grant.
`config` is still present as `jsonb`, unread.

**`load_role` reads the registry rows before the ceiling has been judged**, so
pin extraction is deliberately tolerant — a malformed ceiling yields no pins
and the refusal still comes from `decode_role_record` with its own message.
Raising during extraction would move the refusal off the seam the offline
criteria are decided against, and would make the substrate delegation check
pass for the wrong reason.

**The three seams open their own connections as `app_worker`.** The pinned
signatures take no connection — `load_role(role_name, version)`,
`list_roles()`, `list_integration_tools()` — and compilation happens at step
start in the worker, which is the narrower of the two roles holding `SELECT`.
This differs from `event_log.py`, whose functions take a connection because
they participate in the caller's transaction; these are plain reads that do
not.

**Gate counts.** Offline went from 62 passed / 1 failed to 85 passed / 1
failed; the failure is the pre-existing `.github` case in
`tests/architecture/test_recorded_layout.py`. `ruff format --check .` still
exits 1 on `plan.md:250` alone, also pre-existing. Substrate: 167 passed, 4
skipped in 28 s, the skips being `tests/fault_injection` with no worker
containers started.

## T2b — the pool configuration and the operational surfaces

**Date:** 2026-09-21. Worktree `walking-skeleton-role-compilation`, the project
virtualenv at `.venv`, Python 3.13.13, `pydantic-ai-slim` 2.45.0. Postgres and
MinIO up from `deploy/compose.yaml`, schema at revision 0003; the worker
containers were **not** started, so `tests/fault_injection` skipped.

**What the layer built.** `validate_pool_config(env) -> PoolConfig` parses
`CED_POOL_DEFAULT_LIMITS` and `CED_POOL_ALLOWED_MODEL_IDS`; `verify_boot(env)`
calls it first and returns the validated config, and `PoolConfig` gained
`default_limits` and `allowed_model_ids`. `PoolConfig.from_environment` is
gone — `validate_pool_config` is what replaced it, and its one caller was
`run()`. `model_factory` is **not** added: its `Protocol` and its only
consumer, `ced.agents.models`, belong to the later layer, and adding the field
now would mean a placeholder or an import of a module that does not exist.
That is the open hand-off out of this layer.

**`verify_boot`'s signature changed, and it had to.** It took a `PoolConfig`;
it now takes the environment, because the callable AC-0265 and AC-0270 name has
to be the one that parses. `run_forever` no longer calls it — `run()` does, and
constructs the `Worker` from what it returns, so no worker is built from a
configuration the boot check has not admitted. `src/ced/worker/main.py`
re-exports `run` and needed no change.

**The defaults this rests on were read off the installed package, not
inferred.** `dataclasses.fields(pydantic_ai.usage.UsageLimits)` on 2.45.0:
`request_limit` default `50`; `per_request_input_tokens_limit`,
`input_tokens_limit`, `tool_calls_limit`, `cost_limit`, `output_tokens_limit`,
`total_tokens_limit` all default `None`; `count_tokens_before_request` defaults
`False`. So an omitted key is unlimited on three of AC-0265's four axes and
silently bounded at 50 on the fourth, and AC-0270's omitted-key case is already
the state ADR-0006 D1 wants.

**Two refusals beyond the criteria's literal text, both recorded as decisions.**
A limits key outside the closed shape is refused naming it: the AC-0270 guard
reads one exact name, so a misspelled `count_tokens_before_request` would
otherwise pass unseen while looking deliberate. A non-integer value for one of
the four keys is refused naming the key, with `bool` excluded explicitly —
`bool` subclasses `int`, so a JSON `true` would land as a request limit of 1.
An **empty** `CED_POOL_ALLOWED_MODEL_IDS` array is admitted: no criterion
refuses it, and AC-0251 gives a better error with the role in hand than a boot
failure naming no role.

**The delegation gap is closed by measurement, not by reading.** With
`verify_boot` mutated to build a `PoolConfig` inline instead of calling
`validate_pool_config`, 27 of the 30 checks in
`tests/worker/test_pool_configuration.py` fail; the 3 survivors are the
admitted cases, which call `validate_pool_config` directly and are observable
nowhere else. The suite's autouse fixture replaces `psycopg.connect` with a
function that fails the test, so "the refusal precedes the connection" is
asserted rather than assumed — without it these checks would pass against a
running substrate for the wrong reason.

**The documented invocation was run, not reasoned about.** The `AGENTS.md`
§ Running the two deployables block, copied verbatim, logs
`boot: worker connection verified as app_worker`, then the policy connection,
then `ready: worker-<pid> polling class default`, and exits 0 on `SIGTERM`.
With both variables unset the same entry point exits **1** on
`ValueError: CED_POOL_DEFAULT_LIMITS is required and is unset; it has no
in-code default`.

**Compose was verified through Compose's own renderer.** `docker-compose -f
deploy/compose.yaml config` renders both `worker-a` and `worker-b` with the two
new variables, and `validate_pool_config` accepts each rendered environment.
The folded (`>-`) block keeps its newlines because the continuation lines are
more-indented, which is immaterial: JSON treats them as whitespace, and the
rendered string parses. `worker-b` carries its own copies because `environment`
replaces rather than merges under the `<<` anchor.

**Statements walked backwards.** `PoolConfig.from_environment`'s docstring said
Compose sets "only the worker id and the step-body duration" — already false for
`CED_POOL_CLASS` and now false twice over; the text moved to the `PoolConfig`
class docstring and was corrected. The module docstring's boot-sequence bullet
gained the validation step. `deploy/compose.yaml`'s MinIO comment, the
foundation ledger's "MinIO is not in the worker boot check", and
`AGENTS.md`'s `CED_POOL_CLASS` note all stay true and were left alone.
`docs/specs/walking-skeleton-role-compilation/notes/pre-execute-gate-findings.md`
still says `from_environment` reads two variables — correct as a record of what
the gate found, and not edited.

**Gate counts.** Offline went from 85 passed / 1 failed to **115 passed / 1
failed in 9.11 s**; substrate-only is **167 passed, 4 skipped in 33.84 s**,
unchanged; the whole suite is **282 passed / 1 failed / 4 skipped in 38.80 s**,
against a 252/1/4 baseline. The failure is the pre-existing `.github` case in
`tests/architecture/test_recorded_layout.py`. `ruff format --check .` still
exits 1 on `plan.md:250` alone; `ruff check .` and `mypy` pass.
`tools/lint-no-identifiers.py`, `tools/hooks/pre-pr.py` and
`lint-spec-status.py --all` are clean.

**The worker containers were started against the new required variables, not
reasoned about.** Layer (b) makes `CED_POOL_DEFAULT_LIMITS` and
`CED_POOL_ALLOWED_MODEL_IDS` required with no in-code default on a
`restart: "no"` fleet, so a compose file that set them wrongly would leave both
workers dead and cost `tests/fault_injection` its two-worker precondition — the
failure that looks unrelated. Controller check, after the layer landed:

```
$ docker-compose -f deploy/compose.yaml up -d --build worker-a worker-b
$ docker-compose -f deploy/compose.yaml logs worker-a
worker-a-1  | INFO ced.worker.pool boot: worker connection verified as app_worker
worker-a-1  | INFO ced.worker.pool boot: policy connection verified as app_policy
worker-a-1  | INFO ced.worker.pool ready: worker-a polling class fault-injection
$ ./.venv/bin/python -m pytest
1 failed, 286 passed in 179.29s
```

Both containers reached `ready`, and the full run at r7's real lease timings is
286 passed with the four `tests/fault_injection` checks no longer skipped. The
one failure is the pre-existing `.github` layout case. 179 s sits inside the
spread `AGENTS.md` § The local substrate declines to publish a range for.

## T2c — the toolset stack and the structural checker

Layer (c) of T2: `src/ced/agents/toolsets/**` and the offline suite under
`tests/compiler/`. The compiler, `ced.agents.models` and the quarantine parser
are later layers and are not here.

### What was observed by running it, not asserted

**`WrapperToolset` is a `@dataclass`, and a subclass that adds state must be
one too.** `for_run` and `for_run_step` rebuild the layer with
`dataclasses.replace`, which calls `type(obj)(...)` from `__dataclass_fields__`.
A plain subclass carrying an extra attribute therefore breaks at that call and
not at construction, which is the worst place to find it. Probed directly
against the installed 2.45.0:

```
$ ./.venv/bin/python -c '...'
['wrapped']                                     # fields(WrapperToolset)
7                                               # @dataclass subclass: replace keeps `extra`
plain replace fails: TypeError Plain.__init__() missing 1 required positional argument: 'extra'
```

All three layers are `@dataclass` for that reason, and each says so in its own
docstring.

**`RunContext.tool_call_id` is annotated `str | None` and is populated at
`call_tool`.** `derived_idempotency_key` takes a `str`, so the annotation is
not academic. Probed by driving a real `Agent(TestModel())` through a spy
wrapper:

```
[('ping', 'pyd_ai_tool_call_id__ping', '01a0c4cd-a83a-70d2-b0ca-3d722d1683bb')]
```

The value is present in practice; the layer still refuses rather than deriving
a key from a substitute, because an absent id means the fence has nothing to
dedup on.

### What the new suite decides, and what it does not

- `tests/compiler/test_stack_order_checker.py` decides **AC-0202's second
  predicate only** — the checker rejects a hand-built chain in any other
  composition, and accepts the ratified one. Seven wrong compositions, each a
  chain the compiler must never produce. AC-0202's first predicate walks a real
  `CompiledRole.stack` and belongs to the compiler layer.
- `tests/compiler/test_decision_point_refuses.py` decides **AC-0234**, in both
  directions: the raised type is the interval's declared `ToolCallDenied`, and
  it is neither `ModelRetry` nor a subclass. `ModelRetry`'s identity comes from
  `ced.adapters.framework_contract`, so the exclusion is measured against the
  same object production code resolves.
- **AC-0233 is not decided here.** It enumerates by reading `agent_role` and
  `integration_registry` and carries the `substrate` marker; it needs the
  compiler and both registries, which are later layers.
- **AC-0201 is not decided here.** It is asserted against the constructed
  `Agent`, which this layer does not build.

### Paths this layer ships unexercised, and why that is by contract

`StepEventToolset.call_tool` and `TrustClassToolset.call_tool` are never
reached. The decision point sits above both and refuses every call until
`walking-skeleton-authority-containment` supplies the predicate, so no tool
body executes anywhere in this spec — the spec's § Testing Strategy states
this outright. The refusal is by construction: the decision point admits only
when its resolver returns an admitting entry, and its default resolver,
`NoCeilingEntries`, has none. One check rehearses the admit path with an
injected resolver that admits, which is what shows the refusal came from the
resolver being empty rather than from a literal someone could invert.

`PolicyDecisionPoint`'s delegation to the wrapped layer is unreachable for the
same reason.

**A limit recorded rather than designed around.** r5 § 2 wants
`tool.completed` to carry the parse outcome, so a result the trust-class layer
rejects is attributable rather than merely absent. The shipped `events`
envelope has no outcome column and no payload object is written until
`walking-skeleton-step-lifecycle`, so a raising parse leaves `tool.invoked`
appended with no completion beside it. What a reader can tell today is that the
call started and did not finish. Recorded in `step_events.py`.

### Gates

```
$ ./.venv/bin/ruff format --check .        exit 1 — plan.md:250 only, the known pinned stub
$ ./.venv/bin/ruff check .                 exit 0 — All checks passed!
$ ./.venv/bin/mypy                         exit 0 — no issues in 21 source files
$ ./.venv/bin/python -m pytest -m 'not substrate'
                                           exit 1 — 1 failed, 131 passed in 9.40s
$ ./.venv/bin/python -m pytest             exit 1 — 1 failed, 302 passed in 175.41s
$ python3 tools/lint-no-identifiers.py --staged   exit 0
$ python3 tools/hooks/pre-pr.py                   exit 0
```

Offline moved 115 → 131 and the full run 286 → 302, both +16. The single
failure in each is the pre-existing `.github` layout case.
`tests/architecture/test_dependency_direction.py` is green in both runs, which
is what holds the `Never do` on `pydantic_ai` imports: `agents/` is an admitted
layer, so this package importing the framework is legal.

**`framework_contract`'s docstring was corrected in this layer, not left to
disagree with its own test.** T1 wrote "every framework name the agent layer
depends on is bound here". Layer (c) made that false: `RunContext`,
`ToolsetTool` and `AbstractToolset` resolve directly in
`agents/toolsets/`, which `tests/architecture/dependency_direction.py` admits
because `agents/` is an allowed layer. Routing them through the seam module
would have redded T1's own
`test_the_exported_surface_is_exactly_the_seam_plus_the_pin_constants`, which
closes `__all__` to the § Grounding probe rows plus the two pin constants.

The implementer surfaced the disagreement and correctly declined to resolve it
itself. The controller resolved it toward the test rather than the docstring:
the probed set is the thing with a claim behind it and a suite asserting it,
and widening the seam into an import hub would make the contract suite assert
a set nobody chose. The docstring now states the narrow rule and names the
three exceptions, so the file no longer promises something it does not do.

## T2d

Layer (d) of T2: `ced.agents.compiler`, `ced.agents.models` and the
`PoolConfig.model_factory` seam. Layers (a), (b) and (c) are committed; the
compile-time role refusals are layer (e)'s and are not here.

### The approved stub, before any production code

The AC-0202 stub was extracted **programmatically** from `plan.md` lines
236–268 — read, two-space fence indent stripped, written to
`tests/compiler/test_stack_composition.py`. Byte identity was then verified by
re-adding the indent and comparing against the plan's own lines:

```
fence open : '  ```python\n'
fence close: '  ```\n'
line count plan/file: 33 33
BYTE IDENTITY (after re-adding the 2-space fence indent): True
plan == plan_norm (no trailing-space blanks in plan): True
```

The observed red, run before `src/ced/agents/compiler.py` existed, matches
what the plan records — a **collection** error, not a test failure:

```
$ ./.venv/bin/python -m pytest tests/compiler/test_stack_composition.py
collected 0 items / 1 error
ERROR collecting tests/compiler/test_stack_composition.py
tests/compiler/test_stack_composition.py:5: in <module>
    from ced.agents.compiler import compile_role
E   ModuleNotFoundError: No module named 'ced.agents.compiler'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 1.03s ===============================
EXIT=2
```

**Order matters and is recorded as such: byte identity was verified, then the
red was observed, and only afterwards was the file formatted.** `ruff format`
rewrote the inline role literal across seven lines, so the materialized copy
no longer matches the plan text. That is expected — the plan block is the
starting point, and `ruff format --check .` reds on the block inside `plan.md`
itself, which is a backlog item awaiting an owner decision and is why the
stub could not be formatted first.

**Superseded on 2026-09-21, after this observation was recorded.** The
observation above stands as the record of what happened at T2 layer (d) and is
not rewritten. What no longer holds is its closing rationale: the plan block's
format failure was a backlog item awaiting an owner decision *then*, and the
owner authorized the amendment that closed it — see
[`amendment-2026-09-21-stub-formatting.md`](amendment-2026-09-21-stub-formatting.md).
The plan's stub is now byte-identical to the materialized copy, so the two
sentences above describe an interval that has ended rather than a standing
state.

### Gates

```
$ ./.venv/bin/ruff format --check .        exit 1 — plan.md:250 only, the pinned
                                           stub block; pre-existing, in the backlog
$ ./.venv/bin/ruff check .                 exit 0
$ ./.venv/bin/mypy                         exit 0 — no issues in 23 source files
$ ./.venv/bin/python -m pytest -m 'not substrate'
                                           exit 1 — 1 failed, 148 passed in 9.48s
$ ./.venv/bin/python -m pytest             exit 1 — 1 failed, 319 passed in 166.74s
$ python3 tools/lint-no-identifiers.py --staged   exit 0
$ python3 tools/hooks/pre-pr.py                   exit 0
```

Offline moved 131 → 148 and the full run 302 → 319, both +17. The single
failure in each is the pre-existing `.github` layout case.
`tests/architecture/test_dependency_direction.py` is green in both runs, which
is what holds the `Never do` the `model_factory` seam bends around:
`pydantic_ai.models.Model` is named in `ced.agents.models` and nowhere else,
and `PoolConfig.model_factory` is typed by `ModelFactory`, a `Protocol`
declared in `worker/` whose `__call__` returns `object`.

### Framework facts verified against the installed 2.45.0

Each was run, not inferred, and each is load-bearing for a criterion:

* `Agent.__init__` has **no** `usage_limits` parameter and no `output_retries`
  one. `model` is `Model | KnownModelName | str | None = None`, so `Agent()`
  constructs with no model, and `retries` is `int | AgentRetries | None`. This
  is why `CompiledRole` carries `.limits` and why a pool with no factory still
  compiles.
* A compiled agent's retry budgets are readable only as `Agent._max_tool_retries`
  and `Agent._max_output_retries` — `0`/`0` under `retries={"tools": 0,
  "output": 0}` and `1`/`1` under the default. There is no public reader on
  2.45.0. AC-0205's first half reads those two names; its second half is
  behavioural and depends on neither.
* A malformed structured output under zero output retries raises
  `UnexpectedModelBehavior("Exceeded maximum output retries (0)")` after
  **one** model request; under the framework default it raises after **two**.
  The contrast is what makes the quarantined role's single turn a measurement.
* A refusal raised inside a wrapper toolset's `call_tool` propagates out of
  `Agent.run` unchanged, with the request count at one — the framework catches
  `ModelRetry` and nothing else.
* `_AgentFunctionToolset` is a `FunctionToolset` subclass carrying a `.tools`
  dict, which is the surface AC-0201's decorator case is decided on.
* `FunctionToolset.add_function(func, name=...)` registers one module-level
  callable under any tool name, so the compiler needs no closure per tool —
  the closure the § Grounding probe hit trips context-parameter inference.

### Interval states this layer ships, and why each is a value rather than a lie

* **`StepEventToolset` now takes one `StepContext | None`** instead of six
  separate fields. The compiler builds the layer with `None`, because the
  stack's order is fixed and a missing layer is a different agent, and the
  step path that supplies a connection and a fenced identity is
  `walking-skeleton-step-lifecycle`'s. Six independently-optional fields would
  have made "unbound" a combination rather than a value; the alternative —
  passing a fabricated run id and a `cast(Any, None)` connection from
  production code — would have put a lie where an operator reads one. An
  unbound layer raises if a call ever reaches it, which is reachable only if
  the decision point above it admits, and nothing admits.
* **`compiler.no_parser_installed`** stands where T3's deterministic parser
  will be wired and refuses whatever it is handed. `trust_class.py` says
  nothing there stubs a parser; that is still true of that module, and its
  docstring now records what the compiler wires in the meantime.
* **`compiler.unresolved_tool`** is the body every bound tool resolves to.
  Phase 1 reads no `adapter_ref`, so no tool resolves to a real adapter, and a
  body that raises is what keeps "no tool body executes" a property of the
  runtime rather than of what nobody happened to call.

### What layer (d) decides, and what it does not

Decided here: AC-0201 (both cases, against the constructed `Agent`), AC-0202's
first predicate (the materialized stub; the checker half stays layer (c)'s),
AC-0205, AC-0219 (both directions) and AC-0259. Left to layer (e): AC-0203,
AC-0204, AC-0206, AC-0246, AC-0251's compile half, AC-0258, AC-0260, AC-0267
and AC-0269. Where those guards are absent, a malformed record fails on the
framework's own error rather than on a named refusal — the compiler's module
docstring says so rather than leaving a reader to discover it.

### Statements found false while walking backwards

* `step_events.py`'s module docstring said the step context arrives "as
  constructor parameters"; it now arrives as one `StepContext`, and the
  docstring says what `None` means.
* `PoolConfig`'s docstring explained why `default_limits` and
  `allowed_model_ids` carry no dataclass default; `model_factory` does carry
  one, and the docstring now says why — it is wiring rather than a bound.
* `trust_class.py`, as above.

Reported and **not** edited, each outside this task's `Touches`:

* `role-configuration-seams.md`'s header — "**STATUS: PLANNED** — nothing here
  is built. `src/ced/agents/` is empty." That stopped being true at layer (c)
  and is further false now.
* `worker-runtime.md` § 8's implementation map — "Agent compiler, toolset
  stack, quarantined role | `src/ced/agents/` | … | Designed — the package is
  empty".
* `docs/architecture/README.md` § What is built names neither the toolset
  stack nor the compiler.
* `framework_contract.py`'s docstring calls `ced.agents.models` "the module
  that supplies the model factory". It *consumes* the factory; the pool
  supplies it. The ratified design's `PoolConfig` row words it the same way,
  so the wording is inherited rather than introduced here.

**Controller edit after layer (d) returned: `compile_role`'s fourth parameter
was removed.** The layer shipped `compile_role(role, integrations, pool, step)`
with `step: StepContext | None = None`, so the event layer could be bound once
a step path existed. No caller in this repository supplies it — the chain
builders construct `StepEventToolset` directly — so it was reach for a caller
that does not exist, which `AGENTS.md` § Cut before adding rung 1 refuses. The
ratified design and the approved stub both name the seam at three arguments.
The compiler now builds the event layer unbound, and the spec that builds the
step path adds the argument together with the criterion that reads it, the
same way this spec leaves the output-contract set's third member to the spec
that needs it. `StepContext` itself stays: it is what makes "unbound" one
value rather than a combination of six optional fields.

**Carried forward to the substrate layer, from layer (d)'s report.** AC-0233's
bullet says to drive a call through each pair "with a spy the tool body
increments". Every bound tool in this spec resolves to `unresolved_tool`, which
*raises* — Phase 1 reads no `adapter_ref`, so no tool resolves to a real
adapter. A spy that **replaces** the body satisfies the criterion; a spy that
wraps it does not, because the wrapped body raises before the counter moves.
Recorded before that layer starts rather than discovered inside it.

## T2e — the compile-time refusals over the role record

Layer (e) of T2: the nine guards AC-0203, AC-0204, AC-0206, AC-0246, AC-0251,
AC-0258, AC-0260, AC-0267 and AC-0269. Layer (f) — AC-0233 and AC-0261 — is
not in this layer.

### Where each guard landed

| Criterion | Guard | Decided by |
| --- | --- | --- |
| AC-0260 | `_bound_integrations`, unresolved pin and unlisted tool | `tests/compiler/test_binding_guards.py` |
| AC-0203 | `_bound_integrations`, `free-text` on a bound row | same file, parametrized |
| AC-0258 | `_bound_integrations`, `pool_classes` membership | same file, four cases |
| AC-0267 | membership in `OUTPUT_CONTRACTS`, before the lookup | `tests/compiler/test_declared_sets.py` |
| AC-0269 | `_check_settings`, `ADMITTED_SETTINGS` allowlist | same file |
| AC-0251 (compile half) | `ced.agents.models.resolve_model` | same file |
| AC-0204 | `_check_settings` plus `settings["thinking"] = False` | `tests/compiler/test_thinking_setting.py` |
| AC-0206 | `_resolved_limits` | `tests/compiler/test_limit_ceiling.py` |
| AC-0246 | no new code — the compiled `UsageLimits` carries the pool's flag | same file |

AC-0206's three clauses are three parametrized checks over `DECLARABLE_LIMITS`:
`…_wider_than_the_pool_default_fails_the_build` (clause 1),
`…_narrower_than_the_pool_default_compiles_to_its_own` (clause 2), and
`…_a_key_the_role_omits_inherits_the_pools_value` (clause 3, read off the
compiled `UsageLimits`). Two more cover the pool-owned flag and a limit
outside the declarable four.

### Framework facts established by running the installed package

* `pydantic_ai` 2.45.0. `ModelSettings` is a `total=False` TypedDict of
  **sixteen** keys, `extra_headers` and `extra_body` among them — the claim
  AC-0269 rests on, confirmed against the installed package and not taken
  from the brief.
* **`thinking` never reaches the model inside `ModelSettings` on this
  version.** `Model.prepare_request` resolves it into
  `ModelRequestParameters.thinking` and strips the key from the settings the
  model's `request` receives. It carries the value across when the profile
  declares `supports_thinking` **or** `thinking_always_enabled`, except that
  an explicit `False` is dropped on an always-thinking profile — a model that
  cannot stop reasoning gets no instruction to. AC-0204's original wording,
  "the settings a stub model receives carry `thinking` as `False`", was
  therefore not literally observable on 2.45.0; the criterion was reworded to
  the resolved request parameters on 2026-09-21 under the stub-formatting
  amendment. The hole it names is deferred as **one** Follow-on with a register
  entry, stated over the property that the value the model reads on the
  executor's run path is `False` rather than over any one profile flag: three
  mechanisms drop it downstream and an override defeats it upstream, and a
  guard scoped to any one leaves the rest open. The criterion's intent —
  the value at the model boundary, not on the carrier — is met by asserting
  `info.model_request_parameters.thinking is False` against a stub whose
  profile supports thinking.

  **Superseded on 2026-09-21.** This bullet used to close "Reported, not
  edited: the criterion's wording names a location the pinned version does not
  use." That was the pre-amendment status and is false of `spec.md` as it now
  reads; the owner directed the reword rather than the deferral, and it landed
  in this amendment. Retired here rather than deleted, because leaving a
  corrected claim beside its superseded one is the defect this amendment's own
  record names as dominant, and it recurred three times before this.
* `per_request_input_tokens_limit` is checked **twice** per turn:
  `_agent_graph._prepare_request` calls `check_per_request_input_tokens` on
  `count_tokens`' result before the request, and `_append_response` calls it
  again on the response's own usage. Only the first is pre-request. The
  admitted case in `test_limit_ceiling.py` therefore needs a ceiling clear of
  `FunctionModel`'s estimated usage as well as of the counted value; a first
  draft with a ceiling of 10 and a count of 5 failed on the second check at
  51 estimated input tokens, which is the observation behind
  `PER_REQUEST_CEILING = 500`.
* `Model.count_tokens` raises `NotImplementedError` with no override on
  `TestModel` or `FunctionModel` — re-confirmed here and pinned by
  `tests/contract/test_model_surface.py` (the brief cited
  `test_agent_surface.py`; the `count_tokens` assertions are in
  `test_model_surface.py`).

### The AC-0270 / AC-0246 tension, named rather than left for a reviewer

`test_limit_ceiling.py` sets `count_tokens_before_request` **true**, which
AC-0270 refuses. They do not conflict: AC-0270 governs the deployed
`CED_POOL_DEFAULT_LIMITS` through `verify_boot`, and this file passes a pool
mapping straight to `compile_role`, reaching no environment. The ratified
design § 7 names the counting stub as what sets the flag for this
demonstration. The file's module docstring says so, which is where a reader
meets it.

### Interpretation recorded: AC-0203's "every non-quarantined role"

The case set is derived from the compiler's own output-contract set —
`OUTPUT_CONTRACTS` minus `QUARANTINED_OUTPUT_CONTRACT` — rather than from a
list of role names written in the test. Today that is one class; a role class
added to the set is covered without the file changing. The skeleton carries no
second non-quarantined role to enumerate.

### `RoleCompileError` moved to `ced.agents.models`

The ratified design § 2 puts AC-0251's compile half in `ced.agents.models`,
"which is where AC-0251 is enforced". `ced.agents.compiler` imports that
module, so the module cannot import the compiler, and the shared refusal type
had to sit on the reachable side of that edge. `compiler` re-exports it and
keeps it in `__all__`, so every existing import still resolves and a caller
still catches one named type for every compile refusal. A third module holding
only the exception was declined: the design names two modules in `agents/` and
adding a third is a structural change no ratified document carries.

### Walking backwards — statements this layer made false, and what was done

* `compiler.py`'s module docstring, "**What this module does not yet
  enforce**", listing all of these guards as absent. Replaced with the list of
  guards and where AC-0251 lives instead.
* `_resolved_limits`' docstring, "the comparison … is not applied here yet, so
  today a wider value is simply carried". Rewritten around the three clauses.
* `compile_role`'s docstring, "`integrations` … with those not yet installed,
  the argument is carried and not inspected". Rewritten.
* `models.py`'s module docstring, "gives this module one job". It has two now,
  and the membership check runs first.

Nothing else in `src/` claimed a guard was missing; `grep` for "not yet",
"absent today" and "unguarded" over `src/ced` and `tests/compiler` returns
only statements that are still true.

### Test fixtures that changed, and why the existing suite moved with them

`a_planning_role()` binds `filing-archive` v1 and previously compiled against
`integrations=()`. Under AC-0260 that is now a refusal, so `role_records.py`
gains `an_integration()` — one pinned registry row in the shape `load_role`
returns, whose defaults resolve that ceiling entry — and the seven existing
call sites that compile a planning role pass it. `a_role` gains `pool_class`
and `model_id` parameters, which AC-0258 and AC-0251 vary.
`returns_an_empty_selection` and `CountsTokensModel` are new.

### Declined under `Cut before adding`

* A `free_text` denylist helper shared with `ced.adapters.postgres.roles`'s
  `TRUST_CLASSES` — rung 2, the search found the loader's allowlist and it is
  the loader's, reachable only by making `agents/` import `adapters/postgres`
  for one string literal.
* Importing `DEFAULT_LIMIT_KEYS` and `COUNT_TOKENS_KEY` from
  `ced.worker.pool` — rung 2 again, a hit that does not fit: `agents/` does
  not import `worker/`, which is the reason `compile_role` takes the pool as a
  plain mapping. The two names are written on both sides of that seam with a
  comment saying so.
* A `RoleCompileError` subclass per guard — rung 1. Every criterion says
  "fails to compile" and none reads a type; the message names the key, the
  value or the row, which is what an operator reads.
* A ceiling-entry shape check (`integration_name` present, `predicates` well
  formed) — rung 1 and out of scope: AC-0262 is the loader's and the predicate
  encoding belongs to `walking-skeleton-authority-containment`.

One addition *was* made beyond the criterion's literal words: a role
`model_settings.limits` key outside § 5's four is refused, not only
`count_tokens_before_request`. Without it `cost_limit`, `output_tokens_limit`
and `total_tokens_limit` — all three excluded by § 5, all three accepted by
`UsageLimits` — would reach the constructed limits unexamined, which is the
same failing-open shape AC-0269 closes for `settings`.

### Gates, run unfiltered from the worktree root

| Command | Exit | Result |
| --- | --- | --- |
| `ruff format --check .` | 0 | 146 files already formatted |
| `ruff check .` | 0 | All checks passed |
| `mypy` | 0 | no issues in 23 source files |
| `pytest -m 'not substrate'` | 1 | 187 passed, 1 failed, 171 deselected, 11.31 s |
| `pytest` | 1 | 358 passed, 1 failed, 179.26 s |

The single failure in both suites is
`tests/architecture/test_recorded_layout.py::test_no_top_level_directory_is_unrecorded`
on `.github`, pre-existing on `main` and in the backlog. The baseline handed to
this layer was 148 / 1 offline and 319 / 1 full; the 39 added tests account for
the difference exactly in both. `tests/architecture/test_dependency_direction.py`
is green in the same offline run, which is what T2's `Done when` names.

**`ruff format --check .` now exits 0.** The `plan.md:250` failure recorded as
this layer's second known-not-mine failure was closed while this layer ran, by
the stub-formatting amendment in
[`amendment-2026-09-21-stub-formatting.md`](amendment-2026-09-21-stub-formatting.md).

### Observed and not touched

`plan.md` and `spec.md` were modified in this worktree **during** this layer,
by that amendment — `plan.md` to `Status: Drafting`, `spec.md` to
`Status: Draft`, with the amendment's changelog entry added. Both files are
hash-pinned and this layer edited neither; the modification is recorded here so
a later reader does not attribute it to the implementation commit.

## Amendment rounds 9 to 11 — a procedural slip, recorded

The pre-EXECUTE loop for the stub-formatting amendment ran three review rounds.
Rounds 9 and 10 were adversarial; round 11 was the security lens, fired because
the owner widened the amendment to reword AC-0204, a guarding control. The
earlier not-warranted judgement was not carried forward, because the diff that
justified it no longer described the change.

**On round 11 the controller revised the spec before firing `findings-remain`.**
The skill's order is: adjudication sustains findings, fire `findings-remain`
(`SPEC-PLAN-REVIEW` → `SPEC-PLAN-DRAFTING`), revise from sustained findings
only, then fire `spec-ready`. The edits were made while the engine still read
`SPEC-PLAN-REVIEW`, and the transition was fired afterwards. The end state is
the same and the artifacts are all persisted and classified, so nothing is lost
from the audit trail; what was lost is the ordering guarantee that a revision
cannot begin before the round that authorized it is closed. Recorded rather
than quietly corrected, because a state machine that is obeyed only when
convenient records less than it appears to.

**Where a framework error entered and how far it travelled.** Round 10's
adjudication justified deferring the always-thinking hole partly on the claim
that the pinned Anthropic-on-Bedrock path writes `thinking: {type: disabled}`
for a `False` value. That was read from `models/bedrock.py`'s **non-adaptive**
branch alone. The adaptive branch has no `else`, so an explicit `False` emits
nothing and the provider default governs, and current Claude families take the
adaptive branch. The controller repeated the claim to the owner without
reading the surrounding construct. Round 11's security review caught it, and
the round-11 adjudication records the propagation path. The spec's own trap
list says never to assert a framework fact without reading it; the failure
here was subtler — reading one branch of a conditional and treating it as the
construct — and it is worth naming as its own trap.

## Round 12 — an indeterminate, surfaced and then directed past

The round-12 adversarial adjudication classified `invalid
(indeterminate-present)`. The indeterminate was Nit 5: whether the recorded
account of the round-11 ordering slip is complete. One fact it needed — when
the round-11 adjudication artifact was written to disk, relative to the
content edits — is not recoverable from any readable artifact, because
`.loop-run/events.jsonl` logs state transitions and not artifact writes.

**The controller did not resolve it itself, and the reason is worth stating.**
A file timestamp is one shell command away. The bounded evidence retry in
`finding-adjudication.md` § Bounded evidence retry admits only a gate from a
closed Evidence gate catalog that repository guidance or the approved plan
declared *before the reviewer report existed*, with a literal argument vector
and read-confined isolation. A grep of `AGENTS.md` and `plan.md` finds no such
catalog, so no entry was eligible and ad-hoc execution is precisely what the
rule excludes — otherwise the artifact under adjudication chooses what runs.
The nit's second half, whether a slip of this shape needs more than a ledger
note, is an owner decision the lifecycle reference does not settle.

It was surfaced to the owner with the two other open decisions, and the owner
directed continuation. The account above stands as recorded; the missing
timestamp is not added, because obtaining it would have meant waiving a
control rather than satisfying it.

## Closing the amendment's review loop

Five review rounds ran on this amendment across two lenses: 9 and 10
adversarial, 11 security, 12 both, 13 adversarial. The round-13 adjudication
sustained one finding — a clause in this amendment's own authority note whose
pointer resolved to a different owner question — and refuted the other
outright rather than deferring it, on the ground that the remaining objection
was a wording preference no authority decides and that "the next round can
raise the opposite preference with equal force".

That adjudication also answered the cost question directly: **nothing there
justified a sixth round**, because the sustained item was a text correction
with a determined outcome, no code, gate or contract surface behind it, and it
"can be verified by re-reading the two sentences it touches". The controller
applied the correction, re-read those sentences, and additionally found and
fixed a second copy of the same count claim earlier in the note — a walk the
refuted nit had noticed in passing and which refuting it did not perform.

**No reviewer confirmed that last correction, and the owner directed the build
to proceed.** That is recorded rather than smoothed over: the basis for
treating the pre-EXECUTE review as satisfied is the adjudicator's explicit
no-sixth-round finding plus the controller's own re-read, not a clean reviewer
report. Anyone auditing this run should read it that way.

**What the five rounds bought, stated once.** One inert control: AC-0204's
`thinking=False` does not reach the model on several paths, which no criterion
here could see. It is deferred as a property — that the value the model reads
on the executor's run path is `False` — rather than as a list of mechanisms,
because three downstream drops and one upstream override each defeat it. One
criterion was reworded to an observation point that exists on the pinned
version. Everything else the rounds found was this amendment's own record
keeping, most of it introduced by the controller's own fixes.
