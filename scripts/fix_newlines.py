#!/usr/bin/env python3
"""Measure or fix unwanted blank lines inside Markdown paragraphs.

OCR of the ONS information sheets often splits a single paragraph into several
"paragraphs" by inserting a blank line (a newline pair) mid-sentence. The
tell-tale sign of such an unwanted blank line is that the following line begins
with a lower-case letter: a real paragraph break is almost always followed by a
capital letter, a heading marker, a list bullet, etc. These breaks also tend to
come in runs, so a single file may contain dozens of them.

Usage:
    # Measure: report how many unwanted blank lines each file contains.
    scripts/fix_newlines.py jons/ONS_221.md jons/ONS_220.md

    # Fix: rejoin the split paragraphs, rewriting the files in place.
    scripts/fix_newlines.py --fix jons/*.md

    # Preview the fix without writing anything.
    scripts/fix_newlines.py --fix --dry-run jons/ONS_221.md
"""

import argparse
import re
import sys

# A blank line (one or more empty/whitespace-only lines) immediately followed by
# a line that starts with a lower-case letter. The lower-case letter is captured
# so the fix can rejoin the two paragraphs with a single newline.
UNWANTED = re.compile(r"\n[ \t]*(?:\n[ \t]*)+([a-z])")


def count(text):
    """Return the number of unwanted blank lines in *text*."""
    return len(UNWANTED.findall(text))


def fix(text):
    """Rejoin paragraphs split by unwanted blank lines.

    Each unwanted blank line is replaced by a single newline so the broken
    sentence reads continuously again.
    """
    return UNWANTED.sub(r"\n\1", text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", metavar="FILE", nargs="+",
                        help="Markdown files to measure or fix")
    parser.add_argument("--fix", action="store_true",
                        help="rejoin split paragraphs (default is to measure only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --fix, report changes without writing files")
    args = parser.parse_args(argv)

    total = 0
    changed = 0
    for path in args.files:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"{path}: {e}", file=sys.stderr)
            continue

        n = count(text)
        total += n

        if args.fix:
            if n and not args.dry_run:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(fix(text))
            if n:
                changed += 1
            verb = "would join" if args.dry_run else "joined"
            print(f"{path}: {verb} {n}")
        else:
            print(f"{path}: {n}")

    label = "files affected" if args.fix else "unwanted blank lines"
    print(f"total: {total}" + (f" in {changed} files" if args.fix else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
