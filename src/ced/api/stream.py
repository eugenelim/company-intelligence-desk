"""Server-sent event streaming for committed run events."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager
from uuid import UUID

import psycopg
from fastapi import HTTPException

from ced.adapters.postgres import event_log
from ced.api.models import Event
from ced.domain.events import TERMINAL_EVENT_TYPES

POLL_SECONDS = 0.2
READ_LIMIT = 100


def selected_cursor(
    after_values: Sequence[str], last_event_id: str | None, highest_seq: int
) -> int:
    """Return the resume cursor, preferring ``Last-Event-ID`` over ``after``.

    ``after_values`` is **every** raw ``after`` value as the caller sent it —
    the full list, not the integer FastAPI parsed and not only the last value.
    Pydantic's lax ``int`` already turns ``0_1``, ``1.0`` and ``+1`` into 1, so
    judging the parsed value would leave the query source coercible; and a
    repeated parameter binds only its last value, so judging that one alone
    would let ``?after=x&after=1`` through while refusing ``?after=1&after=x``.
    The last value is the selected ``after``, matching FastAPI's binding.
    Every supplied value, and the header, pass through the one predicate
    below.

    The cursor is accepted only as a bare ASCII decimal integer. ``int()``
    alone is not that test: it parses ``1_0`` as 10, strips surrounding
    whitespace, accepts a leading ``+``, and accepts non-ASCII decimal digits
    such as ``٣``. Each of those is a cursor the caller did not send, so
    admitting them would coerce the value — which AC-0323 forbids by name, and
    which the committed contract also rules out by declaring the header
    ``type: integer, minimum: 0``.

    **``isascii()`` is load-bearing for a second class, and that class is the
    one that reaches this code.** ``str.isdigit()`` is true of characters
    ``int()`` cannot parse at all — a superscript such as ``²`` (U+00B2) — and
    unlike ``٣`` that character is latin-1 encodable, so it travels in an HTTP
    header. Without ``isascii()`` it would pass the digit test, reach
    ``int()``, raise ``ValueError`` uncaught, and return 500 where AC-0323
    requires 422. ``tests/api/test_event_stream.py`` drives it.

    **The negative case has no branch of its own, deliberately.** ``-1`` fails
    the lexical test above — ``-`` is not a digit — so it is refused there,
    and a separate ``cursor < 0`` guard after the parse would be unreachable.
    A guard no input can trip reads as live protection while proving nothing,
    so the lexical predicate carries both obligations and the ledger records
    the negative spelling as one of its mutations.
    """
    # Every *supplied* cursor is judged lexically, selected or not: a
    # malformed `after` is refused even when a valid `Last-Event-ID` outranks
    # it. That is the owner's decision of 2026-10-01, and it agrees with what
    # FastAPI's typed `Query(ge=0)` already does for `-1` and `abc` before this
    # function runs — so every malformed spelling gets the same answer.
    after = after_values[-1] if after_values else None
    # A *present* `Last-Event-ID` is a supplied cursor even when empty: AC-0323
    # selects it "when present", and reading an empty one as absent would be
    # the coercion that criterion forbids. Refusing it costs no browser
    # anything — a conforming `EventSource` sends the header only when its
    # last event ID is non-empty (WHATWG HTML, server-sent events), and simply
    # omits it otherwise. Every `after` value is supplied the same way, so
    # `?after=&after=1` is refused as `?after=1&after=` already is.
    supplied = ([last_event_id] if last_event_id is not None else []) + list(after_values)
    for value in supplied:
        if not (value.isascii() and value.isdigit()):
            raise HTTPException(
                status_code=422,
                detail="stream cursor must be a non-negative decimal integer",
            )
    # The bounds check, by contrast, applies only to the cursor that is used:
    # AC-0323 bounds "the selected stream cursor", and an outranked `after`
    # opens nothing, so its magnitude cannot matter.
    raw = last_event_id or after or "0"
    # A lexically valid all-ASCII-digit string can still exceed Python 3.13's
    # 4 300-digit limit for int() conversion and raise ValueError uncaught,
    # returning 500 where AC-0323 requires 422.  Any cursor that large is
    # necessarily ahead of highest_seq, so the bounds check below would refuse
    # it if the conversion succeeded; catching the failure here keeps the
    # answer 422 regardless of the conversion limit.
    try:
        cursor = int(raw)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="stream cursor must be a non-negative decimal integer",
        ) from None
    if cursor > highest_seq:
        raise HTTPException(
            status_code=422,
            detail="stream cursor is ahead of the run's highest committed sequence",
        )
    return cursor


def highest_committed_seq(conn: psycopg.Connection, run_id: UUID) -> int:
    """Read the highest committed event sequence for ``run_id``."""
    row = conn.execute(
        "SELECT coalesce(max(seq), 0) FROM events WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    assert row is not None
    return int(row[0])


def encode_sse_event(event: Event) -> str:
    """Encode one event envelope as a WHATWG server-sent event block.

    No ``event:`` field is set, and that is deliberate. A named ``event:``
    dispatches the frame under that name, so a client's ``onmessage`` never
    fires and it must register one listener per type — an enumeration
    ``ced.domain.events`` makes impossible to keep complete, because the
    step-scoped vocabulary is deliberately open. The committed type travels in
    the JSON envelope's ``type`` field instead, so one ``EventSource``
    ``onmessage`` handler reads every type, including one added later.
    """
    data = event.model_dump_json()
    return f"id: {event.seq}\ndata: {data}\n\n"


def committed_event_stream(
    connection_factory: Callable[[], AbstractContextManager[psycopg.Connection]],
    *,
    run_id: UUID,
    after: int,
) -> Iterator[str]:
    """Yield committed events until a terminal event closes the stream."""
    cursor = after
    while True:
        with connection_factory() as conn:
            envelopes = event_log.read_events(
                conn,
                run_id=run_id,
                after=cursor,
                limit=READ_LIMIT,
            )
        for envelope in envelopes:
            cursor = envelope.seq
            event = Event.of(envelope)
            yield encode_sse_event(event)
            if envelope.type in TERMINAL_EVENT_TYPES:
                return
        time.sleep(POLL_SECONDS)
