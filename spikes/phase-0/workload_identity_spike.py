#!/usr/bin/env python3
"""Phase 0 spike 1 — LiteLLM over Bedrock via ambient workload identity.

Hypothesis, from runtime-architecture.md § Open Questions:

    Does ADK→LiteLLM→Bedrock resolve credentials from ambient workload identity
    with no static key, preserving streaming and the tool-call loop?
    Falsified if static credentials are required, or streaming or the tool loop
    breaks.

Running this as an administrator would prove nothing: an admin can invoke any
model, so a green result would say nothing about whether a *scoped workload*
can. So the spike creates a least-privilege role, assumes it, and runs
everything under those credentials.

No identifier from this account is ever written to disk. Account id and role ARN
are resolved at runtime and held in memory only.

Usage: ./.venv/bin/python workload_identity_spike.py [--keep]
"""
import json
import os
import sys
import time

import boto3
import litellm

REGION = "us-east-1"
PROFILE = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
MODEL_SUFFIX = "anthropic.claude-haiku-4-5-20251001-v1:0"
ROLE_NAME = "ced-spike-phase0-worker"

iam = boto3.client("iam")
sts = boto3.client("sts")
results = []


def record(ok, name, detail):
    results.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")


caller = sts.get_caller_identity()
account, caller_arn = caller["Account"], caller["Arn"]

# Least privilege: only the two Bedrock invoke actions, only this profile and the
# foundation model behind it. No wildcards on action.
#
# Two tightenings that look correct and are not, established by experiment:
#   * an `aws:RequestedRegion` equality condition DENIES the call, and
#   * a region-pinned foundation-model ARN DENIES the call.
# A `us.`-prefixed profile is a CROSS-REGION inference profile: authorization for
# the underlying model is evaluated in the region Bedrock *routes to*, not the one
# called. So the model ARN must stay region-wildcarded and no region condition may
# be applied. Pinning the inference-profile ARN to the calling region is fine and
# is kept.
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

print("Phase 0 spike 1 — LiteLLM over Bedrock via ambient workload identity\n")

try:
    iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName="bedrock-invoke")
except Exception:
    pass
try:
    iam.delete_role(RoleName=ROLE_NAME)
except Exception:
    pass

iam.create_role(
    RoleName=ROLE_NAME,
    AssumeRolePolicyDocument=json.dumps(trust),
    Description="Phase 0 spike: least-privilege Bedrock invoke. Delete freely.",
    MaxSessionDuration=3600,
    Tags=[{"Key": "project", "Value": "company-intelligence-desk"},
          {"Key": "lifecycle", "Value": "spike-disposable"}])
iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="bedrock-invoke",
                    PolicyDocument=json.dumps(policy))
record(True, "scoped role created",
       f"{ROLE_NAME}: 2 invoke actions, 2 resource ARNs, no wildcard action")

role_arn = f"arn:aws:iam::{account}:role/{ROLE_NAME}"
creds, assumed = None, False
for attempt in range(10):                      # IAM is eventually consistent
    try:
        creds = sts.assume_role(RoleArn=role_arn,
                                RoleSessionName="phase0-spike")["Credentials"]
        assumed = True
        break
    except Exception as e:
        last = str(e)[:90]
        time.sleep(3)
record(assumed, "role assumed",
       "temporary credentials obtained" if assumed else f"could not assume — {last}")
if not assumed:
    sys.exit(1)

# Hand the scoped session to the ambient chain exactly as a task role would:
# environment credentials, no static long-lived key anywhere.
os.environ.update({
    "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
    "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
    "AWS_SESSION_TOKEN": creds["SessionToken"],
    "AWS_REGION": REGION,
})
os.environ.pop("AWS_PROFILE", None)

model = f"bedrock/{PROFILE}"
usage = {"in": 0, "out": 0}

# 1. Non-streaming, credentials resolved by the chain rather than passed in.
try:
    r = litellm.completion(model=model, max_tokens=16, temperature=0,
                           messages=[{"role": "user", "content": "Reply with exactly: OK"}])
    usage["in"] += r.usage.prompt_tokens
    usage["out"] += r.usage.completion_tokens
    record(True, "litellm resolves ambient credentials (no key passed)",
           f"reply {r.choices[0].message.content.strip()!r}, "
           f"{r.usage.prompt_tokens} in / {r.usage.completion_tokens} out")
except Exception as e:
    record(False, "litellm resolves ambient credentials", f"{type(e).__name__}: {str(e)[:120]}")

# 2. Streaming.
try:
    chunks, first_at, t0 = 0, None, time.time()
    for part in litellm.completion(model=model, max_tokens=48, temperature=0, stream=True,
                                   messages=[{"role": "user",
                                              "content": "Count from 1 to 8, space separated."}]):
        if part.choices[0].delta.content:
            chunks += 1
            first_at = first_at or time.time() - t0
    record(chunks > 1, "streaming preserved",
           f"{chunks} content chunks, first at {first_at:.2f}s" if chunks
           else "no chunks received")
except Exception as e:
    record(False, "streaming preserved", f"{type(e).__name__}: {str(e)[:120]}")

# 3. The tool-call loop — the part most likely to break through an adapter.
tools = [{"type": "function", "function": {
    "name": "get_filing_section",
    "description": "Fetch a named section of an SEC filing.",
    "parameters": {"type": "object", "properties": {
        "ticker": {"type": "string"}, "section": {"type": "string"}},
        "required": ["ticker", "section"]}}}]
try:
    msgs = [{"role": "user", "content": "Get the risk factors section for ticker ACME. Use the tool."}]
    r1 = litellm.completion(model=model, messages=msgs, tools=tools,
                            tool_choice="auto", max_tokens=256, temperature=0)
    usage["in"] += r1.usage.prompt_tokens
    usage["out"] += r1.usage.completion_tokens
    calls = r1.choices[0].message.tool_calls
    if not calls:
        record(False, "tool-call loop preserved", "model returned no tool call")
    else:
        call = calls[0]
        args = json.loads(call.function.arguments)
        msgs += [r1.choices[0].message.model_dump(),
                 {"role": "tool", "tool_call_id": call.id, "name": call.function.name,
                  "content": "Risk factors: supply chain concentration increased."}]
        r2 = litellm.completion(model=model, messages=msgs, tools=tools,
                                max_tokens=64, temperature=0)
        usage["in"] += r2.usage.prompt_tokens
        usage["out"] += r2.usage.completion_tokens
        record(True, "tool-call loop preserved",
               f"called {call.function.name}({args}), result fed back, "
               f"final: {r2.choices[0].message.content.strip()[:60]!r}")
except Exception as e:
    record(False, "tool-call loop preserved", f"{type(e).__name__}: {str(e)[:140]}")

# 4. The scope actually bites: a model outside the policy must be refused.
try:
    litellm.completion(model="bedrock/us.anthropic.claude-sonnet-4-6",
                       max_tokens=8, messages=[{"role": "user", "content": "hi"}])
    record(False, "scope denies an out-of-policy model", "ALLOWED — the policy is not binding")
except Exception as e:
    denied = "AccessDenied" in str(e) or "not authorized" in str(e)
    record(denied, "scope denies an out-of-policy model",
           "AccessDeniedException as expected" if denied else f"other error: {str(e)[:100]}")

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
