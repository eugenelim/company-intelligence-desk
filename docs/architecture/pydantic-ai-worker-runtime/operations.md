# Operations record: pydantic-ai worker runtime

This file carries the operational measurements for the worker runtime. Values
recorded here drive the `CED_STEP_DEADLINE_SECONDS` configuration and supply
the evidence for AC-0306 through AC-0311.

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
