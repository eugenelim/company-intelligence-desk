# Plan: First published analysis

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done <!-- Drafting | Approved | Executing | Done -->
- **Repository anchors:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) §§ 4, 5, and 10 for deterministic ingestion, quarantine, evidence, and Phase 2; [`src/ced/domain/quarantine/mint.py`](../../../src/ced/domain/quarantine/mint.py) and [`tests/quarantine/test_mint_constrains_identities.py`](../../../tests/quarantine/test_mint_constrains_identities.py) for the standard-library Inline XBRL parser and its hostile-input checks; [`src/ced/adapters/objectstore/client.py`](../../../src/ced/adapters/objectstore/client.py) for content-addressed writes; [`src/ced/adapters/postgres/event_log.py`](../../../src/ced/adapters/postgres/event_log.py), [`src/ced/worker/executor.py`](../../../src/ced/worker/executor.py), and [`tests/e2e/test_ac_0327_committed_run.py`](../../../tests/e2e/test_ac_0327_committed_run.py) for request, fenced publication, and end-to-end construction; [`src/ced/api/main.py`](../../../src/ced/api/main.py), [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml), and [`tests/api/test_contract_agreement.py`](../../../tests/api/test_contract_agreement.py) for the HTTP contract. Deviation: no ingestion component or local egress proxy exists; this slice adds one serialized SEC acquisition path inside the existing adapter/worker boundaries and records that it does not prove fleet proxy behavior.

> **Plan contract:** this is the implementation strategy. It may change
> substantively only while its Status is `Drafting`, before approval records its
> baseline. After approval, `spec.md` and `plan.md` are pinned in substance;
> execution observations belong in
> `docs/specs/first-published-analysis/notes/verification-ledger.md`.
>
> **Not every field is contract.** `Touches`, `Tests` and `Done when` are what a
> completion gate reads, and they are pinned. `Design`, `Approach`, `Grounding`
> and `Risks` are working material before approval and are pinned with the rest
> of the plan afterwards.

## Approach

Build the source snapshot and pure calculation first, then connect that
deterministic path to the existing worker, event log, object store, and REST API.
The run never fetches live evidence: `ced-ingest` creates an immutable snapshot,
`POST /runs` pins it, and an `analysis`-class worker publishes one canonical artifact.
The last task exercises the real command, deployed local worker, and public API,
then refreshes only the durable records this capability changes.

The slice is intentionally narrow enough for one implementation session. It adds
no model call, dependency, database column, UI, companion-backed behavior, generic
company coverage, or second calculation. Each task is expected to stay below the
work-loop's large-task threshold; a task that crosses it stops for a contract
amendment rather than silently expanding.

### Planning assumptions

- **Files:** implementation stays within the task `Touches` sets: SEC and object
  adapters, one domain module, existing worker/API surfaces, their tests, and named
  durable records.
- **Done:** the acceptance-linked unit and substrate checks, committed OpenAPI
  agreement, the real local CLI-to-API flow, the bounded live SEC observation, and
  repository gates establish completion.
- **Not changing:** the shipped schema vocabulary, model executor, browser stream,
  approval/resume paths, two Draft companion documents, slices 3 and 4, and backlog
  residuals named by the spec.
- **Declined — generic issuer support:** `AGENTS.md` Cut before adding rung 1; the
  owner selected one fixture and broader coverage is not needed for the outcome.
- **Declined — XBRL library:** `AGENTS.md` Cut before adding rung 3; the existing
  standard-library parser already reads the required Inline XBRL identities and a
  small value reader completes this fixed calculation.
- **Declined — new context-service layer:** `AGENTS.md` Cut before adding rung 2;
  content-addressed object storage and the event payload reference already provide
  the needed snapshot pin for this slice.
- **Declined — repair adjacent residuals:** the accepted scope explicitly leaves
  them with their current owners; touching them would be a different delivery.

## Constraints

- `runtime-architecture.md` r8 remains ratified. The deterministic pipeline runs
  before any agent, live acquisition is outside the request path, source objects are
  immutable, and a run pins the snapshot it consumes.
- Quantitative evidence uses XBRL fact references. Filing prose is neither selected
  nor passed to an authority-bearing component.
- The existing partial unique index for `tool.invoked`, `steps.pool_class` claim
  predicate, and `owner_scope` columns already ship in migration 0002. This slice
  consumes the pool class and scope-qualified object keys but needs no migration.
  `awaiting_input` and its events stay out because the deterministic run neither
  asks for input nor suspends.
- A new privacy-safe minimal Inline XBRL fixture is the offline construction source.
  It carries only the selected filing identity, contexts, unit, and facts; tests do
  not read or copy the full Phase 0 filing fixture, make a network call, or commit
  filing prose, signatures, or real-person identifiers. Live SEC access occurs only
  in the bounded manual observation.
- The OpenAPI file describes the currently shipped interface, so the implementation
  task changes it with the runtime rather than making this planning-only PR claim an
  endpoint that does not exist.
- A source client must follow current SEC developer guidance: a declared client,
  HTTPS, and aggregate traffic no faster than the architecture's limit. The slice
  chooses a stricter serialized start interval, fixed finite timeouts, no redirects,
  and no automatic retry.
- No artifact introduced or updated by this slice contains the runtime SEC
  declared-client value or any account, credential, profile, personal, device, or
  absolute-home identifier.

## Grounding

- The recorded Phase 0 rebaseline and a throwaway standard-library HTML parse
  establish the filing identity, fact identity, values, and deterministic result
  owned by AC-0401, AC-0406, and AC-0407. The implementation creates a minimal
  fixture from only those public company and fact structures; it does not copy the
  full filing.
- Migration 0002 already carries the `tool.invoked` partial unique index,
  `steps.pool_class`, the claim predicate, and owner scopes. The current schema
  has no `awaiting_input` state; this deterministic path needs none of those owed
  additions.
- The current object-store writer is canonical and content-addressed but fixes one
  owner scope. The plan extends that existing mechanism rather than creating a
  second store adapter.
- SEC's official EDGAR API and developer-resource pages describe unauthenticated
  public APIs, declared automated clients, and the aggregate request ceiling that
  the stricter shared gate in this plan observes.
- The exact T2 stub compiles as Python and earns its intended collection red:
  `ced.domain.diligence` does not exist before implementation. The disposable
  scratch file is not part of the repository change.

## Construction tests

**Integration tests:**

- A substrate test runs concurrent ingestion clients and observes that the shared
  advisory gate separates request starts by the specified interval while the holder
  stays live, then proves a lost holder connection releases the contender without
  claiming crash-safe spacing.
- A substrate test writes a request object, drives the ordinary worker claim path,
  and reads the terminal artifact through the API without a direct event append.
- Contract agreement compares the generated FastAPI document to
  `contracts/openapi/runs.yaml`, including schemas and responses added by this slice.
- An offline end-to-end test uses only the privacy-safe committed fixture and the real
  MinIO and Postgres substrate.

**Manual verification:**

- Invoke `ced-ingest` in its fixed offline-fixture mode, submit the returned snapshot
  reference to `POST /runs`, wait for the deployed `analysis`-class worker, and read the
  typed artifact from `GET /runs/{run_id}/analysis`; record redacted request and
  response shapes in the verification ledger.
- Run the live SEC observation once with the runtime declared-client configuration,
  persist the command-produced JSON without editing it, and capture stdout, stderr,
  and structured logs in a disposable location. Mechanically compare each stream and
  the JSON with the in-memory runtime value, delete the disposable capture, and record
  only pass/fail redaction proof in the ledger.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| OpenAPI run and analysis contract | T4 | Contract agreement and API behavior checks | Served and committed schemas agree |
| User promise in `README.md` | T5 | Recorded CLI-to-API invocation | Example fields and output match the shipped contract |
| First user guide | T5 | Run the guide's clean-substrate flow as written | `docs/guides/` is mapped in `docs/README.md` and the root `AGENTS.md`, `docs/product/README.md` records it as present, and each command and reference matches the shipped interface |
| SEC operations record | T1, T5 | Client checks and command-produced observation | Configuration, limits, observation, and caveats agree with code |
| Current architecture maps | T3, T5 | Tree-derived worker and ingestion checks | Built/owed wording matches the tree without changing companion substance |
| Release history | T5 | User-visible flow green | Changelog names the capability and its fixed limits |
| Verification ledger and SEC observation | T1-T5 | Mutation reds, gates, API output, generated JSON | Every criterion has evidence and the observation contains no forbidden identifier |

## Design (LLD)

### Design decisions

- **Recorded snapshot before run:** `ced-ingest` is the only live SEC entry point;
  the API accepts its immutable snapshot reference. This preserves as-of replay and
  keeps third-party latency off the request path. Traces to AC-0401–AC-0405,
  AC-0411–AC-0412.
- **Deterministic composer:** a pure domain function extracts the selected facts,
  calculates with `Decimal`, constructs every link, and renders the fixed sentence.
  No framework model is constructed. Traces to AC-0406–AC-0410.
- **Existing publication path:** a role-dispatching worker body handles
  `first-published-analysis`; fault-injection workers keep their existing sleeping
  body and model roles keep the existing executor available to tests. Traces to
  AC-0413 and AC-0416.
- **Public-source read posture:** the analysis endpoint follows the shipped
  unauthenticated, loopback-bound run reads because its payload contains public SEC
  evidence only. Traces to AC-0414–AC-0415 and
  `contracts/openapi/runs.yaml`.

### Data & schema

Raw SEC filing bodies persist as bytes addressed by SHA-256. Snapshot manifests,
request objects, and analysis artifacts persist as canonical JSON objects in the
existing object store; Postgres schema is unchanged. Extend the object-store adapter
so callers supply one closed owner scope while preserving the current
`ced-step-lifecycle/<sha256>` wrapper for existing callers.

Worker readiness uses one deterministic operational sentinel: the fixed bytes
`ced-object-store-readiness-v1` at
`ced-readiness/<sha256-of-those-bytes>`. On each boot the adapter idempotently ensures
the payload bucket, puts those exact bytes, then issues `HeadObject` for that exact
key. Concurrent workers converge on the same object, and a clean MinIO volume needs no
separate provisioning task.

The snapshot manifest carries `schema_version`, company identity, `as_of_date`,
filing metadata, `retrieved_at`, `filing_sha256`, and `filing_ref`. The request object
carries only canonical CIK, as-of date, and `snapshot_ref`. The published analysis
carries:

- `schema_version`, company identity, as-of date, and filing identity;
- `memo.title` plus a `memo.claims` array of claim id, deterministic text, and
  evidence references;
- `evidence_manifest.sources`, each with source id, archived URL, digest, and source
  object reference;
- `evidence_manifest.facts`, each with evidence id, concept, context, period, unit,
  scale, decimal value, source id, and resolvable source fragment;
- `evidence_manifest.calculations`, each with evidence id, operation, input fact
  references, formula, numerator, denominator, rounding rule, output scale, unit, and
  value; and
- `evidence_manifest.claim_links`, one entry per factual claim id.

The artifact excludes run id, retrieval time, and other execution-varying fields so
the same pinned inputs serialize to the same bytes. Run-specific attribution remains
in the event log.

### Interfaces & contracts

`ced-ingest` exposes a live mode and an exact `--offline-fixture` mode. Both print one
JSON result containing the snapshot reference and public filing identity. Live mode
requires the answered SEC access policy's runtime `SEC_CONTACT`; the value is read
only when constructing the request and is never copied into an exception or record. A
companion observation mode uses the same client and writes the fixed
`notes/sec-access.json` schema.

`POST /runs` adds an optional `analysis` object to the existing request. When absent,
the current behavior is unchanged. When present, the route requires the exact analysis
role, validates the exact scope-qualified reference before its first object-store read,
reads the raw snapshot bytes, verifies their digest against the reference before
parsing, writes the request object, creates an `analysis`-class step, and passes that
object reference to `event_log.start_run`, which already calls the payload-capable
`append_run_event` function. No migration is needed.

`GET /runs/{run_id}/analysis` locates the terminal event, checks that the run was an
analysis run, reads the referenced bytes, verifies the digest encoded in the object
key before parsing, validates the full typed schema, and returns it. A failure at any
stage maps to the one `409` outcome rather than leaking object-store detail.

### Component / module decomposition

- `ced.adapters.sec` owns exact-host URL construction, redirect refusal, bounded
  reads, public-address resolution and pinned-address connection, the runtime
  declared-client header, the shared request gate, and observation records.
- `ced.worker.ingestion` owns the CLI, selection from submission metadata, and
  snapshot storage. It depends on adapters and domain types, never on API code.
- `ced.domain.diligence` owns snapshot and artifact types, Inline XBRL fact reading,
  Decimal calculation, deterministic memo construction, canonical serialization,
  and exhaustive lineage validation.
- `ced.worker.analysis` owns request loading, deterministic publication, and
  failure-to-event mapping under the existing lease fence.
- `ced.api` owns request validation and the typed read response; it performs no
  analysis.

### State & control flow

1. Ingestion fetches submission metadata through the shared gate, selects the fixed
   filing as of the fixed date, fetches the archived primary document through the
   same gate, then stores filing bytes followed by the snapshot manifest.
2. The client submits CIK, as-of date, and snapshot reference. The API validates the
   manifest, stores the request object, and atomically starts the run with its
   reference on `run.requested`.
3. An `analysis`-class worker claims the step, loads the exact request and snapshot,
   builds and validates the canonical artifact, stores it, then appends the existing
   completed events under the lease fence.
4. The read route returns only the complete artifact referenced by the completed
   analysis run.

### Behavior & rules

Fact identity is concept plus context. The value reader additionally requires the
specified periods, USD unit, scale 6, and identical values across duplicates. It
selects a stable source fragment from identical copies and rejects any conflict.
Decimal inputs are the filing display values with scale recorded separately; memo
billions derive from the scaled USD values without float conversion.

Lineage validation starts from each entry in `memo.claims` and
`evidence_manifest.claim_links`, follows calculation references to both input facts,
then follows each fact to one source and archived source fragment. The validator
enumerates these closed arrays; an unlinked claim or dangling reference prevents
serialization and publication.

### Failure, edge cases & resilience

- The SEC client uses normal TLS certificate verification, follows no redirect, and
  performs no automatic retry. Every attempt that does not end in AC-0417
  `success`, including one ended by an unexpected exception, and every malformed
  JSON or filing refusal, ends ingestion, releases the gate session, stores no source or snapshot object, and
  records only redacted attempt metadata.
- One Postgres session-level advisory lock is held from immediately before each SEC
  request start through AC-0403's minimum interval. It serializes all SEC hosts and
  releases on normal exit or connection loss. The interval guarantee covers competing
  live sessions; after holder connection loss the next caller proceeds and the adapter
  makes no crash-safe quota claim.
- Object writes precede event references. Orphaned content-addressed objects are
  tolerated; dangling references are not.
- The worker catches domain and adapter refusals at its boundary, appends
  `step.failed`, then appends terminal `run.failed` through the existing fenced
  run-terminal path and lets the pool release the claimed row as failed. It never
  falls through to the model executor for the analysis role and never leaves a failed
  analysis run non-terminal.
- The existing same-origin, abandoned-stream, provider-cancellation, dependency-scan,
  and resumed-output residuals stay unchanged and named in the spec Follow-ons.

### Quality attributes (NFRs)

The exact-host and response-size controls bound untrusted network input. The shared
request gate is stricter than the architecture's SEC ceiling and exposes wait and
status observations. Canonical bytes make reproducibility a digest comparison.
Structured logs and records use request class rather than full headers, so the
runtime declared-client value has no serialization path.

### Dependencies & integration

Use the standard library for HTTP, URL validation, HTML parsing, Decimal arithmetic,
hashing, and canonical JSON. Reuse psycopg, FastAPI/Pydantic, boto3, Postgres, and
MinIO already declared by the project. No package or service dependency is added.

The live client contract is checked against current SEC developer guidance during
implementation and recorded in the verification ledger. Fetched SEC content is data,
not instruction authority.

## Tasks

### T1: One bounded SEC ingestion path produces an immutable snapshot

**Owner:** implementer

**Depends on:** none

**Touches:** `src/ced/adapters/sec/**`, `src/ced/adapters/objectstore/client.py`, `src/ced/worker/ingestion.py`, `pyproject.toml`, `tests/ingestion/**`, `tests/fixtures/first_published_analysis.html`, `tests/fixtures/first_published_analysis.json`, `tests/persistence/test_owner_scopes.py`, `docs/specs/first-published-analysis/notes/verification-ledger.md`, `docs/specs/first-published-analysis/notes/sec-access.json`

**Verification mode:** mixed — TDD for validation, selection, bounds, rate gating,
storage, and redaction; goal-based for the command-generated live observation.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery predicate:
contract acquisition has identified the standard-library redirect hook and response
stream seam, and the existing object-store helper has been split without changing its
public wrappers. Constraint: tests inject a byte transport at the SEC adapter boundary
and may not add a second production fetch path. Required outcome: callable seams for
URL admission, bounded reads, selection, shared gating, content-addressed storage,
and redacted observation. Proof obligation: each AC-0401–AC-0405 and AC-0417 refusal
earns a targeted red before the live command runs.

**Tests:**

- AC-0401 and AC-0405: select the one filing from realistic submission metadata.
  Invoke the `ced-ingest` command main with injected transport and store spies for an
  unsupported CIK and as-of date; each returns refusal with zero source requests and
  zero object writes. Mutate the metadata-derived primary document to an absolute URL,
  userinfo, dot segment, raw and encoded separators or traversal, overlong basename,
  and mismatched CIK/accession; each refuses before a filing request or write. Refuse
  post-as-of filings, duplicates, missing fields, and any fallback attempt before
  storing a manifest.
- AC-0402: mutate scheme, host, any redirect, declared length, streamed length,
  DNS resolution, each non-global IPv4 and IPv6 class, IPv4 and IPv6 multicast, a
  resolution that changes between validation and connection, TLS verification,
  connect/read/total timeout, and missing runtime configuration independently. Assert
  the connection uses one already validated public-unicast address with the SEC
  hostname retained for TLS, certificate verification cannot be disabled, each refusal
  leaves no source or snapshot object, releases a waiting gate client, and exposes no
  runtime contact value. With an injected clock, hold one request behind the shared
  gate beyond the request budget, admit it, and prove the total timer starts only at
  admission while the attempt record keeps gate wait separate from request duration.
- AC-0403: two independently spawned OS processes open separate Postgres sessions and
  report gate-admitted start markers to the test parent; a process-local lock or deleted
  live-session hold interval makes their measured separation red. Terminating the
  holder process after its start marker releases the contender without deadlock, and
  the test does not assert the interval across that crash boundary.
- AC-0404: fixture bytes and manifest round-trip from MinIO, duplicate fixture writes
  retain the filing reference, retrieval-time changes move only the manifest reference,
  and replacing stored filing or snapshot bytes under an existing key makes the
  round-trip digest check fail before parsing. A successful ingestion uses a
  distinctive declared-client value, reads every stored filing and snapshot object
  through the ordinary store path, captures the ordinary `ced-ingest` JSON, stdout,
  stderr, and structured logs, and fails if any object or captured stream contains
  that value. A fixture-content check refuses filing prose, signature structures, or
  real-person identity fields and proves the offline path never opens the full Phase 0
  fixture.
- AC-0417: fixture responses drive success, `403`, `429`, DNS, TLS, and each timeout
  observation shape; each outcome proves one transport attempt, zero retries, and its
  stop condition. A fake monotonic clock proves the command follows AC-0417's complete
  start schedule, records all outcome counts, and fails on a missing or early start.
  The live command's generated record proves its planned and started counts, zero
  retries for every attempt, minimum start interval, first-to-last duration, blocked
  result, schema, and forbidden-value scan across JSON, stdout, stderr, and structured
  logs.

**Approach:**

- Extend the object-store helper with a closed owner-scope parameter while preserving
  all existing call behavior, then build the SEC adapter and CLI on that seam.
- Keep the offline fixture switch exact and path-free: it reads only the privacy-safe
  minimal filing and sidecar selected by the canonical constants.
- Run the bounded live observation after offline tests and substrate gates are green;
  persist its first valid output without hand-editing values.

**Done when:** the offline command emits a readable immutable snapshot, the live
observation artifact is command-produced and redacted, and the named ingestion tests
and mutations are green.

### T2: The pinned filing deterministically produces the linked memo and manifest

**Owner:** implementer

**Depends on:** T1

**Touches:** `src/ced/domain/diligence.py`, `tests/diligence/**`, `docs/specs/first-published-analysis/notes/verification-ledger.md`

**Verification mode:** TDD for the pure extraction, calculation, rendering,
serialization, and lineage invariants.

**Tests:**

```python
# STUB: AC-0407
from decimal import Decimal

from ced.domain.diligence import build_published_analysis
from tests.ingestion.fixture import FILING_CONTENT_HASH, recorded_filing


def test_the_canonical_filing_builds_the_linked_net_sales_claim() -> None:
    artifact = build_published_analysis(
        filing_html=recorded_filing(),
        filing_sha256=FILING_CONTENT_HASH,
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019326000020/aapl-20260627.htm"
        ),
        as_of_date="2026-07-31",
    )

    calculation = artifact.evidence_manifest.calculations[0]
    assert calculation.value == Decimal("16.36")
    assert artifact.memo.claims[0].evidence_refs == (calculation.evidence_id,)
    assert artifact.unresolved_claim_ids() == ()
```

- `test_the_canonical_filing_builds_the_linked_net_sales_claim` (AC-0407)
  `stub: true`

- AC-0406: mutate concept, context, period, unit, scale, value, absent facts, identical
  duplicates, and conflicting duplicates independently.
- AC-0407: mutate either input, the formula, float conversion, rounding mode, and
  output scale; assert the exact Decimal result and complete calculation lineage.
- AC-0408 and AC-0410: compare canonical bytes across repeated builds and change one
  pinned input at a time; monkeypatch the model adapter constructor to fail if called.
  Replace a distinctive non-fact filing string while retaining the required facts and
  assert that the memo still contains exactly AC-0408's approved factual sentence,
  with no mutated filing string or additional factual sentence.
- AC-0409: delete or dangle each claim, calculation, fact, source, and fragment edge;
  the exhaustive validator refuses serialization.

**Approach:**

- Reuse the hostile-input rules in `quarantine/mint.py` while adding value and context
  readers in the diligence module; do not widen the Phase 1 candidate-set API.
- Keep artifact types immutable and serialize Decimal values as canonical strings.

**Done when:** the exact stub and the AC-linked edge matrix are green, every named
mutation reds its owning check, and the fixture produces byte-stable canonical JSON.

### T3: An analysis-class worker publishes the deterministic artifact under the lease fence

**Owner:** implementer

**Depends on:** T2

**Touches:** `src/ced/adapters/postgres/event_log.py`, `src/ced/adapters/objectstore/client.py`, `src/ced/worker/analysis.py`, `src/ced/worker/main.py`, `src/ced/worker/pool.py`, `deploy/compose.yaml`, `tests/worker/test_analysis.py`, `tests/worker/test_pool_paths.py`, `tests/event_log/test_atomic_start.py`, `tests/e2e/test_analysis_publication.py`, `docs/specs/first-published-analysis/notes/verification-ledger.md`

**Verification mode:** TDD on the substrate for request pinning, dispatch, event
ordering, failure mapping, and artifact publication.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery predicate:
the event search has identified the authoritative `run.requested` and terminal event
payload reads, and the worker boot probe has selected the smallest role dispatch seam
that leaves fault-injection workers unchanged. Constraint: all writes use existing
append functions and the ordinary `Worker` claim path. Required outcome: callable
seams for request loading, analysis-role dispatch, and fenced publication. Proof
obligation: AC-0412, AC-0413, and AC-0418 checks fail on event reordering, missing
fence arguments, model fall-through, readiness ordering or dependency failure, and
each domain refusal before they pass.

**Tests:**

- AC-0412: extend `start_run` to pass a prewritten payload reference through its
  existing atomic append and create the step in pool class `analysis`; force
  object-store and database failures separately.
- AC-0413: drive the ordinary claim path and assert ordered event types, shared final
  artifact reference, digest-resolving bytes, and no forbidden event class. Each named
  refusal must append fenced `step.failed` then terminal `run.failed`, publish no
  partial artifact, and leave no non-terminal run. Replace snapshot and filing bytes
  under their existing keys independently; each fails its raw-byte digest check before
  parsing or calculation.
- AC-0416 preparation: analysis requests receive pool class `analysis`; Compose starts
  one worker pinned to that class without changing the two fault-injection workers or
  their tests. With the analysis worker running, an ordinary default-class API run
  remains `runnable` and is not claimed by it.
- AC-0418: after both database checks and before its first poll, the analysis
  worker idempotently ensures the bucket, writes the fixed readiness bytes to their
  content-addressed `ced-readiness/` sentinel key, then calls S3-compatible
  `HeadObject` for that exact key. A clean MinIO store proves the put and head precede
  the first poll. Bucket, put, and head failures independently prevent the poll loop
  from starting and leave seeded analysis work unclaimed.

**Approach:**

- Dispatch on the fixed `first-published-analysis` role before any model executor is
  constructed. Keep the existing sleep body available to the fault-injection pool.
- Add the `analysis`-class worker as a separate Compose service. Its pool predicate
  cannot claim default-class rows, so the Phase 1 two-worker recovery substrate and
  API tests remain intact.

**Done when:** a claimed analysis step reaches one complete fenced publication, every
refusal reaches fenced `step.failed` and terminal `run.failed` with no `run.completed`
or partial artifact, AC-0418 object-store readiness failures leave work unclaimed, and
existing recovery and model executor suites remain green.

### T4: The REST contract starts and reads a complete analysis without breaking existing runs

**Owner:** implementer

**Depends on:** T3

**Touches:** `contracts/openapi/runs.yaml`, `src/ced/api/models.py`, `src/ced/api/main.py`, `tests/api/test_contract_agreement.py`, `tests/api/test_start_and_read_a_run.py`, `tests/api/test_read_analysis.py`, `tests/e2e/test_analysis_publication.py`, `docs/specs/first-published-analysis/notes/verification-ledger.md`

**Verification mode:** mixed — TDD for request/read behavior and contract agreement;
manual API QA is completed in T5.

**TDD stub disposition:** `no stub (implementation-discovered)`. Discovery predicate:
the existing FastAPI dependency overrides and substrate fixtures have selected the
least-mocked seam for object-store read failures without duplicating route logic.
Constraint: checks drive the public routes and compare the full added schema slice,
not private helpers or a copied route list. Required outcome: behavior seams for the
optional analysis request, snapshot agreement, terminal artifact validation, and
documented error mapping. Proof obligation: AC-0411, AC-0414, and AC-0415 earn reds
against the unchanged route table and each invalid state.

**Tests:**

- AC-0411: existing non-analysis request bodies remain green. A non-analysis role with
  an analysis object and the analysis role without one each return `422`; every
  invalid or unknown analysis field, unsupported but well-formed CIK or as-of date,
  overlong, wrong-scope, non-hex, or otherwise malformed snapshot reference returns
  `422` before any object-store read, request object, or run row. A canonical positive
  control reaches the shaped snapshot read. An absent object, raw-byte digest mismatch,
  or manifest disagreement returns detail-free `422` after that read but still before
  writing a request object or run row; an object-store dependency failure returns
  detail-free `503` at the same boundary. Each post-read refusal emits exactly one
  structured diagnostic with reason class `snapshot_not_found`,
  `snapshot_digest_mismatch`, `snapshot_manifest_mismatch`, or
  `snapshot_store_unavailable`; object keys, object bytes, principals, and initiating
  or runtime-contact values are absent. A successful request object contains only the
  three canonical fields.
- AC-0414: completed, pending, failed, non-analysis, unknown, missing-reference,
  missing-object, digest-mismatch, invalid-JSON, and schema-mismatch cases map to the
  specified whole response or error with no partial body. The missing-reference case
  uses a completed analysis terminal event with no artifact reference and returns
  `409`. The failed case is driven through an actual analysis refusal and proves the
  run is terminal before the endpoint returns `409`. Each integrity failure emits one
  structured log with the run id and a closed reason class, while object keys, object
  bytes, and initiating or runtime-contact values are absent.
- AC-0415: direct read succeeds without an identity header, response and logs omit
  initiating and runtime-contact values, loopback default remains, and OpenAPI records
  the direct-read posture and the `404`, `409`, `422`, and `503` response set.
- Contract agreement removes or changes each new operation, request field, response,
  schema, and `x-spec` back-link to
  `docs/specs/first-published-analysis/spec.md#publishing-through-the-existing-run-boundary`
  in turn and observes the comparison red.

**Approach:**

- Validate the snapshot before writing the request object, but keep calculation and
  rendering entirely in the worker.
- Map all post-run artifact integrity failures to one public `409` while retaining a
  structured server log that contains no object bytes or contact value.

**Done when:** the committed and served contracts agree, this slice's OpenAPI additions
carry the tested `x-spec` back-link, the old run API remains green, and the complete
analysis is the only successful response shape.

### T5: The shipped local flow and durable records tell the same bounded story

**Owner:** controller

**Depends on:** T1-T4, T6

**Touches:** `README.md`, `AGENTS.md`, `docs/README.md`, `docs/product/README.md`, `docs/guides/README.md`, `docs/guides/how-to/publish-first-analysis.md`, `docs/architecture/README.md`, `docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md`, `docs/architecture/pydantic-ai-worker-runtime/operations.md`, `docs/product/changelog.md`, `docs/specs/first-published-analysis/notes/verification-ledger.md`

**Verification mode:** goal-based for documentation and repository gates; visual /
manual QA for the real CLI-to-API flow.

**Tests:** `no stub (goal-based and manual QA)`.

- AC-0416: start the clean substrate, migrate, run privacy-safe offline fixture
  ingestion, submit through `POST /runs`, let the Compose analysis worker finish, and
  read the public analysis endpoint. Record commands, exit statuses, public request
  shape, artifact digest, memo sentence, and lineage resolution in the ledger. Run
  the how-to guide's command sequence as written, verify every local link by opening
  its target, and keep the guide oriented to this bounded flow rather than duplicating
  reference material.
- AC-0417: cite the command-produced observation, verify its planned and started
  counts, per-attempt zero retries, minimum interval, first-to-last duration, outcome
  counts, blocked result, and all-stream redaction proof. State its bounded meaning
  without closing the architecture question on one short run.
- Read each durable destination as a whole, update only current claims affected by the
  shipped tree, add the `docs/guides/` source to both `docs/README.md` and the root
  `AGENTS.md` documentation table, replace `docs/product/README.md`'s absent-guide
  statement with the current guide destination, verify every new citation target, and
  run the identifier, intent, prose-total, spec-status, pre-PR, format, lint, type,
  offline, and full test gates.

**Done when:** the manual flow returns the accepted artifact, the first guide area is
mapped in both repository documentation maps and the living product map, its how-to
reproduces the accepted flow, durable outputs match the tree and contract, all gates
pass, and the two Draft companions have no diff.

### T6: Every SEC attempt follows the AC-0402 and AC-0417 rules, checked by one matrix

**Owner:** implementer

**Depends on:** T1

**Touches:** `src/ced/adapters/sec/client.py`, `src/ced/worker/ingestion.py`, `tests/ingestion/test_sec_client.py`, `tests/ingestion/test_attempt_matrix.py`, `tests/ingestion/test_observation.py`, `tests/ingestion/test_snapshot_storage.py`, `docs/architecture/pydantic-ai-worker-runtime/operations.md`, `docs/specs/first-published-analysis/notes/verification-ledger.md`

**Verification mode:** TDD. One table-driven matrix covers every attempt
outcome. Focused checks cover the declared-client value and fail-closed
behaviour.

**TDD stub disposition:** `no stub (implementation-discovered)`. The client
already classifies most failures; this task replaces the per-site handling
with the AC-0417 rule and closes the AC-0402 gaps:

- one validator of the declared-client value, called at the `User-Agent` sink in
  `fetch_url` on the exact configured value, and reused by `acquire_contact`;
- one classifier from exception to no-response class, applied at every site in
  `connect`, the request, the body read, and the `fetch_url` post-read budget
  check, with any unexpected exception becoming `connection`;
- the received status carried out of `_real_fetch` on every failure, so the
  status class and `blocked` survive whatever ends the attempt;
- one function choosing the stop condition in AC-0417's order;
- DNS resolution run in a thread that is abandoned when the total budget runs
  out;
- a strict `Content-Length` reader;
- `run_observation` and `run()` turning every failure into a record and one
  `error:` line, with no traceback.

**Tests:**

- AC-0417, the attempt matrix in `tests/ingestion/test_attempt_matrix.py`. It
  drives the real `fetch_url` through the injected seam. An oracle written in
  the test from the AC-0417 text sets each row's expected status class,
  no-response class, `blocked`, and stop condition. The matrix covers:
  - every reachable pairing of a received status (`200`, `103`, `301`, `304`,
    `403`, `429`, `404`, `500`, `600`) with an ending. The endings are a complete
    body; a body shorter than its declared length; a well-formed length over
    the cap; each malformed length; a stream crossing the cap; a fault during
    the body read; and the total budget spent inside the read loop or at the
    post-read check;
  - every no-status site: resolution, connect, handshake, and request, each
    with its faults and the total budget spent before or during it.

  Pairings `http.client` cannot produce are listed in the test with the stdlib
  reason. For example, a `1xx` or `304` has no body to fault.
- Mutation proof. The ledger records a table of each mutation and the row that
  reds it, covering:
  - every pair of stop-condition steps that can apply to one attempt and give
    different outputs;
  - dropping the status carry at each failure site after a received status;
  - each class mapping;
  - accepting each malformed-length form the AC refuses, including a sign, a
    separator, trailing whitespace, a non-ASCII digit, and two `Content-Length`
    headers, agreeing or not;
  - letting a `1xx` or `600` succeed;
  - accepting a short body;
  - accounting for DNS after the fact rather than bounding it;
  - removing the remaining-budget cap on the connect, the request, or the body
    read, each as its own mutant. Each has its own real-clock row that blocks in
    that phase only. The row uses a total budget below that phase's uncapped
    timeout: under 5 s for connect, and under 15 s for the request and the body
    read. It asserts that `fetch_url` returns, and the gate is released, within
    that budget. The class is the same with or without the cap, so the class is
    not the red.
- AC-0402, the 30-second budget. A resolver that blocks past the budget makes
  `fetch_url` return `total_timeout` and release the gate within the budget,
  measured on the real clock with a shortened budget.
- AC-0402, the declared-client value. Each case goes to `acquire_contact` and
  directly to `fetch_url`, and is refused before the gate is entered or a socket
  opened:
  - a tab, a lone `\r`, a lone `\n`, a trailing newline, a newline followed
    by a space, `\x7f`, a non-ASCII character, and a 257-character value, each
    built around distinctive marker text. The absence check fails on the
    marker text in any rendering across every refusal, record, log record,
    stdout, stderr, and the full `traceback.format_exception` chain;
  - an empty value and an all-space value, which assert refusal only.

  Moving the check after trimming, swapping the rule for `string.printable` or
  a `$`-anchored pattern, or a refusal that interpolates `{raw!r}` each reds a
  case.
- AC-0402, fail closed. Live ingestion, with a store spy and a gate spy, runs
  each of these cases:
  - a refused connection;
  - a reset during the filing body read;
  - an `ssl.SSLError` after the handshake;
  - an over-cap refusal;
  - a short body;
  - a `403`;
  - a `103`;
  - an unexpected `ValueError` during the request.

  Each fails with one `error:` line and no traceback, exits the gate, and
  writes no object. An injected `KeyboardInterrupt` stops `run_observation`
  and live ingestion, exits the gate, and writes nothing.
- `run_observation` records every failed attempt and carries on. The
  `{"refused": 2}` outcome check stays green.
- Security: a `security-reviewer` pass on the diff covers the validator, the
  redaction path, the classifier, and the bounded resolver.

**Done when:** the matrix and every focused check are green, each named
mutation reds as stated, the results are recorded in the verification ledger,
and `operations.md` § Access observation states the AC-0417 rules.

## Rollout

- **Delivery:** one implementation PR, with the optional request object preserving
  existing API clients. Reverting the image and OpenAPI change removes the new path;
  immutable unreferenced objects may remain and are harmless.
- **Infrastructure:** no new managed service or database migration. Compose gains one
  `analysis`-class worker using existing Postgres and MinIO.
- **External-system integration:** tests are offline. The only live dependency is the
  bounded SEC observation and normal live ingestion; either fails closed.
- **Deployment sequencing:** object-scope support and ingestion land before domain
  calculation, worker dispatch before API exposure, and API plus worker before the
  end-to-end witness. The OpenAPI and runtime changes land together.

## Risks

- The standard-library HTML parser is intentionally narrower than a validating XBRL
  processor. The fixed facts and fail-closed edge matrix make that narrowness visible;
  broad issuer support would require a separately approved dependency decision.
- The Postgres advisory gate controls every repository SEC request only while callers
  use the one adapter and the current holder session remains live. Connection loss can
  shorten one interval; it is not crash-safe quota accounting or the accepted fleet
  egress proxy, and the architecture record must retain those limits.
- A live SEC block prevents that attempt from returning source data but is a valid
  AC-0417 observation when the schedule, record, and redaction contract hold. Preserve
  `blocked=true`; do not retry for a better-looking result or treat it as evidence that
  sustained fleet access is settled.
- Direct unauthenticated analysis reads inherit the accepted Phase 1 deployment
  posture. The artifact is public-source data, but ingress authentication remains a
  deployment obligation rather than a property this slice supplies.
- `same-origin-guard-trusts-the-request-host` remains reachable on `POST /runs`.
  This slice adds no browser mutation or private source, but it does not repair the
  existing guard; the follow-on stays explicit.

## Changelog

<!-- Approval entries are added by the two human gates. -->

- 2026-10-03: spec approved by ini-001-owner
- 2026-10-03: plan approved by ini-001-owner
- 2026-10-04: AC-0402 and AC-0417 amended by owner decisions recorded in
  `notes/verification-ledger.md` § Finding 6 and its later decision blocks. The
  amendment adds the `connection` class and records both the status class and
  the no-response class. `blocked` follows any `403` or `429`, and the stop
  condition has a fixed order with only `2xx` as success. The declared-client
  value is limited to U+0020 to U+007E and checked at the header. Every failed
  attempt fails closed, DNS counts against the budget, and the `Content-Length`
  reading is strict. T6 adds the matching matrix.
- 2026-10-04: amended spec approved by ini-001-owner
- 2026-10-04: amended plan approved by ini-001-owner
