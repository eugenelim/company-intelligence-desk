# Publish the first analysis

This guide runs one evidence-backed analysis on your machine. It takes one
Apple Inc. quarterly filing and returns a memo with an evidence manifest. The
memo says quarterly net sales rose 16.36% year over year. The manifest links
that number back to the exact filing facts it came from.

No model is called. The memo and manifest are the same every time you run it.

## Before you start

You need:

- Python 3.13, with the project installed:
  `python3 -m venv .venv && ./.venv/bin/pip install -e '.[dev]'`
- Docker, with the standalone `docker-compose` binary.
- `curl`. The steps below also use `python3` to read one field from JSON.

Run every command from the repository root.

## 1. Start the local services

The run needs Postgres, an object store, and one worker that handles analysis
runs. Start the two stores first. Wait until Postgres accepts connections, then
create the schema, then start the worker:

```bash
docker-compose -f deploy/compose.yaml up -d --build postgres minio
until docker-compose -f deploy/compose.yaml exec -T postgres \
      pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
./.venv/bin/alembic upgrade head \
  && docker-compose -f deploy/compose.yaml up -d --build worker-analysis
```

The worker checks that it can write to and read from the object store before
it takes any work. If that check fails, the worker exits instead of waiting.

## 2. Store the evidence snapshot

A run never fetches from SEC. It reads a snapshot you store first. The
`--offline-fixture` mode stores a small committed copy of the filing's
structured facts, so this step makes no network call:

```bash
./.venv/bin/ced-ingest --offline-fixture | tee snapshot.json
```

The fixture lives in the source tree under `tests/fixtures/` and is not
installed with the package, so this mode needs a source checkout. Elsewhere
the command refuses with `error: --offline-fixture needs a source checkout`.

It prints one JSON line. `snapshot_ref` names the stored snapshot. The other
fields name the filing. The CIK, SEC's number for the company, is
`0000320193`. The form is `10-Q`, a quarterly report. The accession, the
filing's own id, is `0000320193-26-000020`. The filing date and the as-of date
are both `2026-07-31`.

## 3. Start the API

In a second terminal:

```bash
CED_API_PORT=58080 ./.venv/bin/ced-api
```

The API listens on loopback only.

## 4. Start the analysis run

Run this in the first terminal, where `snapshot.json` is:

```bash
SNAPSHOT_REF=$(python3 -c "import json; print(json.load(open('snapshot.json'))['snapshot_ref'])")
RUN_ID=$(curl -s -X POST http://127.0.0.1:58080/runs \
  -H 'content-type: application/json' \
  -d "{\"principal\": \"user@example.com\",
       \"agent_role\": \"first-published-analysis\",
       \"analysis\": {\"cik\": \"0000320193\",
                      \"as_of_date\": \"2026-07-31\",
                      \"snapshot_ref\": \"$SNAPSHOT_REF\"}}" \
  | python3 -c "import json, sys; print(json.load(sys.stdin)['run_id'])")
echo "$RUN_ID"
```

`principal` names who the run acts for. `agent_role` picks which configured
role runs it, and `first-published-analysis` is the one for this analysis.

A `201` response carries the new `run_id`, which the command saves as
`RUN_ID`. The API checks the snapshot before
it creates the run. A wrong company, date or reference, or a snapshot that
does not match, returns `422`, and no run is created.

## 5. Read the result

The worker checks for work every 30 seconds, so allow up to half a minute.
Then read the result:

```bash
curl -s http://127.0.0.1:58080/runs/$RUN_ID/analysis
```

- `200` returns the whole artifact.
- `409` means the run has not finished, or it failed. To tell which, read
  `curl -s http://127.0.0.1:58080/runs/$RUN_ID/events`. A `run.failed` event
  means the run failed. No `run.completed` or `run.failed` event yet means it
  is still pending.
- If it stays pending, check that the worker is still up with
  `docker-compose -f deploy/compose.yaml ps worker-analysis`. A worker that
  cannot reach the object store exits at start.
- `404` means no run has that id.

The artifact has two parts:

- **`memo`** holds one claim: "Quarterly net sales increased 16.36% year over
  year, from USD 94.036 billion to USD 109.417 billion."
- **`evidence_manifest`** links that claim to one calculation. The calculation
  links to two XBRL facts, the tagged numbers inside the filing, and each fact links to a fragment of the archived
  SEC filing.

## 6. Clean up

Stop the API with Ctrl-C, then remove the services and their data:

```bash
docker-compose -f deploy/compose.yaml down -v
rm snapshot.json
```

## What this does not cover

- **Other companies, dates or calculations.** This slice accepts only the one
  filing and the one calculation above.
- **A browser view.** The result is available through the API only.
- **Who may read a result.** Anyone who can reach the API and knows a run id
  can read that run's result. The API is meant to sit behind an authenticating
  ingress.

## Reference

- [`contracts/openapi/runs.yaml`](../../../contracts/openapi/runs.yaml) is the
  HTTP contract, with every status code above.
- [`operations.md` § SEC acquisition](../../architecture/pydantic-ai-worker-runtime/operations.md#sec-acquisition)
  covers live ingestion from SEC: the declared-client setting, request limits,
  and how to read an access observation.
- [`first-published-analysis`](../../specs/first-published-analysis/spec.md)
  is the feature's contract.
