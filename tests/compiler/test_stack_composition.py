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
        role={
            "role_name": "analysis",
            "version": 1,
            "ceiling": [],
            "pool_class": None,
            "model_settings": {"model_id": "stub:counting", "settings": {}, "limits": {}},
            "output_schema_ref": "reference-selection",
        },
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
