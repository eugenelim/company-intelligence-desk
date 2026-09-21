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
