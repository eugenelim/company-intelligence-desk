"""AC-0267, AC-0269 and AC-0251 — three closed sets, each an allowlist.

Every one of them refuses a **non-member** rather than one named bad value, so
a typo, a casing variant or an invented name fails closed instead of reaching
whatever the framework does with it.

The three sets are the compiler's output contracts, the settings keys § 5
declares, and the pool's `allowed_model_ids`. The first two live beside the
compiler; the third is deployment configuration, and the check is in
`ced.agents.models`, which is where the set is read.
"""

from __future__ import annotations

import pytest
from pydantic_ai.settings import ModelSettings

from ced.agents.compiler import (
    ADMITTED_SETTINGS,
    OUTPUT_CONTRACTS,
    RoleCompileError,
    compile_role,
)

from .role_records import (
    STUB_MODEL_ID,
    a_ceiling_entry,
    a_pool,
    a_quarantined_role,
    a_role,
    an_integration,
)

#: Pinned to a name **no named successor adds to the set**.
#: `walking-skeleton-step-lifecycle`'s AC-0255 adds `free-form` as the set's
#: third member, so a case pinned to that value would stop testing membership
#: at exactly the moment the set grows, and would red in that spec's pull
#: request for the wrong reason.
NOT_A_MEMBER = "not-a-contract"


def test_the_case_value_is_outside_the_set_it_is_used_to_probe() -> None:
    """Guards the case itself: a member would make the next check vacuous."""
    assert NOT_A_MEMBER not in OUTPUT_CONTRACTS


def test_an_output_contract_outside_the_declared_set_fails_to_compile() -> None:
    """AC-0267, on a non-quarantined role, which AC-0219's guards do not cover.

    AC-0219 guards the two quarantined pairings only, so without this a
    planning role declaring an unrecognised name is refused by nothing here.
    The refusal is the compiler's named error and not the `KeyError` a bare
    dictionary lookup would raise.
    """
    role = a_role(ceiling=[a_ceiling_entry()], output_schema_ref=NOT_A_MEMBER)

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(an_integration(),), pool=a_pool())

    assert NOT_A_MEMBER in str(caught.value)


def test_the_framework_accepts_the_settings_key_the_compiler_refuses() -> None:
    """What makes the next check a test of the compiler's own allowlist.

    On the pinned 2.45.0 `ModelSettings` is a `total=False` TypedDict of
    sixteen keys. `extra_headers` is one of them, so a compiler that forwarded
    the role's `settings` unchecked would let role data set provider headers —
    and no framework error would say so.
    """
    assert "extra_headers" in ModelSettings.__annotations__
    assert "extra_headers" not in ADMITTED_SETTINGS


def test_a_settings_key_outside_the_declared_set_fails_to_compile() -> None:
    """AC-0269. The key is one the framework's TypedDict accepts."""
    role = a_quarantined_role(settings={"extra_headers": {"x-probe": "1"}})

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(), pool=a_pool())

    assert "extra_headers" in str(caught.value)


def test_the_three_declared_settings_keys_compile() -> None:
    """The admitted half: § 5's shape is what a role may carry."""
    role = a_quarantined_role(
        settings={"max_tokens": 1024, "temperature": 0.0, "thinking": False}
    )

    compiled = compile_role(role=role, integrations=(), pool=a_pool())

    assert compiled.role_name == "quarantine"


def test_a_model_id_outside_the_pools_allowed_set_fails_to_compile() -> None:
    """AC-0251's compile half. The load half — an omitted `model_id` — is the
    loader's and is decided in `test_role_loader.py`."""
    role = a_role(model_id="stub:unlisted")

    with pytest.raises(RoleCompileError) as caught:
        compile_role(role=role, integrations=(), pool=a_pool())

    assert "stub:unlisted" in str(caught.value)
    assert STUB_MODEL_ID in str(caught.value)


def test_a_model_id_inside_the_pools_allowed_set_compiles() -> None:
    """The contrast, and the state every other check in this package rests on."""
    compiled = compile_role(role=a_role(), integrations=(), pool=a_pool())

    assert compiled.role_name == "analysis"
