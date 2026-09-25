"""AC-0223, AC-0224, AC-0225, AC-0254 — a real step under a scoped Bedrock role.

All four criteria require the substrate and live AWS credentials. The test
creates (or updates) the scoped IAM role, assumes it, runs one step, then reads
the evidence from the event log and the payload object.

**The AWS admin profile name is read from ``CED_AWS_ADMIN_PROFILE``**, never
written into this file: a profile name containing an account identifier would
trip ``tools/lint-no-identifiers.py``, which is a hard gate.

**What this test cannot establish, stated alongside what it can.** AC-0224
asserts the absence of a static credential in the test process's environment.
On a deployed fleet the task role supplies credentials with no session token in
the process environment at all — a strictly stronger property. This scan cannot
demonstrate that stronger property.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import threading
import time
import uuid
from typing import Any

import boto3
import psycopg
import pytest

from ced.adapters.bedrock.model_factory import (
    FETCH_ADAPTER_NAME,
    MODEL_ADAPTER_NAME,
    make_bedrock_model,
)
from ced.adapters.bedrock.payload import read_payload
from ced.adapters.framework_contract import PINNED_FRAMEWORK_VERSION
from ced.adapters.postgres.dsn import database_url
from ced.adapters.postgres.event_log import read_events, start_run
from ced.worker.executor import make_step_body
from ced.worker.pool import Lease, PoolConfig

#: The deployable the scan reads. `AGENTS.md` § The local substrate owns how
#: it is brought up; this check reads it and never starts or stops it.
_COMPOSE_FILE = pathlib.Path(__file__).resolve().parents[2] / "deploy" / "compose.yaml"

pytestmark = pytest.mark.substrate

#: Inference profile id — cross-region, no foundation-model suffix.
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
#: The underlying foundation model, used to construct the region-wildcarded ARN.
MODEL_SUFFIX = "anthropic.claude-haiku-4-5-20251001-v1:0"
#: The scoped IAM role, exactly as the plan pins it.
ROLE_NAME = "ced-t1-bedrock-invoke"
REGION = "us-east-1"
#: The policy name the spike used, carried forward unchanged.
POLICY_NAME = "bedrock-invoke"


# ---------------------------------------------------------------------------
# AWS credential setup
# ---------------------------------------------------------------------------


def _require_admin_profile() -> str:
    """Return the admin profile name from the environment, or skip."""
    profile = os.environ.get("CED_AWS_ADMIN_PROFILE", "")
    if not profile:
        pytest.skip(
            "CED_AWS_ADMIN_PROFILE is not set; set it to the AWS admin profile "
            "name to run the provider suite"
        )
    return profile


@pytest.fixture(scope="module")
def scoped_aws_credentials(require_substrate: None) -> Any:
    """Create the scoped IAM role, assume it, and export its credentials to env.

    The IAM shape carries over from spike 1 unchanged:
    - Two invoke actions only.
    - Inference-profile ARN pinned to the calling region.
    - Foundation-model ARN region-wildcarded (cross-region routing).
    - No ``aws:RequestedRegion`` condition (it denies cross-region calls).

    Yields the raw credential dict and restores the original environment on
    teardown.
    """
    profile = _require_admin_profile()
    session = boto3.session.Session(profile_name=profile)
    iam = session.client("iam", region_name=REGION)
    sts = session.client("sts", region_name=REGION)

    caller = sts.get_caller_identity()
    account = caller["Account"]
    caller_arn = caller["Arn"]

    # Trust policy: the same normalisation the spike used so the derived session
    # matches the trust predicate even when the caller is itself an assumed-role
    # session (arn contains assumed-role/).
    normalised_caller = (
        caller_arn.replace(":sts:", ":iam:").replace("assumed-role/", "role/").rsplit("/", 1)[0]
    )
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{account}:root"},
                "Action": "sts:AssumeRole",
                "Condition": {"ArnLike": {"aws:PrincipalArn": f"{normalised_caller}*"}},
            }
        ],
    }
    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                "Resource": [
                    f"arn:aws:bedrock:{REGION}:{account}:inference-profile/{MODEL_ID}",
                    f"arn:aws:bedrock:*::foundation-model/{MODEL_SUFFIX}",
                ],
            }
        ],
    }

    # Upsert the role — create if absent, silently skip if present.
    try:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="T1 provider test: least-privilege Bedrock invoke.",
            MaxSessionDuration=3600,
            Tags=[
                {"Key": "project", "Value": "company-intelligence-desk"},
                {"Key": "lifecycle", "Value": "t1-test"},
            ],
        )
    except iam.exceptions.EntityAlreadyExistsException:
        pass

    # **The trust policy is refreshed on every run, not only at creation.**
    # `create_role` is a no-op once the role exists, so without this the
    # permissions below would be rewritten each run while the predicate
    # deciding *who may assume the role* stayed whatever the first run wrote.
    # A role pre-created in a shared account with a wider principal condition,
    # or one left by a different caller identity, would keep that wider trust
    # indefinitely and nothing here would report it.
    iam.update_assume_role_policy(
        RoleName=ROLE_NAME,
        PolicyDocument=json.dumps(trust_policy),
    )

    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps(inline_policy),
    )

    role_arn = f"arn:aws:iam::{account}:role/{ROLE_NAME}"

    # Assume with retries: IAM is eventually consistent after role creation.
    creds = None
    last_exc: Exception | None = None
    for _ in range(10):
        try:
            creds = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="t1-provider-test",
            )["Credentials"]
            break
        except Exception as exc:
            last_exc = exc
            time.sleep(3)

    if creds is None:
        pytest.fail(f"Could not assume scoped role {ROLE_NAME!r} after 10 attempts: {last_exc}")

    # Hand the scoped session to the ambient chain exactly as a task role would.
    # boto3 reads `AWS_DEFAULT_REGION`; pydantic-ai's BedrockProvider forwards
    # it to the boto3 session client. `AWS_REGION` is the Lambda runtime
    # convention and is not read by the boto3 credential chain itself.
    saved = {
        k: os.environ.pop(k, None)
        for k in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_DEFAULT_REGION",
            "AWS_REGION",
            "AWS_PROFILE",
        )
    }
    os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
    os.environ["AWS_SESSION_TOKEN"] = creds["SessionToken"]
    os.environ["AWS_DEFAULT_REGION"] = REGION

    yield creds

    # Restore the original environment.
    for key, value in saved.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# Database setup and step execution
# ---------------------------------------------------------------------------

_ROLE_NAME_IN_DB = "t1-provider-check"
_PRINCIPAL = "t1-test-principal"
_POOL_CLASS = "t1-test"  # distinct from compose workers' fault-injection class


@pytest.fixture(scope="module")
def step_result(scoped_aws_credentials: Any, require_substrate: None) -> dict[str, Any]:
    """Insert a runnable step, claim it, execute it, and return the evidence.

    Returns a dict with keys ``events`` and ``run_id`` so individual criteria
    can extract what they need without re-executing the provider call.
    """
    # Insert the agent role record. The migration superuser has INSERT on
    # agent_role; app_api and app_worker hold only SELECT.
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            """
            INSERT INTO agent_role
                (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
            VALUES (%s, 1, '[]'::jsonb, '', %s::jsonb, 'reference-selection')
            ON CONFLICT (role_name, version) DO UPDATE
                SET model_settings = EXCLUDED.model_settings
            """,
            (
                _ROLE_NAME_IN_DB,
                json.dumps(
                    {
                        "model_id": MODEL_ID,
                        "settings": {},
                        "limits": {},
                    }
                ),
            ),
        )
        conn.commit()

    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    # start_run requires the API connection (app_api holds INSERT on runs/steps
    # and EXECUTE on append_run_event).
    with psycopg.connect(database_url("api")) as conn:
        start_run(
            conn,
            run_id=run_id,
            step_id=step_id,
            principal=_PRINCIPAL,
            agent_role=_ROLE_NAME_IN_DB,
        )

    # Manually claim the step so the body can append fenced events. The pool
    # class is set to an unused value so the compose workers (fault-injection)
    # never see this row.
    with psycopg.connect(database_url("worker")) as conn:
        row = conn.execute(
            """
            UPDATE steps
               SET state = 'leased',
                   owner = 't1-test-worker',
                   lease_epoch = lease_epoch + 1,
                   lease_expires_at = now() + interval '300 seconds',
                   pool_class = %s
             WHERE step_id = %s
             RETURNING lease_epoch
            """,
            (_POOL_CLASS, step_id),
        ).fetchone()
        conn.commit()

    assert row is not None, "step row not found after start_run"
    epoch = int(row[0])

    lease = Lease(
        step_id=step_id,
        run_id=run_id,
        epoch=epoch,
        agent_role=_ROLE_NAME_IN_DB,
    )

    config = PoolConfig(
        worker_id="t1-test-worker",
        default_limits={
            "per_request_input_tokens_limit": 4000,
            "input_tokens_limit": 40000,
            "request_limit": 8,
            "tool_calls_limit": 4,
            "count_tokens_before_request": False,
        },
        allowed_model_ids=(MODEL_ID,),
        model_factory=make_bedrock_model,
    )

    # Execute the step body synchronously in this process.
    body = make_step_body(config)
    body(lease, threading.Event())

    # Read the full event log for this run.
    with psycopg.connect(database_url("worker")) as conn:
        events = read_events(conn, run_id=run_id)

    return {"events": events, "run_id": run_id}


@pytest.fixture(scope="module")
def completed_event(step_result: dict[str, Any]) -> Any:
    """The ``step.completed`` event, or ``None`` if the step failed."""
    for ev in step_result["events"]:
        if ev.type == "step.completed":
            return ev
    return None


@pytest.fixture(scope="module")
def started_event(step_result: dict[str, Any]) -> Any:
    """The ``step.started`` event, which carries the producer tuple payload."""
    for ev in step_result["events"]:
        if ev.type == "step.started":
            return ev
    return None


@pytest.fixture(scope="module")
def producer_payload(started_event: Any) -> dict[str, Any] | None:
    """The producer tuple read back from the payload object, or ``None``."""
    if started_event is None or started_event.payload_ref is None:
        return None
    return read_payload(started_event.payload_ref)


# ---------------------------------------------------------------------------
# AC-0223: step reaches step.completed from the event log
# ---------------------------------------------------------------------------


def test_ac_0223_step_reaches_completed(completed_event: Any) -> None:
    """AC-0223. The event log contains a ``step.completed`` for this run.

    Evidence comes from the event log (what the system recorded), not from
    test setup or from a value the harness placed.
    """
    assert completed_event is not None, (
        "AC-0223 FAIL: no step.completed event found in the event log. "
        "The step may have appended step.failed instead — check the test log."
    )


# ---------------------------------------------------------------------------
# AC-0224: no long-lived credential in the process environment
# ---------------------------------------------------------------------------


def test_ac_0224_no_long_lived_credential() -> None:
    """AC-0224. The running worker container holds no long-lived credential.

    **The container is the observation, not this process.** An earlier build
    of this check read `os.environ["AWS_ACCESS_KEY_ID"]` in the pytest
    process and asserted it carried the `ASIA` prefix — but the fixture in
    this same file is what put that value there, so the assertion observed
    its own setup and would have held whatever the deployable actually
    shipped. The criterion names the running worker container, and the plan
    is explicit that the compose file is the intent while the container is
    the fact.

    What this establishes on the deployable built from `deploy/Dockerfile`:
    no `AKIA`-prefixed key in the process environment, and no AWS credentials
    file on the running filesystem.

    **What it does not establish**, stated rather than implied. On a deployed
    fleet the task role supplies credentials with no session key in the
    process environment at all, and that stronger property is not what a scan
    of a locally running container can see. Nor can a scan of a *running*
    filesystem decide "baked into the image": a secret added in one layer and
    removed in a later one is still recoverable from the image, and no image
    scanner is wired in this repository. Both limits are recorded in the
    spec's Follow-ons.
    """
    probe = subprocess.run(
        [
            "docker-compose",
            "-f",
            str(_COMPOSE_FILE),
            "exec",
            "-T",
            "worker-a",
            "sh",
            "-lc",
            # Env first, then every credentials file a default AWS chain reads.
            'env; echo "---FILES---"; '
            "cat /root/.aws/credentials ~/.aws/credentials "
            "/root/.aws/config ~/.aws/config 2>/dev/null || true",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if probe.returncode != 0:
        pytest.skip(
            "worker-a is not running; bring the substrate up per AGENTS.md "
            f"§ The local substrate (docker-compose said: {probe.stderr.strip()[:200]})"
        )

    environment, _, files = probe.stdout.partition("---FILES---")

    assert "AKIA" not in environment, (
        "AC-0224 FAIL: an AKIA-prefixed long-lived access key is present in the "
        "running worker container's environment"
    )
    assert "AKIA" not in files, (
        "AC-0224 FAIL: an AKIA-prefixed long-lived access key is readable from a "
        "credentials file inside the running worker container"
    )
    assert "aws_secret_access_key" not in files.lower(), (
        "AC-0224 FAIL: an AWS credentials file is baked into the worker image"
    )

    # The deployable wires no provider at all today, which is a stronger fact
    # than the criterion requires and is worth failing on if it ever changes
    # silently: a credential arriving here should arrive by the assumed-role
    # path the model seam resolves, never as image or compose content.
    static_keys = [
        line
        for line in environment.splitlines()
        if line.startswith("AWS_ACCESS_KEY_ID=") or line.startswith("AWS_SECRET_ACCESS_KEY=")
    ]
    assert not static_keys, (
        "AC-0224 FAIL: the worker container carries an AWS key in its environment: "
        f"{[k.split('=')[0] for k in static_keys]}"
    )


# ---------------------------------------------------------------------------
# AC-0225: producer tuple records the inference profile and framework version
# ---------------------------------------------------------------------------


def test_ac_0225_producer_tuple_records_profile_and_version(
    producer_payload: dict[str, Any] | None,
) -> None:
    """AC-0225. Producer tuple names the inference profile and framework version.

    The payload is written to the object store before ``step.started`` is
    appended, and ``step.started`` carries the payload key. Reading it back
    proves the data was persisted, not inferred from test setup.
    """
    assert producer_payload is not None, (
        "AC-0225 FAIL: no producer tuple payload found. "
        "step.started either was not appended or carried no payload_ref."
    )
    assert "inference_profile" in producer_payload, (
        "AC-0225 FAIL: producer tuple is missing 'inference_profile'."
    )
    assert "framework_version" in producer_payload, (
        "AC-0225 FAIL: producer tuple is missing 'framework_version'."
    )
    assert producer_payload["inference_profile"] == MODEL_ID, (
        f"AC-0225 FAIL: inference_profile is {producer_payload['inference_profile']!r}, "
        f"expected {MODEL_ID!r}."
    )
    assert producer_payload["framework_version"] == PINNED_FRAMEWORK_VERSION, (
        f"AC-0225 FAIL: framework_version is {producer_payload['framework_version']!r}, "
        f"expected {PINNED_FRAMEWORK_VERSION!r}."
    )


# ---------------------------------------------------------------------------
# AC-0254: producer tuple names the three security-bearing members
# ---------------------------------------------------------------------------


def test_ac_0254_producer_tuple_names_security_bearing_members(
    producer_payload: dict[str, Any] | None,
) -> None:
    """AC-0254. Producer tuple names the three security-bearing fields.

    ``model_adapter``, ``fetch_adapter``, and ``tool_manifest_hash`` let an
    auditor distinguish a live Bedrock call from a fixture replay and verify
    what integration tools a step had access to. AC-0223's live-versus-replay
    check rests on ``model_adapter``.
    """
    assert producer_payload is not None, "AC-0254 FAIL: no producer tuple to inspect."
    for field in ("model_adapter", "fetch_adapter", "tool_manifest_hash"):
        assert field in producer_payload, f"AC-0254 FAIL: producer tuple is missing {field!r}."
    assert producer_payload["model_adapter"] == MODEL_ADAPTER_NAME, (
        f"AC-0254 FAIL: model_adapter is {producer_payload['model_adapter']!r}, "
        f"expected {MODEL_ADAPTER_NAME!r}."
    )
    assert producer_payload["fetch_adapter"] == FETCH_ADAPTER_NAME, (
        f"AC-0254 FAIL: fetch_adapter is {producer_payload['fetch_adapter']!r}, "
        f"expected {FETCH_ADAPTER_NAME!r}."
    )
    # tool_manifest_hash is present and is a hex string (sha256 = 64 chars).
    manifest_hash = producer_payload["tool_manifest_hash"]
    assert isinstance(manifest_hash, str) and len(manifest_hash) == 64, (
        f"AC-0254 FAIL: tool_manifest_hash is {manifest_hash!r}; "
        "expected a 64-character hex string."
    )
