# Operations record: pydantic-ai worker runtime

This file carries the operational measurements for the worker runtime. Values
recorded here drive the `CED_STEP_DEADLINE_SECONDS` configuration and supply
the evidence for AC-0306 through AC-0311. [§ SEC acquisition](#sec-acquisition)
covers how live SEC ingestion is configured, bounded and observed, for
`first-published-analysis`.

See
[`docs/specs/walking-skeleton-evidence/spec.md`](../../specs/walking-skeleton-evidence/spec.md)
for the acceptance criteria and
[`docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`](../../specs/walking-skeleton-evidence/notes/verification-ledger.md)
for the construction-test and mutation-proof record.

## Step-duration measurement (AC-0307, AC-0308)

**Sample:** 30 completed real steps, generated with `ced-evidence generate --n
30` against the local Docker substrate using `stub:counting` (TestModel, no
provider call). The executor writes `step.started` and `step.completed` events
via the full executor path with authentic `occurred_at` timestamps.

**Scoping predicate, stated beside the value:** the measurement pairs *every*
`step.started` and `step.completed` in the event log on `step_id`, with no
role, pool-class, principal or time filter. The sample is therefore whatever
completed steps the event log held when the command ran — a step another suite
completes against the same database enters a later sample. The record carries
this predicate in `step_duration.sample_scope`, emitted by the command, so the
value and the predicate cannot be separated.

**Method:** nearest-rank p99. Given n sorted durations,
`p99_index = ceil(0.99 × n) − 1` (0-indexed). The page threshold is
`p99 × 3`, derived from the same p99, not from an independent percentile.

**Platform substitution (Phase 1):** the sample was taken against TestModel on
a local Docker Postgres instance. TestModel executes in-process with no network
latency and no model inference; the durations measure executor overhead and
database round-trips only. A production deployment using a live Bedrock model
introduces inference time, network round-trips to the provider, and ECS
container performance — each contributing latency the local measurement does
not capture. This is the Phase 1 measurement under the local-container
substitution accepted in the spec Assumptions. AC-0314 names the resulting
limits rather than claiming platform equivalence.

| Metric | Value | Unit |
| --- | --- | --- |
| Sample size | 30 | steps |
| p99 (nearest-rank) | 0.087431 | seconds |
| Page threshold (p99 × 3) | 0.262293 | seconds |
| Platform | Darwin (arm64), local Docker Compose substrate | |
| Measurement date | 2026-10-01 (UTC) | |

Every value in that table is a field the command emitted, copied from the
machine-readable record below. The platform string is what `platform.system()`
and `platform.machine()` reported, not a product name written by hand.

**Machine-readable record:**
[`docs/specs/walking-skeleton-evidence/notes/measurements.json`](../../specs/walking-skeleton-evidence/notes/measurements.json)

## Step-deadline configuration (AC-0306)

`CED_STEP_DEADLINE_SECONDS` is set to `0.174862` seconds — the midpoint of
the measured interval `[0.087431, 0.262293]`. This value is derived from the
Phase 1 TestModel measurement above and satisfies
`p99 (0.087431) < step_deadline (0.174862) < page_threshold (0.262293)`. Both
`deploy/compose.yaml` worker services carry this value, and that is its one
provenance: a live-Bedrock calibration would be a different measurement
rather than a correction of this one.

**Which path arms the timer, and which does not.** Carrying the value is not
the same as acting on it, and today no deployed service acts on it. The
`ced-worker` entry point runs `sleep_step_body`, which reads only
`CED_STEP_BODY_SECONDS`; `config.step_deadline` is armed in exactly one
place, `make_step_body` in `src/ced/worker/executor.py`, whose only non-test
caller is `ced-evidence generate`. So both Compose services validate the
variable at boot — `verify_boot` refuses a malformed value — and then never
start a deadline from it. The calibration is therefore a recorded and
deploy-declared figure whose enforcement path is exercised by the measurement
command, not by the running pool. Wiring the executor step body into the
deployed worker is what would make the configured deadline bite; that is
deployment-side work this delivery does not do.

The construction test
`tests/worker/test_evidence.py::test_deployed_deadline_matches_the_record_and_sits_between_measured_limits`
reads the deadline from **two** places — `measurements.json`, where the
command recorded the value it ran with, and every `deploy/compose.yaml`
service that sets the variable — and asserts they agree before asserting
`p99 < step_deadline < page_threshold`. Changing the deployed value on either
worker service reds the gate, because one changed service disagrees with the
other and two changed services disagree with the record.

**The gate reads the committed file, not a running container.** A container
recreated from an older `compose.yaml` keeps the old environment until it is
recreated, so the claim this gate makes is about what this repository
deploys. Recreate the workers after changing the value if a substrate run
needs to see it.

## Cancellation measurement (AC-0309, AC-0310)

**Measured 2026-10-01** using `ced-evidence cancellation` with live AWS
credentials against `us.anthropic.claude-haiku-4-5-20251001-v1:0` in
`us-east-1`. This is the command's own output, copied from
`measurements.json`; every field, `measured` included, is one the command
emitted.

**The stream is checked to be in flight, not assumed to be.** The command asks
for a long reply, so generation lasts far longer than the gap between the first
chunk and the close. `close_stream()` samples whether this process's reader is
still running *immediately before* closing the response body, and the
classifier **refuses** a sample where it was not — a reader that had already
finished means the stream ended on its own and the close cancelled nothing. A
stream that ends before its first chunk is refused outright. So a recorded
`terminated` now means: the reader was running at the close, and finished
after it.

| Metric | Value |
| --- | --- |
| Outcome | terminated |
| Latency | 0.000364 s |
| In flight at close | true |
| Region | us-east-1 |
| Model id | us.anthropic.claude-haiku-4-5-20251001-v1:0 |
| Method | long generation; close response body while the reader is still running; observe reader join within 30 s window |

**Why this replaces the 2026-09-29 value.** The earlier run recorded
`terminated` at 0.000533 s, but the command then could not tell a cancelled
stream from one that had already ended: it requested a one-word reply, started
draining the stream before closing it, and admitted a stream that ended before
its first chunk as "still valid". That observation is not shown invalid, only
**unverified**, and by owner decision of 2026-10-01 the command was fixed and
the measurement taken once more. The new latency is close to the old one, which
is consistent with the old run having been a real cancellation too — but only
the new one is verified. The 2026-09-29 record is kept as history in the
verification ledger, marked unverified.

**One `measured` date in `measurements.json` is still operator-recorded.** The
quota block's `"measured": "2026-09-29"` predates the command's `measured`
stamp, and the quota read has not been re-run. The cancellation block's date
is now command-emitted.

### What this measurement does not establish

This is the record AC-0310 names, and it states both of that criterion's
limits here so the ledger and `spikes/README.md` can cite it rather than
restate them.

**The observation is local.** What was observed is that *this process* stopped
reading the provider stream within the window. It does not establish that the
provider stopped generating, and it does not establish that the provider
stopped billing. The latency is the wall-clock duration on this deployment's
path at the time of measurement, not a provider SLO.

**The `abandoned` branch is not reachable against a real provider by this
measurement.** Closing the response body locally always ends the local reader
promptly, so `terminated` is the only outcome this method can produce against
a live stream. That branch therefore ships *unobserved*, not
observed-and-absent: nothing here is evidence that a real cancellation never
falls into it. Observing the transport itself — which would make `abandoned`
reachable — is deferred to the follow-on
`cancellation-observes-local-reader-not-provider-connection` in `workspace.toml`
`[backlog].open`, which also carries the owner authority for the 2026-09-30
amendment that narrowed AC-0310 to the property a check reaches.

The offline construction test
`tests/worker/test_evidence.py::test_cancellation_outcome_comes_from_the_reader_completing`
drives both branches through stub callables, which is why `abandoned` has
construction coverage while having no live witness.

## Quota measurement (AC-0311)

**Measured 2026-09-29** using `ced-evidence quota` with live AWS credentials
against the Service Quotas API in `us-east-1`.

The quota code `L-58BE175A` was confirmed by a live `ListServiceQuotas` probe
for the `bedrock` service code on 2026-09-29. The returned quota name matches
the cross-region inference profile used by the selected model id
(`us.anthropic.claude-haiku-4-5-20251001-v1:0`). Region is taken from
`client.meta.region_name` (the resolved client's own metadata). Credential
and account metadata (access key, account id, ARN) are never read or written.

| Metric | Value |
| --- | --- |
| Region | us-east-1 |
| Service code | bedrock |
| Quota code | L-58BE175A |
| Quota name | Cross-region model inference tokens per minute for Anthropic Claude Haiku 4.5 |
| Value | 5,000,000 tokens per minute |

### What this measurement does not establish

Unlike the step-duration sample, this one involves **no platform
substitution**: it is a live read of the real Service Quotas API. What it does
not reach is different in kind.

**It is the quota of the account and Region the measuring credentials
resolved to, not of a deployed fleet.** A Phase 2 deployment runs under its
own account and task role, and the quota in force there is whatever that
account carries — this value does not predict it. Re-reading under the
deployment's own credentials is what would establish it.

**A quota is a ceiling, not a consumption measurement.** Nothing here observes
how much of it the worker pool actually draws, so it cannot say whether the
fleet would approach or exceed the limit. That needs throughput under load,
which Phase 1 does not run.

**It is a point-in-time read.** AWS quota values change on request and by
service update; the date above is part of the value.

## SEC acquisition

`ced-ingest` is the only code that reads from SEC. It stores one snapshot
before a run starts, and no run or API request ever fetches from SEC. The
acceptance criteria are AC-0401 through AC-0405 and AC-0417 in
[`first-published-analysis`](../../specs/first-published-analysis/spec.md).
Their test and mutation record is in that spec's
[verification ledger](../../specs/first-published-analysis/notes/verification-ledger.md).

### Configuration

`SEC_CONTACT` holds the declared client that SEC asks automated clients to
send, usually a name and a contact email. It is required for live ingestion
and for `observe`; `--offline-fixture` does not read it. The value is sent
only as the request's `User-Agent`. It never appears in an exception, log,
attempt record, stored object, or command output.

Each live request also takes a Postgres advisory lock, so the local substrate
must be up. See [§ Request gate](#request-gate).

### Request bounds

All bounds are fixed in `src/ced/adapters/sec/client.py`; none is
configurable.

| Bound | Value |
| --- | --- |
| Hosts | `data.sec.gov` and `www.sec.gov`, HTTPS only |
| Address | Resolved once. Only an address Python's `ipaddress` calls global and not multicast is used, and the connection goes to that address while TLS still verifies the SEC hostname |
| TLS | Certificate and hostname verification always on |
| Redirects | None followed; any `3xx` is refused |
| Connect timeout | 5 s |
| Read timeout | 15 s per read, cut to whatever remains of the total budget |
| Total budget | 30 s, counted from when the request gate admits the request. It is a hard wall-clock bound on the attempt and the gate, including a DNS lookup that has not returned |
| Submissions response | 5 MiB cap |
| Filing response | 10 MiB cap; a declared or streamed length over the cap is refused |
| Retries | None |

A refused or failed request stores nothing and releases the request gate.

### Request gate

Every SEC request, from any `ced-ingest` process sharing the substrate, takes
one Postgres session-level advisory lock. The holder keeps the lock for at
least 0.125 s after its request starts, so request starts are at least 0.125 s
apart. That is at most 8 a second, below SEC's published ceiling of 10 a
second.

The interval holds only while the holder's database session stays alive. If a
holder process dies, Postgres releases the lock at once, and the next request
can start sooner. This gate is not crash-safe quota accounting, and it is not
the fleet egress proxy the architecture calls for. It covers one local
substrate.

### Access observation

`SEC_CONTACT=<declared client> ced-ingest observe --out <path>` sends 60
requests for the Apple submissions document, one start per second. Each start
waits at least 1 s after the previous one, so a slow response delays the rest
rather than bunching them. The command writes a JSON record with:

- planned and started counts, which must both be 60;
- the target interval and the smallest interval observed, which must be at
  least 1 s;
- the time from first to last start;
- the count of each outcome;
- whether any `403` or `429` blocked the client;
- one record per attempt: gate wait, duration, zero retries, stop condition,
  HTTP status class, no-response class, and blocked flag.

**Outcome classes (AC-0417).** Every attempt record carries at least one of
`http_status_class` or `no_response_class`:

- `http_status_class`: `"1xx"`–`"5xx"` for statuses 100–599, `"other"` for
  any status outside that range.
- `no_response_class`: `"dns"`, `"tls"`, `"connect_timeout"`, `"read_timeout"`,
  `"total_timeout"`, or `"connection"` for any attempt that ends without a
  complete HTTP response.

`blocked` is `true` when `403` or `429` was received, regardless of what ends
the attempt (a transport failure after a blocked status keeps `blocked: true`).

**Stop condition order (AC-0417).** When both fields are set, the record's
`stop_condition` follows this fixed priority:

1. `no_response_class` — transport failure wins over all HTTP-level outcomes.
2. `"blocked"` — a blocked status wins over redirect, refused, or HTTP class.
3. `"redirect"` — any 3xx.
4. `"refused"` — size cap exceeded (declared or streaming), or malformed
   Content-Length (sign, non-ASCII, duplicate, or non-digit chars).
5. `"http_4xx"` or `"http_5xx"`.
6. `"refused"` — 1xx or status outside 100–599.
7. `"success"` — 2xx only.

**Content-Length strictness (AC-0402, AC-0417).** A declared Content-Length
must be exactly one header whose value is ASCII digit characters only (no sign,
no whitespace, no non-ASCII, no comma). A duplicate or malformed header is
refused before reading, and a body shorter than the declared length is a
`connection` failure.

**Declared-client validation (AC-0402).** The `SEC_CONTACT` value is
validated on the raw (unstripped) value before the gate is entered: 1 to 256
characters, each in U+0020–U+007E, with at least one non-space. A value that
fails the check causes the command to refuse with an error naming the variable
but never echoing the value.

**DNS resolution (AC-0402).** DNS runs in a daemon thread bounded by the
remaining total budget. A thread that does not finish in time produces
`no_response_class="total_timeout"`. Only public unicast non-multicast
addresses are admitted; a result containing only non-public addresses is
`no_response_class="dns"`.

**How to read it.** `blocked: true` means SEC refused the declared client at
least once. That is a valid observation, not a failed command, and the command
never retries for a better result. `blocked: false` means 60 requests at one a
second were all admitted. That is the whole claim. Sixty seconds of traffic do
not show how SEC treats a sustained or fleet-wide load, and the record says so
in its `statement` field.

### Recorded observation

The first live run was on 2026-10-04, and its unedited record is
[`sec-access.json`](../../specs/first-published-analysis/notes/sec-access.json).
All 60 attempts started, the smallest start interval was 1.00009 s, and every
attempt returned `2xx` with no retry. `blocked` was `false`. As stated above,
that covers one minute from one address and is not evidence about sustained
or fleet-wide access.

