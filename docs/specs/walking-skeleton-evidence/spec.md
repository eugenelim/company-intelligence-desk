# Spec: Walking skeleton — evidence

- **Status:** Shipped <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § 10 Rollout, Phase 1
- **Discovery:** none
- **Contract:** [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml) — adds `GET /runs/{run_id}/events/stream` as `text/event-stream`; the paged JSON operation at `GET /runs/{run_id}/events` remains unchanged
- **Shape:** mixed

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Browser Surface`, `Boundaries`,
> `Testing Strategy`, and `Acceptance Criteria` are what a completion gate
> reads, and an amendment changes them. `Objective`, `Durable Outputs`,
> `Follow-ons`, and `Assumptions` are working material, corrected in place
> without an amendment.

## Objective

A browser follows a run's committed events as they arrive, resumes after a
lost connection, and closes the stream at a terminal event. Phase 1 also
leaves reproducible measurements for step duration, its derived operating
limits, model-stream cancellation, the regional token quota, and analytical
quality.

The repository state used for this contract is dated 2026-09-29.
`walking-skeleton-run-state` already owns and ships transitions, approval,
publication, bounded reject-and-resume cycles, and the clean-run path. This
spec consumes those outcomes; it does not reopen or duplicate them.

An unflattering result is still a result. The analytical comparison may remain
falsified, and it does. Cancellation is classified from what this process can
observe, and AC-0310 records which outcome that leaves unreachable rather than
implying both were live. The first honest run is recorded with its limits
instead of being repeated until it looks better.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Operations | Applicable | `docs/architecture/pydantic-ai-worker-runtime/operations.md` | work-loop | Step-duration sample, derived thresholds, cancellation result, and regional quota, each with platform and method | Recorded values agree with the shipped configuration and their verification artifacts |
| Reusable learning | Applicable | `spikes/README.md` | work-loop | Phase 1 results, substitutions, and limits | Hypothesis results are distinct from setup and teardown |
| Current architecture | Applicable | `docs/architecture/README.md`, `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md` | work-loop | Browser stream and Phase 1 measurement state re-derived from the tree | Both maps describe what is built and retain what is not |
| Interface compatibility | Applicable | `contracts/openapi/runs.yaml` | work-loop | Stream media type, cursor precedence and refusal, and terminal-close behavior | Contract and runtime checks agree |
| User-facing evidence | Applicable to the internal evaluation surface | `docs/ux/direction/walking-skeleton-evidence.md`, `docs/ux/walking-skeleton-evidence/evidence.md` | work-loop | Selected direction plus route, state, viewport, interaction, accessibility, and exception evidence | The manifest points to the browser artifacts that establish each claim and the built surface follows the selected direction |
| Recorded decisions | Not applicable | — | — | The UI stays below `src/ced/api/`; measurement and evaluation code stay within existing package layers | No top-level directory or architectural layer is added |

## Browser Surface

### Screen contract

| Field | Decision |
| --- | --- |
| Target user | An engineer evaluating the reference implementation |
| Primary job | Inspect a run's event history while new events arrive |
| Primary action | Open `/runs/{run_id}` and keep the page visible through completion |
| Expected outcome | Every committed event appears once, the connection state is clear, and a terminal run stops reconnecting |
| Next action | Inspect the final event and the recorded run state |
| First-screen hierarchy | Run identity and state; connection status; ordered event rows; cursor detail |
| Product proof | The visible sequence and cursor advance from committed data rather than a decorative activity indicator |
| Read/write character | Read-only |
| Critical states | Loading, waiting for the first worker event, streaming, reconnecting, terminal, unavailable, and offline |
| Responsive behavior | One readable column; metadata wraps without horizontal page scroll; rows remain distinguishable at narrow widths and high zoom |
| Accessibility | Semantic headings and status text, visible focus, non-color status labels, reduced-motion support, and literal rendering of untrusted event fields |
| Measurement event | No product analytics. Browser checks observe stream requests, rendered sequence values, and connection-state transitions locally |

### Aesthetic and design inputs

- **Aesthetic reference:** Raycast — dark surface, compact data rows, clear
  hierarchy, restrained accents, and no gradients.
- **Frontend mechanism:** a nested Vite and React project under
  `src/ced/api/ui/`; the API serves its built assets from the same origin.
- **Design handoff:**
  [`docs/ux/direction/walking-skeleton-evidence.md`](../../ux/direction/walking-skeleton-evidence.md)
  records the selected direction. This spec and plan provide the screen
  contract, state matrix, and seed tokens; no separate screen or token artifact
  exists.
- **Experience-design routing:** skipped because the experience-design pack is
  absent from this workspace.

### State matrix

| State | Trigger | Visible outcome |
| --- | --- | --- |
| Loading | Initial snapshot and stream setup have not completed | Named loading status and stable row placeholders |
| Waiting | Only the initial run event is available | Run identity remains visible and the page says it is waiting for work |
| Streaming | A live connection is delivering events | Ordered rows and cursor update without moving keyboard focus |
| Reconnecting | The stream ends before a terminal event | Existing rows remain; status announces reconnection; resume uses the last applied sequence |
| Terminal | A terminal event arrives | Final state is announced and the stream closes without reconnecting |
| Unavailable | The run is missing or the initial request fails | Error names the failed action and exposes a retry control |
| Offline | The browser reports loss of network | Existing rows remain; offline status and retry control are visible |
| Keyboard only | A user tabs through interactive controls | Focus is visible and retry can be invoked without a pointer |
| High zoom | The page is viewed at 200% zoom in a desktop viewport | Content reflows without two-dimensional scrolling |
| Reduced motion | The operating system requests reduced motion | State changes use no non-essential animation |
| Empty or no results | Not applicable: a valid run begins with `run.requested` | Covered by Unavailable for an invalid run |
| Permission denied | Not applicable: ingress authentication is outside Phase 1 | Named as a deployment residual |
| Forms and destructive actions | Not applicable: the surface is read-only | No form or destructive-action state exists |

## Boundaries

### Always do

- Treat r8 and r5 as ratified. Stop and surface a conflict instead of silently
  designing around one.
- Record what a check does not establish beside what it establishes.
- Record each measurement's sample size, platform, Region when applicable,
  method, and first observed result.
- Render every external event-envelope string as text. Display `payload_ref`
  as an inert identifier; do not dereference it or turn it into a link.

### Ask first

- Any change to a ratified decision.
- A dependency beyond those named in the plan.
- Provider spend above $5.
- A weaker criterion because the observed result is unfavorable.

### Never do

- Reintroduce an unconditional approval gate or alter the shipped run-state
  transition system.
- Repeat a measurement to select a better-looking value.
- Render model- or caller-authored content as markup or a navigable link.
- Append token deltas to the semantic event log.
- Fetch a live filing for the analytical comparison.
- Add permissive cross-origin access to make the development server work.

## Testing Strategy

Every acceptance criterion belongs to one verification group.

- **Construction tests:** AC-0306, AC-0323, AC-0326, AC-0335, AC-0336,
  AC-0337, and AC-0338. Each check is mutation-proved before it is accepted as
  coverage.
- **Browser tests:** AC-0304, AC-0305, and AC-0322. A real browser provides the
  page, request, reconnect, and DOM observations.

  **AC-0305's 100-disconnect run observes the client half.** Its stream
  requests are routed to a local fixture server so the `Last-Event-ID` header
  can be read off a real socket, which the browser does not expose to the test
  harness. That run therefore establishes that the browser resumes from the
  last applied sequence and reapplies nothing; it does not exercise the shipped
  route's cursor selection. Server-side precedence of `Last-Event-ID` over
  `after` is established separately by
  `tests/api/test_event_stream.py::test_last_event_id_precedes_query_cursor`
  against the real route.
- **Measurements:** AC-0307 through AC-0313. Commands refuse invalid samples
  and emit machine-readable evidence; the observed values are not pass/fail
  targets except where a criterion fixes an invariant.
- **Record review:** AC-0314. A reviewer checks that results, substitutions,
  residuals, and references are present without inferring completeness from a
  search pattern built from the listed items.

Mutation proofs, commands, witnesses, and the claim each establishes are
recorded in `notes/verification-ledger.md`. Review-round narrative is not
verification evidence.

## Acceptance Criteria

The source obligations are r8's Phase 1 browser stream and its exit
measurements for step duration, derived limits, cancellation, regional token
quota, and analytical quality. This spec carries r5 rollout criteria 1, 2,
and 7. The clean-publication obligation in r5 criterion 4 is already delivered
by `walking-skeleton-run-state` and is not repeated here.

Criteria that refine those sources add the reconnect observation, complete
plain-text rendering boundary, cursor validation, same-origin boundary,
static-file confinement, declared Phase 1 read posture, browser state
coverage, accessibility checks, producer identity, and honest residual record
needed to make the source obligations verifiable.

### Watching from a browser

- [x] **AC-0304.** A browser at `/runs/{run_id}` renders each event as it
  commits and, after the terminal event appears, observes that the stream has
  closed and does not reconnect.
- [x] **AC-0305.** Across 100 forced disconnects while a writer remains active,
  including tab reload and simulated sleep, the browser misses and reapplies
  no event. On native transport reconnects, the original URL keeps a
  deliberately stale `after=0`; the wire observation shows that the first
  emitted event follows the request's `Last-Event-ID`, and no such reconnect
  emits an event already held by the client.
- [x] **AC-0322.** A browser run containing markup and link targets in every
  caller- or model-controlled string exposed by the Event envelope, including
  `principal`, `agent_role`, `payload_ref`, and `idempotency_key`, displays
  those characters literally. `payload_ref` remains an inert identifier and
  is not dereferenced. A DOM search for the class of HTML-interpreting and
  link-constructing sinks finds no element or navigable target created from an
  external value.
- [x] **AC-0323.** The selected stream cursor — `Last-Event-ID` when present,
  otherwise `after` — must be an integer, non-negative, and no greater than
  the run's highest committed sequence. A violation from either source
  returns `422` rather than coercing the value or opening a stream.
- [x] **AC-0326.** The API serves the built browser client from its own origin,
  no permissive CORS policy is configured, and every state-changing route
  refuses a request whose `Origin` names another origin.
- [x] **AC-0335.** Every request path resolved by the static route remains
  beneath the built bundle root. Plain traversal, percent-encoded traversal,
  and an in-root symlink to an out-of-root file are refused; the page fallback
  serves only the fixed `index.html`.
- [x] **AC-0336.** For every applicable row in the Browser Surface state
  matrix, a browser check drives the named trigger and observes the named
  visible outcome. Reconnection and error states preserve already-rendered
  events.
- [x] **AC-0337.** The page has no automated WCAG 2.2 A or AA violation in its
  supported states, exposes a visible keyboard focus indicator and status
  text, reflows at 200% zoom without two-dimensional page scrolling, and
  suppresses non-essential motion when reduced motion is requested.
- [x] **AC-0338.** Phase 1 read access is intentionally unauthenticated: any
  caller that can reach the API and names an existing run id may read
  `/runs/{run_id}` and `/runs/{run_id}/events/stream`, with no caller-to-run
  ownership check. The server validates run existence and the selected cursor
  before opening a stream, returns `404` for an unknown run, and retains
  `ced-api`'s loopback-only default bind. Authentication and object-level
  authorization at deployed ingress remain outside this delivery and are
  named under AC-0314.

### Calibrating the deadline

- [x] **AC-0307.** The step-duration p99 is recorded from at least 30 completed
  real steps. The measurement command refuses a smaller sample and emits the
  sample size, platform, and method beside the value.
- [x] **AC-0308.** The primary page threshold is recorded as `p99 × 3`, computed
  from the same sample as AC-0307.
- [x] **AC-0306.** A construction test reads the recorded p99, configured
  `step_deadline`, and page threshold and asserts
  `p99 < step_deadline < page_threshold`.

### Measuring cancellation

- [x] **AC-0309.** Cancellation latency on an in-flight model stream is
  measured from the cancellation request to the observed outcome AC-0310
  names — the reader completing after the response body is closed — and
  recorded as a wall-clock value with Region, model id, and method. The
  endpoint is the same locally observed property in both criteria: no
  connection-level outcome is observed by this measurement.
- [x] **AC-0310.** The measurement command emits `terminated` when it observes
  that this process stopped reading the provider stream within its observation
  window — the reader completing after the response body is closed — and
  `abandoned` otherwise. The outcome is derived from that observation and not
  supplied by the operator.

  **The observation is local, and the record says so.** It does not establish
  that the provider stopped generating or stopped billing. Because closing the
  body locally always ends the reader promptly, the `abandoned` branch is not
  reachable against a real provider by this measurement, so that branch ships
  unobserved rather than observed-and-absent. This criterion states both limits, and
  `docs/architecture/pydantic-ai-worker-runtime/operations.md` § Cancellation
  measurement records them beside the measured value; the ledger and
  `spikes/README.md` cite that record rather than restating them. Observing the transport itself is the follow-on named below, and
  the amendment that narrowed this criterion to what a check reaches was the
  owner's decision of 2026-09-30, not a weakening chosen after an unfavourable
  result.

### Recording the regional token budget

- [x] **AC-0311.** The Bedrock tokens-per-minute quota is read from Service
  Quotas and recorded with the Region and quota identity used for the lookup.

### Re-baselining analytical quality

- [x] **AC-0312.** Spike 4's A/B comparison is rerun under the current
  Pydantic AI stack against the recorded 10-Q fixture. The record identifies
  the provider, model id, model revision or provider snapshot when exposed,
  role revision, prompt revision, and fixture revision, and reports the same
  causality, table-anchor, and selection/legal-exposure loss categories as the
  original.
- [x] **AC-0313.** The rerun reports the loss attributable to narrowing the
  admitted set separately from the loss attributable to crossing the
  quarantine boundary.

### Saying what Phase 1 did not establish

<!-- prose-totals:start -->
- [x] **AC-0314.** The Phase 1 record names each measurement's platform
  substitution and the property a deployed fleet would establish that the
  substitute does not. It also names these residuals:

  - The step-duration sample floor is too small to establish a production
    tail estimate, and the page threshold multiplies that estimate.
  - Neither the Python nor browser dependency tree has a vulnerability scan
    in the repository gate, and the browser runtime download is outside the
    lockfiles.
  - The browser evidence uses an unauthenticated loopback ingress and does not
    establish behavior behind deployed authentication.

  The record cites every residual enumerated by
  `walking-skeleton-run-state` AC-0329 without copying or counting that list.
  A record that omits any local residual, any cited sibling residual, or any
  measurement substitution fails this criterion.
<!-- prose-totals:end -->

## Follow-ons

- Observing the provider transport itself during cancellation, so the
  `abandoned` outcome becomes reachable, is deferred. It needs access to the
  underlying HTTP response or socket that the installed SDK surface does not
  obviously expose, and is naturally deployment-side work. Recorded in
  `workspace.toml` `[backlog].open` as
  `cancellation-observes-local-reader-not-provider-connection`, which also
  carries the owner authority for the 2026-09-30 amendment of AC-0310.

- AWS deployment to ECS Fargate, including ingress authentication, remains
  outside Phase 1. The record states which claims require that environment.
- Calibration of the finite reject-and-resume cycle cap belongs to the
  `walking-skeleton-run-state` AC-0321 follow-on. The cap already has a finite
  default and this spec does not absorb its tuning obligation.
- The role-load or role-compilation failure that can strand a run at
  `requested`, the unwritten `awaiting_approval` state, and the compiler-guard
  diagnostic backlog remain run-state or compiler work. This spec may cite
  them but does not change them.
- A task-to-`Touches` completeness check remains a separate process proposal.

## Assumptions

- The measurement environment can call the selected non-adaptive model
  `us.anthropic.claude-haiku-4-5-20251001-v1:0` and query Service Quotas. The
  implementation task performs one bounded capability probe and stops with a
  named unmet precondition if either capability is absent.
- Step duration, cancellation outcome, and analytical loss remain unknown
  until measured. Their values cannot weaken the criteria.
- Local containers substitute for Fargate. AC-0314 records the resulting
  limits instead of claiming platform equivalence.
- The recorded 10-Q fixture under `spikes/phase-0/fixtures/` remains the input
  to the analytical comparison; no live filing fetch is required.

## Changelog

- 2026-10-01: Shipped. Every acceptance criterion met and mutation-proved; the
  review record, every recorded break and the owner decisions taken during
  review are in `notes/verification-ledger.md`.
- 2026-09-30: Controlled amendment. AC-0310 restated to the property the
  measurement reaches, with the unreachable `abandoned` branch recorded and
  the transport-level observation deferred to a named follow-on; AC-0305's
  browser scope recorded in Testing Strategy. Owner authority and reason:
  `workspace.toml` `[backlog].open`
  `cancellation-observes-local-reader-not-provider-connection`.
- 2026-09-29: Browser stream, same-origin read surface, Phase 1 exit
  measurements and the analytical rebaseline implemented; AC-0314's residuals
  recorded in `spikes/README.md` § Phase 1 — evidence.
- 2026-09-29: Re-derived the contract from the tree after run-state shipped;
  removed transition and approval ownership, retained browser and Phase 1
  measurement work, added explicit browser state and accessibility criteria,
  and kept the UI below the existing API package boundary.
- 2026-09-27: Split run-state transitions, approval, publication, and bounding
  controls into `walking-skeleton-run-state`.
- 2026-09-18: Drafted the Phase 1 evidence delivery.
