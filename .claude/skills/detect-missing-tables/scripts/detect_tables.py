#!/usr/bin/env python3
"""Detect bordered tables in scanned ONS PDFs and report which ones the
corresponding Markdown file is missing.

The `jons/` PDFs are scans: every page is one full-page image plus an OCR text
layer, with `drawings == 0`. Vector table finders (pdfplumber `lines`, Camelot
lattice, PyMuPDF `find_tables`) therefore report zero tables on every file in
this corpus. Rules here are found in pixels instead.

Usage:
    detect_tables.py screen IS_001 [IS_002 ...]   # Tier 0: what's missing
    detect_tables.py grids  IS_001                # Tier 1: grid geometry
    detect_tables.py cells  IS_001 --page 3       # Tier 2: cell text

Requires PyMuPDF and numpy (no cv2/pdfplumber/camelot).
"""
import argparse
import pathlib
import re
import sys

try:
    import fitz  # PyMuPDF
    import numpy as np
except ImportError as exc:  # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs PyMuPDF and numpy.")

PDF_DIR = pathlib.Path("~/personal/src/ons-website/static/archive").expanduser()
MD_DIR = pathlib.Path(__file__).resolve().parents[4] / "jons"

# --- tuned defaults -------------------------------------------------------
# THRESH: 185 is stable; 160 lets page-edge scan artifacts through.
# MIN_FRAC: fraction of the *page* a rule must span to be a candidate. Must stay
#   low -- a table often covers well under half its page, so a higher value can
#   make it impossible for that table's rules to ever qualify. Coherence is
#   enforced by the overlap test in find_tables(), not by this threshold.
THRESH, MIN_FRAC, EDGE, SMEAR, DPI = 185, 0.12, 0.02, 2, 110


def _longest_runs(binary):
    """Per row: (row_index, run_start, run_end) of the longest contiguous ink run."""
    out = []
    for i, row in enumerate(binary):
        if not row.any():
            continue
        edges = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
        starts, ends = edges[0::2], edges[1::2]
        k = int(np.argmax(ends - starts))
        out.append((i, int(starts[k]), int(ends[k])))
    return out


def _merge(runs, min_len, gap=6):
    """Keep runs >= min_len, then merge adjacent parallel ones into single rules."""
    runs = [r for r in runs if r[2] - r[1] >= min_len]
    if not runs:
        return []
    rules, cur = [], [runs[0]]
    for r in runs[1:]:
        if r[0] - cur[-1][0] <= gap:
            cur.append(r)
        else:
            rules.append(tuple(int(np.median([c[j] for c in cur])) for j in range(3)))
            cur = [r]
    rules.append(tuple(int(np.median([c[j] for c in cur])) for j in range(3)))
    return rules


def page_grid(page, dpi=DPI, thresh=THRESH, min_frac=MIN_FRAC, edge=EDGE):
    """Return (h_rules, v_rules, (H, W)) in raster pixels.

    h_rules are (y, x0, x1); v_rules are (x, y0, y1). Extents matter: they are
    what the overlap test in find_tables() uses to tell a real grid from
    unrelated rules elsewhere on the page.
    """
    pm = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    gray = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width)
    H, W = gray.shape
    ink = gray < thresh
    # OR-smear perpendicular to each axis so a slightly skewed scan still yields
    # one long contiguous run rather than many short ones.
    hs = np.zeros_like(ink)
    vs = np.zeros_like(ink)
    for k in range(-SMEAR, SMEAR + 1):
        hs |= np.roll(ink, k, axis=0)
        vs |= np.roll(ink, k, axis=1)
    h = _merge(_longest_runs(hs), min_frac * W)
    v = _merge(_longest_runs(vs.T), min_frac * H)
    h = [r for r in h if edge * H < r[0] < (1 - edge) * H]
    v = [r for r in v if edge * W < r[0] < (1 - edge) * W]
    return h, v, (H, W)


def find_tables(h_rules, v_rules, min_overlap=0.5):
    """Group mutually-overlapping rules into table regions.

    Returns dicts with `cols` (reliable) and `rows` (NOT reliable -- interior
    horizontal rules are frequently absent, so rows must come from clustering
    word boxes; see cells_by_column()).
    """
    if len(h_rules) < 2 or len(v_rules) < 2:
        return []
    y0, y1 = min(r[1] for r in v_rules), max(r[2] for r in v_rules)
    x0, x1 = min(r[0] for r in v_rules), max(r[0] for r in v_rules)
    H = [r for r in h_rules
         if min(r[2], x1) - max(r[1], x0) > min_overlap * max(1, x1 - x0)]
    V = [r for r in v_rules
         if min(r[2], y1) - max(r[1], y0) > min_overlap * max(1, y1 - y0)]
    if len(H) < 2 or len(V) < 3:
        return []
    return [{
        "rows_ruled": len(H) - 1,
        "cols": len(V) - 1,
        "bbox_px": (min(v[0] for v in V), min(r[0] for r in H),
                    max(v[0] for v in V), max(r[0] for r in H)),
        "v_px": [v[0] for v in V],
        "h_px": [r[0] for r in H],
    }]


def page_tables(page, **kw):
    h, v, dims = page_grid(page, **kw)
    return find_tables(h, v), dims


HEADERISH = {"no", "date", "notes", "obverse", "reverse", "shape", "weight",
             "designation", "grains", "type", "types", "ref", "wt", "diam",
             "metal", "rarity", "comments", "mint"}


def caption_for(page, table, dims):
    """Nearest text above the grid, plus keywords and a confidence flag.

    Low confidence means the nearest text above the grid is the table's own
    header row rather than a caption -- such anchors match the Markdown
    unreliably and must be checked by hand.
    """
    H, W = dims
    scale = page.rect.width / W
    top = table["bbox_px"][1] * scale
    above = sorted([b for b in page.get_text("blocks") if b[3] < top], key=lambda b: b[3])
    text = " ".join(" ".join(b[4].split()) for b in above[-2:])[-60:]
    words = re.findall(r"[A-Za-z]{4,}", text)[-3:]
    confident = bool(words) and not all(w.lower() in HEADERISH for w in words)
    return text.strip(), words, confident


def cells_by_column(page, table, dims, row_gap=1.6):
    """Assign OCR words to columns via the vertical rules, then cluster into rows.

    Columns are read off the ruling lines and are dependable. Rows are not: this
    groups words into text lines, then splits those lines into rows at interior
    horizontal rules where they exist and at outsized line gaps where they do
    not. Cells spanning several columns still smear across them and need manual
    repair.
    """
    H, W = dims
    scale = page.rect.width / W
    x0, y0, x1, y1 = [c * scale for c in table["bbox_px"]]
    v = [x * scale for x in table["v_px"]]
    interior = [y * scale for y in table["h_px"][1:-1]]
    words = [w for w in page.get_text("words")
             if y0 <= w[1] and w[3] <= y1 and x0 <= w[0] <= x1]
    if not words:
        return []
    line_h = float(np.median([w[3] - w[1] for w in words])) or 10.0

    # 1. group words into text lines by y-centre
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines = []
    for w in words:
        yc = (w[1] + w[3]) / 2
        if lines and yc - lines[-1]["yc"] <= 0.6 * line_h:
            lines[-1]["ws"].append(w)
            lines[-1]["yc"] = float(np.mean([(x[1] + x[3]) / 2 for x in lines[-1]["ws"]]))
        else:
            lines.append({"yc": yc, "ws": [w]})

    # 2. split lines into rows: at an interior rule, or at an outsized gap
    gaps = [lines[i + 1]["yc"] - lines[i]["yc"] for i in range(len(lines) - 1)]
    typical = float(np.median(gaps)) if gaps else line_h
    bands, cur = [], [lines[0]] if lines else []
    for prev, nxt in zip(lines, lines[1:]):
        crossed = any(prev["yc"] < r < nxt["yc"] for r in interior)
        if crossed or (nxt["yc"] - prev["yc"]) > row_gap * typical:
            bands.append(cur)
            cur = []
        cur.append(nxt)
    if cur:
        bands.append(cur)

    out = []
    for band in bands:
        band_words = [w for ln in band for w in ln["ws"]]
        cells = [""] * (len(v) - 1)
        for i in range(len(v) - 1):
            inside = [w for w in band_words if v[i] <= (w[0] + w[2]) / 2 < v[i + 1]]
            inside.sort(key=lambda w: (round(w[1] / max(1.0, line_h * 0.6)), w[0]))
            cells[i] = " ".join(w[4] for w in inside).strip()
        if any(cells):
            out.append(cells)
    return out


def md_pipe_lines(md_path):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    return lines, [bool(re.match(r"\s*\|", ln)) for ln in lines]


def resolve(stem):
    return PDF_DIR / f"{stem}.pdf", MD_DIR / f"{stem}.md"


def cmd_screen(args):
    """Classify each detected grid as PRESENT / MISSING / UNKNOWN.

    UNKNOWN is not a soft MISSING. It means the anchor could not be located, so
    the screen has no opinion -- the table may well be there. Only MISSING is a
    positive finding.
    """
    needs_attention = False
    for stem in args.stems:
        pdf_path, md_path = resolve(stem)
        if not pdf_path.exists():
            print(f"{stem}: no PDF at {pdf_path}")
            continue
        if not md_path.exists():
            print(f"{stem}: no Markdown at {md_path}")
            continue
        lines, ispipe = md_pipe_lines(md_path)
        doc = fitz.open(pdf_path)
        findings = []
        for pno, page in enumerate(doc):
            tables, dims = page_tables(page, dpi=args.dpi)
            for t in tables:
                if t["cols"] < args.min_cols:
                    continue
                text, keys, confident = caption_for(page, t, dims)
                hit = None
                if keys and confident:
                    hit = next((n for n, ln in enumerate(lines)
                                if all(k.lower() in ln.lower() for k in keys)), None)
                if hit is None:
                    verdict, why = "UNKNOWN", ("no usable caption above grid" if not keys
                                               else "weak anchor (looks like a header row)"
                                               if not confident else "anchor not found in md")
                elif any(ispipe[hit:hit + args.window]):
                    verdict, why = "PRESENT", f"pipe table within {args.window} lines"
                else:
                    verdict, why = "MISSING", f"no pipe table within {args.window} lines"
                findings.append((pno, t, keys, hit, verdict, why, text))

        counts = {v: sum(1 for f in findings if f[4] == v)
                  for v in ("MISSING", "UNKNOWN", "PRESENT")}
        if counts["MISSING"] or counts["UNKNOWN"]:
            needs_attention = True
        print(f"{stem}: {len(findings)} bordered table(s) >= {args.min_cols} cols | "
              f"MISSING {counts['MISSING']}  UNKNOWN {counts['UNKNOWN']}  "
              f"PRESENT {counts['PRESENT']}")
        for pno, t, keys, hit, verdict, why, text in findings:
            if verdict == "PRESENT" and not args.verbose:
                continue
            loc = f"md line {hit + 1}" if hit is not None else "-"
            print(f"  {verdict:8} page {pno}: {t['cols']} cols | anchor {keys} "
                  f"-> {loc} | {why}")
            if args.verbose:
                print(f"      caption text: {text!r}")
    return 1 if needs_attention else 0


def cmd_grids(args):
    pdf_path, _ = resolve(args.stem)
    doc = fitz.open(pdf_path)
    pages = [args.page] if args.page is not None else range(doc.page_count)
    for pno in pages:
        page = doc[pno]
        h, v, dims = page_grid(page, dpi=args.dpi)
        tables = find_tables(h, v)
        print(f"page {pno}: raw h={len(h)} v={len(v)} raster={dims[1]}x{dims[0]}"
              f" -> {len(tables)} table(s)")
        for t in tables:
            print(f"   cols={t['cols']}  rows_ruled={t['rows_ruled']}"
                  f" (rows_ruled is unreliable; cluster text for real rows)")
            print(f"   bbox_px={t['bbox_px']}  v_px={t['v_px']}")
    return 0


def cmd_cells(args):
    pdf_path, _ = resolve(args.stem)
    page = fitz.open(pdf_path)[args.page]
    tables, dims = page_tables(page, dpi=args.dpi)
    if not tables:
        print(f"no bordered table found on page {args.page}")
        return 1
    for t in tables:
        grid = cells_by_column(page, t, dims)
        print(f"page {args.page}: {t['cols']} cols x {len(grid)} clustered row(s)")
        for r in grid:
            print("| " + " | ".join(c.replace("|", r"\|") or " " for c in r) + " |")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screen", help="Tier 0: bordered tables the Markdown lacks")
    s.add_argument("stems", nargs="+")
    s.add_argument("--window", type=int, default=15,
                   help="lines after the anchor to search for a pipe table")
    s.add_argument("--min-cols", type=int, default=3,
                   help="ignore grids narrower than this; 2 admits genuine "
                        "2-column tables but also multi-column page layouts")
    s.add_argument("--dpi", type=int, default=DPI)
    s.add_argument("-v", "--verbose", action="store_true",
                   help="also list tables that ARE present")
    s.set_defaults(func=cmd_screen)

    g = sub.add_parser("grids", help="Tier 1: grid geometry per page")
    g.add_argument("stem")
    g.add_argument("--page", type=int, default=None)
    g.add_argument("--dpi", type=int, default=DPI)
    g.set_defaults(func=cmd_grids)

    c = sub.add_parser("cells", help="Tier 2: column-bucketed OCR text")
    c.add_argument("stem")
    c.add_argument("--page", type=int, required=True)
    c.add_argument("--dpi", type=int, default=DPI)
    c.set_defaults(func=cmd_cells)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
