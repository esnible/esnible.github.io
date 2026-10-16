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
import base64
import difflib
import html
import os
import re
import sys
import unicodedata
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

import detect_quote_pairs as dqp

PDF_DIR = Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()
REPO_ROOT = Path(__file__).resolve().parents[4]

WORDS_BEFORE = 7        # anchor the crop on the words leading up to the mark
WORDS_WIDE = 18         # ... and on this many when seven match several pages
CONTEXT_CHARS = 150     # Markdown shown either side of the run
PAD_LINES = 1.2         # printed lines of context above and below the crop


def fold(tok):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", tok).lower())


def alike(a, b):
    """Near-equality, because the Markdown's own garble never matches exactly."""
    if not a or not b:
        return False
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


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
    for off, word, _ctx in dqp.question_findings(text):
        out.append((off, "QUESTION",
                    f"<code>''</code> closing nothing after "
                    f"<code>{html.escape(word)}</code>", "''"))
    out.sort(key=lambda row: row[0])
    return text, out


# --- locating ------------------------------------------------------------

class Scan:
    """The source PDF's pages, with their word boxes, loaded once.

    Scoring every window of every page against every query is far too slow
    on a 90-page issue with sixty findings. Instead each page keeps an index
    from word to positions: a query proposes alignments from the positions of
    its own longest words, and only those few windows are scored.
    """

    def __init__(self, pdf):
        self.doc = pymupdf.open(pdf)
        self.words = [self.doc[p].get_text("words") for p in range(self.doc.page_count)]
        self.folded = [[fold(w[4]) for w in pw] for pw in self.words]
        self.index = []
        for toks in self.folded:
            where = {}
            for k, tok in enumerate(toks):
                if tok:
                    where.setdefault(tok, []).append(k)
            self.index.append(where)
        self._seen = {}
        self._crops = {}

    def locate(self, before):
        """(page, [boxes]) for the words leading up to a mark, or (None, reason)."""
        key = tuple(before)
        if key not in self._seen:
            self._seen[key] = self._locate(before)
        return self._seen[key]

    def _locate(self, before):
        """Seven words usually pin a line; boilerplate needs more.

        A running head or a repeated formula ("Collection Moneta 18,
        Wetteren") matches several pages equally well on a short window, so
        a tie is retried with everything the caller sent. A window that
        matches *nothing* is a different problem -- the OCR mangled the
        words -- and widening it cannot help.
        """
        narrow = self._score(before[-WORDS_BEFORE:])
        if narrow[0] is not None or "equally well" not in str(narrow[1]):
            return narrow
        if len(before) > WORDS_BEFORE:
            wide = self._score(before)
            if wide[0] is not None:
                return wide
        return narrow

    def _score(self, before):
        want = [fold(w) for w in before]
        n = len(want)
        if n < 3:
            return None, "too few words before the mark to anchor a crop"
        # The longest words carry the most information and are the least
        # likely to be the ones the OCR mangled.
        anchors = sorted(range(n), key=lambda i: -len(want[i]))[:4]
        anchors = [i for i in anchors if len(want[i]) >= 4]
        if not anchors:
            return None, "no distinctive word before the mark to anchor on"

        best = []
        for p, where in enumerate(self.index):
            toks = self.folded[p]
            starts = set()
            for i in anchors:
                for pos in where.get(want[i], ()):
                    starts.add(pos - i)
            for k in starts:
                if k < 0 or k + n > len(toks):
                    continue
                hit = sum(1 for a, b in zip(want, toks[k:k + n]) if alike(a, b))
                if hit >= 0.55 * n:
                    best.append((hit, p, k))
        if not best:
            return None, "no page matches the words before the mark"
        best.sort(reverse=True)
        top = best[0]
        rivals = {p for hit, p, _ in best if hit == top[0]}
        if len(rivals) > 1:
            return None, (f"matches {len(rivals)} pages equally well "
                          f"({', '.join('p' + str(p) for p in sorted(rivals))})")
        _hit, page, k = top
        return page, self.words[page][k:k + n + 4]

    def crop(self, page_no, boxes, dpi, quality):
        """A grey JPEG of the band, as a data URI.

        Grey rather than colour and JPEG rather than PNG because these are
        black-on-white scans and a sheet carries a hundred of them: the same
        crops come to ~40KB each this way against ~650KB as colour PNGs.
        Identical bands -- several findings on one printed line -- are
        rendered once and shared.
        """
        page = self.doc[page_no]
        height = max(b[3] - b[1] for b in boxes)
        clip = pymupdf.Rect(
            max(0, min(b[0] for b in boxes) - 40),
            max(0, min(b[1] for b in boxes) - PAD_LINES * height),
            min(page.rect.width, max(b[2] for b in boxes) + 220),
            min(page.rect.height, max(b[3] for b in boxes) + PAD_LINES * height))
        key = (page_no, round(clip.x0), round(clip.y0), round(clip.x1), round(clip.y1))
        if key not in self._crops:
            pix = page.get_pixmap(clip=clip, dpi=dpi, colorspace=pymupdf.csGRAY)
            data = base64.b64encode(pix.tobytes("jpeg", jpg_quality=quality))
            self._crops[key] = "data:image/jpeg;base64," + data.decode("ascii")
        return self._crops[key]


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
superscript <i>digit</i> (<code>⁶</code>), read off the page and cross-checked
against the note list; a question mark restores as <code>?</code>. The PDF's
own text layer repeats the OCR's reading here, so only the image settles it.
</div>
"""


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


def build(path, pdf, rows, text, dpi, quality):
    raw = path.read_text(encoding="utf-8")
    scan = Scan(pdf)
    cells = []
    located = 0
    for off, verdict, note, run in rows:
        line_no = dqp.line_of(text, off)
        before = re.findall(r"[A-Za-z0-9]+", raw[:off + len(run)])[-WORDS_WIDE:]
        page, found = scan.locate(before)
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

    title = f"{path.name} — {len(rows)} finding(s) to settle against the scan"
    return located, f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(path.stem)} quote review</title>
<style>{STYLE}</style></head>
<body>
<header>
<h1>{html.escape(title)}</h1>
<div class="meta">{html.escape(str(path))} against {html.escape(pdf.name)} ·
{located} of {len(rows)} located on the scan · crops at {dpi}dpi grey ·
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
    ap.add_argument("--only", choices=("quotes", "superscript", "question"),
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

    text, rows = collect(path, args.include_single, args.include_wrecks)
    if args.only:
        want = {"quotes": "QUOTES", "superscript": "SUPERSCRIPT",
                "question": "QUESTION"}[args.only]
        rows = [r for r in rows if r[1].startswith(want)]
    if not rows:
        print(f"{path}: clean")
        return 0

    located, page = build(path, pdf, rows, text, args.dpi, args.quality)
    out = Path(args.out) if args.out else Path(f"{path.stem}-quotes.html")
    out.write_text(page, encoding="utf-8")
    print(f"{path}: {len(rows)} finding(s), {located} located -> {out} "
          f"({out.stat().st_size // 1024} KB)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
