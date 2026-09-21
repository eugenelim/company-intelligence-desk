"""`ced.adapters.framework_contract` binds the names the probe rows cover.

The module is the runtime's single resolution point for framework names, so
the suite asserts that each binding is the framework's own object. A re-export
that moves reds in `test_deferred_requests.py`; a *binding* that drifts to some
other object reds here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pydantic_ai
import pydantic_ai.messages
import pydantic_ai.settings
import pydantic_ai.toolsets
import pydantic_ai.usage

from ced.adapters import framework_contract

_SOURCE = Path(framework_contract.__file__)

#: Each seam name, against the framework module that owns it.
CANONICAL = {
    "Agent": pydantic_ai,
    "AgentRetries": pydantic_ai,
    "CancellationToken": pydantic_ai,
    "DeferredToolRequests": pydantic_ai,
    "ModelRetry": pydantic_ai,
    "ModelMessagesTypeAdapter": pydantic_ai.messages,
    "ThinkingPart": pydantic_ai.messages,
    "ModelSettings": pydantic_ai.settings,
    "FunctionToolset": pydantic_ai.toolsets,
    "WrapperToolset": pydantic_ai.toolsets,
    "UsageLimits": pydantic_ai.usage,
}


def test_every_seam_name_binds_the_frameworks_own_object() -> None:
    for name, module in CANONICAL.items():
        assert getattr(framework_contract, name) is getattr(module, name), name


def test_the_exported_surface_is_exactly_the_seam_plus_the_pin_constants() -> None:
    """`__all__` is the surface; an unlisted import is not a seam the runtime may use."""
    assert set(framework_contract.__all__) == set(CANONICAL) | {
        "FRAMEWORK_DISTRIBUTION",
        "PINNED_FRAMEWORK_VERSION",
    }


def test_the_model_type_name_is_not_bound_here() -> None:
    """The ratified design keeps `Model` in `ced.agents.models` and nowhere else.

    The check reads the AST rather than the text, so the sentence in the module
    docstring explaining the rule does not satisfy or violate it.
    """
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
            assert node.module != "pydantic_ai.models", "the model module is a later task's"
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "Model" not in imported
    assert not hasattr(framework_contract, "Model")
