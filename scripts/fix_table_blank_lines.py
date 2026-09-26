#!/usr/bin/env python3
"""Measure or fix pipe tables that touch a non-blank line.

The site is built by Jekyll with kramdown, which only starts a table after a
blank line. A caption, paragraph or `<!-- ... -->` comment directly above a
table swallows it into that paragraph, and a comment directly below one does
the same -- the table renders as a run of `|`-separated text. GitHub's own
Markdown preview does not have this problem, so it goes unnoticed there.

Fenced code blocks are left alone: a genealogy drawn with `|` connectors is
not a table.

Usage:
    # Measure: report how many table edges touch a non-blank line.
    scripts/fix_table_blank_lines.py jons/ONS_140.md

    # Fix: insert a blank line at each such edge, rewriting the files in place.
    scripts/fix_table_blank_lines.py --fix jons/*.md

    # Preview the fix without writing anything.
    scripts/fix_table_blank_lines.py --fix --dry-run jons/ONS_140.md

Check the rendered result with scripts/check_tables.rb.
"""

import argparse
import sys


def is_fence(line):
    return line.lstrip().startswith("```")


def is_table_row(line):
    return line.startswith("|")


def edges(lines):
    """Yield indexes i where a blank line belongs between lines[i-1] and lines[i]."""
    in_fence = False
    for i, line in enumerate(lines):
        if is_fence(line):
            in_fence = not in_fence
        if in_fence or i == 0:
            continue
        prev = lines[i - 1]
        if is_fence(prev) or not prev.strip() or not line.strip():
            continue
        if is_table_row(line) != is_table_row(prev):
            yield i


def fix(text):
    lines = text.split("\n")
    for i in reversed(list(edges(lines))):
        lines.insert(i, "")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--fix", action="store_true", help="insert the blank lines in place")
    ap.add_argument("--dry-run", action="store_true", help="with --fix, report but do not write")
    args = ap.parse_args()

    total = 0
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        lines = text.split("\n")
        found = list(edges(lines))
        if not found:
            continue
        total += len(found)
        print(f"{path}: {len(found)} table edge(s) touching text, at line(s) "
              + ", ".join(str(i + 1) for i in found))
        if args.fix and not args.dry_run:
            with open(path, "w", encoding="utf-8") as f:
                f.write(fix(text))
    print(f"total: {total}")
    sys.exit(1 if total and not (args.fix and not args.dry_run) else 0)


if __name__ == "__main__":
    main()
