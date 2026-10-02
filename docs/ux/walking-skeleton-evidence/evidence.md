# Browser evidence manifest: Walking skeleton evidence

## Surface

The browser surface is served at `GET /runs/{run_id}` from the same origin as
the API. Built assets are mounted at `/static` from `src/ced/api/static` with
Starlette `StaticFiles` and `follow_symlink=False`.

The source mechanism is a nested Vite and React project under
`src/ced/api/ui/`. The checked-in bundle under `src/ced/api/static/` is the
package-served artifact used by `ced-api`.

## Direction

- Aesthetic reference: Raycast.
- Direction source: `docs/ux/direction/walking-skeleton-evidence.md`.
- Applied qualities: compact dark surface, ordered sequence spine, restrained
  accents, ruled rows, and no decorative gradient or imagery.
- Mechanism approved by owner on 2026-09-29: nested Vite and React under the
  API package, served from the same origin.

## States

| State | Check artifact | Evidence status |
| --- | --- | --- |
| Loading | `tests/browser/test_run_page.py::test_applicable_state_matrix` asserts the "Loading committed events" status heading and the three placeholder rows inside the `[aria-busy='true']` list while the first history fetch is delayed | Verified — rendering no placeholder rows reds the check, and so does changing `labelFor("loading")`. The list's own visibility is not evidence of the rows: its top border keeps it visible when empty |
| Waiting | `tests/browser/test_run_page.py::test_applicable_state_matrix` asserts the "Waiting for worker events" heading and that the `<h1>` reads `Run <run id>` after retry with only `run.requested` in history | Verified — changing `labelFor("waiting")` reds the check, and so does dropping `{runId}` from the `<h1>` |
| Streaming | `test_streaming_state_is_scanned` holds Streaming open on the real routes and asserts ordered rows (`#1`, `#2`) and the header cursor at 2, then 3 once the terminal event commits on the open stream; `test_applicable_state_matrix` asserts the `step.started` row appears; `test_streaming_does_not_move_keyboard_focus` asserts the focused element class is unchanged before and after events arrive | Verified — freezing the reducer's cursor reds `test_streaming_state_is_scanned` (the cursor reads 0); dropping the reducer's `event` case reds `test_applicable_state_matrix`; a `blur()` added to `onmessage`'s non-terminal arm reds `test_streaming_does_not_move_keyboard_focus`. Does not reach: focus stability for non-Tab interaction or pointer-driven focus changes |
| Reconnecting | `test_reconnecting_status_is_announced` closes the first stream with `retry: 2000`, so the state is held for that window, and asserts the "Reconnecting from last sequence" heading, the same text inside the `role="status"` live region, and the survival of the already-rendered row; `test_eventsource_resumes_after_forced_disconnects` forces repeated stream closes via mini server proxy | Verified — changing `labelFor("reconnecting")` reds `test_reconnecting_status_is_announced`, and so does moving the label back out of the live region. Does not reach: back-off policy, or any reconnect interval the server does not itself set through `retry:` |
| Terminal | `test_stream_closes_after_terminal_event` asserts no second stream request is issued after the terminal frame; `test_live_region_announces_terminal_outcome` asserts a `run.failed` run is announced as "Run failed" in the heading and the live region and is not painted in the success colour; `test_offline_after_terminal_keeps_terminal` asserts going offline after the terminal frame keeps the terminal heading and offers no Retry; `test_terminal_history_opens_no_stream` asserts a history that already ends in a terminal event shows Terminal and opens no stream, so a failing stream cannot replace it with Unavailable | Verified — removing `source.close()` from `onmessage`'s terminal arm reds `test_stream_closes_after_terminal_event`, which then counts 143 stream requests instead of one; restoring the fixed "Terminal event received" label, painting every terminal type in the success colour, and dropping Terminal's precedence over Offline in the render-time derivation of the shown state each red their own check, and so do ignoring a terminal history in the `snapshot` arm and opening the stream after one. Does not reach: network-layer connection close on the server side |
| Unavailable | `tests/browser/test_run_page.py::test_applicable_state_matrix` drives an event-history failure and observes retry; `test_closed_stream_shows_unavailable` answers the stream with a 503 after history succeeds and expects the Unavailable heading and Retry; `test_accessibility_and_reflow` scans this state | Verified — replacing the `unavailable` reducer arm with `return state` reds the matrix check; dispatching `reconnecting` on every stream error, including a permanent one, reds `test_closed_stream_shows_unavailable`. Both checks also assert the status names the failed request (`Event history returned 503`, `Stream request failed`) and the closed-stream check that the row already rendered remains; replacing either message, or clearing the rows in the `unavailable` arm, reds its check. `test_missing_run_shows_unavailable` opens, on the real routes, a well-formed id that names no run and a malformed id: the page answers `404` but carries the client, which shows Unavailable naming the failed history request (`Event history returned 404`, and `422` for a malformed id, including a malformed percent sequence such as `%`) with Retry; making the page route raise its `404` instead, typing its `run_id` as `UUID` again, removing the client's guard around `decodeURIComponent`, or replacing the message, reds it |
| Offline | The same browser check dispatches the browser offline event from Waiting, a non-terminal state, and observes the offline heading, its Retry, and the `run.requested` row already rendered; `test_stream_drop_while_offline_keeps_offline` fails a stream while the browser is offline and asserts Offline and Retry remain, then Reconnecting once the network returns; `test_history_arriving_offline_keeps_offline` lets the history arrive after the network is lost; `test_retry_while_offline_stays_offline` presses Retry while still offline and asserts Offline with the failed request named; `test_accessibility_and_reflow` scans this state | Verified — clearing the rows in the `offline` reducer arm reds `test_applicable_state_matrix`, `test_offline_after_terminal_keeps_terminal` and `test_retry_while_offline_stays_offline`; deriving the shown state from `connection` alone, ignoring the browser-offline flag, reds `test_stream_drop_while_offline_keeps_offline`, `test_history_arriving_offline_keeps_offline`, `test_retry_while_offline_stays_offline`, `test_applicable_state_matrix` and `test_accessibility_and_reflow`; removing the `online` listener reds the first, the matrix check and the accessibility check, the first also asserting Reconnecting once the network returns; not carrying the flag through the `snapshot` arm reds only the history-arriving check; dropping the failed-request text while offline, or branching the event list on `connection` so a pending Retry shows placeholders instead of the existing rows, reds only the retry-while-offline check. Each break was run against the whole browser suite |
| Keyboard only | `test_applicable_state_matrix` reaches Retry with Tab and invokes it with Enter, and the page leaves Unavailable for Waiting; `test_accessibility_and_reflow` tabs to the skip link, then reads the focused element's computed `box-shadow` and `outline` | Verified — binding Retry's handler to `onPointerDown` instead of `onClick` reds the matrix check, since Enter then does nothing while every `.click()` still passes; the computed-style read is what carries focus visibility, and the `:focus-visible` count beside it is a focus-presence precondition and cannot establish visibility on its own. Break and limits in § Accessibility Result |
| High zoom and narrow width | `test_accessibility_and_reflow` checks no horizontal page overflow at a narrow viewport | Verified — no overflow at 640 × 720 px. **Zoom is not driven; width stands in for it.** 640 CSS px is what a 1280 px viewport yields at 200% zoom, which is the standard reflow technique, but the browser's own zoom was never set. Does not reach: text-only zoom, or a zoom level whose equivalent width is not also tested |
| Reduced motion | CSS limits transitions to `prefers-reduced-motion: no-preference`; the browser check searches for unguarded transitions | Verified — `transition_count == 0` under reduced-motion emulation |

## Routes

| Route | Role | Status |
| --- | --- | --- |
| `GET /runs/{run_id}` | Serves fixed `index.html` from `_STATIC_ROOT` — with status `200` for an existing run and `404` for an unknown or malformed id, so the client can show Unavailable | Verified by `test_run_page_serves_only_the_fixed_index`; the `404` by `tests/api/test_read_access.py::test_unknown_run_is_refused_for_page_and_stream` |
| `GET /static/**` | Confined asset delivery, no symlink following | Verified by `test_static_paths_never_escape_the_bundle_root` |
| `GET /runs/{run_id}/events` | History page for initial load | Consumed by UI; tested by API suite |
| `GET /runs/{run_id}/events/stream` | Server-sent event stream | Verified against the shipped route by `tests/api/test_event_stream.py` — cursor precedence, cursor refusal, terminal close, and the absent `event:` field. **The browser reconnect run does not reach this route:** `test_eventsource_resumes_after_forced_disconnects` re-routes the request to a local fixture server so `Last-Event-ID` can be read off a real socket, which the browser does not expose to the harness. It establishes the client half — that the browser resumes from its last applied sequence and reapplies nothing |

## Supported viewports

| Viewport | Driven by | Observation |
| --- | --- | --- |
| Playwright default (1280 × 720 px) | every browser check | All state, sink, reconnect and accessibility assertions run here |
| 640 × 720 px | `test_accessibility_and_reflow` | No horizontal page overflow; the single readable column holds and rows stay distinguishable |

Those two are the whole set. No check drives a phone-width viewport, a
landscape short-height viewport, or a viewport above 1280 px, so the screen
contract's "rows remain distinguishable at narrow widths and high zoom" is
established at 640 px and asserted nowhere narrower.

## Security and privacy

External event-envelope strings render through React text interpolation in the
source project and `textContent` in the served bundle. `payload_ref` is displayed
as inert text. The UI creates no caller-derived `href`, uses no
`dangerouslySetInnerHTML`, and performs no payload dereference.

`test_external_values_never_create_markup_or_links` verifies that HTML payloads
in all four external fields (`principal`, `agent_role`, `payload_ref`,
`idempotency_key`) appear as visible literal text.  The assertion
enumerates the full sink class — `iframe`, `script`, `object`, `embed`, `svg`,
`a[href]`, and `[href^='javascript:']` — and asserts zero elements in each
independent of the injected field value.  Mutation proof, re-run on 2026-09-30:
routing `principal` through an `<iframe title={…} src="about:blank" />` inside
the event row failed the assertion with `found <iframe> element in event region
— external value reached a sink`; restoring React text interpolation made it
green.

Does not reach: DOM sinks created by third-party scripts (none are loaded),
`srcdoc` or `sandbox` attribute injection on existing elements, or CSS injection
via `style` attributes.

Phase 1 read access is intentionally unauthenticated. The server validates run
existence and stream cursor bounds before opening the stream. Object-level
authorization remains a deployed-ingress residual for AC-0314.

`test_after_cursor_ahead_of_highest_seq_is_refused` verifies that a stream request
with `after` ahead of the run's highest committed sequence returns 422 (AC-0323).
The guard applies regardless of whether the cursor came from `Last-Event-ID` or
the `after` query parameter.  Mutation proof, re-run on 2026-09-30: narrowing
the guard to the header path let the `after=3` request through, so the route
opened a stream that polls for an event that never commits and the check failed
with `TimeoutError: timed out` on the socket read rather than reading a 422.

Does not reach: concurrent-write races where the sequence advances between the
bounds check and the stream open.

## Accessibility Result

All browser checks run in the local substrate suite (Playwright 1.61.0,
Chromium 149.0.7827.55, macOS Darwin 25.5.0). The accessibility and reflow
check passes there.

The implemented surface uses one `main`, one `h1`, semantic status text,
keyboard-visible focus, non-color status labels, and a reduced-motion guard.

### What the automated scan evaluates

Every scan goes through one helper, `_scan_wcag_a_aa` in
`tests/browser/test_run_page.py`, which injects `axe-core` (a devDependency of
the UI manifest, not part of the built bundle) and runs it with an **explicit
`runOnly` list of every rule carrying a WCAG 2.0, 2.1 or 2.2 Level A or AA
tag**. In the installed axe-core 4.10.3 that is 69 rules.

**A bare `axe.run()` would not be this scan, and an earlier revision of this
manifest made exactly that mistake.** With no options, axe evaluates only its
enabled, non-experimental default set — 89 of its 104 registered rules — and
eight A/AA-tagged rules fall outside it:

| Rule | Tag | WCAG criterion | Why the default set skips it |
| --- | --- | --- | --- |
| `aria-roledescription` | `wcag2a` | 4.1.2 | `enabled: false` |
| `audio-caption` | `wcag2a` | 1.2.1 | `enabled: false` |
| `target-size` | `wcag22aa` | **2.5.8 Target Size (Minimum)** | `enabled: false` |
| `css-orientation-lock` | `wcag21aa` | 1.3.4 Orientation | tagged `experimental` |
| `label-content-name-mismatch` | `wcag21a` | 2.5.3 Label in Name | tagged `experimental` |
| `p-as-heading` | `wcag2a` | 1.3.1 | tagged `experimental` |
| `table-fake-caption` | `wcag2a` | 1.3.1 | tagged `experimental` |
| `td-has-header` | `wcag2a` | 1.3.1 | tagged `experimental` |

The explicit rule list overrides both exclusions, so all eight now run. It also
runs **no** best-practice rule, so a failure is a WCAG A/AA failure and the
message says so: `WCAG 2.2 A/AA violations in <state> state`.

**The helper asserts that every listed rule was evaluated**, not only that none
was violated. It compares the rules axe reports having evaluated against the
A/AA rules it registers, so an axe release that quietly skipped a listed rule
would fail the check instead of shrinking its coverage unnoticed. Proved: with
the helper reverted to a bare `axe.run()`, the check failed naming exactly the
eight rules above.

### Which states are scanned

Every supported state in the state matrix is scanned, each while it stands still:

| State | Scanned in | How the state is held |
| --- | --- | --- |
| Loading | `test_accessibility_and_reflow` | the first history request's `Route` is stashed and fulfilled later |
| Unavailable | `test_accessibility_and_reflow` | that held request is released as a 503 |
| Waiting | `test_accessibility_and_reflow` | the stream `Route` is stashed and fulfilled later |
| Streaming | `test_streaming_state_is_scanned` | the real routes serve a run with no terminal event, so the stream stays open |
| Terminal | `test_accessibility_and_reflow` | — |
| Offline | `test_accessibility_and_reflow` | dispatched `offline` event, from Waiting |
| Reconnecting | `test_reconnecting_status_is_announced` | the first frame sets `retry: 2000`, so the browser waits two seconds |

Reconnecting lives in a different check because that check is the only one
that holds it open. Blocking *inside* a route handler instead of stashing the
`Route`, as an earlier revision did, stalls Playwright's own event loop:
measured, such a gate always ran to its full timeout and gated nothing.

**Result: no WCAG 2.2 A or AA violation among all 69 A/AA-tagged rules, in
every state above.** Including `target-size`, so 2.5.8 is now measured rather
than asserted — the retry button's `min-width`/`min-height` clear 24 CSS pixels
and the rule confirms it.

### Mutation proofs

Each scan was proved by a break that fails *its own* scan, not a neighbour's:

| Break | Check run | Red proof |
| --- | --- | --- |
| Unlabelled `<button type="button" />` in the Loading branch only | `test_accessibility_and_reflow` | `WCAG 2.2 A/AA violations in loading state: [critical] button-name` |
| Unlabelled `<button type="button" />` in the Unavailable branch only | `test_accessibility_and_reflow` | `WCAG 2.2 A/AA violations in unavailable state: [critical] button-name` |
| Unlabelled `<button type="button" />` in every state, check run alone | `test_reconnecting_status_is_announced` | `WCAG 2.2 A/AA violations in reconnecting state: [critical] button-name` |
| `<img src="" />` without `alt` in the Streaming state only | `test_streaming_state_is_scanned` | `WCAG 2.2 A/AA violations in streaming state: [critical] image-alt` — `test_accessibility_and_reflow` stays green under the same break |
| Helper reverted to a bare `axe.run()` | `test_accessibility_and_reflow` | `axe registered 69 WCAG A/AA rules but did not evaluate [the eight rules above]` |

Each failure names its state, which is what shows one scan per state finds a
defect a single scan would miss. The Reconnecting break is its own because
changing `labelFor("reconnecting")` fails the heading expectation *before* the
scan is reached, and so proves nothing about it.

**Does not reach:** any state the fulfilled routes cannot produce, since every
state above but Streaming is driven through mocked routes, and Streaming
through events committed by the check rather than by a live worker.

**The focus-indicator assertion reads a computed style, and that is
deliberate.** `page.locator(":focus-visible").count() == 1` on its own cannot
establish a visible indicator: `:focus-visible` is a user-agent state that
matches with every author rule removed, so neutralising the focus ring leaves
that count at 1. The check therefore also reads the focused element's computed
`box-shadow` and `outline`.

**The defect class it reds on is "no indicator at all", author or user-agent —
not "the author rule is gone".** Deleting the
`box-shadow: var(--ds-focus-ring)` rule from `styles.css` leaves this check
**green**, and correctly so: that rule carries a transparent outline alongside
the shadow, so removing it restores Chromium's own focus ring and the element still
paints a visible indicator. The break that reds is suppressing both —
`*:focus-visible { outline: 0 !important; box-shadow: none !important; }` —
which yields `box-shadow='none', outline='none' '0px'`. Both observations are
recorded in the verification ledger's § Post-gates review round 3.

**The ring's contrast is measured.** The same check composites the ring's
computed colour over the focused skip link's backdrop and asserts at least 3:1,
the WCAG 2.2 AA 1.4.11 floor for a state indicator. The ring is the opaque
`--ds-color-accent`; the 45%-alpha ring it replaced measured 2.07:1 against the
canvas and reds this assertion.

**Forced colours are emulated.** `test_forced_colors_focus_outline` opens a
context with `forced_colors="active"`, where the browser drops `box-shadow`,
and asserts the focused skip link and Retry button both compute a non-`none`,
non-zero outline. The focus rule's transparent outline is what the browser
repaints in the system colour; restoring `outline: 0` reds the check with
`Skip link outline style is 'none' in forced-colors mode (width='0px')`.

Does not reach: the ring's contrast on the Retry button's surface backdrop,
which is not measured, though the same opaque token is used there; the colour
forced-colors mode actually paints, since the check reads computed style, not
pixels; thickness and area, which are WCAG 2.2 AAA Focus Appearance and remain
unverified; and the loss of the *author* indicator specifically, which no check
distinguishes from the user-agent fallback.

### What no automated scan reaches

These need a person, whatever the rule set:

- Color contrast under hardware-accelerated display contexts. Headless
  Chromium resolves CSS colors, but rendering may differ on hardware displays.
  Confirmed visually on macOS dark mode.
- Keyboard interaction beyond Tab focus order — custom key bindings, or
  enter/space on interactive elements beyond the browser's default behavior.
- Screen-reader announcement timing. `aria-live="polite"` on the status
  paragraph is asserted present, and its text is asserted to name the
  Reconnecting and Terminal states, but announcement timing is asynchronous and
  not observable through the DOM.

New-in-2.2 AA criteria with **no** automated rule in axe-core 4.10.3, and
therefore unverified here: 2.4.11 Focus Not Obscured (Minimum), 2.5.7 Dragging
Movements, 3.2.6 Consistent Help, 3.3.7 Redundant Entry, and 3.3.8 Accessible
Authentication (Minimum). 2.5.8 is not on this list — `target-size` measures it.

## Catch-all SSE Frame Handling

The server sets no `event:` field on a frame.  `encode_sse_event` in
`src/ced/api/stream.py` emits `id:` and `data:` only, and the committed event
type travels inside the JSON envelope's `type` field.  A named `event:` field is
what dispatches a frame under that name, so a client's `onmessage` never fires
and it has to register one listener per type — an enumeration
`src/ced/domain/events.py` makes impossible to keep complete, because the
step-scoped vocabulary is deliberately open.

The browser source (`src/ced/api/ui/src/App.tsx`) therefore opens one native
`EventSource` with a single `onmessage` handler, which receives every frame and
reads the type out of the parsed envelope.  A new committed domain event type
reaches the reducer and renders with no client-side change.  The native
transport also owns reconnection: it reopens on its own and supplies
`Last-Event-ID` from the last `id:` field it saw, which is the reconnect
AC-0305 observes on the wire.

`test_unknown_event_type_is_rendered` verifies the catch-all: it serves a
`tool.invoked` event and asserts the `.type` span appears with that text.
Mutation proof, re-run against the shipped `EventSource` client on 2026-09-30:
restoring `event: {type}` in `encode_sse_event` and in the test's `_sse()`
helper, then replacing `onmessage` with per-type `addEventListener`
registrations over a seven-name enumeration that omits `tool.invoked`, made the
`tool.invoked` row never appear — `AssertionError: Locator expected to be
visible … element(s) not found`.  Restoring the single `onmessage` handler made
it green.

`tests/api/test_event_stream.py::test_terminal_event_closes_the_stream` pins the
server half: every frame's parsed fields are checked and none may carry
`event:`.  Mutation proof: restoring `event: {event.type}` reds it with
`frames must set no event: field, found ['run.requested', 'run.completed']`.

Does not reach: event types that carry binary or non-JSON data (none are emitted
by the current server); multi-line `data:` frames beyond the two-line test; and
cross-origin stream delivery, since `EventSource` is opened on a same-origin
relative URL and no CORS policy is configured.

**One enumeration survives in the client, and nothing checks it against the
server.** `terminalEvents` in `App.tsx` re-declares the three terminal types
that `src/ced/domain/events.py` holds in `TERMINAL_EVENT_TYPES`. That module's
own rule is that agreement between copies "means checked, not asserted", and it
names a checking mechanism for each other shared name; this copy has none. The
consequence of drift is specific: a terminal type added server-side would end
the stream while the client treated the frame as ordinary, so `source.close()`
would never run and the native transport would reconnect indefinitely — the
AC-0304 failure the frame-format decision was taken to remove at its cause.
Recorded here as uncovered duplication rather than claimed as covered; closing
it means deriving or checking the client set against the server vocabulary.

## Bundle Provenance

The bundle served by `ced-api` is the built output of `src/ced/api/ui/`, checked
in under `src/ced/api/static/`.  SHA-256 checksums of the shipped bundle, after
the round-30 rebuild on 2026-10-01:

- `src/ced/api/static/index.html`:
  `a5a05aa0897f32b66fbf502a7b7e0909f704abc7c3b48cfca785bfd14a37bb51`
- `src/ced/api/static/assets/index-CaJkuxGG.js`:
  `d6c43165644a311729834a9bce9787d2ee7ac78146a4a5b9a28ebf36bf70694f`
- `src/ced/api/static/assets/index-DKLqRv6V.css`:
  `d545dd8f2e7d482485289087029dd81972b8c08e71fb1953e839185b678b0f89`

The asset filenames carry the Vite content hash of the compiled output, and
`index.html` references `index-CaJkuxGG.js` and `index-DKLqRv6V.css` by those
filenames.  The build ran after every UI source change through round 30 was
applied and every mutation proof was restored to green, from a wiped
`node_modules` reinstalled with `npm ci`, so the committed lockfile was
exercised rather than a warm cache.  A second `npm run build` over the same
source reproduced all three checksums exactly, which is what makes the
comparison a check rather than a record.  Nothing enforces this mechanically;
rebuild and compare by hand whenever the UI source changes.

The T5 rebuild of 2026-09-30 produced `index-r3gonaOH.js` and
`index-CdSv7G3w.css`, and the round-17, round-21, round-25 and round-29 rebuilds
`index-U7v6KYTA.js`, `index-C6tHoan6.js`, `index-AWpoQ4Wx.js` and
`index-DL2Mjqau.js`; those
files no longer exist, and their digests in the verification ledger are
history, not the shipped bundle.

## Playwright Dependency Choice

The Python manifest names the direct `playwright` package instead of
`pytest-playwright`. The test suite defines its own `browser`, `browser_context`,
and `page` fixtures and does not use the fixtures `pytest-playwright` provides;
the direct package keeps the harness without pulling in an unused plugin layer.
`pytest-playwright` could be adopted by swapping the pin in `pyproject.toml`; the
suite's custom fixtures would continue to take precedence over the plugin's
same-named fixtures.

## Gate History

- `ruff format --check .`: 272 files already formatted — pass, exit 0.
- `ruff check .`: all checks passed — pass, exit 0.
- `mypy`: no issues in 55 source files — pass, exit 0.
- `python -m pytest`: the gate of record, run whole and unfiltered against the
  final tree — **1112 passed, 3 skipped in 294.99 s, exit 0**, with the local
  substrate up and a real Chromium installed.  No `pytest` process remained
  afterwards.  Every figure in this section comes from that one run; earlier
  per-task runs are not recorded here, because a figure taken before the last
  change describes a tree that is not the one shipping.
- `cd src/ced/api/ui && npm ci && npm run test && npm run build`: pass, exit 0,
  from a wiped `node_modules`.  Checksums under § Bundle Provenance.

  Earlier rounds recorded this as two invocations (`-m 'not substrate'`, then
  `tests/api/ tests/browser/`) and were green that way while the single
  documented command failed 59 checks. The split always puts `tests/browser/`
  last, where its Playwright event loop outlives nothing; run whole, the suite
  sorts it early and every later `asyncio.run` fails. The split result is not
  recorded here, because it was not evidence about the gate.
- `lint-no-identifiers.py --staged`: clean.
- `lint-intents.py`: clean.
- `pre-pr.py`: all checks passed.
- `lint-spec-status.py --root . --all`: spec metadata clean.
