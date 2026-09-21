"""Where this runtime resolves the `pydantic_ai` names its design rests on.

**The seam is the probed set, not every framework name.** Each name below is a
row of `plan.md` § Grounding probe — a claim a ratified document rests on, and
one the framework-seam contract suite asserts — so a re-export moving in a
minor release is a one-file change and reds the offline gate rather than a
production step. `tests/contract/test_seam_module.py` closes `__all__` to
exactly that set plus the two pin constants, which is what keeps the set a
contract rather than a convenience import.

Ordinary framework names carrying no such claim — `RunContext`, `ToolsetTool`,
`AbstractToolset` among them — resolve directly where they are used.
`agents/` and `adapters/` are both admitted layers under
`tests/architecture/dependency_direction.py`, so that is legal, and routing
them through here would widen the seam into an import hub and red the test
above. ADR-0001 puts `pydantic_ai` at the step-level-reasoning-library
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
