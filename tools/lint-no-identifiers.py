#!/usr/bin/env python3
"""Refuse to let account-identifying or private data reach repository history.

This repository is public. Cloud identifiers, principal IDs and personal
addresses are not secrets in the credential sense — they cannot be used to
authenticate — but they name a real account and a real person, and once pushed
they are permanently in history whatever a later commit does.

Scans tracked files only. Vendored pack directories are skipped: they are
upstream content this project does not author, and they legitimately carry
templated examples like `arn:aws:iam::${var.account_id}:policy/...`.

Usage:  python3 tools/lint-no-identifiers.py [--staged]
Exit 1 on any finding.
"""
import re
import subprocess
import sys

SKIP_PREFIXES = (".claude/", ".agents/", ".codex/")
SKIP_SUFFIXES = (".lock",)

# Each rule is (label, compiled pattern, allowance predicate or None).
RULES = [
    ("AWS account id",
     re.compile(r"(?<![\w.-])\d{12}(?![\w.-])"),
     None),
    ("AWS ARN with a literal account id",
     re.compile(r"arn:aws[a-z-]*:[^:\s]*:[^:\s]*:\d{12}:"),
     None),
    ("AWS access key id",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
     None),
    ("AWS principal id",
     re.compile(r"\b(?:AROA|AIDA|AGPA|AIPA|ANPA|ANVA)[0-9A-Z]{16,}\b"),
     None),
    ("email address",
     re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
     # RFC 2606 reserves example.com/.org/.net for documentation, and the
     # noreply address is this project's own commit identity.
     lambda m: m.group(0).endswith("@users.noreply.github.com")
     or re.search(r"@(?:[\w-]+\.)?example\.(?:com|org|net)$", m.group(0))),
    ("private key block",
     re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
     None),
]

# Terraform state and variable files carry resolved identifiers by construction.
FORBIDDEN_PATHS = re.compile(r"(\.tfstate(\.backup)?$|\.tfvars$|(^|/)\.terraform/)")


def tracked_files(staged):
    cmd = (["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
           if staged else ["git", "ls-files"])
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p]


def main():
    staged = "--staged" in sys.argv
    findings = []

    for path in tracked_files(staged):
        if path.startswith(SKIP_PREFIXES) or path.endswith(SKIP_SUFFIXES):
            continue
        if FORBIDDEN_PATHS.search(path):
            findings.append(f"{path}: file type carries resolved identifiers; do not track it")
            continue
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except (OSError, IsADirectoryError):
            continue
        for label, pattern, allowed in RULES:
            for m in pattern.finditer(text):
                if allowed and allowed(m):
                    continue
                line = text[:m.start()].count("\n") + 1
                findings.append(f"{path}:{line}: {label} — {m.group(0)[:48]!r}")

    if findings:
        print("REFUSED — identifying data must not enter repository history:\n")
        for f in findings:
            print(f"  {f}")
        print(f"\n{len(findings)} finding(s). Redact or untrack before committing.")
        return 1

    scope = "staged" if staged else "tracked"
    print(f"clean — no identifying data in {scope} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
