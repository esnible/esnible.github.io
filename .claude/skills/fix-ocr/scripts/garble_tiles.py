#!/usr/bin/env python3
"""Put a file's suspect words in front of a reader at the scan's own pixels.

Reading garble off the page one render at a time costs a whole page image
per word, and a render at a fixed 300 dpi of a 72-dpi scan is four parts
interpolation to one part evidence. This screen does the opposite: it finds
the words worth looking at, cuts each one -- with a word of context either
side -- out of the page image at its native resolution, and packs the tiles
onto a few labelled sheets. The reader answers only for the tiles whose
reading differs from the OCR; silence accepts it.

    garble_tiles.py candidates ONS_159          # counts only, no images
    garble_tiles.py sheets ONS_159              # writes sheets + manifest
    garble_tiles.py edits ONS_159 replies.txt   # replies -> apply_edits.py input

A word is a candidate when the evidence disagrees about it:

  - `cspell` does not know it, and the PDF's own text layer -- a second,
    independent OCR of the same page -- does not spell it the same way; or
  - the two OCRs read it differently, whether or not either is a word.

A non-word both engines read identically is probably printed that way (a
rare name, a transliteration) and is left out unless `--agreed` is given. So is a real word in the Markdown
whose text-layer counterpart is a non-word: the garble is on the other side.
Foreign-script words are tiled too, unless their line already carries a
`script-ok`/`script-guess`/`script-deferred` marker: the reader writes the
reading in, flagged, rather than leaving it for a later pass to look again.

**The text layer is a locator and a second opinion, never an authority.**
Its boxes say where to cut; its reading is shown beside the Markdown's in
the manifest. The tile decides.

Pixels. A page whose scan is one axis-aligned image is cut straight out of
that image, pixel for pixel. A deskewed page (the image is placed with a
slight rotation) is rendered at exactly the image's own resolution, which is
the nearest thing to its pixels the PDF can give. Nothing is ever
interpolated: a scan under 200 dpi is enlarged by a whole number, each of
its pixels drawn as an exact block, so a 72-dpi word is big enough to look
at but shows only what the scan holds.

Replies, one per line, `ID reading`:

    a7 Sasaman
    b12 1,000 Muhammad      # a reading may be several words
    c3 ?                    # unreadable: left alone, listed for the user
    a9 Sasa man => Sasaman  # echo the span: refused if the manifest disagrees
    L486 ^jJï => قلوغ        # a reading beside a tile, by line: `old` must be
                            # on that line once

The reading replaces the tile's highlighted span -- the exact Markdown text
the manifest prints between the guillemets -- so markup in that span must be
carried over. `edits` turns replies into whole-line `old => new` edits,
one per changed line, for `apply_edits.py`, which checks and applies them
all or nothing.
"""
import argparse
import bisect
import difflib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

try:
    import pymupdf
except ImportError as exc:                                   # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs PyMuPDF "
             f"(see .claude/skills/requirements.txt).")
from PIL import Image, ImageDraw, ImageFont

PDF_DIR = Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()
REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_ROOT = Path("/tmp/garble-tiles")

SHEET_SIDE = 1568       # the API shrinks a longer edge, so stay under it
LABEL_W = 44            # the ID column to the left of each tile
GAP = 4                 # pixels between tiles
LABEL_PT = 16           # the ID's type size
MARK_H = 3              # the bar under the suspect span, below the crop
MIN_DPI = 200           # below this a scan's tiles are enlarged, n-by-n
WEAK = 0.6              # a page matching less than this is read by tesseract
TALL = 2.0              # a crop taller than this many lines is not a word
INK = 0.004             # a crop with less dark ink than this missed the word
PAD = 0.1               # of a line height above and below; 4x that across

try:
    FONT = ImageFont.load_default(size=16)
except TypeError:                                            # Pillow < 10.1
    FONT = ImageFont.load_default()


def fold(tok):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", tok).lower())


def plain(tok):
    """A token's letters and digits, case kept: what the two OCRs compare."""
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", tok)).replace("_", "")


def foreign(tok):
    return any(ord(c) > 0x2FF and unicodedata.category(c).startswith("L")
               for c in tok)


# --- the Markdown ---------------------------------------------------------

def md_tokens(text):
    """[(start, end, token, line)] for the words of the prose.

    HTML comments and the `[Original PDF]` header are not page text; a token
    inside one is never a candidate and never aligned.
    """
    hidden = [(m.start(), m.end()) for m in re.finditer(r"<!--.*?-->", text, re.S)]
    toks, h, line, last = [], 0, 1, 0
    for m in re.finditer(r"\S+", text):
        while h < len(hidden) and hidden[h][1] <= m.start():
            h += 1
        if h < len(hidden) and hidden[h][0] <= m.start() < hidden[h][1]:
            continue
        line += text.count("\n", last, m.start())
        last = m.start()
        if line == 1 and text.startswith("[Original PDF]"):
            continue
        if m.group() in ("*[figure]*",) or not plain(m.group()):
            continue
        toks.append((m.start(), m.end(), m.group(), line))
    return toks


def cspell_unknown(path):
    """{(line, col)} cspell reports, 1-based both, as it prints them."""
    try:
        out = subprocess.run(
            ["cspell", "--config", str(REPO_ROOT / "cspell.config.yaml"),
             "--no-progress", "--no-summary", str(path)],
            capture_output=True, text=True, cwd=REPO_ROOT).stdout
    except FileNotFoundError:
        sys.exit("cspell is not on PATH")
    hits = set()
    for m in re.finditer(r":(\d+):(\d+) - (?:Unknown|Forbidden) word", out):
        hits.add((int(m.group(1)), int(m.group(2))))
    return hits


def cspell_words(words):
    """The subset of `words` cspell does not know."""
    if not words:
        return set()
    out = subprocess.run(
        ["cspell", "--config", str(REPO_ROOT / "cspell.config.yaml"),
         "--no-progress", "--no-summary", "--words-only", "--unique", "stdin"],
        input="\n".join(words), capture_output=True, text=True, cwd=REPO_ROOT).stdout
    return set(out.split())


# --- the scan -------------------------------------------------------------

class Scan:
    def __init__(self, stem):
        pdf = PDF_DIR / f"{stem}.pdf"
        if not pdf.exists():
            sys.exit(f"no scan for {stem}: {pdf}\nset ONS_ARCHIVE_DIR")
        self.stem = stem
        self.doc = pymupdf.open(pdf)
        self.words = []          # (page, x0, y0, x1, y1, text)
        for p, page in enumerate(self.doc):
            for w in page.get_text("words", sort=False):
                if plain(w[4]):
                    self.words.append((p, *w[:5]))
        self._images = {}
        self._heights = {}

    def line_height(self, page_no):
        """The page's median word height, in points."""
        if page_no not in self._heights:
            hs = sorted(w[4] - w[2] for w in self.words if w[0] == page_no)
            self._heights[page_no] = hs[len(hs) // 2] if hs else 12.0
        return self._heights[page_no]

    def weak_pages(self, exact, where, floor=WEAK):
        """Pages too little of whose text layer matched the Markdown exactly.

        Some scans' OCR layers are font-encoded noise (`gSIp[I[FIcp`) on
        whole pages: nothing on them can be placed by the text layer.
        """
        used = {}
        for k in exact:
            p = self.words[where[k][0]][0]
            used[p] = used.get(p, 0) + 1
        total = {}
        for w in self.words:
            total[w[0]] = total.get(w[0], 0) + 1
        return {p for p in range(self.doc.page_count)
                if total.get(p, 0) < 20 or used.get(p, 0) < floor * total[p]}

    def reread(self, pages):
        """Replace those pages' words with tesseract's, from the cached
        `locate_on_page.py` index (built on first use, CPU only)."""
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import locate_on_page
        index = locate_on_page.load_index(self.stem)
        keep = [w for w in self.words if w[0] not in pages]
        for entry in index:
            p = entry["page"]
            if p not in pages:
                continue
            k = 72 / entry["dpi"]
            for w in entry["words"]:
                if plain(w["t"]):
                    keep.append((p, w["x"] * k, w["y"] * k, (w["x"] + w["w"]) * k,
                                 (w["y"] + w["h"]) * k, w["t"]))
        self.words = sorted(keep, key=lambda w: w[0])     # stable: page order only
        self._heights = {}

    def native(self, page_no):
        """(image, sx, sy, ox, oy, dpi) for the page's pixels, or None.

        `sx`, `sy` are pixels per PDF point and `ox`, `oy` where the image's
        corner sits on the page. A scan with an invisible OCR layer (text
        render mode 3) is cut from its own embedded image when that image is
        placed square; a deskewed one is rendered at the image's own dpi. A
        page whose text is drawn visibly is typeset, not scanned, and is
        rendered: vector glyphs have no native pixels to preserve.
        """
        if page_no in self._images:
            return self._images[page_no]
        page = self.doc[page_no]
        area = page.rect.width * page.rect.height
        best = None
        for info in page.get_image_info(xrefs=True):
            x0, y0, x1, y1 = info["bbox"]
            if (x1 - x0) * (y1 - y0) > 0.8 * area and info["xref"]:
                best = info
        visible = any(t["type"] != 3 for t in page.get_texttrace())
        if best is None and not visible:
            self._images[page_no] = None
            return None
        img = None
        if best and not visible:
            x0, y0, x1, y1 = best["bbox"]
            sx, sy = best["width"] / (x1 - x0), best["height"] / (y1 - y0)
            dpi = round(72 * sx)
            a, b, c, d, _e, _f = best["transform"]
            if abs(b) < 1e-3 and abs(c) < 1e-3 and a > 0 and d > 0 \
                    and page.rotation == 0:
                try:
                    pix = pymupdf.Pixmap(self.doc, best["xref"])
                    if pix.alpha or pix.n != 1:
                        pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
                    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                    ox, oy = x0, y0
                except Exception:
                    img = None
        else:
            dpi = 300 if visible else round(72 * best["width"] / (best["bbox"][2] - best["bbox"][0]))
        if img is None:
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            sx, sy = pix.width / page.rect.width, pix.height / page.rect.height
            ox = oy = 0
        self._images[page_no] = (img, sx, sy, ox, oy, dpi)
        return self._images[page_no]

    def zoom(self, page_no):
        """The whole-number factor that brings a page's x-height up to a
        size a reader can resolve: 1 for any scan of 150 dpi or more."""
        got = self.native(page_no)
        return 1 if got is None else max(1, round(MIN_DPI / got[5]))

    def tile(self, page_no, box, mark):
        """A PIL image of `box` (PDF points) at native pixels, with `mark`
        (x0, x1 in points) underlined in a strip below the crop.

        A low-resolution scan is enlarged by a whole number with
        nearest-neighbour sampling: each scan pixel becomes an exact n-by-n
        block, so the tile is bigger but holds no value the scan did not.
        """
        got = self.native(page_no)
        if got is None:
            return None
        img, sx, sy, ox, oy, _dpi = got
        x0, y0, x1, y1 = box
        crop = img.crop((max(0, round((x0 - ox) * sx)),
                         max(0, round((y0 - oy) * sy)),
                         min(img.width, round((x1 - ox) * sx)),
                         min(img.height, round((y1 - oy) * sy))))
        n = self.zoom(page_no)
        if n > 1:
            crop = crop.resize((crop.width * n, crop.height * n), Image.NEAREST)
        out = Image.new("L", (crop.width, crop.height + MARK_H + 1), 255)
        out.paste(crop, (0, 0))
        left = max(0, round((mark[0] - x0) * sx * n))
        right = min(crop.width, round((mark[1] - x0) * sx * n))
        ImageDraw.Draw(out).rectangle(
            (left, crop.height + 1, max(left + 1, right), crop.height + MARK_H), fill=0)
        return out


# --- candidates -----------------------------------------------------------

REACH = 40              # how far past an unaligned run its words are sought
SMALL = 3               # a replaced run this short is a word-for-word swap


def align(toks, words):
    """md index -> (lo, hi) text-layer words, and the md indices whose match
    is exact.

    Equal runs map one to one. A short replaced run -- `Sasa man` against
    `Sasaman`, `modem` against `modern` -- maps proportionally, which is
    exact for the one-for-one swap and close enough for a split or a join.
    A long one is a passage the two OCRs did not read alike at all (a table,
    a legend, a page whose text layer is font-encoded noise) and maps to
    nothing: a proportional guess there lands on unrelated words.
    """
    a = [fold(t[2]) for t in toks]
    b = [fold(w[5]) for w in words]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    where, exact = {}, set()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                where[i1 + k] = (j1 + k, j1 + k + 1)
                exact.add(i1 + k)
        elif op == "replace" and i2 - i1 <= SMALL and j2 - j1 <= SMALL:
            n, m = i2 - i1, j2 - j1
            for k in range(n):
                lo = j1 + (k * m) // n
                hi = max(lo + 1, j1 + ((k + 1) * m + n - 1) // n)
                where[i1 + k] = (lo, hi)
        elif op in ("replace", "delete"):
            pin(a, b, i1, i2, max(0, j1 - REACH), min(len(b), j2 + REACH),
                where, exact)
    return where, exact


def pin(a, b, i1, i2, j1, j2, where, exact):
    """Place what can be placed inside a long unaligned run.

    Columns the two OCRs read in a different order (a masthead, a two-column
    page) leave a run the diff cannot align, though most of its words are
    there. A word is pinned where its two neighbours sit either side of one
    word in the text layer, once only in reach; a word the two read alike
    is then exact.
    """
    trio = {}
    for j in range(max(1, j1), min(len(b) - 1, j2)):
        trio.setdefault((b[j - 1], b[j + 1]), []).append(j)
    for k in range(max(1, i1), min(len(a) - 1, i2)):
        if k in where:
            continue
        hits = trio.get((a[k - 1], a[k + 1]), [])
        if len(hits) == 1:
            where[k] = (hits[0], hits[0] + 1)
            if a[k] == b[hits[0]]:
                exact.add(k)


def same_line(u, v):
    h = min(u[4] - u[2], v[4] - v[2])
    return u[0] == v[0] and abs(u[2] - v[2]) < 0.6 * h


def bracket(scan, toks, exact, where, span):
    """(page, box, mark) for a span with no reading of its own in the text
    layer, from the exactly-matched words either side of it on its line.

    Without both neighbours on one printed line the crop would be a guess,
    and a crop of the wrong words is worse than none.
    """
    k0, k1 = span[0], span[-1]
    p = next((k for k in range(k0 - 1, max(-1, k0 - 6), -1) if k in exact), None)
    q = next((k for k in range(k1 + 1, min(len(toks), k1 + 6)) if k in exact), None)
    if p is None or q is None:
        return None
    u, v = scan.words[where[p][0]], scan.words[where[q][0]]
    if not same_line(u, v) or v[1] <= u[3]:
        return None
    box = (u[1], min(u[2], v[2]), v[3], max(u[4], v[4]))
    return u[0], box, (u[3] + 1, v[1] - 1)


def candidates(stem, agreed=False, tesseract=True):
    path = REPO_ROOT / "jons" / f"{stem}.md"
    text = path.read_text(encoding="utf-8")
    toks = md_tokens(text)
    scan = Scan(stem)
    where, exact = align(toks, scan.words)
    if tesseract:
        weak = scan.weak_pages(exact, where)
        if weak:
            scan.reread(weak)
            where, exact = align(toks, scan.words)
    else:
        weak = set()
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
    starts = [t[0] for t in toks]
    spell = set()
    for line, col in cspell_unknown(path):
        off = line_starts[line - 1] + col - 1
        k = bisect.bisect_right(starts, off) - 1
        if 0 <= k < len(toks) and toks[k][0] <= off < toks[k][1]:
            spell.add(k)

    stats = {"weak": sorted(weak), "tokens": len(toks), "foreign": 0, "agreed": 0,
             "cspell": 0, "disagree": 0, "pdf garble": 0, "unplaced": 0}
    pending = []
    for k, (s, e, tok, line) in enumerate(toks):
        if foreign(tok):
            # A reading already marked script-ok/guess/deferred has been
            # looked at; raw foreign-script OCR has not, and is tiled like
            # any other garble.
            ls = text.rfind("\n", 0, s) + 1
            le = text.find("\n", s)
            if "<!-- script-" in text[ls:le if le >= 0 else len(text)]:
                stats["foreign"] += 1
                continue
            if k not in spell:
                spell.add(k)
        pdf = (" ".join(w[5] for w in scan.words[slice(*where[k])])
               if k in where else None)
        if k in exact:
            # Both engines read the same letters, and a non-word they agree
            # on is probably printed that way.
            if k in spell and not agreed:
                stats["agreed"] += 1
                continue
            if k not in spell:
                continue
        elif k not in spell:
            if pdf is None or plain(tok).lower() == plain(pdf).lower():
                continue    # unaligned, or a difference of case alone
        pending.append((k, pdf))

    # A real word in the Markdown against a non-word in the text layer is
    # the text layer's garble, not ours. A real word against another real
    # word is the confusion cspell cannot see, and stays. Lowercased, since
    # cspell splits `earUer` at the capital and passes both halves.
    def letters(pdf):
        return re.findall(r"[^\W\d_]+", pdf.lower())
    unknown = cspell_words(sorted({w for k, pdf in pending if k not in spell
                                   for w in letters(pdf)}))
    sus = []
    for k, pdf in pending:
        if k in spell:
            stats["cspell"] += 1
        elif any(w in unknown for w in letters(pdf)) \
                or not re.search(r"[^\W\d_]", pdf):
            stats["pdf garble"] += 1
            continue
        else:
            stats["disagree"] += 1
        sus.append(k)

    # Neighbouring suspects become one span: a reader settles `Sasa man` as
    # one word, not two.
    spans = []
    for k in sus:
        if spans and k == spans[-1][-1] + 1 and toks[k][3] == toks[spans[-1][-1]][3]:
            spans[-1].append(k)
        else:
            spans.append([k])

    out = []
    for span in spans:
        core = [j for k in span if k in where for j in range(*where[k])]
        placed = None
        if core and all(scan.words[j][0] == scan.words[core[0]][0] for j in core) \
                and all(same_line(scan.words[core[0]], scan.words[j]) for j in core):
            page = scan.words[core[0]][0]
            cb = [scan.words[j] for j in core]
            mark = (min(b[1] for b in cb), max(b[3] for b in cb))
            nb = [scan.words[where[k][0]] for k in (span[0] - 1, span[-1] + 1)
                  if k in exact and same_line(scan.words[where[k][0]], cb[0])]
            boxes = cb + nb
            # The height comes from the neighbours both OCRs agree on when
            # there are any: a garbled word's own box is as unreliable as
            # its letters, and has been seen to sit between printed lines.
            rows = nb or cb
            box = (min(b[1] for b in boxes), min(b[2] for b in rows),
                   max(b[3] for b in boxes), max(b[4] for b in rows))
            if box[3] - box[1] <= TALL * scan.line_height(page):
                placed = (page, box, mark, " ".join(b[5] for b in cb))
        else:
            got = bracket(scan, toks, exact, where, span)
            if got:
                placed = (*got, None)
        if placed is None:
            stats["unplaced"] += 1
            continue
        page, box, mark, pdf = placed
        h = box[3] - box[1]
        box = (box[0] - 4 * PAD * h, box[1] - PAD * h,
               box[2] + 4 * PAD * h, box[3] + PAD * h)
        s, e = toks[span[0]][0], toks[span[-1]][1]
        out.append({
            "line": toks[span[0]][3], "start": s, "end": e,
            "md": text[s:e], "pdf": pdf,
            "spell": any(k in spell for k in span),
            "page": page, "box": box, "mark": mark,
        })
    return scan, out, stats


# --- sheets ---------------------------------------------------------------

def pack(scan, cands, stem, outdir):
    """Shelf-pack the tiles onto sheets no side of which exceeds SHEET_SIDE."""
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob(f"{stem}-*.png"):
        old.unlink()
    tiles = []
    blank = []
    for c in cands:
        got = scan.tile(c["page"], c["box"], c["mark"])
        if got is None:
            continue
        body = got.crop((0, 0, got.width, got.height - MARK_H - 1))
        dark = sum(body.point(lambda v: 255 if v < 128 else 0).histogram()[255:])
        if dark < INK * body.width * body.height:
            blank.append(c)     # the box landed between printed lines
            continue
        tiles.append((c, got))
    sheets, manifest = [], []
    sheet_no, x, y, shelf, placed = 0, 0, 0, 0, []

    def flush():
        nonlocal sheet_no, placed
        if not placed:
            return
        h = max(py + im.height for _l, _px, py, im in placed)
        w = max(px + LABEL_W + im.width for _l, px, py, im in placed)
        sheet = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(sheet)
        for label, px, py, im in placed:
            sheet.paste(im, (px + LABEL_W, py))
            draw.text((px + 2, py + max(0, im.height // 2 - LABEL_PT // 2)),
                      label, fill=0, font=FONT)
            draw.line((px, py + im.height + GAP // 2,
                       px + LABEL_W + im.width, py + im.height + GAP // 2), fill=200)
        out = outdir / f"{stem}-{sheet_no + 1}.png"
        sheet.save(out, optimize=True)
        sheets.append(out)
        sheet_no += 1
        placed = []

    letters = "abcdefghijklmnopqrstuvwxyz"
    n_on_sheet = 0
    for c, im in tiles:
        im = im.crop((0, 0, min(im.width, SHEET_SIDE - LABEL_W), im.height))
        need = LABEL_W + im.width
        if x + need > SHEET_SIDE:
            x, y, shelf = 0, y + shelf + GAP, 0
        if y + im.height > SHEET_SIDE:
            flush()
            x, y, shelf, n_on_sheet = 0, 0, 0, 0
        label = f"{letters[sheet_no % 26]}{n_on_sheet + 1}"
        n_on_sheet += 1
        placed.append((label, x, y, im))
        manifest.append(dict(c, id=label, sheet=sheet_no + 1))
        x += need + GAP
        shelf = max(shelf, im.height)
    flush()
    (outdir / f"{stem}.json").write_text(json.dumps(manifest, indent=0))
    return sheets, manifest, blank


def show(m):
    """One manifest line: the Markdown span, and the text layer's if different."""
    if m["pdf"] is None:
        alt = "  pdf:-"
    else:
        alt = "" if plain(m["pdf"]) == plain(m["md"]) else f"  pdf:{m['pdf']}"
    return f"{m['id']} L{m['line']} «{m['md']}»{alt}"


# --- replies --------------------------------------------------------------

def edits(stem, replies, outdir):
    """`old => new` lines for apply_edits.py, one per changed Markdown line.

    Every reply is applied to a copy of the file first, last span first so
    the manifest's offsets stay good, and each changed line is then written
    out whole. Two readings on one line therefore make one edit, not two
    that overlap. Besides tile IDs a reply may name a line directly,
    `L486 ^jJï => قلوغ`, for a reading the eye found next to a tile: its
    `old` must occur on that line exactly once.
    """
    text = (REPO_ROOT / "jons" / f"{stem}.md").read_text(encoding="utf-8")
    man = {m["id"]: m for m in json.loads((outdir / f"{stem}.json").read_text())}
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    spans, unread, bad = {}, [], 0
    for raw in replies:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        tid, _, reading = line.strip().partition(" ")
        said = None
        # `a7 Sasa man => Sasaman` names the span it means to replace, which
        # catches a reply written against an older manifest.
        if " => " in reading:
            said, reading = reading.split(" => ", 1)
            said = said.strip()
        if re.fullmatch(r"L\d+", tid):
            n = int(tid[1:])
            body = text[starts[n - 1]:starts[n] - 1 if n < len(starts) else len(text)]
            if said is None or body.count(said) != 1:
                print(f"# {tid}: «{said}» is not on that line exactly once", file=sys.stderr)
                bad += 1
                continue
            s0 = starts[n - 1] + body.index(said)
            spans[(s0, s0 + len(said))] = (tid, reading.strip())
            continue
        if tid not in man:
            print(f"# unknown id {tid}", file=sys.stderr)
            bad += 1
            continue
        m = man[tid]
        if said is not None and said != m["md"]:
            print(f"# {tid} is «{m['md']}» in the manifest, not «{said}»; skipped",
                  file=sys.stderr)
            bad += 1
            continue
        if reading.strip() == "?":
            unread.append(m)
            continue
        if text[m["start"]:m["end"]] != m["md"]:
            print(f"# {tid}: the file changed since the sheets were cut", file=sys.stderr)
            bad += 1
            continue
        spans[(m["start"], m["end"])] = (tid, reading.strip())

    order = sorted(spans)
    for (s0, e0), (s1, _e1) in zip(order, order[1:]):
        if s1 < e0:
            sys.exit(f"{spans[(s0, e0)][0]} and {spans[(s1, _e1)][0]} overlap; "
                     f"merge them into one reply")
    new = text
    for s0, e0 in reversed(order):
        new = new[:s0] + spans[(s0, e0)][1] + new[e0:]
    a, b = text.split("\n"), new.split("\n")
    if len(a) != len(b):
        sys.exit("a reading holds a line break; nothing written")
    out = []
    for n, (x, y) in enumerate(zip(a, b), 1):
        if x == y:
            continue
        if text.count(x) != 1:
            print(f"# L{n} repeats verbatim elsewhere; edit it by hand", file=sys.stderr)
            bad += 1
            continue
        out.append(f"{x} => {y}")
    for m in unread:
        out.append(f"# unread {m['id']} L{m['line']} {m['md']}")
    if bad:
        print(f"# {bad} reply(ies) not used", file=sys.stderr)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("candidates", "sheets", "edits"))
    ap.add_argument("stem")
    ap.add_argument("replies", nargs="?", help="for `edits`: replies file (default stdin)")
    ap.add_argument("--agreed", action="store_true",
                    help="also tile non-words both OCRs read identically")
    ap.add_argument("--only-spell", action="store_true",
                    help="tile only cspell hits, not bare OCR disagreements")
    ap.add_argument("--no-tesseract", action="store_true",
                    help="never fall back to tesseract's boxes for pages whose\n"
                         "text layer does not match the Markdown")
    ap.add_argument("--anyway", action="store_true",
                    help="tile a born-digital file regardless")
    ap.add_argument("--out", type=Path, help=f"default {OUT_ROOT}/<STEM>")
    args = ap.parse_args(argv)
    stem = Path(args.stem).stem
    outdir = args.out or OUT_ROOT / stem

    if args.cmd == "edits":
        with open(args.replies, encoding="utf-8") if args.replies else sys.stdin as fh:
            print("\n".join(edits(stem, fh, outdir)))
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import classify_source
    verdict, note = classify_source.classify(PDF_DIR / f"{stem}.pdf")
    if verdict == "BORN-DIGITAL" and not args.anyway:
        print(f"{stem}: {verdict} ({note}). Its text was never OCR'd, so a "
              f"disagreement with the Markdown is pdfmd's, not the page's. "
              f"Pass --anyway to tile it regardless.")
        return 2
    scan, cands, stats = candidates(stem, args.agreed, not args.no_tesseract)
    if args.only_spell:
        cands = [c for c in cands if c["spell"]]
    print(f"{stem}: {stats['tokens']} words; tiles {len(cands)} "
          f"(cspell {stats['cspell']}, OCRs disagree {stats['disagree']}); "
          f"skipped: both OCRs agree {stats['agreed']}, foreign script "
          f"{stats['foreign']} (already marked), text layer garbled {stats['pdf garble']}, "
          f"unplaced {stats['unplaced']}"
          + (f"; tesseract boxes on p{','.join(map(str, stats['weak']))}"
             if stats["weak"] else ""))
    if args.cmd == "candidates":
        return 0
    sheets, manifest, blank = pack(scan, cands, stem, outdir)
    for c in blank:
        print(f"no ink where the text layer puts L{c['line']} «{c['md']}» (p{c['page']}); not tiled")
    res = sorted({scan.native(p)[5] for p in {c["page"] for c in cands}
                  if scan.native(p)})
    zooms = sorted({scan.zoom(c["page"]) for c in cands} - {1})
    print(f"native {', '.join(map(str, res))} dpi"
          + (f" (shown x{', x'.join(map(str, zooms))}, nearest-neighbour)" if zooms else "")
          + f"; manifest {outdir / (stem + '.json')}")
    for s in sheets:
        w, h = Image.open(s).size
        print(f"{s}  {w}x{h}  ~{w * h // 750} tokens")
    sheet = 0
    for m in manifest:
        if m["sheet"] != sheet:
            sheet = m["sheet"]
            print(f"-- sheet {sheet}")
        print(show(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
