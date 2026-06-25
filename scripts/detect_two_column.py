#!/usr/bin/env python3
"""Detect Markdown files where OCR flattened a two-column page layout.

**NOTE** We don't actually use this; none of the OCRed files had this issue.

When a PDF page is laid out in two columns and the OCR engine fails to
recognise the column structure, it reads *across* the page, left to right,
weaving the left- and right-column lines together. Each output line then looks
like

    left-column fragment        right-column fragment

and the prose is scrambled: the second half of every line belongs to a
different sentence than the first half.

The tell-tale signature is the *gutter*, the blank channel between the two
columns. It survives OCR as a run of several spaces, and -- crucially -- it
lands at roughly the same character offset on line after line, forming a
vertical "river" of whitespace. Sporadic gaps (aligned figure captions, table
padding, a stray double space) do not line up vertically, so requiring the gap
to recur at a consistent column across several consecutive lines is what
separates a real two-column gutter from ordinary OCR spacing noise.

Because the detector relies on line structure, run it on the *raw* pdfmd output
-- before scripts/fix_newlines.py joins paragraphs into single long lines. Once
the line breaks are gone the columns can no longer be told apart, so this makes
a good QA gate to run right after OCR (see scripts/build.sh) to catch pages
that need re-OCRing with explicit column handling.

Usage:
    # Report a two-column score for each file.
    scripts/detect_two_column.py jons/ONS_221.md jons/*.md

    # Show the offending line ranges so you can eyeball them.
    scripts/detect_two_column.py --show jons/ONS_221.md

    # Only print files that look two-column (handy for scripting / CI).
    scripts/detect_two_column.py --quiet jons/*.md && echo "all clear"
"""

import argparse
import re
import sys

# A run of GAP_SPACES or more spaces that is not at the very start of the line
# (leading indentation is not a column gutter). Each match's span gives the
# character columns the gap occupies.
GAP_SPACES = 3

# A gutter on two consecutive lines is considered "the same river" when their
# gaps overlap, allowing this much horizontal drift (proportional spacing and
# OCR jitter shift the gutter a few characters line to line).
ALIGN_TOLERANCE = 4

# A run of this many consecutive aligned-gap lines is reported as a two-column
# region. Real columns persist for many lines; incidental gaps do not.
MIN_RUN = 4

_gap = re.compile(r"\S( {%d,})" % GAP_SPACES)


def _gaps(line):
    """Yield (start, end) character spans of interior whitespace gaps."""
    for m in _gap.finditer(line):
        yield m.start(1), m.end(1)


def _overlaps(a, b):
    """True if spans *a* and *b* overlap within ALIGN_TOLERANCE."""
    return a[0] - ALIGN_TOLERANCE < b[1] and b[0] - ALIGN_TOLERANCE < a[1]


def regions(text):
    """Return a list of (start_line, end_line) 1-based two-column line ranges.

    A region is a maximal run of consecutive lines that each contain a
    whitespace gap vertically aligned with the run's gutter.
    """
    lines = text.splitlines()
    out = []
    run_start = None        # 1-based line number where the current run began
    run_span = None         # the running gutter span the river occupies

    for i, line in enumerate(lines, start=1):
        # The gap on this line that best continues the current river, if any.
        match = None
        for span in _gaps(line):
            if run_span is None or _overlaps(span, run_span):
                match = span
                break

        if match is not None:
            if run_start is None:
                run_start = i
            run_span = match
        else:
            if run_start is not None and i - run_start >= MIN_RUN:
                out.append((run_start, i - 1))
            run_start = None
            run_span = None

    if run_start is not None and len(lines) + 1 - run_start >= MIN_RUN:
        out.append((run_start, len(lines)))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", metavar="FILE", nargs="+",
                        help="Markdown files to scan")
    parser.add_argument("--show", action="store_true",
                        help="print the flagged line ranges for each file")
    parser.add_argument("--quiet", action="store_true",
                        help="only print files that look two-column; "
                             "exit non-zero if any are found")
    args = parser.parse_args(argv)

    total_flagged = 0
    for path in args.files:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"{path}: {e}", file=sys.stderr)
            continue

        regs = regions(text)
        flagged = sum(end - start + 1 for start, end in regs)
        if flagged:
            total_flagged += 1

        if args.quiet:
            if regs:
                print(path)
        else:
            print(f"{path}: {len(regs)} region(s), {flagged} line(s)")
            if args.show:
                for start, end in regs:
                    print(f"    lines {start}-{end}")

    if not args.quiet:
        print(f"total: {total_flagged} file(s) look two-column")
    return 1 if (args.quiet and total_flagged) else 0


if __name__ == "__main__":
    sys.exit(main())
