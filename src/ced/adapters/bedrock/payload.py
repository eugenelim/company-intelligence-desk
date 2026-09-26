"""Re-export of the object-store write/read path.

T1 placed the payload writer here because T1's own Touches admitted nothing
else that could hold one and the event schema accepts only a ``payload_ref``.
T3 relocated it to ``adapters/objectstore/``, which owns AC-0231's
scope-qualified key contract formally. This module re-exports the same names
so existing callers need no update.

**Keep all imports from ``adapters/objectstore/client``**, not the other way
round. Nothing in ``bedrock/`` should define object-store behaviour.
"""

from __future__ import annotations

from ced.adapters.objectstore.client import (
    BUCKET_NAME,
    OWNER_SCOPE,
    read_payload,
    read_payload_bytes,
    write_payload,
    write_payload_bytes,
)

__all__ = [
    "BUCKET_NAME",
    "OWNER_SCOPE",
    "read_payload",
    "read_payload_bytes",
    "write_payload",
    "write_payload_bytes",
]
