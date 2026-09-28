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
  * a column dump -- a borderless table OCR'd one column at a time, so a
    line repeats one word (`Cairo Cairo Cairo`) or runs bare numbers
    (`841-842 842-857 857-865 865-872`)
  * graph-axis residue -- a line graph's tick labels OCR'd as text
    (`1,70- 1,60- 1,50 1,40'`, `1550' 1590' '1710`), often glued onto the
    end of the paragraph before the graph
  * a line starting `#` with no space after it (`#076 and #077 ...`) --
    kramdown renders it as a heading; escape it as `\\#076`
  * an ordered list that starts at a number other than 1 (`16.  Sel. ...`)
    with no `{: start="16"}` before or after it -- kramdown ignores the first
    item's number and renders the list from 1
  * a near-duplicate paragraph -- a pipe-mangled copy of the prose next to
    it, left behind when a spurious table was turned back into paragraphs

This does NOT check that the reconstruction is *correct* -- only that it is
well-formed Markdown. Correctness is an eyeball-the-render job.

Usage:
    lint_structure.py jons/IS_009.md
    lint_structure.py IS_009            # resolves to jons/IS_009.md

Exit status is 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^\s*```")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
BARE_HASH_RE = re.compile(r"^\s{0,3}#+[^#\s]")  # kramdown needs no space after `#`
OL_ITEM_RE = re.compile(r"^\s{0,3}(\d{1,9})[.)]\s")  # an ordered-list item
START_IAL_RE = re.compile(r"^\s*\{:.*\bstart=")      # {: start="N"} after a list
SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}")  # a pipe-table separator row
FOREIGN_RE = re.compile(
    "[؀-ۿݐ-ݿऀ-ॿ"
    "ﭐ-﷿ﹰ-﻿‎‏]"
)


# The same token three times running: `Cairo Cairo Cairo`, `3a 3a 3a`, or a
# run of ditto marks `" " "`. The token needs two letters/digits (or is a
# ditto mark) -- `* * *`, `- - -` and `D D D` are separators and OCR specks.
REPEAT_RE = re.compile(r'(?<!\S)("|[^\s*_#]*[A-Za-z0-9][^\s*_#]*[A-Za-z0-9][^\s*_#]*)(?:\s+\1){2,}(?!\S)')
# Four or more bare numbers of 2+ digits, or ranges, in a row:
# `801-815 815-824 825-841 841-842`.
NUMRUN_RE = re.compile(r"(?<!\S)(?:\d{2,4}(?:-\d{1,4})?\s+){3,}\d{2,4}(?:-\d{1,4})?(?!\S)")


# A number carrying graph-axis residue: a tick mark or an OCR'd tick glyph
# before or after it (`1,70-`, `1520'`, `-1520'`, `»1560'`, `16^C3`,
# `'1710`), or a two-place decimal comma (`1,50`, `0,90`) as continental
# axes print it.
TICK_TOK_RE = re.compile(r"^[-»«*'^\\]*\d[\d^]*(?:,\d\d)?[-'’^*\\]*[A-Z]?\d?$")


def is_tick(tok):
    if not TICK_TOK_RE.match(tok):
        return False
    core = re.sub(r"[^\d,]", "", tok)
    return bool(re.fullmatch(r"\d,\d\d", core)) or bool(re.search(r"[-'’^*»\\]", tok))


def axis_ticks(line, need=5, window=8):
    """The first run of `need` tick-like tokens within `window` tokens, or None."""
    toks = line.split()
    flags = [is_tick(t) for t in toks]
    for k in range(len(toks)):
        if flags[k] and sum(flags[k:k + window]) >= need:
            return " ".join(toks[k:k + window])
    return None


def shingles(text, n=6):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(words[k:k + n]) for k in range(len(words) - n + 1)}


def paragraphs(lines, skip):
    """(first line index, text) for each run of non-blank lines, ignoring
    comment-only lines and lines where skip[i] is set (fenced code)."""
    out, start, buf = [], None, []
    for i, l in enumerate(lines + [""]):
        if l.strip() and not skip[i] and not l.lstrip().startswith("<!--"):
            if start is None:
                start = i
            buf.append(l)
        elif start is not None:
            out.append((start, " ".join(buf)))
            start, buf = None, []
    return out


def kramdown_list_mismatches(path):
    """[(line_no, printed)] for list items kramdown renders with another number."""
    script = Path(__file__).resolve().parents[4] / "scripts" / "fix_list_starts.rb"
    if not (shutil.which("ruby") and script.exists()):
        return regex_list_starts(path)
    out = subprocess.run(["ruby", str(script), str(path)], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        if " at line(s) " in line:
            for m in re.finditer(r"(\d+) \((\d+)", line.split(" at line(s) ", 1)[1]):
                found.append((int(m.group(1)), int(m.group(2))))
    return found


def regex_list_starts(path):
    """Fallback without Ruby: a list whose first item isn't 1 and has no IAL."""
    lines = path.read_text(encoding="utf-8").split("\n")
    found, i = [], 0
    while i < len(lines):
        m = OL_ITEM_RE.match(lines[i])
        if not m:
            i += 1
            continue
        start = last = i
        for j in range(i + 1, len(lines)):
            if OL_ITEM_RE.match(lines[j]) or lines[j].startswith((" ", "\t")):
                last = j
            elif lines[j].strip():
                break
        n = int(m.group(1))
        if n != 1 and not (start and START_IAL_RE.match(lines[start - 1])):
            found.append((start + 1, n))
        i = last + 1
    return found


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

    # --- `#` with no space: kramdown still renders a heading --------------
    for i, l in enumerate(lines):
        if not fence_state[i] and BARE_HASH_RE.match(l):
            add(i + 1, "ERROR",
                f"line starts with `#` and no space -- kramdown renders it as a "
                f"heading; escape as `\\#` or remove the garble: {l.strip()[:50]!r}")

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

    # --- column dumps: a borderless table read one column at a time ------
    # No `\|` fingerprint and no ruling for detect-missing-tables to find, so
    # nothing else catches it. IS_020's catalogue came out as lines like
    # `Mint Cairo Cairo Damascus Aleppo Cairo Cairo` and
    # `Reign 841-842 842-857 857-865 865-872 872-901`.
    for i, l in enumerate(lines):
        if fence_state[i] or is_table_row(l) or l.lstrip().startswith("<!--"):
            continue
        m = REPEAT_RE.search(l) or NUMRUN_RE.search(l)
        if m:
            add(i + 1, "WARN",
                f"column dump (table read one column at a time?): {m.group(0).strip()[:50]!r}")

    # --- graph-axis residue -----------------------------------------------
    # A line graph on a scanned page has no vector drawing for anything to
    # detect; pdfmd just OCRs its tick labels, legend and data labels into
    # text. OP_015's four graphs came out as `... useful results.** **\[**
    # --- 1,70- 1,60- 1,50 1,40' ...` and `1550' 1590' \*1670 '1710 '1850`.
    for i, l in enumerate(lines):
        if fence_state[i] or is_table_row(l) or l.lstrip().startswith("<!--"):
            continue
        m = axis_ticks(l)
        if m:
            add(i + 1, "WARN",
                f"graph axis labels (a figure OCR'd as text?): {m[:50]!r}")

    # --- ordered-list items kramdown renders with the wrong number -------
    # kramdown ignores list numbers and counts from 1, so IS_009's catalogue
    # `16.  Sel. ...` came out as `1.`, a note after an unindented paragraph
    # restarts at 1, and a list that skips numbers carries on regardless.
    # Where a list starts and ends is kramdown's call (lazy continuation
    # lines, indented paragraphs), so ask kramdown: scripts/fix_list_starts.rb
    # reports every item that renders with a number other than the printed
    # one, and --fix repairs them. Without Ruby, fall back to a regex guess
    # at list starts, which misreads some lists.
    for line_no, n in kramdown_list_mismatches(path):
        add(line_no, "WARN",
            f"list item {n} renders with a different number in kramdown -- "
            f"run scripts/fix_list_starts.rb --fix, or escape as `{n}\\.`")

    # --- near-duplicate paragraphs --------------------------------------
    # Turning a spurious pdfmd table back into prose can leave the table's
    # text behind as a pipe-mangled copy next to the clean paragraphs (ONS_148
    # kept one through two passes). Compare each paragraph with the next few.
    # Exactly one of the pair carries pipes -- that is the mangled copy;
    # without the pipe test, formulaic catalogue entries match each other.
    paras = [(i, shingles(t), "|" in t) for i, t in paragraphs(lines, fence_state)]
    for k, (i, a, pa) in enumerate(paras):
        if len(a) < 30:
            continue
        for j, b, pb in paras[k + 1:k + 5]:
            if pa != pb and len(b) >= 30 and len(a & b) >= 0.8 * min(len(a), len(b)):
                add(i + 1, "WARN",
                    f"near-duplicate of the paragraph at line {j + 1} -- "
                    f"leftover copy from a rebuilt table?")
                break

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
