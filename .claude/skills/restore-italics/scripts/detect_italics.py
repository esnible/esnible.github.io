#!/usr/bin/env python3
"""Find italic passages the PDF text layer records and the Markdown lost.

The archive PDFs were OCR'd by ABBYY, which assigns a real font face per span
instead of one flat font: book titles, foreign terms and the masthead's
run-in labels come back as `Times-Italic`, `*Times New Roman-BoldItalic-*`,
`*Cambria-BoldItalic-*`. `pdfmd` re-OCRs the page image and never sees any of
it, so on many files the emphasis is simply gone -- ONS_111 carries 35 italic
runs in its text layer, 14 of them real text, against one `*...*` in its
Markdown.

This is the same span data `detect_headings.py` reads bold off, one flag bit
over (`flags & 2`, plus the font name as a fallback), and it inherits that
script's two hard problems:

  separate OCR passes  The text layer and the Markdown disagree about the
                       words themselves ("Umayad" against "Umayyad"), so a run
                       is matched into the Markdown fuzzily, never by position.
  a page-wide mis-tag  Some pages come back italic end to end. The fraction of
                       a page's own text that is italic is checked first and
                       the whole page is dropped above `--italic-noise`, the
                       same gate `score_bold_reliability()` applies to bold.

And adds two of its own:

  garble zones         ABBYY tags unreadable glyph soup italic as readily as
                       prose: 11 of ONS_111's 40 italic spans are `IVi-`,
                       `J:>`, `2=T`. A run has to read as words before it is
                       matched at all.
  a mangled emphasis   On 114 of the 268 files `pdfmd` did carry emphasis
  layer                across -- as per-word asterisks, `*word *` around every
                       word in the passage. There the italics are not missing,
                       they are mangled, which is `clean-ocr-formatting`'s job
                       and not this script's. `fix` refuses to write to such a
                       file; `scan` says so and carries on.

Verdicts:

  MISSING    italic in the scan, plain in the Markdown, located cleanly
  PRESENT    already emphasised -- nothing to do
  PARTIAL    located, but emphasis already overlaps part of the span
  AMBIGUOUS  two or more comparable matches; which one is meant is a guess
  UNSAFE     located, but the span cannot be wrapped (lands mid-word, crosses
             a comment, a table cell or an existing marker)
  OVERLONG   a run the length of a paragraph; see MAX_LEN
  LOST       no match in the Markdown at all -- usually the passage is garbled
             past matching, sometimes `pdfmd` dropped it
  NOISE      the run is not words; never matched, counted only

Only MISSING is ever written. Everything else is reported for a human with the
page open, because the cost of a wrong call here is silent: a `*` in the wrong
place reads as prose.

Usage:
    detect_italics.py scan ONS_111 [ONS_112 ...]   # report, change nothing
    detect_italics.py scan ONS_111 -v              # include PRESENT and NOISE
    detect_italics.py fix  ONS_111                 # write the MISSING ones
    detect_italics.py scan ONS_111 --pair-repeats  # resolve repeated citations

Requires PyMuPDF.
"""
import argparse
import difflib
import os
import pathlib
import re
import sys

try:
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24.3
    except ImportError:  # older PyMuPDF only exposes the legacy `fitz` name
        import fitz
except ImportError as exc:  # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")

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
# RATIO: how much of an italic run has to be found in a Markdown line before
#   the two count as the same text. The text layer and the Markdown were OCR'd
#   separately and disagree, so this cannot be 1.0; 0.85 admits "Umayad" for
#   "Umayyad" and "Coins m the" for "Coins in the" while rejecting a run that
#   merely shares its common letters with a paragraph.
# MARGIN: how far the best match must beat the second best. Below this the run
#   is AMBIGUOUS: `song-pei` occurs 14 times in ONS_111 and the text layer
#   cannot say which one the italic belongs to.
# DENSITY: the matched letters, over the span of Markdown they are spread
#   across. A run can score well on RATIO and still be spread over half as
#   much text again, which means the span picked up a word that is not in the
#   run: ONS_125's garbled `The World oflslanr` matched
#   `The World of Islam4 provided` at 0.88, and wrapping that italicises
#   `provided`. 14 letters over 24 is 0.58, and 0.80 rejects it.
# MIN_EDGE: a span's first and last agreement with the run must be at least
#   this many characters. A single letter at the edge is a coincidence, and
#   acting on one annexes the word it fell in: ONS_134's `Indo-Greek and
#   Indo-Scythic Coinage` aligned its leading `i` to the `i` of the preceding
#   word `his` (the Markdown's own OCR having dropped the `I` from `Indo`),
#   which put `his` inside the italics.
# TRIGRAM: share of a run's three-letter sequences a Markdown line must carry
#   before it is worth the fuzzy match. Purely a speed filter, set well below
#   anything a real match loses to OCR garble.
# CASE_WEIGHT: how much the capitalisation agreement may move a match's score,
#   either way. At 0.08 it separates two matches that are otherwise tied --
#   `Annual Subscription` from `annual subscription: within USA $12` -- by
#   0.16, just over MARGIN, and cannot lift a match that failed on letters.
# MIN_LEN: shortest a run may be, in alphanumerics, before it is matched at
#   all. Short runs are where the false matches live -- `silver` and `copper`
#   (ONS_111 p4, two bold-italic column headers) each occur all over the file
#   in plain prose, and nothing in the span distinguishes them.
# MIN_WORDS: a run needs this many Latin-script words of 3+ letters to be read
#   as text rather than as a tagged scrap of garble.
# ITALIC_NOISE: fraction of a page's own characters that may come back italic
#   before the page is dropped whole. Measured over the 5206 pages of the
#   archive that carry text: 4005 score under 0.1, 53 over 0.5, 17 over 0.9.
#   The high end holds both kinds of page, and the share cannot tell them
#   apart -- OP_001 p1 is a letter-spaced typescript, upright on the page,
#   that ABBYY tagged italic to the last character; ONS_191 p23 is a plate
#   whose captions really are all italic. 0.9 is set to catch the first: it
#   also drops the second, whose captions the Markdown mostly carries as
#   figure markers anyway, and it keeps a page like ONS_064 p4 (0.53, a long
#   quotation in French, genuinely italic) where most of the value is.
# BASELINE_GAP: points that may separate two italic runs on one baseline and
#   still be one passage. A word space in this corpus is 2-5pt; 14 allows the
#   wide gaps a justified line opens up without reaching across a column.
# COLUMN_GAP: points of blank that end a line segment. Wider than any word
#   space a justified line opens, narrower than the gutter between columns.
# MAX_LEN: longest a run may be, in alphanumerics, and still be written. What
#   this corpus italicises is a title or a phrase; a run the length of a
#   paragraph means a page that was mis-tagged below the gate, and wrapping it
#   would italicise the paragraph. Reported as OVERLONG.
# PAGE_CHARS: a page with less text than this is not worth the noise test --
#   a page that is one caption can legitimately be 100% italic.
# ASTERISK_NOISE: per-word emphasis spans (`*word *`) in the Markdown before
#   the file's emphasis layer is judged mangled rather than missing. The
#   corpus is lopsided on this: 111 files have none at all, 42 have fewer
#   than 20, and of the 114 above that most have hundreds (ONS_Supplement_205
#   has over a thousand). 20 is low enough to catch a file whose asterisks are
#   only starting to be cleaned.
RATIO, MARGIN = 0.85, 0.10
CASE_WEIGHT, DENSITY, MIN_EDGE = 0.08, 0.80, 2
TRIGRAM = 0.35
MIN_LEN, MIN_WORDS, MAX_LEN = 12, 2, 200
ITALIC_NOISE, PAGE_CHARS = 0.9, 200
BASELINE_GAP, COLUMN_GAP = 14.0, 24.0
ASTERISK_NOISE = 20

ITALIC_FLAG = 2 ** 1  # PyMuPDF span flags bit 1
# Lines the matcher will not look at: a table row, an HTML comment (the
# `<!-- figure ... -->` and `<!-- OCR: ... -->` markers the other skills
# write), a fenced block, a quote.
# A `#` heading is skipped whole: `pdfmd` turns the masthead's own run-in
# labels into headings (`## Annual Subscription`), and italicising a line that
# is already marked up as a head restyles the Markdown rather than restoring
# the scan. An italic title *inside* a heading is lost with it; that is the
# cheaper mistake.
SKIP_MD = ("|", "<!--", ">", "```", "#")
# Characters that make a span unsafe to wrap: Markdown that would nest, or a
# marker another skill owns.
UNSAFE_CHARS = set("*_[]<>|`")
# `*word *` -- the per-word asterisk artifact `clean-ocr-formatting` strips.
# One short word, carrying a letter, and no bracket: `*[figure]*` is the
# figure marker the other skills write, not a mangled emphasis span, and
# counting those flagged a figure-heavy file as mangled and refused to fix it.
ARTIFACT_RE = re.compile(r"\*(?=[^\s*]*[^\W\d_])[^\s*\[\]<>()]{1,20} ?\*")
WORD_RE = re.compile(r"[A-Za-zÀ-ɏḀ-ỿ'’.-]*[A-Za-zÀ-ɏḀ-ỿ]{3,}[A-Za-zÀ-ɏḀ-ỿ'’.,:;()-]*")


# --- PDF side -------------------------------------------------------------

def span_italic(span):
    return bool(span["flags"] & ITALIC_FLAG) or "italic" in span.get("font", "").lower()
def baselines(page, drop=2.0):
    """{baseline y: line number} for every line of text on the page.

    Two things this cannot do, and both cost real fixes when it does.

    It cannot key on `bbox[1]`: a glyph box's top depends on the face, so on
    ONS_111 p5 the italic title and the roman `Vol. III (Oxford, 1934)` beside
    it keyed to different lines, the title then looked like a whole line, and
    the two bibliography entries below it were joined into one run that
    matched nothing. `origin` is the baseline the typesetter set and every
    face on the line shares it.

    It cannot round into fixed buckets either. Baselines on one line differ by
    fractions of a point and a bucket boundary falls where it likes, which
    split `Fatihin` from `Sikke ve Madalyalari` on ONS_134 p6. The baselines
    are clustered instead, each line taking whatever sits within `drop`.
    """
    ys = sorted({span["origin"][1]
                 for block in page.get_text("dict")["blocks"]
                 if block.get("type") == 0
                 for line in block["lines"] for span in line["spans"]
                 if span["text"].strip()})
    out, line_no = {}, 0
    for i, y in enumerate(ys):
        if i and y - ys[i - 1] > drop:
            line_no += 1
        out[y] = line_no
    return out


def page_segments(page, drop=2.0, column_gap=COLUMN_GAP):
    """The page's lines, cut at column boundaries, each with its own spans.

    A segment is what a reader would call a line: one baseline, within one
    column. Blocks are no use for this -- ABBYY puts a line in a block,
    ONS_210 (born-digital, 13,989 blocks to the page) puts a caption across
    several of them mid-word -- and a whole baseline is no use either, because
    on a two-column page it runs from the left column's first word to the
    right column's last, and then every run in the left column looks like it
    stops in the middle of its line.
    """
    keys = baselines(page, drop)
    rows = {}
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["text"].strip():
                    rows.setdefault(keys[span["origin"][1]], []).append(span)
    segments = []
    for line_no in sorted(rows):
        current = None
        for span in sorted(rows[line_no], key=lambda s: s["bbox"][0]):
            if current and span["bbox"][0] - current["x1"] <= column_gap:
                current["x1"] = max(current["x1"], span["bbox"][2])
                current["words"] += len(span["text"].split())
                current["spans"].append(span)
            else:
                current = {"line": line_no, "y": span["origin"][1],
                           "x0": span["bbox"][0], "x1": span["bbox"][2],
                           "words": len(span["text"].split()), "spans": [span]}
                segments.append(current)
    return segments


def line_pitch(segments):
    """The page's median step from one line to the next, within a column.

    Measured down a column, not down the page. A two-column page interleaves
    its baselines, so the gaps between them in reading order are a mixture of
    real line pitch and the offset between the columns, and the median of that
    mixture is smaller than either. On ONS_210 p19 it came out at 6.4 points
    against a true pitch of 10.4, which closed the join window below the
    page's own line spacing and left a quotation running over five lines in
    five pieces.

    Line numbers cannot stand in for it: they count lines of text, and two
    captions with a plate between them are consecutive by that count.
    """
    steps = []
    for i, seg in enumerate(segments):
        for other in segments[i + 1:]:
            if other["y"] <= seg["y"]:
                continue
            if other["y"] - seg["y"] > 40:
                break
            if min(seg["x1"], other["x1"]) - max(seg["x0"], other["x0"]) > 0:
                steps.append(other["y"] - seg["y"])
                break
    return sorted(steps)[len(steps) // 2] if steps else None


def line_measure(segments):
    """The width of a full line on this page -- a column's measure.

    The median, not a high quantile: a two-column page carries a few lines
    that span both columns (a heading, a footnote rule's text) and they are
    half as wide again as any line in a column. Taken at the 90th percentile
    those set the measure, every line in a column then counts as short, and
    nothing is ever read as continuing onto the next line -- which is what
    kept ONS_210 p19's five-line quotation in five pieces.
    """
    widths = sorted(seg["x1"] - seg["x0"] for seg in segments)
    return widths[len(widths) // 2] if widths else 0.0


def italic_runs(page, pno, drop=2.0, gap=BASELINE_GAP, edge=3.0):
    """The page's italic passages, as a reader would see them.

    Two joins, because the span is not the unit of emphasis and neither is
    the block.

    Along the line  Italic spans side by side in one segment are one run.
                    ABBYY splits `Ta 'rikh al-rusul` at the quote; ONS_210
                    splits `Bukhara` across two blocks 4 points apart on the
                    page, both carrying the `k` where they overlap.
    Down the lines  A run that reaches the end of its segment continues in one
                    that starts the segment below. That is how a quotation set
                    in italics arrives (ONS_210 p19 runs one over five lines)
                    and how a title wraps (`Fatihin` / `Sikke ve Madalyalari`
                    on ONS_134 p6). The test is where the run sits in its
                    line, not whether the two overlap in x -- justified prose
                    wraps from the right margin to the left, so a continuation
                    never overlaps what it continues.

    The unjoined pieces are kept on the run as `pieces`: the second join is a
    judgement, so the matcher falls back to them when the joined text matches
    nothing.
    """
    segments = page_segments(page, drop)
    pitch = line_pitch(segments)
    measure = line_measure(segments)
    runs = []
    for seg in segments:
        current = None
        for span in sorted(seg["spans"], key=lambda s: s["bbox"][0]):
            if not span_italic(span):
                current = None
                continue
            text, bbox = span["text"], list(span["bbox"])
            if current and -6 <= bbox[0] - current["bbox"][2] <= gap:
                # Overlapping blocks share their boundary glyph: ONS_210's
                # `Buk` and `khara` overlap by four points, both with the `k`.
                if (bbox[0] < current["bbox"][2] and text[:1]
                        and current["text"].endswith(text[0])):
                    text = text[1:]
                joiner = "" if (bbox[0] - current["bbox"][2] < 1.5
                                or current["text"].endswith(" ")
                                or text.startswith(" ")) else " "
                current["text"] += joiner + text
                current["pieces"].append(text)
                current["bbox"][2] = max(current["bbox"][2], bbox[2])
                continue
            current = {"text": text, "bbox": bbox, "page": pno,
                       "pieces": [text], "seg": seg, "line": seg["line"],
                       "y": seg["y"]}
            runs.append(current)

    for run in runs:
        seg = run["seg"]
        run["at_start"] = run["bbox"][0] <= seg["x0"] + edge
        run["at_end"] = run["bbox"][2] >= seg["x1"] - edge
        run["line_words"] = seg["words"]

    out = []
    for run in sorted(runs, key=lambda r: (r["y"], r["bbox"][0])):
        host = None
        # The line a run continues is not always the one before it in reading
        # order. ONS_210 p2 sets its plates two to a row, so the second line
        # of a right-hand caption follows a line of the left-hand one. The
        # candidate is looked for up the column instead, within a line of
        # space.
        for cand in reversed(out[-8:]):
            if not pitch or run["y"] - cand["y"] > pitch * 1.6:
                break
            if run["y"] <= cand["y"] or not cand["at_end"] or not run["at_start"]:
                continue
            if min(cand["seg"]["x1"], run["seg"]["x1"]) \
                    - max(cand["seg"]["x0"], run["seg"]["x0"]) <= 0:
                continue  # a different column
            # Text continues onto the next line because it ran out of room, so
            # the line above a continuation is a full one. A short line is a
            # cell or a label instead: ONS_111 p4 sets `silver` and `copper`
            # bold-italic on consecutive lines as column heads, and joined
            # they match `silver and copper` in a paragraph forty lines away.
            if cand["seg"]["x1"] - cand["seg"]["x0"] < measure * 0.6:
                continue
            host = cand
            break
        if host is None:
            out.append(run)
            continue
        host["text"] = host["text"].rstrip() + " " + run["text"].lstrip()
        host["pieces"].append(run["text"])
        host["at_end"], host["line"] = run["at_end"], run["line"]
        host["seg"], host["y"] = run["seg"], run["y"]

    for run in out:
        run["text"] = re.sub(r"\s+", " ", run["text"]).strip()
        run["pieces"] = [re.sub(r"\s+", " ", piece).strip() for piece in run["pieces"]]
        del run["seg"]
    return out


def italic_share(page):
    """(fraction of the page's characters that are italic, characters seen)."""
    total = ital = 0
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                n = len(span["text"].strip())
                if not n:
                    continue
                total += n
                if span_italic(span):
                    ital += n
    return (ital / total if total else 0.0), total


# --- matching -------------------------------------------------------------

def normalize(text):
    """Lowercase alphanumerics, plus a map back to columns in the original.

    One character in, one character out -- `cols[i]` has to be the column
    `chars[i]` came from, and `str.lower()` does not promise that: Turkish
    `İ.lower()` is two characters, `i` plus a combining dot. ONS_219 line 1432
    has one, and the extra character shifted every column after it and then
    ran the map off its end.
    """
    chars, cols = [], []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.lower()[:1])
            cols.append(i)
    return "".join(chars), cols


def word_count(text):
    return sum(1 for t in text.split() if WORD_RE.fullmatch(t))


def is_text(run_text):
    """True for a run that reads as words rather than as tagged garble.

    ABBYY applies an italic face to unreadable glyph runs as willingly as to
    prose. `IVi-`, `J:>`, `M. jf- 17,` and `KT'J^` are all flagged italic in
    ONS_111 and none of them is anything. A run has to carry MIN_WORDS real
    words, and they have to be most of it -- `2=T and` is not a citation.
    """
    toks = run_text.split()
    if not toks:
        return False
    return (word_count(run_text) >= MIN_WORDS
            and word_count(run_text) / len(toks) >= 0.5)


def find_in_line(hay, needle, slack=4):
    """(score, first, last, repeats) for the best run of `needle` in `hay`.

    `score` is how much of the needle was found, `first`/`last` bound it in
    `hay`, and `repeats` is how many times the anchor occurs in the line.

    The window is the whole point. `detect_headings.anchored()` compares a
    heading against a line of much the same length, so it can take
    SequenceMatcher's matching blocks at face value and merely check they sit
    together. Here the haystack is a whole paragraph -- these Markdown files
    run 2000 characters to the line -- and the matcher is free to satisfy a
    short needle out of letters scattered the length of it. That is not a
    tuning problem: `Munzen der Rasuliden` sits verbatim in ONS_111 line 79
    and scored 0.00, because the blocks it was built from spanned 600
    characters and the contiguity test threw the whole thing out.

    So the longest common block is used as an anchor instead: it fixes where
    in the line the run must be, a window of the needle's own length is cut
    there, and the score is measured inside that window only.
    """
    anchor = difflib.SequenceMatcher(None, hay, needle, autojunk=False) \
        .find_longest_match(0, len(hay), 0, len(needle))
    if not anchor.size:
        return 0.0, 0, 0, 0
    start = max(0, anchor.a - anchor.b - slack)
    stop = min(len(hay), start + len(needle) + 2 * slack)
    window = hay[start:stop]
    blocks = [b for b in difflib.SequenceMatcher(None, window, needle,
                                                 autojunk=False)
              .get_matching_blocks() if b.size]
    if not blocks:
        return 0.0, 0, 0, 0
    # Trim coincidental single letters off both ends before the span is
    # measured or scored; what is left is the part that really agrees.
    solid = [b for b in blocks if b.size >= MIN_EDGE]
    if not solid:
        return 0.0, 0, 0, 0
    lo, hi = blocks.index(solid[0]), blocks.index(solid[-1])
    blocks = blocks[lo:hi + 1]
    score = sum(b.size for b in blocks) / len(needle)
    first = start + blocks[0].a
    last = start + blocks[-1].a + blocks[-1].size
    if (last - first) and score * len(needle) / (last - first) < DENSITY:
        return 0.0, 0, 0, 0
    # How many places in this line could have been the anchor. A line that
    # repeats the run's own distinctive words cannot say which one is italic:
    # `song-pei` occurs 14 times in ONS_111 line 187 alone.
    repeats = hay.count(hay[anchor.a:anchor.a + anchor.size]) \
        if anchor.size >= 6 else 1
    return score, first, last, repeats


def case_agreement(run_text, segment):
    """How much two texts agree on which words are capitalised, 0.0 to 1.0.

    The one signal `normalize()` throws away that is worth getting back.
    ONS_111's masthead label `Annual Subscription` matches two lines perfectly
    -- its own, and a book advertisement's `annual subscription: within USA
    $12`. Nothing in the letters chooses between them; the capitals do.
    """
    a = [w[0] for w in re.findall(r"[^\W\d_]+", run_text, re.UNICODE)]
    b = [w[0] for w in re.findall(r"[^\W\d_]+", segment, re.UNICODE)]
    if not a or not b:
        return 0.5
    pairs = list(zip(a, b))
    return sum(x.isupper() == y.isupper() for x, y in pairs) / len(pairs)


def trigrams(text):
    return {text[i:i + 3] for i in range(len(text) - 2)}


def md_index(md_lines):
    """Normalise each Markdown line once, not once per run.

    The matcher asks the same question of the same lines for every italic run
    in the file -- 477 runs against 400 paragraphs on ONS_230 -- and
    normalising a 2000-character paragraph is not free. Lines the matcher will
    never look at are entered as None so they stay cheap to skip.
    """
    index = []
    for line in md_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(SKIP_MD):
            index.append(None)
            continue
        hay, cols = normalize(line)
        index.append((hay, cols, trigrams(hay)) if hay else None)
    return index


def candidates(index, md_lines, run_text, needle_norm, min_ratio=RATIO):
    """Every Markdown line that plausibly carries this run, best first.

    Each hit is (adjusted score, row, start, end, repeats, raw ratio). The
    adjustment is the capitalisation agreement, worth up to +/-CASE_WEIGHT --
    enough to separate two otherwise identical matches, never enough to
    promote one that failed on its letters.

    The trigram prefilter is only for speed, and it is most of the file's
    running time saved: these Markdown lines are whole paragraphs, often 2000
    characters, and the fuzzy match is not cheap enough to run against every
    one of them for every run.
    """
    want = trigrams(needle_norm)
    hits = []
    for row, entry in enumerate(index):
        if entry is None:
            continue
        hay, cols, grams = entry
        if len(hay) < len(needle_norm) * 0.5:
            continue
        # Three-letter sequences shared with the line. Single letters are too
        # common to filter anything out of a 2000-character paragraph, and the
        # fuzzy match that follows is what this file spends its time on.
        # Garble costs a true match a few of these, never most: `Munzen` and
        # `Münzen` share 15 of 18.
        if want and len(want & grams) < len(want) * TRIGRAM:
            continue
        line = md_lines[row]
        score, first, last, repeats = find_in_line(hay, needle_norm)
        if score < min_ratio:
            continue
        start, end = cols[first], cols[last - 1] + 1
        adjusted = score + CASE_WEIGHT * (
            case_agreement(run_text, line[start:end]) - 0.5) * 2
        # The threshold applies to the adjusted score, not the raw one, so
        # that disagreeing capitals can sink a borderline match outright.
        # ONS_112's italic head `Resignations etc.` matches the prose
        # `resignations and other` at 0.87 on letters alone.
        if adjusted < min_ratio:
            continue
        hits.append((adjusted, row, start, end, repeats, score))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return hits


# --- verdicts -------------------------------------------------------------

FIXABLE = ("MISSING",)
REVIEW = ("PARTIAL", "AMBIGUOUS", "UNSAFE", "OVERLONG")
ORDER = ("MISSING", "PARTIAL", "AMBIGUOUS", "UNSAFE", "OVERLONG", "LOST",
         "PRESENT", "NOISE")
QUIET = ("PRESENT", "NOISE")  # only shown with -v


def trim_span(line, start, end):
    """Pull the span in to the words it covers, or None if nothing is left.

    Two jobs. Markdown will not open emphasis on whitespace (`* forte,*` is
    literal asterisks, not italics), and the matched block routinely stops one
    character into a word because that is where the OCR texts stopped agreeing
    -- `Lahor` for `Lahore`. Snapping out to the word boundary and back in off
    the whitespace is what makes the inserted markers land where a reader
    would put them.
    """
    while start > 0 and line[start - 1].isalnum():
        start -= 1
    while end < len(line) and line[end].isalnum():
        end += 1
    while start < end and not (line[start].isalnum() or line[start] in "('\"‘“"):
        start += 1
    while end > start and not (line[end - 1].isalnum() or line[end - 1] in ".,;:!?)'\"’”"):
        end -= 1
    return (start, end) if end - start >= MIN_LEN else None


def classify(line, start, end):
    """MISSING / PRESENT / PARTIAL / UNSAFE for a located span."""
    span = line[start:end]
    before, after = line[:start], line[end:]
    if set(span) & UNSAFE_CHARS:
        # Emphasis already inside the span, or a marker this script must not
        # nest inside. Either way a human decides.
        return "PARTIAL" if set(span) & set("*_") else "UNSAFE"
    # Already wrapped: `*span*`, `**span**`, `_span_`.
    for mark in ("**", "*", "_"):
        if before.endswith(mark) and after.startswith(mark):
            return "PRESENT"
    # An emphasis run that is open across this span -- an odd number of
    # unmatched markers behind it. Reported, never written into.
    if (before.count("*") - before.count("**") * 2) % 2:
        return "PARTIAL"
    if "<!--" in before and "-->" not in before.rsplit("<!--", 1)[1]:
        return "UNSAFE"  # inside a comment another skill owns
    return "MISSING"


def pair_repeats(runs, index, md_lines, min_ratio=RATIO):
    """Match a title cited k times in the scan to its k places in the Markdown.

    A journal cited twice produces two identical runs and two equally good
    matches, and both are AMBIGUOUS under the margin test -- ONS_134 cites
    `Numismatic Digest` on p6 and p8 and `Xinjiang Tuzhi` twice on p8. But
    both files are the same publication read in the same order, so when the
    counts agree exactly the i-th run is the i-th match (here: lines 292 and
    364, lines 383 and 396) and the ambiguity is only apparent.

    Off by default all the same. The counts agreeing is evidence, not proof:
    one false match among the k, or one citation the Markdown lost, shifts the
    whole assignment by one and writes every marker in the wrong place. Opt in
    with --pair-repeats, and read the diff.
    """
    groups = {}
    for run in runs:
        if not is_text(run["text"]):
            continue
        needle, _ = normalize(run["text"])
        if len(needle) >= MIN_LEN:
            groups.setdefault(needle, []).append(run)
    paired = {}
    for needle, group in groups.items():
        if len(group) < 2:
            continue
        hits = candidates(index, md_lines, group[0]["text"], needle, min_ratio)
        # One hit per Markdown line, in document order, and none of them a
        # line that repeats the words itself -- that ambiguity is not the kind
        # counting can resolve.
        hits = sorted(hits, key=lambda h: h[1])
        if len(hits) == len(group) and all(h[4] == 1 for h in hits):
            for run, hit in zip(group, hits):
                paired[id(run)] = hit
    return paired


def analyse(runs, index, md_lines, min_ratio=RATIO, margin=MARGIN, pairing=None):
    found, taken = [], []
    pairing = pairing or {}
    for run in runs:
        if not is_text(run["text"]):
            found.append({"verdict": "NOISE", "run": run, "text": run["text"]})
            continue
        # The joined run first; its per-line pieces only if that found nothing,
        # which is how a wrongly joined pair of neighbouring titles still gets
        # reported instead of vanishing into LOST.
        attempts = [run["text"]]
        if len(run["pieces"]) > 1:
            attempts += [p for p in run["pieces"] if is_text(p)]
        for n, text in enumerate(attempts):
            needle, _ = normalize(text)
            if len(needle) < MIN_LEN:
                continue
            hits = [pairing[id(run)]] if id(run) in pairing \
                else candidates(index, md_lines, text, needle, min_ratio)
            if not hits:
                if n < len(attempts) - 1:
                    continue
                found.append({"verdict": "LOST", "run": run, "text": text})
                break
            score, row, start, end, repeats, ratio = hits[0]
            rec = {"run": run, "text": text, "row": row, "ratio": ratio}
            # Two readings of the same words: a second line that matches about
            # as well, or one line that repeats the run's own anchor words.
            rival = len(hits) > 1 and hits[1][0] > score - margin
            if (rival or repeats > 1) and id(run) not in pairing:
                rec["verdict"] = "AMBIGUOUS"
                rec["start"], rec["end"] = start, end
                rec["others"] = (len(hits) - 1) if rival else repeats - 1
                found.append(rec)
                break
            if len(needle) > MAX_LEN:
                rec["verdict"] = "OVERLONG"
                rec["start"], rec["end"] = start, end
                found.append(rec)
                break
            trimmed = trim_span(md_lines[row], start, end)
            if trimmed is None:
                rec["verdict"] = "UNSAFE"
                rec["start"], rec["end"] = start, end
                found.append(rec)
                break
            start, end = trimmed
            rec["start"], rec["end"] = start, end
            rec["verdict"] = classify(md_lines[row], start, end)
            # Two runs that landed on the same words: the second is a repeat of
            # a running head or a mis-match, and wrapping both would nest.
            if rec["verdict"] == "MISSING" and any(
                    r == row and not (end <= s or start >= e) for r, s, e in taken):
                rec["verdict"] = "AMBIGUOUS"
                rec["others"] = 1
            if rec["verdict"] == "MISSING":
                taken.append((row, start, end))
            found.append(rec)
            break
    found.sort(key=lambda f: (ORDER.index(f["verdict"]), f["run"]["page"],
                              f.get("row", 0)))
    return found


# --- reporting and repair -------------------------------------------------

def artifact_count(md_text):
    return len(ARTIFACT_RE.findall(md_text))


def report(stem, md_lines, found, verbose, artifacts):
    counts = {}
    for f in found:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    open_n = sum(n for v, n in counts.items() if v in FIXABLE)
    review_n = sum(n for v, n in counts.items() if v in REVIEW)
    tail = "  ".join(f"{v} {counts[v]}" for v in ORDER if v in counts)
    print(f"{stem}: {len(found)} italic run(s) | {tail or 'none'}"
          f"  -- {open_n} to fix" + (f", {review_n} to review" if review_n else ""))
    if artifacts > ASTERISK_NOISE:
        print(f"  note: {artifacts} per-word asterisk span(s) in the Markdown -- "
              "this file's emphasis is mangled, not missing. Run "
              "clean-ocr-formatting first; fix will not write here.")
    for f in found:
        if f["verdict"] in QUIET and not verbose:
            continue
        run = f["run"]
        print(f"  {f['verdict']:10s} p{run['page']:<3d} "
              f"ratio={f.get('ratio', 0.0):4.2f} {f['text'][:56]!r}")
        if "row" in f:
            line = md_lines[f["row"]]
            lo, hi = max(0, f["start"] - 24), min(len(line), f["end"] + 24)
            print(f"{'':13s}md line {f['row'] + 1}: ...{line[lo:f['start']]}"
                  f"[{line[f['start']:f['end']]}]{line[f['end']:hi]}...")
    return open_n


# What may sit between two spans of one italic passage and still be part of
# it: nothing, or the punctuation a line break was wrapped around.
JOIN_RE = re.compile(r"^[\s,;:.\u2013-]{0,3}$")


def merge_spans(line, spans):
    """Fuse spans of one passage that the text layer reported line by line.

    A caption set entirely in italics comes back as one run per line of the
    scan -- ONS_210 p2 gives `Turko-Hephthalite ... Khusru`, `II and legends
    in`, `cursive Greek, Brahmi and Pahlevi` for one caption that `pdfmd` put
    on a single Markdown line. Wrapped separately they render as three italic
    phrases with roman joints; wrapped together they render as the caption.
    """
    merged = []
    for start, end in sorted(spans):
        if merged and JOIN_RE.match(line[merged[-1][1]:start]):
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def apply(md_lines, found):
    """Wrap every MISSING span in `*...*`. Returns (new lines, count)."""
    edits = {}
    for f in found:
        if f["verdict"] in FIXABLE:
            edits.setdefault(f["row"], []).append((f["start"], f["end"]))
    out, applied = [], 0
    for row, line in enumerate(md_lines):
        spans = merge_spans(line, edits.get(row, []))
        for start, end in sorted(spans, reverse=True):  # right to left
            line = f"{line[:start]}*{line[start:end]}*{line[end:]}"
            applied += 1
        out.append(line)
    return out, applied


def run_file(stem, args):
    pdf, md = PDF_DIR / f"{stem}.pdf", MD_DIR / f"{stem}.md"
    if not pdf.exists():
        return None, f"{stem}: no PDF at {pdf}"
    if not md.exists():
        return None, f"{stem}: no Markdown at {md}"
    md_text = md.read_text(encoding="utf-8")
    md_lines = md_text.split("\n")
    runs, dropped = [], 0
    with fitz.open(pdf) as doc:
        for pno, page in enumerate(doc, start=1):
            share, chars = italic_share(page)
            if chars >= PAGE_CHARS and share > args.italic_noise:
                dropped += 1
                continue
            runs.extend(italic_runs(page, pno))
    index = md_index(md_lines)
    pairing = pair_repeats(runs, index, md_lines, args.min_ratio) \
        if args.pair_repeats else {}
    found = analyse(runs, index, md_lines, args.min_ratio, args.margin, pairing)
    return (md, md_lines, found, artifact_count(md_text), dropped), None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("scan", "report, change nothing"),
                            ("fix", "wrap the MISSING spans in the Markdown")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("stems", nargs="+", metavar="ONS_111")
        p.add_argument("-v", "--verbose", action="store_true",
                       help="also show runs already emphasised (PRESENT) and "
                            "runs that are not text (NOISE)")
        p.add_argument("--min-ratio", type=float, default=RATIO,
                       help="how much of an italic run must be found in a "
                            "Markdown line before they count as the same text "
                            f"(default {RATIO})")
        p.add_argument("--margin", type=float, default=MARGIN,
                       help="how far the best match must beat the second best "
                            f"before it is trusted (default {MARGIN})")
        p.add_argument("--pair-repeats", action="store_true",
                       help="when a run occurs k times in the scan and matches "
                            "exactly k lines of the Markdown, pair them in "
                            "document order instead of calling them all "
                            "AMBIGUOUS. Off by default: a single bad match "
                            "shifts the whole assignment")
        p.add_argument("--italic-noise", type=float, default=ITALIC_NOISE,
                       help="fraction of a page's characters that may be "
                            "italic before the page is judged mis-tagged and "
                            f"dropped whole (default {ITALIC_NOISE})")
        if name == "fix":
            p.add_argument("--force", action="store_true",
                           help="write even to a file whose emphasis layer is "
                                "mangled with per-word asterisks (normally "
                                "clean-ocr-formatting's job, and refused)")
    args = ap.parse_args()

    total = 0
    for stem in args.stems:
        data, err = run_file(stem, args)
        if err:
            print(err, file=sys.stderr)
            total += 1
            continue
        md, md_lines, found, artifacts, dropped = data
        if dropped:
            print(f"{stem}: {dropped} page(s) dropped -- italic end to end, "
                  "the text layer's own mistake")
        open_n = report(stem, md_lines, found, args.verbose, artifacts)
        if args.cmd == "fix" and open_n:
            if artifacts > ASTERISK_NOISE and not args.force:
                print("  refused: clean this file's per-word asterisks first "
                      "(clean-ocr-formatting), or pass --force")
            else:
                new, applied = apply(md_lines, found)
                if applied:
                    md.write_text("\n".join(new), encoding="utf-8")
                    print(f"  wrote {md} ({applied} span(s) italicised)")
        total += open_n
    return 1 if total else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # `| head`, and the reader stopped reading
        os._exit(0)
