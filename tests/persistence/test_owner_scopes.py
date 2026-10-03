"""Owner scope tests for the extended object-store client.

Verifies that the closed owner-scope parameter on ``write_payload`` and
``write_payload_bytes`` admits only the declared constants and rejects
everything else, while preserving the existing default behavior.

Offline: all tests run without the substrate (no MinIO needed) because we
test the validation logic, not the network call.  The substrate-backed round-
trip is covered in ``tests/ingestion/test_snapshot_storage.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ced.adapters.objectstore.client import (
    _ADMITTED_SCOPES,
    OWNER_SCOPE,
    READINESS_SCOPE,
    SNAPSHOT_SCOPE,
    write_payload,
    write_payload_bytes,
)

# ---------------------------------------------------------------------------
# Scope constants are defined
# ---------------------------------------------------------------------------


def test_owner_scope_constant_value() -> None:
    """OWNER_SCOPE is the canonical walking-skeleton scope string."""
    assert OWNER_SCOPE == "ced-step-lifecycle"


def test_snapshot_scope_constant_value() -> None:
    """SNAPSHOT_SCOPE is the canonical snapshot scope string."""
    assert SNAPSHOT_SCOPE == "ced-first-published-analysis-snapshot"


def test_readiness_scope_constant_value() -> None:
    """READINESS_SCOPE is the canonical readiness-sentinel scope string."""
    assert READINESS_SCOPE == "ced-readiness"


def test_admitted_scopes_contains_all_three() -> None:
    """All three scope constants are in the admitted set.

    Mutation: remove one constant from ``_ADMITTED_SCOPES`` — writes using
    that scope would be refused.
    """
    assert OWNER_SCOPE in _ADMITTED_SCOPES
    assert SNAPSHOT_SCOPE in _ADMITTED_SCOPES
    assert READINESS_SCOPE in _ADMITTED_SCOPES


# ---------------------------------------------------------------------------
# write_payload_bytes refuses unrecognised scope before any network call
# ---------------------------------------------------------------------------


def test_write_payload_bytes_refuses_unrecognised_scope() -> None:
    """An unrecognised owner_scope raises ValueError before any S3 call.

    Mutation: remove the scope check — an arbitrary string would be accepted
    and used as the key prefix, potentially creating orphaned objects.
    """
    with pytest.raises(ValueError, match="not in the admitted set"):
        write_payload_bytes(b"test", owner_scope="ced-unrecognised-scope")


def test_write_payload_refuses_unrecognised_scope() -> None:
    """write_payload also raises ValueError for an unrecognised scope.

    Mutation: delegate to write_payload_bytes only for bytes writes — the
    dict-serialising path would bypass the check.
    """
    with pytest.raises(ValueError, match="not in the admitted set"):
        write_payload({"key": "value"}, owner_scope="not-a-valid-scope")


# ---------------------------------------------------------------------------
# Existing callers' default behavior is preserved
# ---------------------------------------------------------------------------


def test_write_payload_bytes_default_scope_is_owner_scope() -> None:
    """The default scope for write_payload_bytes is still OWNER_SCOPE.

    This verifies that adding the parameter did not change existing callers
    that rely on the default.

    Mutation: change the default to SNAPSHOT_SCOPE — existing callers using
    the keyword-arg default would write to the wrong scope.
    """
    import inspect

    sig = inspect.signature(write_payload_bytes)
    param = sig.parameters.get("owner_scope")
    assert param is not None, "owner_scope parameter must exist"
    assert param.default == OWNER_SCOPE, (
        f"default scope must be {OWNER_SCOPE!r}, got {param.default!r}"
    )


def test_write_payload_default_scope_is_owner_scope() -> None:
    """The default scope for write_payload is still OWNER_SCOPE.

    Mutation: same as above.
    """
    import inspect

    sig = inspect.signature(write_payload)
    param = sig.parameters.get("owner_scope")
    assert param is not None, "owner_scope parameter must exist"
    assert param.default == OWNER_SCOPE


# ---------------------------------------------------------------------------
# Admitted scopes produce correctly prefixed keys (no I/O — mocked)
# ---------------------------------------------------------------------------


def test_write_payload_bytes_uses_snapshot_scope_in_key() -> None:
    """Passing SNAPSHOT_SCOPE produces a key prefixed with that scope.

    Mutation: ignore the ``owner_scope`` argument and always use ``OWNER_SCOPE``
    — the returned key would have the wrong prefix.
    """
    captured_key: list[str] = []

    def fake_put(**kwargs: object) -> None:
        captured_key.append(str(kwargs.get("Key", "")))

    with (
        patch("ced.adapters.objectstore.client._s3_client") as mock_client,
        patch("ced.adapters.objectstore.client._ensure_bucket"),
    ):
        s3 = MagicMock()
        s3.put_object.side_effect = fake_put
        mock_client.return_value = s3

        key = write_payload_bytes(b"snapshot-bytes", owner_scope=SNAPSHOT_SCOPE)

    assert key.startswith(f"{SNAPSHOT_SCOPE}/"), (
        f"key must start with '{SNAPSHOT_SCOPE}/', got {key!r}"
    )


def test_write_payload_bytes_uses_readiness_scope_in_key() -> None:
    """Passing READINESS_SCOPE produces a key prefixed with that scope.

    Mutation: same as above for READINESS_SCOPE.
    """
    with (
        patch("ced.adapters.objectstore.client._s3_client") as mock_client,
        patch("ced.adapters.objectstore.client._ensure_bucket"),
    ):
        s3 = MagicMock()
        s3.put_object.return_value = None
        mock_client.return_value = s3

        key = write_payload_bytes(b"readiness-bytes", owner_scope=READINESS_SCOPE)

    assert key.startswith(f"{READINESS_SCOPE}/"), (
        f"key must start with '{READINESS_SCOPE}/', got {key!r}"
    )


def test_write_payload_bytes_default_uses_owner_scope_in_key() -> None:
    """The default write (no owner_scope) uses OWNER_SCOPE in the key.

    Mutation: change the default to a different scope — existing callers would
    write to the wrong scope and this assertion would fail.
    """
    with (
        patch("ced.adapters.objectstore.client._s3_client") as mock_client,
        patch("ced.adapters.objectstore.client._ensure_bucket"),
    ):
        s3 = MagicMock()
        s3.put_object.return_value = None
        mock_client.return_value = s3

        key = write_payload_bytes(b"lifecycle-bytes")  # no owner_scope

    assert key.startswith(f"{OWNER_SCOPE}/"), (
        f"default key must start with '{OWNER_SCOPE}/', got {key!r}"
    )
