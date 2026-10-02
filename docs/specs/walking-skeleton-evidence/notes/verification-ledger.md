# Verification ledger: Walking skeleton evidence

This ledger separates evidence from narrative. A check is not counted as
coverage until its required break has been observed red and the restored check
has been observed green.

## T1 stream and browser checks

| Claim | Check artifact | Required break | Red proof | Restored proof | Status |
| --- | --- | --- | --- | --- | --- |
| Stream closes at terminal | `tests/api/test_event_stream.py::test_terminal_event_closes_the_stream` | Remove the terminal break from the generator (`committed_event_stream`: deleted `if envelope.type in TERMINAL_EVENT_TYPES: return`) | FAILED — `TimeoutError` on the `stream` call rather than clean close | PASSED — 1 passed in 1.19 s | Proved |
| Stream route stays published | `tests/api/test_contract_agreement.py::test_the_served_routes_match_the_committed_contract` plus `test_the_contract_file_includes_the_stream_operation` | Remove the `stream_events` operation from `contracts/openapi/runs.yaml` while leaving the route implemented | FAILED — `AssertionError: GET /runs/{run_id}/events/stream not in committed table` | PASSED — 9 passed in 0.71 s | Proved |
| `Last-Event-ID` precedes `after` | `tests/api/test_event_stream.py::test_last_event_id_precedes_query_cursor` | Prefer `after` over the header (`selected_cursor`: returned `after` regardless of `last_event_id`) | FAILED — `assert 5 == 3` (cursor resolved to `after` instead of header value) | PASSED — 6 passed in 1.19 s | Proved |
| Invalid stream cursors are refused | `tests/api/test_event_stream.py::test_invalid_last_event_id_is_refused` | Remove the negative-value guard (`if cursor < 0: raise ...` commented out) | FAILED — `assert 200 == 422` for `-1` cursor | PASSED — 6 passed in 1.19 s | Proved |
| Foreign origins are refused on state-changing routes | `tests/api/test_same_origin.py::test_foreign_origin_is_refused_on_every_state_change` | Remove `_guard_same_origin` call from `start_run` | FAILED — `AssertionError: POST /runs` — `assert 201 == 400` | PASSED — 2 passed in 0.81 s | Proved |
| Origin refusal stays published | `tests/api/test_contract_agreement.py::test_the_served_routes_match_the_committed_contract` and `test_every_response_status_the_contract_declares_is_served` | Remove `"400"` response from `start_run` in `contracts/openapi/runs.yaml` while leaving runtime refusal intact | FAILED — `{'POST /runs': {..., 'responses': ['201', '422']}} != {'POST /runs': {..., 'responses': ['201', '400', '422']}}` | PASSED — 9 passed in 0.71 s | Proved |
| Static paths stay under the bundle root | `tests/api/test_static_ui.py::test_static_paths_never_escape_the_bundle_root` | Enable symlink following (`follow_symlink=True` in `StaticFiles`) | FAILED — `assert 200 in {400, 404}` for out-of-root symlink | PASSED — 2 passed in 0.89 s | Proved |
| Phase 1 read posture is explicit | `tests/api/test_read_access.py::test_unknown_run_is_refused_for_page_and_stream` | Remove `_require_run` call from `stream_events` before opening the response | FAILED — `pytest.fail("unknown run stream opened")` — 200 instead of 404 | PASSED — 3 passed in 0.62 s | Proved *(the page half changed in round 19: an unknown run's page is now a 404 carrying the client; see that section)* |
| Browser reconnect continuity is wire-visible (header precedence) | `tests/browser/test_run_page.py::test_eventsource_resumes_after_forced_disconnects` | Remove `id:` field from `_sse()` helper — browser has no event ID to send as `Last-Event-ID` | FAILED — `AssertionError` — wire_captures[k] for k >= 1 is always None | PASSED — 1 passed | Proved |
| Browser reconnect continuity is wire-visible (sink sequence) | `tests/browser/test_run_page.py::test_eventsource_resumes_after_forced_disconnects` | Remove `addEvent` deduplication guard in `App.tsx` and rebuild | FAILED — `TimeoutError` waiting for `Terminal event received` (seq=102 never reached; seq=2 re-served every connection) | PASSED — 1 passed | **Retired** — the red above was observed against the `fetch` client this delivery replaced. Re-performed against the shipped `EventSource` client the break does not red; see § T5 retired row |
| Tab reload resets EventSource session (wire boundary) | `tests/browser/test_run_page.py::test_eventsource_resumes_after_forced_disconnects` | Remove `page.reload()` call — no second None appears in wire_captures | FAILED — `AssertionError: Expected a tab-reload boundary` — reload_idx is None | PASSED — 1 passed | Proved |
| Stream route does not leak a database connection | `tests/api/test_event_stream.py::test_stream_releases_connection_on_disconnect` | Restore `conn: Conn` generator-dependency parameter on `stream_events` | FAILED — `AssertionError: Stream route leaked 1 idle-in-transaction connection(s)` | PASSED — 1 passed | **Did not reproduce** — re-performed 2026-10-01 on FastAPI 0.141.1, the check passed 3 of 3 under this break, because it sampled after disconnect. Re-proved after the check moved its sample; see § Post-gates review round 16 |
| External values remain literal text | `tests/browser/test_run_page.py::test_external_values_never_create_markup_or_links` | Replace `{event.principal}` with `dangerouslySetInnerHTML={{ __html: event.principal }}` in `App.tsx` | FAILED — `img` element found in DOM (HTML interpreted from `<img src=x onerror=...>` principal value) | PASSED — 1 passed in 7.83 s | Proved |
| Browser states are complete (unavailable) | `tests/browser/test_run_page.py::test_applicable_state_matrix` | Replace `unavailable` reducer arm with `return state` | FAILED — `AssertionError` waiting for `Run unavailable` heading | PASSED — 4 passed | Proved |
| Browser states are complete (loading skeleton) | `tests/browser/test_run_page.py::test_applicable_state_matrix` | Remove `aria-busy="true"` from the loading skeleton `ol` in `App.tsx` and rebuild | FAILED — `AssertionError` — `[aria-busy='true']` locator finds nothing | PASSED — 4 passed | Proved |
| Browser states are complete (waiting) | `tests/browser/test_run_page.py::test_applicable_state_matrix` | Change `labelFor("waiting")` return value to `"..."` in `App.tsx` and rebuild | FAILED — `AssertionError` waiting for `Waiting for worker events` heading | PASSED — 4 passed | Proved |
| Accessibility and reflow hold (reduced motion) | `tests/browser/test_run_page.py::test_accessibility_and_reflow` | Remove `@media (prefers-reduced-motion: no-preference)` guard from `.skip-link { transition: ... }` in `styles.css` | FAILED — `assert 1 == 0` (`transition_count` rose to 1 under reduced-motion emulation) | PASSED — 4 passed | Proved |
| Automated WCAG 2.2 A/AA scan catches a real violation | `tests/browser/test_run_page.py::test_accessibility_and_reflow` | Add `<img src="" />` without `alt` to `App.tsx`, rebuild, run the scan | FAILED — `AssertionError: WCAG 2.2 A/AA violations found: [critical] image-alt: Images must have alternate text` *(witness text predates the per-state scan; the shipped message is `WCAG 2.2 A/AA violations in <state> state`)* | PASSED — 4 passed (restored) | Proved |

## T5 browser coverage gaps (AC-0304, AC-0305, AC-0322, AC-0323, AC-0336, AC-0337)

Every row below was **re-observed on 2026-09-30 against the shipped native
`EventSource` client**, after the frame format decision in § Owner decisions
replaced the `fetch` + `getReader()` reader. The earlier red proofs were taken
against a client that no longer exists and were not carried forward: each break
here was performed, observed red, restored, and observed green again.

| Claim | Check artifact | Required break | Red proof | Restored proof | Status |
| --- | --- | --- | --- | --- | --- |
| Terminal frame closes the stream (AC-0304) | `tests/browser/test_run_page.py::test_stream_closes_after_terminal_event` | Remove `source.close()` from `onmessage`'s terminal arm in `App.tsx`; rebuild | FAILED — `AssertionError: Expected exactly one stream request after terminal event; got 143.  The terminal arm did not close the stream.` | PASSED — 1 passed in 4.73 s (restored) | Proved |
| Frames carry no `event:` field (AC-0304 / AC-0305, server half) | `tests/api/test_event_stream.py::test_terminal_event_closes_the_stream` | Restore `event: {event.type}` in `encode_sse_event` | FAILED — `AssertionError: frames must set no event: field, found ['run.requested', 'run.completed']` | PASSED — 1 passed in 0.60 s (restored) | Proved |
| Unknown event types are rendered (AC-0304 / AC-0305 catch-all) | `tests/browser/test_run_page.py::test_unknown_event_type_is_rendered` | Restore `event:` in `encode_sse_event` **and** in the test's `_sse()` helper, then replace the single `onmessage` handler with per-type `addEventListener` registrations over a seven-name enumeration omitting `tool.invoked`; rebuild | FAILED — `AssertionError: Locator expected to be visible … element(s) not found` — the `tool.invoked` row never rendered | PASSED — 1 passed in 3.12 s (restored) | Proved |
| Reconnecting status text is rendered (AC-0336) | `tests/browser/test_run_page.py::test_reconnecting_status_is_announced` | Change `labelFor("reconnecting")` to return `"Resuming from last sequence"` in `App.tsx`; rebuild | FAILED — `AssertionError: Locator expected to be visible … element(s) not found` — heading `Reconnecting from last sequence` never appeared | PASSED — 1 passed in 4.75 s (restored) | Proved |
| Streaming does not move keyboard focus (AC-0336) | `tests/browser/test_run_page.py::test_streaming_does_not_move_keyboard_focus` | Add `(document.activeElement as HTMLElement \| null)?.blur()` to `onmessage`'s non-terminal arm in `App.tsx`; rebuild | FAILED — `AssertionError: Keyboard focus moved during streaming: was 'skip-link', now ''` | PASSED — 1 passed in 4.71 s (restored) | Proved |
| Per-state WCAG scan catches unavailable-branch violation (AC-0337) | `tests/browser/test_run_page.py::test_accessibility_and_reflow` | Add an empty `<button type="button" />` (no accessible name) to the `unavailable` branch in `App.tsx`; rebuild | FAILED — `AssertionError: WCAG 2.2 A/AA violations in unavailable state: [critical] button-name: Ensure buttons have discernible text` — the message names the unavailable scan, so a single scan would not have found it | PASSED — 1 passed in 2.98 s (restored) | Proved |
| Sink class enumeration catches iframe (AC-0322) | `tests/browser/test_run_page.py::test_external_values_never_create_markup_or_links` | Add `<iframe title={event.principal} src="about:blank" />` to the event-row `div.spine` in `App.tsx`; rebuild | FAILED — `AssertionError: found <iframe> element in event region — external value reached a sink` | PASSED — 1 passed in 2.79 s (restored) | Proved |
| `after` cursor ahead of highest committed sequence is refused (AC-0323) | `tests/api/test_event_stream.py::test_after_cursor_ahead_of_highest_seq_is_refused` | Narrow the bounds guard in `selected_cursor` to `if cursor > highest_seq and last_event_id not in (None, "")` | FAILED — `TimeoutError: timed out` on the socket read — the `after=3` request opened a stream that polls for an event that never commits, instead of returning 422 | PASSED — 1 passed (restored) | Proved |
| Stream operation present in committed contract | `tests/api/test_contract_agreement.py::test_the_contract_file_includes_the_stream_operation` | Rename the `/runs/{run_id}/events/stream` path in `contracts/openapi/runs.yaml` while leaving the route implemented | FAILED — `AssertionError: assert 'GET /runs/{run_id}/events/stream' in {…}` | PASSED — 1 passed in 0.29 s (restored) | Proved |
| Retry does not open a second stream against the same run | `tests/browser/test_run_page.py::test_applicable_state_matrix` | Remove `retryToken: state.retryToken` from the reducer's `snapshot` arm in `App.tsx`, so the token reseeds to 0 and the connect effect re-runs; rebuild | FAILED — `AssertionError: Locator expected to be visible … element(s) not found` — the held-stream gate saw two requests and the page never held in Waiting | PASSED — 1 passed (restored) | Proved |

### T5 transport change and its consequences for the gates

An `EventSource` request does not pass through `window.fetch`, so every
JavaScript gate that patched `window.fetch` to pause a **stream** request
stopped gating when the transport changed. Each was re-gated and re-proved:

- `test_reconnecting_status_is_announced` and
  `test_streaming_does_not_move_keyboard_focus` now hold their state with the
  SSE `retry:` field. The server closes the first connection after setting
  `retry: 2000`, so the browser waits two seconds before dialling again and the
  state is stable for the assertion.
- `test_applicable_state_matrix` and `test_accessibility_and_reflow` hold the
  Waiting state by stashing the stream `Route` and fulfilling it later from the
  test thread. The matrix check keeps its `window.fetch` patch for the Loading
  delay, which is correct: the committed-history load is still an ordinary
  `fetch`.
- `test_accessibility_and_reflow` previously blocked inside the route handler on
  a `threading.Event`. **That gate never gated.** Blocking there stalls
  Playwright's own event loop, so `stream_gate.set()` could not run until the
  wait had already expired. Measured directly: with `timeout=30` the check took
  30.62 s and with `timeout=5` it took 10.86 s — the wait ran to its full
  timeout both times. Re-gated on the stashed `Route`, the same check runs in
  0.66 s and the Waiting scan is now deterministic rather than racing the
  stream's arrival.

### T5 retired row

| Claim | Check artifact | Break attempted | Observation | Status |
| --- | --- | --- | --- | --- |
| Client-side `(run_id, seq)` deduplication is pinned by the reconnect check | `tests/browser/test_run_page.py::test_eventsource_resumes_after_forced_disconnects` | Remove the `addEvent` early return (`if (state.events[event.seq]) return state`) in `App.tsx`; rebuild | **Did not red** — 1 passed in 5.91 s with the guard removed | Retired |

This row was proved against the `fetch` client and does not survive the
transport change. The mini server pops each event from its queue and never
re-serves one, so no duplicate ever reaches the sink and removing the guard
changes nothing observable. This is not a regression in the criterion: `plan.md`
§ Design → *Stream contract and control flow* already states that row keying is
a defensive idempotency layer and that the wire assertion proves server
precedence independently of it. AC-0305's "no such reconnect emits an event
already held by the client" is a property of the wire, and the wire assertion
over `wire_captures` still proves it — the `id:`-removal break below still reds
that check. *(Superseded in round 16: the guard is not merely defensive. On the
shipped route the client opens its first stream at `after=0` with no
`Last-Event-ID`, so the route resends every event the history response already
delivered, and the guard is what keeps each row single.
`test_history_stream_overlap_renders_once` now pins it; see § Post-gates review
round 16.)*

### T5 re-observation of the T1 browser rows

Two rows in § T1 name breaks against the browser client this task replaced.
Both were re-performed against the native `EventSource` client and still red
their check, so § T1 stands as written:

- Remove `id:` from `_sse()` → FAILED — `AssertionError: wire_captures[2] =
  None; expected '3' (seq of served_events[1]). Native reconnects must carry the
  previous event's seq as Last-Event-ID.`; restored 1 passed in 5.66 s.
- Remove `page.reload()` → FAILED — `AssertionError: Expected a tab-reload
  boundary (a second None in wire captures).`; restored 1 passed in 5.58 s.

The third § T1 browser row — the `addEvent` deduplication guard — is the retired
row above.

### T5 bundle provenance

*(History. These digests describe the T5 bundle, whose asset files no longer
exist. The shipped bundle's digests are in § Post-gates review round 17 and in
`docs/ux/walking-skeleton-evidence/evidence.md` § Bundle Provenance.)*

Built from a wiped `node_modules` reinstalled with `npm ci`, so the committed
lockfile was exercised. `npm run test` (`tsc --noEmit`) passed with no output.
SHA-256 after `npm run build`:

```
e7fe53c09a16e7d0b25589aab302dda8c9874a3f2c3abef856ba5ec1533c52aa  src/ced/api/static/index.html
8203769f01861b0488c954e7417b91727b8cd625a107c4b11f7dcc76058004c4  src/ced/api/static/assets/index-r3gonaOH.js
15f07870059adf651e74f19d1aa8074db2a641b45ed4f113bdf4b5c37eb18815  src/ced/api/static/assets/index-CdSv7G3w.css
```

A second `npm run build` over the same source reproduced all three digests
exactly, which is what makes the comparison a check rather than a transcript.
`index.html` references `index-r3gonaOH.js` and `index-CdSv7G3w.css`, the two
filenames present on disk.

### T5 findings routed elsewhere

- `contracts/openapi/runs.yaml` still describes the stream frame as carrying
  "the domain event type as `event`". That is false against the shipped encoder
  after this task. The contract file is T8's `Touches`, not T5's, so the
  correction belongs to T8's reconciliation. **Closed by T8:** the published
  description now states the committed sequence as `id`, one JSON envelope as
  `data`, and no `event:` field, read against `encode_sse_event`.

## T2 offline checks (AC-0306 – AC-0311)

| Claim | Check artifact | Required break | Red proof | Restored proof | Status |
| --- | --- | --- | --- | --- | --- |
| Sample floor enforced (AC-0307) | `tests/worker/test_evidence.py::test_step_duration_measurement_refuses_an_undersized_sample` | Lower `SAMPLE_FLOOR` to 29 in `evidence.py` | FAILED — `Failed: DID NOT RAISE ValueError` for `[0.1] * 29` (29 ≥ 29 no longer raises) | PASSED — 1 passed in 0.24 s | Proved |
| Page threshold from same sample (AC-0308) | `tests/worker/test_evidence.py::test_thresholds_share_one_sample` | Compute `page_threshold` from `sorted(durations[:-1])` instead of `p99 * 3` | FAILED — `AssertionError: page_threshold 90.0 must equal p99 31.0 × 3` | PASSED — 1 passed in 0.24 s | Proved |
| Deadline sits strictly between measured limits (AC-0306) | `tests/worker/test_evidence.py::test_configured_deadline_sits_between_measured_limits` | Set `configured_step_deadline_seconds` to `0.104624` (= p99, lower boundary) in `measurements.json` | FAILED — `AssertionError: ordering violated: p99=0.104624 < step_deadline=0.104624 < page_threshold=0.313872 must hold` | PASSED — 1 passed in 0.24 s | Proved |
| Outcome from observation, not caller (AC-0309 / AC-0310) — mutation A | `tests/worker/test_evidence.py::test_cancellation_outcome_comes_from_connection_observation` | Replace `return "terminated" if observed_closed else "abandoned"` with `return "terminated"` | FAILED — `AssertionError: a stream that does not close within the window must produce 'abandoned', got 'terminated'` | PASSED — 1 passed in 0.24 s | Proved |
| Outcome from observation, not caller (AC-0309 / AC-0310) — mutation B | `tests/worker/test_evidence.py::test_cancellation_outcome_comes_from_connection_observation` | Replace body with `close_stream(); return "terminated"` (ignores `observe_closure`) | FAILED — `AssertionError: a stream that does not close within the window must produce 'abandoned', got 'terminated'` | PASSED — 1 passed in 0.24 s | Proved |
| Region from resolved client, not constant (AC-0311) — mutation A | `tests/worker/test_evidence.py::test_quota_record_uses_the_resolved_client_region` | Hard-code `region = "us-east-1"` instead of `client.meta.region_name` in `read_quota_record` | FAILED — `AssertionError: region must come from client.meta.region_name ('us-stub-2'), got 'us-east-1'` | PASSED — 1 passed in 0.24 s | Proved |
| Quota identity recorded (AC-0311) — mutation B | `tests/worker/test_evidence.py::test_quota_record_uses_the_resolved_client_region` | Remove `service_code` key from the returned dict | FAILED — `AssertionError: service_code must be 'bedrock', got None` | PASSED — 1 passed in 0.24 s | Proved |

**Three rows above are superseded and are kept only as history.** T6 replaced
the artifacts they name, so each cites a check that no longer exists under that
name, and the AC-0306 row's break value is a number `measurements.json` no
longer carries. The live evidence for those claims is in § T6.

**The same two retired names also appear in `plan.md` § Construction tests and
mutation proofs** (the `Configured deadline ordering holds` and `Cancellation
classification is observed` rows). The plan is sealed, so those rows cannot be
edited; this note is where a reader following them finds the live names. They
are the only two dangling check references left in this delivery's records — a
sweep of every `::test_*` reference across the spec, plan, this ledger, the
evidence manifest, `spikes/README.md`, `AGENTS.md`, `operations.md` and
`docs/architecture/README.md` found no others.

The mapping, for both the rows above and the plan's:

| Superseded row | Named check, now | Live evidence |
| --- | --- | --- |
| Deadline sits strictly between measured limits (AC-0306) | `test_deployed_deadline_matches_the_record_and_sits_between_measured_limits` | § T6 — the check now reads the deployed value as well as the recorded one |
| Outcome from observation (AC-0309 / AC-0310), mutations A and B | `test_cancellation_outcome_comes_from_the_reader_completing` | § T6 — restated to AC-0310's amended property, the reader completing after the body is closed |

The AC-0307 and AC-0308 rows, and both AC-0311 rows, name checks that still
exist under those names and stand as written.

### T2 thirty-step witness

`ced-evidence generate --n 30` ran against the local substrate with `stub:counting` (TestModel, no provider call).

```
{"generated": 30, "requested": 30, "pool_class": "ced-evidence-measure", "role": "ced-evidence-measurement"}
```

`ced-evidence step-duration --out docs/specs/walking-skeleton-evidence/notes/measurements.json` produced:

```json
{
  "step_duration": {
    "p99_seconds": 0.104624,
    "page_threshold_seconds": 0.313872,
    "sample_size": 30,
    "method": "nearest-rank p99, floor 30",
    "platform": "macOS 15 (arm64), local Docker Compose substrate",
    "platform_note": "Local Docker Compose substrate with stub:counting (TestModel, no provider call). Phase 1 measurement under the local-container substitution accepted in the spec Assumptions; AC-0314 names the resulting limits."
  }
}
```

`CED_STEP_DEADLINE_SECONDS` was set to `0.209248` (midpoint of `[0.104624, 0.313872]`), the Phase 1 calibrated value derived from the TestModel measurement above.

**This witness is superseded; the figures above are the 2026-09-29 observation and no longer describe the tree.** T6 found the sample unreproducible — the API suite's own fixtures delete events between tests, so `step-duration` read zero completed steps against the live event log — and AC-0307 requires `measurements.json` to be the command's actual output. The shipped figures, and why they moved, are in § T6 *re-measurement, and why the numbers moved*. `deploy/compose.yaml` carries the superseding value on both worker services; it does not carry `0.209248`.

### T2 cancellation witness (AC-0309, AC-0310)

**Unverified history — superseded by the 2026-10-01 witness in § Post-gates
review round 14.** This run cannot be shown to have measured an in-flight
stream. The command then requested a one-word reply, began draining the stream
on a reader thread *before* closing it, and admitted a stream that ended before
its first chunk as "still valid" — so a reader that had finished on its own was
indistinguishable from one the close ended, and either would have been recorded
`terminated`. It is kept, not deleted, because it is the first observation
taken; it is not shown invalid, only unverified.

`ced-evidence cancellation` ran with live AWS credentials against `us.anthropic.claude-haiku-4-5-20251001-v1:0` in `us-east-1` on 2026-09-29. First response chunk was consumed before close was initiated.

```json
{
  "cancellation": {
    "outcome": "terminated",
    "latency_seconds": 0.000533,
    "region": "us-east-1",
    "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "method": "close response body; observe reader join within 30s window"
  }
}
```

Outcome derived from `observe_closure(30)` returning `True` (reader thread joined within the window). No caller-supplied outcome was used. No AWS resources were created.

### T2 quota witness (AC-0311)

`ced-evidence quota` ran with live AWS credentials against the Service Quotas API in `us-east-1` on 2026-09-29. Quota code `L-58BE175A` was confirmed by a preceding `ListServiceQuotas` probe; the initial placeholder `L-3F12E1C1` resolved as `NoSuchResourceException`. Region taken from `client.meta.region_name`.

```json
{
  "quota": {
    "region": "us-east-1",
    "service_code": "bedrock",
    "quota_code": "L-58BE175A",
    "quota_name": "Cross-region model inference tokens per minute for Anthropic Claude Haiku 4.5",
    "value": 5000000.0
  }
}
```

No credential or account metadata written. No AWS resources were created.

## T3 analytical comparison (AC-0312, AC-0313)

| Claim | Check artifact | Required break | Red proof | Restored proof | Status |
| --- | --- | --- | --- | --- | --- |
| Analytical costs remain separate | `tests/worker/test_evaluation.py::test_rebaseline_separates_narrowing_from_boundary_loss` | In `compute_loss_breakdown`, replace return `{"narrowing_loss": ..., "boundary_loss": ...}` with `{"total_loss": {"dropped": total_dropped}}` | FAILED — `AssertionError: narrowing_loss must be a separate field; collapsing to a total removes this key and fails this assertion` — `assert 'narrowing_loss' in {'total_loss': {'dropped': 4}}` | PASSED — 1 passed in 0.27 s | Proved |

### T3 provider witness (AC-0312, AC-0313)

`python -m ced.worker.evaluation rebaseline --root . --out docs/specs/walking-skeleton-evidence/notes/rebaseline.json` ran with live AWS credentials on 2026-09-29.

Prior claim (from `spikes/README.md` § Spike 4): the spike ran with a 20-label vocabulary, 6 of 8 observations admitted after anchor resolution, and the analyst produced partial output. Hypothesis falsified: causality, table-anchor, and selection/legal-exposure losses identified.

Current observation:
- Wide run (20 spike labels): 8 pre-anchor observations, 5 admitted after anchor check.
- Narrow run (3 shipped labels): 5 pre-anchor observations, 0 admitted after anchor check (all 5 refused by anchor resolution failure).
- Narrowing loss: 8 wide\_pre − 5 narrow\_pre = 3 dropped by vocabulary narrowing.
- Boundary loss: 5 narrow\_pre − 0 narrow\_post = 5 dropped by anchor resolution.
- Analyst on full prose (A): substantive three-point analysis with 13 figures cited.
- Analyst on post-boundary (B): unable to produce analysis (0 observations crossed).

The result is **worse than the spike**: zero observations crossed the shipped boundary vs six in the spike. The comparison remains falsified. Recorded as the first valid observation; no retry. Approx cost $0.025. No AWS resources created.

## T6 measurement record against its command (AC-0306, AC-0307, AC-0309, AC-0310)

| Claim | Check artifact | Required break | Red proof | Restored proof | Status |
| --- | --- | --- | --- | --- | --- |
| The deployed deadline agrees with the recorded one — one service changed | `tests/worker/test_evidence.py::test_deployed_deadline_matches_the_record_and_sits_between_measured_limits` | Set `CED_STEP_DEADLINE_SECONDS` to `0.180000` on `worker-a` only in `deploy/compose.yaml` | FAILED — `assert {0.174862, 0.18} == {0.174862}`, extra item `0.18` | PASSED — 1 passed in 0.26 s | Proved |
| The deployed deadline agrees with the recorded one — both services changed | same | Set `CED_STEP_DEADLINE_SECONDS` to `0.180000` on both worker services | FAILED — `assert {0.18} == {0.174862}`, extra item `0.174862` in the right set | PASSED — 1 passed in 0.32 s | Proved |
| AC-0306 fails, not skips, when its evidence is gone | same, via `_read_measurements` | Rename `measurements.json` to `measurements.json.renamed` | FAILED — `AssertionError` at `test_evidence.py:61`, 2 failed 4 passed; the AC-0307 record check reds with it | PASSED — 6 passed in 0.26 s | Proved |
| The record carries only fields the command emits (AC-0307) | `tests/worker/test_evidence.py::test_the_record_carries_only_fields_the_command_emits` | Hand-edit `step_duration.platform` to `macOS 15 (arm64), …` and `platform_note` to prose no command emits | FAILED — `AssertionError` at `test_evidence.py:242`, diff shows `+ Hand-written prose that no command emits.` | PASSED after re-running the command (not after undoing the edit): `CED_STEP_DEADLINE_SECONDS=0.174862 ced-evidence step-duration --out …` restored the file **byte-identical** to the pre-break output (`diff` empty), 6 passed in 0.33 s | Proved |
| The cancellation outcome comes from the reader completing, not from a supplied value (AC-0309, AC-0310) — ignore the observation | `tests/worker/test_evidence.py::test_cancellation_outcome_comes_from_the_reader_completing` | Replace `return "terminated" if observed_closed else "abandoned"` with `return "terminated"` | FAILED — `AssertionError` at `test_evidence.py:322`, `abandoned` case got `terminated` | PASSED — 1 passed in 0.22 s | Proved |
| same — accept an operator-supplied outcome | same | Add `outcome: str | None = None` to the signature and return it when supplied | FAILED — `Failed: DID NOT RAISE TypeError` at `test_evidence.py:329` | PASSED — 1 passed in 0.22 s | Proved |

`src/ced/worker/evidence.py` was compared against its pre-mutation copy after
the last restoration and is byte-identical (`diff` empty).

**T6 gates, run against the restored tree after every break.** Each exit code
was read from the command itself, not through a pipe:
`ruff format --check .` 272 files already formatted, exit 0;
`ruff check .` all checks passed, exit 0;
`mypy` no issues in 55 source files, exit 0;
`python -m pytest` **1063 passed, 3 skipped in 269.33 s, exit 0** — one
unfiltered whole-suite process, which then exited (`pgrep -f "python -m
pytest"` found nothing). Repository checks: `lint-no-identifiers.py` clean
over tracked files, `lint-intents.py` clean, `hooks/pre-pr.py` all checks
passed, `lint-spec-status.py --root . --all` clean over 7 specs — all exit 0.

**These are T6's restoration witnesses, not the gate of record.** They describe
the tree as it stood at T6's close, two checks behind the shipping one. The
gate of record is the single run against the final tree in § Commands run; the
figures here establish only that T6's own mutations were restored.

### T6 what the deadline check reads, and what it does not

The check reads **`deploy/compose.yaml`**, not a running container. It
enumerates every service that sets `CED_STEP_DEADLINE_SECONDS` rather than
naming the two workers, so a third service added with a disagreeing value
reds it too. A container keeps the environment it was created with until it is
recreated, so this gate's claim is about what the repository deploys. The
workers running during this task still carry the previous value `0.209248`;
they were deliberately not recreated, because nothing in the suite asserts on
the deadline's magnitude — both the old and new values are far below
`CED_STEP_BODY_SECONDS: "600"`, which is what the fault-injection bodies
actually sleep for.

### T6 re-measurement, and why the numbers moved

The sample T2 recorded was **not reproducible**: `ced-evidence step-duration`
against the live substrate reported `sample too small: 0 completed step(s)`,
because the event log no longer held T2's steps. AC-0307 requires the record
to be the command's output, and the only way to produce that is to measure
again. `ced-evidence generate --n 30` then `step-duration` was run twice and
returned identical values both times, so the figures below are the command's
output and not a one-off.

| Value | T2 (2026-09-29) | T6 (2026-10-01 UTC) |
| --- | --- | --- |
| p99 (s) | 0.104624 | 0.087431 |
| Page threshold (s) | 0.313872 | 0.262293 |
| Configured deadline (s) | 0.209248 | 0.174862 |
| Platform string | `macOS 15 (arm64), …` (hand-written) | `Darwin (arm64), …` (from `platform.system()`) |

`0.174862` is the midpoint of `[0.087431, 0.262293]`.

*(Superseded for the cancellation block by § Post-gates review round 14, which re-measured it once on owner direction; the quota block still stands as written here.)* The cancellation and quota blocks were **not** re-measured: both reach AWS,
both are first valid observations under the spec's no-repeat rule, and their
recorded values and `measured: 2026-09-29` dates are preserved byte-for-byte.
What changed is that `--out` now **merges** its subcommand's own top-level keys
into the existing record instead of replacing the file, so the record's five
keys compose from three independent runs without any operator pasting a block
back by hand. The count is not one key per subcommand: `step-duration` writes
three of the five. Both commands now also emit the `measured` stamp the record
already carried.

### T6 where the deadline value now comes from

`ced-evidence step-duration` reads `CED_STEP_DEADLINE_SECONDS` from its own
environment and **refuses to measure without it** — absent, blank,
unparseable, non-finite or non-positive all fail with the variable named. It
records the value it ran with, plus a `configured_step_deadline_source` string
saying where it came from. Before this task the record's deadline had no
producer at all, which is why AC-0306 was comparing the record against itself.
`src/ced/worker/evidence.py` does not parse `deploy/compose.yaml`: `pyyaml` is
a `[dev]`-only dependency the manifest records as test-only, and reading
structured configuration by line match is an anti-pattern. The test parses it
with `yaml.safe_load`, which is where the dependency is admitted.

### T6 the step-duration sample is unscoped, and the record says so

`query_step_durations` pairs *every* `step.started` and `step.completed` in the
event log on `step_id`, with no role, pool-class, principal or time filter.
The sample is therefore whatever the event log held when the command ran, and
a step another suite completes against the same database enters a later
sample. **This happened during T6:** the whole-suite gate run that followed
the measurement left further completed steps in the event log, so re-running
`step-duration` now would draw a larger, different sample. That is a property
of the measurement, not a defect introduced here, and it is why the predicate
has to sit beside the value. The predicate now travels in the record as
`step_duration.sample_scope`, emitted by the command from the `SAMPLE_SCOPE`
constant, and the offline check asserts the recorded string equals that
constant — so changing the query without changing the statement, or editing
the statement by hand, reds the gate. The predicate was left unscoped rather
than narrowed to the measurement role: narrowing it would make the measurement
reproducible while hiding the states outside the narrowing, and the task asked
for the predicate to be recorded, not changed.

### T6 AC-0310's two limits

They are stated once, in
`docs/architecture/pydantic-ai-worker-runtime/operations.md` § Cancellation
measurement § What this measurement does not establish — the record AC-0310
names by path. This ledger cites that record rather than restating them, as the
criterion directs.

### T6 disposition of `make_references_test_model`

Kept in `src/ced/adapters/bedrock/quota.py`, with the reason now stated in its
docstring — the second of the two dispositions `plan.md` admits, chosen because
it is self-contained and the first requires amending T6's `Touches`. The reason
is true but names a debt: two constraints meet in that module. AC-0007 confines
`pydantic_ai` imports to `agents/` and `adapters/`, so the factory cannot sit
beside its only caller in `worker/`; and the module is in fact the evidence
commands' single adapter boundary — it already owns the Bedrock cancellation
stream as well as the quota read — rather than a Service Quotas module that
acquired an unrelated function. Its *name* is narrower than its
responsibility. The module docstring now says so. **Renaming the module is the
better fix and is out of scope here**, because it reaches `src/ced/worker/`
import sites and test modules beyond this task's `Touches`.

### T6 findings routed elsewhere

- Two files outside T6's `Touches` still quote the superseded T2 figures and
  are now stale against the tree:
  `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md`
  (lines ~1160–1162) and `spikes/README.md` (the AC-0306 row, line ~963) both
  carry `0.104624` / `0.313872` / `0.209248`. **Both are owned, and no
  amendment is needed:** `spikes/README.md` is T8's `Touches` and
  `runtime-architecture.md` is T4's. T8 corrected the first; T4 corrects the
  second. (T6 reported `runtime-architecture.md` as unowned; that was wrong —
  it is named in T4's `Touches` in `plan.md`.)
- The § T2 offline checks table cites three artifact names this task retired:
  `test_configured_deadline_sits_between_measured_limits` and
  `test_cancellation_outcome_comes_from_connection_observation`, and a break
  against a `measurements.json` value that no longer exists. The § T6 rows
  above supersede those three rows. The § T2 section is T2's evidence and was
  left as written; correcting the dangling names belongs to T8's
  reconciliation, which owns this file. **`plan.md` § Construction tests and
  mutation proofs carries the same two names**, and the plan is sealed — the
  supersession note under § T2 records the mapping for both sites.
- `docs/architecture/pydantic-ai-worker-runtime/operations.md` is in both T6's
  and T8's `Touches`; T8 should re-read the step-duration and deadline sections
  against the final tree, since T6 rewrote the figures in them.

### T6 cut-before-adding search

`rg -n "safe_load|compose.yaml" src tests` (rung 2, bounded to this
repository) found one precedent for reading the deployed environment:
`tests/thinking_reaches_the_model/test_the_deployment_declares_its_stub.py`'s
`_environment(service)`, which `yaml.safe_load`s `deploy/compose.yaml`. Its
*shape* was reused — the same library, the same file, both worker services
rather than the one a reader happens to check — but not the function itself: it
is a private helper in another test package, and it resolves one **named**
service, while AC-0306 must read every service that sets the variable so an
added service cannot escape the check. The ladder stopped at rung 5, an
already-installed dependency: `pyyaml==6.0.3` is in `[project.optional-dependencies] dev`,
so no dependency was added. The search also confirmed no existing helper
merges JSON records, which is why `_write_record` is six lines in the module
that owns the record rather than a new utility.

## T7 analytical comparison schema (AC-0312, AC-0313)

### T7 where the key set came from

The producer tuple's key set was read from the shipped builder —
`build_producer_tuple`'s `return` statement in `src/ced/worker/evaluation.py`,
lines 298–307 — and not from any prose list. It is
`provider`, `model_id`, `model_revision`, `model_adapter`, `framework_version`,
`fixture_sha256`, `role_revision`, `prompt_revision`. The committed record
`notes/rebaseline.json` carries the same set, which corroborates the read.

`tests/worker/test_evaluation.py` asserts `set(producer) == EXPECTED_PRODUCER_KEYS`
rather than a containment check per key. A containment check cannot fail when a
key is deleted from the builder, so it would keep confirming whatever list the
test author happened to write; set equality also reds an undeclared key being
added.

The loss categories are pinned the same way, as
`set(categories) == {"causality", "table_anchor", "selection_legal"}` in **both**
`narrowing_loss` and `boundary_loss`, plus a non-empty-string check on each
category's recorded content.

### T7 mutation witnesses

Each break was applied on its own against a pristine copy of
`src/ced/worker/evaluation.py`, the owning check was run, the file was restored,
and the check was re-run. `src/ced/worker/evaluation.py` is outside T7's
`Touches` for authoring; it was mutated only to earn these reds. No break stands
in for another.

| Break | Owning check | Red proof | Restored proof |
| --- | --- | --- | --- |
| Delete `"provider"` from `build_producer_tuple` | `test_producer_tuple_emits_exactly_the_recorded_key_set`, `test_producer_tuple_values_are_the_arguments_and_the_recorded_defaults` | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `"model_id"` | same two checks | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `"model_revision"` | same two checks | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `"model_adapter"` | same two checks | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `"framework_version"` | same two checks | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `"fixture_sha256"` | same two checks | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `"role_revision"` | same two checks | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `"prompt_revision"` | same two checks | FAILED — exit 1, 2 failed, 7 passed | PASSED — exit 0, 9 passed |
| Delete `narrowing_loss.categories["causality"]` | `test_rebaseline_separates_narrowing_from_boundary_loss` | FAILED — exit 1, 1 failed, 8 passed | PASSED — exit 0, 9 passed |
| Delete `narrowing_loss.categories["table_anchor"]` | same check | FAILED — exit 1, 1 failed, 8 passed | PASSED — exit 0, 9 passed |
| Delete `narrowing_loss.categories["selection_legal"]` | same check | FAILED — exit 1, 1 failed, 8 passed | PASSED — exit 0, 9 passed |
| Delete `boundary_loss.categories["causality"]` | same check | FAILED — exit 1, 1 failed, 8 passed | PASSED — exit 0, 9 passed |
| Delete `boundary_loss.categories["table_anchor"]` | same check | FAILED — exit 1, 1 failed, 8 passed | PASSED — exit 0, 9 passed |
| Delete `boundary_loss.categories["selection_legal"]` | same check | FAILED — exit 1, 1 failed, 8 passed | PASSED — exit 0, 9 passed |

Every pinned key's deletion reds its owning assertion. No key is uncovered.

After the last restoration, `diff` against the pristine copy was empty and the
SHA-256 of `src/ced/worker/evaluation.py` was
`068c37c9d534f85368ae01f700295fc520d0f65df87316ebdc7c127c6235fb56`, equal to the
pre-mutation value. `git status --porcelain` reports the file as staged-added
with no unstaged modification, so the working-tree copy equals the committed
content.

### T7 no provider call

The analytical comparison was not rerun. `notes/rebaseline.json` is byte-identical
to its committed content — `git status --porcelain` shows no unstaged change to
it. T7 is pure construction testing against the committed record: no AWS
credential was used and no spend was incurred. The recorded result is
**falsified**, and that is the outcome of record.

### T7 the two limits now stated in the record

`notes/rebaseline.md` § Limits of this result now states that the loss
categories are asserted rather than derived per run — the check pins the keys
and their recorded content, not that a fresh run would re-derive them — and that
narrowing loss is a difference between two independent single model calls, so it
bounds rather than isolates the vocabulary effect. Neither restates AC-0310's
limits or the substitutions `operations.md` owns.

### T7 findings routed elsewhere

- `compute_loss_breakdown`'s docstring in `src/ced/worker/evaluation.py` (around
  line 213) says anchor checking is excluded "so the vocabulary effect is
  isolated". That contradicts the limit the record now states: two independent
  calls bound the effect rather than isolate it. The module is outside T7's
  `Touches`, so the wording was left alone. T8, or a follow-on that owns the
  module, should correct the docstring to say "bounds".

## T8 record reconciliation

Controller-owned. This task states no new claim about behaviour; it removes
claims the tree does not support and re-records every gate figure from one run
against the final tree. Verification is by reading each record against its
subject, which is why no mutation row appears here.

| Record | What was wrong | What it says now |
| --- | --- | --- |
| `contracts/openapi/runs.yaml` — `stream_events` `description` | Said each frame carries "the domain event type as `event`", which the shipped encoder stopped emitting | States the committed sequence as `id`, one JSON envelope as `data`, and **no** `event:` field, with the reason. Checked by reading the published description against `encode_sse_event`; no gate compares operation descriptions, so nothing reds on this |
| `contracts/openapi/runs.yaml` — `start_run` `x-spec` | Pointed the whole operation at this spec's browser section, though `walking-skeleton-foundation` owns `start_run` | The operation-level back-reference is removed and the pointer is scoped to the `400` response, which is the only part of that operation this delivery adds |
| `docs/ux/walking-skeleton-evidence/evidence.md` — Routes | Claimed the stream route was "verified by `test_eventsource_resumes_after_forced_disconnects` via mini server proxy" | Names `tests/api/test_event_stream.py` as what reaches the shipped route, and states that the browser reconnect run is re-routed to a fixture server and establishes the client half only |
| `spikes/README.md` — AC-0305 row | Read as though wire precedence was proved against the shipped route | Distinguishes what the browser *sends* (proved on the wire at the fixture server) from the route's own preference (proved by `test_last_event_id_precedes_query_cursor`) |
| `spikes/README.md` — AC-0337 row | "an axe-core scan reporting no violation", without saying where it ran | **Superseded by § Post-gates review round 8**, which widened the scan: the row now states that every supported state is scanned, Loading included, against every A/AA-tagged axe rule. What this cell first recorded — five states plus Reconnecting, with Loading uncovered — was true when T8 wrote it and is kept as history |
| `spikes/README.md` — cancellation residual | Restated AC-0310's limits, and had already drifted: it carried the local-observation limit and dropped the unreachable `abandoned` branch | Cites `operations.md` § Cancellation measurement → *What this measurement does not establish*, which is the record AC-0310 names |
| `spikes/README.md` — AC-0306/0307/0308 row | Carried the superseded T2 figures | Carries the shipped figures and names both Compose services as what the check reads |
| This ledger — § Commands run | Carried T5's per-task figures, plus two split-invocation rows that measured a filter rather than a gate | One run against the final tree. The split is described, with no figure, and the reason it is not a figure |
| This ledger — § T2 | Three rows cite checks T6 renamed, and a `measurements.json` value that no longer exists; the thirty-step witness said Compose carries `0.209248` | Both are marked superseded with a pointer to § T6, and the rows that still stand are named so the marking cannot be read as retiring all of them |
| `workspace.toml` | `stream-contract-description-still-names-the-event-field` was open, and its own text named T8 as its closer | Moved to `[backlog].closed` with what closed it. The entry stays the durable mirror of the 2026-09-30 owner decision: closing the defect does not retract the authority |

`cancellation-observes-local-reader-not-provider-connection` remains in
`[backlog].open`, which is where `spec.md` § Follow-ons, § Changelog, and
`state.json`'s first `amendment_history` entry all say it lives. It is the
owner authority for the AC-0310 amendment and is not closed by this delivery —
what it owes is transport-level observation, which is deployment-side work.

One finding is routed out rather than fixed: `compute_loss_breakdown`'s
docstring in `src/ced/worker/evaluation.py` says anchor checking is excluded
"so the vocabulary effect is isolated", which contradicts the bound-not-isolate
limit `rebaseline.md` now records. That module is outside every open task's
`Touches` in this sealed plan, so correcting a comment there would have widened
a pinned contract. Recorded in `workspace.toml` `[backlog].open` as
`narrowing-loss-docstring-claims-isolation-the-method-does-not-reach`, owed by
the next change that owns the module. No behaviour and no check is affected.

## Post-gates review round 3, and the three accessibility breaks it forced

Adversarial review sustained 11 findings against the final tree; the
adjudication refuted none. Two were blockers, and both were about a claim being
stronger than its evidence rather than about behaviour.

### The focus-indicator clause rested on an assertion that could not red

`page.locator(":focus-visible").count() == 1` observes a **user-agent focus
state**, not an author style, so it matches with every focus rule removed.
AC-0337's "exposes a visible keyboard focus indicator" clause was pinned by it
and by nothing else. The check now also reads the focused element's computed
`box-shadow` and `outline`, which is what makes the clause observable.

Proving it took two mutations, and the first is worth recording because it
*correctly* stayed green:

| Break | Result | Reading |
| --- | --- | --- |
| Delete the `box-shadow: var(--ds-focus-ring)` rule from `styles.css` (the author indicator), rebuild | **PASSED** — 1 passed in 3.41 s | Not a false negative. Removing the author rule also removes its `outline: 0`, so Chromium paints its own focus ring: the element still has a visible indicator, which is what the criterion asks for |
| Append `*:focus-visible { outline: 0 !important; box-shadow: none !important; }`, rebuild | FAILED — `AssertionError: the focused element paints no focus indicator: box-shadow='none', outline='none' '0px'` | The real defect class — no indicator at all, author or UA |

Restored: 1 passed in 4.87 s, and `styles.css` is byte-identical to its
pre-mutation copy.

### The other two construction-table breaks

`plan.md` § Construction tests names "Remove the focus style, status
semantics, or narrow-width wrapping rule **in turn**" as this check's required
break. None of the three had been recorded.

| Break | Red proof | Restored |
| --- | --- | --- |
| Remove `role="status"` / `aria-live="polite"` from the status paragraph in `App.tsx`, rebuild | FAILED — `AssertionError: Locator expected to be visible … waiting for get_by_role("status")` | 1 passed in 5.01 s |
| Change `overflow-wrap: anywhere` to `normal` at all three sites in `styles.css`, rebuild | FAILED — `assert True is False` on the 640 px horizontal-overflow check | 1 passed |

### The reflow assertion could not red until its fixture changed

The narrow-width break above does not red the check as the check stood. Two
mutations were run against the original fixture and **both stayed green**:
dropping `.event-row`'s single-column rule from the ≤42 rem media query, and
neutralising `overflow-wrap` at all three sites. The cause was the data, not
the rule: every value the check rendered was a short word like `operator`, so
the browser had word boundaries to break at and no wrapping rule was
load-bearing.

A diagnostic over `payload_ref` lengths 40, 60, 71, 90 and 120 characters
confirmed the page itself reflows correctly at 640 px at every length — the
document's `scrollWidth` stayed at 640 with no overflowing element, so there
was no product defect here, only an unfalsifiable check. Round 3 changed the
check to render an unbroken 120-character `payload_ref` and justified that by
AC-0322's literal-rendering requirement, and the wrapping break red it.

**Both halves of that sentence are superseded — see § `The reflow fixture now
uses the shape the system emits` below.** Round 4 found the justification wrong
(AC-0322 governs escaping and says nothing about length or breakability) and
the fixture needlessly synthetic; round 5 then found this passage still
describing the replaced fixture. The check now renders
`ced-step-lifecycle/<64 hex>`, the 83-character key `write_payload_bytes`
actually emits, and the break is re-proved at that length.

**One measurement in this round was mine and was wrong.** An intermediate
"baseline" run reported red with the long value and no mutation, which would
have meant a real reflow defect. It was an artifact: `styles.css` had been
restored but the bundle had not been rebuilt, so the served assets still
carried the previous mutation. Rebuilt, the baseline is green. Recorded because
a stale bundle is invisible in the diff and reads exactly like a product fault.

### Records corrected in the same round

Seven sustained findings were record defects, each fixed where the record is
read: the AC-0304 row in `spikes/README.md` claimed the terminal-close check
reaches the shipped `ced-api` when its events are fulfilled by the test; the
quota measurement had no substitution bullet, which AC-0314 fails a record for
omitting; the stream route's per-viewer threadpool and connection cost was
recorded nowhere; the High-zoom trigger is met by viewport equivalence rather
than driven; the Reconnecting state is now scanned in
`test_reconnecting_status_is_announced`, the only check that holds it open; the
client's `terminalEvents` duplication is recorded as uncovered; and
`cancellation.measured` / `quota.measured` are recorded as operator-recorded
dates no subcommand run produced. *(The cancellation date is no longer operator-recorded: the round-14 re-run stamped it itself. Only the quota date still is.)*

**That last one was first fixed in the wrong place.** A `measured_source` key
was added to both blocks in `measurements.json`, and the record-shape check
caught it — `AssertionError: unexpected cancellation fields` — because the
check's whole point is that every field in that file is one a subcommand
emits, and a hand-written explanation of a hand-written field is still a
hand-written field. The provenance now lives in
`docs/architecture/pydantic-ai-worker-runtime/operations.md`, the record that
owns the measurement, and `measurements.json` is back to command-emitted
fields only. The check behaved exactly as designed; it is recorded here
because the failure is the evidence that it works.

After the fixes the whole suite was re-run unfiltered in one process. Figures
are in § Commands run, which carries one run against the final tree.

## Post-gates review round 4

The previous round's fixes were themselves reviewed. Eight findings, all
sustained and none refuted. Two were blockers, and both were introduced *by*
the round-3 fixes rather than surviving them.

### Fixing the reported site and leaving its sibling

Round 3 corrected worker-a's Compose comment to say no service arms a timer
from `CED_STEP_DEADLINE_SECONDS`. **worker-b's comment forty-seven lines below
still read "The second service that exercises the calibrated deadline"** — the
very claim the finding was raised against — so one file shipped both readings.
worker-b now states the same relationship and points at worker-a for the
provenance and for the path that does arm the timer.

### A record contradicting its own evidence

The manifest said the computed-style focus assertion "reds when the
`box-shadow: var(--ds-focus-ring)` rule is deleted". The ledger's witness table
in § Post-gates review round 3 records that exact deletion as **PASSED**, with
the reason. Both statements were written in the same session. The manifest now
states the defect class the assertion actually reds on — no indicator at all,
author or user-agent — and records the author-rule deletion as correctly
passing. It also names what no check distinguishes: loss of the *author*
indicator alone, as against the user-agent fallback.

### The Reconnecting scan had no break of its own

The manifest claimed the new Reconnecting WCAG scan was proved by "the same
mutation that pins the status text". It is not: changing
`labelFor("reconnecting")` fails the heading expectation *before* `axe.run()`
is reached, so that break proves nothing about the scan. Proved properly:

| Break | Red proof | Restored |
| --- | --- | --- |
| Render `<button type="button" />` (unlabelled) in every state, rebuild, run `test_reconnecting_status_is_announced` alone | FAILED — `AssertionError: WCAG 2.2 A/AA violations in reconnecting state: [critical] button-name: Ensure buttons have discernible text` | 1 passed in 5.65 s |

Running that check alone is what isolates the scan: the violation is present in
every state, so only this check's scan can be the one that caught it.

### The reflow fixture now uses the shape the system emits

Round 3 justified its unbroken 120-character `payload_ref` by AC-0322's
literal-rendering requirement — which is about escaping, and says nothing about
length or breakability. The fixture now carries
`ced-step-lifecycle/<64 hex>`, the 83-character key `write_payload_bytes`
actually produces, whose 64-character digest is the unbreakable run. The
wrapping break still reds at that length (`assert True is False` on the 640 px
overflow check), so the break is proved at the length the system really
produces rather than above it.

### Four stale citations

`test_accessibility_and_reflow`'s docstring listed two mutations whose recorded
witnesses contradict it, including the focus one this delivery disproved and a
status-semantics one it attributed to an axe scan when the real witness is a
locator expectation that runs after every scan. The manifest's Keyboard-only
row still certified the focus clause with the superseded `:focus-visible`
count. `tests/worker/test_evidence.py`'s docstring cited `measurements.json`
and § T6 for a provenance statement that lives in `operations.md` § Cancellation
measurement and in § Post-gates review round 3. The § T1 table named
`test_the_contract_file_describes_five_routes`, which exists nowhere. All four
now name what the tree holds.

### A procedural stop worth recording

The first adjudication of this round was refused by strict classification —
`invalid (indeterminate-audit-not-none)` — because it appended a
verification-posture note after `## Indeterminate audit`. The envelope grammar
admits no prose outside its three sections, and the artifact may not be trimmed
to make it parse, so the round stopped. Recovered on owner direction by
re-adjudicating the same eight unchanged source findings into a valid envelope.
Both artifacts are retained: the refused one as
`4-post-gates-adversarial-reviewer-adjudication.invalid-envelope.md`.

## Post-gates review round 6

Eight findings, all sustained, none refuted. **The first in three rounds to
name a defect in shipped code rather than in a record.**

### `selected_cursor` coerced a malformed `Last-Event-ID` (AC-0323)

`int(raw)` is not a test for "is an integer". It parses `1_0` as 10, strips
surrounding whitespace, accepts a leading `+`, and accepts non-ASCII decimal
digits — so a header the caller never sent resolved to a cursor and opened a
stream. AC-0323 refuses exactly that ("rather than coercing the value"), and
the committed contract fixes the same outcome independently by declaring the
header `type: integer, minimum: 0`. The guard is now lexical:
`raw.isascii() and raw.isdigit()`.

| Break | Red proof | Restored |
| --- | --- | --- |
| Replace the lexical guard with a plain `try: int(raw)` | FAILED — 3 of the then-5 parametrized cases (`-1`, `+1`, `0_2`). Re-observed in round 7 rather than asserted: the three do **not** share a failure shape, which the first recording wrongly implied. See § Post-gates review round 7 for the per-case texts | restored green |

**Two things about this proof are worth recording, because both were wrong on
the first attempt.**

*The first parametrization proved nothing.* `1_0`, `" 3 "` and `+4` coerce to
10, 3 and 4, and the run's highest committed sequence is 2 — so under the
mutation all three were still refused, by the **bounds** guard, and the check
passed for a reason unrelated to the branch under test. Only values coercing
to within the committed range can red it: the cases are now `+1` and `0_2`.

*One spelling the function refuses is unreachable over HTTP; the other claim
in this paragraph was wrong and round 7 corrected it.* Surrounding whitespace
is stripped from a header value by the HTTP layer before the application sees
it (RFC 7230), so `" 2 "` arrives as `"2"`, legitimately opens a stream, and
was observed to time out the check rather than refuse. That half stands.

**The `isascii()` half did not.** It read: a non-ASCII decimal digit cannot be
sent at all, because header values are latin-1 — true of `٣`, and the
conclusion drawn from it, that the `isascii()` arm is "defence at the function,
not wire-observed coverage", was false. `str.isdigit()` is also true of
characters `int()` cannot parse, and one of them — `²`, U+00B2 — *is* latin-1
encodable and does reach the arm. See § Post-gates review round 7.

*The negative branch is gone, not forgotten.* `-1` fails the lexical test, so a
`cursor < 0` guard after the parse would be unreachable. A guard no input can
trip reads as live protection while proving nothing, so it was removed and the
lexical predicate carries both obligations — with `-1` kept as one of its
driven cases.

### Two construction-table breaks had never been recorded

Both were named in `plan.md` § Construction tests and neither appeared in this
ledger. Performed now:

| Claim | Break | Red proof | Restored |
| --- | --- | --- | --- |
| Phase 1 keeps the loopback default bind (AC-0338) | Change `CED_API_HOST`'s default from `127.0.0.1` to `0.0.0.0` in `src/ced/api/main.py` | FAILED — `AssertionError: assert '0.0.0.0' == '127.0.0.1'` | 3 passed in 0.52 s |
| The cursor guard's lexical branch (AC-0323) | The `try: int(raw)` replacement above | FAILED — as recorded above | 10 passed in 1.98 s |

The second closes the construction table's "remove **each** validation branch"
obligation: the negative branch no longer exists, the lexical branch is proved
here, and the bounds branch was proved in § T5.

### The axe scan does not measure the conformance level it named

**Superseded — both figures in this paragraph are wrong, and § Post-gates review round 8 replaces it.** "All 104 default rules" was the registered count; a bare `axe.run()` evaluates 89. "Anything A or AA is inside the default set" was false: eight A/AA rules sit outside it. Kept as history.

`axe.run()` is called with no `runOnly`, so the installed axe-core 4.10.3 runs
all 104 default rules, 30 of them tagged `best-practice` rather than WCAG. The
direction was always safe for AC-0337 — anything A or AA is inside the default
set — but the record claimed the scan "targets WCAG 2.2 A and AA rules" and
every failure message said `WCAG 2.2 A/AA violations`. Both now say what runs:
the message reads `axe-core violations in <state> state`, and the manifest
records that the scan establishes "no axe-core default-set violation", of which
AC-0337's clause is a subset.

### Records corrected

The OpenAPI header claimed AC-0009 compares the routes the application
*serves*; it compares generated paths, and this delivery adds two served routes
absent from the schema — the browser page, registered `include_in_schema=False`,
and the `/static` mount. The header now names both and says each is covered by
its own check. `AGENTS.md` and two docstrings in `src/ced/worker/evidence.py`
said `--out` merges "one top-level key" per subcommand; `step-duration` writes
three of the record's five. The round-4 reflow finding was misattributed to
round 5. § T6's gate figures are now marked as that task's restoration
witnesses rather than reading as a second gate of record.

## Post-gates review round 7

Seven findings, all sustained, none refuted. Recorded past the review retry cap
on the owner's explicit direction of 2026-10-01, using
`--allow-retry-cap-override` on both the `findings-remain` transition and the
matching `review record` — passing it to one half alone leaves the engine and
the cohort a round apart.

### The `isascii()` arm was live, wire-reachable, and undriven

Round 6 added `raw.isascii() and raw.isdigit()` and deferred the non-ASCII case
on the premise that a non-ASCII digit cannot traverse an HTTP header. **That
premise was true only of non-ASCII *decimal* digits.** `str.isdigit()` is also
true of characters `int()` cannot parse at all, and one of them — `²`, U+00B2 —
*is* latin-1 encodable, so it reaches the guard. With `isascii()` removed it
passes the digit test, reaches `int()`, raises `ValueError` uncaught, and the
route answers **500** where AC-0323 requires 422.

Shipped behaviour was correct throughout — the guard refuses `²` today. What
was wrong is that no case drove the arm, so the construction table's "remove
each validation branch" was unmet for it, and the record read as coverage.

| Break | Red proof | Restored |
| --- | --- | --- |
| Remove `isascii()` from the guard, leaving `raw.isdigit()` | FAILED — `assert 500 == 422` on the `²` case | 11 passed in 2.91 s |

### Re-observed per-case failure texts, because the first recording asserted them

The round-6 row said the plain-`int()` mutation made three cases "return 200
instead of 422". Adjudication found that claim unverified and its proposed
replacement — a uniform `TimeoutError` — equally wrong. Re-run case by case:

| Case | Observed under the plain-`int()` mutation |
| --- | --- |
| `-1` | `assert 200 == 422` |
| `+1` | `assert 200 == 422` |
| `0_2` | `TimeoutError: timed out` — coerces to 2, the run's highest committed sequence, so the stream opens and polls |
| `²` | **PASSED** — `int("²")` raises `ValueError`, so that mutation still refuses it. `²` reds the `isascii()` mutation above, not this one |
| `not-an-integer`, `3` | PASSED — refused by the surviving branches |

Two mutations, two disjoint case sets: the coercion cases pin the lexical
predicate, `²` pins the `isascii()` conjunct. Neither substitutes for the
other, and the round-6 row's "3 of 6" denominator was wrong — the
parametrization held five cases then and six now.

### The axe scan is inexact in both directions, and the record now says so

**Superseded by § Post-gates review round 8.** This section counted three skipped A/AA rules and 96 evaluated; the measured figures are eight and 89, because axe also excludes rules tagged `experimental`. It also recorded the gap rather than closing it — round 8 widened the scan so every A/AA rule runs. Kept as history.

`axe.run()` with no `runOnly` evaluates the **enabled** default set: axe-core
4.10.3 registers 104 rules and ships 8 `enabled: false`, so 96 run. That is
wider than WCAG 2.2 A/AA — best-practice rules are included — and also
**narrower**, because three of the disabled eight carry A/AA tags:
`aria-roledescription` (`wcag2a`), `audio-caption` (`wcag2a`) and `target-size`
(`wcag22aa`, WCAG 2.2 AA 2.5.8 Target Size (Minimum)).

So "anything A or AA is inside the default set", which § Post-gates review
round 6 asserted, is false. AC-0337's A/AA clause is machine-covered only for
the A/AA rules the default set enables. 2.5.8 now appears in the manifest's
unverified new-in-2.2 list, and the manifest's claim that the retry button
clears 24 CSS pixels is marked as author assertion read off the stylesheet
rather than a measured result — `target-size` is precisely the rule that would
measure it.

### Four sibling sites of already-corrected claims

`spikes/README.md` still called the scan a "WCAG 2.2 A/AA scan" — the third
site of a claim round 6 corrected in two. § T6 of this ledger still said `--out`
merges "one top-level key" and that "three keys compose" — the fourth site of
that claim, inside the file recording its correction. Three recorded axe
witnesses quoted the pre-rename failure message; each is now marked as
predating the rename rather than re-quoted, since the witness text is history.
The round-6 reachability paragraph is restated to the characters it covers.

## Post-gates review round 8

Five findings, all sustained, none refuted. Recorded past the retry cap on the
owner's direction, with `--allow-retry-cap-override` on both halves. Two were
code-or-test defects; one was the question of whether AC-0337 could stay
ticked at all.

### The `after` source was still coerced (AC-0323)

Round 6 made the header strict and left the query open. `after` is a FastAPI
`int`, and pydantic's lax `int` turns `0_1`, `1.0` and `+1` into 1 before the
handler runs — so `selected_cursor` received `str(1)`, clean digits, and its
lexical guard had nothing to refuse. `?after=0_1` opened a stream.

The fix installs the control at the class, not the source: the handler passes
the **raw query string** to `selected_cursor`, so one predicate judges both
sources. The typed `after: int = Query(ge=0)` parameter stays, which is what
keeps the generated schema at `integer, minimum: 0` — the contract-agreement
check stayed green throughout.

| Break | Red proof | Restored |
| --- | --- | --- |
| Pass the parsed `str(after)` to `selected_cursor` instead of the raw query string | FAILED — all three of `0_1`, `1.0`, `%2B1`: `assert 200 == 422` | 23 passed across the stream and contract modules |

Every case coerces to 1, inside the run's committed range, so the bounds guard
cannot answer for it — the trap round 6 fell into first.

### AC-0337 is now met as written, not narrowed

The adjudication found AC-0337 ticked while its own record said the clause was
only partly met, and identified the decision: either a scan satisfies the
criterion as written, or the owner narrows it under § Boundaries → Ask first.
**A scan that satisfies it as written exists, so no owner decision was
needed.**

Measured in a real browser against the installed axe-core 4.10.3:

| Configuration | Rules evaluated | A/AA rules skipped |
| --- | --- | --- |
| Bare `axe.run()` | 89 of 104 registered | 8 — three `enabled: false`, five tagged `experimental` |
| `runOnly: {type: 'rule', values: <every A/AA-tagged id>}` | 69 of 69 A/AA rules | none |

Every scan now goes through `_scan_wcag_a_aa`, which uses the second
configuration, and a Loading-state scan was added by holding the first history
request on a stashed `Route`. All seven supported states are scanned against
all 69 A/AA rules, and **none reports a violation** — including `target-size`,
so 2.5.8 moved from asserted to measured without any page change.

The risk going in was that forcing the eight rules on would expose a real
defect. It did not: every state came back clean.

| Break | Red proof | Restored |
| --- | --- | --- |
| Unlabelled `<button>` in the Loading branch only, rebuild | FAILED — `WCAG 2.2 A/AA violations in loading state: [critical] button-name` | 1 passed in 3.04 s; bundle checksums byte-identical to the committed ones |
| Revert the helper to a bare `axe.run()` | FAILED — `axe registered 69 WCAG A/AA rules but did not evaluate ['aria-roledescription', 'audio-caption', 'css-orientation-lock', 'label-content-name-mismatch', 'p-as-heading', 'table-fake-caption', 'target-size', 'td-has-header']` | restored green |

The second row is the point of the helper. A scan that merely reports no
violations would stay green if axe quietly stopped evaluating a rule; asserting
that every listed rule *ran* turns shrinking coverage into a failure. Its red
output also independently confirms the reviewer's list of eight.

**Two things went wrong while proving this, and both are recorded.** The first
attempt at the Loading break failed to build — a sibling element inside
`{cond && ( … )}` is a JSX syntax error — and the test then ran green against
the *previous* bundle. Reading the build's exit code is what caught it; a green
check over a stale bundle is evidence of nothing. And one run of the
accessibility check took 34 s against a usual 3–6 s; per-scan timing showed
each scan at 0.02–0.04 s and three re-runs at 2.9–5.7 s, so it was a cold start,
not a hidden timeout.

### Records rewritten rather than patched

Round 6 and round 7 each corrected the axe claims site by site, and each time a
sibling survived. `docs/ux/walking-skeleton-evidence/evidence.md`
§ Accessibility Result was rewritten as one block — what the scan evaluates,
which states, the mutation proofs, and what no automated scan reaches — instead
of patched again. Widening the scan reversed several claims at once: 2.5.8 is
measured, Loading is scanned, and the failure message names WCAG 2.2 A/AA
again, so the "predates the rename" markers added in round 7 were themselves
false and were removed. The § Post-gates review round 6 and round 7 axe
sections are marked superseded in place.

## Post-gates review round 9

No blockers. Four findings, all sustained, none refuted. The reviewer also
recorded spot-checks that **held**, which bear on whether round 8's
structural changes were sound: the A/AA tag list selects exactly 69 rules in
axe-core 4.10.3 (that version has no `wcag22a` tag, and no selected rule is
`best-practice`); in every state `incomplete` was empty and `target-size`
landed in `passes`, never `inapplicable`, covering the Retry button; and the
Loading scan runs while the page is genuinely in Loading.

### An outranked `after` is now validated (owner decision)

With a valid `Last-Event-ID` present, `after` is not the cursor used. A
malformed one got opposite answers: `after=0_1` → 200, because the lexical
check judged only the selected source; `after=-1` or `abc` → 422 from FastAPI's
typed parameter, before the handler ran. Adjudication ruled AC-0323 silent on
the point and the case a design call. The owner chose to refuse it — see
§ Owner decisions. Every supplied cursor is now judged lexically; the bounds
check stays on the selected cursor only, as AC-0323 states.

| Break | Red proof |
| --- | --- |
| Judge only the selected source lexically | FAILED — both `0_1` and `1.0` with a valid header: `assert 200 == 422` |

### The negative and non-numeric `after` cases, and why no single break reds them

These two were claimed in `spikes/README.md` but driven by no stream-route
check. They are now. Measured, they are held by more than one layer each, so
the record says that rather than implying one mutation proves them:

| Break | `after=-1` | `after=abc` |
| --- | --- | --- |
| Remove `Query(ge=0)` only | still 422 — the lexical check refuses it | still 422 |
| Remove `ge=0` **and** bypass the lexical check | **FAILED** — `assert 200 == 422` | still 422 — FastAPI's `int` type cannot parse `abc` |

`abc` reds only if `after` stops being declared `int`, which would change the
published schema. The check therefore pins the observable 422, not a layer.
**The docstring first claimed that removing both named layers would red both
cases; the measurement showed `abc` has a third**, and the docstring and this
record were corrected to what was observed.

### Records

The rewritten § Accessibility Result opened with "Six of the state matrix's
supported states" above a table of seven — a prose total surviving inside the
very rewrite meant to stop drift. The total was dropped rather than corrected.
The § T8 reconciliation row still described the AC-0337 row as leaving Loading
uncovered; it is marked superseded in place. The `spikes/README.md` AC-0323 row
now states which refusals this delivery's checks prove and which rest first on
FastAPI's typed parameter.

## Post-gates review round 10

No blockers. Four findings: three sustained, one refuted. The reviewer
confirmed that cursor selection, the selected-only bounds check, and the
multi-layer `-1`/`abc` account all hold.

**Refuted:** the "three terminal types" cardinal in the evidence manifest.
`AGENTS.md` § Repository checks admits a mid-sentence cardinal that quantifies
a set its own sentence names, and the count is accurate. Refuted findings are
not acted on, so it stands.

### The served 422 description disagreed with the committed one

The 422 text was widened in `contracts/openapi/runs.yaml` for the 2026-10-01
owner decision, but the route's `responses=` mapping in `src/ced/api/main.py` —
what `/openapi.json` actually publishes — still carried the pre-decision
wording. `tests/api/test_contract_agreement.py` compares response codes, not
descriptions, so no gate saw it. The served text now matches the committed text
exactly; checked by comparing `app.openapi()` against the YAML, whitespace
normalised: equal.

### A repeated `after` escaped the lexical check (owner decision reaches it)

FastAPI and `query_params.get` both bind a repeated parameter to its last
value, so `?after=x&after=1` passed while `?after=1&after=x` was refused. The
adjudication ruled that the recorded owner decision — "every supplied cursor is
judged lexically" — already covers the first value of a repeated parameter, so
this needed no new decision. The handler now passes `query_params.getlist`, and
`selected_cursor` judges every value; the last remains the selected `after`.

| Break | `after=0_1&after=1` | `after=1&after=0_1` |
| --- | --- | --- |
| Pass only the last value | **FAILED** — `assert 200 == 422` | still 422 — the last value is the malformed one |

The second case is the order the previous code already refused; it guards
against regressing that order, so it is correct that this mutation leaves it
green.

### A test docstring recorded the wrong failure text

`test_after_cursor_ahead_of_highest_seq_is_refused` said its bounds mutation
fails with `assert 200 == 422`. It does not: `after=3` opens a stream past the
last committed event that polls forever, so the failure is
`TimeoutError: timed out` on the socket read, which is what this ledger and the
manifest already recorded. The docstring now says so.

## Post-gates review round 11

No blockers. Two findings, both sustained, both determined by existing
authority. The reviewer confirmed `selected_cursor` has one caller and that
`after_values[-1]` is exactly the value FastAPI binds, so the bounds check and
the stream start agree.

### An empty `after` value reopened the order dependence

The lexical loop skipped `""` for every source, so `?after=&after=1` returned
200 while `?after=1&after=` was refused by FastAPI's typed `int`. Round 10's
fix had closed order dependence for a malformed value and left it open for an
empty one. An empty `after` value is one the caller wrote into the query, so
it is supplied and malformed; it is now refused. Round 11 left the header's
empty case as "absent", on the stated ground that an `EventSource` that has
seen no `id:` sends "no `Last-Event-ID`, or an empty one". **That ground was
false, and round 12 reversed the rule** — see § Post-gates review round 12.

| Break | `after=&after=1` |
| --- | --- |
| Treat an empty `after` value as absent | **FAILED** — `assert 200 == 422` |

Boundaries checked directly against `selected_cursor` at the time: a valid
header outranks `after`, and a lone or leading empty `after` is refused. The
empty-header boundary recorded here then — that an empty header with `after=1`
selects 1 — no longer holds; round 12 made an empty header a refused cursor.

### The served stream contract now matches the committed one

Round 10 aligned only the 422 text. Four other differences remained, none
gated: the `after` and `Last-Event-ID` descriptions omitted the committed bound
wording, and the 200 response listed `application/json` beside
`text/event-stream` because FastAPI merges its default JSON response into a
route with no `response_class`. All three are fixed, and every response and
parameter description is now equal to the committed text, whitespace
normalised, as checked against `app.openapi()`.

**One difference stays, deliberately, and is recorded in
`contracts/openapi/runs.yaml` beside the AC-0009 note.** The header is committed
as `integer, minimum: 0` — the domain a caller may send — but served as
`string | null`, because the route reads it as a raw string so it can be judged
character by character. Typing it `int` would let pydantic coerce `+1` or `1_0`
into a valid cursor before any check ran.

### A recovery worth recording

Recording this round, the `findings-remain` transition succeeded at seq 71 and
the matching `review record` did not: an unquoted shell variable holding the
fingerprint flags was passed as one argument, because zsh does not word-split
it, and the record refused for lack of a fingerprint. That left the engine one
round ahead of the cohort. It was recovered by re-issuing the record under the
same operation id, `:71`, after confirming the cohort had written nothing — the
cohort's last operation was still `:68`. The two are back in step.

## Post-gates review round 12

No blockers. Three findings: two sustained, one refuted.

**Refuted:** a claim that the round-11 ledger paragraph announced "four
differences" and listed three. It lists three fixed and, in the next
paragraph, the fourth — the deliberate `Last-Event-ID` schema difference — so
the count is accurate. Refuted findings are not acted on.

### An empty `Last-Event-ID` was read as absent, on a false premise

Round 11 kept an empty header as "no prior id", with this justification in the
code and in this ledger: an `EventSource` that has seen no `id:` sends "no
`Last-Event-ID`, or an empty one". **That is false.** Checked at the source,
WHATWG HTML § Server-sent events reads: *"If the `EventSource` object's last
event ID string is not the empty string: … Set (`Last-Event-ID`,
lastEventIDValue) in request's header list."* A conforming browser omits the
header when its last ID is empty; it never sends an empty one.

Without that premise the rule had no ground, and AC-0323 decides the case:
the cursor is "`Last-Event-ID` when present", an empty header is present and
not a non-negative integer, and reading it as absent is the coercion the
criterion forbids. Adjudication ruled the remedy determined, so it needed no
owner decision; the other branch the reviewer offered — amending AC-0323 to
call an empty header absent — would weaken a criterion, which § Boundaries
reserves to the owner. An empty header is now refused, and refusing it costs
no browser anything.

| Break | Red proof | Restored |
| --- | --- | --- |
| Treat an empty `Last-Event-ID` as absent, as round 11 did | FAILED — `assert 200 == 422` (fell back to `after=1` and opened a stream) | 31 passed across the stream and contract modules |

The round-11 paragraphs that stated the false premise are corrected in place,
pointing here.

### The `runs.yaml` header overstated what matches

The comment said "one field differs between this file and the generated
document". That holds within `stream_events` only: on the operations other
specs own, the generated document still serves FastAPI's default response
descriptions where `runs.yaml` commits specific text. The comment is now
scoped to `stream_events` and says so.

## Post-gates review round 14

No blockers. One sustained finding, the most consequential measurement finding
in this delivery, and one refuted (a remark about the review brief's scope,
not a defect in the target).

### The cancellation witness could not show its stream was in flight

AC-0309 measures cancellation "on an in-flight model stream". The command
could not establish that. It requested `"Reply with one word."` with
`max_tokens=64`; it started a reader thread draining the stream immediately
after the first chunk, *before* the caller closed it; and it caught
`StopIteration` on the first chunk with the comment "still valid to observe
close". A reader that had exhausted a short stream on its own was then
observed as finished and recorded `terminated` — exactly as a cancelled one
would be. The recorded 0.000533 s fitted either case, so AC-0309's premise
could not fail.

The first adjudication returned `ADJUDICATION-INDETERMINATE`: the remedy
turned on whether to re-run a provider measurement, which § Boundaries and the
plan's first-valid-observation rule reserve to the owner. That is not a
machine-checkable fact, so the round stopped. **The owner decided on
2026-10-01** — see § Owner decisions — to treat the old witness as unverified,
fix the command, and re-run once. A replacement adjudication of the unchanged
report then sustained the finding with a determined remedy. The indeterminate
artifact is retained as `14-post-gates-adversarial-reviewer-adjudication.indeterminate.md`.

### The fix

- **The stream is long enough to be in flight.** The request now asks for a
  long reply with `max_tokens=2048`.
- **Being in flight is checked, not assumed.** `close_stream()` samples whether
  the reader is still running *immediately before* closing the body and
  returns it. `classify_cancellation_outcome` raises `StreamNotInFlightError`
  instead of classifying when it was not, and still joins the reader so
  resources are released. The command refuses with a non-zero exit and writes
  no record.
- **A stream that ends before its first chunk is refused**, not admitted as
  "still valid".
- The record carries `in_flight_at_close`, so the witness holds the
  observation its premise rests on.

| Break | Red proof | Restored |
| --- | --- | --- |
| Drop the liveness check (ignore `close_stream()`'s return value) | FAILED — `Failed: DID NOT RAISE StreamNotInFlightError` | the evidence module green |

### The re-run, taken once

**A false start, recorded because it is not a measurement and must not be
mistaken for one.** The first invocation failed with `error: Bedrock invoke
failed: You must specify a region.` — botocore's client-side `NoRegionError`,
raised while the client was built, before any network call: no stream was
opened and Bedrock was never reached. `measurements.json` was confirmed
unchanged. botocore reads `AWS_DEFAULT_REGION`, not `AWS_REGION`; with that
set, the measurement was taken **once**:

```json
{
  "cancellation": {
    "outcome": "terminated",
    "latency_seconds": 0.000364,
    "region": "us-east-1",
    "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "method": "long generation; close response body while the reader is still running; observe reader join within 30s window",
    "in_flight_at_close": true,
    "measured": "2026-10-01"
  }
}
```

`in_flight_at_close: true` is what makes this a cancellation witness: the
reader was running when the body was closed, and finished after it. The value
is the command's own output, written by `--out`, `measured` included — so the
cancellation block no longer carries an operator-recorded date. The latency is
close to the unverified 0.000533 s, consistent with the old run having been a
real cancellation as well; only this one is verified. One provider call, well
under the $5 cap; no AWS resource was created.

### Records

`operations.md` § Cancellation measurement, `spikes/README.md`'s AC-0309/0310
row and `runtime-architecture.md` now carry the verified value and state that
being in flight is observed. The § T2 cancellation witness is marked
unverified history. The § T6 and § Post-gates review round 3 statements that
the cancellation block was never re-measured and carried an operator-written
date are marked superseded in place; the quota block still stands as they say.

## Post-gates review round 16

Round 16 ran the frontend, experience, security and quality reviewers over the
whole delivery. Every sustained finding whose fix the contract fixes was
fixed; the advisory ones are listed under § Not changed. Each break below was
re-performed by the controller on 2026-10-01 against the running substrate,
with the source restored and the bundle rebuilt afterwards to the digests
then recorded in § Post-gates review round 17.

### The page

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| Reconnecting is announced, not only shown (AC-0336) | `test_reconnecting_status_is_announced` | Move the status label back out of the `role="status"` paragraph | `AssertionError` — the live region does not contain "Reconnecting from last sequence" | passed |
| Terminal names its outcome (AC-0336) | `test_live_region_announces_terminal_outcome` | Restore the fixed "Terminal event received" label | heading "Run failed" not found | passed |
| A failed run is not painted as a success | `test_live_region_announces_terminal_outcome` | `statusClass` returns `status-terminal-completed` for `run.failed` | `AssertionError: a run.failed status bar is painted in the success colour: {'border': 'rgb(85, 201, 147)', 'success': 'rgb(85, 201, 147)', 'danger': 'rgb(239, 118, 122)'}` | passed |
| Focus is visible in forced-colors mode (AC-0337, WCAG 2.4.7) | `test_forced_colors_focus_outline` | Restore `outline: 0` in the focus rule | `AssertionError: Skip link outline style is 'none' in forced-colors mode (width='0px')` | passed |
| The focus ring reaches 3:1 (AC-0337, WCAG 1.4.11) | `test_accessibility_and_reflow` | Restore `rgb(139 124 246 / 45%)` on `--ds-focus-ring` | `AssertionError: Focus ring contrast 2.07:1 is below the WCAG 1.4.11 minimum of 3:1` | passed |
| A permanently failed stream reaches Unavailable with Retry | `test_closed_stream_shows_unavailable` | `onerror` dispatches `reconnecting` whatever `readyState` is | heading "Run unavailable" not found; the page shows "Reconnecting from last sequence" | passed |
| Going offline does not undo Terminal | `test_offline_after_terminal_keeps_terminal` | Remove the offline arm's terminal guard | heading "Run completed" no longer visible, 3 of 3 runs | passed |
| The real route's history–stream overlap renders once | `test_history_stream_overlap_renders_once` | Remove the `addEvent` duplicate guard and rebuild | `AssertionError: Expected seqs [1, 2, 3], got [1, 1, 2, 2, 3, 3]`, 3 of 3 runs | passed |
| Streaming is scanned while it stands still (AC-0337) | `test_streaming_state_is_scanned` | `<img src="" />` without `alt` only while `connection === "streaming"` | `WCAG 2.2 A/AA violations in streaming state: [critical] image-alt` | passed |

The Streaming break left `test_accessibility_and_reflow` **green**. Its scan
labelled "streaming" had run after the terminal frame arrived, so it scanned
the Terminal page twice under two names. That scan is removed, and Streaming
is now held open by the real routes on a run with no terminal event.

The offline check now waits two animation frames inside the page after
dispatching `offline`. The reads that follow otherwise run before React commits
the update. The reconnecting and offline arms carry the same guard text, so a
break written as a text replacement must anchor on the offline arm: replacing
the first match edits the reconnecting arm and leaves this check green, which
is what the first attempt at this break did.

The overlap check and the Streaming scan drive the real `ced-api` routes with
no mock. As delivered, the overlap check mocked the stream, which would have
pinned the client against a replay the test wrote rather than the one the
route sends. It now commits the run's events, terminal included, before the
page loads.

### The stream route

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| An over-long `Last-Event-ID` is refused with 422 (AC-0323) | `test_invalid_last_event_id_is_refused["9"*5000]` | Remove the `ValueError` guard around `int(raw)` | `assert 500 == 422` | passed |
| The live tail advances its cursor (AC-0304) | `test_live_tail_cursor_advance_and_paging` | Delete `cursor = envelope.seq` | `AssertionError: stream did not close within 30 s` | passed |
| The live tail crosses a `READ_LIMIT` page (AC-0304) | `test_live_tail_cursor_advance_and_paging` | End the stream after the first full page | `AssertionError: expected seqs 1–103 (103 events), got 101 events` | passed |
| The stream route holds no connection while open | `test_stream_releases_connection_on_disconnect` | Restore `conn: Conn` on `stream_events` | `AssertionError: Stream route leaked 1 idle-in-transaction connection(s) while the socket was open`, 3 of 3 runs | passed, 3 of 3 |

The connection-leak row in § T1 recorded this break as red, and it was not:
re-performed on FastAPI 0.141.1 before the fix, the check passed 3 of 3 under
the break, because it sampled `pg_stat_activity` after the socket closed. A
probe sampling while the socket was open read 0 on the shipped code and 1
under the break, so the check now samples there.

An over-long `?after=` is refused with 422 by FastAPI's typed `after` before
the handler runs. No break reds a check of that path short of changing the
published schema, so no check claims it.

### The evidence and rebaseline commands

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| `--out` refuses an unreadable record and leaves it untouched | `test_write_record_refuses_corrupt_file_and_leaves_it_untouched`, `test_write_record_refuses_json_array_and_leaves_it_untouched` | Restore the silent fallback to an empty record | `Failed: DID NOT RAISE ValueError`, both checks | passed |
| An interrupted `--out` write keeps the old record | `test_write_record_atomic_write_protects_original_on_failure` | Write directly with `open(out_path, "w")` instead of a temporary file and `os.replace` | `AssertionError: original must be byte-for-byte intact after an interrupted write` — `b''` | passed |
| The committed threshold is `p99 × 3` (AC-0308) | `test_committed_record_p99_relation_and_sample_floor` | `page_threshold_seconds` 0.262293 → 0.9 | `assert 0.9 == 0.262293` | passed |
| The committed sample meets the floor (AC-0307) | `test_committed_record_p99_relation_and_sample_floor` | `sample_size` 30 → 5 | `assert 5 >= 30` | passed |
| The parser never raises on malformed shapes (AC-0312) | `test_parse_qa_observations_fail_closed_on_malformed_shapes`, `test_parse_qa_observations_never_raises_on_arbitrary_json_observations` | Remove the list, object and string-label guards | `TypeError: 'NoneType' object is not iterable`; `AttributeError: 'str' object has no attribute 'get'` | passed |
| Each loss is fed by its own predicate (AC-0313) | `test_derive_loss_from_qa_responses_wires_narrow_pre_as_no_anchor_check` | `check_anchors=True` for `narrow_pre_obs` in `derive_loss_from_qa_responses` | `assert 0 == 1` | passed |
| The rebaseline refuses a fixture whose bytes disagree with its declared digest (AC-0312) | `test_verify_fixture_digest_refuses_wrong_content` | Make the digest comparison a no-op | `Failed: DID NOT RAISE ValueError` | passed |
| The cancellation body closes before closure is observed | `test_cancellation_outcome_comes_from_the_reader_completing` | Observe closure before closing the stream | `AssertionError: close_stream must be called before observe_closure on the terminated path` | passed |

The atomic-write check as delivered patched `os.replace` to fail, which an
interrupted write never reaches. It now fails serialisation, where the old
truncating write had already emptied the file.

### Records corrected

The Phase 1 record in `spikes/README.md` said a stream's cost lasts "for as
long as the page is open". An abandoned stream keeps its worker until the next
event commits, and one opened on a terminal run at its highest sequence never
releases it; the record now says so. The `compute_loss_breakdown` docstring no
longer claims narrowing loss isolates the vocabulary effect, which closes that
backlog item. `AGENTS.md` § Phase 1 evidence commands records the `--out`
refusal and the atomic write.

### Not changed

Sustained as advisory, because the contract does not fix the remedy or the
ground is working material: the header's `State` field showing `pending` and
the last event type; metadata emphasis, alignment and the sequence colour;
the boot validation of `CED_STEP_DEADLINE_SECONDS`; the same-origin guard's
trust in the request `Host` and the abandoned stream's worker, both recorded
in `workspace.toml` `[backlog].open`.

## Post-gates review round 17

The adversarial reviewer found that two named outcomes of the state matrix
were driven but not observed, and that the bundle digests on record belonged
to files no longer in the tree. All were sustained and fixed.

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| Offline keeps the rows already rendered (state matrix, AC-0336) | `test_applicable_state_matrix` | Clear `events` and `order` in the `offline` reducer arm | `test_run_page.py:717` — `Locator expected to be visible` for the `run.requested` row | passed |
| Unavailable keeps the rows already rendered (AC-0336) | `test_closed_stream_shows_unavailable` | Clear `events` and `order` in the `unavailable` reducer arm | `test_run_page.py:1309` — `Locator expected to be visible` for the `run.requested` row | passed |
| A failed history request names that request | `test_applicable_state_matrix` | Replace `Event history returned ${response.status}` with `Something went wrong` | `Locator expected to contain text 'Event history returned 503'` — actual `Run unavailable: Something went wrong` | passed |
| A permanently failed stream names that request | `test_closed_stream_shows_unavailable` | Replace `Stream request failed: ${streamUrl}` with `Something went wrong` | `Locator expected to contain text 'Stream request failed'` — actual `Run unavailable: Something went wrong` | passed |

The Offline drive had a comment saying existing rows remain and no assertion
that they did, and every Unavailable check asserted the heading and Retry but
not the message.

### Bundle provenance

*(History since round 21, which rebuilt the bundle; the shipped digests are in
§ Post-gates review round 21.)* Rebuilt from a wiped `node_modules`
reinstalled with `npm ci`; `npm run test` passed; a second `npm run build`
over the same source reproduced every digest. SHA-256 of the round-17 bundle:

```
ae9f0b5d63da08d29330bad3d01dc32acc3957a2dc131ddad9e9b161da9825a4  src/ced/api/static/index.html
06aef73a75d8e24c24e6a8701b0b133f7886892047a43f93847675fc067f3d6e  src/ced/api/static/assets/index-U7v6KYTA.js
d545dd8f2e7d482485289087029dd81972b8c08e71fb1953e839185b678b0f89  src/ced/api/static/assets/index-DKLqRv6V.css
```

`index.html` references `index-U7v6KYTA.js` and `index-DKLqRv6V.css`.

## Post-gates review round 18

The adversarial reviewer found more state-matrix outcomes that were driven but
not asserted — the class round 17 fixed for Offline and Unavailable. Rather
than fix only the rows reported, every applicable row's named outcomes were
read against the assertions that observe them, clause by clause. The gaps were
taken to be the ones reported; Reconnecting, Terminal, Offline, High zoom and
Reduced motion already assert every outcome they name. *(Round 19 found one
the audit missed: Loading's "stable row placeholders" was asserted through the
`aria-busy` list, which stays visible with no rows in it. See § Post-gates
review round 19.)*

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| Loading shows a named status (state matrix) | `test_applicable_state_matrix` | `labelFor("loading")` returns `Please wait` | `Locator expected to be visible` for the "Loading committed events" heading | passed |
| Retry can be invoked without a pointer (Keyboard only) | `test_applicable_state_matrix` | Bind Retry's handler to `onPointerDown` instead of `onClick` | Enter leaves the page Unavailable; `Locator expected to be visible` for "Waiting for worker events" | passed |
| Waiting keeps the run identity visible | `test_applicable_state_matrix` | Drop `{runId}` from the `<h1>` | `Locator expected to have text 'Run <run id>'` — actual `Run ` | passed |
| Streaming updates the cursor | `test_streaming_state_is_scanned` | Keep `state.cursor` instead of `Math.max(state.cursor, event.seq)` | `Locator expected to have text '2'` — actual `0` | passed |

The keyboard break is specific to keyboard input: `.click()` dispatches
pointer events, so every other Retry in the suite still passes under it and
only the Enter path reds. The cursor check reads the header value at 2 while
Streaming is held open and at 3 after the terminal event commits on the open
stream, so it observes the cursor advancing live rather than a value present
from the first render.

A missing run is the other branch of the Unavailable trigger, and no browser
check drives it. The page route refuses an unknown run with 404 before serving
the bundle, so no page exists to show the Unavailable state for it. That branch
rests on `tests/api/test_read_access.py::test_unknown_run_is_refused_for_page_and_stream`,
and the manifest's Unavailable row now says so. *(Superseded in round 19 by an
owner decision: the page now serves the client with its 404, and a browser
check drives a missing run to Unavailable.)*

## Post-gates review round 19

The adversarial reviewer found that Loading's placeholder rows were not
observed, that a missing run could not reach the Unavailable outcome the state
matrix gives it, and that the Phase 1 record named the wrong check for the
Streaming scan. All were sustained.

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| Loading shows stable row placeholders (state matrix) | `test_applicable_state_matrix` | Render no placeholder rows (an empty map in the loading `<ol>`) | `Locator expected to have count '3'` — actual `0` | passed, 3 of 3 |
| A missing run reaches Unavailable (state matrix, AC-0336) | `test_missing_run_shows_unavailable` | `read_run_page` raises its 404 instead of serving the page | `Locator expected to be visible` for "Run unavailable" | passed |
| A missing run's error names the failed request | `test_missing_run_shows_unavailable` | Replace the history-failure message in App.tsx | `Locator expected to contain text 'Event history returned 404'` — actual `Run unavailable: Something went wrong` | passed |
| An unknown run's page is a 404 that carries the client (AC-0338) | `test_unknown_run_is_refused_for_page_and_stream` | Same `read_run_page` break | `assert 'application/json' == 'text/html'` | passed |

The placeholder list has a top border, so `[aria-busy='true']` stays visible
with no rows in it; the reviewer's empty-map break left the earlier check green
in 3.79 s. The check now counts the placeholder rows themselves.

The missing-run fix is an owner decision (§ Owner decisions, 2026-10-01). The
page route still answers `404` for an unknown run, as AC-0338 requires, but
the response carries the browser client. The client's own history request then
answers `404`, and the page shows the Unavailable outcome with no mock.

## Post-gates review round 20

The adversarial reviewer found that a malformed run id still received
FastAPI's JSON `422`, so no page loaded to show Unavailable. The round-19
decision had reached only a well-formed id. Sustained as advisory, since the
contract did not say whether a malformed id is a missing or invalid run; the
owner extended the round-19 decision to it (§ Owner decisions). `read_run_page`
now takes `run_id` as a string and parses it itself, so a malformed id gets the
same `404` page.

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| A malformed id reaches Unavailable | `test_missing_run_shows_unavailable["not-a-run-id"]` | `read_run_page` raises `404` on a malformed id instead of serving the page | `Locator expected to be visible` for "Run unavailable" | passed |
| A malformed id's page is not FastAPI's `422` | `test_missing_run_shows_unavailable["not-a-run-id"]`, `test_unknown_run_is_refused_for_page_and_stream` | Type `read_run_page`'s `run_id` as `UUID` again | `assert ... 422 == 404`; `AssertionError: not-a-run-id` — `assert 422 == 404` | passed |
| The error names the failed request | `test_missing_run_shows_unavailable` | Replace the history-failure message in App.tsx | `Locator expected to contain text 'Event history returned 404'` | passed |

For a malformed id the page's history request answers `422`, from that route's
typed `run_id`, and the page names it: `Event history returned 422`. The page
route still serves only the fixed `index.html`, so AC-0335 is unchanged, and
the traversal checks in `tests/api` pass.

## Post-gates review round 21

The adversarial reviewer found that a run id holding a malformed percent
sequence, such as `/runs/%`, received the `404` page and then a blank screen:
`runIdFromLocation` called `decodeURIComponent` unguarded, it threw a
`URIError` during render, and with no error boundary React unmounted the
root. Sustained as a blocker, determined by the round-20 owner decision, which
already requires every id the page route serves to reach Unavailable.
`runIdFromLocation` now keeps the raw segment when decoding fails, so the
history request still goes out, answers `422`, and the page names it.

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| A malformed percent sequence reaches Unavailable | `test_missing_run_shows_unavailable["%"]` | Remove the `try`/`catch` around `decodeURIComponent` | `Locator expected to be visible` for "Run unavailable", 3 of 3 runs | passed |

With three cases, the earlier page-route breaks were re-run per case on
2026-10-01: making `read_run_page` raise its `404` fails all three; typing its
`run_id` as `UUID` again fails `not-a-run-id` and `%` and leaves the
well-formed case passing; replacing the history-failure message fails all
three. Rounds 22 and 23 found the test's docstring still describing two cases
and a `404` history status for all of them, and it now gives each case's
status.

The reviewer also drove hyphenless, braced and `urn:uuid:` ids, which reach
Unavailable because the page and history routes accept the same UUID forms,
and `/runs/a%2Fb`, which Starlette decodes before routing so it never reaches
`read_run_page`.

### Bundle provenance

*(History since round 25, which rebuilt the bundle; the shipped digests are in
§ Post-gates review round 25.)* The UI source changed, so the bundle was
rebuilt from a wiped `node_modules`
reinstalled with `npm ci`; `npm run test` passed; a second `npm run build`
over the same source reproduced every digest. SHA-256 of the shipped bundle:

```
47e51d34cc5f6a4021102abbd62f93f419482817fc6e4155eae55414eafb8642  src/ced/api/static/index.html
f3009525667dc6e50067ea7ae536adba5daa27bc89d889da98023703544b85de  src/ced/api/static/assets/index-C6tHoan6.js
d545dd8f2e7d482485289087029dd81972b8c08e71fb1953e839185b678b0f89  src/ced/api/static/assets/index-DKLqRv6V.css
```

`index.html` references `index-C6tHoan6.js` and `index-DKLqRv6V.css`.

## Post-gates review rounds 22 to 25

Rounds 22 and 23 each found one stale sentence in
`test_missing_run_shows_unavailable`'s docstring, recorded in § round 21.
Round 24's adversarial review was clean. Round 25 re-ran the four specialist
reviewers over the whole delivery, against fresh captures of the round-21
bundle. The security review was clean. Two findings were sustained as
required and fixed; the rest were advisory, listed under § Not changed below.

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| A history that already ends in a terminal event shows Terminal (Terminal row; a terminal run stops reconnecting) | `test_terminal_history_opens_no_stream` | Drop the `endsInTerminal` arm from the `snapshot` reducer case | `Locator expected to be visible` for "Run completed" | passed |
| Such a run opens no stream, so a failing one cannot replace Terminal | `test_terminal_history_opens_no_stream` | Remove the early return after the snapshot in `connect()` | `Locator expected to contain text 'Run completed'` — actual `Run unavailable: Stream request failed: …` | passed |
| A stream that fails while the browser is offline leaves Offline and Retry (Offline row) | `test_stream_drop_while_offline_keeps_offline` | Drop the `offline` guard from the `reconnecting` arm | `Locator expected to be visible` for "Browser is offline" | passed, 3 of 3 *(superseded in round 29: that guard is gone; Offline is now derived at render, see § rounds 26 to 30)* |
| The real route's history–stream overlap still renders once | `test_history_stream_overlap_renders_once` | Remove the `addEvent` duplicate guard | `Expected seqs [1, 2, 3], got [1, 1, 2, 2, 3]`, 3 of 3 | passed |

The overlap check had committed its terminal event before the page loaded.
With the first fix that run is already finished, opens no stream, and so has
no overlap to show; the check now commits the terminal event once the page is
streaming. The offline check aborts the pending stream, a network failure
before it ever opened: fulfilling it would fire `onopen`, which rightly
clears Offline, since an open stream shows the network is back. It waits on
the browser's own reconnect request rather than a sleep.

Round 26 found the new check's docstring describing failures its breaks
cannot cause: the reducer arm and `connect()`'s own check are independent
guards, so dropping the reducer arm leaves the page on Streaming with no
stream, and removing the early return fails at the status text before the
request count. The docstring now matches the table above, and the overlap
check's docstring names the `[1, 1, 2, 2, 3]` it actually observes. Round 27
found one docstring citing that check by a truncated name; a sweep of every
`test_` name cited in the tests and these records against the defined tests
found no other live one, only names this ledger already records as retired.

Two records were false and are corrected. The hypothesis property's docstring
claimed it reaches the label and anchor guards; its strategy almost never
produces those keys, so it now says only the parametrized cases pin them.
`AGENTS.md` said a missing `--out` file is created; a missing directory is not,
and it now says so.

### Bundle provenance

*(History since round 29, which rebuilt the bundle; the shipped digests are in
§ Post-gates review rounds 26 to 30.)* Rebuilt from a wiped `node_modules`
reinstalled with `npm ci`; `npm run test` passed; a second `npm run build`
reproduced every digest. SHA-256 of the round-25 bundle:

```
c5cc57be5f8c4a7091c8dc568fcfd37dca4c0d5c40645ed76dd5c88740b53b21  src/ced/api/static/index.html
55448da55f9bca0163082373dcca81db0ea240b3ba6b634ddfef45a22bfc7d02  src/ced/api/static/assets/index-AWpoQ4Wx.js
d545dd8f2e7d482485289087029dd81972b8c08e71fb1953e839185b678b0f89  src/ced/api/static/assets/index-DKLqRv6V.css
```

### Not changed

Sustained as advisory, because the contract does not fix the remedy or the
ground is working material: the status label shown both as the heading and at
the start of the status line, which the live region needs and only the
design direction argues against; Retry's hover drawing the focus ring; the
live-tail check ordering its commit by a sleep rather than by the first
delivered event; `_cmd_rebaseline` parsing the narrow observations once for
the analyst and again for the loss record; a missing `--out` directory
raising a traceback; and the leak check's unscoped `pg_stat_activity` count.

## Post-gates review rounds 26 to 30

Rounds 26 and 27 each found one stale docstring sentence, recorded in
§ rounds 22 to 25. Round 28's adversarial review was clean. Round 29 re-ran the
frontend reviewer against fresh captures, and it found Offline still displaced
by later events along three paths: a history arriving after the network was
lost, Retry pressed while still offline, and — introduced by round 25's guard
— Offline left up after the network returned while the stream kept failing.
One cause underlay all three: Offline was a value of `connection`, so any
later reducer arm could overwrite it, and round 25 had guarded one arm. The
first was sustained as required and the other two as advisory; one control
resolves all three.

Offline is now a separate `browserOffline` flag, set by the window `offline`
event and cleared by `online`, and the shown state is derived at render:
Terminal, then Offline while the flag is set, then `connection`. While shown
as Offline the status keeps any failed-request text, so the Unavailable row's
naming is not lost. Round 25's `offline` guard on the `reconnecting` arm is
removed. `stream-open` does not clear the flag: no check could pin that, and
the `online` event is the signal. The two state-matrix checks that pressed
Retry after an `offline` event now fire `online` instead, since with the flag
the network's return is what lifts Offline.

| Claim | Check | Break | Red | Green |
| --- | --- | --- | --- | --- |
| No later event displaces Offline while the browser reports no network | `test_stream_drop_while_offline_keeps_offline`, `test_history_arriving_offline_keeps_offline`, `test_retry_while_offline_stays_offline`, `test_applicable_state_matrix`, `test_accessibility_and_reflow` | Derive the shown state from `connection` alone | these five fail; the rest of `tests/browser` passes | passed |
| Offline lifts when the network returns, showing Reconnecting | `test_stream_drop_while_offline_keeps_offline`, `test_applicable_state_matrix`, `test_accessibility_and_reflow` | Remove the `online` listener | these three fail; the rest passes | passed |
| A history arriving while offline keeps Offline | `test_history_arriving_offline_keeps_offline` | Seed `browserOffline` from `initialState` in the `snapshot` arm | that check alone fails | passed |
| Retry while offline still names the failed request | `test_retry_while_offline_stays_offline` | Show only "Network connection lost" while offline | that check alone fails | passed |
| Retry while offline keeps the rows already shown (Offline row) | `test_retry_while_offline_stays_offline` | Branch the event list on `connection` rather than the shown state | that check alone fails, at the `run.requested` row while the retry is pending | passed |
| A finished run keeps its final state when the network drops | `test_offline_after_terminal_keeps_terminal` | Drop Terminal's precedence from the render-time derivation | that check alone fails, at "Run completed" | passed |

Each break was run against the whole of `tests/browser` on 2026-10-01, so each
row names every check it reds; the round-29 version of this table listed only
the checks it set out to pin, and round 30 found `test_accessibility_and_reflow`
missing from two rows. Round 30 also found the event list still branching on
`connection`, so a Retry pressed while offline showed the Loading placeholders
under the Offline heading; the list now follows the shown state. Round 31
found the same incompleteness in `evidence.md`'s Offline row for the older
row-clearing break (round 17): run against the whole browser suite on
2026-10-01 it reds `test_applicable_state_matrix`,
`test_offline_after_terminal_keeps_terminal` and
`test_retry_while_offline_stays_offline` (3 failed, 18 passed), and the row now
names all three. It also found two break notes describing a failure path the
`connection`-only break cannot reach; since no arm writes Offline into
`connection`, the Offline heading simply never appears, and both notes now say
so.

The precedence of Offline over Unavailable while the browser reports no
network is this delivery's choice: both rows hold at once, the round-29
adjudication found that the contract does not rank them, and the single
render-time control implies it.

### Bundle provenance

Rebuilt after round 30 from a wiped `node_modules` reinstalled with `npm ci`;
`npm run test` passed; a second `npm run build` reproduced every digest.
SHA-256 of the shipped bundle:

```
a5a05aa0897f32b66fbf502a7b7e0909f704abc7c3b48cfca785bfd14a37bb51  src/ced/api/static/index.html
d6c43165644a311729834a9bce9787d2ee7ac78146a4a5b9a28ebf36bf70694f  src/ced/api/static/assets/index-CaJkuxGG.js
d545dd8f2e7d482485289087029dd81972b8c08e71fb1953e839185b678b0f89  src/ced/api/static/assets/index-DKLqRv6V.css
```

## Owner decisions

| Date | Decision | Why it was needed |
| --- | --- | --- |
| 2026-09-30 | AC-0310 is amended to the property the cancellation measurement observes — that this process stopped reading — and the unreachable `abandoned` branch is recorded rather than implied live. | The measurement closes the local response body and joins the reader thread, so it establishes nothing about the provider connection. Follow-on: `workspace.toml` `[backlog].open` `cancellation-observes-local-reader-not-provider-connection`. |
| 2026-09-30 | The server-sent event frame carries no `event:` field; the committed event type travels in the JSON envelope, and the browser reads every frame through a native `EventSource` `onmessage` handler. | A named `event:` field is why `onmessage` never fires, which forced the browser to register a listener per hand-written type — an enumeration `src/ced/domain/events.py` makes impossible to complete, since the step-scoped vocabulary is deliberately open. Moving the type into the payload fixes AC-0304 at its cause and keeps AC-0305's native-reconnect premise true, rather than replacing the transport and leaving the criterion describing a mechanism the client no longer uses. Requires `src/ced/api/stream.py` in T5's `Touches`, which is what the second controlled amendment of 2026-09-30 adds. |
| 2026-10-01 | The review retry cap is raised for this run, and review continues past it. | The cap (5) was reached with sustained blockers outstanding and the specialist reviewers not yet run. The override is applied with `--allow-retry-cap-override` on both the `findings-remain` transition and the matching `review record`, from round 7 onward. |
| 2026-10-01 | A malformed `after` is refused with 422 even when a valid `Last-Event-ID` outranks it: every supplied cursor is judged lexically, and the bounds check applies only to the selected one. | AC-0323 bounds "the selected stream cursor", so its text did not decide an outranked `after` — adjudication ruled it a design call. Refusing it was chosen over ignoring it because FastAPI's typed `Query(ge=0)` already refuses an outranked `-1` or `abc`, so validating gives every malformed spelling the same answer without changing the published schema; ignoring would have required declaring `after` a string. `contracts/openapi/runs.yaml`'s `422` description was widened to match. |
| 2026-10-01 | The AC-0309 cancellation witness of 2026-09-29 is treated as **unverified**, the measurement command is fixed, and the provider measurement is **re-run once** with the fixed command. The 2026-09-29 record is kept as history, marked unverified, not deleted. | Round-14 adjudication found the command could record `terminated` for a stream that had ended on its own before the close: it requested a one-word reply, started draining the stream before closing it, and admitted a stream that ended before its first chunk as "still valid". So AC-0309's "in-flight model stream" premise could not fail, and the recorded 0.000533 s fits either case. The adjudication ruled the re-run reserved to the owner, because the plan records the first *valid* observation and that one was unverified rather than shown invalid. The re-run is to obtain a valid observation, not a better-looking value; cost is one call, far under the $5 cap. |
| 2026-10-01 | An unknown run's page is served with status `404` and the browser client as its body, rather than a JSON `404`. | The state matrix gives a missing run the Unavailable outcome — an error naming the failed action and a retry control — and its Empty-or-no-results row routes an invalid run there, while AC-0338 requires `404` for an unknown run. A JSON `404` met AC-0338 and left no page to show Unavailable. Serving the client with the `404` meets both clauses without amending the contract; amending the state matrix to defer to the `404` was the alternative. |
| 2026-10-01 | The unknown-run page decision extends to a malformed run id: the page route parses `run_id` itself and serves the client with `404` for any id that names no run. | A malformed id received FastAPI's JSON `422` and no page, so it could not reach the Unavailable outcome the state matrix gives an invalid run. Recording a malformed id as outside the matrix's trigger was the alternative. |


## Commands run

Every figure below comes from **one run of the gates against the final tree**,
taken in the primary worktree after T5, T6 and T7 had all landed. A per-task
figure describes a tree that is not the one shipping, so none is carried here.

| Command | Result | Establishes | Limit |
| --- | --- | --- | --- |
| `./.venv/bin/ruff format --check .` | Pass: 272 files already formatted, exit 0 | Python formatting across the project | Does not cover UI source |
| `./.venv/bin/ruff check .` | Pass: all checks passed, exit 0 | Python lint across the project | Does not execute runtime paths |
| `./.venv/bin/mypy` | Pass: no issues in 55 source files, exit 0 | Strict types over `src/ced` | Does not typecheck tests |
| `./.venv/bin/python -m pytest` | Pass: 1112 passed, 3 skipped in 294.99 s, exit 0 | Gate of record — whole suite in one unfiltered process, including all substrate, API, and browser checks. No `pytest` process remained afterwards | Runs against local substrate; the duration moves with the survivor's poll offset and with suite composition, so read the number `pytest` prints |
| `cd src/ced/api/ui && npm ci && npm run test && npm run build` | Pass: `tsc --noEmit` silent, build emitted three files, exit 0 | UI typecheck and the served bundle, built from a wiped `node_modules` so the lockfile is exercised | Does not run the UI in a browser; the browser behaviour is covered by `tests/browser/` |
| `python3 tools/lint-no-identifiers.py --staged` | Pass: clean — no identifying data in staged files | No account ids, ARNs, keys, emails, or home paths in staged files | Only staged files are checked |
| `python3 tools/lint-intents.py` | Pass: clean | Intent file structural lint | Does not check spec or plan files |
| `python3 tools/hooks/pre-pr.py` | Pass: all checks passed | Knowledge lint, loop-cohort check, ADR shape lint, prose totals | Review cohort skipped (FSM not CODE-REVIEW) |
| `python3 tools/lint-prose-totals.py` | Pass: exit 0 | No sentence-initial cardinal totalling a list inside a guarded region | Reads `docs/**/*.md` only; a guard elsewhere needs its path passed |
| `python3 .claude/skills/work-loop/scripts/lint-spec-status.py --root . --all` | Pass: spec metadata clean (7 specs, 4 hidden warnings) | Spec and plan status metadata across all specs | Warnings hidden; re-run with `--verbose` to inspect |

**The split invocation is deliberately not recorded as a figure.** Running
`-m 'not substrate'` and `tests/api/ tests/browser/` as two commands was green
on an earlier tree while the single documented command failed 59 checks: the
split always sorts `tests/browser/` last, where its Playwright event loop
outlives nothing, and run whole the suite sorts it early so every later
`asyncio.run` fails. Those numbers measured the filter, not the gate, so
carrying them here would record a pass that was not one.

## Cut-before-adding search

### T5

`rg -n "EventSource|onmessage|readSSEStream|encode_sse_event|text/event-stream"
src tests` found no reusable SSE client helper in the repository. The ladder
stopped at rung 4, a native platform capability: the browser's own
`EventSource` satisfies the outcome, so the hand-written `fetch` +
`getReader()` frame parser was deleted rather than repaired, and the client
gained no replacement helper. The two re-gated browser checks reuse mechanisms
already present in this suite — the SSE `retry:` field, and holding a
Playwright `Route` — rather than adding a harness.

### T7

Rung 2 stopped the search. `rg -n "build_producer_tuple|producer|set\(.*keys\(\)\)|keys\(\) =="
tests src` found one precedent for checking a producer tuple:
`tests/provider/test_a_step_runs_under_a_scoped_role.py`'s
`test_ac_0225_producer_tuple_records_profile_and_version` and
`test_ac_0254_producer_tuple_names_security_bearing_members`. Neither was
reusable. They assert the **executor's** fourteen-field r8 § 5 tuple, a
different schema from `ced.worker.evaluation`'s, they read it out of a payload
object written during a substrate run, and they use `field in producer_payload`
containment — the very shape T7 must not use, because a deletion cannot red it.
No existing helper compares a dict's exact key set, so the check is a
`set(...) == {...}` literal in the module that owns the schema: rung 6, one
obvious line, with no new helper and no new dependency.

### T1

Rung 2 stopped the search. `rg -n "Origin|CORS|StaticFiles|StreamingResponse|EventSource|text/event-stream|Last-Event-ID|after=" src tests contracts pyproject.toml` found the existing approval-route Origin precedent and contract comparison pattern, and found no reusable SSE/static helper. The implementation reused the approval-origin policy shape and contract comparison and added the minimum stream/static seams inside `src/ced/api/`.
