#!/usr/bin/env python3
"""Phase 0 spike 2 — ADK as a step-level library under application-owned control.

The design's § Ownership split claims the application owns orchestration and ADK
is used as a step-level reasoning library behind the `BaseLlm` seam. That claim
only holds if three things are true, and each is tested here:

  1. The application decides when a step runs. ADK does not own the outer loop.
  2. A tool call can be **intercepted and denied before it executes**. This is
     the seam the policy decision point occupies; without it, argument-value
     authorization has nowhere to stand and `policy.decision` cannot commit
     before the action.
  3. Step N+1's context is assembled by the application, not carried implicitly
     by an ADK session. The design states the context service is an application
     capability, not ADK's `SessionService`.

Identity is not retested here — spike 1 covers it. This runs under the ambient
developer session.

Usage: ./.venv/bin/python adk_orchestration_spike.py
"""
import asyncio
import sys

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

PROFILE = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
results = []
audit = []          # stands in for the event log


def record(ok, name, detail):
    results.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")


def fetch_filing_section(ticker: str, section: str) -> dict:
    """Fetch a named section of an SEC filing for a ticker."""
    audit.append(("tool.executed", ticker, section))
    return {"text": f"[{section} for {ticker}] Supply-chain concentration increased."}


# --- The policy decision point ------------------------------------------------
# Denies on ARGUMENT VALUE, not on tool name: the same tool is allowed for one
# ticker and refused for another. That is the distinction the design turns on.
ALLOWED_TICKERS = {"ACME"}


def before_tool(tool, args, tool_context):
    decision = "allow" if args.get("ticker") in ALLOWED_TICKERS else "deny"
    audit.append(("policy.decision", tool.name, args.get("ticker"), decision))
    if decision == "deny":
        # Returning a dict short-circuits the tool: it never executes.
        return {"error": f"policy denied: ticker {args.get('ticker')!r} out of scope"}
    return None


def build_agent():
    return LlmAgent(
        name="filing_reader",
        model=LiteLlm(model=f"bedrock/{PROFILE}"),
        instruction=("You read SEC filing sections. Use the fetch_filing_section tool "
                     "when asked about a filing. Be terse."),
        tools=[fetch_filing_section],
        before_tool_callback=before_tool,
    )


async def run_one_step(runner, session_id, text):
    """One application-controlled step. The app decides there is a next one."""
    out = []
    async for event in runner.run_async(
            user_id="spike", session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        if event.content and event.content.parts:
            for p in event.content.parts:
                if p.text:
                    out.append(p.text)
    return "".join(out).strip()


async def main():
    print("Phase 0 spike 2 — ADK under application-owned orchestration\n")
    runner = InMemoryRunner(agent=build_agent(), app_name="phase0")

    s1 = await runner.session_service.create_session(app_name="phase0", user_id="spike")
    reply1 = await run_one_step(runner, s1.id, "Read the risk factors for ACME.")
    executed = [a for a in audit if a[0] == "tool.executed"]
    decisions = [a for a in audit if a[0] == "policy.decision"]
    record(bool(executed) and bool(decisions),
           "1. application drives a single step; tool ran under it",
           f"{len(decisions)} decision(s), {len(executed)} execution(s); "
           f"reply {reply1[:54]!r}")

    # 2. The same tool, a different argument value, must be refused.
    audit.clear()
    s2 = await runner.session_service.create_session(app_name="phase0", user_id="spike")
    reply2 = await run_one_step(runner, s2.id, "Read the risk factors for ENRON.")
    denied = [a for a in audit if a[0] == "policy.decision" and a[-1] == "deny"]
    executed2 = [a for a in audit if a[0] == "tool.executed"]
    record(bool(denied) and not executed2,
           "2. tool denied on argument value, before it executed",
           f"{len(denied)} deny decision(s), {len(executed2)} execution(s) — "
           f"the deny is what the PDP needs; reply {reply2[:44]!r}")

    # 3. A fresh session with application-supplied context: continuity comes from
    #    what the application passes in, not from ADK carrying it implicitly.
    audit.clear()
    s3 = await runner.session_service.create_session(app_name="phase0", user_id="spike")
    carried = "Earlier step established: ACME risk factors mention supply-chain concentration."
    reply3 = await run_one_step(
        runner, s3.id,
        f"{carried}\nAnswer from that text alone. Do NOT call any tool. "
        f"Name the single risk in four words or fewer.")
    # Answering from supplied context means answering WITHOUT the tool. If the
    # model fetched instead, continuity was not demonstrated and a keyword match
    # would be incidental.
    tool_ran = [a for a in audit if a[0] == "tool.executed"]
    mentions = any(w in reply3.lower() for w in ("supply", "chain", "concentration"))
    record(mentions and not tool_ran,
           "3. step context supplied by the application, not ADK session state",
           f"tool calls: {len(tool_ran)} (must be 0); reply {reply3[:60]!r}")

    # 4. A session with no prior turn must NOT know it — proving continuity was
    #    ours in check 3 rather than ADK quietly carrying state across sessions.
    s4 = await runner.session_service.create_session(app_name="phase0", user_id="spike")
    reply4 = await run_one_step(runner, s4.id,
                                "What did the earlier step establish? If nothing, say NOTHING.")
    isolated = "nothing" in reply4.lower()
    record(isolated, "4. sessions are isolated, so check 3 proves app-supplied context",
           f"reply {reply4[:60]!r}")

    failed = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


sys.exit(asyncio.run(main()))
