"""Adapter module for the ``ced-evidence`` measurement commands.

The name records the first measurement this module carried — the Service
Quotas read — not the whole of what it owns. It is the one place the evidence
commands reach an out-of-process or framework boundary, so it also holds the
Bedrock cancellation stream and the TestModel factory the step-duration
sample is generated with.

Reads the regional TPM quota from AWS Service Quotas. Region comes from the
resolved client (``client.meta.region_name``), never from a configured
constant, so the record names where the measurement was taken.

The record excludes credential and account metadata: it carries the region,
service code, quota code, quota name, and quota value only — nothing that
identifies the caller or the account. AC-0311.

**The quota code is a well-known AWS identifier**, not a discovery made at
runtime. It is defined here so both the command and the test share the same
constant. The live probe verifies it resolves and confirms the quota name
matches the model's TPM limit; the offline construction test stubs the
client and proves the region and identity are recorded.

All boto3 / AWS SDK calls for the evidence commands live here rather than in
``worker/`` because the dependency-direction gate (AC-0007) confines AWS SDK
imports to ``adapters/``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = [
    "BEDROCK_SERVICE_CODE",
    "BEDROCK_TPM_QUOTA_CODE",
    "make_references_test_model",
    "open_cancellation_stream",
    "read_quota_record",
    "run_quota_measurement",
]


def make_references_test_model() -> object:
    """Return a TestModel configured to emit an empty references list.

    Used exclusively by the ``ced-evidence generate`` subcommand to drive steps
    through the full executor path without making provider calls.

    **Why a module named for Service Quotas owns a model factory.** Two
    constraints meet here. The dependency-direction gate (AC-0007) confines
    ``pydantic_ai`` imports to ``agents/`` and ``adapters/``, so this factory
    cannot live beside its only caller in ``worker/``; and this module is the
    evidence commands' single adapter boundary — see the module docstring —
    rather than a Service Quotas module that acquired an unrelated function.
    The name is narrower than the responsibility, which is a naming debt, not
    a layering one: renaming the module is the better fix and is recorded as
    out of scope in this spec's verification ledger, because it reaches files
    beyond the task that found it.
    """
    from pydantic_ai.models.test import TestModel  # noqa: PLC0415

    return TestModel(custom_output_args={"references": []})


#: The AWS Service Quotas service code for Amazon Bedrock.
BEDROCK_SERVICE_CODE = "bedrock"

#: The quota code for the cross-region tokens-per-minute limit for Anthropic
#: Claude Haiku 4.5 in us-east-1. Confirmed by live Service Quotas probe
#: on 2026-09-29; the probe verified the quota name matches the model's TPM
#: limit for the cross-region inference profile (``us.*`` model id prefix).
BEDROCK_TPM_QUOTA_CODE = "L-58BE175A"


def read_quota_record(client: Any) -> dict[str, object]:
    """Read the Bedrock on-demand TPM quota from Service Quotas.

    ``client`` is a boto3 ``service-quotas`` client. Region is taken from
    ``client.meta.region_name`` — the resolved client's own metadata — not from
    a configured constant or an environment variable. That is the AC-0311
    requirement: the record names the region the measurement was actually taken
    in, not a region someone declared.

    The returned dict carries:
    - ``region``: the resolved client region
    - ``service_code``: BEDROCK_SERVICE_CODE
    - ``quota_code``: BEDROCK_TPM_QUOTA_CODE
    - ``quota_name``: the name AWS returns for the quota
    - ``value``: the quota limit (float, tokens per minute)

    Credential metadata (access key, account id, ARN) is never read or stored.
    """
    region: str = client.meta.region_name
    response = client.get_service_quota(
        ServiceCode=BEDROCK_SERVICE_CODE,
        QuotaCode=BEDROCK_TPM_QUOTA_CODE,
    )
    quota = response["Quota"]
    return {
        "region": region,
        "service_code": BEDROCK_SERVICE_CODE,
        "quota_code": BEDROCK_TPM_QUOTA_CODE,
        "quota_name": str(quota["QuotaName"]),
        "value": float(quota["Value"]),
    }


def run_quota_measurement() -> dict[str, object]:
    """Create a live Service Quotas client and return the quota record.

    Thin shim that owns the ``boto3`` import so ``worker/`` need not reach
    the AWS SDK directly. Region comes from the resolved client. AC-0311.
    """
    import boto3

    client = boto3.client("service-quotas")
    return read_quota_record(client)


def open_cancellation_stream(
    model_id: str,
    *,
    max_tokens: int = 2048,
) -> tuple[str, Callable[[], bool], Callable[[float], bool]]:
    """Open a Bedrock response stream and return measurement callables.

    Returns ``(region, close_stream, observe_closure)`` where:
    - ``region`` is taken from the resolved bedrock-runtime client.
    - ``close_stream()`` initiates cancellation by closing the response body,
      and returns whether this process's reader was **still running at the
      moment of the close** — sampled immediately before the close, so a
      stream that had already ended on its own is reported as such.
    - ``observe_closure(timeout)`` joins the reader thread and returns ``True``
      when it finishes within ``timeout`` seconds. This observes **this
      process's** reader and nothing about the provider's side of the
      transport.

    The request asks for a long reply, so normal generation lasts far longer
    than the gap between the first chunk and the close. Being in flight is
    then *checked*, not assumed: ``close_stream`` reports whether the reader
    was still running, and the classifier refuses a sample where it was not.
    A stream that ends before its first chunk is refused here outright. All
    local resources (thread, stream) are released through the returned
    callables; the caller must invoke both to avoid leaks.

    Raises on a failed ``invoke_model_with_response_stream`` call so the
    caller can name the denied action without reading credentials.

    Lives in ``adapters/`` because the dependency-direction gate confines boto3
    to that layer.
    """
    import json
    import threading

    import boto3

    bedrock = boto3.client("bedrock-runtime")
    region: str = bedrock.meta.region_name

    body_bytes = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            # A long reply, deliberately: the stream must still be generating
            # when the body is closed, or the close cancels nothing.
            "messages": [
                {
                    "role": "user",
                    "content": "Count from 1 to 1000, one number per line, with no other text.",
                }
            ],
        }
    ).encode()

    response = bedrock.invoke_model_with_response_stream(
        modelId=model_id,
        body=body_bytes,
        contentType="application/json",
        accept="application/json",
    )
    event_stream = response["body"]

    # Consume the first chunk, so the stream has started before cancellation.
    # A stream that ends before even its first chunk was never in flight, so
    # it is refused rather than passed through as a sample.
    try:
        next(iter(event_stream))
    except StopIteration as exc:
        event_stream.close()
        raise RuntimeError(
            "the response stream ended before its first chunk; not an in-flight sample"
        ) from exc

    # Reader thread drains what remains after close is called.
    reader_done = threading.Event()

    def _drain() -> None:
        try:
            for _ in event_stream:
                pass
        except Exception:
            pass
        reader_done.set()

    reader_thread = threading.Thread(target=_drain, daemon=True)
    reader_thread.start()

    def close_stream() -> bool:
        # Sampled *before* the close: a reader already finished here means the
        # stream ended on its own and this close cancels nothing.
        in_flight = reader_thread.is_alive()
        try:
            event_stream.close()
        except Exception:
            pass
        return in_flight

    def observe_closure(timeout_s: float) -> bool:
        reader_thread.join(timeout=timeout_s)
        return not reader_thread.is_alive()

    return region, close_stream, observe_closure
