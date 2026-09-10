# Company Intelligence Desk

A reference **design** for a governed multi-agent application, worked through
public-company diligence. **No implementation exists yet** — what is here is the
charter, the architecture, and the record of how each decision was reached.

For an engineer deciding how to build an agent system that has to survive
review: where the untrusted-content boundary goes, what an agent is allowed to
do with a tool, and how anyone proves afterwards what actually happened.

## The patterns this project is a reference for

Each is specified in detail and **none is built**. The invariants below are
design commitments whose proof is a Phase 0 deliverable, not measured results —
each links to the section that specifies it, and every one has recorded limits
in [§ Known at ship](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#known-at-ship).

| Pattern | The failure it addresses | Specified in |
| --- | --- | --- |
| **Quarantine boundary** | Untrusted content reaching a component that holds tool authority. Free prose does not cross; validated references, closed-vocabulary labels and typed scalars do. Reference *selection* stays an attacker-influenced channel, and is recorded as unmitigated | [§ Injection defence](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#injection-defence) |
| **Argument-value authorization** | A well-typed but *unauthorised* tool call — the case a schema check passes and a permission check misses | [§ Structure](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#structure) |
| **Commit-before-action** | An action taking effect while the record of the decision that allowed it is lost | [§ Identity — two layers](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#identity--two-layers) |
| **Delegated authority ceiling** | An agent doing something the human who invoked it could not have done directly | [§ Authentication and authorization](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#authentication-and-authorization) |
| **Claim–commit–work with lease fencing** | A worker the platform killed mid-run acting twice, or a zombie worker writing after its lease expired | [§ Step execution](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#step-execution-claim-commit-work) |
| **Append-only event log with a resumable stream** | A run whose history can only be recovered by re-running it — which you cannot do against as-of-dated evidence | [§ Event log](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#event-log-and-stream-mechanism) |
| **Application-owned orchestration** | An agent framework owning your control flow, so its limits quietly become your architecture's limits | [§ Ownership split](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#ownership-split) |
| **Two-plane observability** | Telemetry quietly becoming the system of record for a claim you later have to defend | [§ The two planes](docs/architecture/inspectable-multi-agent-diligence/observability-and-evaluation.md#the-two-planes) |
| **Typed-artifact rendering** | Model output becoming markup, and an injection becoming code execution in a browser | [§ The presentation contract](docs/architecture/inspectable-multi-agent-diligence/experience-and-presentation.md#the-presentation-contract) |
| **Content-addressed evidence snapshot** | Evidence published after the fact silently entering a historical as-of analysis | [§ Context, evidence, and reproducibility](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md#context-evidence-and-reproducibility) |

Each is meant to be liftable into a system with nothing to do with company
diligence.

## Things you can do here today

**Decide whether detection-based injection defence is right for your system.**
Start at the [evidence survey](docs/product/research/prompt-injection-defence-survey.md),
then read § Four grounded facts and § Alternatives Considered → *Detection-based
injection defence*. In-band detection "collapsed from near-zero to **>90%
success** under adaptive attacks"; six production guardrails, including Azure
Prompt Shield and Meta Prompt Guard, were evaded at **up to 100%**. Then read
§ Known at ship — the architecture's list of open gaps — for the residual the
structural alternative does *not* close.

**Trace a ratified constraint from decision to consequence.** A ratified
constraint is one the project owner fixed, which the architecture may satisfy
but not reverse. Pick any row in
[the constraint index](docs/product/intents/README.md), follow it to the
document that owns its exact wording, then to where the architecture satisfies
it. Each constraint appears in exactly one place; everything else cites it.

## Status: designed, not built

The architecture is a Draft awaiting owner sign-off **and four Phase 0 spikes
that could change it**. It ships with five recorded gaps, and its security
posture rests on moderate, self-assessed confidence rather than independent
replication — stated in the architecture rather than left for a reader to find.

No ADRs have been written yet, and three edits to the architecture are
outstanding. So the decision record is real but not finished: it covers how each
control was chosen, what evidence it rests on, and what it does not cover.

## How this repository is organised

```
docs/
  CHARTER.md          mission, scope, principles — changes go through an RFC
  CONVENTIONS.md      how work is done here
  rfc/                proposals that change the charter or governance
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
