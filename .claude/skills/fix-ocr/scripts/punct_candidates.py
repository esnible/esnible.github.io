#!/usr/bin/env python3
"""List punctuation the page prints but the Markdown lacks (or vice versa).

Some issues' PDF text layers dropped nearly every sentence-ending period, so
neither cspell nor the text layer can find them. This renders each PDF page,
runs tesseract on it, aligns tesseract's words against the Markdown's words,
and reports every aligned word whose trailing punctuation differs -- with a
render command clipped to that word so the candidate can be confirmed by eye.

Why that is not circular, given `scripts/build.sh` runs `pdfmd --ocr auto
--lang eng+ara`: **on these files pdfmd did not OCR anything.** `--ocr auto`
takes the PDF's embedded text layer when there is one, and every scan in this
corpus has one. Measured on ONS_158, the Markdown's trailing-period pattern
agrees with that embedded layer on 100.0% of aligned words (99.9% on page 13)
and with a fresh tesseract run on only 95%. The Markdown's period density
tracks the layer's everywhere it was checked -- ONS_158 22.0 -> 28.1,
ONS_159 13.5 -> 17.0, ONS_171 14.6 -> 15.9, and for files whose layer is good,
ONS_200 64.3 -> 65.8 and ONS_190 70.6 -> 70.3 per 1000 words.

So the comparison here is not tesseract against itself. It is tesseract
against whatever OCR the scanner's operator ran years ago, and tesseract wins
by a wide margin: 64.3 periods per 1000 words against the layer's 22.0 on
ONS_158, 38.8 against 13.5 on ONS_159, on page text whose *words* the two
agree about 98% of the time. 64.3 is close to the 72.8 an undamaged file in
this corpus has, which is the sense in which the marks are recoverable at
all.

Neither the language nor the resolution explains the gap, so neither is worth
tuning: `-l eng` and `-l eng+ara` return identical period counts on three of
four sampled pages, and tesseract recovers 68.0 per 1000 at every DPI from
150 to 400 (58.1 even at 100).

The practical consequence is for the build, not for this script: a corpus
rebuilt so that scanned pages are re-OCR'd rather than read from their
embedded layer would not need the `punctuation` screen's WHOLESALE class at
all.

    python3 punct_candidates.py jons/ONS_146.md
    python3 punct_candidates.py jons/ONS_146.md --pages 2-9

Output, one candidate per line, `line:col` as cspell gives it:

    jons/ONS_146.md:57:214  md 'types'  page 'types.'  p3  --clip 312 440 372 452

Tesseract's reading is a candidate, not evidence: confirm each with the
render (batch several clips per page) before editing. Table rows, figure
markers and HTML comments are skipped. Needs PyMuPDF and the `tesseract` CLI.
Page renders and tesseract output are cached under
$TMPDIR/ons-render/<STEM>/tess/.

`--apply` turns the listing into a pass. Reading every page does not earn
its cost: ONS_158 had all 37 of its pages rendered and read and still took
53 bad edits, and ONS_157 took 4 from 20 pages read. What caught them both
was re-running this alignment afterwards, which costs nothing. So apply the
one class that is safe to place without an eye -- the Markdown has no
trailing punctuation and the page has exactly one `.` or `:` -- then
re-align and report only what still disagrees:

    python3 punct_candidates.py jons/ONS_146.md --apply          # dry run
    python3 punct_candidates.py jons/ONS_146.md --apply --write
    python3 punct_candidates.py jons/ONS_146.md --apply --write --sheet-rows r.tsv

An EXTRA row is the one to care about: the Markdown has a mark the page
does not, so either tesseract read a speck or a mark went in at the wrong
spot. MISSING rows are the classes `--apply` does not touch. Feed
`--sheet-rows` to `shared/crop_sheets.py` to settle the residue from a
couple of sheets instead of a render apiece.
"""
import argparse
import csv
import difflib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError as exc:
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")

PDF_DIR = pathlib.Path(
    os.environ.get("ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")
).expanduser()
DPI = 300
PUNCT = ".,;:!?"
QUOTES = {"“": '"', "”": '"', "‘": "'", "’": "'"}
WORD = r"0-9A-Za-zÀ-ɏḀ-ỿ"


def norm(tok):
    return re.sub(r"[^0-9a-z]", "", tok.lower())


def trailing_punct(tok):
    """The run of PUNCT at the end of a token, ignoring quotes/brackets/markup around it."""
    tok = "".join(QUOTES.get(c, c) for c in tok)
    m = re.search(rf"[{WORD}]([^{WORD}]*)$", tok)
    tail = m.group(1) if m else ""
    return "".join(c for c in tail if c in PUNCT)


def page_words(pdf, page, cache):
    """tesseract words on one page as (text, left, top, right, bottom) in PDF points."""
    tsv = cache / f"p{page:03d}.tsv"
    if not tsv.exists():
        png = cache / f"p{page:03d}.png"
        pdf[page].get_pixmap(dpi=DPI).save(png)
        subprocess.run(["tesseract", str(png), str(tsv.with_suffix("")), "tsv"],
                       check=True, capture_output=True)
    scale = 72 / DPI
    words, carry = [], None
    with open(tsv, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r["level"] != "5" or not r["text"].strip():
                continue
            x0, y0 = int(r["left"]) * scale, int(r["top"]) * scale
            x1, y1 = x0 + int(r["width"]) * scale, y0 + int(r["height"]) * scale
            text = r["text"]
            if carry:  # rejoin a word hyphenated across a line break
                text, x0, y0 = carry[0] + text, carry[1], carry[2]
                carry = None
            if re.search(r"[A-Za-z]-$", text):
                carry = (text[:-1], x0, y0)
                continue
            words.append((text, x0, y0, x1, y1))
    if carry:
        words.append((carry[0] + "-", carry[1], carry[2], carry[1], carry[2]))
    return words


def md_words(text):
    """(line, col, token) for every word, `col` 1-based within its line.

    The column is what makes a finding placeable. Reporting the token alone
    throws it away, and the token is routinely not unique on its line: the
    Indian-tokens review in ONS_157 says `from region to region. Some`, so
    one finding for `region` has two slots and a pass that picks the first
    puts the period in the wrong one.
    """
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s.startswith(("|", "<!--", "*[figure]")):
            continue
        for m in re.finditer(r"\S+", line):
            if norm(m.group()):
                out.append((i, m.start() + 1, m.group()))
    return out


def parse_pages(spec, n):
    if not spec:
        return range(n)
    pages = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        pages.update(range(int(a), int(b or a) + 1))
    return sorted(p for p in pages if p < n)


def candidates(text, page_toks):
    """Aligned words whose trailing punctuation differs, as rows."""
    mdt = md_words(text)
    a = [norm(t) for _, _, t in mdt]
    b = [norm(w[0]) for w, _ in page_toks]
    rows = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, a0, a1, b0, _ in matcher.get_opcodes():
        if op != "equal":
            continue
        for k in range(a1 - a0):
            line, col, tok = mdt[a0 + k]
            (ptok, x0, y0, x1, y1), page = page_toks[b0 + k]
            if trailing_punct(tok) == trailing_punct(ptok):
                continue
            clip = f"{max(0, x0 - 60):.0f} {y0 - 4:.0f} {x1 + 60:.0f} {y1 + 4:.0f}"
            rows.append((line, col, tok, ptok, page, clip))
    return rows


def placeable(rows, marks, emphasis=False):
    """(line, col, old, new) for the rows safe to place without an eye.

    A row qualifies only when the Markdown token carries no trailing
    punctuation at all, the page carries exactly one mark from `marks`, and
    the page's token is the Markdown's with that mark on the end and nothing
    else changed. That last test is the one that matters. Words are aligned
    on their letters alone, so `KM` pairs with the page's `K.M.` and `Ghazi-`
    with `Ghazi.`; appending the trailing mark to those gives `KM.` and
    `Ghazi-.`, which is neither reading. Curly quotes are folded first so a
    genuine `tokens"` -> `tokens".` is not lost to the quote style alone.

    A token ending in emphasis markup is left out by default, because whether
    the mark belongs inside or outside the asterisks is a judgement this
    alignment cannot make. `--emphasis` takes those too and puts the mark
    outside, which is what the scans show: of ONS_156's four sampled italic
    titles -- `INJ 8.`, `ONS Newsletter.`, `...from Kasur.`, `...invasion of
    India.` -- every one sets the full stop upright after the italic, and
    `*title*.` is the Markdown that says so. The same letters-unchanged test
    still applies, run against the token with its markup stripped.
    """
    def unquote(s):
        return "".join(QUOTES.get(c, c) for c in s)

    out = []
    for line, col, tok, ptok, _page, _clip in rows:
        pg = trailing_punct(ptok)
        if trailing_punct(tok) or len(pg) != 1 or pg not in marks:
            continue
        bare = tok.rstrip("*_`")
        if bare != tok and not emphasis:
            continue
        if not bare or unquote(ptok) != unquote(bare) + pg:
            continue
        out.append((line, col, tok, tok + pg))
    return out


def place(text, edits):
    """Rewrite `text`, each edit at its own offset, right to left.

    Right to left so earlier offsets on a line stay valid, and every edit is
    checked against the text it claims to replace rather than searched for.
    """
    lines = text.split("\n")
    for line, col, old, new in sorted(edits, reverse=True):
        i, start = line - 1, col - 1
        if lines[i][start:start + len(old)] != old:
            sys.exit(f"{line}:{col}: expected {old!r}, found "
                     f"{lines[i][start:start + len(old)]!r}")
        if "\n" in new:
            sys.exit(f"{line}:{col}: replacement would add a line")
        lines[i] = lines[i][:start] + new + lines[i][start + len(old):]
    return "\n".join(lines)


def anchor(text, line, col, width=42):
    """A span of the line around a finding, for crop_sheets to place."""
    row = text.split("\n")[line - 1]
    lo = max(0, col - 1 - width // 2)
    return " ".join(row[lo:lo + width].split())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("--pages", help="0-based PDF page indices, e.g. 2-9,14 (default: all)")
    ap.add_argument("--apply", action="store_true",
                    help="place the safe class, re-align, report only what still disagrees")
    ap.add_argument("--write", action="store_true", help="with --apply, save the file")
    ap.add_argument("--marks", default=".:", help="marks --apply may place (default '.:')")
    ap.add_argument("--emphasis", action="store_true",
                    help="with --apply, also place a mark outside a trailing *, _ or `")
    ap.add_argument("--sheet-rows", help="with --apply, write the residue as crop_sheets.py rows")
    args = ap.parse_args()

    if not shutil.which("tesseract"):
        sys.exit("tesseract not found on PATH (brew install tesseract)")
    stem = pathlib.Path(args.md).stem
    pdf_path = PDF_DIR / f"{stem}.pdf"
    if not pdf_path.exists():
        sys.exit(f"no PDF at {pdf_path} -- set ONS_ARCHIVE_DIR")
    cache = pathlib.Path(tempfile.gettempdir()) / "ons-render" / stem / "tess"
    cache.mkdir(parents=True, exist_ok=True)

    pdf = fitz.open(pdf_path)
    page_toks = []
    for p in parse_pages(args.pages, len(pdf)):
        page_toks += [(w, p) for w in page_words(pdf, p, cache)]

    path = pathlib.Path(args.md)
    text = path.read_text(encoding="utf-8")
    rows = candidates(text, page_toks)

    def show(label, row):
        line, col, tok, ptok, page, clip = row
        print(f"{label}{args.md}:{line}:{col}  md {tok!r}  page {ptok!r}  "
              f"p{page}  --clip {clip}")

    if not args.apply:
        for row in rows:
            show("", row)
        print(f"{len(rows)} candidate(s)", file=sys.stderr)
        return

    edits = placeable(rows, args.marks, args.emphasis)
    new_text = place(text, edits)
    if new_text.count("\n") != text.count("\n"):
        sys.exit("refusing to write: line count changed")

    left = candidates(new_text, page_toks)
    extra = [r for r in left if trailing_punct(r[2]) and not trailing_punct(r[3])]
    missing = [r for r in left if not trailing_punct(r[2])]
    for row in extra:
        show("EXTRA    ", row)
    for row in missing:
        show("MISSING  ", row)

    if args.sheet_rows:
        with open(args.sheet_rows, "w", encoding="utf-8") as f:
            for label, group in (("extra", extra), ("missing", missing)):
                for line, col, tok, ptok, _page, _clip in group:
                    f.write(f"{label} {line}:{col} {tok!r}->{ptok!r}\t"
                            f"{anchor(new_text, line, col)}\n")
        print(f"-- {len(extra) + len(missing)} row(s) for crop_sheets.py "
              f"in {args.sheet_rows}", file=sys.stderr)

    if args.write:
        path.write_text(new_text, encoding="utf-8")
    print(f"{len(edits)} mark(s) placed{'' if args.write else ' (dry run)'}; "
          f"{len(extra)} EXTRA, {len(missing)} MISSING left to settle",
          file=sys.stderr)


if __name__ == "__main__":
    main()
