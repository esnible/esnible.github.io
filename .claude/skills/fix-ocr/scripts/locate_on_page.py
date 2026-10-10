#!/usr/bin/env python3
"""Find where a Markdown line sits on its scanned page, and crop it.

`triage_percent.py` leans on the PDF's own text layer to say what a suspect
character really is. Two PDFs in the archive -- ONS_177 and ONS_197 -- carry
no text layer at all, and a garbled line can defeat the alignment even where
one exists. Then the only evidence left is the page itself, and the problem
becomes mechanical: which of forty pages is this line on, and where?

This script answers that. It OCRs each page image with tesseract, keeping
every word's bounding box, then slides the Markdown line's own words over
each page to find the best match. The matched box gives a tight crop -- a
band of two or three lines, legible at a glance -- instead of a whole page.

The tesseract pass is a locator, NOT a reading: it has no more authority
than any other OCR. Decide from the crop, by eye.

    # once per PDF, ~4s a page; cached under the index directory
    python3 locate_on_page.py index ONS_177

    # one crop per site, as STEM:LINE:COLUMN (column is 0-based)
    python3 locate_on_page.py crop out/ ONS_177:815:203 ONS_177:1041:38

Each crop prints the page, the match score, and both readings of the window,
so a bad match is obvious before you open the image:

    ONS_177:815:203  p21 score=24/24  ONS_177_815_203.png
        md  : being the rarest coins) than the 7% skar (1-150-1-152) and the 2% skar
        ocr : being the rarest coins) than the 74 skar (1-150-1-152) and the 2% skar

A score well under the maximum means the window did not land: usually the
line is a flattened table or a scrambled two-column region, whose words do
not sit together on the page in that order. Those belong to
`restructure-flattened-md` or `reconstruct-scrambled-md`, not here.
"""
import argparse
import csv
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError as exc:
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")

PDF_DIR = pathlib.Path(
    os.environ.get("ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")
).expanduser()
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MD_DIR = REPO_ROOT / "jons"
INDEX_DIR = pathlib.Path(
    os.environ.get("ONS_PAGE_INDEX", tempfile.gettempdir() + "/ons-page-index")
)

OCR_DPI = 300      # tesseract wants ~300 for body text at these point sizes
WINDOW = 6         # context words either side of the column
ZOOM = 5           # crop render scale; 5x is comfortably readable


def norm(tok):
    return re.sub(r"[^a-z0-9]", "", tok.lower())


def build_index(stem):
    """OCR every page of the PDF, keeping each word's box in page pixels."""
    pdf = PDF_DIR / f"{stem}.pdf"
    if not pdf.exists():
        sys.exit(f"no such PDF: {pdf}")
    doc = pymupdf.open(pdf)
    pages = []
    with tempfile.TemporaryDirectory() as td:
        png = pathlib.Path(td) / "page.png"
        for i in range(doc.page_count):
            doc[i].get_pixmap(dpi=OCR_DPI).save(png)
            tsv = subprocess.run(
                ["tesseract", str(png), "stdout", "--psm", "3",
                 "-c", "preserve_interword_spaces=1", "tsv"],
                capture_output=True, text=True).stdout
            words = []
            for row in csv.DictReader(io.StringIO(tsv), delimiter="\t",
                                      quoting=csv.QUOTE_NONE):
                text = (row.get("text") or "").strip()
                if not text:
                    continue
                words.append({"t": text, "x": int(row["left"]),
                              "y": int(row["top"]), "w": int(row["width"]),
                              "h": int(row["height"])})
            pages.append({"page": i, "dpi": OCR_DPI, "words": words})
            print(f"{stem} p{i}: {len(words)} words", file=sys.stderr)
    doc.close()
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    out = INDEX_DIR / f"{stem}.json"
    out.write_text(json.dumps(pages))
    return out


def load_index(stem):
    path = INDEX_DIR / f"{stem}.json"
    if not path.exists():
        print(f"indexing {stem} (no cache at {path})", file=sys.stderr)
        path = build_index(stem)
    return json.loads(path.read_text())


def md_window(stem, line_no, col):
    """The words around `col`, and which of them holds it."""
    line = (MD_DIR / f"{stem}.md").read_text(
        encoding="utf-8").splitlines()[line_no - 1]
    words, at = [], None
    for m in re.finditer(r"\S+", line):
        if m.start() <= col < m.end():
            at = len(words)
        words.append(m.group())
    if at is None:
        sys.exit(f"{stem}:{line_no}:{col} falls on whitespace")
    lo, hi = max(0, at - WINDOW), min(len(words), at + WINDOW + 1)
    return words[lo:hi], at - lo


def best_match(pages, window, hole):
    """Slide the window across every page. The suspect word is skipped --
    it is precisely the one the two OCR passes disagree about."""
    keys = [norm(w) for w in window]
    best = None
    for pg in pages:
        page_keys = [norm(w["t"]) for w in pg["words"]]
        for i in range(len(page_keys) - len(keys) + 1):
            score = 0
            for j, key in enumerate(keys):
                if j == hole or not key:
                    continue
                other = page_keys[i + j]
                if key == other:
                    score += 2
                elif other and (key in other or other in key):
                    score += 1
            if best is None or score > best[0]:
                best = (score, pg["page"], i, pg["dpi"])
    return best


def crop(outdir, spec):
    stem, line_no, col = spec.split(":")
    line_no, col = int(line_no), int(col)
    window, hole = md_window(stem, line_no, col)
    score, page, i, dpi = best_match(load_index(stem), window, hole)
    words = load_index(stem)[page]["words"][i:i + len(window)]
    scale = 72.0 / dpi
    doc = pymupdf.open(PDF_DIR / f"{stem}.pdf")
    pg = doc[page]
    box = pymupdf.Rect(
        max(0, min(w["x"] for w in words) * scale - 20),
        max(0, min(w["y"] for w in words) * scale - 12),
        min(pg.rect.x1, max(w["x"] + w["w"] for w in words) * scale + 20),
        min(pg.rect.y1, max(w["y"] + w["h"] for w in words) * scale + 12))
    out = outdir / f"{stem}_{line_no}_{col}.png"
    pg.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), clip=box).save(out)
    doc.close()
    print(f"{spec}  p{page} score={score}/{2 * (len(window) - 1)}  {out.name}")
    print(f"    md  : {' '.join(window)}")
    print(f"    ocr : {' '.join(w['t'] for w in words)}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    idx = sub.add_parser("index", help="OCR a PDF's pages and cache the boxes")
    idx.add_argument("stems", nargs="+")
    cr = sub.add_parser("crop", help="crop one or more STEM:LINE:COLUMN sites")
    cr.add_argument("outdir", type=pathlib.Path)
    cr.add_argument("sites", nargs="+")
    args = ap.parse_args()

    if args.cmd == "index":
        for stem in args.stems:
            print(build_index(stem))
        return
    args.outdir.mkdir(parents=True, exist_ok=True)
    for site in args.sites:
        crop(args.outdir, site)


if __name__ == "__main__":
    main()
