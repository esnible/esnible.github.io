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

# Left in a cell whose ink is not explained by OCR text, i.e. holds a figure.
# FIGURE_PLACEHOLDER renders, so a reader sees that artwork is missing; the
# accompanying HTML comment does not render and carries the source rect.
FIGURE_PLACEHOLDER = "*[figure]*"


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


def _cluster_vrules(v_rules, min_overlap=0.5):
    """Group vertical rules that share a y-extent, one group per table.

    A page may carry several stacked tables. Treating the page as one grid
    fails both ways: two tables whose spans happen to overlap merge into a
    single bogus column count, and two that do not cancel out entirely, because
    no rule covers half of the combined span. Clustering first avoids both.
    """
    clusters = []
    for r in sorted(v_rules, key=lambda r: r[1]):
        for c in clusters:
            cy0, cy1 = min(x[1] for x in c), max(x[2] for x in c)
            overlap = min(r[2], cy1) - max(r[1], cy0)
            if overlap > min_overlap * max(1, min(r[2] - r[1], cy1 - cy0)):
                c.append(r)
                break
        else:
            clusters.append([r])
    return clusters


def find_tables(h_rules, v_rules, min_overlap=0.5):
    """Find every table region on a page.

    Returns one dict per table, ordered top to bottom, with `cols` (reliable)
    and `rows_ruled` (NOT reliable -- interior horizontal rules are frequently
    absent, so rows must come from clustering word boxes; see
    cells_by_column()).
    """
    if len(h_rules) < 2 or len(v_rules) < 2:
        return []
    out = []
    for V in _cluster_vrules(v_rules, min_overlap):
        if len(V) < 3:
            continue
        y0, y1 = min(r[1] for r in V), max(r[2] for r in V)
        x0, x1 = min(r[0] for r in V), max(r[0] for r in V)
        pad = 0.02 * max(1, y1 - y0)
        # 0.35 rather than min_overlap: a header underline is often segmented by
        # sub-column dividers (IS_001 page 4's `OBVERSE MARKS` band) and fails a
        # half-width test despite being a genuine rule.
        H = [r for r in h_rules
             if y0 - pad <= r[0] <= y1 + pad
             and min(r[2], x1) - max(r[1], x0) > 0.35 * max(1, x1 - x0)]
        # One horizontal rule is enough. The vertical rules already bound the
        # table, and a table's bottom border is often lost at the page edge, so
        # demanding two drops real tables.
        if not H:
            continue
        out.append({
            "rows_ruled": max(0, len(H) - 1),
            "cols": len(V) - 1,
            "bbox_px": (x0, min(y0, min(r[0] for r in H)),
                        x1, max(y1, max(r[0] for r in H))),
            "v_px": [v[0] for v in V],
            "h_px": [r[0] for r in H],
        })
    return sorted(out, key=lambda t: t["bbox_px"][1])


def _word_count(page, table, dims):
    scale = page.rect.width / dims[1]
    x0, y0, x1, y1 = [c * scale for c in table["bbox_px"]]
    return sum(1 for w in page.get_text("words")
               if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1)


def page_tables(page, **kw):
    """Tables on a page, with photographs filtered out.

    A scanned photograph has strong rectangular edges and readily yields enough
    rules to look like a grid -- ONS_146 page 0 is two press photos that
    register as a 9-column table. Real tables carry text: measured across this
    corpus they run 3.7 to 22 words per column, while a photo scores 0. Requiring
    a modest word density separates them with a wide margin.
    """
    h, v, dims = page_grid(page, **kw)
    tables = [t for t in find_tables(h, v)
              if _word_count(page, t, dims) >= max(8, 1.5 * t["cols"])]
    return tables, dims


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

    def keys_of(blocks):
        text = " ".join(" ".join(b[4].split()) for b in blocks)[-60:]
        return text.strip(), re.findall(r"[A-Za-z]{4,}", text)[-3:]

    # Walk upward for the first candidate that is not just the table's own
    # header row. A grid whose nearest text is `REVERSE NOTES` often has a real
    # caption a line or two higher -- on IS_001 page 7 that is
    # `5 SEMI-AUTONOMOUS MAURYAN CITIES`, two blocks up.
    fallback = keys_of(above[-2:]) if above else ("", [])
    for depth in range(1, min(len(above), 6) + 1):
        text, words = keys_of(above[-depth - 1:len(above) - depth + 1] or above[-depth:])
        if words and not all(w.lower() in HEADERISH for w in words):
            return text, words, True
    return fallback[0], fallback[1], False


def anchor_match(lines, keys, max_span=60):
    """Best Markdown line for `keys`, or None.

    Keyword-anywhere matching is not enough: a long prose paragraph can contain
    every keyword by coincidence and outrank the real caption. On IS_001 the
    keys MAGADHAN/EMPIRE/CONTINUED match a prose line 63 lines before the
    actual `## MAGADHAN EMPIRE continued.` heading.

    So a candidate must contain the keywords within a compact span, and
    heading-like lines are preferred over body text.
    """
    if not keys:
        return None
    best = None
    for n, line in enumerate(lines):
        low = line.lower()
        pos = [low.find(k.lower()) for k in keys]
        if any(p < 0 for p in pos):
            continue
        span = max(p + len(k) for p, k in zip(pos, keys)) - min(pos)
        if span > max_span:
            continue                       # keywords scattered: coincidence
        score = (0 if line.lstrip().startswith("#") else 1, span, len(line))
        if best is None or score < best[0]:
            best = (score, n)
    return None if best is None else best[1]


def figure_mark(text, bbox, page_no, cell_words):
    """Annotate a cell that holds artwork.

    Emits a rendered placeholder so a reader can see something is missing, plus
    an HTML comment recording where the artwork lives in the source PDF, so it
    never has to be located again:

        *[figure]* <!-- figure page=3 rect=436.7,331.0,489.2,372.4 -->

    The rect is in PDF points and page-relative, so it stays valid at any DPI:

        fitz.open(pdf)[page].get_pixmap(dpi=300, clip=fitz.Rect(*rect))

    The placeholder goes before or after the caption to match the page: artwork
    usually sits above its caption, but not always.
    """
    rect = ",".join(f"{c:.1f}" for c in (bbox.x0, bbox.y0, bbox.x1, bbox.y1))
    mark = f"{FIGURE_PLACEHOLDER} <!-- figure page={page_no} rect={rect} -->"
    if not text:
        return mark
    above = cell_words and bbox.y1 <= min(w[1] for w in cell_words)
    return f"{mark} {text}" if above else f"{text} {mark}"


def _trim(mask, axis, rel=0.02):
    """First/last index along `axis` holding a non-trivial amount of ink.

    Trims scanner speckle so the reported rect hugs the artwork instead of the
    whole cell.
    """
    proj = mask.sum(axis=axis)
    if not proj.any():
        return None
    keep = np.flatnonzero(proj >= max(1, rel * proj.max()))
    return int(keep[0]), int(keep[-1])


def _figure_ink(page, dims, rect, words, thresh=THRESH, inset=3.0, pad=1.5):
    """Ink in a cell that no OCR word accounts for, with its bounding box.

    The page is one flat scan, so a figure is not an embedded image object --
    get_images() returns just the page scan. A figure is ink left over once
    every recognised word box is masked out. The rect is inset first so the
    cell's own ruling lines do not count as figure ink.

    Returns (fraction, pixel_count, bbox) where bbox is a fitz.Rect in PDF
    points, or None. Points are used deliberately: they are DPI-independent, so
    a stored rect stays valid however the page is later rendered.
    """
    r = fitz.Rect(rect.x0 + inset, rect.y0 + inset, rect.x1 - inset, rect.y1 - inset)
    if r.is_empty or r.width <= 0 or r.height <= 0:
        return 0.0, 0, None
    scale = dims[1] / page.rect.width
    pm = page.get_pixmap(dpi=int(72 * scale), colorspace=fitz.csGRAY, clip=r)
    if pm.width == 0 or pm.height == 0:
        return 0.0, 0, None
    g = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width)
    ink = g < thresh
    px = pm.width / r.width
    for w in words:
        wr = fitz.Rect(w[:4]) & r
        if wr.is_empty:
            continue
        x0 = max(0, int((wr.x0 - r.x0 - pad) * px))
        x1 = min(pm.width, int((wr.x1 - r.x0 + pad) * px))
        y0 = max(0, int((wr.y0 - r.y0 - pad) * px))
        y1 = min(pm.height, int((wr.y1 - r.y0 + pad) * px))
        ink[y0:y1, x0:x1] = False
    count = int(ink.sum())
    if not count:
        return 0.0, 0, None
    xs, ys = _trim(ink, 0), _trim(ink, 1)
    bbox = None
    if xs and ys:
        bbox = fitz.Rect(r.x0 + xs[0] / px, r.y0 + ys[0] / px,
                         r.x0 + (xs[1] + 1) / px, r.y0 + (ys[1] + 1) / px)
    return float(count) / ink.size, count, bbox


def cell_has_figure(page, dims, rect, words, min_frac=0.012, min_px=150):
    """(found, fraction, pixel_count, bbox_in_points) for one cell."""
    frac, count, bbox = _figure_ink(page, dims, rect, words)
    return (frac >= min_frac and count >= min_px and bbox is not None,
            frac, count, bbox)


def cells_by_column(page, table, dims, row_gap=1.6, mark_figures=True):
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
        top = min(w[1] for w in band_words)
        bot = max(w[3] for w in band_words)
        cells = [""] * (len(v) - 1)
        for i in range(len(v) - 1):
            inside = [w for w in band_words if v[i] <= (w[0] + w[2]) / 2 < v[i + 1]]
            inside.sort(key=lambda w: (round(w[1] / max(1.0, line_h * 0.6)), w[0]))
            cells[i] = " ".join(w[4] for w in inside).strip()
            if mark_figures:
                rect = fitz.Rect(v[i], top, v[i + 1], bot)
                # every word overlapping the cell rect, not just this band's --
                # a figure often sits between two rows' text lines
                near = [w for w in page.get_text("words")
                        if fitz.Rect(w[:4]).intersects(rect)]
                found, _, _, bbox = cell_has_figure(page, dims, rect, near)
                if found:
                    cells[i] = figure_mark(cells[i], bbox, page.number, inside)
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
                hit = anchor_match(lines, keys) if confident else None
                if hit is None:
                    verdict, why = "UNKNOWN", ("no usable caption above grid" if not keys
                                               else "weak anchor (looks like a header row)"
                                               if not confident else "anchor not found in md")
                else:
                    # Widest pipe row near the anchor. Presence alone is not
                    # enough: pdfmd often leaves a mangled 2-3 column fragment
                    # where a wide table belongs, and treating that as the table
                    # yields a false PRESENT -- the one error that silently ends
                    # the investigation.
                    near = [lines[n].count("|") - 1
                            for n in range(hit, min(len(lines), hit + args.window))
                            if ispipe[n]]
                    md_cols = max(near) if near else 0
                    if not md_cols:
                        verdict, why = "MISSING", f"no pipe table within {args.window} lines"
                    elif md_cols < args.col_ratio * t["cols"]:
                        verdict, why = ("MISSING",
                                        f"nearby table has {md_cols} cols, PDF grid has "
                                        f"{t['cols']} -- looks like a fragment")
                    else:
                        verdict, why = "PRESENT", f"{md_cols}-col table within {args.window} lines"
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
    s.add_argument("--col-ratio", type=float, default=0.6,
                   help="a nearby Markdown table must have at least this "
                        "fraction of the PDF grid's columns to count as PRESENT")
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
