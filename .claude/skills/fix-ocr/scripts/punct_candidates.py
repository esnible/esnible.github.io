#!/usr/bin/env python3
"""List punctuation the page prints but the Markdown lacks (or vice versa).

Some issues' PDF text layers dropped nearly every sentence-ending period, so
neither cspell nor the text layer can find them. This renders each PDF page,
runs tesseract on it (a second, independent OCR), aligns tesseract's words
against the Markdown's words, and reports every aligned word whose trailing
punctuation differs -- with a render command clipped to that word so the
candidate can be confirmed by eye.

    python3 punct_candidates.py jons/ONS_146.md
    python3 punct_candidates.py jons/ONS_146.md --pages 2-9

Output, one candidate per line:

    jons/ONS_146.md:57  md 'types'  page 'types.'  p3  --clip 312 440 372 452

Tesseract's reading is a candidate, not evidence: confirm each with the
render (batch several clips per page) before editing. Table rows, figure
markers and HTML comments are skipped. Needs PyMuPDF and the `tesseract` CLI.
Page renders and tesseract output are cached under
$TMPDIR/ons-render/<STEM>/tess/.
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


def md_words(path):
    out = []
    for i, line in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
        s = line.strip()
        if s.startswith(("|", "<!--", "*[figure]")):
            continue
        for tok in line.split():
            if norm(tok):
                out.append((i, tok))
    return out


def parse_pages(spec, n):
    if not spec:
        return range(n)
    pages = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        pages.update(range(int(a), int(b or a) + 1))
    return sorted(p for p in pages if p < n)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("--pages", help="0-based PDF page indices, e.g. 2-9,14 (default: all)")
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
    mdt = md_words(args.md)

    a = [norm(t) for _, t in mdt]
    b = [norm(w[0]) for w, _ in page_toks]
    n = 0
    for op, a0, a1, b0, _ in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "equal":
            continue
        for k in range(a1 - a0):
            line, tok = mdt[a0 + k]
            (ptok, x0, y0, x1, y1), page = page_toks[b0 + k]
            if trailing_punct(tok) == trailing_punct(ptok):
                continue
            n += 1
            clip = f"{max(0, x0 - 60):.0f} {y0 - 4:.0f} {x1 + 60:.0f} {y1 + 4:.0f}"
            print(f"{args.md}:{line}  md {tok!r}  page {ptok!r}  p{page}  --clip {clip}")
    print(f"{n} candidate(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
