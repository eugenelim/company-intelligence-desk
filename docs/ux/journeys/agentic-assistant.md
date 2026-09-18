---
type: customer-journey
slug: agentic-assistant
persona: diligence analyst
outcome: a defensible judgement about one company as of an explicit date, reached by conversing with the system rather than operating it
surface: responsive-web
evidence-level: assumption-based
---

# Journey: the diligence analyst and the assistant

**Persona:** A diligence analyst. Competent with financial filings, not with
the system. Judged on whether their conclusion survives someone else
challenging it, which makes *defensibility* their real currency — not speed.
Single operator today; see
[`portable-identity-first-runtime`](../../product/intents/portable-identity-first-runtime.md)
§ Principal scope for what changes when there are two.

**Outcome:** A judgement they are willing to defend, with every claim in it
traceable to an evidence item or a recorded calculation.

**Surface:** Responsive web. Progressive disclosure matters more than usual
here — the inspection surface is large and an analyst mid-thought should not
be paying for it.

**Genre:** Analytical (arrive with a question, leave with a decision and an
action), with **workspace-genre** concerns layered on because a diligence run
takes tens of minutes and outlives the session that started it.

**Trigger:** The analyst has a company and a date and a question they cannot
answer from memory.

**End state:** A judgement recorded, its claims resolvable, and any action they
took (a refresh, a new ticker, a published report) confirmed as having landed.

> **Evidence level: assumption-based.** No user interviews, usability sessions
> or analytics exist for this product. Every emotion and pain below is a team
> hypothesis derived from the system's known properties and from the Phase 0
> spike results — not from observation. The pains in Stage 3 are the ones most
> worth testing first, because they are the ones the architecture *predicts*
> rather than the ones a designer imagines.

---

## Stage 1: Arriving

| Row | Content |
|-----|---------|
| **Actions** | Opens the workbench. Looks for what was left running. Re-establishes which company and which as-of date they were working in. Reopens yesterday's conversation. |
| **Emotions** | Neutral drifting to mild anxiety — *"where was I, and did that finish?"* |
| **Pains** | A run outlives the session that started it, so arriving often means arriving *mid-thing*. The conversation and the run are separate objects with separate lifetimes, and it is not obvious which one is "where I was". The as-of date is the thing that makes an analysis meaningful and the easiest thing to lose track of between sessions. |
| **Opportunities** | The system already has a snapshot join point; treat re-entry as the *default* view rather than a recovery path. Make the as-of date ambient — a persistent frame, not a field someone must remember they set. |

## Stage 2: Framing the question

| Row | Content |
|-----|---------|
| **Actions** | Types a question. Chooses, implicitly, between the assistant inside the module they are in and the overall assistant. Names a company; may or may not name a date. |
| **Emotions** | Hopeful, and uncertain about the size of the box — *"can it actually do that?"* |
| **Pains** | A chat box advertises no capabilities. The analyst cannot tell what this assistant may do, what the *other* assistant may do, or whether the difference matters. They will either under-ask (treating it as search) or over-ask and be refused. Asking without a date produces an analysis whose meaning is undefined, and a prompt field will not stop them. |
| **Opportunities** | Authority is already stored as data rather than written into code, so *"what can you do here"* is answerable from the system's own records instead of a hand-maintained help page — and it stays true as capabilities change. The module/overall distinction should be visible as a difference in reach, not left for the analyst to infer. |

## Stage 3: Interrogating the evidence

| Row | Content |
|-----|---------|
| **Actions** | Asks follow-ups. Asks *where did that come from*. Expands a figure to see the filing behind it. Pushes on something that looks wrong. |
| **Emotions** | Engaged, then **suspicious** — the sharpest negative turn in the journey. |
| **Pains** | An answer without visible provenance is worth nothing to someone who will be challenged on it, and asking for the source every time is a tax on thinking. **Worse: there are questions the system deliberately cannot answer, and a refusal is indistinguishable from incompetence.** Phase 0 measured this — causal attribution ("margin expanded *because of* tariff refunds") and untagged narrative (risk factors, legal proceedings, much of MD&A) do not cross the safety boundary. The analyst asks the single most natural diligence question — *why* — and gets less than they expect, with no way to tell whether the system is being careful or being stupid. |
| **Opportunities** | Provenance inline and always, not on request. And **make the boundary legible**: *"I can't carry that across — it's narrative the filing doesn't tag, here is the passage, you judge it"* is a good answer. Silence is not. A deliberate safety property that reads as a defect is a design failure, not a user error. |

## Stage 4: Modelling the scenario

| Row | Content |
|-----|---------|
| **Actions** | *"What if margins compress 200 basis points?"* Varies an assumption. Compares against the base case. |
| **Emotions** | Exploratory, low-stakes, the most enjoyable part of the work. |
| **Pains** | In a chat transcript a hypothetical and a finding look identical. Three turns later the analyst cannot tell which numbers came from a filing and which they invented, and neither can anyone reading over their shoulder. If a scenario figure reaches the report, its assumptions are the inputs that make it traceable — and a number lifted out of a conversation arrives without them. |
| **Opportunities** | A scenario is an object with its assumption set attached, not a sentence in a transcript. Hypotheticals should be visually unmistakable from evidence-backed claims — and should stay unmistakable when copied. |

## Stage 5: Deciding

| Row | Content |
|-----|---------|
| **Actions** | Reviews the claims they are about to stand behind. Checks each one resolves to something. Forms the judgement. |
| **Emotions** | Cautious confidence when provenance holds — **the high point of the journey** — or unease when it does not. |
| **Pains** | The readiness checks run automatically and are invisible until something fails, so the analyst learns their work is not publishable at the moment they expected to be finished. Late failure is the expensive kind. |
| **Opportunities** | Show the release gate continuously while the work is forming, so "publishable" is a state the analyst can watch approach rather than a verdict delivered at the end. |

## Stage 6: Acting and confirming

| Row | Content |
|-----|---------|
| **Actions** | Refreshes a ticker, or adds one. Launches a fuller run. Publishes. Then checks the thing actually happened. |
| **Emotions** | Hesitancy before anything that feels irreversible; relief on confirmation; irritation at being asked to confirm things that plainly do not matter. |
| **Pains** | A chat box flattens everything into one affordance: a free question and a corpus-wide ingest look the same going in. The analyst cannot see, before committing, which actions spend money, which change shared state, and which are undoable. Confirm everything and they stop reading the prompts; confirm nothing and they discover the cost afterwards. |
| **Opportunities** | Graduate the friction to the blast radius: reversible and cheap simply happens and is recorded; spend or shared-state mutation confirms. Show the consequence **before** the confirmation, not inside it. And close the loop — an action whose effect the analyst has to go and verify separately is not finished. |

---

## Frontstage actions

- **Action:** resume-prior-context
- **Action:** set-analysis-frame
- **Action:** ask-module-assistant
- **Action:** ask-overall-assistant
- **Action:** request-provenance
- **Action:** inspect-evidence-item
- **Action:** challenge-an-answer
- **Action:** vary-assumption
- **Action:** compare-to-base-case
- **Action:** review-claim-set
- **Action:** refresh-ticker
- **Action:** add-ticker
- **Action:** launch-run
- **Action:** confirm-consequential-action
- **Action:** publish-judgement
- **Action:** verify-action-landed

---

## Emotional arc

Neutral at **Arriving**, lifting at **Framing** on optimism, then falling hard
through **Interrogating**, recovering during **Modelling** because the stakes
are low, rising to the journey's high point at **Deciding** when provenance
holds, and ending unevenly at **Acting** depending on whether the analyst
could see what an action would cost before taking it.

**Lowest point: Stage 3 — suspicion — because a deliberate safety boundary and
a failure of competence are indistinguishable from the outside.** This is the
one the architecture actively predicts rather than one a designer imagined:
the quarantine boundary is *supposed* to stop causal attribution and untagged
narrative from crossing, and Phase 0 confirmed it does. The design question is
not how to remove the boundary — it is how to make a refusal read as care.

**Second dip: Stage 6 — irreversibility ambiguity** — the analyst cannot tell
a cheap question from an expensive commitment until after.

**Highest-opportunity pain, in the analyst's words:** *"It told me something
and I have no idea whether it's from the filing, from a calculation, or from
its imagination — and when it won't answer, I can't tell if that's the system
being careful or being useless."*

**Peak positive: Stage 5**, the moment a claim set resolves cleanly and the
analyst knows they can defend it. That is the experience the product is
actually selling, and everything upstream should be read as either protecting
or eroding it.

---

## Handoff notes

**For `user-flow`:** sequence around Stage 3 first — provenance display,
boundary-refusal wording, and evidence expansion carry the highest-opportunity
pains. Stage 6's graduated-confirmation affordance is second. Stage 1's
re-entry view is third and is largely a matter of making an existing capability
the default rather than building something new.

**For `service-blueprint`:** the backstage this journey leans on is designed in
[`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md).
Named textually here, to be mapped there:

- **Interactive execution plane** — chat turns cannot wait on a 30-second poll;
  this journey needs a latency path the diligence-run path does not.
- **Conversation lifetime** — Stages 1 and 4 both depend on a conversation that
  persists across sessions and stays distinguishable from a run.
- **Policy decision point** — Stage 2's "what can you do" and Stage 6's
  graduated confirmation both read from the same stored authority.
- **Trust-class enforcement** — the direct cause of Stage 3's dip.
- **Approval / input suspension** — the mechanism behind Stage 6's confirmations
  and any mid-run clarification.
- **Event log and its stream** — Stage 1's re-entry, Stage 5's readiness display,
  and Stage 6's did-it-land confirmation are all projections over it.
- **Integration registry** — bounds what "run these reports" and "add a ticker"
  can mean, and whether scenario modelling exists at all.

**Open, and owned by nobody yet:** whether the assistant's capability catalogue
is a product concern, a runtime concern, or its own. It is the subject of the
intent this journey feeds.
