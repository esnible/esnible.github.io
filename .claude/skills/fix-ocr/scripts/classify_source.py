#!/usr/bin/env python3
"""Say whether a file's source PDF is a scan, born-digital, or has no text layer.

Most of the corpus is scanned paper: a full-page image with an OCR text layer
behind it, where every mark in the Markdown is a guess the renders can settle.
A born-digital issue is different in kind -- its text is the publisher's own,
so the quote and superscript screens are reading typography that was never
OCR'd, and repairing it from page renders is the wrong tool. A third case
reads as a scan but carries no text layer at all, which no script that
locates words on the page can work with.

    classify_source.py scan ONS_192 ONS_117
    classify_source.py scan jons/*.md

    jons/ONS_192.md: BORN-DIGITAL  text 3559 chars/page, images cover 0.05
    jons/ONS_117.md: SCAN  text 2892 chars/page, images cover 1.00

Exit 0 when every file is a scan, 1 when any is not, 2 on usage.
"""
import os
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError as exc:                                   # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs PyMuPDF "
             f"(see .claude/skills/requirements.txt).")

PDF_DIR = Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()
REPO_ROOT = Path(__file__).resolve().parents[4]
PAGES = 3           # enough to tell the two apart; the first page may be a cover
TEXT_FLOOR = 200    # characters per page below which there is no usable layer
IMAGE_FLOOR = 0.6   # page area covered by images, above which it is a scan


def measure(pdf):
    """(chars per page, share of the page covered by images) over the first pages."""
    doc = pymupdf.open(pdf)
    pages = min(PAGES, doc.page_count)
    chars = cover = 0
    for number in range(pages):
        page = doc[number]
        chars += len(page.get_text().strip())
        area = abs(page.rect)
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                cover += abs(rect) / area
    return chars // pages, cover / pages


def classify(pdf):
    """(verdict, note). BORN-DIGITAL and NO-TEXT-LAYER are both findings."""
    chars, cover = measure(pdf)
    note = f"text {chars} chars/page, images cover {cover:.2f}"
    if chars < TEXT_FLOOR:
        return "NO-TEXT-LAYER", f"{note} -- nothing to locate words against"
    if cover < IMAGE_FLOOR:
        return "BORN-DIGITAL", f"{note} -- the publisher's own text, not OCR"
    return "SCAN", note


def resolve(arg):
    p = Path(arg)
    if not p.exists() and "/" not in arg and not arg.endswith(".md"):
        p = REPO_ROOT / "jons" / f"{arg}.md"
    return p


def main(argv):
    if len(argv) < 2 or argv[0] != "scan":
        print(__doc__)
        return 2
    findings = 0
    for arg in argv[1:]:
        path = resolve(arg)
        pdf = PDF_DIR / f"{path.stem}.pdf"
        if not pdf.exists():
            print(f"{path}: NO-SCAN  no {pdf.name} in {PDF_DIR}")
            findings += 1
            continue
        verdict, note = classify(pdf)
        print(f"{path}: {verdict}  {note}")
        findings += verdict != "SCAN"
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
