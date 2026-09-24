"""The layout on disk matches ADR-0003, which is the only review it now gets.

The owner waived the RFC route for this delivery on 2026-09-18, so nothing
stands between a wrong directory set and the code that inherits it except
ADR-0003 and this check. The plan therefore makes it a test rather than a note:
`walking-skeleton-foundation` plan T1, `Tests:`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_0003 = REPO_ROOT / "docs" / "adr" / "0003-repository-layout.md"
ADR_0007 = (
    REPO_ROOT / "docs" / "adr" / "0007-github-directory-is-not-an-application-directory.md"
)

#: Top-level directories that predate ADR-0003 and that D2 explicitly leaves
#: ungoverned. Enumerated rather than pattern-matched — a rule like "ignore
#: anything that looks like tooling" is a hole through which a sixth
#: application directory arrives unrecorded.
#:
#: **`.github/` is deliberately absent.** It postdates ADR-0003 by four days,
#: so adding it here would make the sentence above false and turn this set
#: into the pattern-match hole it refuses. ADR-0007 records it instead, and
#: `_directories_adr_0007_names` is how this check reads that record.
PREDATING = frozenset(
    {
        ".agents",
        ".claude",
        ".codex",
        "docs",
        "governance",
        "spikes",
        "tools",
    }
)


def _tracked_top_level_directories() -> set[str]:
    """Return the top-level directories git tracks.

    Tracked content, not filesystem entries. The Never-do is about the layout
    that enters history, and a tool cache such as `.pytest_cache/` or a local
    `.venv/` is neither reviewed nor committed — reading the filesystem would
    make this check fail on whichever tool ran last, which is how a real gate
    gets switched off.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {path.split("/", 1)[0] for path in listing.split("\0") if path and "/" in path}


def _directories_adr_0003_names() -> set[str]:
    """Return the directory names D1's table names, read from the record.

    Parsed from the ADR rather than restated here. A list duplicated into the
    test would let the two drift apart, and then the test would be checking
    the copy rather than the decision.
    """
    text = ADR_0003.read_text(encoding="utf-8")
    decision = text.split("## Decision", 1)[1].split("## Consequences", 1)[0]
    # The table is nested inside D1's list item, so rows carry leading
    # indentation. Anchoring on `|` alone would also match the Consequences
    # tables, which is why the slice above is bounded to ## Decision.
    return set(re.findall(r"^\s*\| `([a-z_]+)/` \|", decision, flags=re.MULTILINE))


def _directories_adr_0007_names() -> set[str]:
    """Return the non-application directory names ADR-0007 D1's table names.

    Read from the superseding record for the same reason the sibling above
    reads ADR-0003: ADR-0007 D3 makes parsing both records the decision, so a
    list restated here would check the copy. The pattern admits a leading dot,
    which is the whole difference from the sibling — a platform-mandated path
    is exactly the kind this record exists to carry.
    """
    text = ADR_0007.read_text(encoding="utf-8")
    decision = text.split("## Decision", 1)[1].split("## Consequences", 1)[0]
    return set(re.findall(r"^\s*\| `(\.?[a-z_]+)/` \|", decision, flags=re.MULTILINE))


def test_adr_0003_names_the_directories_the_plan_needs() -> None:
    """Setup check: the parse found a table, not an empty set."""
    assert _directories_adr_0003_names() == {
        "src",
        "tests",
        "migrations",
        "contracts",
        "deploy",
    }


def test_adr_0007_names_the_non_application_directories() -> None:
    """Setup check for the superseding record's own parse.

    Without it, an ADR-0007 whose table stopped parsing would make
    `test_no_top_level_directory_is_unrecorded` red for a reason that has
    nothing to do with the layout, and the message would name the directory
    rather than the broken parse.
    """
    assert _directories_adr_0007_names() == {".github"}


def test_no_top_level_directory_is_unrecorded() -> None:
    """The Never-do: no top-level directory neither ADR names."""
    recorded = _directories_adr_0003_names() | _directories_adr_0007_names() | PREDATING

    unrecorded = _tracked_top_level_directories() - recorded
    assert not unrecorded, (
        f"top-level directories named by neither ADR-0003 nor ADR-0007: "
        f"{sorted(unrecorded)}. An application directory amends ADR-0003 with "
        "a superseding record; a platform- or tooling-mandated path amends "
        "ADR-0007 D1's table. Otherwise move the content."
    )


def test_every_directory_adr_0003_names_exists() -> None:
    """The record is narrowest-set, so an unused named directory is a defect."""
    missing = {
        name for name in _directories_adr_0003_names() if not (REPO_ROOT / name).is_dir()
    }
    assert not missing, f"ADR-0003 names directories that do not exist: {sorted(missing)}"


def test_the_package_has_the_five_layers_adr_0003_d3_names() -> None:
    package = REPO_ROOT / "src" / "ced"
    layers = {p.name for p in package.iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert {"domain", "agents", "adapters", "api", "worker"} <= layers
