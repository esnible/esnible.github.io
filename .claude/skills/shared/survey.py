#!/usr/bin/env python3
"""Count what each screen has to say about each file, once, and keep it.

Running a screen is not free: `detect_figures` rasterises every page,
`detect_tables` every page again, `detect_headings` once more to probe for
underlines. Running all of them over a file to discover that three have
nothing to say is the wrong way round -- on seven newsletters measured,
`detect_tables` found nothing in any of them, because bordered grids are a
journal's habit.

So the counting happens once, across the corpus, and the answer is kept in a
table. Picking the next file is then a `sort` of that table rather than
twenty minutes of rendering, and working a file means running only the
screens the table says have something on it.

    survey.py run --all                  # fill in what is missing, resumably
    survey.py run ONS_181 --refresh      # re-measure one file
    survey.py show --screen figures      # the worklist for one screen
    survey.py show --file ONS_181        # what is outstanding on one file

The table is `docs/screens.tsv`: one row per file and screen, with the count
a render has to settle, the count a batch can write by itself, and the date
it was measured. A screen's findings move when a file is repaired, so a row
is only as true as its date -- `--refresh` after working a file.
"""
import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / ".claude" / "skills"
MD_DIR = ROOT / "jons"
TABLE = ROOT / "docs" / "screens.tsv"
PDF_DIR = Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()
FIELDS = ("file", "screen", "rows", "batch", "measured")

# Each screen: the command that writes `crop_sheets.py` rows for it, and the
# command (if any) that writes an `apply_edits.py` batch instead.
SCREENS = {
    "quotes": {
        "rows": ["fix-ocr/scripts/detect_quote_pairs.py", "rows", "@md"],
        "batch": ["fix-ocr/scripts/detect_quote_pairs.py", "ordinals", "@md"],
    },
    "headings": {
        "rows": ["restore-headings/scripts/detect_headings.py", "rows", "@stem"],
    },
    "tables": {
        "rows": ["detect-missing-tables/scripts/detect_tables.py", "rows", "@stem"],
    },
    "figures": {
        "rows": ["detect-missing-figures/scripts/detect_figures.py", "rows", "@stem"],
    },
    "lists": {
        "rows": ["restore-lists/scripts/detect_lists.py", "rows", "@stem"],
    },
    # The two Markdown-only screens. They need no render, so they cost
    # milliseconds against the minutes the five above spend rasterising --
    # but they are measured here all the same, because a screen nobody
    # has a row for is a screen nobody runs. Both report candidates for
    # the rendering tools and write nothing themselves.
    "punctuation": {
        "rows": ["fix-ocr/scripts/detect_dropped_punct.py", "rows", "@md"],
    },
    "markers": {
        "rows": ["fix-ocr/scripts/detect_marker_noise.py", "rows", "@md"],
    },
}


def run_screen(spec, stem):
    """Lines a screen emits, or None when it could not run."""
    cmd = [sys.executable, "-I", str(SKILLS / spec[0]), spec[1]]
    cmd.append(str(MD_DIR / f"{stem}.md") if spec[2] == "@md" else stem)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return None
    if out.returncode not in (0, 1):
        return None
    return [l for l in out.stdout.splitlines() if l.strip() and not l.startswith("#")]


def measure(stem, screens):
    for name in screens:
        spec = SCREENS[name]
        rows = run_screen(spec["rows"], stem)
        if rows is None:
            print(f"  {stem} {name}: screen failed", file=sys.stderr)
            continue
        batch = 0
        if "batch" in spec:
            got = run_screen(spec["batch"], stem)
            batch = len(got) if got else 0
        yield {"file": stem, "screen": name, "rows": len(rows),
               "batch": batch, "measured": time.strftime("%Y-%m-%d")}


def load():
    if not TABLE.exists():
        return {}
    with TABLE.open(encoding="utf-8") as fh:
        return {(r["file"], r["screen"]): r
                for r in csv.DictReader(fh, delimiter="\t")}


def save(table):
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    with TABLE.open("w", encoding="utf-8", newline="") as fh:
        out = csv.DictWriter(fh, FIELDS, delimiter="\t", lineterminator="\n")
        out.writeheader()
        for key in sorted(table):
            out.writerow(table[key])


def cmd_run(args):
    stems = args.stems
    if args.all:
        stems = sorted(f.stem for f in MD_DIR.glob("*.md")
                       if (PDF_DIR / f"{f.stem}.pdf").exists())
    if not stems:
        sys.exit("give one or more stems, or --all")
    screens = args.screens.split(",") if args.screens else list(SCREENS)
    table = load()
    done = 0
    for stem in stems:
        todo = [s for s in screens
                if args.refresh or (stem, s) not in table]
        if not todo:
            continue
        for row in measure(stem, todo):
            table[(row["file"], row["screen"])] = row
        save(table)                       # written as it goes: this is slow
        done += 1
        print(f"{stem}: " + "  ".join(
            f"{s} {table[(stem, s)]['rows']}" for s in screens
            if (stem, s) in table), flush=True)
    print(f"-- {done} file(s) measured into {TABLE}")
    return 0


def cmd_show(args):
    table = load()
    if not table:
        sys.exit(f"nothing measured yet: run `survey.py run --all` ({TABLE})")
    rows = [r for r in table.values() if int(r["rows"]) or int(r["batch"])]
    if args.screen:
        rows = [r for r in rows if r["screen"] == args.screen]
    if args.file:
        rows = [r for r in rows if r["file"] == args.file]
    rows.sort(key=lambda r: (-int(r["rows"]), -int(r["batch"]), r["file"]))
    print(f"{'file':22} {'screen':9} {'render':>6} {'batch':>6}  measured")
    for r in rows[:args.top]:
        print(f"{r['file']:22} {r['screen']:9} {r['rows']:>6} {r['batch']:>6}"
              f"  {r['measured']}")
    print(f"-- {len(rows)} row(s) with work; "
          f"{sum(int(r['rows']) for r in rows)} need a render, "
          f"{sum(int(r['batch']) for r in rows)} are batchable")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="measure files into the table")
    r.add_argument("stems", nargs="*")
    r.add_argument("--all", action="store_true", help="every file with a scan")
    r.add_argument("--screens", help="comma-separated subset of "
                                     + ",".join(SCREENS))
    r.add_argument("--refresh", action="store_true",
                   help="re-measure files already in the table")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("show", help="read the table")
    s.add_argument("--screen")
    s.add_argument("--file")
    s.add_argument("--top", type=int, default=25)
    s.set_defaults(func=cmd_show)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
