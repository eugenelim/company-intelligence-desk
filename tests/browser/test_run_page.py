"""Browser evidence for the run event surface."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from tests.api.conftest import Client

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
Browser = Any
BrowserContext = Any
Page = Any

pytestmark = pytest.mark.substrate

# Path to axe-core's minified bundle, installed as a dev dependency of the
# browser manifest.  Injected via page.add_script_tag before each scan.
_AXE_MIN_JS = (
    Path(__file__).parents[2]
    / "src"
    / "ced"
    / "api"
    / "ui"
    / "node_modules"
    / "axe-core"
    / "axe.min.js"
)

#: The axe-core tags for every WCAG 2.0, 2.1 and 2.2 Level A and AA rule —
#: the conformance levels AC-0337 names.
_WCAG_A_AA_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa")


def _scan_wcag_a_aa(page: Page, label: str) -> None:
    """Assert no WCAG 2.2 A or AA violation, evaluating **every** A/AA-tagged rule.

    A bare ``axe.run()`` is not that scan. It evaluates the *enabled,
    non-experimental* default set, and in axe-core 4.10.3 eight A/AA-tagged
    rules fall outside it: ``aria-roledescription``, ``audio-caption`` and
    ``target-size`` (WCAG 2.2 AA 2.5.8) ship ``enabled: false``, and
    ``css-orientation-lock``, ``label-content-name-mismatch``, ``p-as-heading``,
    ``table-fake-caption`` and ``td-has-header`` are tagged ``experimental``.
    An explicit ``runOnly`` rule list overrides both exclusions, so every rule
    carrying an A/AA tag runs — and no best-practice rule does, so a hit here
    is a WCAG A/AA hit and the message can say so.

    **The evaluated-rule count is asserted, not assumed.** If a future axe
    release skipped an A/AA rule even when listed, the scan would quietly
    cover less than AC-0337 claims; comparing the rules axe reports having
    evaluated against the A/AA rules it registers turns that into a failure.
    """
    result: dict[str, Any] = page.evaluate(
        """async (tags) => {
            const ids = axe.getRules()
                .filter((rule) => rule.tags.some((tag) => tags.includes(tag)))
                .map((rule) => rule.ruleId);
            const res = await axe.run({ runOnly: { type: "rule", values: ids } });
            const evaluated = new Set(
                [...res.passes, ...res.violations, ...res.incomplete, ...res.inapplicable]
                    .map((rule) => rule.id),
            );
            return {
                expected: ids.length,
                unevaluated: ids.filter((id) => !evaluated.has(id)),
                violations: res.violations.map((v) => ({
                    id: v.id, impact: v.impact, description: v.description,
                })),
            };
        }""",
        list(_WCAG_A_AA_TAGS),
    )
    assert result["unevaluated"] == [], (
        f"{label} state: axe registered {result['expected']} WCAG A/AA rules but did "
        f"not evaluate {result['unevaluated']}; the scan covers less than AC-0337 claims"
    )
    violations: list[dict[str, Any]] = result["violations"]
    assert violations == [], f"WCAG 2.2 A/AA violations in {label} state:\n" + "\n".join(
        f"  [{v['impact']}] {v['id']}: {v['description']}" for v in violations
    )


def _parse_rgba(css: str) -> tuple[int, int, int, float] | None:
    """Extract (r, g, b, alpha) from a CSS rgb()/rgba() string. Alpha defaults to 1."""
    m = re.search(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s]+([\d.]+))?\s*\)", css)
    if m:
        a = float(m.group(4)) if m.group(4) else 1.0
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), a)
    return None


def _composite_over(
    fg: tuple[int, int, int, float], bg: tuple[int, int, int]
) -> tuple[int, int, int]:
    """Alpha-composite an rgba foreground over an opaque RGB background."""
    r, g, b, a = fg
    br, bg_, bb = bg
    return (
        round(a * r + (1.0 - a) * br),
        round(a * g + (1.0 - a) * bg_),
        round(a * b + (1.0 - a) * bb),
    )


def _relative_luminance(r: int, g: int, b: int) -> float:
    """Compute WCAG relative luminance of an opaque sRGB colour."""

    def f(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast_ratio(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Compute WCAG contrast ratio between two opaque RGB colours."""
    L1 = _relative_luminance(*c1)
    L2 = _relative_luminance(*c2)
    lighter = max(L1, L2)
    darker = min(L1, L2)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    # Module scope (not session) ensures sync_playwright()'s internal asyncio
    # event loop is stopped when the browser test module finishes.  A session-
    # scoped manager leaves the loop running on the main thread for the rest of
    # the session, which causes asyncio.run() in later suites to raise
    # RuntimeError: cannot be called from a running event loop.
    with playwright.sync_playwright() as manager:
        browser = manager.chromium.launch()
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def browser_context(browser: Browser) -> Iterator[BrowserContext]:
    context = browser.new_context()
    try:
        yield context
    finally:
        context.close()


@pytest.fixture
def page(browser_context: BrowserContext) -> Iterator[Page]:
    page = browser_context.new_page()
    try:
        yield page
    finally:
        page.close()


def _event(run_id: str, seq: int, event_type: str, **overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "seq": seq,
        "type": event_type,
        "principal": "operator",
        "step_id": None,
        "agent_role": None,
        "payload_ref": None,
        "idempotency_key": None,
    }
    event.update(overrides)
    return event


def _sse(event: dict[str, object], *, retry_ms: int = 1) -> str:
    """Encode one frame exactly as ``ced.api.stream.encode_sse_event`` does.

    No ``event:`` field: the committed type travels in the JSON envelope, which
    is what lets the client's single ``onmessage`` handler see every type.  The
    ``retry:`` field is the test harness's own, setting the browser's
    reconnection delay; the shipped encoder does not emit it.
    """
    return f"retry: {retry_ms}\nid: {event['seq']}\ndata: {json.dumps(event)}\n\n"


def test_eventsource_resumes_after_forced_disconnects(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """AC-0305: 100 forced disconnects with concurrent writer, tab reload, and sleep.

    Proved claims:
    - Wire: native reconnects carry Last-Event-ID (EventSource header precedence).
      The URL keeps a deliberately stale after=0; Last-Event-ID from the native
      transport takes precedence and is captured at a real HTTP server.
      (Playwright's route.request.headers does not expose Last-Event-ID — it is
      set by the browser's native EventSource, not the page script, and is
      filtered before reaching the CDP route handler.  A real TCP server sees it.)
    - Wire: stale after=0 is preserved on the URL across all reconnects.
    - Sink: no event is missed or reapplied after all forced disconnects.
    - Concurrent writer: the mini server receives events from the queue while
      the browser is already streaming the initial events.
    - Tab reload: page.reload() resets the EventSource session; the first
      post-reload successful connection has no Last-Event-ID (new session).
    - Simulated sleep: visibilitychange to hidden does not break continuity.

    Mutations (each must make this check red):
    - Remove ``id:`` field from ``_sse()`` → browser sends no Last-Event-ID →
      wire_captures[k] for k >= 1 is always None → AssertionError.
    - Replace ``retry: 1`` in ``_sse()`` with ``retry: 60000`` → reconnects
      take 60 s each → terminal event never arrives within 30 s → TimeoutError.

    Note: removing the ``addEvent`` deduplication guard does not red this check
    (the ledger records the reproduced witness);
    ``test_history_stream_overlap_renders_once`` covers deduplication
    deterministically.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    # All 101 stream events: seq 2..102, last is run.completed.
    all_stream_events: list[dict[str, object]] = [
        _event(
            run_id,
            seq,
            "run.completed" if seq == 102 else "step.started",
            agent_role="coordinator",
        )
        for seq in range(2, 103)
    ]

    # Start with the first 40 events pre-populated.  The concurrent writer
    # adds events 41..102 to the queue while the browser is already streaming.
    event_queue: list[dict[str, object]] = list(all_stream_events[:40])

    # Track events delivered by the mini server.  The dynamic history mock
    # returns these after a tab reload so the App never misses pre-reload events.
    served_events: list[dict[str, object]] = []

    # Wire capture: one entry per *successful* serve.  Entries are the
    # Last-Event-ID header value seen at the mini server (None when absent —
    # initial connection and the first post-reload connection).  Empty-queue
    # responses (body "retry: 1\n\n") are NOT recorded.
    wire_captures: list[str | None] = []
    cap_lock = threading.Lock()

    def _writer() -> None:
        """Concurrent writer: feeds events to the queue while the browser streams."""
        for ev in all_stream_events[40:]:
            time.sleep(0.04)  # 40 ms between events (simulates commit latency)
            with cap_lock:
                event_queue.append(ev)

    api_origin = api_server.base_url  # e.g. http://127.0.0.1:PORT

    # Allocate a free port for the mini server.
    with socket.socket() as _s:
        _s.bind(("127.0.0.1", 0))
        mini_port = _s.getsockname()[1]

    class _SSEHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", api_origin)
            self.send_header("Access-Control-Allow-Headers", "Last-Event-ID, Cache-Control")
            self.send_header("Access-Control-Allow-Methods", "GET")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            # The mini server receives the REAL HTTP request from the browser,
            # so Last-Event-ID is visible here (unlike Playwright route handlers,
            # which receive a filtered copy of the headers).
            raw = self.headers.get("Last-Event-ID") or self.headers.get("last-event-id") or None

            event: dict[str, object] | None = None
            with cap_lock:
                if event_queue:
                    wire_captures.append(raw)
                    event = event_queue.pop(0)
                    served_events.append(event)

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self._cors()
            self.end_headers()
            try:
                if event is None:
                    # Queue temporarily empty (writer catching up).  Return a
                    # valid SSE response that sets retry to 1 ms and carries no
                    # id: field.  The EventSource reconnects in 1 ms, preserving
                    # its current last-event-id.  Returning 503 here would cause
                    # Chromium's EventSource to "fail the connection" permanently
                    # rather than retrying; 200/text-event-stream avoids that.
                    self.wfile.write(b"retry: 1\n\n")
                else:
                    self.wfile.write(_sse(event).encode())
                self.wfile.flush()
            except OSError:
                pass

    mini_server = ThreadingHTTPServer(("127.0.0.1", mini_port), _SSEHandler)
    mini_thread = threading.Thread(target=mini_server.serve_forever, daemon=True)
    mini_thread.start()

    writer_thread = threading.Thread(target=_writer, daemon=True)
    writer_thread.start()

    # Dynamic history mock: returns event 1 plus all events already delivered
    # by the mini server.  After a tab reload the browser re-fetches history;
    # this ensures no events served before the reload are lost from the sink.
    def history(route: Any) -> None:
        with cap_lock:
            delivered = list(served_events)
        history_events = [_event(run_id, 1, "run.requested")] + delivered
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": history_events}),
        )

    def stream(route: Any) -> None:
        # Forward to the mini server.  The mini server sees the REAL request
        # headers (including Last-Event-ID) and responds with one SSE event per
        # connection (forced disconnect).
        route.continue_(url=f"http://127.0.0.1:{mini_port}/stream")

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    # Let the browser stream some of the initial events before simulating sleep.
    page.wait_for_timeout(500)

    # Simulated sleep: dispatch visibilitychange to hidden.  The EventSource
    # should not break when the tab is backgrounded.
    page.evaluate("document.dispatchEvent(new Event('visibilitychange', {bubbles: true}))")
    page.wait_for_timeout(300)

    # Tab reload: the browser reinitializes, refetches history (which now
    # includes all events served so far), and opens a new EventSource session.
    # The new EventSource has no Last-Event-ID, so the first post-reload
    # successful serve is the reload boundary marker (None in wire_captures).
    page.reload()

    # Wait for the terminal event to confirm all 101 stream events arrived.
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=30000)

    sequence_text = page.locator(".seq").all_inner_texts()
    observed = [int(text.removeprefix("#")) for text in sequence_text]
    assert observed == list(range(1, 103)), (
        f"Sink has {len(observed)} events, expected 102. "
        f"Missing: {set(range(1, 103)) - set(observed)}"
    )
    assert page.locator(".seq").count() == len(set(observed))

    # Wire assertion: prove Last-Event-ID header precedence independently of
    # client-side deduplication.
    #
    # wire_captures[k] is the Last-Event-ID header on the k-th *successful*
    # connection.  served_events[k] is the event served on that connection.
    #
    # Invariants:
    #   wire_captures[0]          == None   (initial connection — no prior id)
    #   wire_captures[reload_idx] == None   (new session after page.reload())
    #   wire_captures[k]          == str(served_events[k-1]['seq'])
    #                                       for k >= 1 and k != reload_idx
    #
    # The formula str(served_events[k-1]['seq']) holds even when empty-queue
    # responses intervene between k-1 and k: those responses carry no id:
    # field, so the EventSource preserves last-event-id from served_events[k-1]
    # through all empty-queue retries until the next successful serve.
    assert wire_captures[0] is None, "Initial connection must have no Last-Event-ID"

    reload_idx = next((i for i, v in enumerate(wire_captures) if i > 0 and v is None), None)
    assert reload_idx is not None, (
        "Expected a tab-reload boundary (a second None in wire captures). "
        "Did page.reload() run before the new session received its first event?"
    )

    for k in range(1, len(wire_captures)):
        if k == reload_idx:
            assert wire_captures[k] is None, f"Reload boundary at [{k}] should be None"
        else:
            expected = str(served_events[k - 1]["seq"])
            assert wire_captures[k] == expected, (
                f"wire_captures[{k}] = {wire_captures[k]!r}; "
                f"expected {expected!r} (seq of served_events[{k - 1}]). "
                "Native reconnects must carry the previous event's seq as Last-Event-ID."
            )

    try:
        mini_server.shutdown()
    finally:
        mini_server.server_close()


def test_unknown_event_type_is_rendered(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """AC-0304/AC-0305: one onmessage handler dispatches every frame type.

    The server sets no ``event:`` field, so every frame dispatches as a plain
    message and the client's single ``EventSource.onmessage`` handler reads the
    committed type out of the JSON envelope.  A type absent from any
    hand-written client list therefore still renders, and adding a new domain
    type to the server requires no client change.

    Mutation: restore the ``event:`` field in ``encode_sse_event`` and in
    ``_sse()``, and replace onmessage with per-type ``addEventListener``
    registrations enumerating every type except 'tool.invoked'.  That frame
    dispatches under its own name, no listener is registered for it, so it is
    silently dropped and the .type span carrying the text never appears.  This
    check then fails with a TimeoutError.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    def stream(route: Any) -> None:
        # Deliver an event whose type was absent from the old ALL_DOMAIN_EVENT_TYPES
        # enumeration, followed by a terminal event.
        body = _sse(_event(run_id, 2, "tool.invoked", step_id="step-1")) + _sse(
            _event(run_id, 3, "run.completed")
        )
        route.fulfill(status=200, content_type="text/event-stream", body=body)

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    # The unlisted type and the terminal event must both appear.
    expect(page.locator(".type", has_text="tool.invoked")).to_be_visible(timeout=5000)
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)


def test_stream_closes_after_terminal_event(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """AC-0304: after the terminal event the stream closes and does not reconnect.

    The terminal arm of onmessage calls source.close(), which stops the native
    transport from reconnecting.  No further stream request is issued.

    Mutation: remove ``source.close()`` from the terminal arm of onmessage in
    App.tsx and rebuild.  The EventSource stays open, so when the server closes
    the connection the native transport reconnects (``retry: 1``) and issues a
    second stream request.  This check then fails because stream_requests has
    more than one entry after the 500 ms observation window.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    stream_requests: list[str] = []

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    def stream(route: Any) -> None:
        stream_requests.append(route.request.url)
        event = _event(run_id, 2, "run.completed")
        route.fulfill(status=200, content_type="text/event-stream", body=_sse(event))

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)

    # Allow time for any spurious reconnect to manifest.
    page.wait_for_timeout(500)

    assert len(stream_requests) == 1, (
        f"Expected exactly one stream request after terminal event; "
        f"got {len(stream_requests)}.  The terminal arm did not close the stream."
    )


def test_external_values_never_create_markup_or_links(
    page: Any,
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """AC-0322: external values are rendered as literal text; the DOM sink class is clean.

    External event-envelope fields (principal, agent_role, payload_ref,
    idempotency_key) are rendered via React text interpolation only.  No member
    of the HTML-interpreting and link-constructing sink class — img, iframe,
    script, object, embed, svg, any anchor with href, or javascript: targets —
    appears in the event region, independent of what the fixture injected.

    Mutations (each must make this check red):
    - Replace {event.principal} with dangerouslySetInnerHTML and rebuild;
      inject '<iframe src="https://attacker.invalid"></iframe>' as principal.
      The iframe element appears in the event region → iframe count > 0 →
      AssertionError.
    - Inject '<img src=x onerror=alert(1)>' as principal with plain text
      rendering (existing check): the img element does not appear and this
      check stays green, confirming the existing img guard is independent.
    """
    created = api_server.post(
        "/runs",
        {"principal": "<strong>operator</strong>", "agent_role": "<em>coordinator</em>"},
    )
    run_id = created.body["run_id"]
    with owner_conn.transaction():
        owner_conn.execute(
            """
            INSERT INTO events (
                run_id, seq, type, step_id, principal, agent_role,
                payload_ref, idempotency_key
            )
            VALUES (
                %s, 2, 'step.started', NULL, %s, %s, %s, %s
            )
            """,
            (
                UUID(run_id),
                '<img src=x onerror=alert("principal")>',
                '<a href="https://attacker.invalid">role</a>',
                'payload:<script>alert("payload")</script>',
                'idem:<a href="https://attacker.invalid">key</a>',
            ),
        )
        owner_conn.execute(
            """
            INSERT INTO events (run_id, seq, type, step_id, principal)
            VALUES (%s, 3, 'run.completed', NULL, 'worker')
            """,
            (UUID(run_id),),
        )
        owner_conn.execute(
            "UPDATE runs SET state = 'completed' WHERE run_id = %s", (UUID(run_id),)
        )
    # `clean_runs` issues a SELECT on `owner_conn` before yielding, which starts
    # an implicit transaction.  `conn.transaction()` above therefore creates a
    # SAVEPOINT rather than a full BEGIN/COMMIT cycle.  The data is visible
    # within this connection but NOT to the API's separate connection until we
    # commit the outer transaction explicitly.
    owner_conn.commit()

    page.goto(f"{api_server.base_url}/runs/{run_id}")
    expect(page.get_by_text('<img src=x onerror=alert("principal")>')).to_be_visible()
    expect(page.get_by_text('<a href="https://attacker.invalid">role</a>')).to_be_visible()
    expect(page.get_by_text('payload:<script>alert("payload")</script>')).to_be_visible()
    expect(page.get_by_text('idem:<a href="https://attacker.invalid">key</a>')).to_be_visible()

    # Enumerate the HTML-interpreting and link-constructing sink class in the
    # event region, independent of the specific values the fixture injected.
    # A caller-controlled field rendered through any of these sinks would allow
    # markup injection or navigation.
    event_section = page.locator("#events")
    for sink in ("img", "iframe", "script", "object", "embed", "svg"):
        assert event_section.locator(sink).count() == 0, (
            f"found <{sink}> element in event region — external value reached a sink"
        )
    # No anchor with an href in the event region (caller-derived navigable target).
    assert event_section.locator("a[href]").count() == 0, (
        "found <a href> in event region — external value reached a navigable target"
    )
    # No javascript: scheme anywhere on the page.
    assert page.locator("[href^='javascript:']").count() == 0, (
        "found javascript: target — external value reached a script-execution sink"
    )


def test_applicable_state_matrix(page: Any, api_server: Client, clean_runs: None) -> None:
    """AC-0336: every applicable state-matrix row is driven to its visible outcome.

    States driven by this test:
    - Loading: the named "Loading committed events" status and the aria-busy
      row placeholders, while the first history fetch is delayed.
    - Unavailable: history returns 503; the error names the history request
      and exposes Retry.
    - Keyboard only: Retry is reached with Tab and invoked with Enter, which
      moves the page out of Unavailable.
    - Waiting: history returns only run.requested; the run-identity heading
      names the run and the page says it is waiting for work.
    - Offline: browser reports loss of network from Waiting state (non-terminal);
      existing rows remain; offline status and retry control visible.
    - Streaming: stream delivers step.started followed by run.completed; event
      rows appear and persist through terminal state.
    - Terminal: stream delivers run.completed; stream closes.

    Offline is driven from Waiting (non-terminal) rather than after Terminal
    because a terminal run outranks Offline: the page keeps the terminal
    heading and suppresses the Retry control.  A separate check,
    ``test_offline_after_terminal_keeps_terminal``, proves the guard.

    Reconnecting is not driven here because the two-stream timing window is
    narrower than Playwright's polling resolution.  It is proved fully by the
    standalone ``test_reconnecting_status_is_announced`` check, which holds the
    reconnecting state open with an SSE ``retry:`` window.  The Streaming focus
    stability assertion is proved by ``test_streaming_does_not_move_keyboard_focus``.

    Keyboard-only focus visibility, High-zoom, and Reduced-motion are covered
    by ``test_accessibility_and_reflow``; invoking Retry without a pointer is
    driven here.  The Streaming cursor update is observed by
    ``test_streaming_state_is_scanned``, which holds Streaming open.

    The row list is derived from the spec's Browser Surface state matrix, not
    copied from this brief.

    The Loading delay is a ``window.fetch`` patch and stays one: the committed
    history load is an ordinary fetch.  The stream is not — an ``EventSource``
    request never passes through ``window.fetch`` — so Waiting is held by
    stashing the stream Route instead.

    Mutations (each must make this check red):
    - Replace the ``unavailable`` reducer arm with ``return state`` → "Run
      unavailable" heading never appears → AssertionError.
    - Remove ``aria-busy="true"`` from the loading skeleton in App.tsx →
      the locator ``[aria-busy='true']`` finds nothing → AssertionError.
    - Change ``labelFor("loading")`` to a different string → the "Loading
      committed events" heading never appears → AssertionError.
    - Render no placeholder rows (an empty map in the loading ``<ol>``) → the
      row count is 0, not 3 → AssertionError.  The ``aria-busy`` list check
      alone stays green under this break.
    - Bind Retry's handler to ``onPointerDown`` instead of ``onClick`` → Enter
      does not activate it, the page stays Unavailable → AssertionError.
    - Drop ``{runId}`` from the ``<h1>`` → the run-identity check fails.
    - Change ``labelFor("waiting")`` to a different string → "Waiting for worker
      events" heading never appears → AssertionError.
    - Drop the ``event`` case from the reducer (so only terminal events add rows)
      → step.started is never added to ``state.order`` → the ``.type`` span with
      "step.started" never appears in the event list → AssertionError.
    - Change ``labelFor("terminal", "run.completed")`` to return a different
      string → "Run completed" heading never appears → AssertionError.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    failed_once = False
    held_stream: list[Any] = []

    # Inject a 500 ms delay on the first history fetch so the Loading state
    # (aria-busy skeleton) is observable after page.goto() returns.  Without
    # the delay the history response may arrive before the assertion runs.
    page.add_init_script(
        """
        const _fetch = window.fetch;
        let _historyDelayed = false;
        window.fetch = function (url, ...args) {
          if (!_historyDelayed && typeof url === 'string' && url.includes('/events?')) {
            _historyDelayed = true;
            return new Promise(r => setTimeout(() => r(_fetch(url, ...args)), 500));
          }
          return _fetch(url, ...args);
        };
        """
    )

    def history(route: Any) -> None:
        if failed_once:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}
                ),
            )
        else:
            route.fulfill(status=503, content_type="application/json", body="{}")

    def stream(route: Any) -> None:
        # Stash the Route without handling it: the EventSource request stays
        # open, so Waiting persists until the test fulfills it below.
        held_stream.append(route)

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    # Drive: Loading — the skeleton with aria-busy="true" is visible while the
    # first history fetch is delayed by the injected script.
    expect(page.locator("[aria-busy='true']")).to_be_visible(timeout=2000)
    expect(page.get_by_role("heading", name="Loading committed events")).to_be_visible()
    # The placeholders are the rows themselves, a fixed set while loading lasts.
    # The list alone is not evidence: its top border keeps it visible when empty.
    expect(page.locator("[aria-busy='true'] > li.event-row.skeleton")).to_have_count(3)

    # Drive: Unavailable — the first history returns 503.  Spec state: "Error
    # names the failed action and exposes a retry control."  Break: replace the
    # history-failure message in App.tsx → the status text check fails.
    expect(page.get_by_role("heading", name="Run unavailable")).to_be_visible()
    expect(page.get_by_role("status")).to_contain_text("Event history returned 503")

    failed_once = True
    # Drive: Keyboard only — reach Retry with Tab (the skip link comes first)
    # and invoke it with Enter, with no pointer event at all.
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    focused = page.evaluate(
        "document.activeElement?.tagName + ':' + (document.activeElement?.textContent ?? '')"
    )
    assert focused == "BUTTON:Retry", f"Tab did not reach Retry; focused {focused!r}"
    page.keyboard.press("Enter")

    # Drive: Waiting — history returns only run.requested (one event; no worker
    # events).  Spec state: "Run identity remains visible and the page says it
    # is waiting for work."
    expect(page.get_by_role("heading", name="Waiting for worker events")).to_be_visible()
    expect(page.get_by_role("heading", level=1)).to_have_text(f"Run {run_id}")

    # Drive: Offline from Waiting (non-terminal) — browser reports network loss.
    # Spec state: existing rows remain; offline status and retry control visible.
    # Break: clear `events` and `order` in the offline reducer arm → the
    # already-rendered run.requested row disappears → the row check fails.
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    expect(page.locator(".type", has_text="run.requested")).to_be_visible()

    # The network comes back: Offline is lifted and the underlying state,
    # still Waiting on the held stream, is shown again.
    page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(page.get_by_role("heading", name="Waiting for worker events")).to_be_visible()

    # Drive: Streaming — release the latest held stream.  Both events go in one
    # body: step.started (non-terminal) is added to order; run.completed then
    # closes as terminal.  Both rows persist in the event list, so the assertion
    # does not depend on catching the brief streaming window.
    assert len(held_stream) >= 1, (
        f"expected at least one held stream request, got {len(held_stream)}"
    )
    held_stream[-1].fulfill(
        status=200,
        content_type="text/event-stream",
        body=_sse(_event(run_id, 2, "step.started", agent_role="coordinator"))
        + _sse(_event(run_id, 3, "run.completed")),
    )
    expect(page.locator(".type", has_text="step.started")).to_be_visible(timeout=5000)

    # Drive: Terminal — run.completed was delivered in the same stream body;
    # the page closes to terminal state.
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)


def test_reconnecting_status_is_announced(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """AC-0336: the Reconnecting state displays 'Reconnecting from last sequence'.

    The gate is the SSE ``retry:`` field, not a ``window.fetch`` patch: an
    ``EventSource`` request never passes through ``window.fetch``, so patching
    it cannot hold a stream open.  The first connection's frame sets
    ``retry: 2000``, so when the server closes that connection the browser
    waits two seconds before reconnecting.  The page sits in Reconnecting for
    that whole window, which is what the assertion observes.

    The live-region assertion confirms the ``role="status"`` paragraph includes
    the current status label, so the state change is announced to screen readers.

    Mutations:
    - Change labelFor('reconnecting') to return a different string in App.tsx
      and rebuild.  The heading never shows 'Reconnecting from last sequence'
      so the expect times out with a TimeoutError.
    - Move the status label out of the live region → the role="status" element
      no longer contains 'Reconnecting from last sequence' → AssertionError.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    connections = 0

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    def stream(route: Any) -> None:
        nonlocal connections
        connections += 1
        if connections == 1:
            # One non-terminal event, then close.  retry: 2000 holds the browser
            # in Reconnecting for two seconds before it dials again.
            event = _event(run_id, 2, "step.started", agent_role="coordinator")
            route.fulfill(
                status=200, content_type="text/event-stream", body=_sse(event, retry_ms=2000)
            )
        else:
            # Terminal on the reconnect, so the source closes and the test ends.
            route.fulfill(
                status=200,
                content_type="text/event-stream",
                body=_sse(_event(run_id, 3, "run.completed")),
            )

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    expect(page.get_by_role("heading", name="Reconnecting from last sequence")).to_be_visible(
        timeout=5000
    )

    # The live region must include the status label so screen readers announce
    # the transition (a state change without new events would leave a count-only
    # region unchanged and therefore silent).
    expect(page.get_by_role("status")).to_contain_text("Reconnecting from last sequence")

    # Already-rendered events survive the reconnect (AC-0336's preservation clause).
    expect(page.locator(".type", has_text="step.started")).to_be_visible()

    # AC-0337 scan of the Reconnecting state.  It lives here rather than in
    # `test_accessibility_and_reflow` because this is the only check that holds
    # Reconnecting open — the `retry: 2000` window above.  Without it the state
    # is a supported one that no scan reaches, while the record claims every
    # supported state is scanned.
    assert _AXE_MIN_JS.is_file(), (
        f"axe-core not installed at {_AXE_MIN_JS}; run: cd src/ced/api/ui && npm ci"
    )
    page.add_script_tag(path=str(_AXE_MIN_JS))
    _scan_wcag_a_aa(page, "reconnecting")

    # The native transport reconnects on its own and the run reaches terminal.
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=10000)


def test_streaming_does_not_move_keyboard_focus(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """AC-0336: streaming events arrive without moving keyboard focus.

    The gate is the SSE ``retry:`` field, not a ``window.fetch`` patch: an
    ``EventSource`` request never passes through ``window.fetch``.  The first
    connection carries no event and sets ``retry: 2000``, so the browser holds
    off two seconds before dialling again — a window in which the test puts
    keyboard focus on the skip-link.  The second connection then delivers
    step.started and run.completed while that focus is held.

    Mutation: add ``(document.activeElement as HTMLElement | null)?.blur()`` to
    the non-terminal arm of onmessage in App.tsx and rebuild.  When an event
    arrives focus is dropped, so the final document.activeElement.className no
    longer equals the skip-link class and the assertion fails.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    connections = 0

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    def stream(route: Any) -> None:
        nonlocal connections
        connections += 1
        if connections == 1:
            # No event, and a two-second reconnection delay.  A retry-only frame
            # carries no id:, so the browser's last-event-id is untouched.
            route.fulfill(status=200, content_type="text/event-stream", body="retry: 2000\n\n")
        else:
            # Deliver a non-terminal event then terminal — one trip through
            # streaming, with focus already parked on the skip-link.
            body = _sse(_event(run_id, 2, "step.started", agent_role="coordinator")) + _sse(
                _event(run_id, 3, "run.completed")
            )
            route.fulfill(status=200, content_type="text/event-stream", body=body)

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    # The first connection delivered nothing and closed, so the page is holding
    # in Reconnecting for the two-second retry window.
    expect(page.get_by_role("heading", name="Reconnecting from last sequence")).to_be_visible(
        timeout=5000
    )

    # Set focus on the skip-link before any streaming event arrives.
    page.keyboard.press("Tab")
    focused_class_before = page.evaluate("document.activeElement?.className ?? ''")
    assert focused_class_before != "", "Tab did not focus a classed element; gate opened early"

    # The native transport reconnects on its own and delivers the events.
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=10000)
    expect(page.locator(".type", has_text="step.started")).to_be_visible()

    # Focus must not have moved during streaming.
    focused_class_after = page.evaluate("document.activeElement?.className ?? ''")
    assert focused_class_before == focused_class_after, (
        f"Keyboard focus moved during streaming: "
        f"was {focused_class_before!r}, now {focused_class_after!r}"
    )


def test_accessibility_and_reflow(page: Any, api_server: Client, clean_runs: None) -> None:
    """AC-0337: no WCAG 2.2 A/AA violation in each supported state this check holds.

    Also covers: visible focus, focus ring contrast ≥ 3:1 (WCAG 1.4.11),
    status semantics, reflow at narrow width, and reduced-motion guard.

    ``_scan_wcag_a_aa`` runs once per state, in this order: loading,
    unavailable (with the Retry button), waiting, offline (with the Retry
    button, from a non-terminal state), and terminal. Each scan evaluates
    every A/AA-tagged axe rule, not axe's default set; see that helper's
    docstring. The sixth supported state, reconnecting, is scanned in
    ``test_reconnecting_status_is_announced``, the only check that holds it.
    This check has no Streaming scan: here step.started and run.completed
    arrive in one SSE body, so the page passes through Streaming without
    resting there. ``test_streaming_state_is_scanned`` owns that scan; it holds
    Streaming open on the real routes.

    Offline is driven from Waiting (non-terminal) so that the Retry control is
    visible during the scan.  A terminal run guards the offline transition;
    ``test_offline_after_terminal_keeps_terminal`` proves that guard.

    The first history request's Route is stashed, which holds the page in
    loading for its scan; releasing it as a 503 drives the page to unavailable.
    The stream route handler stashes its Route without handling it, so the
    EventSource request stays open and the waiting state persists for its scan.
    After the test fires ``online`` and fulfills the stream held since the
    Retry that moved Unavailable to Waiting, the stream delivers step.started
    and run.completed in one body.
    step.started persists in the event list after terminal closes, so the
    terminal scan observes the event-list DOM reliably.

    Mutations (each must make this check red).  Every entry states the
    mechanism actually observed; the verification ledger's § Post-gates review
    round 3 carries the witnesses:
    - Suppress every focus indicator, author and user-agent —
      ``*:focus-visible { outline: 0 !important; box-shadow: none !important; }``
      → the computed-style read below reports ``box-shadow='none'``,
      ``outline='none' '0px'`` → AssertionError.  Deleting only the author
      ``box-shadow: var(--ds-focus-ring)`` rule does **not** red this check,
      and should not: that rule carries ``outline: 0.125rem solid transparent``,
      so removing it restores Chromium's own ring and the element still paints
      an indicator.
    - Restore the 45 % alpha on ``--ds-focus-ring`` → the composited ring
      falls below 3:1 contrast → AssertionError on the contrast check.
    - Remove ``role="status"`` / ``aria-live="polite"`` from the status
      paragraph → the ``expect(page.get_by_role("status"))`` below fails with
      ``Locator expected to be visible``.  No axe scan reports it: execution
      stops at that failing expectation, which precedes the terminal scan.
    - Remove ``@media (prefers-reduced-motion: no-preference)`` guard from the
      transition rule → transition_count rises to 1 → AssertionError.
    - Add ``<img src="" />`` without ``alt`` to App.tsx and rebuild → axe
      catches ``image-alt`` violation → AssertionError on violations.
    - Add an unlabelled ``<button>`` to the unavailable-state branch in
      App.tsx and rebuild → axe catches the unlabelled control in the
      unavailable state scan → AssertionError.  If the scan ran only in the
      waiting state (where the unlabelled button is hidden), this violation
      would not be found — the per-state scan is what makes it detectable.
    - The same unlabelled ``<button>`` in the loading branch only →
      ``WCAG 2.2 A/AA violations in loading state`` → AssertionError.
    - Revert ``_scan_wcag_a_aa`` to a bare ``axe.run()`` → its completeness
      assertion fails naming the eight A/AA rules axe's default set skips.

    Remaining gaps not covered by the automated scan (per AC-0314 residuals):
    - Color-contrast correctness depends on computed styles in a rendered
      viewport.  Headless Chromium resolves colors but may differ from a
      hardware-accelerated display context.
    - Keyboard interaction beyond Tab focus order (e.g. custom key bindings).
    - Screen-reader announcement timing (aria-live polling is asynchronous
      and not observable via DOM inspection alone).
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    assert _AXE_MIN_JS.is_file(), (
        f"axe-core not installed at {_AXE_MIN_JS}; run: cd src/ced/api/ui && npm ci"
    )

    failed_once = False
    # Gate: the stream route handler stashes its Route and returns without
    # handling it, so the EventSource request stays open and the page holds in
    # Waiting until the test fulfills the stashed Route.  Blocking inside the
    # handler instead would stall Playwright's own event loop — measured at the
    # gate's full timeout every run — and gate nothing.
    held_stream: list[Any] = []
    # The very first history request is held the same way, which is what holds
    # the page in Loading long enough to scan it.  Loading is an applicable row
    # of the state matrix, so AC-0337's "supported states" includes it.
    held_history: list[Any] = []

    def history(route: Any) -> None:
        if not failed_once and not held_history:
            held_history.append(route)
            return
        if failed_once:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}
                ),
            )
        else:
            route.fulfill(status=503, content_type="application/json", body="{}")

    def stream(route: Any) -> None:
        held_stream.append(route)

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    # Inject axe-core once; it remains available for all subsequent evaluate calls.
    page.add_script_tag(path=str(_AXE_MIN_JS))

    def _scan(label: str) -> None:
        _scan_wcag_a_aa(page, label)

    # Scan: Loading state — the history request is held, so the aria-busy
    # skeleton stands still for the scan.  Then release it as a 503, which is
    # what drives the page on to Unavailable.
    expect(page.locator("[aria-busy='true']")).to_be_visible()
    _scan("loading")
    assert len(held_history) == 1, f"expected one held history request, got {len(held_history)}"
    held_history[0].fulfill(status=503, content_type="application/json", body="{}")

    # Scan: Unavailable state (Retry button visible — interactive control that
    # could be unlabelled).
    expect(page.get_by_role("heading", name="Run unavailable")).to_be_visible()
    _scan("unavailable")

    # Transition to Waiting state; the stashed Route holds the stream open so
    # the waiting state persists until the test fulfills it.
    failed_once = True
    page.get_by_role("button", name="Retry").click()
    expect(page.get_by_role("heading", name="Waiting for worker events")).to_be_visible()
    _scan("waiting")

    # Scan: Offline from Waiting (non-terminal) — the Retry control appears.
    # A terminal run guards this transition; ``test_offline_after_terminal_keeps_terminal``
    # proves the guard.
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()
    _scan("offline")

    # The network comes back: the page shows Waiting again on the held stream.
    page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(page.get_by_role("heading", name="Waiting for worker events")).to_be_visible()

    # Release the gate.  Both events go in one body: step.started (non-terminal)
    # followed by run.completed (terminal), so the terminal scan below runs with
    # both rows rendered.
    assert len(held_stream) >= 1, (
        f"expected at least one held stream request, got {len(held_stream)}"
    )
    held_stream[-1].fulfill(
        status=200,
        content_type="text/event-stream",
        body=_sse(
            _event(
                run_id,
                2,
                "step.started",
                agent_role="coordinator",
                # The shape `write_payload_bytes` actually emits:
                # `<OWNER_SCOPE>/<sha256 hex>`, 83 characters whose 64-character
                # digest is an unbreakable run (see
                # src/ced/adapters/objectstore/client.py).  The length is what
                # makes the reflow assertion below load-bearing, not the field's
                # escaping: with ordinary short values the browser always has a
                # word boundary to break at, so deleting every wrapping rule
                # still produces no horizontal overflow at 640 px and the check
                # could not red.  Using the production shape rather than a
                # longer synthetic token means the break is proved at the length
                # the system really produces.
                payload_ref="ced-step-lifecycle/" + "a1b2c3d4" * 8,
            )
        )
        + _sse(_event(run_id, 3, "run.completed")),
    )

    # step.started persists in terminal state so the event-list DOM is stable.
    expect(page.locator(".type", has_text="step.started")).to_be_visible(timeout=5000)

    # Scan: Terminal state.
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)
    _scan("terminal")

    # Keyboard focus check (run after WCAG scans, before viewport and motion changes).
    expect(page.get_by_role("main")).to_be_visible()
    expect(page.get_by_role("status")).to_be_visible()
    page.keyboard.press("Tab")
    assert page.locator(":focus-visible").count() == 1

    # `:focus-visible` is a user-agent state, not an author style: it matches
    # with every author rule removed, so counting it cannot establish that a
    # focus indicator is *visible*.  Read the indicator actually painted on the
    # focused element instead.  What reds this is the absence of any indicator,
    # author or user-agent — see the docstring's mutation list; deleting the
    # author `box-shadow: var(--ds-focus-ring)` rule alone does not, because
    # that rule carries `outline: 0.125rem solid transparent` and removing it
    # restores Chromium's ring.
    indicator = page.evaluate(
        """() => {
            const el = document.activeElement;
            if (!el || el === document.body) return null;
            const style = getComputedStyle(el);
            return {
              shadow: style.boxShadow,
              outlineStyle: style.outlineStyle,
              outlineWidth: style.outlineWidth,
            };
        }"""
    )
    assert indicator is not None, "Tab moved focus to no element"
    painted_shadow = indicator["shadow"] not in ("none", "")
    painted_outline = indicator["outlineStyle"] not in ("none", "") and indicator[
        "outlineWidth"
    ] not in ("0px", "")
    assert painted_shadow or painted_outline, (
        "the focused element paints no focus indicator: "
        f"box-shadow={indicator['shadow']!r}, "
        f"outline={indicator['outlineStyle']!r} {indicator['outlineWidth']!r}. "
        "AC-0337 requires a visible keyboard focus indicator"
    )

    # Focus ring contrast ≥ 3:1 (WCAG 1.4.11).
    # Read the ring colour from box-shadow and composite it over the element's
    # backdrop.  A semi-transparent ring may fall below 3:1; the fix uses the
    # opaque --ds-color-accent token.
    # Break: restore the 45 % alpha on --ds-focus-ring → composited ring is
    # 2.07:1 against the canvas → contrast < 3.0 → AssertionError.
    assert painted_shadow, (
        "the focus ring is the author box-shadow; its contrast cannot be read without it"
    )
    backdrop_css = page.evaluate(
        """() => {
            let node = document.activeElement?.parentElement;
            while (node) {
                const bg = getComputedStyle(node).backgroundColor;
                if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg;
                node = node.parentElement;
            }
            return getComputedStyle(document.documentElement).backgroundColor;
        }"""
    )
    ring_rgba = _parse_rgba(indicator["shadow"])
    bg_rgba = _parse_rgba(backdrop_css or "")
    assert ring_rgba is not None, (
        f"could not parse the ring colour from {indicator['shadow']!r}"
    )
    assert bg_rgba is not None, f"could not parse the backdrop colour {backdrop_css!r}"
    bg_rgb = (bg_rgba[0], bg_rgba[1], bg_rgba[2])
    ring_rgb = (
        _composite_over(ring_rgba, bg_rgb)
        if ring_rgba[3] < 1.0
        else (ring_rgba[0], ring_rgba[1], ring_rgba[2])
    )
    contrast = _contrast_ratio(ring_rgb, bg_rgb)
    assert contrast >= 3.0, (
        f"Focus ring contrast {contrast:.2f}:1 is below the WCAG 1.4.11 minimum "
        f"of 3:1. Ring: rgba{ring_rgba}, backdrop: {backdrop_css!r}. "
        "Set --ds-focus-ring to use the opaque --ds-color-accent token."
    )

    # Reflow at narrow width — no horizontal page scroll at 640 px.
    page.set_viewport_size({"width": 640, "height": 720})
    overflow = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert overflow is False

    # Reduced motion — no unguarded CSS transitions.
    page.emulate_media(reduced_motion="reduce")
    transition_count = page.evaluate(
        """
        [...document.styleSheets].flatMap((sheet) => [...sheet.cssRules])
          .filter((rule) => rule.cssText.includes("transition"))
          .filter((rule) => !rule.cssText.includes("prefers-reduced-motion: no-preference"))
          .length
        """
    )
    assert transition_count == 0


def test_forced_colors_focus_outline(
    browser: Browser,
    api_server: Client,
    clean_runs: None,
) -> None:
    """Focus outline is visible in forced-colors (high-contrast) mode (AC-0337).

    In forced-colors mode the browser ignores box-shadow, so the focus ring
    must rely on an outline.  ``outline: 0.125rem solid transparent`` provides
    a non-zero solid outline that the browser paints using the system
    ``ButtonText`` or ``Highlight`` colour.  ``outline: 0`` gives a zero-width
    outline that disappears even in forced-colors mode.

    Mutation: restore ``outline: 0`` in the focus rule in styles.css and
    rebuild → in forced-colors mode the focused element's computed
    outlineStyle is 'none' and outlineWidth is '0px' → AssertionError.
    """
    context = browser.new_context(forced_colors="active")
    page = context.new_page()
    try:
        created = api_server.post(
            "/runs", {"principal": "operator", "agent_role": "coordinator"}
        )
        run_id = created.body["run_id"]

        def history(route: Any) -> None:
            # Serve 503 so the Retry button appears (Unavailable state).
            route.fulfill(status=503, content_type="application/json", body="{}")

        page.route(f"**/runs/{run_id}/events?after=0", history)
        page.goto(f"{api_server.base_url}/runs/{run_id}")

        expect(page.get_by_role("heading", name="Run unavailable")).to_be_visible(timeout=5000)

        def _outline_for_focused() -> dict[str, str] | None:
            return page.evaluate(
                """() => {
                    const el = document.activeElement;
                    if (!el || el === document.body) return null;
                    const s = getComputedStyle(el);
                    return { style: s.outlineStyle, width: s.outlineWidth };
                }"""
            )

        # Tab once: focus lands on the skip link (first interactive element).
        page.keyboard.press("Tab")
        skip_outline = _outline_for_focused()
        assert skip_outline is not None, "Tab did not focus any element"
        assert skip_outline["style"] != "none", (
            f"Skip link outline style is 'none' in forced-colors mode "
            f"(width={skip_outline['width']!r}). AC-0337 requires a visible focus indicator."
        )
        assert skip_outline["width"] not in ("0px", ""), (
            f"Skip link outline width is zero in forced-colors mode "
            f"(style={skip_outline['style']!r})."
        )

        # Tab again: focus lands on the Retry button.
        page.keyboard.press("Tab")
        retry_outline = _outline_for_focused()
        assert retry_outline is not None, "Second Tab did not focus any element"
        assert retry_outline["style"] != "none", (
            f"Retry button outline style is 'none' in forced-colors mode "
            f"(width={retry_outline['width']!r}). AC-0337 requires a visible focus indicator."
        )
        assert retry_outline["width"] not in ("0px", ""), (
            f"Retry button outline width is zero in forced-colors mode "
            f"(style={retry_outline['style']!r})."
        )
    finally:
        page.close()
        context.close()


def test_closed_stream_shows_unavailable(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """A permanently failed stream shows Unavailable with a Retry button (AC-0336).

    When the EventSource receives a non-200 response Chromium closes the
    connection (readyState becomes CLOSED).  The onerror handler detects this
    and dispatches 'unavailable' so the Retry control appears.  Without the
    guard it would dispatch 'reconnecting' and the page would show the
    Reconnecting heading with no way to recover.

    The Unavailable row also requires that the error names the failed action,
    and AC-0336 that an error state keeps the rows already rendered, so both
    are asserted: the status names the stream request, and the run.requested
    row from history is still shown.

    Mutations:
    (a) Make ``source.onerror`` unconditionally dispatch ``reconnecting``
        regardless of ``readyState`` → the page shows 'Reconnecting from last
        sequence' instead of 'Run unavailable' → AssertionError.
    (b) Replace the closed-stream message with one that names no request →
        the status text check fails.
    (c) Clear ``events`` and ``order`` in the ``unavailable`` reducer arm →
        the row check fails.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    def stream(route: Any) -> None:
        # Non-200 response causes Chromium EventSource to set readyState=CLOSED.
        route.fulfill(status=503, content_type="application/json", body="{}")

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    expect(page.get_by_role("heading", name="Run unavailable")).to_be_visible(timeout=5000)
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    expect(page.get_by_role("status")).to_contain_text("Stream request failed")
    expect(page.locator(".type", has_text="run.requested")).to_be_visible()
    # Reconnecting heading must not appear.
    assert page.get_by_role("heading", name="Reconnecting from last sequence").count() == 0


def test_live_region_announces_terminal_outcome(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """The live region names the terminal outcome, not a generic label (AC-0336).

    For a run.failed terminal event the heading and live region must both show
    'Run failed', not 'Terminal event received'.  This proves that the label is
    derived from the terminal event type, not from a fixed string.

    Mutations:
    (a) Move the label out of the live region → the role="status" element no
        longer contains 'Run failed' → AssertionError on to_contain_text.
    (b) Restore the fixed label 'Terminal event received' in labelFor →
        the heading and live region show that string → AssertionError on
        the heading name check and on to_contain_text.
    (c) Make ``statusClass`` return ``status-terminal-completed`` for every
        terminal type → the failed run's border resolves to the success
        colour → AssertionError on the colour check.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    def stream(route: Any) -> None:
        # Deliver a run.failed terminal event (not run.completed) to exercise
        # the outcome-specific label branch.
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=_sse(_event(run_id, 2, "run.failed")),
        )

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    expect(page.get_by_role("heading", name="Run failed")).to_be_visible(timeout=5000)
    # The live region must include the outcome label, not a generic placeholder.
    expect(page.get_by_role("status")).to_contain_text("Run failed")
    assert page.get_by_role("heading", name="Terminal event received").count() == 0

    # A failed run must not be painted in the success colour. The status bar's
    # computed border is compared with each token resolved in the same page.
    colours = page.evaluate(
        """() => {
            const resolve = (token) => {
                const probe = document.createElement("div");
                probe.style.color = `var(${token})`;
                document.body.append(probe);
                const value = getComputedStyle(probe).color;
                probe.remove();
                return value;
            };
            const section = document.getElementById("status-title").closest("section");
            return {
                border: getComputedStyle(section).borderInlineStartColor,
                success: resolve("--ds-color-success"),
                danger: resolve("--ds-color-danger"),
            };
        }"""
    )
    assert colours["border"] != colours["success"], (
        f"a run.failed status bar is painted in the success colour: {colours}"
    )
    assert colours["border"] == colours["danger"], (
        f"a run.failed status bar should use --ds-color-danger: {colours}"
    )


def test_offline_after_terminal_keeps_terminal(
    page: Any,
    api_server: Client,
    clean_runs: None,
) -> None:
    """Offline after terminal keeps the terminal heading and shows no Retry (AC-0336).

    A terminal run has no stream to lose, so an offline event must not replace
    the terminal heading with 'Browser is offline' or expose a Retry control
    that would reopen the closed stream.

    Mutation: drop Terminal's precedence from the render-time derivation of
    the shown state (show Offline whenever ``browserOffline`` is set) → the
    offline event replaces the terminal heading → red on the "Run completed"
    heading.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    def stream(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=_sse(_event(run_id, 2, "run.completed")),
        )

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")

    # Wait for terminal state.
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)

    # Dispatch offline after terminal, then let React commit the update before
    # reading the DOM: without the wait the reads below run against the
    # pre-update render and pass whether or not the guard exists.
    page.evaluate(
        """async () => {
            window.dispatchEvent(new Event("offline"));
            await new Promise((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(resolve))
            );
        }"""
    )

    # The page must keep the terminal heading; offline must not replace it.
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible()
    assert page.get_by_role("heading", name="Browser is offline").count() == 0, (
        "Offline after terminal replaced the terminal heading with 'Browser is offline'"
    )
    assert page.get_by_role("button", name="Retry").count() == 0, (
        "Retry appeared after offline in terminal state"
    )


def test_history_stream_overlap_renders_once(
    page: Any,
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """History-stream overlap on the real ced-api route: each event renders exactly once.

    The client fetches history (after=0) and then opens the stream at after=0
    with no ``Last-Event-ID``, so on a first connection the shipped stream
    route resends every event the history response already delivered. The
    ``addEvent`` duplicate guard in the reducer is what keeps each row single.

    Nothing is mocked. Seqs 1 and 2 are committed before the page loads, so
    history delivers them and the stream's first poll resends them; the
    terminal seq 3 is committed once the page is streaming. A history that
    already ended in a terminal event would open no stream at all, so the
    terminal must not be committed first. Whenever seq 3 lands relative to
    the stream's first poll, that poll reads from cursor 0 and resends 1 and
    2, so the overlap is deterministic.

    Mutation: remove the ``addEvent`` duplicate guard in App.tsx and rebuild
    → seqs 1 and 2, which history and the stream both delivered, render twice
    (``[1, 1, 2, 2, 3]``) → the sequence-order assertion fails.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    # seq 1 (run.requested) was committed by the POST; commit seq 2.
    with owner_conn.transaction():
        owner_conn.execute(
            """
            INSERT INTO events (
                run_id, seq, type, step_id, principal, agent_role,
                payload_ref, idempotency_key
            )
            VALUES (%s, 2, 'step.started', NULL, 'worker', 'coordinator', NULL, NULL)
            """,
            (UUID(run_id),),
        )
    # The fixture's implicit transaction makes the block above a savepoint;
    # commit so the API's own connections can read the rows.
    owner_conn.commit()

    page.goto(f"{api_server.base_url}/runs/{run_id}")
    expect(page.get_by_role("heading", name="Streaming committed events")).to_be_visible(
        timeout=5000
    )

    # Now the terminal seq 3, and mark the run completed, as the worker would.
    with owner_conn.transaction():
        owner_conn.execute(
            """
            INSERT INTO events (run_id, seq, type, step_id, principal)
            VALUES (%s, 3, 'run.completed', NULL, 'worker')
            """,
            (UUID(run_id),),
        )
        owner_conn.execute(
            "UPDATE runs SET state = 'completed' WHERE run_id = %s", (UUID(run_id),)
        )
    owner_conn.commit()

    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)

    seq_texts = page.locator(".seq").all_inner_texts()
    observed = [int(t.removeprefix("#")) for t in seq_texts]
    assert observed == list(range(1, 4)), f"Expected seqs [1, 2, 3], got {observed}"
    for seq in range(1, 4):
        count = observed.count(seq)
        assert count == 1, (
            f"seq #{seq} rendered {count} times (expected once). "
            "The addEvent deduplication guard must prevent stream events from duplicating "
            "events already loaded from history."
        )


def test_streaming_state_is_scanned(
    page: Any,
    api_server: Client,
    owner_conn: psycopg.Connection,
    clean_runs: None,
) -> None:
    """AC-0337: the Streaming state is scanned while it stands still.

    The real ``ced-api`` routes hold Streaming open without any gate: the run
    has two committed events and no terminal one, so history and stream both
    deliver them and the stream then stays open, polling for more. The page
    therefore rests in Streaming for as long as the check needs.

    The terminal event is committed at the end so the server's stream
    generator returns rather than polling an abandoned run until the API
    process exits.

    It also observes the Streaming row's other named outcomes: the rows are
    ordered, and the header cursor shows the last applied sequence and advances
    when the terminal event commits on the open stream.

    Mutations: freeze the reducer's ``cursor`` (keep ``state.cursor`` instead
    of ``Math.max(state.cursor, event.seq)``) → the cursor reads 0 → the
    cursor check fails.  Render an ``<img src="" />`` without ``alt`` only while
    ``state.connection === "streaming"`` in App.tsx and rebuild → the axe
    scan reports ``image-alt`` → AssertionError. A violation shown only in
    Streaming reds this check, so the scan observes that state and not a
    neighbouring one.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    with owner_conn.transaction():
        owner_conn.execute(
            """
            INSERT INTO events (
                run_id, seq, type, step_id, principal, agent_role,
                payload_ref, idempotency_key
            )
            VALUES (%s, 2, 'step.started', NULL, 'worker', 'coordinator', NULL, NULL)
            """,
            (UUID(run_id),),
        )
    owner_conn.commit()

    try:
        page.goto(f"{api_server.base_url}/runs/{run_id}")
        cursor = page.locator(
            ".summary div", has=page.locator("dt", has_text="Cursor")
        ).locator("dd")
        expect(page.get_by_role("heading", name="Streaming committed events")).to_be_visible(
            timeout=5000
        )
        expect(page.locator(".type", has_text="step.started")).to_be_visible()
        # Ordered rows and the cursor, both from committed data.
        assert page.locator(".seq").all_inner_texts() == ["#1", "#2"]
        expect(cursor).to_have_text("2")
        assert _AXE_MIN_JS.is_file(), (
            f"axe-core not installed at {_AXE_MIN_JS}; run: cd src/ced/api/ui && npm ci"
        )
        page.add_script_tag(path=str(_AXE_MIN_JS))
        _scan_wcag_a_aa(page, "streaming")
        expect(page.get_by_role("heading", name="Streaming committed events")).to_be_visible()
    finally:
        with owner_conn.transaction():
            owner_conn.execute(
                """
                INSERT INTO events (run_id, seq, type, step_id, principal)
                VALUES (%s, 3, 'run.completed', NULL, 'worker')
                """,
                (UUID(run_id),),
            )
            owner_conn.execute(
                "UPDATE runs SET state = 'completed' WHERE run_id = %s", (UUID(run_id),)
            )
        owner_conn.commit()
        expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)
        # The cursor advances when a new event commits on the open stream.
        expect(cursor).to_have_text("3")


@pytest.mark.parametrize(
    ("run_id", "history_status"),
    [
        # A well-formed id that names no run: the history route answers 404.
        ("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", 404),
        # A malformed id names no run either: the typed history route answers 422.
        ("not-a-run-id", 422),
        # A malformed percent sequence: decodeURIComponent rejects it, so the
        # client keeps the raw segment and its history request answers 422.
        ("%", 422),
    ],
)
def test_missing_run_shows_unavailable(
    page: Any, api_server: Client, clean_runs: None, run_id: str, history_status: int
) -> None:
    """AC-0336: a missing run reaches the Unavailable outcome on the real routes.

    The state matrix's Unavailable trigger includes "the run is missing", and
    its "Empty or no results" row routes an invalid run there. Nothing is
    mocked: the page route answers ``404`` but serves the client, whose history
    request then fails — ``404`` for the well-formed unknown id, ``422`` for
    ``not-a-run-id`` and ``%``, from that route's typed ``run_id`` — so the
    page names that request with its status and offers Retry.

    A well-formed unknown id, a malformed id and a malformed percent sequence
    are driven: none names a run, and the matrix routes an invalid run to
    Unavailable.

    Mutations:
    (a) Make ``read_run_page`` raise its ``404`` instead of serving the page →
        no page loads → the Unavailable heading never appears → red, every case.
    (b) Declare ``read_run_page``'s ``run_id`` as ``UUID`` again → FastAPI
        answers a malformed id with JSON ``422`` → red, both malformed cases
        (``not-a-run-id`` and ``%``); the well-formed case still passes.
    (c) Replace the history-failure message in App.tsx → the status text no
        longer names the history request → red, every case.
    (d) Remove the ``try``/``catch`` around ``decodeURIComponent`` in
        ``runIdFromLocation`` → the ``%`` case throws during render and the page
        is blank → red, ``%`` case.
    """
    response = page.goto(f"{api_server.base_url}/runs/{run_id}")
    assert response is not None and response.status == 404

    expect(page.get_by_role("heading", name="Run unavailable")).to_be_visible(timeout=5000)
    expect(page.get_by_role("status")).to_contain_text(
        f"Event history returned {history_status}"
    )
    expect(page.get_by_role("button", name="Retry")).to_be_visible()


def test_terminal_history_opens_no_stream(
    page: Any, api_server: Client, clean_runs: None
) -> None:
    """A history that already ends in a terminal event shows Terminal and opens no stream.

    The screen contract's expected outcome is that a terminal run stops
    reconnecting, and the Terminal row that its final state is announced.
    The history already carries the terminal event, so the page must reach
    Terminal from it alone; a stream request that then failed would
    otherwise replace Terminal with Unavailable. The stream here answers
    ``503`` and counts its requests, so either failure is visible.

    The two guards are independent: the reducer decides the state shown, and
    ``connect()``'s own ``endsInTerminal`` check decides whether a stream opens.

    Mutations:
    (a) Drop the ``endsInTerminal`` arm from the ``snapshot`` reducer case →
        ``connect()`` still opens no stream, but the three-event snapshot
        shows Streaming → red on the "Run completed" heading.
    (b) Remove the early return after the snapshot in ``connect()`` → the
        stream opens and fails, and Unavailable replaces Terminal → red on the
        status-text check, before the request count is reached.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    stream_requests: list[str] = []

    def history(route: Any) -> None:
        events = [
            _event(run_id, 1, "run.requested"),
            _event(run_id, 2, "step.started", principal="worker", agent_role="coordinator"),
            _event(run_id, 3, "run.completed", principal="worker"),
        ]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": events}),
        )

    def stream(route: Any) -> None:
        stream_requests.append(route.request.url)
        route.fulfill(status=503, content_type="application/json", body="{}")

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", stream)

    page.goto(f"{api_server.base_url}/runs/{run_id}")
    expect(page.get_by_role("heading", name="Run completed")).to_be_visible(timeout=5000)
    expect(page.get_by_role("status")).to_contain_text("Run completed")
    # Give a stream request, if one were made, time to be issued and fail.
    page.wait_for_load_state("networkidle")
    assert stream_requests == [], f"a terminal run opened a stream: {stream_requests}"
    assert page.get_by_role("heading", name="Run unavailable").count() == 0


def test_stream_drop_while_offline_keeps_offline(
    page: Any, api_server: Client, clean_runs: None
) -> None:
    """A stream that drops while the browser is offline leaves Offline and its Retry in place.

    The Offline row requires offline status and a retry control while the
    browser reports loss of network. A stream that ends in that window makes
    the native transport report an error and reconnect, which must not turn
    Offline into Reconnecting.

    The pending stream is aborted, a network failure before it ever opened,
    so ``onerror`` fires with the transport reconnecting and ``onopen`` never
    does (an open stream would itself show the network is back). The check
    waits on a real signal rather than a sleep: the browser's reconnect
    request, the second stashed stream, proves ``onerror`` has already run.

    When the network comes back, the page must show Reconnecting rather than
    stay on Offline, since the stream is still reconnecting.

    Mutations:
    (a) Derive the shown state from ``connection`` alone, ignoring
        ``browserOffline`` → no reducer arm writes Offline into
        ``connection``, so the Offline heading never appears once the
        ``offline`` event fires → red at the first "Browser is offline"
        expectation, before the stream fails.
    (b) Remove the ``online`` listener → Offline stays up after the network
        returns → red on the "Reconnecting from last sequence" heading.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    held: list[Any] = []

    def history(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}),
        )

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", lambda route: held.append(route))

    page.goto(f"{api_server.base_url}/runs/{run_id}")
    expect(page.get_by_role("heading", name="Waiting for worker events")).to_be_visible(
        timeout=5000
    )
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()

    # Fail the pending stream; the browser schedules its own reconnect.
    assert len(held) == 1, f"expected one held stream, got {len(held)}"
    held[0].abort()
    for _ in range(200):
        if len(held) >= 2:
            break
        page.wait_for_timeout(50)
    assert len(held) >= 2, "the browser never reconnected, so onerror was not observed"
    # Let React commit whatever onerror dispatched before reading the DOM.
    page.evaluate(
        "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )

    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    assert page.get_by_role("heading", name="Reconnecting from last sequence").count() == 0

    # The network comes back while the stream is still reconnecting: Offline
    # is lifted and the page shows the Reconnecting it was holding back.
    page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(page.get_by_role("heading", name="Reconnecting from last sequence")).to_be_visible()

    # Leave the page so its EventSource closes; the held reconnect is
    # cancelled with it, and closing the page then has nothing to wait on.
    page.goto("about:blank")


def test_history_arriving_offline_keeps_offline(
    page: Any, api_server: Client, clean_runs: None
) -> None:
    """Offline survives a history that arrives after the browser lost its network.

    The browser reports loss of network while the history request is in
    flight; the history then succeeds and the stream fails. The Offline row
    requires offline status and Retry for as long as the browser reports no
    network, so neither the snapshot nor the stream failure may replace it.

    Mutation: stop the ``snapshot`` arm carrying ``browserOffline`` forward
    (seed it from ``initialState``) → the snapshot clears Offline and the
    stream failure shows Reconnecting with no Retry → red.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    held_history: list[Any] = []
    held_stream: list[Any] = []

    page.route(f"**/runs/{run_id}/events?after=0", lambda route: held_history.append(route))
    page.route(
        f"**/runs/{run_id}/events/stream?after=0", lambda route: held_stream.append(route)
    )

    page.goto(f"{api_server.base_url}/runs/{run_id}")
    expect(page.get_by_role("heading", name="Loading committed events")).to_be_visible(
        timeout=5000
    )
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()

    events = [_event(run_id, 1, "run.requested"), _event(run_id, 2, "step.started")]
    held_history[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"run_id": run_id, "events": events}),
    )
    for _ in range(200):
        if held_stream:
            break
        page.wait_for_timeout(50)
    assert held_stream, "the page never opened its stream"
    held_stream[0].abort()
    for _ in range(200):
        if len(held_stream) >= 2:
            break
        page.wait_for_timeout(50)
    assert len(held_stream) >= 2, "the browser never reconnected, so onerror was not observed"
    page.evaluate(
        "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )

    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    expect(page.locator(".type", has_text="step.started")).to_be_visible()
    page.goto("about:blank")


def test_retry_while_offline_stays_offline(
    page: Any, api_server: Client, clean_runs: None
) -> None:
    """Retry pressed while still offline keeps Offline and names the request that failed.

    While the retried history request is pending, the page is still shown
    as Offline, so the rows already rendered stay on screen ("Existing rows
    remain") rather than giving way to the Loading placeholders. The request
    then fails because the network is down. The browser still reports no
    network, so the page shows Offline with Retry, and its status names the
    failed request so the Unavailable row's wording is kept.

    Mutations:
    (a) Derive the shown state from ``connection`` alone → the Offline heading
        never appears once the ``offline`` event fires → red at the first
        "Browser is offline" expectation, before Retry is pressed.
    (b) Show only "Network connection lost" while offline, dropping
        ``state.error`` → the status no longer names the failed request → red.
    (c) Branch the event list on ``connection`` rather than the shown state →
        the pending retry shows the Loading placeholders, not the row → red.
    """
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]
    calls = {"history": 0}
    held_retry: list[Any] = []

    def history(route: Any) -> None:
        calls["history"] += 1
        if calls["history"] == 1:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"run_id": run_id, "events": [_event(run_id, 1, "run.requested")]}
                ),
            )
        else:
            held_retry.append(route)

    page.route(f"**/runs/{run_id}/events?after=0", history)
    page.route(f"**/runs/{run_id}/events/stream?after=0", lambda route: None)

    page.goto(f"{api_server.base_url}/runs/{run_id}")
    expect(page.get_by_role("heading", name="Waiting for worker events")).to_be_visible(
        timeout=5000
    )
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()

    page.get_by_role("button", name="Retry").click()
    for _ in range(200):
        if held_retry:
            break
        page.wait_for_timeout(50)
    assert held_retry, "the retried history request was never made"
    # The retry is pending: still Offline, and the existing row still shown.
    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()
    expect(page.locator(".type", has_text="run.requested")).to_be_visible()
    assert page.locator("[aria-busy='true']").count() == 0

    held_retry[0].abort()
    expect(page.get_by_role("status")).to_contain_text("Event history request failed")
    expect(page.get_by_role("heading", name="Browser is offline")).to_be_visible()
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    assert page.get_by_role("heading", name="Run unavailable").count() == 0
    page.goto("about:blank")
