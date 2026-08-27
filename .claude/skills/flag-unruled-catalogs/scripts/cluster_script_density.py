#!/usr/bin/env python3
"""Distinguish an isolated foreign-script legend from a sustained, unruled
catalog table in a `jons/` Markdown file, by clustering the same raw
foreign-script line hits `transcribe-foreign-script screen` reports.

Why this exists: on IS_005, `transcribe-foreign-script screen` correctly
found 80 raw foreign-script line hits between md lines 442 and 701 -- but
that skill's Tier 2 (render one page, spawn one Opus call per legend,
require it to corroborate against an adjacent gloss) is built for the IS_004
shape: a handful of short, independently-corroborable legends. It is the
wrong tool for 80 hits that turn out to be one continuous, column-typed
catalog table with no ruled borders (so `detect-missing-tables` never saw it
either) and mostly no per-cell gloss to corroborate against.

This script does NOT attempt to detect table rows or columns -- two
different geometric approaches were tried and both failed on this corpus's
multi-line, sparsely-populated table rows (see this skill's SKILL.md). It
only answers the cheaper, more honest question: is a foreign-script region
isolated (hand it to `transcribe-foreign-script` as-is) or sustained (stop --
this needs a human to read the render and reconstruct the table by hand,
the same judgment call `detect-missing-tables` makes for its hardest cases)?

Usage:
    cluster_script_density.py screen IS_005 [IS_004 ...]

Requires no dependencies beyond the standard library -- it only reads the
Markdown, not the PDF. Use `transcribe-foreign-script`'s `locate`/`render`
subcommands to look at a flagged region once one is found here.
"""
import argparse
import pathlib
import re
import sys

MD_DIR = pathlib.Path(__file__).resolve().parents[4] / "jons"

# Same script blocks as transcribe-foreign-script's detector, duplicated
# rather than imported -- these skills are meant to stand alone.
SCRIPT_BLOCKS = {
    "Arabic": "؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿",
    "Hebrew": "֐-׿",
    "Devanagari": "ऀ-ॿ",
    "CJK": "一-鿿㐀-䶿",
}
FOREIGN_RE = re.compile("[" + "".join(SCRIPT_BLOCKS.values()) + "]+")
MARKER_RE = re.compile(r"<!--\s*script-(ok|deferred|guess)\b")
MIN_CHARS = 2

CATALOG_THRESHOLD = 5  # hits at or above this size in one cluster -> CATALOG, not a per-line job


def resolve(stem):
    return MD_DIR / f"{stem}.md"


def raw_hit_lines(lines):
    """0-based line indices with a foreign-script run outside any HTML
    comment, excluding lines already covered by an adjacent script-ok/
    script-deferred/script-guess marker. Mirrors transcribe-foreign-script's
    RAW pass, including its table-block extension: a marker right after a
    reconstructed table resolves every row in it, not just the last one."""
    hits = []
    resolved = set()
    prev_content_idx = None
    in_code = False
    # See transcribe-foreign-script's detect_script_garble.py for why there
    # are two of these: table_block is the actively-building run (a genuine
    # gap ends it); last_table_block survives exactly the blank line GitHub's
    # renderer wants between a table and a following comment, so a marker
    # separated from its table by one still resolves every row in it.
    table_block = []
    last_table_block = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if table_block:
                last_table_block = table_block
                table_block = []
            continue
        if stripped.startswith("```"):
            in_code = not in_code
            prev_content_idx = i
            table_block = []
            last_table_block = []
            continue
        m = MARKER_RE.search(line)
        if m:
            if prev_content_idx is not None:
                if table_block and table_block[-1] == prev_content_idx:
                    resolved.update(table_block)
                elif last_table_block and last_table_block[-1] == prev_content_idx:
                    resolved.update(last_table_block)
                else:
                    resolved.add(prev_content_idx)
            continue
        is_table_row = stripped.startswith("|")
        if is_table_row and table_block and table_block[-1] == prev_content_idx:
            table_block.append(i)
        elif is_table_row:
            table_block = [i]
        else:
            table_block = []
            last_table_block = []
        if not in_code:
            visible = re.sub(r"<!--.*?-->", "", line)
            for run in FOREIGN_RE.findall(visible):
                if len(run) >= MIN_CHARS:
                    hits.append(i)
                    break
        prev_content_idx = i
    return [i for i in hits if i not in resolved]


def cluster(hits, gap):
    """Group hit line indices into runs where consecutive hits are within
    `gap` lines of each other."""
    if not hits:
        return []
    groups = [[hits[0]]]
    for h in hits[1:]:
        if h - groups[-1][-1] <= gap:
            groups[-1].append(h)
        else:
            groups.append([h])
    return groups


def cmd_screen(args):
    needs_attention = False
    for stem in args.stems:
        md_path = resolve(stem)
        if not md_path.exists():
            print(f"{stem}: no Markdown at {md_path}")
            continue
        lines = md_path.read_text(encoding="utf-8").splitlines()
        hits = raw_hit_lines(lines)
        groups = cluster(hits, args.gap)
        isolated = [g for g in groups if len(g) < CATALOG_THRESHOLD]
        catalogs = [g for g in groups if len(g) >= CATALOG_THRESHOLD]
        if catalogs:
            needs_attention = True
        status = "nothing outstanding" if not groups else (
            f"{len(catalogs)} catalog cluster(s), {len(isolated)} isolated" if catalogs
            else f"{len(isolated)} isolated (fine for transcribe-foreign-script as-is)"
        )
        print(f"{stem}: {len(hits)} raw hit(s) in {len(groups)} cluster(s) -- {status}")
        for g in catalogs:
            print(f"  CATALOG   md lines {g[0]+1}-{g[-1]+1}  ({len(g)} hits) "
                  f"-- likely an unruled table; render and reconstruct by hand, "
                  f"do not run transcribe-foreign-script Tier 2 line-by-line on this")
        if args.verbose:
            for g in isolated:
                span = f"line {g[0]+1}" if len(g) == 1 else f"lines {g[0]+1}-{g[-1]+1}"
                print(f"  isolated  {span}  ({len(g)} hit(s))")
    sys.exit(1 if needs_attention else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("screen")
    p.add_argument("stems", nargs="+")
    p.add_argument("--gap", type=int, default=12,
                    help="max md lines between hits to merge into one cluster (default 12)")
    p.add_argument("-v", "--verbose", action="store_true", help="also list isolated clusters")
    p.set_defaults(func=cmd_screen)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
