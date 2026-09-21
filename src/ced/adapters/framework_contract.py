"""The single place this runtime resolves its `pydantic_ai` names.

Every framework name the agent layer depends on is bound here, so a re-export
moving in a minor release is a one-file change rather than a scatter of import
edits — and so the framework-seam contract suite has one object to assert
against. ADR-0001 puts `pydantic_ai` at the step-level-reasoning-library
position; ADR-0002 D1 pins the version exactly, because the vendor does not
class an additive re-export move as breaking.

`pydantic_ai.models.Model` is deliberately absent. The ratified design keeps
that type name in `ced.agents.models` alone, which is the module that supplies
the model factory; naming it here would put it in a second place.
"""

from __future__ import annotations

from pydantic_ai import (
    Agent,
    AgentRetries,
    CancellationToken,
    DeferredToolRequests,
    ModelRetry,
)
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ThinkingPart,
)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset
from pydantic_ai.usage import UsageLimits

#: The `pydantic-ai-slim` release this runtime is contracted against, per
#: ADR-0002 D1. The contract suite asserts the installed distribution and the
#: manifest both agree with this value, so a silent version drift reds the
#: offline gate instead of a production step.
PINNED_FRAMEWORK_VERSION = "2.45.0"

#: The distribution that provides every name above. The `[bedrock]` extra is
#: part of the same pin; the contract suite imports the Bedrock model to prove
#: the extra is installed, and no code here reaches a provider.
FRAMEWORK_DISTRIBUTION = "pydantic-ai-slim"

__all__ = [
    "FRAMEWORK_DISTRIBUTION",
    "PINNED_FRAMEWORK_VERSION",
    "Agent",
    "AgentRetries",
    "CancellationToken",
    "DeferredToolRequests",
    "FunctionToolset",
    "ModelMessagesTypeAdapter",
    "ModelRetry",
    "ModelSettings",
    "ThinkingPart",
    "UsageLimits",
    "WrapperToolset",
]
