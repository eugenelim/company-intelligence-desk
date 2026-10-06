# Spec: First published analysis

- **Status:** Shipped <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** ini-001-owner
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0003](../../adr/0003-repository-layout.md)
- **Brief:** docs/product/briefs/inspectable-diligence-mvp.md
- **Discovery:** evidence-backed-company-diligence
- **Contract:** [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml) — extends `POST /runs` with an analysis request and adds `GET /runs/{run_id}/analysis`
- **Shape:** mixed

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Agent Rules`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Outcome`, `What Changes`, `Durable Outputs`, `Follow-ons` and
> `Assumptions` are working material: they orient a reader and an author corrects
> them in place as the work teaches, without an amendment and without a review
> round.

## Outcome

An engineer can run one as-of-dated public-company analysis and receive a
deterministic research memo plus a machine-readable evidence manifest. Success
means the reported calculation resolves through exact XBRL facts to the archived
SEC filing, with no model call and no unsupported published claim.

## What Changes

- SEC ingestion — a bounded command stores one filing snapshot before a run starts.
- Deterministic analysis — the canonical filing produces one quarterly net-sales
  year-over-year calculation and a fixed-format memo.
- Run publication — the worker publishes one typed analysis artifact through the
  existing event-log and object-store path.
- HTTP surface — the run request accepts a pinned evidence snapshot and a read
  endpoint returns the published analysis.
- Operational evidence — SEC access observations record whether the declared,
  rate-respecting client is blocked without storing its runtime contact value.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Interface compatibility | Applicable | `contracts/openapi/runs.yaml` | work-loop | Generated-versus-committed contract check and API behavior checks | The analysis request and read operation agree with the served schema and runtime |
| User promise | Applicable | `README.md` | work-loop | A runnable ingestion-to-read example using placeholders only | The repository no longer claims that no implementation exists and the example matches the shipped contract |
| User guide | Applicable | `docs/guides/README.md`, `docs/guides/how-to/publish-first-analysis.md`, `docs/README.md`, `docs/product/README.md`, `AGENTS.md` | work-loop | The clean-substrate CLI-to-API flow is exercised from the guide | Both repository documentation maps name the first guide area, the product map no longer says guides are absent, the how-to orients the user, and every command and link matches the shipped interface |
| Operations | Applicable | `docs/architecture/pydantic-ai-worker-runtime/operations.md` | work-loop | SEC client configuration, source bounds, rate-gate behavior, and live observation method | An operator can reproduce the bounded ingestion and interpret a blocked or unblocked observation |
| Current architecture | Applicable | `docs/architecture/README.md`, `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md` | work-loop | Tree-derived component and rollout status; SEC observation recorded without changing ratified decisions | Built and owed statements match the shipped tree, and the two Draft companions remain untouched |
| Release history | Applicable | `docs/product/changelog.md` | close-work | User-visible slice summary | The released capability and its limits are recorded once |
| Delivery evidence | Applicable | `docs/specs/first-published-analysis/notes/verification-ledger.md`, `docs/specs/first-published-analysis/notes/sec-access.json` | work-loop | Mutation reds, end-to-end output, and the first bounded live SEC observation | Each final criterion has stable evidence and the observation states what it does not establish |
| Recorded decisions | Not applicable | — | — | The accepted architecture and product-intent decisions are sufficient | No ADR, RFC, top-level directory, or companion ratification is introduced |

## Agent Rules

### Always do

- Treat the archived SEC filing and its Inline XBRL as untrusted input; validate
  structure, identity, bounds, and provenance before publishing any value.
- Write source bytes, snapshot manifests, request payloads, and the final analysis
  artifact before appending an event that references them.
- Fail the ingestion or run when the required source, fact, period, unit, scale,
  lineage link, or snapshot match is absent, conflicting, or ambiguous.
- Keep SEC contact data runtime-only and redact it from stdout, stderr, logs,
  event payloads, object-store objects, test artifacts, and committed evidence.
- Keep the memo and manifest deterministic: identical pinned inputs produce
  byte-identical canonical JSON.

### Ask first

- A company, filing, as-of date, calculation, rounding rule, or source tier other
  than the canonical choices in this spec.
- A new dependency, database schema change, new top-level directory, or deviation
  from the accepted runtime architecture.
- Any model or agent call, any prose authored from filing content, or any work that
  depends on the two unratified architecture companions.
- Admission of a fallback source or a partial analysis after a source or lineage
  refusal.

### Never do

- Fetch SEC data on a user request path; a run consumes a snapshot created before
  `POST /runs`.
- Send filing prose, memo prose, or another attacker-authored string to a component
  holding tool authority.
- Treat a ticker, company name, URL, XBRL label, or scalar supplied by the filing as
  trusted because it is structured.
- Fall back to company facts, search results, another filing, scraped tables, or a
  model when the selected Inline XBRL facts do not resolve uniquely.
- Build the multi-view workspace, evaluation receipt, guarded result experience,
  filing-language comparison, or opposed readings in this slice.

## Testing Strategy

- **TDD, unit surface:** SEC response validation, XBRL extraction, duplicate-fact
  handling, Decimal calculation, deterministic rendering, and claim-lineage
  completeness. Each check earns a targeted mutation red.
- **TDD, integration surface:** the object store and Postgres prove content-addressed
  snapshots, request pinning, fenced publication, terminal ordering, and read-back.
  A privacy-safe committed Inline XBRL fixture replaces the network; no test fetches
  the live SEC site or reads the full Phase 0 filing fixture.
- **Goal-based check:** the generated OpenAPI document agrees with the committed
  contract, the SEC observation record conforms to its schema, and all repository
  gates pass.
- **Visual / manual QA, API and CLI surfaces:** a real `ced-ingest` invocation over
  the privacy-safe committed fixture, followed by `POST /runs` and
  `GET /runs/{run_id}/analysis`, returns the expected memo and manifest. A separate
  bounded live SEC observation exercises the real declared client once and records
  the first valid result.

## Acceptance Criteria

### Acquiring one immutable evidence snapshot

- [x] **AC-0401.** `ced-ingest` accepts only CIK `0000320193` and as-of date
  `2026-07-31` for this slice, selects accession `0000320193-26-000020` from SEC
  submission metadata, then fetches that accession's archived primary Inline XBRL
  document. The metadata-derived primary document must match
  `[A-Za-z0-9][A-Za-z0-9._-]{0,255}` and normalize to one relative basename inside
  the selected CIK/accession archive directory. An absolute URL, userinfo, dot
  segment, raw or encoded path separator or traversal, CIK/accession mismatch, other
  company, or other date is refused before a filing request, source write, or snapshot
  manifest.
- [x] **AC-0402.** The SEC client permits HTTPS requests only to
  `data.sec.gov` and `www.sec.gov`, requires its declared-client value from runtime
  configuration, and follows no redirect. The declared-client value is checked
  exactly as configured, before any trimming, wherever it becomes the `User-Agent`
  header, whichever function sends it. It must be 1 to 256 characters, each in
  U+0020 to U+007E, and at least one of them not a space. Any other value is
  refused before the gate is entered or a socket opened. No refusal, record, log,
  output, or exception chain carries the value in any rendering. Before connecting, it resolves the selected
  host and admits only public unicast addresses: Python 3.13 `ipaddress` must classify
  an address as global and must not classify it as multicast. It connects only to one
  of the validated addresses without a second resolution while retaining the selected
  host for TLS verification. Each request has a 5-second connect timeout, a 15-second
  read timeout, and a 30-second total budget measured after the shared gate admits it.
  The budget is a hard wall-clock bound on the attempt and on the gate it holds,
  including DNS resolution that has not returned. TLS certificate verification
  cannot be disabled. The submissions response is
  capped at 5 MiB and the filing response at 10 MiB; a declared length above the
  applicable cap is refused before reading, and a stream first crossing the cap is
  stopped and refused. Every attempt that does not end in AC-0417 `success`,
  including one ended by an unexpected exception, fails closed: it releases the gate
  session, stores no source or snapshot object, and records only redacted attempt
  metadata.
- [x] **AC-0403.** Every SEC request passes through one repository-wide gate that
  serializes request starts at least 0.125 seconds apart across concurrent ingestion
  processes using the shared Postgres substrate while the current gate holder's
  database session remains live. The second process is the first input that waits;
  the gate's monotonic elapsed-time check prevents a live contender from starting
  before the interval expires. Connection loss releases the lock and must not
  deadlock a contender, but this local gate makes no crash-safe or fleet-wide quota
  claim.
- [x] **AC-0404.** A successful ingestion stores the filing bytes by SHA-256 and
  stores a canonical snapshot manifest that names the company identity, as-of date,
  form, filing date, accession, archived source URL, retrieval time, filing digest,
  and object reference. Re-ingesting byte-identical evidence yields the same filing
  object reference; the manifest remains a new immutable observation when its
  retrieval time differs. Every ingestion round-trip recomputes the SHA-256 encoded
  in the filing and snapshot object references before parsing either object. A
  successful-ingestion check uses a distinctive runtime declared-client value and
  proves it is absent from every stored filing and snapshot object. The offline
  fixture contains only the filing identity and Inline XBRL contexts, unit, and facts
  needed by AC-0406; it contains no filing prose, signatures, or real-person
  identifiers and does not read or copy the full Phase 0 filing fixture.
- [x] **AC-0405.** Selection admits no filing dated after the requested as-of date
  and no source outside SEC submission metadata plus the selected archived primary
  Inline XBRL filing. A missing or ambiguous selected filing or required source
  fails ingestion without producing a snapshot manifest.

### Calculating and linking the published claims

- [x] **AC-0406.** The canonical filing resolves the consolidated quarterly net-sales
  facts for contexts `c-18` and `c-19` under concept
  `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` as USD values
  `109417` and `94036` at scale 6 for the periods ending `2026-06-27` and
  `2025-06-28`. Identical duplicate facts collapse to one identity; a conflicting
  duplicate, absent context, period mismatch, unit mismatch, or scale mismatch
  fails the run.
- [x] **AC-0407.** The calculation uses Decimal arithmetic for
  `(current - prior) / prior × 100`, rounds once to two decimal places with
  `ROUND_HALF_UP`, and publishes `16.36` with unit `percent`. Its lineage names
  both input fact references, the formula, unrounded numerator and denominator,
  rounding mode, output scale, and result.
- [x] **AC-0408.** The canonical artifact contains a fixed-format memo and an
  evidence manifest. The memo's sole factual sentence reports that quarterly net
  sales increased 16.36% year over year, from USD 94.036 billion to USD 109.417
  billion; no model, provider, tool call, or filing-derived prose contributes any
  byte of the artifact.
- [x] **AC-0409.** Every factual claim represented in the memo or evidence manifest
  carries at least one resolvable reference to an archived SEC source fragment or to
  deterministic calculation lineage whose inputs resolve to such fragments.
  Schema labels, field names, identifiers, and fixed headings are structural and are
  not claims; publication fails if any represented claim lacks a resolvable link.
- [x] **AC-0410.** Canonical JSON serialization makes two builds from the same
  snapshot bytes, request values, and schema version byte-identical. The artifact
  records the filing digest and as-of date, and no later evidence can enter a replay
  without changing the pinned snapshot reference.

### Publishing through the existing run boundary

- [x] **AC-0411.** `POST /runs` remains backward-compatible for existing run
  requests and additionally accepts an analysis request containing the canonical
  CIK, as-of date, and snapshot reference when `agent_role` is
  `first-published-analysis`; that role requires the object, and every other role
  refuses it. Before any object-store access, persistence, or run creation, the
  snapshot reference must match exactly
  `ced-first-published-analysis-snapshot/[0-9a-f]{64}`. A mismatched role, missing
  analysis object, unsupported company or date, overlong, wrong-scope, non-hex, or
  otherwise malformed reference, unknown analysis field, absent snapshot object,
  snapshot digest mismatch, or snapshot whose manifest disagrees with the request
  returns `422`. An object-store dependency failure returns a detail-free `503`.
  Each refusal creates no request object or run. Only the canonical CIK, as-of date,
  and snapshot reference enter the persisted request object.
- [x] **AC-0412.** An accepted analysis request is stored before the atomic run,
  `analysis`-class step, and `run.requested` commit, and that event's `payload_ref`
  pins the exact request object. An object-store failure creates no run; a database
  failure may leave an unreferenced object but never a run with a dangling request
  reference.
- [x] **AC-0413.** The `analysis`-class worker consumes the pinned snapshot, appends
  `step.started`, recomputes the snapshot digest from its raw bytes, and recomputes the
  filing digest from its raw bytes against both the manifest digest and object
  reference before parsing or calculation. It stores the complete analysis artifact,
  then appends `step.completed` and `run.completed` with that artifact reference under
  the existing lease fence. A digest, parse, source, calculation, lineage, or
  object-store failure appends `step.failed` followed by terminal `run.failed` through
  the same fenced run-terminal path, with no `run.completed` and no partial analysis
  artifact; no analysis run appends a model-, tool-, suspension-, or approval-related
  event.
- [x] **AC-0414.** `GET /runs/{run_id}/analysis` returns the typed artifact only when
  the terminal event is `run.completed` with a readable, digest-matching analysis
  payload. It returns `404` for an unknown run and `409` for a non-completed run, a
  non-analysis run, a missing reference, unreadable bytes, digest mismatch, or
  schema mismatch; it never returns a partial memo or manifest.
- [x] **AC-0415.** The new analysis read keeps the shipped Phase 1 direct-read
  posture: any caller that can reach the loopback-bound API and knows a run id may
  read the public-source artifact, with no caller-to-run ownership check. The
  response omits initiating and SEC-client contact values, and the OpenAPI contract
  states this posture and every `404`, `409`, `422`, and `503` outcome above.
- [x] **AC-0416.** One real local flow ingests the privacy-safe committed filing
  fixture, starts an analysis run through the public HTTP API, lets the deployed
  `analysis`-class worker complete it, and reads a memo plus manifest whose values and
  links satisfy AC-0406 through AC-0410. The shipped how-to guide reproduces that flow
  and links to the interface and operations references. No test-only database append
  or direct worker call stands in for that end-to-end path.

### Observing SEC access without overclaiming it

- [x] **AC-0417.** Each real SEC attempt records request class, gate wait,
  monotonic duration, retry count, stop condition, `blocked`, the status class of
  any status line received, and, when a transport failure ends it, one closed,
  redacted no-response class. Every attempt carries at least one of the two
  classes.
  - **Status classes:** `1xx` to `5xx`, and `other` for any status outside 100 to
    599. A status is received when `http.client` returns a response object for it.
    A status line it parsed and then discarded is not received.
  - **No-response classes:** `dns` when resolution fails or admits no public
    unicast address; `tls` for any `ssl.SSLError`; `total_timeout` when
    resolution or any part of the attempt outruns the total budget, which wins over
    a phase timeout the budget shortened; `connect_timeout` for a TCP connect or
    TLS handshake timeout;
    `read_timeout` for a request or body timeout; and `connection` for any other
    socket or protocol failure or unexpected `Exception`, such as a refused, reset,
    or garbled connection, or a body that ends before its declared length. An
    interrupt or system exit is not an attempt outcome. It stops the run, releases
    the gate, and stores nothing.
  - **Well-formed length:** a response without `Content-Length` is read under the
    stream cap. A response with one must carry exactly one, whose value is ASCII
    digits alone, or its length is malformed.
  - **`blocked`:** true when a received status is `403` or `429`, whatever ends
    the attempt.
  - **Stop condition:** the first of these that applies:
    1. the no-response class;
    2. `blocked`;
    3. `redirect` for a `3xx`;
    4. `refused` for a well-formed length over the cap, a malformed length, or
       a stream crossing the cap;
    5. `http_4xx` or `http_5xx`;
    6. `refused` for `1xx` or `other`;
    7. otherwise `success`, which only a `2xx` can reach.

  A bounded live observation schedules 60 attempts through the same client at one
  start per second for 60 seconds. Its command-produced
  `notes/sec-access.json` records the planned and started attempt counts, target and
  minimum observed start interval, first-to-last start duration, outcome counts, and
  whether any `403` or `429` blocked the client; a started-attempt count other than 60
  or a minimum interval below one second fails the observation. The record states that
  this short observation does not settle sustained fleet behavior. A `403` or `429`
  makes `blocked=true` a valid observed outcome rather than an acceptance failure by
  itself; the command does not retry for a more favorable result. The runtime
  declared-client value is absent from stdout, stderr, logs, the record, and committed
  artifacts.

### Gating the analysis worker on object-store readiness

- [x] **AC-0418.** After its database boot checks and before its first poll or claim,
  the `analysis`-class worker idempotently ensures the object-store bucket, writes the
  fixed bytes `ced-object-store-readiness-v1` to
  `ced-readiness/<sha256-of-those-bytes>`, and calls S3-compatible `HeadObject` for
  that exact key. A clean MinIO store completes this sequence without a separate
  provisioner. A bucket, put, or head failure prevents the poll loop from starting
  and leaves seeded analysis work unclaimed.

## Follow-ons

- Initiative owner: `workspace.toml` `[backlog].open` entry
  `same-origin-guard-trusts-the-request-host` — choose and enforce the trusted
  expected-origin configuration; this slice neither weakens nor repairs the guard.
- Initiative owner: `workspace.toml` `[backlog].open` entry
  `abandoned-stream-keeps-its-worker` — release abandoned stream workers; analysis
  publication does not change the stream implementation.
- Initiative owner: `workspace.toml` `[backlog].open` entry
  `cancellation-observes-local-reader-not-provider-connection` — observe provider
  transport cancellation; this slice makes no provider call.
- Initiative owner: `workspace.toml` `[backlog].open` dependency-scanning entry on
  `pyproject.toml` — add dependency and secret scanning independently; this slice
  adds no dependency.
- Initiative owner: [`walking-skeleton-run-state`](../walking-skeleton-run-state/spec.md)
  § Follow-ons, “A resumed run publishes an object carrying no output” — repair the
  model resume artifact separately; deterministic analysis neither suspends nor
  resumes.
- Initiative owner: [`inspectable-diligence-mvp`](../../product/briefs/inspectable-diligence-mvp.md)
  § Companion-dependent scope — ratify the experience and observability companions,
  then cut the later slice that delivers the multi-view workspace, guarded
  user-visible result, and evaluation receipt.

## Assumptions

None. The owner fixed the company and filing, calculation, source hierarchy,
material-claim reading, API-only presentation, deterministic memo, and existing
REST/OpenAPI boundary before this draft entered review.
