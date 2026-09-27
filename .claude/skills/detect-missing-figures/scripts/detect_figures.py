#!/usr/bin/env python3
"""Find figures (maps, graphs, drawings, coin photos, plates) on a source-PDF
page that the `jons/` Markdown has no marker for.

The corpus PDFs are scans with an OCR text layer, so a figure leaves no
vector drawing for anything to find, and pdfmd either drops it silently
(OP_015's distribution map) or OCRs its labels into garbage text (OP_015's
graphs). Neither leaves a signal in the Markdown. This works from the page
image instead: it renders the page, erases every word box the text layer
knows about, and looks for large clusters of the ink that remains. A page
with such a cluster and no `figure` / `script-*` / `table-*` marker for that
page in the Markdown is reported as MISSING.

    detect_figures.py screen OP_015
    detect_figures.py screen ONS_146 ONS_147 -v    # -v: also list covered pages
    detect_figures.py screen --all                 # every jons/*.md with a PDF

Verdicts per page with figure-like ink:
    MISSING   no marker for this page -- render it and look
    COVERED   a figure / script-* / table-* marker names this page
    RULED     unmarked, and the ink is mostly thin straight rules: a bordered
              table or frame, which detect-missing-tables owns -- not counted

The `rect=` is in PDF points, ready for `detect_script_garble.py render
--clip`. Exit status 1 when anything is MISSING.

Blind spots: a figure on a page that already has any marker counts as
covered (a second, unmarked figure there is not detected); pale photos can
fall under the ink threshold; a page whose text layer is missing entirely
reads as all-figure.
"""
import argparse
import os
import pathlib
import re
import sys

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF only exposes the legacy `fitz` name
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")
try:
    import numpy as np
except ImportError as exc:  # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs numpy.")

# ONS_ARCHIVE_DIR overrides the default checkout-relative path -- set it when
# the ons-website PDFs live somewhere else on this machine (they come from
# the private esnible/ons-website repo, not this one, so the path varies).
PDF_DIR = pathlib.Path(
    os.environ.get("ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")
).expanduser()
if not PDF_DIR.is_dir():
    print(f"warning: PDF archive {PDF_DIR} does not exist -- set ONS_ARCHIVE_DIR "
          "to the ons-website static/archive checkout", file=sys.stderr)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MD_DIR = REPO_ROOT / "jons"

MARKER_RE = re.compile(
    r"<!--\s*(figure|script-ok|script-guess|script-deferred|table-ok|table-deferred)"
    r"\s+page=(\d+)")

DPI = 50            # 1 px ~ 1.4 pt: plenty for finding blobs, fast
INK = 110           # gray level below which a pixel is ink
WORD_PAD = 2        # px of padding around each erased word box
MARGIN = 0.04       # fraction of each edge ignored (scan borders, punch holes)
CELL = 6            # px per grid cell when clustering leftover ink
CELL_INK = 0.04     # a cell with more than this ink fraction is "inked"
MIN_SIDE = 0.05     # a region's width and height must each be >= this fraction of the page
MIN_CELLS = 8       # ...and it must hold at least this many inked cells
PAGE_CELLS = 40     # a page is figure-like when its FIGURE regions hold this many cells in all
RULED = 0.70        # fraction of a region's ink in long straight runs => RULED
RUN = 25            # px length of a run that counts as a rule


def page_ink(page):
    """Boolean ink mask with every text-layer word box erased."""
    pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    ink = img < INK
    s = DPI / 72
    for x0, y0, x1, y1, *_ in page.get_text("words"):
        ink[max(0, int(y0 * s) - WORD_PAD):int(y1 * s) + WORD_PAD + 1,
            max(0, int(x0 * s) - WORD_PAD):int(x1 * s) + WORD_PAD + 1] = False
    h, w = ink.shape
    my, mx = int(h * MARGIN), int(w * MARGIN)
    ink[:my], ink[h - my:], ink[:, :mx], ink[:, w - mx:] = False, False, False, False
    return ink


def long_runs(mask):
    """Pixels lying on a thin horizontal or vertical run of >= RUN ink pixels.

    Thin: a horizontal run's pixels must not have ink both 2 px above and
    2 px below (likewise left/right for vertical), so the interior of a solid
    dark photo does not count as ruling."""
    out = np.zeros_like(mask)
    pad = np.pad(mask, 2)
    thin_h = mask & ~(pad[:-4, 2:-2] & pad[4:, 2:-2])
    thin_v = mask & ~(pad[2:-2, :-4] & pad[2:-2, 4:])
    for m, o in ((thin_h, out), (thin_v.T, out.T)):
        for r in range(m.shape[0]):
            row = m[r]
            if row.sum() < RUN:
                continue
            d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
            for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
                if b - a >= RUN:
                    o[r, a:b] = True
    return out


def regions(ink):
    """Bounding boxes (px) of clusters of inked grid cells, with cell counts."""
    h, w = ink.shape
    gh, gw = h // CELL, w // CELL
    cells = ink[:gh * CELL, :gw * CELL].reshape(gh, CELL, gw, CELL).mean(axis=(1, 3)) > CELL_INK
    # close small gaps so a drawing's separate strokes join into one region
    grown = cells.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(cells, dy, 0), dx, 1)
    seen = np.zeros_like(grown)
    out = []
    for y, x in zip(*np.nonzero(grown)):
        if seen[y, x]:
            continue
        stack, pts = [(y, x)], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            pts.append((cy, cx))
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < gh and 0 <= nx < gw and grown[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        ys, xs = zip(*pts)
        n = int(sum(cells[p] for p in pts))
        out.append(((min(xs) * CELL, min(ys) * CELL, (max(xs) + 1) * CELL, (max(ys) + 1) * CELL), n))
    return out


def figure_regions(page, pno=None):
    """[(rect_pt, kind, cells)] for figure-like regions on the page; kind
    FIGURE or RULED. On the cover (pno 0) a small region in the top fifth --
    the society's logo in the masthead -- is skipped."""
    ink = page_ink(page)
    h, w = ink.shape
    runs = None
    found = []
    for (x0, y0, x1, y1), n in regions(ink):
        if n < MIN_CELLS or (x1 - x0) < MIN_SIDE * w or (y1 - y0) < MIN_SIDE * h:
            continue
        if pno == 0 and y1 < 0.22 * h and (x1 - x0) < 0.35 * w:
            continue
        if runs is None:
            runs = long_runs(ink)
        sub = ink[y0:y1, x0:x1]
        ruled = runs[y0:y1, x0:x1].sum() / max(1, sub.sum())
        s = 72 / DPI
        found.append(((x0 * s, y0 * s, x1 * s, y1 * s), "RULED" if ruled >= RULED else "FIGURE", n))
    return found


def figure_ink(regs):
    """FIGURE regions, if together they are big enough to call the page figure-like."""
    figs = [r for r in regs if r[1] == "FIGURE"]
    return figs if sum(r[2] for r in figs) >= PAGE_CELLS else []


def ruled_ink(regs):
    return [r for r in regs if r[1] == "RULED" and r[2] >= PAGE_CELLS]


def marked_pages(md_text):
    return {int(m.group(2)) for m in MARKER_RE.finditer(md_text)}


def screen(stem, verbose, md_override=None):
    pdf_path = PDF_DIR / f"{stem}.pdf"
    md_path = pathlib.Path(md_override) if md_override else MD_DIR / f"{stem}.md"
    if not pdf_path.exists():
        print(f"{stem}: no PDF at {pdf_path}")
        return False
    if not md_path.exists():
        print(f"{stem}: no Markdown at {md_path}")
        return False
    marked = marked_pages(md_path.read_text(encoding="utf-8"))
    doc = fitz.open(pdf_path)
    rows, counts = [], {"MISSING": 0, "COVERED": 0, "RULED": 0}
    for pno in range(len(doc)):
        regs = figure_regions(doc[pno], pno)
        figs, ruled = figure_ink(regs), ruled_ink(regs)
        if (figs or ruled) and pno in marked:
            verdict, show = "COVERED", figs + ruled
        elif figs:
            verdict, show = "MISSING", figs
        elif ruled:
            verdict, show = "RULED", ruled
        else:
            continue
        counts[verdict] += 1
        if verdict == "MISSING" or verbose:
            for (x0, y0, x1, y1), _, n in show:
                rows.append(f"  {verdict:8} p{pno}  rect={x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}  cells={n}")
    status = "nothing outstanding" if not counts["MISSING"] else f"{counts['MISSING']} page(s) to review"
    print(f"{stem}: {len(doc)} page(s) | MISSING {counts['MISSING']}  COVERED {counts['COVERED']}  "
          f"RULED {counts['RULED']} -- {status}")
    for r in rows:
        print(r)
    return counts["MISSING"] > 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("screen", help="report pages with unmarked figure-like ink")
    p.add_argument("stems", nargs="*", help="e.g. OP_015 ONS_146")
    p.add_argument("--all", action="store_true", help="every jons/*.md that has a PDF")
    p.add_argument("-v", "--verbose", action="store_true", help="also list COVERED and RULED pages")
    p.add_argument("--md", help="read markers from this Markdown file instead of jons/<STEM>.md (one stem only)")
    args = ap.parse_args()
    stems = args.stems
    if args.all:
        stems = sorted(f.stem for f in MD_DIR.glob("*.md") if (PDF_DIR / f"{f.stem}.pdf").exists())
    if not stems:
        ap.error("give one or more stems, or --all")
    if args.md and len(stems) != 1:
        ap.error("--md takes exactly one stem")
    missing = False
    for stem in stems:
        missing |= screen(stem, args.verbose, args.md)
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
