#!/usr/bin/env python3
"""Build an HTML review sheet for one file's quote and superscript findings.

`detect_quote_pairs.py` says *that* a run is wrong; only the scan says what
it should be, and every verdict it reports needs its own look at the page.
Doing that one render at a time is slow and -- when an agent is the one
reading the crops -- expensive. This script does the locating and cropping
in one pass and hands back a single self-contained HTML file: one row per
finding, the Markdown line on the left with the offending run highlighted,
the matching band of the scan on the right.

Open it in a browser next to your editor and work down the list. Nothing is
rewritten here; the script only reports, like its siblings.

    quote_crops.py ONS_179                      # -> ONS_179-quotes.html
    quote_crops.py jons/ONS_179.md --out /tmp/review.html
    quote_crops.py ONS_179 --dpi 600            # bigger crops, bigger file
    quote_crops.py ONS_179 --include-single --include-wrecks

The PDF comes from `ONS_ARCHIVE_DIR` (default
`~/personal/src/ons-website/static/archive`), the same as the other scripts
that render.

**A crop is a located guess, not a promise.** The words before each mark are
matched against the page's own text layer, and that layer is garbled in
exactly the places this screen reports. Where the match is weak or lands on
two pages equally well, the row says so and shows no image rather than
showing the wrong part of the scan. Check that the highlighted Markdown and
the crop are the same sentence before trusting either.

Needs PyMuPDF (`.claude/skills/requirements.txt`).

Exit status is 0 when the file is clean, 1 when a sheet was written
(sibling-skill convention), 2 on a usage error.
"""

import argparse
import html
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError as exc:  # pragma: no cover - environment dependent
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF "
                 f"(see .claude/skills/requirements.txt).")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

import classify_source as source
import detect_quote_pairs as dqp
# The locating and the stacked sheets are not quote-specific: every screen
# that reports against the scan wants them. They live in `shared/`.
from crop_sheets import (PAD_LINES, STACK_WIDTH, Scan,  # noqa: F401
                         WORDS_BEFORE, WORDS_WIDE, anchor_words, stack)

PDF_DIR = Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()
REPO_ROOT = Path(__file__).resolve().parents[4]

CONTEXT_CHARS = 150     # Markdown shown either side of the run


# --- findings ------------------------------------------------------------

def collect(path, include_single=False, include_wrecks=False):
    """[(offset, verdict, note, run)] for every finding, in file order."""
    text = dqp.readable(path)
    out = []
    for off, opener, closer, span, wreck in dqp.quote_findings(text, include_single):
        if wreck and not include_wrecks:
            continue
        out.append((off, "QUOTES-WRECK" if wreck else "QUOTES",
                    f"opener <code>{html.escape(opener)}</code> vs closer "
                    f"<code>{html.escape(closer)}</code>", span))
    for off, run, reading, _ctx in dqp.superscript_findings(text):
        if reading:
            _n, _suf, old, new = reading
            note = (f"reads as an ordinal: <code>{html.escape(old)}</code> &rarr; "
                    f"<code>{html.escape(new)}</code>")
            out.append((off, "SUPERSCRIPT ordinal", note, old))
        else:
            out.append((off, "SUPERSCRIPT check",
                        "a run after a digit: ordinal, footnote marker, or a "
                        "real quote?", run))
    for off, run, _ctx in dqp.marker_findings(text):
        out.append((off, "MARKER",
                    "more marks than the page prints: "
                    f"<code>{html.escape(run)}</code> is a folded-in footnote "
                    "marker, or a doubled closer",
                    run))
    for off, quoted, _ctx in dqp.qmark_findings(text):
        out.append((off, "QMARK",
                    "a <code>?</code> that cannot end this sentence: the page "
                    "prints a closing mark", quoted))
    for off, word, _ctx in dqp.question_findings(text):
        out.append((off, "QUESTION",
                    f"<code>''</code> closing nothing after "
                    f"<code>{html.escape(word)}</code>", "''"))
    out.sort(key=lambda row: row[0])
    return text, out


# --- locating ------------------------------------------------------------

def place(path, rows, text, scan):
    """Each finding with the page and word boxes it was located on.

    [(line_no, verdict, note, offset, run, page, found)], page None when the
    words could not be placed -- `found` is then the reason.
    """
    raw = path.read_text(encoding="utf-8")
    out = []
    for off, verdict, note, run in rows:
        page, found = scan.locate(anchor_words(raw[:off + len(run)]))
        out.append((dqp.line_of(text, off), verdict, note, off, run, page, found))
    return raw, out


# --- the sheet -----------------------------------------------------------

STYLE = """
:root {
  --bg: #fbfaf8; --fg: #1b1a18; --rule: #d9d4cc; --dim: #6d6760;
  --mark: #ffe08a; --card: #ffffff; --accent: #8a5a00;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15140f; --fg: #ece8e1; --rule: #3a362f; --dim: #a09a91;
    --mark: #7a5c00; --card: #1d1b16; --accent: #e0b25a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 16px; background: var(--bg); color: var(--fg);
       font: 15px/1.5 ui-serif, Georgia, "Times New Roman", serif; }
header { max-width: 1400px; margin: 0 auto 20px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.meta, .legend { color: var(--dim); font-size: 13px; }
.legend { margin-top: 10px; border-top: 1px solid var(--rule); padding-top: 10px; }
.legend b { color: var(--fg); font-weight: 600; }
table { max-width: 1400px; margin: 0 auto; border-collapse: collapse; width: 100%; }
th { text-align: left; font-size: 12px; letter-spacing: .04em; text-transform: uppercase;
     color: var(--dim); border-bottom: 1px solid var(--rule); padding: 6px 10px;
     position: sticky; top: 0; background: var(--bg); }
td { border-bottom: 1px solid var(--rule); padding: 12px 10px; vertical-align: top; }
tr.done { opacity: .35; }
td.n { width: 64px; color: var(--dim); font-variant-numeric: tabular-nums;
       font-size: 13px; white-space: nowrap; }
td.md { width: 44%; }
.verdict { display: inline-block; font: 600 11px/1.6 ui-sans-serif, system-ui, sans-serif;
           letter-spacing: .04em; text-transform: uppercase; color: var(--accent); }
.note { color: var(--dim); font-size: 13px; margin: 2px 0 8px; }
.text { white-space: pre-wrap; word-break: break-word; font-size: 14px; }
mark { background: var(--mark); color: inherit; padding: 0 1px; border-radius: 2px; }
code { font: 13px/1.4 ui-monospace, "SF Mono", Menlo, monospace;
       background: var(--card); border: 1px solid var(--rule); border-radius: 3px;
       padding: 0 3px; }
img { width: 100%; height: auto; display: block; background: #fff;
      border: 1px solid var(--rule); border-radius: 4px; }
.missing { color: var(--dim); font-size: 13px; font-style: italic; }
input[type=checkbox] { width: 15px; height: 15px; accent-color: var(--accent); }
@media (max-width: 860px) {
  td.md, td.n { width: auto; }
  table, tbody, tr, td { display: block; width: 100%; }
  thead { display: none; }
  tr { border-bottom: 2px solid var(--rule); padding: 6px 0; }
  td { border: 0; }
}
"""

SCRIPT = """
document.addEventListener('change', e => {
  if (e.target.matches('input[type=checkbox]'))
    e.target.closest('tr').classList.toggle('done', e.target.checked);
});
"""

LEGEND = """
<div class="legend">
<b>QUOTES</b> — the opener and closer disagree. The page decides what was
printed; it is not always a quotation mark (ONS_051's was a heading with no
quotes at all). Leave a ʿayn inside a quotation
(<code>("'Abd Allah")</code>), a nested closing
(<code>the Name "Safi""</code>) and a balanced inch mark
(<code>10 3/8" x 7 3/8"</code>) exactly as they are.<br>
<b>SUPERSCRIPT ordinal</b> — restore as plain <code>14th</code>; this corpus
writes 3,599 ordinals that way and not one as <code>14ᵗʰ</code>.<br>
<b>SUPERSCRIPT check</b> / <b>QUESTION</b> — a footnote marker restores as a
superscript <i>digit</i> (<code>&lt;sup&gt;6&lt;/sup&gt;</code>), read off the page and cross-checked
against the note list; a question mark restores as <code>?</code>. The PDF's
own text layer repeats the OCR's reading here, so only the image settles it.
</div>
"""


def plain(raw, off, length):
    """The Markdown around a run, on one line, with the run in brackets."""
    line = raw[:off].rfind("\n") + 1
    end = raw.find("\n", off)
    end = len(raw) if end < 0 else end
    before = raw[max(line, off - 60):off]
    after = raw[off + length:min(end, off + length + 60)]
    out = f"{before}[[{raw[off:off + length]}]]{after}"
    return re.sub(r"\s+", " ", out)


def window(raw, off, length):
    """The Markdown line around the mark, trimmed, with the run highlighted."""
    start = raw.rfind("\n", 0, off) + 1
    end = raw.find("\n", off)
    end = len(raw) if end < 0 else end
    line = raw[start:end]
    col = off - start
    left = max(0, col - CONTEXT_CHARS)
    right = min(len(line), col + length + CONTEXT_CHARS)
    chunk = (("… " if left else "") + html.escape(line[left:col])
             + "<mark>" + html.escape(line[col:col + length]) + "</mark>"
             + html.escape(line[col + length:right]) + (" …" if right < len(line) else ""))
    return chunk


def build(path, pdf, raw, placements, scan, dpi, quality):
    cells = []
    located = 0
    for line_no, verdict, note, off, run, page, found in placements:
        if page is None:
            crop = f'<div class="missing">no crop — {html.escape(found)}</div>'
            where = "—"
        else:
            src = scan.crop(page, found, dpi, quality)
            crop = f'<img alt="scan of line {line_no}" loading="lazy" src="{src}">'
            where = f"p{page}"
            located += 1
        cells.append(
            f'<tr><td class="n"><input type="checkbox" aria-label="done">'
            f'<div>{line_no}</div><div>{where}</div></td>'
            f'<td class="md"><div class="verdict">{html.escape(verdict)}</div>'
            f'<div class="note">{note}</div>'
            f'<div class="text">{window(raw, off, len(run))}</div></td>'
            f'<td>{crop}</td></tr>')

    title = f"{path.name} — {len(placements)} finding(s) to settle against the scan"
    return located, f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(path.stem)} quote review</title>
<style>{STYLE}</style></head>
<body>
<header>
<h1>{html.escape(title)}</h1>
<div class="meta">{html.escape(str(path))} against {html.escape(pdf.name)} ·
{located} of {len(placements)} located on the scan · crops at {dpi}dpi grey ·
page numbers are 0-based, as the skills count them</div>
{LEGEND}
</header>
<table><thead><tr><th>line</th><th>markdown</th><th>scan</th></tr></thead>
<tbody>
{chr(10).join(cells)}
</tbody></table>
<script>{SCRIPT}</script>
</body></html>
"""


def resolve(arg):
    p = Path(arg)
    if not p.exists() and "/" not in arg and not arg.endswith(".md"):
        p = REPO_ROOT / "jons" / f"{arg}.md"
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="a jons/ Markdown file, or just its stem")
    ap.add_argument("--out", help="where to write the sheet "
                                  "(default <STEM>-quotes.html here)")
    ap.add_argument("--dpi", type=int, default=300,
                    help="crop resolution; 450 for a close look (default 300)")
    ap.add_argument("--quality", type=int, default=72,
                    help="JPEG quality of the crops, 1-100 (default 72)")
    ap.add_argument("--anyway", action="store_true",
                    help="build the sheet even when the source is not a scan")
    ap.add_argument("--stack", action="store_true",
                    help="labelled JPEG sheets instead of HTML, for an agent "
                         "reading the scans itself")
    ap.add_argument("--per-sheet", type=int, default=5,
                    help="findings per stacked sheet (default 5)")
    ap.add_argument("--only", choices=("quotes", "superscript", "question",
                                       "marker", "qmark"),
                    help="one verdict only, to take a long list in batches")
    ap.add_argument("--include-single", action="store_true",
                    help="also rows for single-vs-single disagreements")
    ap.add_argument("--include-wrecks", action="store_true",
                    help="also rows for spans inside OCR wreckage")
    args = ap.parse_args(argv)

    path = resolve(args.file)
    if not path.exists():
        print(f"no such file: {path}")
        return 2
    pdf = PDF_DIR / f"{path.stem}.pdf"
    if not pdf.exists():
        print(f"no scan for {path.stem}: {pdf}\n"
              f"set ONS_ARCHIVE_DIR to the archive directory")
        return 2

    verdict, note = source.classify(pdf)
    if verdict != "SCAN" and not args.anyway:
        print(f"{path}: {verdict}  {note}\n"
              f"a sheet settles OCR guesses against the page image; this file "
              f"has none to settle. Pass --anyway to build it regardless.")
        return 2

    text, rows = collect(path, args.include_single, args.include_wrecks)
    if args.only:
        want = {"quotes": "QUOTES", "superscript": "SUPERSCRIPT",
                "question": "QUESTION", "marker": "MARKER",
                "qmark": "QMARK"}[args.only]
        rows = [r for r in rows if r[1].startswith(want)]
    if not rows:
        print(f"{path}: clean")
        return 0

    scan = Scan(pdf)
    raw, placements = place(path, rows, text, scan)

    if args.stack:
        stem = args.out or f"{path.stem}-quotes"
        sheets = stack(scan,
                       [(f"line {line_no} - {verdict}", page, found)
                        for line_no, verdict, _n, _o, _r, page, found in placements],
                       stem, args.dpi, args.quality, args.per_sheet)
        for line_no, verdict, _note, off, run, page, found in placements:
            where = f"p{page}" if page is not None else f"no crop -- {found}"
            print(f"{path}:{line_no}: {verdict}  {where}\n"
                  f"    {plain(raw, off, len(run))}")
        placed_n = sum(1 for row in placements if row[5] is not None)
        print(f"{path}: {len(placements)} finding(s), {placed_n} located -> "
              + ", ".join(f"{s} ({s.stat().st_size // 1024} KB)" for s in sheets))
        return 1

    located, page = build(path, pdf, raw, placements, scan, args.dpi, args.quality)
    out = Path(args.out) if args.out else Path(f"{path.stem}-quotes.html")
    out.write_text(page, encoding="utf-8")
    print(f"{path}: {len(rows)} finding(s), {located} located -> {out} "
          f"({out.stat().st_size // 1024} KB)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
