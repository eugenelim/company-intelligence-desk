#!/usr/bin/env python3
"""Phase 0 spike 7 — Pydantic AI over Bedrock via ambient workload identity.

Re-spikes hypothesis 1 against the replacement agent framework, and adds the
three Shape-A claims that spike 1 never had to make because ADK could not make
them.

Hypotheses:

  H1  Pydantic AI's BedrockConverseModel resolves credentials from the ambient
      chain with no static key, preserving streaming and the tool-call loop,
      under a least-privilege role.
      Falsified if an explicit credential is required, or either breaks.

  H2  A PDP implemented as a WrapperToolset.call_tool override refuses a
      well-typed call on an ARGUMENT VALUE before the tool body executes.
      Falsified if the tool body runs, or if the refusal cannot be observed
      inside the agent run.

  H3  A run's message history round-trips through ModelMessagesTypeAdapter to
      JSON and back, and a FRESH Agent resumes from the deserialized history.
      This is the claim that replaces ADK's SessionService as the inspection
      and replay substrate. Falsified if the round-trip is lossy or a resumed
      run cannot see prior turns.

  H4  A tool marked requires_approval=True suspends the run with
      DeferredToolRequests, and the decision can be returned through
      deferred_tool_results on a SEPARATE run object built from the serialized
      history — i.e. the approval gate survives a process boundary.
      Falsified if resumption requires the original in-memory run.

Running this as an administrator would prove nothing about H1: an admin can
invoke any model. So the spike creates a least-privilege role, assumes it, and
runs everything under those credentials — same construction as spike 1.

No identifier from this account is ever written to disk. Account id and role ARN
are resolved at runtime and held in memory only.

Usage: ./.venv/bin/python pydantic_ai_bedrock_spike.py [--keep]
"""
import asyncio
import json
import os
import sys
import time
from typing import Any

import boto3

REGION = "us-east-1"
PROFILE = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
MODEL_SUFFIX = "anthropic.claude-haiku-4-5-20251001-v1:0"
OUT_OF_POLICY = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
ROLE_NAME = "ced-spike-phase0-worker-pai"

iam = boto3.client("iam")
sts = boto3.client("sts")
results: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, detail: str) -> None:
    results.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")


caller = sts.get_caller_identity()
account, caller_arn = caller["Account"], caller["Arn"]

# Least privilege: only the two Bedrock invoke actions, only this profile and
# the foundation model behind it. No wildcard on action.
#
# The two tightenings that look correct and are not — an `aws:RequestedRegion`
# equality condition, and a region-pinned foundation-model ARN — were
# established by spike 1 and are not re-litigated here. A `us.`-prefixed
# profile is a CROSS-REGION inference profile, so the model ARN stays
# region-wildcarded. This spike inherits that shape to confirm it still holds
# through a different SDK path.
policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        "Resource": [
            f"arn:aws:bedrock:{REGION}:{account}:inference-profile/{PROFILE}",
            f"arn:aws:bedrock:*::foundation-model/{MODEL_SUFFIX}",
        ],
    }],
}
trust = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": f"arn:aws:iam::{account}:root"},
        "Action": "sts:AssumeRole",
        "Condition": {"ArnLike": {"aws:PrincipalArn": caller_arn.replace(
            ":sts:", ":iam:").replace("assumed-role/", "role/").rsplit("/", 1)[0] + "*"}},
    }],
}

print("Phase 0 spike 7 — Pydantic AI over Bedrock via ambient workload identity\n")

for cleanup in (lambda: iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName="bedrock-invoke"),
                lambda: iam.delete_role(RoleName=ROLE_NAME)):
    try:
        cleanup()
    except Exception:
        pass

iam.create_role(
    RoleName=ROLE_NAME,
    AssumeRolePolicyDocument=json.dumps(trust),
    Description="Phase 0 spike 7: least-privilege Bedrock invoke. Delete freely.",
    MaxSessionDuration=3600,
    Tags=[{"Key": "project", "Value": "company-intelligence-desk"},
          {"Key": "lifecycle", "Value": "spike-disposable"}])
iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="bedrock-invoke",
                    PolicyDocument=json.dumps(policy))
record(True, "scoped role created",
       f"{ROLE_NAME}: 2 invoke actions, 2 resource ARNs, no wildcard action")

role_arn = f"arn:aws:iam::{account}:role/{ROLE_NAME}"
creds, assumed, last = None, False, ""
for _ in range(10):                            # IAM is eventually consistent
    try:
        creds = sts.assume_role(RoleArn=role_arn,
                                RoleSessionName="phase0-spike7")["Credentials"]
        assumed = True
        break
    except Exception as e:
        last = str(e)[:90]
        time.sleep(3)
record(assumed, "role assumed",
       "temporary credentials obtained" if assumed else f"could not assume — {last}")
if not assumed:
    sys.exit(1)

# Hand the scoped session to the ambient chain exactly as an ECS task role
# would: environment credentials, no static long-lived key anywhere. Nothing
# below ever passes a credential to Pydantic AI.
os.environ.update({
    "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
    "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
    "AWS_SESSION_TOKEN": creds["SessionToken"],
    "AWS_REGION": REGION,
    "AWS_DEFAULT_REGION": REGION,
})
os.environ.pop("AWS_PROFILE", None)

# Imported only after the ambient environment is in place, so there is no
# chance of a client being constructed against the admin caller.
from pydantic_ai import Agent, RunContext                        # noqa: E402
from pydantic_ai.exceptions import ApprovalRequired, ModelHTTPError  # noqa: E402
from pydantic_ai.messages import ModelMessagesTypeAdapter        # noqa: E402
from pydantic_ai.models.bedrock import BedrockConverseModel      # noqa: E402
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults  # noqa: E402
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset  # noqa: E402

# No provider= argument, no credentials, no boto3 client: the model is expected
# to build its own client off the ambient chain. That is the whole of H1.
model = BedrockConverseModel(PROFILE)
usage = {"in": 0, "out": 0}


def tally(result: Any) -> None:
    u = result.usage
    usage["in"] += u.input_tokens or 0
    usage["out"] += u.output_tokens or 0


# ---------------------------------------------------------------- H1
async def h1_nonstreaming() -> None:
    try:
        agent = Agent(model)
        r = await agent.run("Reply with exactly: OK",
                            model_settings={"temperature": 0, "max_tokens": 16})
        tally(r)
        record(True, "H1a ambient credentials resolved (no key passed)",
               f"reply {r.output.strip()!r}, "
               f"{r.usage.input_tokens} in / {r.usage.output_tokens} out")
    except Exception as e:
        record(False, "H1a ambient credentials resolved",
               f"{type(e).__name__}: {str(e)[:140]}")


async def h1_streaming() -> None:
    try:
        agent = Agent(model)
        chunks, first_at, t0, text = 0, None, time.time(), ""
        async with agent.run_stream(
                "Count from 1 to 8, space separated.",
                model_settings={"temperature": 0, "max_tokens": 48}) as stream:
            async for delta in stream.stream_text(delta=True, debounce_by=None):
                if delta:
                    chunks += 1
                    text += delta
                    first_at = first_at or time.time() - t0
        record(chunks > 1, "H1b streaming preserved",
               f"{chunks} deltas, first at {first_at:.2f}s, text {text.strip()[:32]!r}"
               if chunks else "no deltas received")
    except Exception as e:
        record(False, "H1b streaming preserved", f"{type(e).__name__}: {str(e)[:140]}")


async def h1_tool_loop() -> None:
    try:
        agent = Agent(model)
        seen: list[dict[str, Any]] = []

        @agent.tool_plain
        def get_filing_section(ticker: str, section: str) -> str:
            """Fetch a named section of an SEC filing."""
            seen.append({"ticker": ticker, "section": section})
            return "Risk factors: supply chain concentration increased."

        r = await agent.run(
            "Get the risk factors section for ticker ACME. Use the tool, then summarise in one line.",
            model_settings={"temperature": 0, "max_tokens": 256})
        tally(r)
        record(bool(seen), "H1c tool-call loop preserved",
               f"called get_filing_section({seen[0]}), final {r.output.strip()[:56]!r}"
               if seen else "model returned no tool call")
    except Exception as e:
        record(False, "H1c tool-call loop preserved", f"{type(e).__name__}: {str(e)[:140]}")


async def h1_scope_bites() -> None:
    try:
        await Agent(BedrockConverseModel(OUT_OF_POLICY)).run(
            "hi", model_settings={"max_tokens": 8})
        record(False, "H1d scope denies an out-of-policy model",
               "ALLOWED — the policy is not binding")
    except Exception as e:
        blob = str(e)
        denied = "AccessDenied" in blob or "not authorized" in blob
        record(denied, "H1d scope denies an out-of-policy model",
               "AccessDeniedException as expected" if denied
               else f"{type(e).__name__}: {blob[:120]}")


# ---------------------------------------------------------------- H2
class Denied(Exception):
    """Raised by the PDP. Not a ModelRetry: a denial is terminal, not advice."""


class PolicyDecisionPoint(WrapperToolset):
    """Argument-VALUE authorization, outside any model's context window.

    The ceiling is a conjunction of independent per-argument predicates, per
    runtime-architecture.md § Decidability. Checking the tool NAME and argument
    TYPES is the documented anti-pattern this exists to avoid.
    """

    def __init__(self, wrapped: Any, ceiling: dict[str, dict[str, set[str]]]):
        super().__init__(wrapped)
        self.ceiling = ceiling
        self.decisions: list[tuple[str, str, dict[str, Any]]] = []

    async def call_tool(self, name: str, tool_args: dict[str, Any],
                        ctx: RunContext, tool: Any) -> Any:
        allowed = self.ceiling.get(name)
        if allowed is None:
            self.decisions.append(("deny", name, tool_args))
            raise Denied(f"tool {name!r} is not in the acting role's ceiling")
        for arg, permitted in allowed.items():
            if tool_args.get(arg) not in permitted:
                self.decisions.append(("deny", name, tool_args))
                raise Denied(
                    f"argument {arg}={tool_args.get(arg)!r} lies outside the ceiling")
        self.decisions.append(("allow", name, tool_args))
        return await super().call_tool(name, tool_args, ctx, tool)


async def h2_pdp_inside() -> None:
    executed: list[str] = []

    def fetch_filing(ticker: str) -> str:
        """Fetch the latest filing for a ticker."""
        executed.append(ticker)
        return f"filing body for {ticker}"

    base = FunctionToolset([fetch_filing])
    # ACME is inside the ceiling; every other ticker is outside it. Both calls
    # below are WELL-TYPED — only the value differs.
    pdp = PolicyDecisionPoint(base, {"fetch_filing": {"ticker": {"ACME"}}})
    agent = Agent(model, toolsets=[pdp])

    try:
        r = await agent.run("Fetch the filing for ticker ACME. Use the tool.",
                            model_settings={"temperature": 0, "max_tokens": 200})
        tally(r)
        record(executed == ["ACME"] and ("allow", "fetch_filing", {"ticker": "ACME"}) in pdp.decisions,
               "H2a PDP admits an in-ceiling argument value",
               f"decisions={pdp.decisions}, tool body ran for {executed}")
    except Exception as e:
        record(False, "H2a PDP admits an in-ceiling argument value",
               f"{type(e).__name__}: {str(e)[:140]}")

    executed.clear()
    pdp.decisions.clear()
    try:
        r = await agent.run("Fetch the filing for ticker EVILCORP. Use the tool.",
                            model_settings={"temperature": 0, "max_tokens": 200})
        tally(r)
        denied_body_not_run = executed == []
        saw_deny = any(d[0] == "deny" for d in pdp.decisions)
        record(denied_body_not_run and saw_deny,
               "H2b PDP refuses an out-of-ceiling argument value before the tool body runs",
               f"decisions={pdp.decisions}, tool body executions={executed}")
    except Denied as e:
        record(executed == [], "H2b PDP refuses an out-of-ceiling argument value "
                               "before the tool body runs",
               f"Denied propagated out of the run: {e}; tool body executions={executed}")
    except Exception as e:
        record(False, "H2b PDP refuses an out-of-ceiling argument value",
               f"unexpected {type(e).__name__}: {str(e)[:140]}")


# ---------------------------------------------------------------- H3
async def h3_history_roundtrip() -> None:
    try:
        agent = Agent(model)
        r1 = await agent.run("My analysis subject is ticker ZXQ9. Reply with exactly: NOTED",
                             model_settings={"temperature": 0, "max_tokens": 16})
        tally(r1)

        # Serialize exactly as the event log would: JSON bytes, nothing else.
        blob = ModelMessagesTypeAdapter.dump_json(r1.all_messages())
        restored = ModelMessagesTypeAdapter.validate_json(blob)
        reblob = ModelMessagesTypeAdapter.dump_json(restored)
        lossless = blob == reblob
        record(lossless, "H3a message history round-trips through JSON byte-identically",
               f"{len(blob)} bytes, {len(restored)} messages, "
               f"second dump {'identical' if lossless else 'DIFFERS'}")

        # A FRESH Agent object — nothing shared with the run above but the bytes.
        fresh = Agent(model)
        r2 = await fresh.run("What ticker did I name? Reply with the ticker only.",
                             message_history=restored,
                             model_settings={"temperature": 0, "max_tokens": 16})
        tally(r2)
        carried = "ZXQ9" in r2.output.upper()
        record(carried, "H3b a fresh Agent resumes from deserialized history",
               f"answered {r2.output.strip()!r} — prior turn {'visible' if carried else 'LOST'}")
    except Exception as e:
        record(False, "H3 message history round-trip", f"{type(e).__name__}: {str(e)[:140]}")


# ---------------------------------------------------------------- H4
async def h4_approval_across_process() -> None:
    try:
        def publish_report(claim: str) -> str:
            """Publish the finished report."""
            return f"published: {claim}"

        toolset = FunctionToolset()
        toolset.add_function(publish_report, requires_approval=True)

        agent = Agent(model, toolsets=[toolset],
                      output_type=[str, DeferredToolRequests])
        r1 = await agent.run(
            "Publish the report with claim 'revenue grew 4%'. Use the tool.",
            model_settings={"temperature": 0, "max_tokens": 200})
        tally(r1)

        if not isinstance(r1.output, DeferredToolRequests):
            record(False, "H4a run suspends on an approval-gated tool",
                   f"expected DeferredToolRequests, got {type(r1.output).__name__}")
            return
        pending = r1.output.approvals
        record(bool(pending), "H4a run suspends on an approval-gated tool",
               f"{len(pending)} approval request(s): "
               f"{[(p.tool_name, p.args) for p in pending]}")

        # Cross the process boundary: only JSON bytes survive.
        blob = ModelMessagesTypeAdapter.dump_json(r1.all_messages())
        history = ModelMessagesTypeAdapter.validate_json(blob)

        approvals = {p.tool_call_id: True for p in pending}
        resumed = Agent(model, toolsets=[toolset], output_type=[str, DeferredToolRequests])
        r2 = await resumed.run(
            message_history=history,
            deferred_tool_results=DeferredToolResults(approvals=approvals),
            model_settings={"temperature": 0, "max_tokens": 200})
        tally(r2)
        ok = isinstance(r2.output, str) and "published" in str(r2.output).lower()
        record(ok, "H4b approval decision returns through a fresh Agent + serialized history",
               f"resumed output {str(r2.output).strip()[:72]!r}")
    except Exception as e:
        record(False, "H4 approval gate across a process boundary",
               f"{type(e).__name__}: {str(e)[:180]}")


async def main() -> None:
    await h1_nonstreaming()
    await h1_streaming()
    await h1_tool_loop()
    await h1_scope_bites()
    await h2_pdp_inside()
    await h3_history_roundtrip()
    await h4_approval_across_process()


asyncio.run(main())

if "--keep" not in sys.argv:
    iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName="bedrock-invoke")
    iam.delete_role(RoleName=ROLE_NAME)
    record(True, "torn down", f"{ROLE_NAME} deleted")

# Haiku 4.5 list price at time of run: $1/M input, $5/M output.
cost = usage["in"] / 1e6 * 1.0 + usage["out"] / 1e6 * 5.0
print(f"\n  tokens: {usage['in']} in / {usage['out']} out   approx cost: ${cost:.5f}")
failed = [r for r in results if not r[0]]
print(f"{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
