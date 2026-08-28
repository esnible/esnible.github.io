#!/usr/bin/env python3
"""Mechanical structure lint for a `jons/` Markdown file after a
restructure-flattened-md rebuild.

A large rewrite -- swapping flattened prose for fenced code blocks, pipe
tables, and `*[figure]*` placeholders -- introduces a predictable set of
mechanical defects that render wrong but are invisible in a diff:

  * a `#` heading with no blank line before or after it
  * a pipe table split in two by a stray blank line, or with no `|:--- |`
    separator row at all
  * an unbalanced ``` fence (everything after it renders as code)
  * a `*[figure]*` placeholder that lost its `<!-- figure ... -->` comment
  * a `\\|` left in a non-table line (the fingerprint detect-missing-tables
    screens for -- the rebuild was supposed to remove it)
  * a stray Arabic / Devanagari glyph left in an English prose line

This does NOT check that the reconstruction is *correct* -- only that it is
well-formed Markdown. Correctness is an eyeball-the-render job.

Usage:
    lint_structure.py jons/IS_009.md
    lint_structure.py IS_009            # resolves to jons/IS_009.md

Exit status is 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""

import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^\s*```")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}")  # a pipe-table separator row
FOREIGN_RE = re.compile(
    "[؀-ۿݐ-ݿऀ-ॿ"
    "ﭐ-﷿ﹰ-﻿‎‏]"
)


def is_table_row(line):
    return line.lstrip().startswith("|")


def is_sep_row(line):
    body = line.strip().strip("|")
    return bool(body) and set(body) <= set(" :-|")


def lint(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    findings = []  # (line_no, severity, message)

    def add(n, sev, msg):
        findings.append((n, sev, msg))

    # --- fences -------------------------------------------------------------
    fence_lines = [i for i, l in enumerate(lines) if FENCE_RE.match(l)]
    if len(fence_lines) % 2:
        add(fence_lines[-1] + 1, "ERROR",
            "odd number of ``` fences -- unbalanced code block")
    in_fence = False
    fence_state = []  # per-line: True when inside a fenced block
    for i, l in enumerate(lines):
        if FENCE_RE.match(l):
            in_fence = not in_fence
            fence_state.append(in_fence or True)  # the fence line itself
        else:
            fence_state.append(in_fence)

    def blank(i):
        return i < 0 or i >= len(lines) or lines[i].strip() == ""

    # --- headings ---------------------------------------------------------
    for i, l in enumerate(lines):
        if fence_state[i] or not HEADING_RE.match(l):
            continue
        if i > 0 and not blank(i - 1):
            add(i + 1, "ERROR",
                f"heading has no blank line before it: {l.strip()[:60]!r}")
        if not blank(i + 1):
            add(i + 1, "ERROR",
                f"heading has no blank line after it: {l.strip()[:60]!r}")

    # --- pipe tables ----------------------------------------------------
    i = 0
    while i < len(lines):
        if fence_state[i] or not is_table_row(lines[i]):
            i += 1
            continue
        start = i
        while i < len(lines) and is_table_row(lines[i]):
            i += 1
        block = lines[start:i]
        has_sep = any(is_sep_row(b) for b in block)
        if len(block) >= 2 and not has_sep:
            add(start + 1, "ERROR",
                "pipe table has no `|:--- |` separator row")
        # blank line splitting a table: the group after the blank is a bare
        # run of rows with no separator of its own -> an orphaned continuation,
        # not a legitimately new table
        if i < len(lines) and blank(i):
            j = i + 1
            nxt = []
            while j < len(lines) and is_table_row(lines[j]):
                nxt.append(lines[j])
                j += 1
            if nxt and not any(is_sep_row(x) for x in nxt):
                add(i + 1, "ERROR",
                    "blank line splits a pipe table (rows after it have no "
                    "separator of their own)")

    # --- figure placeholders ------------------------------------------
    for i, l in enumerate(lines):
        if "*[figure]*" in l and "<!-- figure" not in l:
            add(i + 1, "WARN",
                "*[figure]* with no companion <!-- figure ... --> comment")

    # --- escaped pipes outside tables --------------------------------
    for i, l in enumerate(lines):
        if fence_state[i]:
            continue
        if "\\|" in l and not is_table_row(l):
            add(i + 1, "ERROR",
                f"\\| in a non-table line -- flattened residue: {l.strip()[:70]!r}")

    # --- stray foreign-script glyphs in English prose ---------------
    # HTML comments legitimately carry transcribed script (transcribe-foreign-
    # script's script-ok / script-guess markers); skip them.
    for i, l in enumerate(lines):
        if fence_state[i] or is_table_row(l) or l.lstrip().startswith("<!--"):
            continue
        if re.search(r"script-(ok|guess|deferred)|<!--\s*OCR", l):
            continue
        if FOREIGN_RE.search(l) and len(re.findall(r"[A-Za-z]", l)) >= 25:
            add(i + 1, "WARN",
                f"non-Latin glyph in an English prose line: {l.strip()[:70]!r}")

    return findings


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    arg = argv[1]
    path = Path(arg)
    if not path.exists() and "/" not in arg and not arg.endswith(".md"):
        path = Path("jons") / f"{arg}.md"
    if not path.exists():
        print(f"no such file: {path}")
        return 2

    findings = lint(path)
    if not findings:
        print(f"{path}: clean")
        return 0

    findings.sort()
    errs = sum(1 for _, s, _ in findings if s == "ERROR")
    warns = len(findings) - errs
    for n, sev, msg in findings:
        print(f"{path}:{n}: {sev}  {msg}")
    print(f"-- {errs} error(s), {warns} warning(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
