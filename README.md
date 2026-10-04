# Company Intelligence Desk

A reference design, now partly built, for a governed multi-agent application,
worked through public-company diligence. What is here is the charter, the
architecture, the code built so far, and the record of how each decision was
reached.

For an engineer deciding how to build an agent system that has to survive
review: where the untrusted-content boundary goes, what an agent is allowed to
do with a tool, and how anyone proves afterwards what actually happened.

## The patterns this project is a reference for

Each is specified in detail, and several are now built.
[`docs/architecture/README.md` § What is built](docs/architecture/README.md#what-is-built)
says which. Each row links to the section that specifies it, and every one has
recorded limits in
[§ 9 Accepted limits](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#accepted-limits--open-and-not-a-task-list).

| Pattern | The failure it addresses | Specified in |
| --- | --- | --- |
| **Quarantine boundary** | Untrusted content reaching a component that holds tool authority. Free prose does not cross; validated references, closed-vocabulary labels and typed scalars do. Reference *selection* stays an attacker-influenced channel, and is recorded as unmitigated | [§ 4 Trust boundaries](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#trust-boundaries) |
| **Argument-value authorization** | A well-typed but *unauthorised* tool call — the case a schema check passes and a permission check misses | [§ 9 Decisions](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#decisions) |
| **Commit-before-action** | An action taking effect while the record of the decision that allowed it is lost | [§ Identity — two layers](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#identity--two-layers) |
| **Delegated authority ceiling** | An agent doing something the human who invoked it could not have done directly | [§ 4 Identity — two layers](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#identity--two-layers) |
| **Claim–commit–work with lease fencing** | A worker the platform killed mid-run acting twice, or a zombie worker writing after its lease expired | [§ 3 Runtime Model](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#3-runtime-model) |
| **Append-only event log with a resumable stream** | A run whose history can only be recovered by re-running it — which you cannot do against as-of-dated evidence | [§ 3 Runtime Model](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#3-runtime-model) |
| **Application-owned orchestration** | An agent framework owning your control flow, so its limits quietly become your architecture's limits | [§ 9 Alternatives considered](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#alternatives-considered) |
| **Two-plane observability** | Telemetry quietly becoming the system of record for a claim you later have to defend | [§ The two planes](docs/architecture/inspectable-multi-agent-diligence/observability-and-evaluation.md#the-two-planes) |
| **Typed-artifact rendering** | Model output becoming markup, and an injection becoming code execution in a browser | [§ The presentation contract](docs/architecture/inspectable-multi-agent-diligence/experience-and-presentation.md#the-presentation-contract) |
| **Content-addressed evidence snapshot** | Evidence published after the fact silently entering a historical as-of analysis | [§ 4 Evidence acquisition](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#evidence-acquisition) |

Each is meant to be liftable into a system with nothing to do with company
diligence.

## Things you can do here today

**Publish an evidence-backed analysis on your machine.** One command stores an
SEC filing snapshot, one `POST /runs` starts the analysis, and one `GET` returns
a memo with an evidence manifest. Every figure links back to the filing's XBRL
facts. It needs Python 3.13 and Docker:

```bash
./.venv/bin/ced-ingest --offline-fixture      # prints the snapshot_ref
curl -s -X POST http://127.0.0.1:58080/runs -H 'content-type: application/json' \
  -d '{"principal": "user@example.com", "agent_role": "first-published-analysis",
       "analysis": {"cik": "0000320193", "as_of_date": "2026-07-31",
                    "snapshot_ref": "<snapshot_ref>"}}'
curl -s http://127.0.0.1:58080/runs/<run_id>/analysis
```

[The how-to guide](docs/guides/how-to/publish-first-analysis.md) has the full
steps, including starting the local services and the API.

**Decide whether detection-based injection defence is right for your system.**
Start at the [evidence survey](docs/product/research/prompt-injection-defence-survey.md),
then read § Four grounded facts and § Alternatives Considered → *Detection-based
injection defence*. In-band detection "collapsed from near-zero to **>90%
success** under adaptive attacks"; six production guardrails, including Azure
Prompt Shield and Meta Prompt Guard, were evaded at **up to 100%**. Then read
§ 9 Accepted limits — the architecture's list of open gaps — for the residual the
structural alternative does *not* close.

**Trace a ratified constraint from decision to consequence.** A ratified
constraint is one the project owner fixed, which the architecture may satisfy
but not reverse. Pick any row in
[the constraint index](docs/product/intents/README.md), follow it to the
document that owns its exact wording, then to where the architecture satisfies
it. Each constraint appears in exactly one place; everything else cites it.

## Status: partly built

The runtime architecture was ratified on 2026-09-18, with five recorded gaps
accepted as open. Its security posture rests on moderate, self-assessed
confidence rather than independent replication. The architecture states this
itself rather than leaving a reader to find it.

The walking skeleton and the first published analysis ship. The analysis
covers one company, one filing and one deterministic calculation, through the
API only. Its two companion designs, for observability and for the user
experience, are still Draft.

## How this repository is organised

```
docs/
  README.md           what belongs where, and which parts must match reality
  CHARTER.md          mission, scope, principles — changes go through an RFC
  CONVENTIONS.md      why the work loop has the shape it does
  adr/                why a past choice was made
  rfc/                proposals that change the charter or governance
  guides/             how to use what ships today
  specs/              the contract for each feature, with its plan
  product/
    intents/          what the system must achieve, and who fixed what
    briefs/           delivery coordination
    research/         evidence, with per-finding confidence ratings
  architecture/
    inspectable-multi-agent-diligence/   the design and its two companions
```

Start with the
[architecture README](docs/architecture/inspectable-multi-agent-diligence/README.md),
which gives a reading order.

The `.claude/`, `.agents/` and `.codex/` directories are installed agent tooling
from [agent-ready-repo](https://github.com/eugenelim/agent-ready-repo). They are
vendored, are most of the file count, and are none of the interesting content.

## How decisions are made here

An **intent** records what must be true before any solution is chosen, and is
accepted only after independent review; the charter records why, and changing
its mission or principles takes an RFC.

Two rules do most of the work:

- **A fixed constraint has exactly one normative home.** Everything else cites
  it. A hand-copy drifts, and a drifted copy of an owner's commitment is
  indistinguishable from an author's preference.
- **Every outcome carries a falsifying observation.** If nothing could show the
  outcome was not met, it is not an outcome — it is a wish.

## Licence

Licensed under either [Apache License 2.0](LICENSE-APACHE) or
[MIT](LICENSE-MIT), **at your option**. The Apache arm carries an express patent
grant; the MIT arm keeps the material usable by GPLv2 projects, which Apache 2.0
alone would not.

**Contributions are not being accepted yet** — the process is undecided. If that
changes, contributions will be dual-licensed under the same terms unless stated
otherwise.
