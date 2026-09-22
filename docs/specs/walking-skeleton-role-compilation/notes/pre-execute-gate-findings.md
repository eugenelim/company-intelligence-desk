# Pre-EXECUTE gate, 2026-09-20 — what eight review rounds established

The spec and plan entered the pre-EXECUTE gate Approved. Eight adversarial
rounds plus a spec-stage secure-design pass did not converge: findings ran
26 → 18 → 12 → 11 → 20 → 9 → 11 → 13, and the two spikes each followed an
amendment written to fix the round before it.

The owner stopped the gate on 2026-09-20 and ruled for a design pass before any
further spec work. This note is the input to that pass. The rejected amendment
is beside it as `rejected-amendment-2026-09-20.patch`; the raw reviewer reports
and the framework evidence are in the session's review directory, which is not
committed.

## Why it did not converge

Every round's blockers reduced to one condition: **criteria written against
infrastructure that does not exist.** Closing a finding meant inventing the
missing design — a migration, columns, registries, environment variables, a
seed fixture — and each invention was unreviewed design that produced the next
round's findings. That is subsystem design conducted through an adversarial
reviewer one finding at a time.

The gaps are listed below so the design pass can settle them together rather
than one at a time.

## What the design pass has to settle

**Role configuration storage.** `agent_role` ships `role_name`, `version`,
`ceiling`, `pool_class`, `instructions`, `created_at` (migration 0001) and
`owner_scope` (0002). Five compile-time guards read attributes none of those
carry: a model id (AC-0251), model settings (AC-0204), a declared usage limit
(AC-0206), an integration binding (AC-0203) and a trust class (AC-0219). r5
§ "Two kinds of configuration" puts them on the role record. A role→integration
binding is a many-relationship and cannot be a column. Any new table needs an
explicit `GRANT SELECT … TO app_api, app_worker`; migration 0001 grants per
table, and a schema check run as the migration owner passes while the worker
fails. `ALTER TABLE … ADD COLUMN … NOT NULL` without a default errors on a
non-empty table, which is why 0002's `owner_scope` widening carried
`DEFAULT 'default'`.

**Pool configuration.** `PoolConfig.from_environment` reads `CED_WORKER_ID` and
`CED_POOL_CLASS` only. AC-0206 compares a role limit against a pool default and
AC-0251 a model id against a pool allowed set; neither exists. Adding required
environment variables reaches further than it looks: `deploy/compose.yaml` sets
four `CED_` variables, `restart: "no"` keeps a failed worker dead, and
`tests/fault_injection` fails its two-worker precondition — plus four
`PoolConfig(...)` constructions in `tests/worker/test_pool_paths.py` and the
worker invocation documented in `AGENTS.md`.

**Where the compiler's inputs come from.** `compile_role` needs a role record,
its resolved integrations, a base `Model` for the role's model id, and a
declared output type. None of those resolution paths is designed. Two
constraints shape it: a criterion must be decidable without a running step, and
a production contract must not be widened to make a test possible, so injection
seams have to be the ones production uses.

**Which criteria need a running step.** AC-0222, AC-0242, AC-0255 and AC-0256
cannot be observed without a step path and a context assembler, which
`walking-skeleton-step-lifecycle` builds. The gate moved them there under
`docs/specs/README.md` § Cutting one outcome into several specs; the design pass
should confirm that placement rather than inherit it.

## Framework facts established, all verified against the pinned 2.45.0

These were each established by running code, and several contradicted what the
spec or plan asserted. They belong in § Grounding probe whatever shape the spec
takes.

- `Agent.__init__` has no `usage_limits`. It is a per-call argument to
  `Agent.run`, so a compiler cannot bind it to an agent; something on the run
  path has to carry the resolved limits.
- `Agent.toolset` is a **registration decorator**, not an attribute.
  `Agent.toolsets` always carries the agent's own `_AgentFunctionToolset`
  alongside any passed toolset, and only the private `_user_toolsets` holds the
  passed list. A chain walk needs a root the project owns.
- `ModelSettings` is a fixed TypedDict of sixteen keys. `thinking` is one, which
  is what AC-0204 reads; `output_type` is not — it is an `Agent.__init__`
  parameter.
- `Model.count_tokens` raises `NotImplementedError` by default, and neither
  `TestModel` nor `FunctionModel` overrides it.
- `UsageLimits` carries `cost_limit`, `request_limit`, `tool_calls_limit`,
  `input_tokens_limit`, `output_tokens_limit`, `total_tokens_limit`,
  `per_request_input_tokens_limit` and `count_tokens_before_request`.
  `check_before_request` reaches its `cost_limit` arm only when `usage.cost` is
  non-`None`, which it is not for a test model — so a cost ceiling cannot be
  demonstrated under test. The **token** arm can: with a model implementing
  `count_tokens`, `UsageLimits(input_tokens_limit=10,
  count_tokens_before_request=True)` raises `UsageLimitExceeded` and the model's
  `request` is never called. That is the framework primitive to prefer over a
  bespoke wrapper.
- **But** `count_tokens_before_request` makes `BedrockConverseModel` issue a
  separate `bedrock:CountTokens` call against the geo-prefix-stripped model id.
  Spike 1 established those models are not invocable by raw model id, and the
  IAM shape is pinned as not re-derived, so enabling the flag reaches
  `walking-skeleton-step-lifecycle`'s only real provider call. The design pass
  owns that trade-off.
- `pydantic_ai.models.wrapper.WrapperModel` exists and `Model.request` receives
  the assembled message list, so a model-level seam is available if one is
  wanted for a different reason.

## Criterion defects the gate sustained, independent of the design gaps

- AC-0220's parser criterion governed integration output, while AC-0219 gives a
  quarantined role no integrations — so nothing put the parser on the
  quarantined agent's own output, and the prohibition lived only in § Boundaries
  prose. A criterion is needed.
- The input trust class is stated by r5 by **destination** — a planning role's
  context carries only references, labels and typed scalars, enforced by the
  substrate — while every criterion scoped it by **provenance**. A path not
  originating in a quarantined step was unconstrained.
- Neither AC-0233 nor AC-0234 asserted that a refusal propagates out of the
  agent run; a wrapper catching its own refusal and returning a tool-error
  string satisfied both.
- AC-0246's oracle went green on the `NotImplementedError` crash path and on the
  never-enforced path identically.
- AC-0233's enumeration reads registries that no production seed populates, so
  its universe is whatever a test fixture wrote.
- No task carried a TDD stub or a legal no-stub disposition, which the
  spec-and-plan contract requires; the compile-and-red step is what would have
  caught the two framework defects at PLAN.
