#!/usr/bin/env python3
"""Stack the evidence for a file's findings onto a few page crops.

Every screen in this repo that reports against the scan has the same problem
once someone goes to settle its findings: one render per finding. Forty
findings is forty renders, and an agent doing the reading pays for each in
images *and* in tool calls. The quote screen's sheets cut that to one image
per five or six findings, and nothing in the cutting is quote-specific.

So it lives here. Give it a file's stem and a row per finding -- a label and
the text to find on the page -- and it writes tall labelled JPEGs, merging
the bands of findings that share a printed line:

    crop_sheets.py sheets ONS_166 --rows findings.tsv
    printf 'line 94 heading\tMichael Willis, Who built\n' | crop_sheets.py sheets ONS_166

Each row is `label<TAB>anchor`, where the anchor is text from the Markdown
near the finding; its words are matched against the page's own text layer,
which is garbled in exactly the places a screen reports, so the match is
fuzzy. **A crop is a located guess, not a promise**: a row that cannot be
placed says why and shows no band rather than showing the wrong part of the
scan. Check that the Markdown and the band are the same sentence before
trusting either.

Importers get the same thing as `locate(...)` and `stack(...)`; see
`fix-ocr/scripts/quote_crops.py`, which builds both these sheets and an HTML
one for a person, from the same placements.
"""
import argparse
import base64
import os
import re
import sys
import unicodedata
import difflib
from pathlib import Path

try:
    import pymupdf
except ImportError as exc:                                   # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs PyMuPDF "
             f"(see .claude/skills/requirements.txt).")

PDF_DIR = Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()
REPO_ROOT = Path(__file__).resolve().parents[3]
WORDS_BEFORE = 7        # anchor a band on the words leading up to the finding
WORDS_WIDE = 18         # ... and on this many when seven match several pages
PAD_LINES = 1.2         # printed lines of context above and below a band
STACK_WIDTH = 1500      # pixels across a sheet
STACK_LABEL = 26        # the caption strip above each band, in those pixels
BAND_MERGE = 2.2        # a merged band may grow to this much of one band
MAX_BAND = 900          # a band taller than this is scaled down to fit it
MAX_SHEET = 4200        # ... and a sheet is cut here, however few bands it has


def laid_out(sizes, per_sheet, max_band=None, max_sheet=None):
    """Pack bands into sheets, by height as well as by count.

    A band is as tall as its crop: a line of prose is 120 pixels and a
    full-page table 2,000, so a fixed count of bands per sheet can produce a
    sheet 10,000 pixels tall -- which costs the reader more than the separate
    renders it was meant to replace. A band taller than MAX_BAND is scaled
    down whole (it is a figure or a grid, and the question asked of it is
    whether it is there, not what it says), and a sheet is cut at MAX_SHEET.
    """
    max_band = max_band or MAX_BAND
    max_sheet = max_sheet or MAX_SHEET
    sheets, chunk, height = [], [], 0.0
    for item, tall in sizes:
        scale = min(1.0, max_band / tall)
        tall, width = tall * scale, STACK_WIDTH * scale
        if chunk and (len(chunk) >= per_sheet
                      or height + tall + STACK_LABEL > max_sheet):
            sheets.append(chunk)
            chunk, height = [], 0.0
        chunk.append((item, width, tall))
        height += tall + STACK_LABEL
    if chunk:
        sheets.append(chunk)
    return sheets


def fold(tok):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", tok).lower())


def alike(a, b):
    """Near-equality, because the Markdown's own garble never matches exactly."""
    if not a or not b:
        return False
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


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

    def clip(self, page_no, boxes):
        """The band to show: the located words, plus a line above and below."""
        page = self.doc[page_no]
        height = max(b[3] - b[1] for b in boxes)
        return pymupdf.Rect(
            max(0, min(b[0] for b in boxes) - 40),
            max(0, min(b[1] for b in boxes) - PAD_LINES * height),
            min(page.rect.width, max(b[2] for b in boxes) + 220),
            min(page.rect.height, max(b[3] for b in boxes) + PAD_LINES * height))

    def clip_rect(self, page_no, rect, pad=14.0):
        """A region a screen measured for itself, with a little air round it."""
        page = self.doc[page_no]
        x0, y0, x1, y1 = rect
        return pymupdf.Rect(max(0, x0 - pad), max(0, y0 - pad),
                            min(page.rect.width, x1 + pad),
                            min(page.rect.height, y1 + pad))

    def locate_on(self, page_no, text):
        """Boxes for `text` on a page already known, however short the text.

        A screen that reports against a page line knows which page it is, so
        the fuzzy search over the whole file has nothing to add -- and a head
        is often two words (`fig. 2`, `Beischlage`), under the minimum the
        fuzzy anchor needs to be safe. Here the text layer is searched
        directly, then by its first words, then by its longest word.
        """
        if not 0 <= page_no < self.doc.page_count:
            return None, (f"p{page_no} is not in a {self.doc.page_count}-page "
                          f"scan -- pages are counted from 0 here")
        page = self.doc[page_no]
        probe = " ".join(text.split())[:60]
        words = probe.split()
        tries = [probe, " ".join(words[:4])]
        if words:
            tries.append(max(words, key=len))
        for attempt in tries:
            if len(attempt) < 3:
                continue
            hits = page.search_for(attempt)
            if hits:
                r = hits[0]
                return page_no, [(r.x0, r.y0, r.x1, r.y1, attempt)]
        return None, f"p{page_no} does not have that text in its layer"

    def crop(self, page_no, boxes, dpi, quality):
        """A grey JPEG of the band, as a data URI.

        Grey rather than colour and JPEG rather than PNG because these are
        black-on-white scans and a sheet carries a hundred of them: the same
        crops come to ~40KB each this way against ~650KB as colour PNGs.
        Identical bands -- several findings on one printed line -- are
        rendered once and shared.
        """
        page = self.doc[page_no]
        clip = self.clip(page_no, boxes)
        key = (page_no, round(clip.x0), round(clip.y0), round(clip.x1), round(clip.y1))
        if key not in self._crops:
            pix = page.get_pixmap(clip=clip, dpi=dpi, colorspace=pymupdf.csGRAY)
            data = base64.b64encode(pix.tobytes("jpeg", jpg_quality=quality))
            self._crops[key] = "data:image/jpeg;base64," + data.decode("ascii")
        return self._crops[key]


class RECT(list):
    """A region given by the caller, to be cropped as it stands."""


def anchor_words(text, limit=WORDS_WIDE):
    """The last words of `text`, cut the way the page's own words are cut.

    The index keys are whole whitespace-delimited words of the page, folded.
    A query that splits `so-called` into `so` and `called` has one more token
    than the page does and misaligns the whole window against it, so the row
    comes back unplaced with its words plainly on the page. Splitting on
    whitespace and letting `fold` drop the punctuation keeps the two in step.
    """
    return [w for w in text.split() if fold(w)][-limit:]


def locate(scan, rows):
    """[(label, page, found)] for rows of (label, anchor); page None if unplaced.

    The anchor is text near the finding; its last words do the matching, as
    those are the ones that sit against the band being cropped.
    """
    return [(label, *scan.locate(anchor_words(anchor))) for label, anchor in rows]


class Library:
    """The scans, opened as they are wanted and kept.

    A screen's last few findings are usually one apiece across a dozen
    files, and a sheet per file is a sheet per finding -- the cost the
    stacking exists to avoid. So a row may name its own file, and the bands
    of several files go onto one sheet.
    """

    def __init__(self):
        self.scans = {}

    def scan(self, stem):
        if stem not in self.scans:
            pdf = pdf_for(stem)
            if not pdf.exists():
                raise FileNotFoundError(f"no scan for {stem}: {pdf}")
            self.scans[stem] = Scan(pdf)
        return self.scans[stem]

    def place(self, rows):
        """[(stem, label, page, found)] for (stem, label, page_hint, anchor).

        A page hint is used as given: the screen that wrote the row read it
        off that page.
        """
        out = []
        for stem, label, hint, anchor in rows:
            scan = self.scan(stem)
            if anchor.startswith("@"):
                # The screens that find tables and figures measure the region
                # themselves; there is no text to search for, and the rect is
                # better evidence than any anchor would be.
                if hint is None:
                    out.append((stem, label, None, "a `@rect` row needs a page"))
                    continue
                try:
                    rect = [float(v) for v in anchor[1:].split(",")]
                except ValueError:
                    out.append((stem, label, None, f"unreadable rect {anchor!r}"))
                    continue
                if not 0 <= hint < scan.doc.page_count:
                    out.append((stem, label, None,
                                f"p{hint} is not in a {scan.doc.page_count}-page scan"))
                    continue
                out.append((stem, label, hint, RECT(rect)))
                continue
            if hint is None:
                page, found = scan.locate(anchor_words(anchor))
            else:
                page, found = scan.locate_on(hint, anchor)
            out.append((stem, label, page, found))
        return out


def bands_of(scan, placed):
    """Merge the placements that share a printed line into one band each.

    Several findings in one paragraph crop to overlapping bands, and every
    pixel sent twice is paid for twice.
    """
    bands = []
    for label, page, found in placed:
        if page is None:
            continue
        clip = (scan.clip_rect(page, found) if isinstance(found, RECT)
                else scan.clip(page, found))
        if bands and bands[-1][0] == page:
            grown = bands[-1][1] | clip
            if clip.y0 < bands[-1][1].y1 and grown.height <= BAND_MERGE * clip.height:
                bands[-1][1] = grown
                bands[-1][2].append(label)
                continue
        bands.append([page, clip, [label]])
    return bands


def stack(scan, placed, out_stem, dpi=300, quality=80, per_sheet=6,
          max_band=None, max_sheet=None):
    """Write the bands as tall labelled JPEGs; returns the paths written.

    `scan` may be a `Library`, and `placed` rows `(stem, label, page, found)`,
    to put bands from several files on one sheet.
    """
    if isinstance(scan, Library):
        return stack_many(scan, placed, out_stem, dpi, quality, per_sheet,
                          max_band, max_sheet)
    sizes = []
    for page, clip, labels in bands_of(scan, placed):
        label = " + ".join(sorted(dict.fromkeys(labels))) + f" - page {page}"
        sizes.append(((label, scan, page, clip), STACK_WIDTH * clip.height / clip.width))
    return draw(laid_out(sizes, per_sheet, max_band, max_sheet),
                out_stem, dpi, quality)


def stack_many(library, placed, out_stem, dpi, quality, per_sheet,
               max_band=None, max_sheet=None):
    """One sheet of bands drawn from several files, each captioned with its own."""
    sizes = []
    for stem, label, page, found in placed:
        if page is None:
            continue
        scan = library.scan(stem)
        clip = (scan.clip_rect(page, found) if isinstance(found, RECT)
                else scan.clip(page, found))
        sizes.append(((f"{stem} {label} - page {page}", scan, page, clip),
                      STACK_WIDTH * clip.height / clip.width))
    return draw(laid_out(sizes, per_sheet, max_band, max_sheet),
                out_stem, dpi, quality)


def draw(sheets, out_stem, dpi, quality):
    """Write each packed sheet; a band narrower than the sheet is centred."""
    written = []
    for chunk in sheets:
        page_doc = pymupdf.open()
        sheet = page_doc.new_page(
            width=STACK_WIDTH,
            height=sum(tall + STACK_LABEL for _item, _w, tall in chunk))
        y = 0.0
        for (label, scan, page, clip), width, tall in chunk:
            sheet.draw_rect(pymupdf.Rect(0, y, STACK_WIDTH, y + STACK_LABEL),
                            color=None, fill=(0.87, 0.87, 0.87))
            sheet.insert_text((6, y + 18), label, fontsize=12)
            left = (STACK_WIDTH - width) / 2
            sheet.insert_image(
                pymupdf.Rect(left, y + STACK_LABEL, left + width,
                             y + STACK_LABEL + tall),
                pixmap=scan.doc[page].get_pixmap(clip=clip, dpi=dpi,
                                                 colorspace=pymupdf.csGRAY))
            y += STACK_LABEL + tall
        out = Path(f"{out_stem}-{len(written) + 1}.jpg")
        out.write_bytes(sheet.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
                        .tobytes("jpeg", jpg_quality=quality))
        written.append(out)
    return written


def pdf_for(stem):
    """The scan behind a file, whether given a stem or a jons/ path."""
    return PDF_DIR / f"{Path(stem).stem}.pdf"


def read_rows(handle):
    """A row is 2, 3 or 4 tab-separated fields:

        label<TAB>anchor
        file<TAB>label<TAB>anchor                 -- to mix files on a sheet
        file<TAB>label<TAB>page<TAB>anchor        -- when the screen knows the page
        file<TAB>label<TAB>page<TAB>@x0,y0,x1,y1  -- a region the screen measured

    Blank lines and `#` comments are ignored.
    """
    rows = []
    for line in handle:
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            rows.append((None, parts[0].strip(), None, parts[1]))
        elif len(parts) == 3:
            rows.append((parts[0].strip(), parts[1].strip(), None, parts[2]))
        elif len(parts) >= 4:
            page = parts[2].strip().lstrip("pP")
            rows.append((parts[0].strip(), parts[1].strip(),
                         int(page) if page.isdigit() else None,
                         "\t".join(parts[3:])))
        else:
            sys.exit(f"a row needs `label<TAB>anchor`: {line!r}")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("sheets",))
    ap.add_argument("file", nargs="?",
                    help="a jons/ Markdown file or its stem; omit it when the "
                         "rows name their own file")
    ap.add_argument("--rows", help="rows file (default: stdin)")
    ap.add_argument("--out", help="sheet name stem (default <STEM>-sheet here)")
    ap.add_argument("--per-sheet", type=int, default=6)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--max-band", type=int, default=MAX_BAND,
                    help="a taller band is scaled down whole; raise it to\n"
                         f"read a full-page table (default {MAX_BAND})")
    ap.add_argument("--max-sheet", type=int, default=MAX_SHEET,
                    help=f"cut a sheet here (default {MAX_SHEET})")
    args = ap.parse_args(argv)

    with open(args.rows, encoding="utf-8") if args.rows else sys.stdin as handle:
        rows = read_rows(handle)
    if not rows:
        print("no rows given")
        return 2
    if any(stem is None for stem, _l, _h, _a in rows) and not args.file:
        print("rows without a file of their own need the `file` argument")
        return 2

    library = Library()
    default = Path(args.file).stem if args.file else None
    try:
        placed = library.place([(stem or default, label, hint, anchor)
                                for stem, label, hint, anchor in rows])
    except FileNotFoundError as exc:
        print(f"{exc}\nset ONS_ARCHIVE_DIR to the archive directory")
        return 2
    for stem, label, page, found in placed:
        print(f"{stem} {label}: "
              + (f"p{page}" if page is not None else f"no crop -- {found}"))
    sheets = stack(library, placed,
                   args.out or f"{default or 'corpus'}-sheet",
                   args.dpi, args.quality, args.per_sheet,
                   args.max_band, args.max_sheet)
    kept = sum(1 for _s, _l, p, _f in placed if p is not None)
    print(f"{len(rows)} row(s), {kept} located -> "
          + ", ".join(f"{s} ({s.stat().st_size // 1024} KB)" for s in sheets))
    return 0 if kept == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
