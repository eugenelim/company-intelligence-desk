# Plan: Walking skeleton — evidence

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`src/ced/api/main.py`](../../../src/ced/api/main.py) for the current HTTP surface; [`src/ced/adapters/postgres/event_log.py`](../../../src/ced/adapters/postgres/event_log.py) for committed-event reads; [`src/ced/worker/executor.py`](../../../src/ced/worker/executor.py) and [`src/ced/worker/pool.py`](../../../src/ced/worker/pool.py) for provider execution and deadlines; [`spikes/phase-0/stream_resumption_spike.py`](../../../spikes/phase-0/stream_resumption_spike.py) for server-side cursor precedent; [`spikes/phase-0/quarantine_quality_spike.py`](../../../spikes/phase-0/quarantine_quality_spike.py) for the comparison being rerun; [`docs/ux/direction/walking-skeleton-evidence.md`](../../ux/direction/walking-skeleton-evidence.md) for the selected visual direction

> **Plan contract:** the implementation strategy. Substantive change is allowed
> only while Status is `Drafting`. After approval, spec and plan are pinned in
> substance; execution observations go to
> `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests`, and `Done when` are what
> a completion gate reads and are pinned. `Design`, `Approach`, `Grounding`,
> and `Risks` are working material.

## Approach

Build the stream and its browser first, then add reusable measurement and
evaluation commands, run the first honest measurements, and close the durable
record. The stream can be proved from deterministic local events. Provider
measurements stay behind a bounded capability probe so missing external access
does not become an implicit contract change.

The current package boundaries are sufficient. Browser source lives under the
API package, measurement and evaluation orchestration lives under the worker
package, and provider-specific calls remain under the Bedrock adapter. No new
top-level directory, application layer, schema, transition, approval path, or
agent role is introduced.

Governance and record edits remain controller work. T1 through T3 and T5
through T7 are implementation tasks and receive implementer dispatch receipts.
T4 and T8 are controller-owned record and closeout tasks. Each task's `Owner`
field is authoritative where this sentence and it disagree.

## Planning assumptions

- **Files:** implementation stays within the task `Touches` sets: API and
  nested UI for T1, existing worker and Bedrock adapter layers for T2 and T3,
  and governance or durable records for T4.
- **Done:** the named API, browser, worker, and evaluation checks establish the
  acceptance criteria; real browser and provider witnesses establish the
  manual or goal-based surfaces; repository gates establish integration.
- **Not changing:** schema, run-state transitions, approval semantics, agent
  roles, provider authority, deployed ingress, or top-level repository layout.

Declined additions:

- A top-level `ui/` directory — cut-before-adding rung 2: the existing API
  package is an adequate owner and avoids reopening the recorded layout.
- A payload-object reader — cut-before-adding rung 1: the event-envelope page
  does not need it, and adding one would open an unrelated access boundary.
- A new measurement or evaluation layer — cut-before-adding rung 2: the worker
  and Bedrock adapter already own the responsibilities.
- A dependency scanner in this delivery — cut-before-adding rung 1: the spec
  requires the unscanned trees to remain an explicit residual and does not
  authorize a repository-wide supply-chain program.

## Resolve-vs-surface record

- **Resolve:** nested Vite and React under the API package, by the current
  package boundary and the owner's 2026-09-29 approval.
- **Resolve:** Raycast as a secondary precedent, by the owner's 2026-09-29
  approval and the selected direction artifact that names the qualities taken
  and left.
- **Resolve:** cycle-cap calibration remains a run-state follow-on, by shipped
  AC-0321 and this spec's narrowed objective.
- **Resolve:** the direct Phase 1 read posture is intentionally unauthenticated,
  by AC-0338 and the loopback-default deployment boundary.
- **Surface on evidence only:** a denied provider or Service Quotas capability
  after the single bounded probe. No other unresolved value or authority choice
  remains before implementation.

## Constraints

- The shipped run-state transition system, approval interface, publication
  path, cycle cap, and spend controls are dependencies, not change targets.
- The browser surface is read-only and same-origin. Missing authentication is
  recorded as a deployment residual, not repaired here.
- The selected provider model is
  `us.anthropic.claude-haiku-4-5-20251001-v1:0`; an adaptive model fails the
  existing compile guard.
- Provider spend stops before $5 and any AWS resource created for evidence is
  registered with its teardown command and removed before session close.
- Repository files must not contain an account id, ARN, access key, profile
  name, email address, or user-specific absolute path.
- Measurement output records the first valid observation. A poor result is not
  permission to rerun.
- Reviewer findings pass through the finding-adjudication gateway before any
  repair.

## DR dispositions

| Decision | Disposition |
| --- | --- |
| Publication is an executor transition | Already shipped by `walking-skeleton-run-state`; consumed only |
| Liveness is the out-of-loop watchdog | Already shipped; unchanged |
| Reject-and-resume has a finite cycle cap | Already shipped under AC-0321; calibration remains that spec's follow-on |
| Analytical quality is re-baselined in Phase 1 | Lands in T3 |
| `trust_class` is a construction | Already shipped; T3 measures the cost of the resulting narrowed set |

## Construction tests and mutation proofs

Each automated check is accepted only after its named break makes that check
red. The ledger records the break, the failing artifact, the restored result,
and the claim established. A real measurement is a witness rather than a
coverage check; the command that validates and derives it is mutation-proved.

| Claim | Planned check | Required break |
| --- | --- | --- |
| Stream closes at terminal | `tests/api/test_event_stream.py::test_terminal_event_closes_the_stream` | Remove the terminal break from the generator |
| Stream operation stays published | `tests/api/test_contract_agreement.py::test_the_served_routes_match_the_committed_contract` | Remove the stream operation from the served document while leaving the route implemented |
| Header precedence and bounds | `tests/api/test_event_stream.py::test_last_event_id_precedes_query_cursor` and `::test_invalid_last_event_id_is_refused` | Prefer `after`, then remove each validation branch |
| Foreign origins are refused | `tests/api/test_same_origin.py::test_foreign_origin_is_refused_on_every_state_change` | Remove the shared origin guard from one discovered state-changing route |
| Origin refusal stays published | `tests/api/test_contract_agreement.py::test_the_served_routes_match_the_committed_contract` | Remove the `400` response from the served start-run operation while leaving runtime refusal intact |
| Static path confinement | `tests/api/test_static_ui.py::test_static_paths_never_escape_the_bundle_root` | Enable symlink following or replace the fixed fallback with caller-relative resolution |
| Browser continuity is wire-visible | `tests/browser/test_run_page.py::test_eventsource_resumes_after_forced_disconnects` | Across the 100-disconnect run with an active writer, tab reload, and simulated sleep, ignore `Last-Event-ID` on native reconnects while leaving stale `after=0` and client de-duplication intact; the check must red on wire precedence and on missed or reapplied sequence values |
| External strings stay text | `tests/browser/test_run_page.py::test_external_values_never_create_markup_or_links` | Send one enumerated external field through an HTML-interpreting sink |
| Browser states are complete | `tests/browser/test_run_page.py::test_applicable_state_matrix` | Suppress one named state transition while leaving event rendering intact |
| Accessibility and reflow hold | `tests/browser/test_run_page.py::test_accessibility_and_reflow` | Remove the focus style, status semantics, or narrow-width wrapping rule in turn |
| Phase 1 read posture is explicit | `tests/api/test_read_access.py` | Open the stream before the run-existence check, then change the API's default bind away from loopback |
| Sample floor and derivation hold | `tests/worker/test_evidence.py::test_step_duration_measurement_refuses_an_undersized_sample` and `::test_thresholds_share_one_sample` | Lower the sample floor, then calculate a threshold from a different sample |
| Configured deadline ordering holds | `tests/worker/test_evidence.py::test_configured_deadline_sits_between_measured_limits` | Set the configured deadline to either boundary |
| Cancellation classification is observed | `tests/worker/test_evidence.py::test_cancellation_outcome_comes_from_connection_observation` | Accept an operator-supplied outcome or ignore the connection-close observation |
| Quota Region and identity are recorded | `tests/worker/test_evidence.py::test_quota_record_uses_the_resolved_client_region` | Substitute a configured Region or omit the quota identity |
| Analytical costs remain separate | `tests/worker/test_evaluation.py::test_rebaseline_separates_narrowing_from_boundary_loss` | Collapse the two loss fields into one total |
| Record completeness holds | A closeout review against AC-0314, with class searches for residual markers and measurement records | Remove one required substitution or referenced residual and confirm the review fails |

PLAN stub tally: exact stub blocks — none; uncovered — none; `no stub
(implementation-discovered)` — T1, T2, T3, T5, T6, and T7; `no stub
(goal-based)` — T4 and T8.
Each discovery disposition below names the predicate and proof obligation that
must close before its task may call a check coverage.

## Durable-output map

| Durable output | Task | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| OpenAPI stream contract | T1, T5, T8 | Contract agreement plus stream behavior checks | Generated application schema and hand-authored contract agree |
| Browser direction and evidence manifest | T1, T5, T8, T4 | Selected direction plus route, state, viewport, interaction, and accessibility artifacts | `docs/ux/walking-skeleton-evidence/evidence.md` maps every required field and the built surface matches the direction |
| Operations record | T2, T6, T8, T4 | Machine-readable measurement output | Recorded values, platform, Region, method, and configuration agree |
| Analytical rebaseline | T3, T7, T4 | Machine-readable comparison and producer tuple | `notes/rebaseline.md` preserves separate loss categories and limits |
| Phase 1 learning | T8, T4 | Results and residuals | `spikes/README.md` separates established, substituted, and not established |
| Current architecture | T4 | Tree-derived statements | Architecture status no longer calls shipped browser or evidence work planned |

## Design (LLD)

### Stream contract and control flow

`GET /runs/{run_id}/events/stream` returns server-sent events. Each frame has
the committed sequence in `id:` and one JSON envelope in `data:`, whose
`type` field carries the committed event type. **No `event:` field is set,
and that is deliberate.** A named `event:` field dispatches the frame under
that name, so `onmessage` never fires and a client must register a listener
per type — an enumeration `src/ced/domain/events.py` makes impossible to keep
complete, because the step-scoped vocabulary is deliberately open. Carrying
the type in the payload lets one native `EventSource` `onmessage` handler
read every committed type, including one added later, and keeps the native
transport reconnect AC-0305 observes. The route prefers `Last-Event-ID` over `after`, validates
the selected cursor before opening the response, reads only committed events,
and ends after emitting a terminal event.

The synchronous event-log reader remains the source of truth. Starlette runs a
bounded polling generator outside the event loop. The generator owns its
database connection, releases it on disconnect, and emits no synthetic domain
events. The existing paged route and response model remain unchanged.

After initial history load, the browser constructs a native `EventSource`.
The forced transport-reconnect case uses `after=0`, so native resume keeps the
stale query value while the browser adds `Last-Event-ID`. Reload cases rebuild
the visible history from committed events before reopening the stream. Rows
are keyed by `(run_id, seq)` as a defensive idempotency layer, but the wire
assertion proves server precedence independently of that sink.

### Same-origin static delivery

The API serves a fixed packaged `index.html` for `/runs/{run_id}` and mounts
built assets below a fixed asset prefix using the framework's confined static
file primitive with symlink following disabled. A fallback never joins a
caller path to a filesystem root.

A shared origin validator applies to the class of state-changing routes
discovered from the application router. A present foreign origin is always
refused. Each route retains its existing absent-header policy: the approval
decision continues to refuse a missing `Origin`, while a route that currently
admits non-browser clients without the header remains available to them. No
CORS middleware is installed. The Vite development server uses a proxy.

### Browser component and state design

The component tree is deliberately shallow: page shell, run header,
connection status, event list, and event row. React text interpolation is the
only rendering path for model- and caller-controlled Event-envelope strings.
`payload_ref` is displayed as an inert identifier and is not dereferenced. No
`dangerouslySetInnerHTML`, markdown renderer, caller-derived `href`, or raw DOM
insertion is admitted.

The state reducer owns the spec's state matrix. It preserves the ordered event
map across reconnect, offline, and error transitions and stops reconnection
only after a terminal event. Status changes use a polite live region without
moving focus.

Seed tokens, established before component markup:

```css
:root {
  --color-canvas: #0d0f12;
  --color-surface: #171a20;
  --color-surface-raised: #20242c;
  --color-text: #f2f4f8;
  --color-text-muted: #a7afbd;
  --color-border: #323844;
  --color-accent: #8b7cf6;
  --color-success: #55c993;
  --color-warning: #e6b85c;
  --color-danger: #ef767a;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --radius-sm: 0.375rem;
  --radius-md: 0.625rem;
  --font-sans: Inter, ui-sans-serif, system-ui, sans-serif;
  --font-mono: "SFMono-Regular", Consolas, monospace;
  --focus-ring: 0 0 0 0.1875rem rgb(139 124 246 / 45%);
}
```

### Measurement command

A `ced-evidence` console command lives in the worker package and emits JSON.
Its step-duration subcommand pairs completed real-step events from the event
log, refuses an undersized sample, computes p99 with a documented nearest-rank
method, derives the page threshold from the same sample, and reads the shipped
deadline configuration for the ordering check.

The worker gains one explicit `CED_STEP_DEADLINE_SECONDS` configuration seam.
Boot validation accepts a positive finite value or an intentional unset value.
After the measurement, both worker services receive the recorded calibrated
value in the same change as the operations record.

The cancellation subcommand opens a real Bedrock response stream, waits for a
response chunk, requests cancellation by closing the response body, and
observes the reader through a bounded join. Reader completion within the
window produces `terminated`; otherwise the command records `abandoned` and
still releases local resources. This provider contract is acquired from the
installed SDK or first-party documentation before implementation.

The quota adapter asks Service Quotas for the model's token-per-minute quota
and takes Region from the resolved client. The record excludes credential and
account metadata. The implementation probe checks only whether the call is
available and reports the denied action or unavailable quota without reading
protected configuration.

### Analytical comparison

The evaluation command reuses the recorded fixture and current quarantine
types. It produces machine-readable A/B results for the original comparison,
the narrowed admitted set, and the post-boundary input. Causality,
table-anchor, and selection/legal-exposure loss stay separate, as do narrowing
loss and boundary loss. The producer tuple fingerprints repository-owned role,
prompt, and fixture inputs and records provider metadata when the provider
exposes it.

### Dependencies and installation

- Browser manifest: React, Vite, TypeScript, Playwright test support, and an
  accessibility assertion library, locked under `src/ced/api/ui/`.
- Python development manifest: Playwright's Python binding only if the browser
  runner remains in pytest after the contract probe. Existing boto3,
  botocore, Pydantic AI, pytest, and FastAPI dependencies are reused.
- The controller records verified frozen-install, browser-runtime install, UI
  build, browser-test, and evidence-command instructions in `AGENTS.md` before
  the delivery closes.
- Python package data includes only the built browser bundle needed by
  `ced-api`. Source maps are omitted from the packaged bundle unless a test
  proves they are needed.

## Tasks

### T1: Stream committed events into the same-origin browser

**Owner:** implementer subagent

**Depends on:** none

**Touches:** `src/ced/api/main.py`, `src/ced/api/stream.py`, `src/ced/api/ui/**`, `src/ced/api/static/**`, `contracts/openapi/runs.yaml`, `pyproject.toml`, `tests/api/test_contract_agreement.py`, `tests/api/test_event_stream.py`, `tests/api/test_read_access.py`, `tests/api/test_same_origin.py`, `tests/api/test_start_and_read_a_run.py`, `tests/api/test_static_ui.py`, `tests/browser/**`, `docs/ux/walking-skeleton-evidence/evidence.md`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`

**Verification mode:** mixed — TDD for API, contract, origin, and confinement
checks; visual/manual QA driven by Playwright for rendered states, reconnect,
keyboard, zoom, reduced motion, and DOM-sink observations. The artifacts are
the named pytest files and the evidence manifest.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery
predicate: the FastAPI/Starlette contract probe has selected the stream
generator lifetime and static-file primitive, and the browser contract probe
has selected the Python or Node Playwright harness. Constraint: tests must
drive the public HTTP/browser surfaces and may not invent a private helper to
make a stub compile. Required outcome: callable seams for cursor validation,
origin policy, path confinement, state reduction, and rendered DOM evidence.
Proof obligation: materialize the full named checks, earn their intended reds,
and record every mutation in the ledger before coverage is claimed. Visual and
manual QA has no stub by mode.

**Tests:**

- AC-0304, AC-0322, AC-0323, AC-0326, AC-0335, AC-0336, AC-0337, and
  AC-0338 through the planned API and browser checks above.
- AC-0305 through
  `tests/browser/test_run_page.py::test_eventsource_resumes_after_forced_disconnects`:
  one run forces 100 disconnects with a concurrent writer, including tab
  reload and simulated sleep; native reconnects retain stale `after=0` while
  the wire proves `Last-Event-ID` precedence; the final sink has no missing or
  reapplied sequence. The ledger records separate mutations for ignored
  header precedence and for a removed sink sequence.
- `tests/api/test_contract_agreement.py` proves the new OpenAPI operation and
  the affected start-run response agree with runtime. Its setup check asserts
  the stream operation exists without pinning a route total, and a mutation
  that removes the stream operation makes the comparison red. A separate
  mutation removes the served start-run `400` while leaving runtime refusal
  intact and must make the same comparison red.
- Each automated check has the matching mutation proof from the construction
  table recorded before it is called coverage.

**Approach:**

- Acquire the installed FastAPI/Starlette static-file and streaming contracts,
  and the Playwright/EventSource contract, before authoring unfamiliar APIs.
- Add the OpenAPI operation and `x-spec` back-pointer before runtime code.
- Implement the confined stream and static route, then the state reducer and
  compact event list against the approved screen contract and tokens.
- Preserve the Phase 1 direct-read rule explicitly: validate run existence and
  cursor before opening a stream, keep the API's loopback default, and add no
  payload dereference or caller-to-run authorization claim.
- Search for the class of state-changing routes when testing the origin guard;
  do not build the completeness assertion from a list copied out of the plan.
- Replace the existing hard-coded served-route list and route-count anchor
  checks with stream-specific positive assertions plus full generated-versus-
  committed route-table comparison; the completeness claim comes from the
  route class, not from a copied member list.
- Apply the selected creative direction's sequence spine, density, restraint,
  and compositional commitments without copying Raycast wholesale.

**Done when:** the API and browser criteria are green in a real browser, the
wire proves cursor precedence independently of client de-duplication, every
named mutation turns its owning check red across the ratified continuity run,
the locked install works from a clean dependency state, and the initial
evidence manifest names any remaining WCAG 2.2 gap.

### T2: Measure and configure the operating limits

**Owner:** implementer subagent

**Depends on:** T1 for a complete terminal run and approved external contract

**Touches:** `src/ced/worker/evidence.py`, `src/ced/worker/pool.py`, `src/ced/adapters/bedrock/quota.py`, `deploy/compose.yaml`, `pyproject.toml`, `tests/worker/test_evidence.py`, `docs/architecture/pydantic-ai-worker-runtime/operations.md`, `docs/specs/walking-skeleton-evidence/notes/measurements.json`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`

**Verification mode:** mixed — TDD for command validation, derivation,
configuration, cancellation classification, and quota serialization;
goal-based checks for the real completed-step sample, cancellation witness,
and quota read. The artifacts are the named pytest module, measurement JSON,
and operations record.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery
predicate: the event-class search has identified the durable start/completion
pair for a real step, and contract acquisition has identified the installed
Bedrock stream close and Service Quotas response seams. Constraint: the test
surface is the public `ced-evidence` data contract, not a test-only adapter.
Required outcome: callable seams for sample refusal, same-sample derivation,
deadline configuration, observed cancellation classification, and quota
serialization. Proof obligation: the named tests earn their reds against the
unimplemented command or installed mutations before the real witnesses run.
Goal-based provider witnesses have no stub by mode.

**Tests:**

- AC-0307 and AC-0308: sample refusal and same-sample derivation.
- AC-0306: recorded values and actual worker configuration satisfy the strict
  ordering.
- AC-0309 and AC-0310: fixture streams prove both derived outcomes before the
  real provider witness is recorded.
- AC-0311: a stubbed client proves quota identity and resolved Region; the real
  read supplies the witness.
- Every automated check has the named mutation proof in the ledger.

**Approach:**

- Implement and prove the offline command paths first.
- Perform one bounded provider and quota capability probe with the selected
  model. Stop this task with the unmet action named if it fails; do not inspect
  credentials or retry a policy denial.
- Generate the required completed-step sample once, run cancellation once, and
  query the quota once. Register and tear down any AWS resource if the chosen
  path creates one.
- Write machine-readable evidence, configure the measured deadline, and then
  prove the record/configuration ordering.

**Done when:** AC-0306 through AC-0311 hold; the operations record and JSON
evidence agree; the worker services use the recorded deadline; the first valid
provider observations are preserved; and no created AWS resource remains.

### T3: Rerun the analytical comparison under the current stack

**Owner:** implementer subagent

**Depends on:** T2's successful provider capability probe

**Touches:** `src/ced/worker/evaluation.py`, `tests/worker/test_evaluation.py`, `docs/specs/walking-skeleton-evidence/notes/rebaseline.json`, `docs/specs/walking-skeleton-evidence/notes/rebaseline.md`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`

**Verification mode:** mixed — TDD for fixture identity, producer-tuple shape,
loss categories, and cost separation; a goal-based provider run for the
recorded analytical witness. The artifacts are the named pytest module and the
rebaseline JSON and Markdown records.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery
predicate: the current Pydantic AI and quarantine contract probe has fixed the
evaluation entry point and the comparable A/B input shapes. Constraint: reuse
the recorded fixture and shipped quarantine types rather than inventing a
parallel evaluation model. Required outcome: a callable comparison that emits
the producer tuple and separate narrowing and boundary losses. Proof
obligation: the named construction test earns its red when those losses are
collapsed, before the goal-based provider witness runs.

**Tests:**

- AC-0312: the fixture, question, producer tuple, and loss-category schema are
  pinned and the current stack produces the recorded comparison.
- AC-0313: narrowing loss and boundary loss are independently derived and
  independently serialized.
- The loss-separation mutation turns the owning test red.

**Approach:**

- Reproduce the prior claim as written from the spike record before correcting
  any stale statement.
- Reuse the recorded fixture, current Pydantic AI model adapter, quarantine
  types, and selected non-adaptive model.
- Run the comparison once. Record falsification without retry if that is the
  observed result.

**Done when:** the producer tuple and all named loss dimensions are recorded,
the two causal costs remain separate, the result is labelled without being
selected, and provider spend across T2 and T3 remains below the approved cap.

### T4: Reconcile the Phase 1 record and close the delivery

**Owner:** controller

**Depends on:** T1, T2, T3, T5, T6, T7, and T8 — this task certifies that every
acceptance box has evidence, so it must follow the tasks that re-establish the
eleven criteria the 2026-09-30 amendment reopened. Scheduling it on the
completed tasks alone would dispatch it into a wave where its own `Done when`
is unsatisfiable.

**Touches:** `AGENTS.md`, `docs/architecture/pydantic-ai-worker-runtime/operations.md`, `docs/architecture/README.md`, `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md`, `spikes/README.md`, `docs/ux/walking-skeleton-evidence/evidence.md`, `docs/specs/walking-skeleton-evidence/spec.md`, `docs/specs/walking-skeleton-evidence/plan.md`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`, `workspace.toml`

**Verification mode:** goal-based record review. The artifacts are the
verification ledger, evidence manifest, tree-derived architecture searches,
repository lint output, and final spec-status output. No implementation-test
stub is owed for this controller-owned documentation task.

**Stub disposition:** `no stub (goal-based)`. The task verifies durable
records and repository status against named commands and class searches.

**Tests:**

- AC-0314 is reviewed against its residual class, the measurement artifact
  class, and the run-state residual section. The search is not constructed
  from the members already listed.
- Claims corrected in architecture records are first reproduced as written and
  checked against the tree.
- `python3 tools/lint-prose-totals.py` checks the guarded residual section.
- Repository gates and spec-status lint pass before PR creation.

**Approach:**

- Transfer machine-readable witnesses into the operator and Phase 1 records
  without adding unsupported interpretation.
- Re-derive architecture status from code, schema, manifests, and tests. Date
  remaining historical descriptions instead of leaving them in present tense.
- Complete the frontend evidence manifest with routes, supported viewports,
  states, interactions, keyboard and zoom checks, automated accessibility
  output, known exceptions, and gate history.
- Mark criteria complete only after their ledger entries point to a command or
  witness that can fail in the claimed direction.
- Derive and run the browser and evidence commands from their manifests, then
  record only the verified frozen-install, runtime-install, build, and test
  commands in `AGENTS.md`.

**Done when:** AC-0314 holds, the evidence manifest is complete, architecture
and Phase 1 records match the tree, all acceptance boxes have evidence, status
lint passes, and no prose total duplicates a living list.

### T5: Close the browser surface's coverage gaps

**Owner:** implementer subagent

**Depends on:** T1

**Touches:** `src/ced/api/stream.py`, `src/ced/api/ui/src/App.tsx`, `src/ced/api/static/**`, `tests/browser/test_run_page.py`, `tests/api/test_event_stream.py`, `tests/api/test_contract_agreement.py`, `docs/ux/walking-skeleton-evidence/evidence.md`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`

**Verification mode:** mixed — TDD for the API cursor case and the contract check; visual/manual QA driven by Playwright for rendering, terminal close, state coverage, sink class, and the accessibility scan.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery predicate: the catch-all frame seam and the per-state scan seam are chosen against the installed EventSource and axe-core surfaces. Proof obligation: each named mutation earns its red before coverage is claimed.

**Tests:**

- AC-0304 gains a browser check that no stream request is issued after the terminal frame. Break: remove `source.close()` from the terminal arm.
- AC-0304 and AC-0305: the frame carries no `event:` field, the type travels in the envelope, and a native `EventSource` `onmessage` handler renders every committed type. Break: restore the `event:` field and a per-type listener, then commit a type absent from that list — the check must red because the event never renders.
- AC-0337: the accessibility scan runs at each state the matrix check drives. Break: add an unlabelled control to the error branch and observe the scan red in that state.
- AC-0336: the Reconnecting status text and Streaming focus stability are observed. Break: suppress the reconnecting status; move focus on event arrival.
- AC-0322: the sink assertion enumerates the sink class — `iframe`, `script`, `object`, `embed`, `svg`, any caller-derived navigable target and `javascript:` — independent of the fixture's injected values. Break: route one enumerated field through each sink kind in turn.
- AC-0323: one request with `after` ahead of the highest committed sequence returns `422`. Break: narrow the bounds guard to the header path.
- The contract setup check drops its route total. Break: the generated-versus-committed comparison must still red when the stream operation is removed.

**Done when:** the Playwright checks are green in a real browser and the AC-0323 cursor case and contract-agreement check are green under `pytest`, each with its mutation recorded in the ledger; the served bundle is rebuilt from source and proved identical; and the evidence manifest states what each check does and does not reach.

### T6: Make the measurement record match its command

**Owner:** implementer subagent

**Depends on:** T2

**Touches:** `src/ced/worker/evidence.py`, `src/ced/adapters/bedrock/quota.py`, `deploy/compose.yaml`, `tests/worker/test_evidence.py`, `docs/specs/walking-skeleton-evidence/notes/measurements.json`, `docs/architecture/pydantic-ai-worker-runtime/operations.md`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`

**Verification mode:** TDD for the configuration read and the absent-input failure; goal-based for regenerating the measurement record from the command.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery predicate: the deployed-value read seam is chosen against the shipped Compose configuration. Proof obligation: before this task calls any check coverage, each break named in its `Tests` bullets — the changed deployed value, the renamed measurement file, the hand-edited emitted field, the operator-supplied cancellation outcome, and the ignored reader observation — is observed red against its owning check and green after restoration, with every witness recorded in the ledger.

**Tests:**

- AC-0306 reads the deployed `CED_STEP_DEADLINE_SECONDS` as well as the recorded value and asserts they agree and satisfy the ordering. Break: change the deployed value.
- AC-0306's check fails, rather than skips, when the recorded measurement is absent. Break: rename `measurements.json`.
- AC-0307: `measurements.json` is the command's actual output, platform string included, or the command emits every recorded field. Break: hand-edit a field and re-run the command.
- The step-duration sample's scoping predicate is recorded beside the value, and `docs/architecture/pydantic-ai-worker-runtime/operations.md` § Cancellation measurement — the record AC-0310 names — states that the observation is local and that `abandoned` is unreachable against a real provider.
- AC-0309 and AC-0310: the cancellation check is restated to the amended property — the reader completing after the response body is closed — and its name and docstring stop describing the discarded connection-close contract. Break: accept an operator-supplied outcome; and separately, ignore the reader observation. Both must red it.
- `make_references_test_model` either moves to a module whose responsibility it matches, with this task's `Touches` amended and the authority recorded, or its docstring states why a Service Quotas module owns it. Sustained finding 15 of the post-gates adjudication is discharged either way; leaving it unstated is not a disposition.

**Done when:** no recorded measurement is attributed to a command that cannot produce it, the Compose comment states one provenance for the deadline and says which services exercise it, and each break above is recorded red then green in the ledger.

### T7: Pin the analytical comparison's schema

**Owner:** implementer subagent

**Depends on:** T3

**Touches:** `tests/worker/test_evaluation.py`, `docs/specs/walking-skeleton-evidence/notes/rebaseline.md`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`

**Verification mode:** TDD.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery predicate: the producer tuple's key set is read from the shipped builder. Proof obligation: before this task calls coverage, deleting each producer-tuple key in turn, and each of the three loss-category keys, is observed to red the owning assertion and green after restoration, with the witnesses recorded in the ledger.

**Tests:**

- AC-0312: the producer-tuple keys and the three loss-category keys are asserted against fixed literals. Break: delete each of `role_revision`, `prompt_revision`, `fixture_sha256`, `framework_version` and each category key in turn.
- The record states that the loss categories are asserted rather than derived per run, and that narrowing loss is a difference between two independent single calls, so it bounds rather than isolates the vocabulary effect.

**Done when:** removing any pinned key reds the owning test, and the rebaseline record names both limits.

### T8: Reconcile the records against the amended contract

**Owner:** controller

**Depends on:** T5, T6, T7

**Touches:** `contracts/openapi/runs.yaml`, `docs/specs/walking-skeleton-evidence/spec.md`, `docs/specs/walking-skeleton-evidence/plan.md`, `docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`, `docs/ux/walking-skeleton-evidence/evidence.md`, `spikes/README.md`, `docs/architecture/pydantic-ai-worker-runtime/operations.md`, `workspace.toml`

**Verification mode:** goal-based record review.

**Stub disposition:** `no stub (goal-based)`.

**Tests:**

- Record hygiene, carried by this task's `Done when` rather than by a criterion: every recorded gate figure is re-recorded from one run of the gates against the final tree, in both the ledger and the evidence manifest.
- Record hygiene, carried by this task's `Done when` rather than by a criterion: `start_run`'s `x-spec` back-reference points at its owning spec or is scoped to the `400` response this delivery adds.
- AC-0305 and AC-0337 record clauses: the records no longer claim the browser run reaches the shipped route, nor that the accessibility scan covers states it does not.
- AC-0314: `python3 tools/lint-prose-totals.py` and the spec-status lint pass.
- The `stream_events` `description` in `contracts/openapi/runs.yaml` states the frame format the shipped encoder produces — the committed type in the JSON envelope, and **no** `event:` field. Nothing in `tests/api/test_contract_agreement.py` compares operation descriptions, so this is checked by reading the published description against `encode_sse_event`.
- AC-0310 record clause: the amendment's follow-on resolves where the spec says it lives: `cancellation-observes-local-reader-not-provider-connection` is in `workspace.toml` `[backlog].open`, not `closed`, and the Follow-ons and Changelog citations resolve to it.

**Done when:** no record states a claim the tree does not support; AC-0310 states its two limits and `operations.md` § Cancellation measurement records them beside the measured value, with the ledger and `spikes/README.md` citing that record rather than restating them; and the follow-on register entry is open where its citations say it is.


## Rollout

- Deliver the tasks sequentially on the current feature branch. Keep commits
  semantic so browser, measurement, evaluation, and record changes remain
  independently reviewable inside the PR.
- Use the repository pull-request template and report facts only. Do not put
  reviewer rounds, method narration, credentials, profile names, or local
  absolute paths in the title, body, commits, or comments.
- Merge with `Merge PR #N: <subject>.` after required local gates and review
  roles are clean.
- No production deployment occurs. Rollback removes the API stream/static
  routes, browser bundle, console command, configuration seam, and records;
  there is no schema reversal.

## Risks

- **Native EventSource reconnection can make a broken server look correct.**
  Client de-duplication hides replay, so AC-0305 inspects the wire.
- **The browser toolchain adds an unscanned dependency tree.** The lockfile and
  frozen install give repeatability, not vulnerability assurance; AC-0314
  keeps that limit visible.
- **Cancellation is observed only at the local reader.** The 2026-09-30
  amendment settled this: the command records that this process stopped
  reading, the transport-level outcome is deferred to the
  `cancellation-observes-local-reader-not-provider-connection` follow-on, and
  the existing hard step timeout remains the functional bound.
- **Local p99 is not fleet p99.** The record states the platform substitution
  and leaves Fargate remeasurement to deployment work.
- **Provider or quota access may be absent.** A single bounded probe names the
  unmet permission or capability; it does not trigger credential inspection,
  repeated retries, or a weaker criterion.
- **The analytical comparison may remain falsified.** That is evidence, not a
  reason to select another run.

## Changelog

- 2026-09-30: Frame-format amendment — build strategy approved by eugenelim.
- 2026-09-30: Frame-format amendment — spec scope approved by eugenelim.
- 2026-09-30: Amended build strategy approved by eugenelim.
- 2026-09-30: Amended spec scope approved by eugenelim.
- 2026-09-30: Controlled amendment. AC-0310 narrowed to the observable
  property and AC-0305's browser scope recorded; T5 through T8 added to close
  the coverage gaps adversarial review sustained. T1 through T3 are complete
  and their sections are unchanged.
- 2026-09-29: Build strategy approved by eugenelim.
- 2026-09-29: Spec scope approved by eugenelim.
- 2026-09-29: Rebuilt the plan from the current repository after run-state
  shipped; removed state-machine, schema, approval, top-level layout, and ADR
  work; placed the UI below the API package; added the state contract, seed
  tokens, selected creative direction, mutation ledger, bounded provider probe,
  and explicit closeout work.
- 2026-09-27: Moved run-state transitions, approval, publication, and bounding
  controls to `walking-skeleton-run-state`.
- 2026-09-18: Drafted the Phase 1 evidence plan.
