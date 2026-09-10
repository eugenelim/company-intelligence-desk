# Prompt-injection defence for a governed multi-agent research system

> Discipline: applied (practitioner-pattern survey)

**Question.** For a multi-agent research workbench where (a) a user-supplied
prompt drives autonomous agents and (b) those agents ingest retrieved SEC
filings, what defence actually works — measured, not claimed? Is detection-based
defence tractable at all, and what would rolling our own involve?

**Date.** 2026-09-09. This field moves fast; findings older than ~18 months are
flagged under the `stale prior art` factor.

**Retrievers used.** WebSearch, WebFetch, arXiv retriever. Perplexity retriever
present but `PERPLEXITY_API_KEY` unset — one fewer independent path, compensated
by weighting primary literature and applying the practitioner-independence rule
(same vendor counts once).

**Scope correction made during research.** This survey initially scoped only
*indirect* injection (adversarial text inside retrieved documents). That was
wrong for this system: the user's prompt is itself the instruction driving the
agents, so *direct* injection is equally in scope. The two are treated
separately throughout, because they do not share a defence.

---

## The load-bearing distinction

For **retrieved content**, the classical mitigation is available: never place
untrusted text in an instruction position. For **user input**, that mitigation is
structurally unavailable — the user's text legitimately *is* the instruction.
Sources routinely blur these; where one does, it is flagged. `[synthesis]`

---

## Findings — tractability of detection

**F1. Detection-based defences collapse under adaptive attack.** `[high]`

Eight defences (delimiters, perplexity flagging, LLM-as-detector, rephrasing,
fine-tuning) were evaluated on AgentDojo; adaptive attacks bypassed **all eight**
at ASR consistently above 50% ([arXiv:2503.00061](https://arxiv.org/abs/2503.00061),
NAACL Findings 2025, primary). A separate group found in-band detection
"collapsed from near-zero to **>90% success** under adaptive attacks"
([arXiv:2606.26479](https://arxiv.org/html/2606.26479v1), primary). Six
production guardrail systems including Azure Prompt Shield and Meta Prompt Guard
were evaded at **up to 100%** using character injection and adversarial-ML
transfer ([arXiv:2504.11168](https://arxiv.org/abs/2504.11168), primary).
Confirmed again by an independent black-box framework
([arXiv:2606.15057](https://arxiv.org/pdf/2606.15057), primary).

Four distinct author groups, converging. Triangulation satisfied.

**F2. LLM-as-detector is structurally circular.** `[moderate]`

A detector that is itself an LLM inherits the susceptibility of the system it
protects ([arXiv:2507.05630](https://arxiv.org/pdf/2507.05630), primary).
Conceptual rather than benchmark-driven, hence `[moderate]` — downgrade factor:
*single primary source, argument not measurement*.

**F3. Static benchmark performance does not transfer.** `[high]`

Microsoft Spotlighting reported ~0% ASR under static attack; adaptive attacks
restore **>95%** ([arXiv:2403.14720](https://arxiv.org/html/2403.14720v1),
primary, static-only self-evaluation; adaptive result from
[arXiv:2606.26479](https://arxiv.org/html/2606.26479v1)). StruQ achieves near-
complete defence against simple injection but **56% ASR** under GCG-optimised
attack ([arXiv:2402.06363](https://arxiv.org/abs/2402.06363), USENIX Security
2025). Leave-One-Dataset-Out evaluation reduces classifier AUC by **8–16.5
points**, with **28–44% of top learned features being dataset-specific
shortcuts** (arXiv:2602.14161, primary, independent).

**F4. No formal impossibility proof exists.** `[high]`

The case against detection is empirical and conceptual, not a lower bound.
Verified absence across the retrieved literature. This matters: "detection is
impossible" would be an overclaim. "Detection has lost every adaptive evaluation
published to date" is what the evidence supports. `[synthesis]`

---

## Findings — structural defences

**F5. Structural/authorization defences hold where detection fails.** `[moderate]`

| Method | Result | Attack type |
|---|---|---|
| Progent | 25.8% → 4.2% static-defended → **2.6% adaptive** | Adaptive |
| ScopeGate | **0/48** static bypass; **0/29** unauthorised under 40-iteration adaptive; 0/10 false denies | Adaptive |
| CaMeL | 77% task success vs 84% undefended; "practically solves" AgentDojo security | Largely static |
| MCP proxy enforcement | Prompt-level restrictions bypassable; proxy enforcement not | Static |

Sources: [arXiv:2606.26479](https://arxiv.org/html/2606.26479v1),
[arXiv:2606.28679](https://arxiv.org/html/2606.28679),
[arXiv:2503.18813](https://arxiv.org/abs/2503.18813v2),
[arXiv:2605.18414](https://arxiv.org/html/2605.18414) — all primary.

Rated `[moderate]` not `[high]`. Downgrade factor: *each method is evaluated by
its own authors*. Convergence across four independent groups is real, but no
disinterested third party has re-run any of them.

**F6. The property that makes authorization work is policy living outside the
model's context.** `[moderate]`

ScopeGate's five-stage decision point — scope, argument-value authorisation,
ceiling, idempotency, default deny — succeeds because policy is not in the
context window, enforcement is deterministic and fail-closed, and **argument
values** are checked, not merely tool names
([arXiv:2606.28679](https://arxiv.org/html/2606.28679), primary).

**F7. Capability gates are not authorization — a widespread production
anti-pattern.** `[high]`

LangChain, LlamaIndex, and the Stripe Agent Toolkit all validate tool-name
existence and schema *type*, but perform no per-call argument-*value*
authorisation. A model persuaded to emit a well-typed but unauthorised call has
it executed. Measured rate of attempted unauthorised calls: **0.603** for
deployment-tier models, **0.189** for flagship — a 3.2× spread
([arXiv:2606.28679](https://arxiv.org/html/2606.28679), primary). Corroborated
structurally by the Cloud Security Alliance's confused-deputy note (secondary)
and by the MCP-proxy result (F5).

**F8. CaMeL is the strongest published structural result, and its costs are
stated.** `[moderate]`

Privileged LLM plans but never reads untrusted content; Quarantined LLM reads
untrusted content and returns only *symbolic references*; a custom interpreter
mediates tool calls with capability-based access control. Capability cost: **7
percentage points** of task success (77% vs 84%)
([arXiv:2503.18813](https://arxiv.org/abs/2503.18813v2), primary,
self-evaluated). Authors' stated limitations: users must codify and maintain
policies; declassification prompts cause fatigue; tight runtime integration
required. The Q-LLM→P-LLM pathway remains open if the quarantined model can be
induced to forge references — noted by Willison
([simonwillison.net](https://simonwillison.net/2025/Apr/11/camel/), secondary).

---

## Findings — the tool landscape

**F9. Most of the open-source detection ecosystem is archived or
unmaintained.** `[high]`

| Tool | Status |
|---|---|
| Rebuff | **Archived May 2025**; last release Jan 2024 |
| LLM Guard | **Archived July 2026** |
| Guardrails AI `detect_prompt_injection` | Standalone repo **archived** |
| Vigil | Last meaningful commit **Dec 2023**; alpha |
| ProtectAI DeBERTa injection models | **Archived** (weights remain on HF) |
| NeMo Guardrails | Active, Apache-2.0 |
| LlamaFirewall / PromptGuard 2 | Active, Llama Community Licence |

Primary sources: the repositories' own archive status. Independent of one
another. Note the referral chain: Rebuff's maintainers direct users to LLM
Guard, which is *itself* now archived.

**F10. Two of the best-known "guardrail" models do not detect prompt injection
at all.** `[high]`

**ShieldGemma** covers six *content-safety* categories and has **no
prompt-injection detection whatsoever**
([arXiv:2407.21772](https://arxiv.org/abs/2407.21772), primary). **Llama Guard
3** covers 14 MLCommons hazard categories with no injection category, and its own
model card warns it "may be susceptible to adversarial attacks or prompt
injection attacks"
([HuggingFace model card](https://huggingface.co/meta-llama/Llama-Guard-3-8B),
primary). Content safety, jailbreak, and injection are three different problems
routinely marketed as one. `[synthesis]`

**F11. Vendor-reported classifier accuracy does not survive independent
evaluation.** `[high]`

ProtectAI's DeBERTa injection model claims **99.99% accuracy** on its own model
card. Knostic.ai measured **~90%** across 17 datasets, attributing the gap to
dataset-specific overfitting ([knostic.ai](https://www.knostic.ai/blog/revolutionizing-prompt-injection-detection-a-leap-to-99-accuracy),
primary, independent). InjecGuard found ProtectAI v2 scored **56.64% on benign
inputs containing injection-trigger words** — near random guessing, i.e. severe
over-defence ([arXiv:2410.22770](https://arxiv.org/abs/2410.22770), primary,
independent, university-affiliated).

**F12. The Bedrock Guardrails baseline has no disinterested evaluation.**
`[high]` on the absence; `[low]` on any performance figure.

AWS publishes **no precision/recall/F1** for `PROMPT_ATTACK` (verified absence
across AWS documentation). The only two available evaluations were both run by
**competing commercial vendors**: GuardionAI reports F1 **5.42–10.83%**
(precision 96.34%, recall 5.74%); Alice.io reports F1 **0.561**. Both have a
direct conflict of interest. Directionally they agree — high precision, very low
recall, i.e. the filter is conservative and lets most attacks through — but
neither is admissible as an independent measurement. Any specific number here is
`[low]`; downgrade factor: *conflict of interest, no reproducible methodology*.

Separately, AWS's own documentation states that Bedrock Agents **does not pass
tool input and output through guardrails by default**
([AWS blog](https://aws.amazon.com/blogs/machine-learning/securing-amazon-bedrock-agents-a-guide-to-safeguarding-against-indirect-prompt-injections/),
primary, vendor).

**F13. The one genuinely independent academic tool benchmark ranks these tools
low.** `[moderate]`

The Palit Benchmark (University of Edinburgh,
[arXiv:2505.13028](https://arxiv.org/html/2505.13028v2), primary, independent)
measured LLM Guard at **58% accuracy, F1 0.669, 1.6 s latency**, below Lakera
Guard (F1 0.809, 0.305 s) and Azure Prompt Shield. `[moderate]` — downgrade
factor: *single independent benchmark, limited tool coverage*.

**F14. Licence terms disqualify two of the live options for an open-source
reference implementation.** `[high]`

Llama Guard 3 and PromptGuard 2 ship under the **Llama Community Licence**, which
imposes a 700M-MAU commercial condition. ShieldGemma ships under **Gemma Terms of
Use**, not Apache-2.0. NeMo Guardrails (framework) and the archived ProtectAI
weights are Apache-2.0; LLM Guard is MIT. Primary sources: the respective licence
files.

**F15. No tool reviewed publishes any evaluation against indirect injection in
retrieved documents.** `[high]`

Verified absence across all eleven tools surveyed. The nearest work —
LlamaFirewall's AlignmentCheck and the arXiv:2510.05244 sanitiser — is not a
packaged production tool. `[synthesis]`

---

## Findings — direct injection and human oversight

**F16. Multi-turn attacks outperform single-turn, and compositional
authorisation is unsolved.** `[moderate]`

Crescendo-style gradual escalation succeeds where single-shot fails; models
"lacking conversational history are inherently more resistant". Salami-slicing
formalises the composition of individually-authorised micro-actions into an
unauthorised macro-action ([arXiv:2604.11309](https://arxiv.org/pdf/2604.11309),
primary). **No published defence addresses compositional authorisation across
turns.** Downgrade factor: *most multi-turn results target content-policy
evasion, not privilege escalation, and sources rarely separate the two*.

**F17. Human oversight has a capacity limit, and past it more review makes
systems less safe.** `[moderate]`

Reviewer agreement on what is "risky" is only **Fleiss' κ = 0.52** — moderate,
indicating no objective ground truth. Safety follows an **inverted-U curve**
against escalation rate: beyond an optimum, volume degrades judgment.
Adversarial flooding deliberately exploits this. Suggested target: **5–15%
escalation rate**, treated as resource allocation
([arXiv:2606.08919](https://arxiv.org/abs/2606.08919), primary). Downgrade
factor: *small hand-labelled dataset (125 actions), author-run*.

**F18. Instruction-hierarchy training helps but does not resolve.** `[moderate]`

OpenAI reports **up to 63% improved robustness**
([arXiv:2404.13208](https://arxiv.org/abs/2404.13208), primary), with authors
explicitly noting models "are likely still vulnerable to powerful adversarial
attacks". A later paper diagnoses instruction-hierarchy failures specifically in
reasoning models ([arXiv:2606.07808](https://arxiv.org/pdf/2606.07808), primary)
— relevant to any coordinator that plans via chain-of-thought. Downgrade factor:
*the 63% figure is not decomposed by attack objective, so it cannot be read as
privilege-escalation robustness*.

---

## What this means for a build-vs-buy decision `[inference]`

Marked `[inference]` — a defensible deduction from the findings above, not a
claim any single source makes.

**Buying a detector is the weakest option available.** It is the category that
loses under adaptive attack (F1, F3), most of the ecosystem is archived (F9),
two of the best-known models do not address injection at all (F10), vendor
accuracy does not replicate (F11), the baseline being compared against has no
disinterested evaluation and the conflicted ones are poor (F12), and none has
been evaluated against retrieved-document injection (F15).

**Rolling our own *detector* is the same bet with worse odds** — it would face
the adaptive-attack result with fewer resources than the vendors who already lost.

**Rolling our own *structural control* is the defensible path**, and it is what
the evidence supports (F5, F6, F7). It is also mostly a reshape of components
rather than net-new machinery: application-owned orchestration, capability-based
authority, and policy outside the model context are the properties that make
ScopeGate and CaMeL work.

**Detection is not worthless — it is worth what a cheap layer is worth.** Free,
local, model-free checks (protocol validation, structural anomaly detection) cost
nothing and catch unsophisticated attempts. They must not be described as closing
the boundary.

---

## Known unknowns

- **Known-unknown:** Does any structural defence hold under *unlimited-budget*
  adaptive attack? ScopeGate was tested at 40 iterations; CaMeL largely
  statically. *Would be closed by:* an independent red-team evaluation with no
  iteration cap and oracle access.
- **Known-unknown:** How do these defences perform on *long-document financial
  filings* specifically? Every benchmark reviewed uses email, web, workspace, or
  travel scenarios. *Would be closed by:* running AgentDojo-style evaluation with
  a filings corpus.
- **Known-unknown:** What is Bedrock Guardrails' actual efficacy? *Would be
  closed by:* AWS publishing methodology and figures, or a disinterested academic
  evaluation.
- **Known-unknown:** Do CaMeL's costs hold outside AgentDojo? The 7-point
  capability penalty is measured on 97 tasks. *Would be closed by:* a deployment
  study with real policy complexity.
- **Known-unknown:** CPU-only latency for the larger classifier models. Not
  published for Llama Guard 3 8B or ShieldGemma 9B/27B. *Would be closed by:*
  direct measurement.
- **Unknowable:** Whether detection-based defence is *fundamentally* intractable.
  *Why not:* no formal lower bound exists, and absence of a successful defence to
  date cannot establish impossibility. The honest position is empirical, not
  theoretical.
- **Unknowable:** Whether a defence published today survives attacks not yet
  invented. *Why not:* the adversary adapts after publication; every static
  result has a shelf life that cannot be known in advance.

---

## Moderator pass

Two high-signal items surfaced in retrieval but uncited above, added here:

- **Lakera's PINT benchmark is open-source** even though Lakera Guard is
  commercial and cloud-only. It is usable to evaluate self-hosted candidates —
  a practical route to closing the "no independent evaluation" gap for whatever
  is chosen.
- **SecAlign** ([arXiv:2410.05451](https://arxiv.org/html/2410.05451v1)) reports
  **2% ASR against GCG**, materially better than StruQ's 56%. Training-time
  rather than runtime, so not directly adoptable here, but it is the strongest
  published model-side result and worth tracking if a fine-tuned model ever
  enters scope.
