# Verification ledger — walking-skeleton-step-lifecycle

Execution observations for this spec. The spec and plan are pinned; anything
learned while building goes here.

## Pre-EXECUTE measurements (2026-09-24)

Taken by the controller against the pinned `pydantic-ai` 2.45.0 in `.venv`
while the contract was under review. Each settled a claim the contract rests
on, and each is reproducible from this repository with no credential and no
network.

### The rendering the reasoning-disable seam reads

`prepare_request(ModelSettings(thinking=False), ModelRequestParameters())`
followed by the adapter's own additional-fields build:

| model id | `bedrock_thinking_variant` | adaptive | rendered fields |
| --- | --- | --- | --- |
| `claude-sonnet-4-5` (bare family name) | `None` | `None` | `None` |
| `anthropic.claude-sonnet-4-5-v1:0` | `anthropic` | `False` | `{'thinking': {'type': 'disabled'}}` |
| `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | `anthropic` | `False` | `{'thinking': {'type': 'disabled'}}` |
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `anthropic` | `False` | `{'thinking': {'type': 'disabled'}}` |
| `us.anthropic.claude-sonnet-5` | `anthropic` | `True` | `None` |
| `us.anthropic.claude-opus-4-7` | `anthropic` | `True` | `None` |
| `us.anthropic.claude-opus-4-8` | `anthropic` | `True` | `None` |
| `amazon.nova-pro-v1:0` | `None` | `None` | `None` |

**A bare family name renders exactly what an adaptive model renders.** That is
why T6's real-adapter pair requires provider-prefixed ids: built from bare
names the admitted half would red through the no-profile refusal rather than
through the rendering it exists to calibrate.

`BedrockConverseModel` constructs from a region name alone, with no
credentials and no network. Without a region it raises
`UserError: You must provide a 'region_name' or a boto3 client for Bedrock Runtime.`

### The adaptive prefix set

`profiles/anthropic.py` declares an eight-member prefix tuple and sets
`anthropic_supports_adaptive_thinking` from membership of it;
`providers/bedrock.py` reads that flag off the downstream profile and sets
`bedrock_supports_adaptive_thinking`, which is the flag the rendering branch
tests. The members are `claude-fable-5`, `claude-mythos-5`,
`claude-sonnet-4-6`, `claude-sonnet-5`, `claude-opus-4-6`, `claude-opus-4-7`,
`claude-opus-4-8` and `claude-opus-5`. Membership is by prefix, so
`claude-opus-5-5` is adaptive and `claude-haiku-5` is not.

### Usage limits reach no model-side seam

`Model.request` and `Model.count_tokens` take only
`(messages, model_settings, model_request_parameters)`.
`ModelRequestParameters` carries no limits field, and neither does
`ModelRequestContext`. `RunContext.usage_limits` is the only exposure, and it
is **the identical object** the caller passes to `Agent.run` — measured
`is` → `True` from a tool inside a compiled stack.

That is why AC-0263's identity half must be driven through the production step
path: read from a run the test itself started, the assertion is a tautology.

## T6 mutation proof (2026-09-24)

The guard is `_check_reasoning_disable` in `src/ced/agents/compiler.py`, called
from `compile_role` over the answer `ced.adapters.reasoning_disable` gives for
the model the compiled agent carries. Baseline before the change: 572 passed,
214 deselected. After it: **588 passed, 214 deselected in 13.97 s** under
`pytest -m 'not substrate'`.

Each mutation below was applied alone and reverted before the next. Every red
is quoted by the reason `pytest` reported, because a red on a missing fixture
or an import error proves nothing about the guard — the shape that shipped
green twice in this task's own stubs.

### M1 — the guard is not called at all

`compile_role` skips `_check_reasoning_disable`. **Five red, all with
`Failed: DID NOT RAISE ThinkingDisableUnreachable`**, which is the guard's own
reason and not a collection or fixture fault:

| check | what it would have refused |
| --- | --- |
| `test_a_model_whose_request_carries_no_disable_is_refused_naming_the_id` | a real adaptive Bedrock model |
| `test_a_model_id_resolving_to_no_profile_is_refused` | a bare family name |
| `test_an_in_process_double_is_refused_when_nothing_declares_it` | an undeclared `FunctionModel` |
| `test_the_declaration_is_what_admits_a_non_provider_model` | its second half, the undeclared compile |
| `test_a_declared_id_resolving_to_a_provider_backed_model_is_refused` | a declared id wired to a real adapter |

**Green and correctly so:** the two admitted compiles
(`test_a_model_whose_request_carries_a_disable_compiles`,
`test_a_pool_that_wired_no_adapter_compiles`), the deployment pair in
`test_the_deployment_declares_its_stub.py`, the seam-level
`test_reasoning_enabled_is_not_read_as_a_disable`, and the six
`verify_boot` checks. None of those asserts a compile refusal, and the last
seven reach a different unit entirely.

### M2 — the seam answers `CARRIED` for every model

**24 red.** Four of this task's own — the three refusal compiles above plus
`test_reasoning_enabled_is_not_read_as_a_disable`, which is the only check
that catches this mutation at the seam rather than through a compile — and
**20 pre-existing compiler and quarantine checks**, which red because a
declared `stub:counting` answering `CARRIED` is read as a provider-backed
misdeclaration and refused. That blast radius is the intended one: an
always-`CARRIED` seam cannot pass this repository's suite.

### M3 — an uninterrogable class is admitted (the fail-open the carve-out replaced)

Undeclared `UNINTERROGABLE` returns instead of raising. **Two red**, both
`DID NOT RAISE ThinkingDisableUnreachable`:
`test_an_in_process_double_is_refused_when_nothing_declares_it` and the
second half of `test_the_declaration_is_what_admits_a_non_provider_model`.
Everything else stays green, which is what makes the declaration's
discrimination check the one that carries this clause.

### M4 — the declaration parser answers `()` on a decode error

`_parse_non_provider_model_ids` swallows every parse failure. **Five red**, the
whole `test_a_malformed_non_provider_declaration_fails_boot_naming_it`
parametrisation. The reported reason is the `no_database` fixture's
`AssertionError: verify_boot opened a connection before validating`, not a
missing-fixture error: with nothing refused, `verify_boot` runs on to its two
connections, so the fixture firing *is* the observation that validation
admitted a value it must refuse. This is the check that would otherwise boot
every worker green on the unquoted-array hand edit `[stub:counting]`.

### M5 — the seam re-raises instead of failing closed

The `except` in `reasoning_disable_of` re-raises. **One red**,
`test_a_resolution_that_raises_answers_no_disable`, reported as the
`RuntimeError` the stand-in adapter raises escaping the seam — so the check
observes the fail-closed branch and not merely the answer. Final state after
every mutation was reverted: **589 passed, 214 deselected**.

## T6 review round 1 — the interrogability predicate was wrong (2026-09-24)

Three reviewers reached the same root cause by three routes, and the
controller reproduced each witness before acting on it.

### The defect

`reasoning_disable_of` decided interrogability with
`isinstance(model, BedrockConverseModel)` and answered `UNINTERROGABLE` for
everything else; the compiler admitted that answer whenever the id was
declared non-provider-backed. So the predicate was asked "is this
provider-backed?" and could only answer "is this exactly one class?".

Reproduced through the public seam:

```
inner   = BedrockConverseModel("us.anthropic.claude-sonnet-5", ...)   -> NOT_CARRIED
wrapped = InstrumentedModel(inner)                                    -> UNINTERROGABLE
compile_role(..., declared=("stub:counting",), factory -> wrapped)    -> ADMITTED
```

`deploy/compose.yaml` ships that declaration on both workers today, so the
moment a `model_factory` returned an instrumented model — the ordinary shape
once the observability companion lands — reasoning would have reached the
provider with AC-0275 recorded green. An adversarial reviewer independently
found the same hole via a second provider's adapter, which is what showed the
defect was the class-level predicate rather than the wrapper case.

### The repair

The seam now unwraps `WrapperModel` chains, then **positively identifies** an
in-process double (`FunctionModel`, `TestModel`) as the only answer the
declaration may admit. Anything it can neither render nor prove local —
another provider's adapter, or a double the framework adds later — falls to
`NOT_CARRIED` and is refused. The enum member is renamed
`NOT_PROVIDER_BACKED`, which is the property the criterion actually turns on.

| configuration | seam | compile |
| --- | --- | --- |
| declared + `WrapperModel(adaptive Bedrock)` | `NOT_CARRIED` | refused |
| declared + `WrapperModel(disabling Bedrock)` | `CARRIED` | refused |
| declared + another provider's adapter | `NOT_CARRIED` | refused |
| declared + `FunctionModel` | `NOT_PROVIDER_BACKED` | admitted |

### Mutation proof for the repair

Each mutation applied alone and reverted; the suite is 594 green unmutated.

| # | mutation | result |
| --- | --- | --- |
| renderer-alone | discard `prepare_request`'s parameters, hand the renderer a value built from the settings | **red** — `test_the_answer_comes_from_the_models_own_resolution_not_the_rendering_rule` |
| M6 | remove the `WrapperModel` unwrap | **red** — `test_a_wrapped_model_is_classified_by_what_it_wraps` |
| M7 | restore the old `not isinstance(..., BedrockConverseModel)` predicate | **red** — `test_a_declared_id_on_an_unknown_providers_adapter_is_refused` |
| M8 | remove the empty-value branch and its advice | **red** — `test_an_empty_non_provider_declaration_says_to_unset_it` |

**Two dead checks were caught during this round and are recorded because the
shape matters more than the instances.**

The renderer-alone mutant — the exact restatement AC-0275 forbids — left the
**whole suite green at 589** before this round. Every fixture sat on a profile
where the correct and forbidden implementations agree. It is now pinned by a
Bedrock adapter on a `thinking_always_enabled=True` profile, where
`prepare_request` discards the explicit `False` and the two answers diverge.
The plan anticipated this ("green today only because no Bedrock Anthropic
profile sets `thinking_always_enabled` on this pin — a property of the pin,
not of the guard"); nothing had closed it.

The first wrapper check written for the repair **also could not fail.** It
asserted that a wrapper around an adaptive model is refused — true with or
without the unwrap, since an un-unwrapped wrapper matches neither branch and
falls to the refusal anyway. M6 stayed green against it.

**This paragraph previously claimed that check had been replaced. It had not,
and the correction is kept rather than quietly fixed.** A second check wrapping
a *disabling* model was added — the unwrap is observable only where it admits —
but the dead one was left on disk, so the ledger asserted a repair the tree had
not received. Round 2's adversarial review audited all thirteen new checks for
an isolating mutation, found this the only one without, and caught the false
record alongside it. The dead check is now removed as subsumed by
`test_a_wrapped_model_is_classified_by_what_it_wraps` and
`test_a_declared_id_resolving_to_a_provider_backed_model_is_refused`.

### Findings refuted rather than applied

Four of the ten review findings were refuted on adjudication, and acting on
them would have been wrong: the `a_pool()` default cannot mask a check because
`a_pool_resolving_to` makes `declared` a required keyword-only argument; the
probe's synthetic `ModelRequestParameters` violate no clause, since AC-0275
fixes the probe's *settings*; the missing refusal-reason record is already an
accepted open register entry deferred to the spec that opens the payload-object
write path; and the settings aliasing has no consequence on the pin.

### Carried to the pull request, not fixed here

`src/ced/adapters/reasoning_disable.py` now logs the swallowed probe exception,
so a signature drift on the private build is visible rather than silent. What
is **not** done is making the refusal itself distinguishable from a genuine
"this model would reason" answer: that widens the enum and adds a compiler
branch, changing observable behaviour across two modules, so it was left as a
deferred finding rather than taken without a scope decision.


## T6 review round 2 — what the repair itself got wrong (2026-09-24)

Reviewing the repair found six more defects. Four were checks that could not
fail, which is the same class the repair was written to close.

### The offline gate was not offline

`tests/thinking_reaches_the_model/adapters.py` claimed the Bedrock adapter is
built with "no credential, no network". The credential half was true; **the
network half was false.** Constructing the adapter makes boto3 walk the AWS
credential chain, which attempts outbound connections to the EC2 instance
metadata address `169.254.169.254` — measured on this machine at 2 connects
and 2.2 s, and reported by the reviewer at 18 connects and 24.8 s on a
different configuration. On a cloud runner that silently pulls instance-role
credentials into a suite asserted to need none; on a network that blackholes
the address it hangs the gate.

Fixed by supplying explicit placeholder credentials to `BedrockProvider`, which
short-circuits the chain. Measured after: **0 connect attempts across the whole
`tests/thinking_reaches_the_model` suite**, 0.5 s per construct. The docstring
now states what the suite actually does.

### Four things the suite did not pin

Each was proved unpinned by deleting it and observing the suite stay green, and
each now reds on a named check.

| deleted | was | now reds |
| --- | --- | --- |
| `TestModel` from the admitted set | green | `test_each_in_process_double_is_admitted_by_the_declaration` |
| the undeclared-double refusal branch | green | `test_an_undeclared_double_is_refused_for_the_missing_declaration` |
| the probe-failure `log.warning` | green | `test_a_failed_probe_is_recorded_for_the_operator` |
| the wrapper-depth exhaustion branch | untested | `test_a_wrapper_chain_deeper_than_the_bound_is_refused` |

The third matters beyond its size: the decision to defer making a probe failure
*distinguishable* from a model that would reason rested on that log line being
there, and the line was free to be removed without notice.

### Two claims about the framework that were wrong

`FallbackModel` is **not** a `WrapperModel` on the pin — it holds a `models`
list, not a `wrapped` attribute — so the unwrap never descends a fallback chain.
Two docstrings asserted the opposite. The direction is safe, since such a model
falls through to refusal, but the consequence is real and is now recorded as a
residual in the criterion: a legitimate fallback configuration cannot compile
until the seam learns to read one.

The seam's module docstring still described the `UNINTERROGABLE` rule the repair
had removed, two screens above the class docstring stating the opposite. A
future edit could have restored the documented rule over the implemented one.

### The contract was amended

The repair inverted a sentence of AC-0275: the criterion admitted a declared id
wired to a class the seam cannot interrogate, and the repaired seam refuses it.
The code is right and the contract described the vulnerable behaviour, so under
`AGENTS.md` § Coding conventions the conflict was surfaced rather than resolved
silently, and the owner authorised a controlled amendment on 2026-09-24. The
old wording is quoted inside the criterion rather than deleted.

## T6 — the full mutation audit (2026-09-24)

Round 3's three reviewers all terminated on an infrastructure spend limit
before writing anything, so the audit they were asked for was run directly
instead. Fifteen mutations were applied one at a time, each reverted, and the
whole offline suite run against each. The question for every check T6 adds is
the only one that matters: **does some mutation red it for its own reason?**

**Result: 19 of 19 checks have an isolating mutation.** The table below names
one per check; several have more.

| check | reds under |
| --- | --- |
| `..._carries_a_disable_compiles` | seam pinned to NOT_CARRIED |
| `..._carries_no_disable_is_refused_naming_the_id` | guard never called |
| `..._resolving_to_no_profile_is_refused` | guard never called |
| `test_reasoning_enabled_is_not_read_as_a_disable` | seam pinned to CARRIED |
| `..._resolution_that_raises_answers_no_disable` | seam pinned to CARRIED |
| `..._in_process_double_is_refused_when_nothing_declares_it` | guard never called |
| `..._declaration_is_what_admits_a_non_provider_model` | guard never called |
| `..._declared_id_resolving_to_a_provider_backed_model_is_refused` | guard never called |
| `..._pool_that_wired_no_adapter_compiles` | no-adapter path inverted |
| `..._declared_id_on_an_unknown_providers_adapter_is_refused` | guard never called |
| `..._comes_from_the_models_own_resolution_not_the_rendering_rule` | renderer-alone restatement |
| `..._wrapped_model_is_classified_by_what_it_wraps` | unwrap removed |
| `..._each_in_process_double_is_admitted_by_the_declaration` | `TestModel` dropped |
| `..._undeclared_double_is_refused_for_the_missing_declaration` | refusal branch deleted |
| `..._failed_probe_is_recorded_for_the_operator` | probe log deleted |
| `..._wrapper_chain_deeper_than_the_bound_is_refused` | bound widened |
| `..._malformed_non_provider_declaration_fails_boot_naming_it` | parser made lenient |
| `..._empty_non_provider_declaration_says_to_unset_it` | empty-value branch removed |
| `..._unset_non_provider_declaration_declares_no_id` | unset made a refusal |

### The audit found one more check that could not fail, and it was mine

`test_a_wrapper_chain_deeper_than_the_bound_is_refused` built its chain as
`MAX_WRAPPER_DEPTH + 1` — deriving the length from the constant under test.
Widening the bound from 16 to 10,000 therefore widened the chain too, and the
check passed unchanged: **the only mutation in the sweep that survived.** The
chain is now a literal, so raising the bound past it lets the seam read the
chain to the end, answer `CARRIED` for the disabling model inside, and red the
check. Re-running the same mutation now reds exactly that check and nothing
else.

That is the third check-that-cannot-fail found in this task, across three
rounds, and the second written by the repair rather than the original build. A
check reading the constant it tests is the same failure as a check asserting an
outcome that holds either way: both look like coverage and neither is.

### Two checks the sweep could not judge, and why that was the sweep's fault

`..._malformed_non_provider_declaration_fails_boot_naming_it` and
`..._unset_non_provider_declaration_declares_no_id` appeared unpinned because
the sweep mutated the seam, the compiler guard and one pool branch, and never
made the declaration parser lenient or made an unset variable raise. Both
mutations were then run directly and both checks red. Recorded because "no
mutation reds it" is only evidence when the mutation set can reach the code:
an incomplete sweep reports a live check as dead.

## T1 — the first live provider call (2026-09-24)

A step compiled a quarantined role, called Bedrock under a scoped assumed
role, and reached `step.completed`. Model
`us.anthropic.claude-haiku-4-5-20251001-v1:0`, chosen because it is
non-adaptive on the pin: T6's compile guard admits it and the disable reaches
the wire. Spend was around $0.001, against the spec's $5 ask-first boundary.

Evidence read back from the event log rather than from setup:
`inference_profile` and `framework_version = 2.45.0` in the producer tuple,
`model_adapter = BedrockConverseModel`, `fetch_adapter = BedrockProvider`, and
a 64-hex `tool_manifest_hash`.

### AC-0224 was delivered as a check that observed its own setup

It read `os.environ["AWS_ACCESS_KEY_ID"]` in the pytest process and asserted
the `ASIA` prefix — a value the fixture in the same file had just placed
there. It would have held whatever the deployable actually shipped. The
criterion names the **running worker container**, and the plan says the
compose file is the intent while the container is the fact.

It now execs into `worker-a` and scans the environment plus every credentials
file a default AWS chain reads. Mutation-proved: planting
`AWS_ACCESS_KEY_ID=AKIA…` on the container reds it, reverting passes. The
measured fact is stronger than the criterion needs — the deployable carries no
`AWS_*` variable and no credentials file at all.

Two limits are stated in the check rather than implied: a local container scan
cannot show the deployed-fleet property, and scanning a *running* filesystem
cannot decide "baked into the image" when a secret may sit in a discarded
layer. Both were already recorded in § Follow-ons.

### The trust policy was refreshed only at creation

`create_role` is a no-op once the role exists, so each run rewrote the role's
**permissions** while the predicate deciding **who may assume it** stayed
whatever the first run wrote. A role pre-created in a shared account with a
wider principal condition would have kept that trust indefinitely with nothing
reporting it. `update_assume_role_policy` now runs unconditionally beside
`put_role_policy`.

### The endpoint guard's first version did not address its own finding

`CED_OBJECT_STORE_ENDPOINT` was unvalidated, so a mistyped or hostile value
would direct every payload write wherever it pointed. The first guard checked
only the scheme — and `http://169.254.169.254/` is a well-formed http URL with
a host, so it was admitted and boto3 tried to connect. That was caught only
because the verification command hung.

The guard now refuses the link-local range specifically, which covers both the
instance-metadata address and the ECS task-metadata address at
`169.254.170.2`. Loopback and ordinary private addresses stay admitted on
purpose: MinIO is served on one, and refusing them would refuse the deployment
rather than the hazard. Removing the link-local branch reds the two checks that
name it.

### boto3 was an undeclared direct dependency

`ced.adapters.bedrock.payload` imports `boto3`, which reached the environment
only as a transitive of the `[bedrock]` extra. `AGENTS.md` § Coding conventions
counts an import missing from the owning manifest as a new dependency **even
when it resolves locally**, and T1's plan states "No new package dependency".
It is now declared. No package is added by the line: the version stays with the
extra rather than being pinned twice in disagreement.

### Why the payload writer lives under `adapters/bedrock/`

It is an object-store concern and belongs in `adapters/objectstore/`, which is
**T3's** `Touches` and not T1's. The event schema accepts only a
`payload_ref`, never an inline value, so recording the producer tuple required
writing an object; T1's pinned `Touches` admits `src/**/adapters/bedrock/**`
and nothing else that could hold it. T3 owns the permanent adapter and
AC-0231's scope-qualified keys, and should relocate this module rather than
duplicate it.

## T2 — step suspension and deadline (2026-09-25)

### AC-0232: CancellationToken fires within deadline

**Test:** `tests/suspension/test_step_deadline.py::test_a_hung_run_is_cancelled_within_the_deadline`

Mutation proof — three mutations and their verdicts:

1. **Remove `cancellation_token=token` from `_run_compiled_agent`'s `run_sync` call.**
   Without the token the run is never registered for cancellation. The timer fires but
   nothing cancels the asyncio task. The test hangs beyond `3 × DEADLINE`.
   Verdict: **reds the test** (confirmed: test hangs without the argument).

2. **Replace `await asyncio.sleep(1000)` with `return ModelResponse(...)` immediately.**
   The model returns immediately; the `CancellationToken` fires but the run is already
   done. `RunCancelled` is never raised. The test fails with `Failed: DID NOT RAISE`.
   Verdict: **reds the test**.

3. **Set `_DEADLINE = 100.0`.**
   The timer fires after 100 s. The elapsed assertion `< 300 s` still passes (the
   model's `asyncio.sleep(1000)` is still cancelled promptly), but the test takes
   over 100 s — any CI wall-clock budget rejects it.
   Verdict: **not a cancellation regression** but confirms the timer controls elapsed.

**Why async model function is required.** `pydantic_ai._utils.run_in_executor` calls
`anyio.to_thread.run_sync(func, abandon_on_cancel=_abandon_on_cancel.get())`. Outside
the `abandon_threads_on_cancel()` context manager `_abandon_on_cancel.get()` is `False`,
so anyio shields the await: the `CancelledError` is only delivered after the thread
returns. A sync `time.sleep(1000)` therefore blocks for 1000 s after the token fires.
An async function is detected by `_utils.is_async_callable` (line 167 of `function.py`)
and awaited directly — no thread — so `asyncio.sleep(1000)` is cancelled immediately
when the driving asyncio task is cancelled. Reproduced by switching to sync sleep:
test hangs indefinitely.

### AC-0237: suspended step releases lease

**Test:** `tests/suspension/test_step_suspends.py::test_a_step_suspends_releases_its_lease_and_is_claimable` (substrate)

Mutation proof — three mutations:

1. **Remove the `UPDATE steps SET … owner = NULL` block from the suspension path.**
   The lease is never cleared. Assertion 2 (`owner = NULL`) fails. Assertion 3
   (`claim_one` returns non-None) also fails because the row stays in `state='leased'`.
   Verdict: **reds assertions 2 and 3**.

2. **Change `isinstance(result.output, DeferredToolRequests)` to `False` (never suspend).**
   The executor takes the normal return path. No `step.suspended` event is written.
   Assertion 1 (`len(suspended) == 1`) fails.
   Verdict: **reds assertion 1**.

3. **Write the `step.suspended` event after clearing the lease (reverse code order).**
   **Reds, and this entry previously said it did not.** The implementer recorded
   the ordering as a documentation claim that no test predicate asserts; the
   controller ran the mutation on 2026-09-25 and the test failed — so the
   correction is kept rather than quietly replaced, because "not pinned" is the
   claim that stops the next reader looking.

   The mutation reds for exactly the criterion's own reason, and the fence is
   what does it rather than an assertion: with `owner` already cleared, the
   fenced append refuses and raises `Fenced`. That is AC-0237's clause "without
   the release making that append unfenced", enforced by the database rather
   than asserted by the suite. Both statements share one transaction, so the
   ordering is invisible to an outside reader after the commit — which is why
   reading final state proves nothing and why the mutation, not the assertion,
   is the evidence here.

### AC-0263: usage limits identity and enforcement

**Tests:** `tests/usage_limits/test_usage_limits_in_force.py`

**Identity mutation:** Replace `usage_limits=compiled.limits` in `_run_compiled_agent`
with `usage_limits=UsageLimits()` (a fresh object). The `ctx.usage_limits is compiled.limits`
assertion fails with `AssertionError`. Verdict: **reds the identity check**.

**Enforcement mutation:** Remove `usage_limits=compiled.limits` argument from `run_sync`
entirely. The framework enforces no limits; a `request_limit=0` pool runs without
raising `UsageLimitExceeded`. Verdict: **reds the enforcement check**.

**Why `request_limit=0` and not `tool_calls_limit=0`.** `requires_approval=True` tools
are intercepted by pydantic_ai before the tool-calls counter increments. Setting
`tool_calls_limit=0` returns `DeferredToolRequests` instead of raising
`UsageLimitExceeded` because the deferred intercept fires before the counter check.
`request_limit=0` fires before the first model request and is not bypassed by the
deferred mechanism. Confirmed by switching to `tool_calls_limit=0`: test fails with
`Failed: DID NOT RAISE <class '...UsageLimitExceeded'>`.

### T2 mutations re-run by the controller (2026-09-25)

Every T2 check was re-checked against a mutation rather than taken from the
implementer's report. Two results differ from what that report claimed.

| mutation | result |
| --- | --- |
| release the lease before the fenced append | **reds** `test_a_step_suspends_releases_its_lease_and_is_claimable` with `Fenced` — recorded above as unpinned, which was wrong |
| executor threads a different `UsageLimits` object | **reds both** `test_usage_limits_identity` and `test_usage_limits_are_enforced` |

The second is the one AC-0263 was restated to make possible. The identity check
calls `_run_compiled_agent`, the executor's own function, so the executor
supplies the limits and the test only observes; had the test called
`agent.run_sync` itself it would have asserted its own argument, since
`RunContext.usage_limits` is the identical object the caller passes. That is
the tautology the criterion's 2026-09-24 restatement exists to prevent, and it
is avoided.
