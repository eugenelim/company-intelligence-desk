"""AC-0206 and AC-0246 — what a role may ask of the pool's limits, and when.

AC-0206 has three clauses and all three are here, because each fails in a
different way. A **wider** role value fails the build rather than being
clamped, so the role file and the limit in force cannot disagree (ADR-0006
D4's strict reading). A **narrower** one compiles to its own value. And a key
the role **omits** inherits the pool's — asserted on the compiled
`UsageLimits` and not on the record, because a compiler that dropped the key
would leave the field unset, which 2.45.0 treats as unlimited. AC-0265 cannot
catch that: it only ever compares the pool against itself.

AC-0246 is a different question — *when* the bound is applied. A settings read
would pass on a flag that is set and never consulted, so the stub model below
implements `count_tokens` and records whether `request` ran.

**`count_tokens_before_request` is true in this file's pool mapping, and
AC-0270 refuses exactly that.** They do not conflict. AC-0270 governs the
deployed `CED_POOL_DEFAULT_LIMITS` through `verify_boot`, where ADR-0006 D1
suspends the pre-request bound over an IAM shape that was not re-derived; this
file passes a pool mapping straight to `compile_role`, reaching no environment
and no deployment. The ratified design § 7 names the counting stub as what
sets the flag for exactly this demonstration.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded

from ced.agents.compiler import (
    DECLARABLE_LIMITS,
    POOL_OWNED_LIMIT,
    RoleCompileError,
    compile_role,
)

from .role_records import (
    POOL_DEFAULT_LIMITS,
    CountsTokensModel,
    a_pool,
    a_quarantined_role,
)


@pytest.mark.parametrize("key", DECLARABLE_LIMITS)
def test_a_role_value_wider_than_the_pool_default_fails_the_build(key: str) -> None:
    """AC-0206, first clause, over each of the four keys."""
    wider = int(POOL_DEFAULT_LIMITS[key]) + 1
    role = a_quarantined_role(limits={key: wider})

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(), pool=a_pool())

    assert key in str(caught.value)
    assert str(wider) in str(caught.value)
    assert str(POOL_DEFAULT_LIMITS[key]) in str(caught.value)


@pytest.mark.parametrize("key", DECLARABLE_LIMITS)
def test_a_role_value_narrower_than_the_pool_default_compiles_to_its_own(key: str) -> None:
    """AC-0206, second clause. The role's value is what the agent is bounded by."""
    narrower = int(POOL_DEFAULT_LIMITS[key]) - 1
    compiled = compile_role(
        role=a_quarantined_role(limits={key: narrower}), integrations=(), pool=a_pool()
    )

    assert getattr(compiled.limits, key) == narrower


@pytest.mark.parametrize("key", DECLARABLE_LIMITS)
def test_a_key_the_role_omits_inherits_the_pools_value(key: str) -> None:
    """AC-0206, third clause, read off the **compiled** limits.

    The silent one: a dropped key leaves the `UsageLimits` field at its
    unset default, which is no bound at all.
    """
    compiled = compile_role(role=a_quarantined_role(), integrations=(), pool=a_pool())

    assert getattr(compiled.limits, key) == POOL_DEFAULT_LIMITS[key]


def test_a_role_declaring_the_pool_owned_flag_fails_the_build() -> None:
    """§ 5: the pool supplies `count_tokens_before_request` and a role may not."""
    role = a_quarantined_role(limits={POOL_OWNED_LIMIT: True})

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(), pool=a_pool())

    assert POOL_OWNED_LIMIT in str(caught.value)


def test_a_limit_outside_the_declarable_four_fails_the_build() -> None:
    """§ 5 excludes `cost_limit`, and `UsageLimits` would accept it unexamined."""
    role = a_quarantined_role(limits={"cost_limit": 5})

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(), pool=a_pool())

    assert "cost_limit" in str(caught.value)


#: The per-request ceiling both AC-0246 checks narrow to. It sits well above
#: the input tokens `FunctionModel` estimates for the one-word prompt below,
#: because 2.45.0 checks this same limit a **second** time in
#: `_append_response`, against the response's own usage. Only the first check
#: is pre-request, and only a ceiling clear of the estimate lets the admitted
#: case reach the model rather than dying on the way back.
PER_REQUEST_CEILING = 500


def a_counting_pool(counted_tokens: int) -> tuple[CountsTokensModel, dict[str, object]]:
    """A stub model that counts `counted_tokens`, and the pool that wires it."""
    model = CountsTokensModel(counted_tokens)
    limits = dict(POOL_DEFAULT_LIMITS) | {POOL_OWNED_LIMIT: True}
    return model, a_pool(model=model, default_limits=limits)


def test_a_request_over_the_per_request_input_ceiling_raises_before_the_request() -> None:
    """AC-0246. The ceiling is per request and denominated in tokens.

    `input_tokens_limit` is cumulative across a run and cannot bound one
    request, which is why the narrowed key is the per-request one. The empty
    `requests` list is the whole point: the run died before the model was
    asked.
    """
    model, pool = a_counting_pool(counted_tokens=PER_REQUEST_CEILING * 2)
    compiled = compile_role(
        role=a_quarantined_role(limits={"per_request_input_tokens_limit": PER_REQUEST_CEILING}),
        integrations=(),
        pool=pool,
    )

    with pytest.raises(UsageLimitExceeded) as caught:
        asyncio.run(compiled.agent.run("go", usage_limits=compiled.limits))

    assert "per_request_input_tokens_limit" in str(caught.value)
    assert model.requests == [], "the model was asked despite the ceiling"


def test_a_request_under_the_same_ceiling_reaches_the_model() -> None:
    """The contrast: the bound is what stopped the run above, not the stub."""
    model, pool = a_counting_pool(counted_tokens=5)
    compiled = compile_role(
        role=a_quarantined_role(limits={"per_request_input_tokens_limit": PER_REQUEST_CEILING}),
        integrations=(),
        pool=pool,
    )

    asyncio.run(compiled.agent.run("go", usage_limits=compiled.limits))

    assert model.requests == [1]
