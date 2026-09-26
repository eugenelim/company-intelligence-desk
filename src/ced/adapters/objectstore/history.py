"""Message-history serialization with reasoning strip, and approval-resume helper.

``pydantic_ai`` imports are allowed here (``adapters/``). The serialization and
deserialization functions are the canonical implementations; ``worker/persistence.py``
calls them rather than importing ``pydantic_ai`` directly.

**The strip is mandatory, not optional.** DR8 requires that no persisted history
contain a reasoning part. The executor calls ``serialise_history`` before writing
the suspension payload; the strip is part of the write path, not a post-process.

**``run_with_approval`` is isolated here for the same reason.** ``DeferredToolResults``
is a ``pydantic_ai.tools`` name; keeping the import in ``adapters/`` is what keeps
``worker/`` free of a direct ``pydantic_ai`` dependency.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from pydantic_ai import DeferredToolResults
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, ThinkingPart
from pydantic_ai.toolsets import FunctionToolset

__all__ = [
    "deserialise_history",
    "run_with_approval",
    "serialise_history",
]


def serialise_history(messages: list[Any]) -> bytes:
    """Strip reasoning parts and serialize the history to bytes.

    The strip is DR8's storage backstop (AC-0228): no persisted history may
    contain a ``ThinkingPart``. The bytes are canonical ``ModelMessagesTypeAdapter``
    JSON; ``deserialise_history`` inverts this operation exactly.
    """
    stripped = _strip_reasoning(messages)
    return ModelMessagesTypeAdapter.dump_json(stripped)


def deserialise_history(data: bytes) -> list[Any]:
    """Deserialize history bytes produced by ``serialise_history``."""
    return ModelMessagesTypeAdapter.validate_json(data)


def run_with_approval(
    agent: Any,
    *,
    history: list[Any],
    approval_map: Mapping[str, bool],
    usage_limits: Any,
    output_type: Any,
    approval_toolset: FunctionToolset[Any],
    cancellation_token: Any | None = None,
) -> Any:
    """Resume an agent from history, applying a set of approval decisions.

    Called by ``worker/persistence.py``'s resume function, where the
    ``DeferredToolResults`` import would violate the no-``pydantic_ai``-in-``worker/``
    rule. ``approval_map`` is ``{tool_call_id: bool}`` — ``True`` to approve,
    ``False`` to deny.
    """
    return agent.run_sync(
        message_history=history,
        deferred_tool_results=DeferredToolResults(approvals=approval_map),  # type: ignore[arg-type]
        usage_limits=usage_limits,
        output_type=output_type,
        toolsets=[approval_toolset],
        cancellation_token=cancellation_token,
    )


def _strip_reasoning(messages: list[Any]) -> list[Any]:
    """Remove every ``ThinkingPart`` from every ``ModelResponse`` in ``messages``.

    The design decision (recorded in ``plan.md`` § Design decisions and in
    ``spec.md`` § Boundaries) is that the strip happens in the executor before
    serialising, **not** via a history processor. A processor changes what is
    sent to the model; a processor would leave the reasoning part in the
    serialised bytes, which is the mistake AC-0228 exists to catch.

    Only ``ModelResponse`` messages carry parts; ``ModelRequest`` messages are
    left unchanged.
    """
    result: list[Any] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            kept = [p for p in msg.parts if not isinstance(p, ThinkingPart)]
            result.append(dataclasses.replace(msg, parts=kept))
        else:
            result.append(msg)
    return result
