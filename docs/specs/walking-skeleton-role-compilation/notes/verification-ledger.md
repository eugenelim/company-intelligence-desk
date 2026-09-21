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
