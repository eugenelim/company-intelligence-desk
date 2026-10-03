"""SEC EDGAR adapter — bounded, rate-gated HTTP acquisition.

Exports the public surface used by ``ced.worker.ingestion`` and the
observation command. All live network access goes through this module.
"""

from ced.adapters.sec.client import (
    SEC_CONTACT_ENV,
    AttemptRecord,
    SecBlockedError,
    SecClientError,
    SecRedirectError,
    acquire_contact,
    fetch_filing,
    fetch_submissions,
    open_postgres_gate,
    run_observation,
)

__all__ = [
    "SEC_CONTACT_ENV",
    "AttemptRecord",
    "SecBlockedError",
    "SecClientError",
    "SecRedirectError",
    "acquire_contact",
    "fetch_filing",
    "fetch_submissions",
    "open_postgres_gate",
    "run_observation",
]
