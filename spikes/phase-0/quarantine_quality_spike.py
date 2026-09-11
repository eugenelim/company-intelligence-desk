#!/usr/bin/env python3
"""Phase 0 spike 4 — does references-only quarantine preserve analytical quality?

Hypothesis, from runtime-architecture.md § Open Questions:

    Does references-only quarantine preserve analytical quality on a real
    filing? *Falsified if* closed-vocabulary classification loses distinctions
    the diligence output depends on.

Design under test (§ Injection defence): a quarantined agent reads untrusted
filing prose and holds no tools. Only **validated references, closed-vocabulary
classifications and typed scalars** cross to a planning agent, through a
deterministic fail-closed parser. The planning agent never sees the prose.

The experiment runs the same analytical question twice over the same real
filing:

    A  baseline   — analyst reads the full prose
    B  quarantined — analyst reads ONLY what survived the boundary

and compares what each produced. This is n=1 on one filing section; it is
evidence, not proof.

Usage: ./.venv/bin/python quarantine_quality_spike.py
"""
import glob
import json
import pathlib
import re
import sys

import litellm

QA_MODEL = "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"
ANALYST = "bedrock/us.anthropic.claude-sonnet-4-6"

# The closed vocabulary. Anything outside it is dropped by the parser.
LABELS = {
    "revenue_increase", "revenue_decrease", "margin_expansion", "margin_compression",
    "segment_outperformance", "segment_underperformance", "cost_increase",
    "cost_decrease", "tax_rate_change", "share_repurchase", "dividend_change",
    "litigation_exposure", "regulatory_exposure", "supply_concentration",
    "customer_concentration", "guidance_raised", "guidance_lowered",
    "foreign_exchange_headwind", "foreign_exchange_tailwind", "no_material_change",
}
usage = {"in": 0, "out": 0}


def ask(model, prompt, max_tokens=4000):
    r = litellm.completion(model=model, max_tokens=max_tokens, temperature=0,
                           messages=[{"role": "user", "content": prompt}])
    usage["in"] += r.usage.prompt_tokens
    usage["out"] += r.usage.completion_tokens
    return r.choices[0].message.content


def filing_text():
    html = pathlib.Path(glob.glob("fixtures/*.html")[0]).read_text(errors="ignore")
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&#\d+;|&[a-z]+;", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


text = filing_text()
start = text.find("Products and Services Performance")
excerpt = text[start:start + 30000]
manifest = json.loads(pathlib.Path(glob.glob("fixtures/*.json")[0]).read_text())

print("Phase 0 spike 4 — quarantine and analytical quality\n")
print(f"  filing   : {manifest['form']} {manifest['entity']}, filed {manifest['filing_date']}")
print(f"  excerpt  : {len(excerpt):,} chars of MD&A\n")

# --- The quarantined agent: prose in, admitted forms out ----------------------
qa_raw = ask(QA_MODEL, f"""You are reading an SEC filing excerpt. You hold no tools and cannot act.

Emit ONLY JSON with this shape, and nothing else:
{{"observations": [
   {{"label": "<one of the allowed labels>",
     "anchor": "<a short verbatim quote, <=60 chars, locating the claim>",
     "scalars": [{{"name":"<what>","value":<number>,"unit":"<USD_millions|percent|ratio>","period":"<text>"}}]
   }}]}}

Allowed labels, and NOTHING else: {sorted(LABELS)}

Rules: no prose, no explanation, no labels outside the list. Scalars must be
numbers appearing in the text. Emit at most 8 observations, and at most 2
scalars each — a truncated response is a dropped response.

FILING EXCERPT:
{excerpt}""")

# --- The deterministic fail-closed parser ------------------------------------
m = re.search(r"\{.*\}", qa_raw, re.S)
parsed, dropped = [], []
if not m:
    print("  parser: no JSON object found in the quarantined agent's output")
if m:
    try:
        for o in json.loads(m.group(0)).get("observations", []):
            if o.get("label") in LABELS and isinstance(o.get("anchor"), str):
                # An anchor must RESOLVE against the source, or it is a forgery.
                # Compare on whitespace-normalised text: the filing is full of
                # runs of spaces, and a strict match rejects true observations.
                norm = lambda x: re.sub(r"\s+", " ", x).strip()
                if norm(o["anchor"])[:40] and norm(o["anchor"])[:40] in norm(excerpt):
                    parsed.append(o)
                else:
                    dropped.append((o.get("label"),
                                    f"anchor not present in source: {o['anchor'][:60]!r}"))
            else:
                dropped.append((o.get("label"), "label outside closed vocabulary"))
    except json.JSONDecodeError as e:
        print(f"  parser: JSON invalid — {e}")
        print(f"  parser: response was {len(qa_raw)} chars; tail: {qa_raw[-90:]!r}")

print(f"  boundary : {len(parsed)} observation(s) admitted, {len(dropped)} dropped")
for lab, why in dropped[:4]:
    print(f"             dropped {lab!r}:\n               {why}")
if not parsed:
    sys.exit("no observations survived the boundary — falsified on its face")

crossed = json.dumps({"observations": parsed}, indent=1)
print(f"  payload  : {len(crossed):,} chars crossed the boundary "
      f"({len(crossed)/len(excerpt)*100:.1f}% of the prose)\n")

QUESTION = ("Identify the three most material changes for a diligence reader. "
            "For each: one sentence, and cite the figure you relied on. Be terse.")

a = ask(ANALYST, f"{QUESTION}\n\nSOURCE (filing excerpt):\n{excerpt}")
b = ask(ANALYST, f"{QUESTION}\n\nSOURCE (structured observations only — you have "
                 f"no access to the filing prose):\n{crossed}")

print("── A. baseline (full prose) " + "─" * 42)
print(a.strip()[:1100])
print("\n── B. quarantined (admitted forms only) " + "─" * 30)
print(b.strip()[:1100])

nums = lambda s: set(re.findall(r"\d+(?:\.\d+)?", s))
shared = nums(a) & nums(b)
print("\n── comparison " + "─" * 56)
print(f"  figures cited by A : {len(nums(a))}")
print(f"  figures cited by B : {len(nums(b))}")
print(f"  figures in common  : {len(shared)}")
cost = usage["in"]/1e6*1.0 + usage["out"]/1e6*5.0
print(f"\n  tokens {usage['in']} in / {usage['out']} out   approx cost ${cost:.3f}")
print("\n  Verdict is a judgement, not an assertion: read A and B above and decide")
print("  whether B lost a distinction a diligence reader depends on.")
