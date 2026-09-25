"""Write and read content-addressed JSON payloads to the local object store.

T1's minimal payload path. T3 replaces this with ``adapters/objectstore/``,
which owns AC-0231's scope-qualified key contract formally. Until then this
module holds the write path the executor needs to persist the producer tuple.

**MinIO credentials are explicit, never ambient.** After the scoped Bedrock role
is assumed, the process environment holds an ``AWS_ACCESS_KEY_ID`` with an
``ASIA*`` prefix (a temporary session key). ``boto3``'s default credential chain
would resolve that key for every client, including the S3 client that talks to
MinIO, and MinIO would reject the signature — the endpoint and the AWS signing
region are both wrong. Passing explicit ``aws_access_key_id`` /
``aws_secret_access_key`` to ``boto3.client()`` creates a static-credential
provider that wins over the chain, so the Bedrock role credential never reaches
this client.

**Key format follows AC-0231 from the first write.** T3 owns AC-0231 formally,
but the scope-qualified shape is a one-way door: keys written without a prefix
cannot be renamed atomically once a corpus exists, so this module follows the
rule early. Keys are ``<OWNER_SCOPE>/<sha256_hex>`` of the serialized payload
bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
from ipaddress import ip_address
from typing import Any, cast
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

__all__ = ["BUCKET_NAME", "OWNER_SCOPE", "read_payload", "write_payload"]

#: The object store bucket all CED payload objects share.
BUCKET_NAME = "ced-payloads"

#: AC-0231's scope qualifier for payloads written by this spec.
OWNER_SCOPE = "ced-step-lifecycle"

_DEFAULT_ENDPOINT = "http://127.0.0.1:59000"
_DEFAULT_ACCESS_KEY = "local_only_not_a_secret"
_DEFAULT_SECRET_KEY = "local_only_not_a_secret"

#: Environment variables for overriding the local MinIO defaults. The test
#: suite relies on the defaults; a deployed process would set these.
_ACCESS_KEY_VAR = "CED_OBJECT_STORE_ACCESS_KEY"
_SECRET_KEY_VAR = "CED_OBJECT_STORE_SECRET_KEY"
_ENDPOINT_VAR = "CED_OBJECT_STORE_ENDPOINT"


def write_payload(data: dict[str, Any]) -> str:
    """Serialize ``data`` as canonical JSON, write to the object store, and return the key.

    The key is ``<OWNER_SCOPE>/<sha256_hex>`` of the canonical bytes.
    Content-addressed: the same data written twice produces the same key, so a
    crash-and-retry leaves one unreferenced object rather than two.

    The payload object is written **before** any fenced append that references
    it, which is the ordering r5 § 3 requires: a crash between the two writes
    leaves an unreferenced object rather than a dangling reference on a run
    that can never resume.
    """
    body = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(body).hexdigest()
    key = f"{OWNER_SCOPE}/{digest}"
    client = _s3_client()
    _ensure_bucket(client)
    client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    return key


def read_payload(key: str) -> dict[str, Any]:
    """Read and deserialize a payload from the object store by its key."""
    response = _s3_client().get_object(Bucket=BUCKET_NAME, Key=key)
    return cast(dict[str, Any], json.loads(response["Body"].read()))


def _checked_endpoint(value: str) -> str:
    """Refuse an object-store endpoint that is not a plain http(s) URL.

    The endpoint is deployment configuration and nothing else reads it, so a
    mistyped or hostile value would otherwise send every payload write
    wherever it pointed — a link-local address such as the cloud metadata
    endpoint among them. The S3 protocol makes that a poor exfiltration
    channel rather than a good one, which is why this is a guard and not a
    control: it refuses the obvious mistake close to where the value is used.

    The permanent object-store adapter is `walking-skeleton-step-lifecycle`'s
    T3, which owns `adapters/objectstore/` and AC-0231's scope-qualified keys.
    This module exists because T1 must write one payload object to record the
    producer tuple and the event schema accepts only a reference, never an
    inline value.
    """
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            f"{_ENDPOINT_VAR} must be an http or https URL with a host; got {value!r}"
        )
    # **The scheme check alone is not the control.** A link-local address is a
    # perfectly well-formed http URL, so checking only the scheme would admit
    # the cloud instance-metadata endpoint — the case this guard exists for.
    # Loopback and ordinary private addresses stay admitted: the local
    # substrate serves MinIO on one, and refusing those would refuse the
    # deployment this module ships against.
    try:
        host = ip_address(parsed.hostname)
    except ValueError:
        return value
    if host.is_link_local:
        raise ValueError(
            f"{_ENDPOINT_VAR} resolves to the link-local range ({parsed.hostname}), "
            "which is where cloud instance metadata is served; refusing to "
            "direct object-store writes there"
        )
    return value


def _s3_client() -> Any:
    """Construct an S3 client with explicit MinIO credentials.

    Explicit ``aws_access_key_id`` / ``aws_secret_access_key`` parameters
    create a static-credential provider that takes precedence over the
    environment-variable chain, so the assumed Bedrock role's temporary key in
    ``AWS_ACCESS_KEY_ID`` does not reach this client. No session token is
    passed; MinIO does not use one.
    """
    endpoint = _checked_endpoint(os.environ.get(_ENDPOINT_VAR, _DEFAULT_ENDPOINT))
    access_key = os.environ.get(_ACCESS_KEY_VAR, _DEFAULT_ACCESS_KEY)
    secret_key = os.environ.get(_SECRET_KEY_VAR, _DEFAULT_SECRET_KEY)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )


def _ensure_bucket(client: Any) -> None:
    """Create the bucket if it does not exist. Idempotent."""
    try:
        client.head_bucket(Bucket=BUCKET_NAME)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "404":
            client.create_bucket(Bucket=BUCKET_NAME)
        else:
            raise
