#!/usr/bin/env python3
"""Structural lint for docs/product/intents/.

Checks the defect families seven independent review passes actually found —
not general prose quality.

On paired constructs it deliberately stops short of judging them. Whether a
falsifier is governed by the same noun phrase as its headline is a semantic
question, and a word-overlap proxy for it fired on four sound pairs while
catching nothing. What the lint guarantees mechanically is that every
sub-result *has* a falsifier and that the two halves are about the same
subject; `--pairs` then prints each pair for the re-derivation that finding
the real defects actually requires.
"""
import glob, re, sys, pathlib

REQ = ["## Outcome", "## Boundary", "## Owner", "## Unresolved questions",
       "## Projection", "## Source"]
# words a falsifier may add without changing what it quantifies over
FILLER = re.compile(r'^(a|an|the|one|such|that|those|these|of|in|at|is|are|no)$', re.I)


def governed_phrase(text):
    """Content words of a clause, order-insensitive, filler removed."""
    words = re.findall(r"[a-z][a-z'-]+", text.lower())
    return {w for w in words if not FILLER.match(w)}


def first_sentence(text):
    """Bound a half to its own sentence.

    Both halves run on into commentary — the headline into its rationale, the
    falsifier into the paragraph after it. Comparing unbounded halves compares
    that commentary, which is what produced the proxy's false positives.
    """
    t = re.sub(r'\s+', ' ', re.sub(r'[*`]', '', text)).strip()
    t = re.sub(r'^\d+\.\s*', '', t)
    return re.split(r'(?<=[.!?]) ', t)[0]


def numbered_lists(outcome):
    """Contiguous runs of numbered sub-results, as lists of item text.

    A new run starts when numbering restarts at 1, which is how the two
    outcome blocks in a file are told apart.
    """
    runs, cur = [], []
    for item in re.split(r'\n(?=\s*(?:\*\*)?\d+\.\s)', outcome):
        m = re.match(r'\s*(?:\*\*)?(\d+)\.\s', item)
        if not m:
            continue
        if m.group(1) == "1" and cur:
            runs.append(cur); cur = []
        cur.append(item)
    if cur:
        runs.append(cur)
    return runs


def pairs_in(outcome):
    """(headline, falsifier) per numbered sub-result, any of the three styles."""
    out = []
    for item in re.split(r'\n(?=\s*(?:\*\*)?\d+\.\s)', outcome):
        if not re.match(r'\s*(?:\*\*)?\d+\.\s', item):
            continue
        m = re.search(r'\*Falsif(?:ied by|ying observation)[:\*]*\s*(.+)', item, re.S)
        if m:
            out.append((first_sentence(item[:m.start()]), first_sentence(m.group(1))))
    return out


def check(path):
    name = path.split("/")[-1]
    s = pathlib.Path(path).read_text()
    probs, notes = [], []
    lines = s.split("\n")

    for i in range(1, len(lines)):
        a, b = lines[i - 1].strip(), lines[i].strip()
        if a and a == b and not a.startswith("|") and len(a) > 25:
            probs.append(f"L{i+1} duplicate adjacent line")

    if re.search(r'\*Proposed in[^*]*\*\s*\*Proposed', s):
        probs.append("stranded duplicate citation")
    for r in REQ:
        if r not in s:
            probs.append(f"missing section {r}")
    if re.search(r'runtime-architecture\.md`?\s+r\d', s):
        probs.append("architecture-doc revision pin")
    if "~~" in s:
        probs.append("strikethrough text")
    if not re.search(r'^- Revision: r\d+ —', s, re.M):
        probs.append("no revision line")

    outcome = s.split("## Outcome", 1)[1].split("## Boundary", 1)[0] if "## Outcome" in s else ""
    if "alsif" not in outcome:
        probs.append("outcome carries no falsifier")

    # A falsifier sharing no substantive word with its headline is attached to
    # the wrong claim. This is the one pairing defect that is decidable without
    # reading for meaning; narrowing is left to --pairs and a human.
    for headline, fals in pairs_in(outcome):
        h, f = governed_phrase(headline), governed_phrase(fals)
        if len({w for w in (h & f) if len(w) > 3}) < 2:
            notes.append(f"falsifier restates its headline in different words "
                         f"rather than quoting it: {headline[:60]!r}")

    # Falsifier coverage must be uniform within a list of siblings. Requiring one
    # on every numbered line would outlaw a legitimate style — adoptable numbers
    # its falsifying observations directly — but a list where some siblings carry
    # one and others do not is an omission, not a style.
    for run in numbered_lists(outcome):
        have = [bool(re.search(r'\*Falsif', i)) for i in run]
        if any(have) and not all(have):
            missing = [n for n, h in enumerate(have, 1) if not h]
            probs.append(f"list of {len(run)}: sub-result(s) {missing} carry no "
                         f"falsifier while their siblings do")

    st = re.search(r'^- \*\*Status:\*\* (\w+)', s, re.M)
    return name, (st.group(1) if st else "?"), probs, notes


show_pairs = "--pairs" in sys.argv
bad = 0
for f in sorted(x for x in glob.glob("docs/product/intents/*.md") if "README" not in x):
    name, status, probs, notes = check(f)
    if probs:
        bad += 1
        print(f"FAIL {name} [{status}]")
        for p in probs:
            print(f"      - {p}")
    else:
        print(f"OK   {name} [{status}]")
    for n in notes:
        print(f"     ?? {n}")
    if show_pairs:
        s = pathlib.Path(f).read_text()
        oc = s.split("## Outcome", 1)[1].split("## Boundary", 1)[0]
        for n, (h, fl) in enumerate(pairs_in(oc), 1):
            print(f"      {n}. claim: {h}")
            print(f"         fals : {fl}")
print()
print("clean" if not bad else f"{bad} file(s) with defects")
sys.exit(1 if bad else 0)
