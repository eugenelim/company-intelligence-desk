"""AC-0008 — the identifier lint catches an embedded account id and only that.

`tools/lint-no-identifiers.py` scans files git knows about, so these tests give
it a throwaway git repository of its own and run the real script as a
subprocess against it. Exercising the script's exit code rather than importing
its regex is the point: the gate is the command, and a passing regex with a
broken file walk is a gate that never fires.

Both halves are needed. A pattern that catches an embedded account id and also
catches the twelve-digit run inside a content hash is not a gate either — it is
a reason to stop running the gate.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT = REPO_ROOT / "tools" / "lint-no-identifiers.py"

# ── Why every fixture below is assembled from fragments ──────────────────────
#
# `lint-no-identifiers.py` scans this file too, so a fixture written as one
# literal makes the gate refuse the commit that adds its own regression test.
# Joining fragments at run time means the repository text genuinely contains no
# twelve-digit identifier and no non-reserved address, which is exactly what the
# rule protects — the gate is not weakened, and nothing is added to its skip
# list. Do not "tidy" these back into literals; the commit will be refused.

#: Not a real account. What matters is the *shape*: twelve digits bounded by
#: `_` or `-` inside a larger identifier, which is what slipped through before
#: the pattern's boundary was fixed.
FAKE_ACCOUNT_ID = "9192" + "9394" + "9596"

#: A real sha256 — of b"13", the smallest input found by search whose digest
#: contains a twelve-digit run. That run is exactly the false positive the rule
#: must not make, and a digest without one would make the negative test
#: vacuous. `test_the_chosen_hash_...` below is the guard on that property.
#: The split falls *inside* the digit run, which is what keeps this line itself
#: from tripping the gate.
CONTENT_HASH = "3fdba35f04dc8c462986c992bcf87554" + "6257113072a909c162f7e470e581e278"


#: `(stage(name, content), run() -> CompletedProcess)` over a throwaway repo.
StagedRepo = tuple[
    Callable[[str, str], None],
    Callable[[], "subprocess.CompletedProcess[str]"],
]


@pytest.fixture
def staged_repo(tmp_path: Path) -> Iterator[StagedRepo]:
    """Return a writer that stages a file in a throwaway git repo."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    def _stage(name: str, content: str) -> None:
        (tmp_path / name).write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", name], cwd=tmp_path, check=True)

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(LINT), "--staged"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    yield _stage, _run


def _digit_run_of_twelve(text: str) -> str:
    """Return the first twelve-character all-digit substring, or ''.

    Guards the second half of AC-0008 against a silently vacuous assertion: if
    the chosen hash happened to contain no twelve-digit run, the negative test
    would pass while proving nothing.
    """
    for i in range(len(text) - 11):
        window = text[i : i + 12]
        if window.isdigit():
            return window
    return ""


def test_the_chosen_hash_really_contains_a_twelve_digit_run() -> None:
    """Setup check, reported separately because it cannot fail on the code."""
    assert _digit_run_of_twelve(CONTENT_HASH), (
        "the negative case needs a hash with a twelve-digit run inside it; "
        "pick a different hash"
    )


@pytest.mark.parametrize(
    "embedding",
    [
        "AWS_{id}_Admin",
        "acme-{id}-logs",
        "profile={id}",
        "s3://acme-{id}-artifacts/key",
        "arn:aws:iam::{id}:role/Example",
    ],
)
def test_an_embedded_account_id_is_refused(staged_repo: StagedRepo, embedding: str) -> None:
    """AC-0008, first half — the id is caught inside a larger identifier."""
    stage, run = staged_repo
    stage("config.txt", embedding.format(id=FAKE_ACCOUNT_ID) + "\n")

    result = run()

    assert result.returncode == 1, result.stdout
    assert "AWS account id" in result.stdout or "ARN" in result.stdout
    assert FAKE_ACCOUNT_ID in result.stdout


def test_a_twelve_digit_run_inside_a_content_hash_is_allowed(staged_repo: StagedRepo) -> None:
    """AC-0008, second half — the rule does not fire on a content hash."""
    stage, run = staged_repo
    stage(
        "manifest.json",
        f'{{"content_hash": "{CONTENT_HASH}"}}\n',
    )

    result = run()

    assert result.returncode == 0, result.stdout
    assert "clean" in result.stdout


def test_the_bare_example_tld_is_allowed(staged_repo: StagedRepo) -> None:
    """RFC 2606 reserves `.example`, and a bypass example needs to be writable.

    `https://www.sec.gov@attacker.example/` is the third allowlist bypass the
    r4 table omits. Its userinfo component parses as an email address, so a
    lint that refused the bare `.example` TLD would make the bypass
    undocumentable — which is how a known bypass stops being written down.
    """
    stage, run = staged_repo
    stage("notes.md", "Bypass: `https://www.sec.gov@attacker.example/`\n")

    result = run()

    assert result.returncode == 0, result.stdout


def test_a_real_looking_email_is_still_refused(staged_repo: StagedRepo) -> None:
    """The allowance is scoped to reserved domains, not to addresses at large."""
    stage, run = staged_repo
    address = "someone@" + "acme-corp" + ".net"
    stage("notes.md", f"Contact: {address}\n")

    result = run()

    assert result.returncode == 1, result.stdout
    assert "email address" in result.stdout
