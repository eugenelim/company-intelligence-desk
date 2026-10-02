"""SSE stream behavior for committed run events."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from uuid import UUID

import psycopg
import pytest

from ced.api.stream import READ_LIMIT

from .conftest import Client

pytestmark = pytest.mark.substrate


def _stream_request(
    api_server: Client,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    request = urllib.request.Request(api_server.base_url + path, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (
                response.status,
                response.headers.get_content_type(),
                response.read().decode(),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get_content_type(), exc.read().decode()


def _blocks(raw: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for block in raw.strip().split("\n\n"):
        event: dict[str, Any] = {}
        data = ""
        for line in block.splitlines():
            if line.startswith("id: "):
                event["id"] = line.removeprefix("id: ")
            elif line.startswith("event: "):
                event["event"] = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        if data:
            event["data"] = json.loads(data)
        if event:
            parsed.append(event)
    return parsed


def _insert_terminal(conn: psycopg.Connection, run_id: str, seq: int = 2) -> None:
    with conn.transaction():
        conn.execute(
            """
            INSERT INTO events (run_id, seq, type, step_id, principal)
            VALUES (%s, %s, 'run.completed', NULL, 'worker')
            """,
            (UUID(run_id), seq),
        )
        conn.execute("UPDATE runs SET state = 'completed' WHERE run_id = %s", (UUID(run_id),))
    # The `owner_conn` fixture starts an implicit transaction with its first SELECT
    # (from `clean_runs`).  `conn.transaction()` therefore creates a SAVEPOINT rather
    # than a full BEGIN/COMMIT cycle, leaving the inserted rows invisible to the
    # separate connection opened by the stream endpoint.  Committing here makes them
    # durable and visible to all subsequent readers.
    conn.commit()


def test_terminal_event_closes_the_stream(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """The stream emits one frame per committed event and ends at the terminal one.

    No frame carries an ``event:`` field; the committed type travels in the
    envelope.  That is what lets a browser read every type through a single
    ``EventSource.onmessage`` handler rather than a per-type listener
    enumeration that the open step-scoped vocabulary could never complete.

    Mutation: restore ``event: {event.type}`` in ``encode_sse_event``.  The
    absence assertion below fails with the emitted type in the message.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)

    status, media_type, raw = _stream_request(api_server, f"/runs/{run_id}/events/stream")

    assert status == 200
    assert media_type == "text/event-stream"
    blocks = _blocks(raw)
    assert [block["id"] for block in blocks] == ["1", "2"]
    assert blocks[-1]["data"]["type"] == "run.completed"
    named = [block["event"] for block in blocks if "event" in block]
    assert named == [], f"frames must set no event: field, found {named}"


def test_last_event_id_precedes_query_cursor(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)

    status, _, raw = _stream_request(
        api_server,
        f"/runs/{run_id}/events/stream?after=0",
        headers={"Last-Event-ID": "1"},
    )

    assert status == 200
    assert [block["id"] for block in _blocks(raw)] == ["2"]


@pytest.mark.parametrize(
    "header",
    [
        "not-an-integer",
        "-1",
        "3",
        # Coercible spellings `int()` accepts: a leading plus and an
        # underscore separator. Each would resolve to a cursor the caller
        # never sent, which AC-0323 refuses as coercion.
        #
        # **Each coerces to 1 or 2, deliberately — inside this run's committed
        # range.** The run's highest sequence is 2, so a spelling that coerced
        # to something larger would be refused by the bounds guard instead and
        # would pass this check for the wrong reason, proving nothing about the
        # lexical guard. Measured: with the lexical guard replaced by a plain
        # `int()`, `1_0` (→ 10), `" 3 "` (→ 3) and `+4` (→ 4) all still
        # returned 422 from the bounds guard; only values inside the range red
        # the mutation.
        #
        "+1",
        "0_2",
        # A superscript two. This is the case that exercises the guard's
        # `isascii()` arm, and it is reachable: U+00B2 is `isdigit()`-true but
        # NOT `isdecimal()`, and it is latin-1 encodable, so it travels in a
        # header. `int("²")` raises `ValueError`, so with `isascii()` removed
        # this request returns 500 rather than the 422 AC-0323 requires.
        #
        # An earlier revision of this comment claimed no non-ASCII digit could
        # reach the server, and deferred the case on that basis. That is true
        # only of non-ASCII *decimal* digits such as "٣" (int("٣") == 3), which
        # latin-1 cannot encode — the client raises `UnicodeEncodeError` before
        # any request. It is false of the isdigit-but-not-decimal class, which
        # is exactly the class `isascii()` exists to refuse.
        "²",
        # Surrounding whitespace is still not driven, and that claim does hold:
        # the HTTP layer strips leading and trailing whitespace from a header
        # value before the application sees it (RFC 7230), so `" 2 "` arrives
        # as `"2"` and legitimately opens a stream. Observed: that case timed
        # out against the open stream rather than being refused.
        #
        # A cursor of 5 000 ASCII digits is lexically valid (all ASCII, all
        # digits) but exceeds Python 3.13's 4 300-digit limit for `int()`
        # conversion.  Without a guard the parse raises `ValueError` uncaught,
        # returning 500.  The cursor is also far above any run's highest_seq,
        # so a successful conversion would still be refused by the bounds
        # check; the important property is that the *path* never raises.
        #
        # Mutation: remove the `try/except ValueError` around `int(raw)` in
        # `selected_cursor`.  This request returns 500 rather than 422.
        "9" * 5000,
    ],
)
def test_invalid_last_event_id_is_refused(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
    header: str,
) -> None:
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)

    status, _, _ = _stream_request(
        api_server,
        f"/runs/{run_id}/events/stream?after=0",
        headers={"Last-Event-ID": header},
    )

    assert status == 422


def test_after_cursor_ahead_of_highest_seq_is_refused(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """AC-0323: ``after`` ahead of the run's highest committed sequence returns 422.

    ``selected_cursor`` validates the resolved cursor against the highest
    committed sequence regardless of whether the cursor came from
    ``Last-Event-ID`` or from the ``after`` query parameter.  This check
    exercises the ``after`` path: a non-negative integer that exceeds the
    highest committed sequence.

    Mutation: narrow the bounds guard to apply only when ``Last-Event-ID`` is
    present (skip the check when the cursor resolves from ``after``).  The
    ``after=3`` request then opens a stream past the run's last committed
    event, which polls forever for an event that never commits, so the check
    fails with ``TimeoutError: timed out`` on the socket read — the ``assert
    status == 422`` line is never reached.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)  # adds seq=2; highest_seq is now 2

    # after=3 exceeds the highest committed sequence (2).
    status, _, _ = _stream_request(api_server, f"/runs/{run_id}/events/stream?after=3")

    assert status == 422


@pytest.mark.parametrize("query", ["0_1", "1.0", "%2B1"])
def test_non_canonical_after_cursor_is_refused(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
    query: str,
) -> None:
    """AC-0323: a non-canonical ``after`` spelling returns 422, as the header does.

    ``after`` is declared a FastAPI ``int``, and pydantic's lax ``int`` coerces
    ``0_1``, ``1.0`` and ``+1`` (sent percent-encoded, since a bare ``+`` in a
    query string decodes to a space) to 1 before the handler runs. AC-0323
    refuses a coerced cursor from **either** source, so the handler judges the
    raw query string rather than the parsed integer.

    **Every case coerces to 1, inside this run's committed range (highest
    sequence 2), deliberately.** A spelling that coerced past the range would
    be refused by the bounds guard instead, and would pass this check for a
    reason unrelated to the branch under test.

    Mutation: pass the parsed ``after`` (``str(after)``) to ``selected_cursor``
    instead of the raw query string. Each case then opens a stream at cursor 1
    rather than returning 422.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)  # adds seq=2; highest_seq is now 2

    status, _, _ = _stream_request(api_server, f"/runs/{run_id}/events/stream?after={query}")

    assert status == 422


@pytest.mark.parametrize("query", ["0_1", "1.0"])
def test_unselected_malformed_after_is_refused(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
    query: str,
) -> None:
    """A malformed ``after`` is refused even when ``Last-Event-ID`` outranks it.

    With a valid header present, ``after`` is not the cursor the stream uses.
    Validating it anyway is the owner's decision of 2026-10-01: AC-0323 bounds
    only "the selected stream cursor", so its text does not settle an
    outranked one, and refusing it is what makes every malformed spelling get
    the same answer — FastAPI's typed ``Query(ge=0)`` already refuses an
    outranked ``-1`` or ``abc`` before the handler runs.

    Mutation: judge only the selected source lexically (check ``raw`` rather
    than every supplied cursor). The valid header is then the only value
    examined, so ``after=0_1`` slips through and the stream opens.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)  # adds seq=2; highest_seq is now 2

    status, _, _ = _stream_request(
        api_server,
        f"/runs/{run_id}/events/stream?after={query}",
        headers={"Last-Event-ID": "1"},
    )

    assert status == 422


@pytest.mark.parametrize("query", ["after=0_1&after=1", "after=1&after=0_1", "after=&after=1"])
def test_every_value_of_a_repeated_after_is_judged(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
    query: str,
) -> None:
    """A malformed value anywhere in a repeated ``after`` is refused.

    FastAPI binds a repeated scalar parameter to its *last* value, and so does
    ``query_params.get``. Judging that value alone made the answer depend on
    order: ``after=1&after=0_1`` was refused while ``after=0_1&after=1`` opened
    a stream. Both carry a malformed supplied cursor, and the owner decision of
    2026-10-01 judges every supplied cursor lexically, so the handler passes
    every value and both orders are refused.

    An empty value is a supplied value too: ``after=&after=1`` is refused, as
    ``after=1&after=`` already is (FastAPI's typed ``int`` refuses that empty
    last value before the handler runs).

    Mutations:
    - Pass only ``query_params.get("after")`` — the last value — to
      ``selected_cursor``. The ``after=0_1&after=1`` case then opens a stream.
    - Treat an empty ``after`` value as absent. (A present empty
      ``Last-Event-ID`` is refused too; see
      ``test_present_but_empty_last_event_id_is_refused``.)
      The ``after=&after=1`` case then opens a stream.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)  # adds seq=2; highest_seq is now 2

    status, _, _ = _stream_request(api_server, f"/runs/{run_id}/events/stream?{query}")

    assert status == 422


def test_present_but_empty_last_event_id_is_refused(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """AC-0323: an empty ``Last-Event-ID`` is a present, malformed cursor.

    AC-0323 selects "``Last-Event-ID`` when present", so an empty header is
    present, and it is not a non-negative integer. Reading it as absent and
    falling back to ``after`` would be the coercion the criterion forbids.

    Refusing it breaks no browser. A conforming ``EventSource`` sets the header
    only when its last event ID is non-empty (WHATWG HTML, server-sent events)
    and otherwise omits it, so the empty spelling reaches this route only from
    a non-browser caller.

    Mutation: treat an empty header as absent, as an earlier revision did. The
    request then falls back to ``after=1`` and opens a stream.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)  # adds seq=2; highest_seq is now 2

    status, _, _ = _stream_request(
        api_server,
        f"/runs/{run_id}/events/stream?after=1",
        headers={"Last-Event-ID": ""},
    )

    assert status == 422


@pytest.mark.parametrize("query", ["-1", "abc"])
def test_negative_or_non_numeric_after_is_refused_on_the_stream_route(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
    query: str,
) -> None:
    """AC-0323: a negative or non-numeric ``after`` returns 422 on the stream route.

    **More than one layer refuses each case, so no single break reds this
    check, and that is recorded rather than hidden.** Measured:

    - ``-1`` is refused by FastAPI's ``Query(ge=0)`` and, failing that, by
      ``selected_cursor``'s lexical check (``-`` is not a digit). Removing
      either alone leaves it refused; removing both makes it open a stream
      (``assert 200 == 422``).
    - ``abc`` is refused by FastAPI's ``int`` type itself, independently of
      ``ge=0``, and by the lexical check. Removing ``ge=0`` and the lexical
      check together still leaves it refused, because the typed parameter
      cannot parse it. It reds only if ``after`` stops being declared ``int`` —
      which would change the published schema, a change the owner declined.

    The check pins the observable contract — 422 — rather than any one layer.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    _insert_terminal(owner_conn, run_id)

    status, _, _ = _stream_request(api_server, f"/runs/{run_id}/events/stream?after={query}")

    assert status == 422


def test_live_tail_cursor_advance_and_paging(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """Cursor advance and READ_LIMIT paging are exercised by a live tail.

    Events are committed **after** the stream opens so the generator must poll
    and advance its cursor across multiple READ_LIMIT-sized pages.  Every
    sequence must arrive exactly once in strictly increasing order, and the
    stream must close after the terminal event.

    Breaks:
    (a) Delete ``cursor = envelope.seq`` in ``committed_event_stream``.  The
        cursor stays at the opening ``after`` of 0, so every poll re-reads the
        first ``READ_LIMIT`` events and never reaches the terminal event at
        ``seq=103``.  The stream never closes; ``thread.is_alive()`` is True at
        the join timeout.
    (b) End the stream after the first full ``READ_LIMIT`` page.  Sequences
        102 and 103 never arrive; ``seqs == list(range(1, 104))`` fails.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    # seq=1 is committed by start_run (run.requested).

    stream_result: dict[str, Any] = {}
    stream_exc: list[BaseException] = []

    def _read() -> None:
        try:
            status, _, raw = _stream_request(api_server, f"/runs/{run_id}/events/stream")
            stream_result["status"] = status
            stream_result["raw"] = raw
        except BaseException as exc:  # noqa: BLE001
            stream_exc.append(exc)

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()

    # Allow the stream to open and poll at least once (seq=1 is already visible).
    time.sleep(0.5)

    # Commit READ_LIMIT + 1 non-terminal events (seqs 2–102) and a terminal
    # event (seq 103) so the generator must page across two batches:
    #   batch 1: seqs 1–100  (READ_LIMIT events from cursor 0)
    #   batch 2: seqs 101–103 (including terminal)
    terminal_seq = 2 + READ_LIMIT + 1  # 103
    with owner_conn.transaction():
        for seq in range(2, terminal_seq):
            owner_conn.execute(
                "INSERT INTO events (run_id, seq, type, step_id, principal) "
                "VALUES (%s, %s, 'step.noted', NULL, 'worker')",
                (UUID(run_id), seq),
            )
        owner_conn.execute(
            "INSERT INTO events (run_id, seq, type, step_id, principal) "
            "VALUES (%s, %s, 'run.completed', NULL, 'worker')",
            (UUID(run_id), terminal_seq),
        )
        owner_conn.execute(
            "UPDATE runs SET state = 'completed' WHERE run_id = %s",
            (UUID(run_id),),
        )
    # Commit makes rows durable and visible to the stream's separate connections.
    owner_conn.commit()

    thread.join(timeout=30)
    assert not thread.is_alive(), (
        "stream did not close within 30 s; "
        "likely hung on a missing cursor advance or page boundary"
    )
    assert not stream_exc, f"stream raised: {stream_exc[0]}"
    assert stream_result.get("status") == 200

    blocks = _blocks(stream_result["raw"])
    seqs = [int(block["id"]) for block in blocks]
    expected = list(range(1, terminal_seq + 1))
    assert seqs == expected, (
        f"expected seqs 1–{terminal_seq} ({len(expected)} events), "
        f"got {len(seqs)} events; first diff at index "
        f"{next((i for i, (a, b) in enumerate(zip(seqs, expected, strict=False)) if a != b), len(seqs))}"  # noqa: E501
    )
    assert blocks[-1]["data"]["type"] == "run.completed"


def test_stream_validates_run_existence_before_opening(api_server: Client) -> None:
    status, _, _ = _stream_request(
        api_server, "/runs/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/events/stream"
    )

    assert status == 404


def test_stream_releases_connection_on_disconnect(
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """Stream route must not hold a database connection for the stream's lifetime.

    The route validates run existence and cursor on a short-lived connection
    that is released before the StreamingResponse is returned.  A
    generator-dependency connection (``conn: Conn``) would be held open
    until the response completes — which for a non-terminal run is never —
    leaving the connection idle in transaction.

    This check opens a raw socket to the stream endpoint, reads the response
    headers to confirm streaming started, then — **before closing the socket**
    — samples ``pg_stat_activity`` for ``app_api`` connections in state
    ``idle in transaction``.  Under the green code the validation connection
    is released before headers are sent, so the count is 0.  Under the break
    (``conn: Conn`` as a FastAPI dependency) the connection is held for the
    stream's lifetime and appears in the sample while the socket is open.

    Mutation: revert the fix by restoring ``conn: Conn`` as a parameter to
    ``stream_events`` and using it for ``_require_run`` and
    ``highest_committed_seq``.  Run this check three times under the break
    and three times green to confirm: break always shows 1 idle-in-transaction
    connection while the socket is open; green always shows 0.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    # Open a raw TCP connection to the stream endpoint and disconnect before
    # any terminal event is committed.
    parsed = urllib.parse.urlparse(api_server.base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80

    sock = socket.create_connection((host, port), timeout=5)
    try:
        sock.sendall(
            (
                f"GET /runs/{run_id}/events/stream HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
        )
        # Read until the response headers arrive to confirm streaming started.
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        assert b"200" in buf, f"Expected 200 response, got: {buf[:200]!r}"

        # Brief settle so uvicorn has finished its internal setup and the
        # connection is in its steady streaming state (polling, no active query).
        time.sleep(0.1)

        # Sample pg_stat_activity while the socket is still open.
        # Under the green code the validation connection is released before
        # headers are sent: count is 0.  Under the break (generator-dependency
        # connection) the connection is held idle in transaction for the
        # stream's lifetime: count is 1 while the socket is open.
        row = owner_conn.execute(
            """
            SELECT count(*)
            FROM pg_stat_activity
            WHERE usename = 'app_api'
              AND state = 'idle in transaction'
            """,
        ).fetchone()
        assert row is not None
        count = int(row[0])
        assert count == 0, (
            f"Stream route leaked {count} idle-in-transaction connection(s) "
            "while the socket was open. "
            "Validate run and cursor on a short-lived connection released before "
            "StreamingResponse is returned, not via a generator dependency."
        )
    finally:
        sock.close()
