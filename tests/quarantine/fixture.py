"""The recorded corpus and the one step scope the quarantine suite mints for.

§ Boundaries — Never do: no live SEC fetch on a run's request path. The
recorded Apple 10-Q under `spikes/phase-0/fixtures/` is the corpus, and its
file name is the content hash the sidecar records.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

_REPOSITORY = Path(__file__).resolve().parents[2]

#: The recorded filing's content hash, which is also both fixture file names.
FILING_CONTENT_HASH = "4ad5bea67cedfa7542d623900355cc8d143ef95c1acc135a597f2eedabdb9177"

_FIXTURES = _REPOSITORY / "spikes" / "phase-0" / "fixtures"

#: Two step scopes over the *same* recorded filing. Identical evidence is what
#: makes AC-0221's case sharp: a reference minted for the other step is well
#: formed and resolves there, and differs from this step's only in provenance.
STEP_A = UUID("5c1a0b7e-9d3f-4a62-8e10-2b4c6d8f0a1e")
STEP_B = UUID("7a2b3c4d-5e6f-4071-9b8c-1d2e3f4a5b6c")


def recorded_filing() -> str:
    """The recorded 10-Q as text, read from the committed fixture."""
    return (_FIXTURES / f"{FILING_CONTENT_HASH}.html").read_text(
        encoding="utf-8", errors="replace"
    )


def expected_candidate_set() -> list[str]:
    """The committed baseline AC-0238 compares against, read literally.

    A committed artifact rather than a second call to the pipeline under
    test: an expectation computed from that pipeline cannot fail for a
    pipeline that derives the wrong set from the fixture.
    """
    path = _REPOSITORY / "tests" / "fixtures" / "candidate_set_expected.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    assert baseline["step_id"] == str(STEP_A)
    assert baseline["filing_content_hash"] == FILING_CONTENT_HASH
    references: list[str] = baseline["references"]
    return references
