# Company Intelligence Desk

An inspectable reference implementation of a **governed multi-agent
application**, demonstrated through evidence-backed public-company diligence.

The diligence is the demonstration, not the point. The point is that every part
of how an answer was produced is open to inspection: the workflow, the evidence,
the context each step received, the policies applied, the verification, and
where a human retained authority.

Most published references are one of two things — a toy demonstration that skips
governance, or a production system whose internals nobody outside the team can
see. This is an attempt at the third thing.

## Status: designed, not built

**There is no implementation yet.** This repository currently contains the
charter, the intents, the architecture, and the reasoning that produced them.
The architecture is a Draft awaiting owner sign-off, and it ships with five
recorded gaps rather than pretending to have none.

That means the patterns below are **specified, not demonstrated**. If you came
looking for code that embodies them, it does not exist yet, and this README
would rather tell you that than let you find out three files in.

What the repository *does* offer today is a complete decision trail: how each
control was chosen, what evidence it rests on, what it does not cover, and who
decided.

## The patterns this project is a reference for

| Pattern | Problem it addresses | Specified in |
| --- | --- | --- |
| **Quarantine boundary** | Untrusted content reaching a component that holds tool authority. Only validated references, closed-vocabulary classifications and typed scalars cross; free prose never does | [`runtime-architecture.md`](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md) § Injection defence |
| **Argument-value authorization** | A well-typed but unauthorised tool call. Authorization decides on argument *values*, not just tool names | Same file, § Structure |
| **Commit-before-action** | An action taking effect while its decision record is lost. The policy decision must commit before the invocation is issued; a failed append is a denial, not a retry | Same file, § Structure and § Identity — two layers |
| **Delegated authority ceiling** | An agent amplifying the authority of the human who invoked it | Same file, § Authentication and authorization |
| **Claim–commit–work with lease fencing** | A worker resumed after host loss double-acting, or a zombie worker writing after its lease expired | Same file, § Step execution: claim, commit, work |
| **Append-only event log with a resumable stream** | Reconstructing what a long-running agent workflow actually did, after the fact, without re-running it | Same file, § Event log and stream mechanism |
| **Application-owned orchestration** | An agent framework owning your control flow, so its limits become your architecture's limits | Same file, § Ownership split |
| **Two-plane observability** | Telemetry quietly becoming the system of record for an audit claim | [`observability-and-evaluation.md`](docs/architecture/inspectable-multi-agent-diligence/observability-and-evaluation.md) § The two planes |
| **Typed-artifact rendering** | Model output becoming markup, and an injection becoming code execution in a browser | [`experience-and-presentation.md`](docs/architecture/inspectable-multi-agent-diligence/experience-and-presentation.md) § The presentation contract |
| **Content-addressed evidence snapshot** | Later evidence silently entering a historical as-of analysis | [`runtime-architecture.md`](docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md) § Context, evidence, and reproducibility |

Each is meant to be liftable into a system that has nothing to do with company
diligence. Where a pattern is specific to this domain, that is called out where
it is specified.

## Things you can do here today

Each of these can be completed end to end from this repository alone.

**Decide whether detection-based injection defence is right for your system.**
Start at [`prompt-injection-defence-survey.md`](docs/product/research/prompt-injection-defence-survey.md),
then read § Four grounded facts and § Alternatives Considered → *Detection-based
injection defence* in the architecture. You will find cited attack-success
figures, the reason the structural alternative was chosen instead, and — in
§ Known at ship — the residual that choice does **not** close. That last part is
the one most write-ups omit.

**Trace a ratified constraint from decision to consequence.** Pick any row in
[`docs/product/intents/README.md`](docs/product/intents/README.md) § 1, follow it
to the intent that owns its normative wording, then to where the architecture
satisfies it. The constraint appears in exactly one place; everything else cites
it. That discipline is deliberate, and the repository's history shows what it
costs when it lapses.

**See how a claim's confidence is graded and bounded.** The security posture
rests on `[moderate]`, self-evaluated evidence, and the architecture says so in
its own § Known at ship rather than in a footnote.

## How this repository is organised

```
docs/
  CHARTER.md          mission, scope, principles — changes go through an RFC
  CONVENTIONS.md      how work is done here
  rfc/                proposals that change the charter or governance
  product/
    intents/          what the system must achieve, and who ratified what
    briefs/           delivery coordination
    research/         evidence, with per-finding confidence ratings
  architecture/
    inspectable-multi-agent-diligence/   the design and its two companions
```

Start with [`docs/architecture/inspectable-multi-agent-diligence/README.md`](docs/architecture/inspectable-multi-agent-diligence/README.md),
which gives a reading order.

The `.claude/`, `.agents/` and `.codex/` directories are installed agent tooling
from [agent-ready-repo](https://github.com/eugenelim/agent-ready-repo). They are
vendored, not part of what this project demonstrates. They are the large majority
of the file count and none of the interesting content.

## How decisions are made here

Intents record *what must be true* before a solution is chosen, and are accepted
only after independent review. The charter records *why*, and changing its
mission, scope, or principles takes an RFC. Architecture proposes *how*, and does
not get to reverse a ratified constraint.

Two conventions do most of the work:

- **A ratified constraint has exactly one normative home.** Everything else
  cites it. A hand-copy drifts, and a drifted copy of an owner's commitment is
  indistinguishable from an author's preference.
- **Every outcome carries a falsifying observation.** If nothing could show the
  outcome was not met, it is not an outcome — it is a wish.

## Licence

**Not yet chosen.** The charter ratifies that this is an open-source reference
implementation, but no licence file exists yet, which means default copyright
applies and you do not currently have permission to reuse this material. That is
a gap, not an intention — it is tracked as an open question in
[`adoptable-reference-implementation`](docs/product/intents/adoptable-reference-implementation.md).
Until a licence lands, treat this repository as readable but not reusable.
