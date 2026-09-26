"""Offline persistence tests: AC-0226 and AC-0228.

AC-0226 — a history carrying a tool call, a tool return, a retry part and a
pending approval serialises, deserialises and re-serialises to identical bytes.

AC-0228 — no persisted history contains a reasoning part, demonstrated against
a history that carried one before persisting.  The strip is asserted on storage
(the bytes), not on the in-memory messages after deserialisation: a strip that
only affects memory would let a serialisation regression put reasoning back.

These run offline; no substrate is needed.

**Mutation proofs (required, per plan.md):**

AC-0226 mutation: remove the ``serialise_history`` → ``deserialise_history``
round-trip and compare the original bytes to a re-serialised version of a
manually constructed history missing one part.  The byte comparison fails with
a mismatch on the length.  Recorded as: "replacing ``deserialise_history``
with a hand-built history that drops the RetryPromptPart reds the second-dump
equality check."

AC-0228 mutation: remove ``_strip_reasoning`` from ``serialise_history`` (i.e.,
call ``ModelMessagesTypeAdapter.dump_json`` directly without stripping).  The
``b"thinking"`` assertion fails because the bytes still contain the ThinkingPart.
Recorded as: "bypassing _strip_reasoning in serialise_history reds the
``b'thinking' not in first`` assertion."
"""

from __future__ import annotations

import datetime

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from ced.adapters.objectstore.history import deserialise_history, serialise_history

#: A fixed timestamp makes the bytes stable without freezing the clock.
_AT = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

#: Distinctive text that must be absent from the stripped bytes.
_REASONING = "cross-checking-two-cik-numbers"

#: The tool_call_id for the pending approval at suspension.
_APPROVAL_CALL_ID = "toolu_approval_01"


def _history_with_pending_approval():
    """A realistic history carrying tool call, tool return, retry, and pending approval.

    The last part is a ToolCallPart for ``request_approval`` with no
    corresponding ToolReturnPart — this is what the message history looks like
    at the point of suspension.  It is what AC-0226 says "pending approval"
    means: a deferred call in the history, not a separate data structure.
    """
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
                ToolCallPart(
                    tool_name="fetch_filing",
                    args={"cik": "9999999999"},
                    tool_call_id="toolu_01bad",
                ),
            ],
            timestamp=_AT,
        ),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content="unknown cik",
                    tool_name="fetch_filing",
                    tool_call_id="toolu_01bad",
                    timestamp=_AT,
                )
            ]
        ),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="fetch_filing",
                    args={"cik": "0000320193"},
                    tool_call_id="toolu_01good",
                )
            ],
            timestamp=_AT,
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="fetch_filing",
                    content={"revenue": 1},
                    tool_call_id="toolu_01good",
                    timestamp=_AT,
                )
            ]
        ),
        # Pending approval: the model called request_approval but no return has
        # been recorded yet.  This is the suspended state.
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="request_approval",
                    args={},
                    tool_call_id=_APPROVAL_CALL_ID,
                )
            ],
            timestamp=_AT,
        ),
    ]


def test_ac0226_history_with_pending_approval_round_trips_byte_identically() -> None:
    """AC-0226: serialise → deserialise → serialise produces identical bytes.

    The combination of tool call, tool return, retry part and pending approval
    is what no prior probe asserted as a whole.  Testing each half separately
    would miss serialiser bugs that only appear when all four shapes coexist.

    Reasoning parts are stripped by ``serialise_history`` before the first
    dump (AC-0228's backstop), so the comparison is between two runs of the
    stripped serialiser.
    """
    history = _history_with_pending_approval()
    first = serialise_history(history)
    restored = deserialise_history(first)
    second = serialise_history(restored)
    assert first == second, (
        "serialise → deserialise → serialise did not produce identical bytes; "
        f"first length={len(first)}, second length={len(second)}"
    )

    # Verify the part shapes survived: tool call, retry, tool return and the
    # pending approval call are all present in the restored history.
    kinds = [type(part).__name__ for message in restored for part in message.parts]
    # ThinkingPart was stripped; the rest must survive.
    assert "ThinkingPart" not in kinds, (
        "ThinkingPart survived the round trip — the reasoning strip did not fire"
    )
    assert "RetryPromptPart" in kinds
    assert "ToolReturnPart" in kinds
    # The pending approval call is the last ToolCallPart.
    tool_call_parts = [
        (part.tool_name, part.tool_call_id)
        for message in restored
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert any(name == "request_approval" for name, _ in tool_call_parts), (
        "pending approval ToolCallPart not found in restored history"
    )


def test_ac0228_no_reasoning_part_in_persisted_bytes() -> None:
    """AC-0228: serialise_history strips ThinkingPart before writing.

    The assertion is on the *bytes* — not on the in-memory representation
    after deserialisation.  A strip that only affects memory would let a
    serialisation regression put reasoning back into the stored payload.

    The history carries a ThinkingPart whose ``content`` is a distinctive
    string; the test asserts that neither the content nor the ``thinking``
    discriminator field appear in the serialised bytes.
    """
    history = _history_with_pending_approval()

    # Confirm the history carries the reasoning before serialisation.
    assert any(
        isinstance(part, ThinkingPart)
        for msg in history
        if isinstance(msg, ModelResponse)
        for part in msg.parts
    ), "fixture does not carry a ThinkingPart — the test proves nothing"

    first = serialise_history(history)

    assert _REASONING.encode() not in first, (
        "the reasoning content is present in the serialised bytes; "
        "the strip did not run before serialisation"
    )
    assert b"thinking" not in first, (
        "the 'thinking' discriminator is present in the serialised bytes; "
        "a ThinkingPart survived the strip"
    )

    # The strip must be selective: the non-reasoning content must survive.
    assert b"fetch_filing" in first
    assert b"request_approval" in first


def test_ac0228_strip_is_in_the_write_path_not_only_in_memory() -> None:
    """AC-0228 guard: a raw ModelMessagesTypeAdapter dump still carries reasoning.

    This calibration check ensures the strip is in ``serialise_history`` and
    is not already done by the framework itself.  If the framework's own
    serialiser strips ThinkingPart, both the AC-0228 test and this one would
    agree — but the reasoning-strip code in ``_strip_reasoning`` would be a
    no-op and the storage backstop would be vacuous.

    A raw dump MUST contain the ThinkingPart; the stripped dump must not.
    """
    history = _history_with_pending_approval()
    raw_bytes = ModelMessagesTypeAdapter.dump_json(history)
    stripped_bytes = serialise_history(history)

    assert _REASONING.encode() in raw_bytes, (
        "the raw TypeAdapter dump does not contain the reasoning content — "
        "the framework already strips ThinkingPart and AC-0228's strip is vacuous"
    )
    assert _REASONING.encode() not in stripped_bytes, (
        "the reasoning content survived serialise_history"
    )
