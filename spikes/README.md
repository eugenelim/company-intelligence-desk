# Spikes

Throwaway code that produces **evidence, not product**. Nothing here ships, and
nothing here is a delivery slice. Phase 0 spikes exist to falsify architecture
hypotheses *before* the design is ratified, per
[`runtime-architecture.md`](../docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md)
§ Rollout.

A spike that cannot fail is not a spike. Each one below states what would have
falsified it.

## Phase 0 — status

| # | Hypothesis / test | Needs | Result |
| --- | --- | --- | --- |
| 1 | LiteLLM resolves Bedrock credentials from ambient workload identity, preserving streaming and the tool loop | AWS | **passed** |
| 2 | ADK step invocation under an application-owned orchestrator | model | **passed** |
| 3 | Stream resumption across forced disconnects, with concurrent writers | Postgres | **passed** |
| 4 | Quarantine split preserves analytical quality on a real filing | model | **falsified as run** — see below |
| P1 | `worker` role is refused `INSERT INTO events (type='policy.decision')` | Postgres | **passed** |
| P2 | Concurrent append/claim deadlock ordering | Postgres | **passed** |

## Running the Postgres spikes

```bash
cd phase-0
docker run -d --name ced-spike-pg \
  -e POSTGRES_PASSWORD=spike_only_not_a_secret -e POSTGRES_DB=ced \
  -p 55432:5432 postgres:17-alpine -c log_lock_waits=on -c deadlock_timeout=200ms
docker exec -i ced-spike-pg psql -U postgres -d ced -v ON_ERROR_STOP=1 < schema.sql

python3 privilege_test.py                  # P1
./.venv/bin/python concurrency_test.py     # P2  (needs psycopg)
```

The passwords here are local-only literals for a throwaway container. Nothing in
this directory is a real credential.

## P1 — the privilege split holds

7/7 assertions. The invariant under test, from § Identity — two layers: *the
database role that writes a `policy.decision` event is not the role that
performs the worker's general writes, and no runtime identity holds both.*

Postgres has no row-value-level grant, so the split is built by revoking direct
`INSERT` on `events` from everyone and exposing two `SECURITY DEFINER` functions
with **disjoint** `EXECUTE` grants. `app_worker` is refused the table, refused
the reserved event type by its own append path, and refused the policy function;
`app_policy` is refused the general append path. Both can still do their own
job, which matters — a split that also blocks the legitimate path proves
nothing.

**Finding: `SECURITY DEFINER` misattributes the caller.** The first version
raised `... (role %)` using `current_user`, which inside a definer function is
the *definer* (`ced_owner`), not the caller. An audit trail built on that would
name the wrong principal every time. Now uses `session_user`, which correctly
reports `app_worker`. Cheap to fix here; expensive to discover in a log during
an incident.

## P2 — lock ordering is load-bearing, and more precisely than stated

3/3 claims. Under 8 concurrent writers × 25 appends:

- **Sequence integrity.** 200/200 events, `seq` dense from 1 with zero
  duplicates. This is the concrete reason the design rejects `bigserial`: a
  per-run counter updated inside the append transaction is undone by rollback,
  so a rolled-back append leaves no hole, while a `bigserial` allocation
  survives rollback and does.
- **The designed order does not deadlock.** Zero deadlocks, zero errors.
- **Mixed orders do deadlock.** 12 observed.

**Finding: a uniformly inverted order does *not* deadlock.** The first attempt
made every writer take `runs` before `steps` and produced zero deadlocks — all
writers serialize on the same `runs` row, so no cycle can form. The hazard is
strictly one path inverting *against* another. The design already says this
("inverting the order **against the worker path**"), and the test now
demonstrates the distinction rather than a weaker claim: a rule that cannot be
shown failing is not a rule.

## Spike 1 — ambient workload identity holds

7/7, under a least-privilege role rather than under Admin. Ambient credential
resolution with no static key, streaming, and the tool-call loop all work
through LiteLLM to Bedrock, and a model outside the policy is refused — which is
what makes the scope meaningful rather than decorative. Cost $0.002.

**Finding: cross-region inference profiles change the shape of least privilege.**
A `us.`-prefixed profile routes to other regions, and authorization for the
underlying foundation model is evaluated in the **routed** region. Established by
running three policy variants against the same call:

| Tightening | Result |
| --- | --- |
| Region-pinned inference-profile ARN | allowed |
| Region-pinned foundation-model ARN | **denied** |
| `aws:RequestedRegion` equality condition | **denied** |

Both failing tightenings look obviously correct. A team applying them would read
the denial as a permissions bug and widen the wrong thing.

**Finding: these models are not invocable by raw model id.** Bedrock requires an
inference profile. The design already carries `inference_profile` in the producer
tuple, so the shape was anticipated; the spike establishes it is mandatory.

## Spike 2 — ADK sits under application control

4/4. The application drives each step; ADK does not own the outer loop.

The load-bearing check is the second: a tool call is **denied on argument
value** — same tool, one ticker allowed and another refused — and denied
*before* it executes. That is the seam the policy decision point occupies. If
ADK executed tools without an interceptable hook, argument-value authorization
would have nowhere to stand and `policy.decision` could not commit before the
action.

Checks 3 and 4 are a pair: step context is supplied by the application and
answered without a tool call, and a session with no prior turn does not know the
earlier fact. Without check 4, check 3 could pass on ADK quietly carrying state.

## Spike 3 — resumption holds under concurrent writers

4/4. Across **9 forced mid-stream disconnects** while four writers appended
concurrently: 160 events delivered, 160 distinct, covering 1..160 with zero
duplicates and monotonic order across every resume boundary.

The concurrency is what makes this worth running. A resumable stream over a
quiescent log is easy; resuming correctly *while appends continue* is the claim.

The client deliberately sent a **stale `after=0`** on every reconnect while
supplying the correct `Last-Event-ID`. Delivery had no duplicates, which is the
observable consequence of the server preferring `Last-Event-ID` over the query
parameter — the behaviour § Event log and stream mechanism specifies because
EventSource re-requests the original URL on reconnect. Had the server trusted
`after=`, every resume would have replayed from zero.

## Spike 4 — falsified as run, and usefully so

Run against a real Apple 10-Q filed 2026-07-31, on 30,000 characters of MD&A.
The same question was put to the same analyst model twice: once over the full
prose, once over **only** what survived the quarantine boundary — 6 observations,
2,029 characters, **6.8% of the prose**. Cost $0.022.

**The hypothesis does not hold at n=1.** Closed-vocabulary classification lost
distinctions a diligence reader depends on. Three losses, with different causes.

### 1. Causality cannot cross a closed vocabulary

The baseline found: *"Products gross margin expanded 560 bps YoY, driven partly
by tariff refunds — a non-recurring tailwind that inflates reported
profitability."*

The vocabulary contains `margin_expansion`. It has no way to carry *why*, and
"non-recurring tailwind that inflates reported profitability" **is** the
diligence judgement — the reader's question is not whether margin moved but
whether the move is repeatable. A label plus a scalar cannot express it, and no
enlargement of the label set fixes this: the content is an argument, not a
category.

### 2. The anchor-resolution check systematically drops tabular facts

Two of eight observations were rejected because their anchors did not resolve.
Both were **substantively true**, and the reasons differ:

| Dropped | Anchor the agent emitted | Reality |
| --- | --- | --- |
| `tax_rate_change` | `"effective tax rate 17.9 % 16.4 %"` | `effective tax rate`, `17.9` and `16.4` all appear — as **separate table cells**. The contiguous string does not exist |
| `margin_expansion` | `"Products gross margin percentage increased"` | The phrase appears **nowhere** in the document. Invented |

The first is the structural finding: **financial filings put their most material
quantitative facts in tables, and a verbatim-substring anchor can never resolve
a fact assembled from table cells.** Requiring prose quotes as the reference type
guarantees that the figures a diligence product exists to analyse are the ones
most likely to be dropped.

The second is the forgery risk the design already names — *"a quarantined model
induced to forge a reference"* — occurring here **with no adversary present**,
at 1 in 8, from ordinary paraphrase.

**The fail-closed parser worked.** Both were caught and neither crossed. That is
the mechanism behaving exactly as specified; the cost is that true observations
were dropped with the fabricated one.

### 3. A material legal exposure never crossed

The baseline surfaced the Epic/App Store injunction with Supreme Court review
pending, and separately an explicit management warning that semiconductor, NAND
and DRAM shortages are *expected to intensify*. `litigation_exposure` and
`supply_concentration` are both **in** the vocabulary, so this is not a
vocabulary limit — the quarantined agent simply did not select them under a
"most material" instruction. Selection is itself a channel, which is the
residual `runtime-architecture.md` § Known at ship already records as
unmitigated.

### The construction this spike tested was weaker than it needed to be

The quarantined agent here both *read* the prose and *emitted* the references,
so the parser could only reject bad ones afterwards — a detection control, of
the kind this design rejects everywhere else.

The stronger construction runs a **deterministic semantic pipeline first**:
XBRL facts, parsed table cells with coordinates, section boundaries. The agent
then only **selects and labels among candidates that already resolve**, and
cannot mint an identifier. Forgery stops being a thing to catch and becomes a
thing that cannot be expressed — and the agent's remaining task is small enough
for a light model.

Both failure modes this spike measured are artefacts of the weaker design: the
fabricated anchor could not occur, and the table-cell anchor would carry a cell
coordinate rather than a reconstructed quote. **What it does not fix is
§ Causality above**, plus untagged narrative, selection influence, and
cross-fact inference — see `runtime-architecture.md` § Known at ship.

### What this changes

The losses have identifiable causes, and the largest has a clean fix:
**quantitative claims should cross as XBRL fact references, not prose quotes.**
XBRL facts are already tagged, identified and individually addressable, so they
resolve deterministically — a genuine admitted form for exactly the facts prose
anchors handle worst. SEC publishes them through `companyfacts`, which the
ingestion tiers already reach.

Prose quotes remain right for narrative claims. Causality remains outside the
boundary, and that is a real, recorded cost rather than a bug to fix.

### Limits of this result

n=1: one filing, one section, one hand-written vocabulary of 20 labels, one
quarantined model (Haiku 4.5), one analyst (Sonnet 4.6), one prompt. A different
vocabulary, a stronger quarantined agent, or an XBRL-based reference type could
each move the result. It is evidence that the cost is real and where it falls —
not a measurement of its size.

SEC EDGAR returns **403 "Your Request Originates from an Undeclared Automated
Tool"** from this network, across several user-agent formats that follow SEC's
documented guidance. General egress is fine, so this is SEC's own Akamai edge
refusing this caller, not a local network block. Probing stopped there:
circumventing a deliberate access control is not a spike result.

**This is a deployment finding, not just a spike inconvenience.** § Trust
boundaries specifies the worker reaching EDGAR "via the egress proxy, hostname
allowlist, SEC-compliant user agent, rate limiting". A compliant user agent is
necessary and evidently **not sufficient** — the caller's egress address
matters. A Fargate deployment behind a NAT gateway inherits whatever reputation
that address carries, so this can fail in production having passed in
development.

To unblock: obtain one filing from an unblocked network, once, and record it as
a fixture. That is precisely what § Local development's recorded-fixture replay
exists for, and the fetch adapter then replays it for every subsequent run.

## What these results do not establish

- Both Postgres spikes ran against a **local container**, not RDS or Aurora.
  Lock behaviour is core Postgres and should carry, but managed-service
  differences — connection pooling, failover, `deadlock_timeout` defaults — are
  untested.
- `deadlock_timeout` here is 200 ms, well below the 1 s default, which makes
  deadlocks surface faster than they would in production.
- Neither test says anything about the *AWS* identity layer. They prove the
  database privilege model, which is where the `policy.decision` split actually
  lives.
