"""§ Grounding probe rows 8 and 9 — history round-trips, and row 4's reasoning part.

r5 § 10 Rollout criterion 6 requires a stored history to come back unchanged,
because the step lifecycle persists one and resumes from it. DR8 requires the
reasoning parts to be strippable and to leave nothing behind in the bytes.

The history below is deliberately realistic: it carries a tool call, a tool
return and a retry part, which are the shapes a naive serializer gets wrong.
"""

from __future__ import annotations

import datetime

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

#: A fixed timestamp keeps the bytes comparable without freezing the clock.
_AT = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

#: The reasoning text. It is asserted absent from the stripped bytes, so it has
#: to be a string nothing else in the history contains.
_REASONING = "weighing-two-filings"


def _history() -> list[ModelMessage]:
    """A history covering the part types the worker persists."""
    return [
        ModelRequest(
            parts=[
                SystemPromptPart(content="You are an analyst.", timestamp=_AT),
                UserPromptPart(content="Summarise the filing.", timestamp=_AT),
            ]
        ),
        ModelResponse(
            parts=[
                ThinkingPart(content=_REASONING),
                ToolCallPart(tool_name="fetch", args={"cik": "0000000000"}, tool_call_id="c1"),
            ],
            timestamp=_AT,
        ),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content="unknown cik", tool_name="fetch", tool_call_id="c1", timestamp=_AT
                )
            ]
        ),
        ModelResponse(
            parts=[
                ToolCallPart(tool_name="fetch", args={"cik": "0000320193"}, tool_call_id="c2")
            ],
            timestamp=_AT,
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="fetch",
                    content={"revenue": 1},
                    tool_call_id="c2",
                    timestamp=_AT,
                )
            ]
        ),
        ModelResponse(parts=[TextPart(content="Revenue rose.")], timestamp=_AT),
    ]


def _strip_reasoning(history: list[ModelMessage]) -> list[ModelMessage]:
    """Drop every reasoning part, leaving the rest of the history alone."""
    stripped: list[ModelMessage] = []
    for message in history:
        if isinstance(message, ModelResponse):
            kept = [part for part in message.parts if not isinstance(part, ThinkingPart)]
            stripped.append(ModelResponse(parts=kept, timestamp=message.timestamp))
        else:
            stripped.append(message)
    return stripped


def test_a_realistic_history_round_trips_byte_identically() -> None:
    """Row 8. Dump, validate, dump again — the second dump must match the first."""
    history = _history()
    first = ModelMessagesTypeAdapter.dump_json(history)
    restored = ModelMessagesTypeAdapter.validate_json(first)
    second = ModelMessagesTypeAdapter.dump_json(restored)

    assert first == second

    # The part types survive the trip, not just the byte count.
    kinds = [type(part).__name__ for message in restored for part in message.parts]
    assert kinds == [
        "SystemPromptPart",
        "UserPromptPart",
        "ThinkingPart",
        "ToolCallPart",
        "RetryPromptPart",
        "ToolCallPart",
        "ToolReturnPart",
        "TextPart",
    ]


def test_a_reasoning_part_survives_the_round_trip_as_a_reasoning_part() -> None:
    """Row 4, second clause. DR8 can only strip a part the deserializer still names."""
    restored = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json(_history())
    )
    thinking = [
        part
        for message in restored
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ThinkingPart)
    ]
    assert [part.content for part in thinking] == [_REASONING]


def test_a_reasoning_stripped_history_round_trips_and_leaks_no_reasoning() -> None:
    """Row 9. Both halves: the bytes are stable, and the reasoning is gone from them."""
    stripped = _strip_reasoning(_history())
    first = ModelMessagesTypeAdapter.dump_json(stripped)
    second = ModelMessagesTypeAdapter.dump_json(ModelMessagesTypeAdapter.validate_json(first))

    assert first == second
    assert _REASONING.encode() not in first
    assert b"thinking" not in first

    # The stripping removed only the reasoning: everything else is still there.
    assert b"fetch" in first
    assert _REASONING.encode() in ModelMessagesTypeAdapter.dump_json(_history())
