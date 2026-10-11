#!/usr/bin/env python3
"""Find headings that `pdfmd` folded into the body text of a `jons/` Markdown file.

The source PDFs are typewritten scans. A section head is set on its own line,
separated from the paragraphs around it by extra leading, and marked either by
underlining it with the typewriter's underscore key or by typing it in capitals.
`pdfmd` frequently loses the line break and the mark together: the head is
appended to the tail of the paragraph above it, so a reader meets it
mid-sentence instead of as a section break.

This is not the flattened-table problem `detect_tables.py` screens for. No table
is involved and the escaped-pipe fingerprint never fires on it.

Four signals are combined, because no one of them decides on its own:

  set apart   A line with clear space above AND below that stops short of the
              right margin. Necessary, never sufficient -- a short body line
              between two figures looks exactly the same.
  underline   A long contiguous horizontal ink run under the line's own
              x-extent, measured in pixels, minus the same measurement taken in
              the margin to its right. The subtraction matters: a scan smudge
              running clear across the page scores as high as a real underline
              until you notice it does not stop where the text stops.
  capitals    An all-capitals line, which is how these typewriters mark a head
              when they do not underline it (`NOTE`, `BIBLIOGRAPHY`).
  bold        A line whose OCR text layer is flagged bold end to end. Later
              issues (ONS_131 on) print heads in a bold proportional face
              instead of underlining them, which the pixel underline test
              cannot see at all -- it only looks for ink under the line, and
              bold text has none. Trusted only on a page where ordinary body
              text is not *also* OCR'd bold -- some scans mis-tag a whole
              page's text that way, the same failure mode the margin control
              catches for underlines, so the fraction of long body lines that
              come back bold is checked first and the signal is dropped for
              that page if it is high.

Being set apart makes a line a candidate; an underline, capitals, or bold mark
makes it a head. A candidate that is none of these wants a paragraph break but
no marker.

The check runs in both directions, because each finds errors the other cannot:

  PDF -> Markdown   a head in the scan that the Markdown lost      (FOLDED, FLAT)
  Markdown -> PDF   a marker in the Markdown the scan does not     (OVERSET)
                    justify

Usage:
    detect_headings.py scan IS_001 [IS_002 ...]   # report, change nothing
    detect_headings.py scan IS_001 -v             # include what is already right
    detect_headings.py fix  IS_001                # rewrite the Markdown

Requires PyMuPDF and numpy.
"""
import argparse
import difflib
import os
import pathlib
import re
import sys

try:
    import numpy as np
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24.3
    except ImportError:  # older PyMuPDF only exposes the legacy `fitz` name
        import fitz
except ImportError as exc:  # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs PyMuPDF and numpy.")

# ONS_ARCHIVE_DIR overrides the default checkout-relative path -- set it when
# the ons-website PDFs live somewhere else on this machine (they come from
# the private esnible/ons-website repo, not this one, so the path varies).
PDF_DIR = pathlib.Path(
    os.environ.get("ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")
).expanduser()
if not PDF_DIR.is_dir():
    print(f"warning: PDF archive {PDF_DIR} does not exist -- set ONS_ARCHIVE_DIR "
          "to the ons-website static/archive checkout", file=sys.stderr)
MD_DIR = pathlib.Path(__file__).resolve().parents[4] / "jons"

# --- tuned defaults -------------------------------------------------------
# THRESH/SMEAR match detect_tables.py; these are the same scans.
# GAP: multiples of the page's own median leading that must sit above AND below
#   a line for it to read as set apart. IS_001's heads clear 1.9x while ordinary
#   interline spacing is 1.0x, so 1.4 sits between them rather than on either.
# WIDTH: a head is short. 0.75 of the page's body measure admits a long head and
#   still rejects a full-measure body line.
# UNDERLINE / MARGIN: an underline must score this much under the text, and must
#   beat the margin control by MARGIN. On IS_001 real underlines score 0.51-0.97
#   against a margin control near zero, plain body lines 0.05-0.19, and the
#   page-wide smudge under `September 1971` scores 0.37 in both places.
# BOLD: fraction of a line's characters the OCR text layer flags bold before it
#   counts as a bold head. Real heads come back 1.00; nothing seen scoring
#   under 0.75 was a real head, so 0.9 leaves margin either side.
# BOLD_NOISE: fraction of a page's own long (>=10 char) body lines that may
#   come back >50% bold before the page is judged unreliable for this signal
#   and bold is ignored on it entirely. A clean page scores at or near 0; a
#   page whose whole text layer was mis-tagged bold scores 1.0. 0.15 sits
#   below the lowest "really is noisy" page seen (0.27) and above ordinary
#   noise from a handful of genuine bold run-in labels.
# RATIO: the PDF text layer and the Markdown were OCR'd separately and disagree
#   ("ORIEOTAL" vs "ORIENTAL"), so matching is fuzzy.
# SHAPE_*: the second way a line can read as set apart, for a head the
#   typesetter put flush in the text block with no extra leading either side.
#   ONS_109's `ONS News` and `Notes` score 9.1-11.5pt of leading against the
#   13.8pt the gap test wants, and come back bold=0.00 from a text layer that
#   tagged nothing on the page -- heading, body line and article title all
#   Times-Roman 9.0. Neither existing signal exists there. What is left is the
#   shape a reader uses: a short line sitting between a paragraph's last line
#   (short, because it is the last) and the full-measure line that opens the
#   next block. Measured against ONS_109's own 23 headings, the three
#   conditions together score 12 hits / 11 real; dropping SHAPE_NEXT alone
#   drops that to 23 / 13, because "short line after a short line" also
#   describes every list item and run-in label.
THRESH, SMEAR, DPI = 185, 2, 200
GAP, WIDTH, UNDERLINE, MARGIN, BOLD, BOLD_NOISE, RATIO = 1.4, 0.75, 0.45, 0.25, 0.9, 0.15, 0.72
SHAPE_WIDTH, SHAPE_PREV, SHAPE_NEXT = 0.35, 0.95, 0.90

MARKER_RE = re.compile(r"^(#{1,6}\s+|\*\*|__)")
# Longest a marked line may be and still be trusted as a real title rather than
# a paragraph that picked up a stray marker.
TITLE_LEN = 60
SKIP_MD = ("|", "<!--", "- ", "* ", "> ", "```")
DEFAULT_MARKER = "##"


# --- PDF side -------------------------------------------------------------

BOLD_FLAG = 2 ** 4  # PyMuPDF span flags bit 4


def _span_bold(span):
    return bool(span["flags"] & BOLD_FLAG) or "bold" in span.get("font", "").lower()


def visual_lines(page, tol=2.0):
    """Text-layer fragments grouped into the lines a reader would see.

    PyMuPDF reports `A Typical Magadhan coin` and `(Nanda dynasty)` as separate
    lines because the typewriter left a wide gap between them. On the page they
    are one line -- and only the first half of it is underlined.
    """
    frags = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(s["text"] for s in line["spans"]).strip()
            if not text:
                continue
            total = sum(len(s["text"]) for s in line["spans"])
            bold = sum(len(s["text"]) for s in line["spans"] if _span_bold(s))
            frags.append((line["bbox"], text, bold, total))
    frags.sort(key=lambda f: (f[0][1], f[0][0]))

    out = []
    for bbox, text, bold, total in frags:
        if out and abs(bbox[1] - out[-1]["y0"]) <= tol:
            cur = out[-1]
            cur["x0"], cur["x1"] = min(cur["x0"], bbox[0]), max(cur["x1"], bbox[2])
            cur["y1"] = max(cur["y1"], bbox[3])
            cur["text"] += " " + text
            cur["_bold_chars"] += bold
            cur["_total_chars"] += total
        else:
            out.append({"y0": bbox[1], "y1": bbox[3], "x0": bbox[0],
                        "x1": bbox[2], "text": text,
                        "_bold_chars": bold, "_total_chars": total})
    for ln in out:
        ln["bold"] = ln["_bold_chars"] / ln["_total_chars"] if ln["_total_chars"] else 0.0
    return out


def page_metrics(lines):
    """(median leading, body measure) for one page, in points."""
    deltas = [b["y0"] - a["y0"] for a, b in zip(lines, lines[1:])
              if 0 < b["y0"] - a["y0"] < 60]
    if len(lines) < 3 or not deltas:
        return None, None
    widths = sorted(l["x1"] - l["x0"] for l in lines)
    return float(np.median(deltas)), widths[int(len(widths) * 0.9)]


def mark_set_apart(lines, gap=GAP, width=WIDTH, shape=True):
    """Flag lines that read as set apart, by leading or by shape.

    Two independent routes, recorded in `apart_by` so a reviewer can weigh
    them differently:

    `gap`   -- clear space above and below, stopping short of the margin.
               The original test, and the stronger evidence.
    `shape` -- no extra leading at all, but the three-line shape of a head:
               short line, a paragraph's last line above it, a full-measure
               line below. See SHAPE_* above. Finds heads the gap test cannot
               see at any threshold, because there is no gap to find.
    """
    leading, measure = page_metrics(lines)
    for i, ln in enumerate(lines):
        ln["set_apart"], ln["apart_by"] = False, None
        if not leading or not measure:
            continue
        if len(re.sub(r"[^A-Za-z0-9]", "", ln["text"])) < 4:
            continue
        w = ln["x1"] - ln["x0"]
        above = ln["y0"] - lines[i - 1]["y0"] if i else 1e9
        below = lines[i + 1]["y0"] - ln["y0"] if i + 1 < len(lines) else 1e9
        if (above >= leading * gap and below >= leading * gap
                and w <= measure * width):
            ln["set_apart"], ln["apart_by"] = True, "gap"
        elif (shape and 0 < i < len(lines) - 1
                and w <= measure * SHAPE_WIDTH
                and lines[i - 1]["x1"] - lines[i - 1]["x0"] < measure * SHAPE_PREV
                and lines[i + 1]["x1"] - lines[i + 1]["x0"] >= measure * SHAPE_NEXT
                and mostly_words(ln["text"])):
            ln["set_apart"], ln["apart_by"] = True, "shape"


def score_bold_reliability(lines, noise=BOLD_NOISE):
    """Zero out the bold signal on a page where body text is bold too.

    Mirrors the underline/margin split: `bold` read straight off the OCR text
    layer is usually trustworthy, because it comes from the scanner's own font
    detection rather than a pixel measurement -- but some scans get it wrong
    for the whole page (an unusual face, a heavy scan), and on those pages
    ordinary body paragraphs come back bold too. A page is judged unreliable
    when more than `noise` of its own long, full-measure lines score over 50%
    bold; `bold` is then set to 0.0 for every line on it rather than left to
    promote half the page to headings.

    The body sample is picked by *width*, not `set_apart`: a short heading
    line routinely fails `set_apart` (ONS_133's masthead and section heads
    among them -- tight neighbouring spacing defeats the gap test even though
    the line reads as a head to a human) and would otherwise count itself as
    "noise", pushing a page's own genuine bold heads over the threshold and
    switching the signal off for exactly the lines it exists to catch. A line
    close to the page's own body measure is, almost without exception, a
    wrapped paragraph line rather than a head, wrongly set apart or not.
    """
    _, measure = page_metrics(lines)
    if not measure:
        return
    body = [ln for ln in lines
            if (ln["x1"] - ln["x0"]) >= measure * 0.85
            and len(re.sub(r"[^A-Za-z0-9]", "", ln["text"])) >= 10]
    if not body:
        return
    noisy = sum(1 for ln in body if ln["bold"] > 0.5)
    if noisy / len(body) > noise:
        for ln in lines:
            ln["bold"] = 0.0


def _longest_run(row, smear=SMEAR):
    if not row.any():
        return 0
    smeared = row.copy()
    for shift in range(1, smear + 1):  # tolerate a skewed scan
        smeared[:-shift] |= row[shift:]
        smeared[shift:] |= row[:-shift]
    edges = np.flatnonzero(
        np.diff(np.concatenate(([0], smeared.view(np.int8), [0]))))
    return int((edges[1::2] - edges[0::2]).max()) if len(edges) else 0


def score_underlines(page, lines, dpi=DPI):
    """Ink run under each line, and the same measured in the margin beside it.

    A real underline stops where the text stops. A horizontal scan artifact does
    not, so the margin control is what tells the two apart.
    """
    # Every line is scored, not just the set-apart ones: the Markdown -> PDF
    # direction has to ask whether an arbitrary line is underlined, and a
    # centred title is usually too wide to be set apart in the first place.
    live = lines
    if not live:
        return
    scale = dpi / 72.0
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    ink = img.reshape(pix.height, pix.width, pix.n)[:, :, 0] < THRESH
    height, page_w = ink.shape
    for ln in live:
        px0, px1 = max(0, int(ln["x0"] * scale)), min(page_w, int(ln["x1"] * scale))
        span = px1 - px0
        mx0 = min(page_w, px1 + int(6 * scale))
        mx1 = min(page_w, mx0 + span)
        under = margin = 0
        for y in range(int((ln["y1"] - 5) * scale), int((ln["y1"] + 5) * scale)):
            if not 0 <= y < height:
                continue
            under = max(under, _longest_run(ink[y, px0:px1]))
            if mx1 > mx0:
                margin = max(margin, _longest_run(ink[y, mx0:mx1]))
        ln["underline"] = under / max(1, span)
        ln["margin"] = margin / max(1, mx1 - mx0) if mx1 > mx0 else 0.0


def is_head(line, underline=UNDERLINE, margin=MARGIN, bold=BOLD):
    """A set-apart line the typewriter (or the printer) marked as a head."""
    if line.get("underline", 0.0) >= underline and \
            line["underline"] - line.get("margin", 0.0) >= margin:
        return "underlined"
    letters = [c for c in line["text"] if c.isalpha()]
    if len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.9:
        return "capitals"
    if line.get("bold", 0.0) >= bold:
        return "bold"
    return None


# --- matching -------------------------------------------------------------

def normalize(text):
    """Lowercase alphanumerics, plus a map back to columns in the original."""
    chars, cols = [], []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.lower())
            cols.append(i)
    return "".join(chars), cols


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def anchored(hay, needle, edge=2, share=0.6):
    """Best (score, where) for `needle` at the head or the tail of `hay`.

    `score` is how much of `needle` was found; `where` is "start" or "end", and
    those are the only two answers. A heading either starts its Markdown line
    or -- the failure this tool exists to find -- was appended to the end of
    one. A match floating in the middle of a paragraph is a coincidence, and
    saying so is what stops `B I B L I O G R A P H Y` from matching the words
    `Bibliography of hoards` inside a numbered reference.

    A "start" match additionally has to account for at least `share` of the
    line. Without that, the bibliography subhead `Historical` matches the
    opening of `## Historical Summary` perfectly and the real head, folded onto
    the end of a line eleven pages later, is never reported.
    """
    blocks = [b for b in difflib.SequenceMatcher(None, hay, needle,
                                                 autojunk=False)
              .get_matching_blocks() if b.size]
    if not blocks:
        return 0.0, None
    score = sum(b.size for b in blocks) / len(needle)
    first, last = blocks[0].a, blocks[-1].a + blocks[-1].size
    # The matched pieces have to sit together. Summing scattered blocks lets a
    # long paragraph "contain" any short head by coincidence -- it is how
    # `B I B L I O G R A P H Y` scored 1.00 against a paragraph about the
    # Mauryan dynasty. The slack over len(needle) is for OCR garble, which
    # splits a run without moving it ("ORIEOTAL" for "ORIENTAL").
    if last - first > len(needle) * 1.4 + 4:
        return 0.0, None
    if first <= edge and last >= len(hay) * share:
        return score, "start"
    if last >= len(hay) - edge and first > edge:
        return score, "end"
    return 0.0, None


def locate_in_md(md_lines, text, min_ratio=RATIO, cursor=0, slack=0.08):
    """(row, where, ratio, start col) of `text` in the Markdown, or None.

    Both files run in the same order, so a match at or after `cursor` -- the
    row the previous head matched -- is preferred over an equally good one
    behind it, and beats a slightly better one by up to `slack`. Without this,
    the short bibliography subhead `Historical` on page 11 matches
    `## Historical Summary` back on page 1 with a perfect score, and the real
    head goes unreported.
    """
    needle, _ = normalize(text)
    if len(needle) < 6:
        return None
    best = best_fwd = None
    for row, line in enumerate(md_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(SKIP_MD):
            continue
        hay, cols = normalize(line)
        if not hay:
            continue
        ratio, where = anchored(hay, needle)
        if ratio < min_ratio:
            continue
        blocks = [b for b in difflib.SequenceMatcher(None, hay, needle,
                                                     autojunk=False)
                  .get_matching_blocks() if b.size]
        hit = (row, where, ratio, cols[blocks[0].a])
        if best is None or ratio > best[2]:
            best = hit
        if row >= cursor and (best_fwd is None or ratio > best_fwd[2]):
            best_fwd = hit
    if best_fwd and (best is None or best_fwd[2] >= best[2] - slack):
        return best_fwd
    return best


def locate_in_pdf(pdf_lines, text, min_ratio=RATIO):
    """The PDF line that best matches a Markdown heading line, or None.

    The `share` rule inside anchored() carries the weight here too: it is what
    keeps the heading `# NOTE` from matching the body line `Note: Up to twenty
    small marks may occur...`, which it otherwise does perfectly.
    """
    needle, _ = normalize(text)
    if len(needle) < 4:
        return None
    best = None
    for ln in pdf_lines:
        hay, _ = normalize(ln["text"])
        if not hay:
            continue
        ratio, where = anchored(hay, needle)
        # "start" only. A Markdown heading is a whole line, so it must account
        # for a whole PDF line; letting it match the tail of one lets
        # `# THE REALMS OF` land on a paragraph about Karshapanas.
        if where == "start" and ratio >= min_ratio and (best is None or ratio > best[1]):
            best = (ln, ratio)
    return best


WORD_RE = re.compile(r"[A-Za-zÀ-ɏḀ-ỿ'’.-]*[A-Za-zÀ-ɏḀ-ỿ]{3,}[A-Za-zÀ-ɏḀ-ỿ'’.,:;()-]*")


def mostly_words(text, share=0.5):
    """True when at least `share` of the tokens are Latin-script words of 3+
    letters. `Qa'itbay " " Reign 841-842 842-857` and `#8 © EF EEE + Ww` are
    not; `SIKH COINS OF THE LAHORE MINT` is."""
    toks = text.split()
    return bool(toks) and sum(bool(WORD_RE.fullmatch(t)) for t in toks) / len(toks) >= share


# --- verdicts -------------------------------------------------------------
#
# FOLDED        the scan sets this head apart; the Markdown appended it to the
#               paragraph above.  Split the line and mark it.
# FOLDED-PLAIN  set apart in the scan but not marked as a head, and still
#               appended.  Wants the paragraph break, not a marker.
# FLAT          on its own line already, but the marker is missing.
# OVERSET       the Markdown marks it as a head; the scan does not.
# LOST          an underlined or capitalised head with no counterpart in the
#               Markdown at all.
# UNMATCHED     the reverse of LOST: a `#` heading whose text matches no line
#               of the scan at all and is mostly not words. Usually OCR garble or a flattened
#               table's cells that happened to start with `#` (IS_020's
#               catalogue became `## Qa'itbay " " Reign 841-842 ...` and
#               `#8 © EF EEE + Ww`). Reported for review, never applied --
#               removing the marker would leave the garble in place.
# FOLDED-PLAIN is repairable but not repaired unless asked for: it moves prose
# that carries no marker, so a wrong call there is a wrong paragraph break in
# running text. It is reported, and left out of the "to fix" count.
FIXABLE = ("FOLDED", "FLAT", "OVERSET")
OPTIONAL = ("FOLDED-PLAIN",)
# Reported, never applied. A split that lands inside a word is a mis-match, not
# a folded head: it once turned `# ORIENTAL NUMISMATIC SOCIETY INFORMATION
# SHEET` into `# ORIEN` plus `## TAL NUMISMATIC SOCIETY INFORMATION SHEET`.
UNSAFE = ("FOLDED-MIDWORD", "FOLDED-PLAIN-MIDWORD",
          "FOLDED-LOWER", "FOLDED-PLAIN-LOWER")
ORDER = ("FOLDED", "FLAT", "OVERSET", "FOLDED-MIDWORD", "FOLDED-LOWER",
         "FOLDED-PLAIN", "FOLDED-PLAIN-MIDWORD", "FOLDED-PLAIN-LOWER",
         "LOST", "UNMATCHED", "OK")
REVIEW = ("UNMATCHED",)


def analyse(pdf_lines, md_lines, min_ratio=RATIO, underline=UNDERLINE,
            margin=MARGIN, bold=BOLD):
    # `seen` keeps a running head that repeats on every page of a long table
    # ("APPENDIX 1 (Continued)") from being reported once per page against the
    # single Markdown line it all collapsed into.
    found, claimed, cursor, seen = [], set(), 0, set()

    # PDF -> Markdown: heads the conversion lost.
    for ln in pdf_lines:
        if not ln.get("set_apart"):
            continue
        head = is_head(ln, underline, margin, bold)
        hit = locate_in_md(md_lines, ln["text"], min_ratio, cursor)
        if hit is None:
            if head:
                found.append({"verdict": "LOST", "pdf": ln, "head": head})
            continue
        row, where, ratio, col = hit
        claimed.add(row)
        if ratio >= 0.9:  # only a confident match may move the cursor forward
            cursor = max(cursor, row)
        marked = bool(MARKER_RE.match(md_lines[row].lstrip()))
        if where == "end" and col > 0:
            verdict = "FOLDED" if head else "FOLDED-PLAIN"
            if md_lines[row][col - 1].isalnum() and md_lines[row][col].isalnum():
                verdict += "-MIDWORD"  # reported, never applied
            elif md_lines[row][col:col + 1].islower() and not (
                    MARKER_RE.match(md_lines[row].lstrip())
                    and len(md_lines[row][:col].strip()) <= TITLE_LEN):
                # A head starting lower-case, cut out of a line that is itself
                # running prose, is a sentence tail rather than a head: `(see`
                # / `appendix).`, `I have now developed a` / `classific-`. The
                # exception preserved is a by-line cut from a title --
                # `# THE COINAGE OF COOCH BEHAR` / `by N.G. Rhodes` -- where
                # what is left behind is a heading, not a sentence. It has to
                # be a *short* heading: a paragraph carrying a stray `#` is
                # still a paragraph, and letting the marker alone vouch for it
                # cut `...to an accuracy of 0 02 of a` from `millimeter`.
                verdict += "-LOWER"
        elif head and not marked:
            verdict = "FLAT"
        elif marked and not head:
            verdict = "OVERSET"
        else:
            verdict = "OK"
        if verdict == "OK" or (verdict, row) not in seen:
            seen.add((verdict, row))
            found.append({"verdict": verdict, "pdf": ln, "head": head,
                          "row": row, "col": col, "ratio": ratio})

    # Markdown -> PDF: markers the scan does not justify. Only lines the pass
    # above did not already account for, so nothing is reported twice.
    for row, line in enumerate(md_lines):
        if row in claimed or not MARKER_RE.match(line.lstrip()):
            continue
        body = MARKER_RE.sub("", line.lstrip(), count=1).strip().rstrip("*_")
        hit = locate_in_pdf(pdf_lines, body, min_ratio)
        if hit is None:
            # Only a `#` heading, and only one that is mostly not words: a real
            # title the scan's OCR happened to read differently (`# THE REALMS
            # OF PUNCHMARKED COINAGE`) is not garble, and bold run-in openers
            # (`**Lists Received**`) are not headings at all. Too short to
            # match reliably (`## by`) is not evidence either.
            if (line.lstrip().startswith("#") and len(normalize(body)[0]) >= 4
                    and not mostly_words(body)):
                found.append({"verdict": "UNMATCHED", "pdf": None, "head": None,
                              "row": row, "col": 0, "ratio": 0.0})
            continue
        ln, ratio = hit
        # Deliberately not requiring `set_apart` here: a centred title is often
        # too wide for that test, yet it is plainly a head and its marker is
        # correct. What disqualifies a marker is the scan not marking the line
        # at all -- no underline, no capitals, and no bold.
        head = is_head(ln, underline, margin, bold)
        if not head:
            found.append({"verdict": "OVERSET", "pdf": ln, "head": head,
                          "row": row, "col": 0, "ratio": ratio})
    found.sort(key=lambda f: (ORDER.index(f["verdict"]),
                              f["pdf"]["page"] if f["pdf"] else 0, f.get("row", 0)))
    return found


# --- reporting and repair -------------------------------------------------

def report(stem, md_lines, found, verbose):
    counts = {}
    for f in found:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    open_n = sum(n for v, n in counts.items() if v in FIXABLE)
    review_n = sum(n for v, n in counts.items() if v in REVIEW)
    tail = "  ".join(f"{v} {counts[v]}" for v in ORDER if v in counts)
    print(f"{stem}: {len(found) - review_n} set-apart line(s) | {tail or 'none'}"
          f"  -- {open_n} to fix" + (f", {review_n} to review" if review_n else ""))
    for f in found:
        if f["verdict"] == "OK" and not verbose:
            continue
        ln = f["pdf"]
        if ln is None:
            print(f"  {f['verdict']:12s} md line {f['row'] + 1}: "
                  f"{md_lines[f['row']].strip()[:70]!r}")
            continue
        print(f"  {f['verdict']:12s} p{ln['page']:<3d} "
              f"underline={ln.get('underline', 0.0):4.2f}"
              f"-{ln.get('margin', 0.0):4.2f} bold={ln.get('bold', 0.0):4.2f} "
              f"{f['head'] or 'plain':10s} [{ln.get('apart_by') or '-':5s}] "
              f"{ln['text'][:52]!r}")
        if "row" in f:
            print(f"{'':18s}md line {f['row'] + 1}: "
                  f"{md_lines[f['row']].strip()[:70]!r}")
    return open_n


def apply(md_lines, found, marker, include_plain, include_shape=False):
    """Rewrite the Markdown. Returns (new lines, count applied)."""
    edits = {}
    for f in found:
        # A candidate the gap test could not see, surfaced by shape alone, is
        # reported but not applied without `--include-shape`. Measured over
        # six files, the heads it adds beyond the gap test are about half
        # real -- ONS_130's `Corrigendum` is a head, `Illustrations are x
        # 1.5.` on the same page is the last line of a paragraph -- and
        # `fix` writes FOLDED/FLAT/OVERSET without asking. Good enough to put
        # in front of a reader with the page open, not good enough to write.
        if f["pdf"] is not None and f["pdf"].get("apart_by") == "shape" \
                and not include_shape:
            continue
        if f["verdict"] == "FOLDED-PLAIN":
            if not include_plain:
                continue
        elif f["verdict"] not in FIXABLE:
            continue
        edits.setdefault(f["row"], f)  # first verdict wins; never stack two
    out, applied = [], 0
    for row, line in enumerate(md_lines):
        f = edits.get(row)
        if f is None:
            out.append(line)
            continue
        applied += 1
        verdict = f["verdict"]
        if verdict == "FLAT":
            out.append(f"{marker} {line.strip()}")
        elif verdict == "OVERSET":
            # Only the marker goes. No blank line is inserted after it: a line
            # wrongly marked as a head is often the first line of a paragraph
            # that continues on the next line, and breaking there would split a
            # sentence. Leaving the two adjacent renders them as one paragraph,
            # which is what the scan shows.
            out.append(MARKER_RE.sub("", line.lstrip(), count=1).strip())
        else:  # FOLDED / FOLDED-PLAIN
            head, tail = line[:f["col"]].rstrip(), line[f["col"]:].strip()
            if head:
                out.extend([head, ""])
            out.append(f"{marker} {tail}" if verdict == "FOLDED" else tail)
    return out, applied


def run(stem, args):
    pdf, md = PDF_DIR / f"{stem}.pdf", MD_DIR / f"{stem}.md"
    if not pdf.exists():
        return None, f"{stem}: no PDF at {pdf}"
    if not md.exists():
        return None, f"{stem}: no Markdown at {md}"
    md_lines = md.read_text(encoding="utf-8").split("\n")
    pdf_lines = []
    with fitz.open(pdf) as doc:
        for pno, page in enumerate(doc, start=1):
            lines = visual_lines(page)
            mark_set_apart(lines, args.gap, args.width, not args.no_shape)
            score_underlines(page, lines, args.dpi)
            score_bold_reliability(lines, args.bold_noise)
            for ln in lines:
                ln["page"] = pno
            pdf_lines.extend(lines)
    found = analyse(pdf_lines, md_lines, args.min_ratio,
                    args.min_underline, args.min_margin, args.min_bold)
    return (md, md_lines, found), None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("scan", "report, change nothing"),
                            ("fix", "rewrite the Markdown in place")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("stems", nargs="+", metavar="IS_001")
        p.add_argument("-v", "--verbose", action="store_true",
                       help="also show set-apart lines the Markdown got right")
        p.add_argument("--gap", type=float, default=GAP,
                       help="blank space wanted above and below a head, in "
                            f"multiples of the page's median leading (default {GAP})")
        p.add_argument("--width", type=float, default=WIDTH,
                       help="longest a head may be, as a fraction of the page's "
                            f"body measure (default {WIDTH})")
        p.add_argument("--no-shape", action="store_true",
                       help="only treat a line as set apart when it has clear "
                            "leading above and below, disabling the three-line "
                            "shape test (short line, paragraph-final line "
                            "above, full-measure line below)")
        p.add_argument("--min-ratio", type=float, default=RATIO,
                       help="similarity a PDF line and a Markdown line need "
                            f"before they count as the same text (default {RATIO})")
        p.add_argument("--min-underline", type=float, default=UNDERLINE,
                       help="ink run under a line, over the line's own width, "
                            "before it counts as underlined. Lower it for a "
                            "faint scan -- IS_003's running heads score 0.42 "
                            f"where IS_001's score 0.90+ (default {UNDERLINE})")
        p.add_argument("--min-margin", type=float, default=MARGIN,
                       help="how far that run must beat the same measurement "
                            "taken in the margin beside the line, which is what "
                            "separates an underline from a scan streak "
                            f"(default {MARGIN})")
        p.add_argument("--dpi", type=int, default=DPI,
                       help=f"render DPI for the underline probe (default {DPI})")
        p.add_argument("--min-bold", type=float, default=BOLD,
                       help="fraction of a line's characters the OCR text "
                            "layer must flag bold before it counts as a bold "
                            f"head (default {BOLD})")
        p.add_argument("--bold-noise", type=float, default=BOLD_NOISE,
                       help="fraction of a page's own long body lines that "
                            "may come back bold before the bold signal is "
                            f"distrusted for that whole page (default {BOLD_NOISE})")
        if name == "fix":
            p.add_argument("--marker", default=DEFAULT_MARKER,
                           help=f"what to prefix a head with (default {DEFAULT_MARKER!r})")
            p.add_argument("--include-shape", action="store_true",
                           help="also apply candidates found only by the "
                                "three-line shape test. Off by default: these "
                                "are roughly half real, so confirm each "
                                "against a render first")
            p.add_argument("--include-plain", action="store_true",
                           help="also break FOLDED-PLAIN lines: they get the "
                                "paragraph break but no marker")
    args = ap.parse_args()

    total = 0
    for stem in args.stems:
        data, err = run(stem, args)
        if err:
            print(err, file=sys.stderr)
            total += 1
            continue
        md, md_lines, found = data
        open_n = report(stem, md_lines, found, args.verbose)
        if args.cmd == "fix" and (open_n or args.include_plain):
            new, applied = apply(md_lines, found, args.marker,
                                 args.include_plain, args.include_shape)
            if applied:
                md.write_text("\n".join(new), encoding="utf-8")
                print(f"  wrote {md} ({applied} line(s) changed)")
        total += open_n
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
