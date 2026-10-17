#!/usr/bin/env python3
"""Find lists that a `jons/` Markdown file does not render as lists.

`pdfmd` reads a list on the page as running text. The items come out as
one paragraph (`1A: Coins bearing ... 1341. 1B: Coins bearing ...`), as
labelled lines kramdown joins into one (`i. The silver ...` / `ii. The
silver ...`), or with their labels dropped altogether (ONS_130's eight
Bhutanese coins became `Obv. ... Wt. 3.4g. Obv. As last ...`). None of
these renders as a list, and the last leaves nothing in the Markdown to
search for. The scan still shows the list, though: each item starts a new
line, at the same left edge as the others, usually with a label the text
layer kept even where the Markdown lost it.

    detect_lists.py lint ONS_130            # Markdown only, seconds
    detect_lists.py lint jons/*.md
    detect_lists.py screen ONS_130          # scan against Markdown
    detect_lists.py screen --all
    detect_lists.py screen ONS_130 --md old.md
    detect_lists.py rows ONS_130            # crop_sheets.py rows

`lint` needs no PDF. It reports:
    LINED     two or more lines or paragraphs opening with sequential labels
              kramdown does not read as list items -- `1)`, `(a)`, `ii.`,
              `1A:` -- whether they end in `<br>` or not
    UNMARKED  a bullet list whose items open with labels, with no
              `{: .labelled}` above it, so it renders a bullet and a label
    IAL       a `{: .labelled}` with no blank line above it (kramdown hangs
              it on the paragraph instead), no bullet item under it, or an
              item under it with no label (the bullet is hidden, so nothing
              marks the item)

`screen` reads the scan's text layer for runs of two or more lines at one
left edge whose labels count up -- arabic, roman, letter, digit+letter, read
OCR-tolerantly (`lA` is 1A, `ili.` is iii., a bare `1` followed by a
typewriter tab is 1., and `I` / `II` with the dots lost count on consecutive
lines only) -- with the lines of each item between them. Each line
is placed in the Markdown, and each break the page makes is read off what
the Markdown has there: a list item, a `<br>`, a paragraph break, or nothing
(a soft break or the middle of a line, both of which render as a space).
Verdicts:
    FLATTENED  an item glued to the one before it: the Markdown has no
               break where the page starts the next item. Labels the
               Markdown dropped are listed.
    NOT-LIST   every item starts its own line or paragraph, but not as a
               list item -- labelled paragraphs, or `<br>` lines
    RUN-ON     (`--loose`) the items are separate, but a short line inside
               one is run on into the next (ONS_130's Copper / Obverse /
               Reverse lines before they were given `<br>`)
    OK / UNPLACED  shown with -v; UNPLACED is a run the Markdown match was
               too weak to judge

Exit status 1 when anything is reported. Pages are 0-based, as in every
`page=N` marker, and `rect=` is in PDF points for `detect_script_garble.py
render --clip`.

Blind spots: a list whose items carry no label is not looked for at all --
a screen for short lines at one left edge was tried and dropped, because on
these justified typescripts it mostly finds the narrow columns of two-column
pages (8,719 hits); a list set in two columns side by side reads as a table
and is skipped (`detect-missing-tables`' job); a run whose text layer and
Markdown disagree badly (catalogue rows, heavy garble on either side) comes
back UNPLACED.
"""
import argparse
import os
import pathlib
import re
import statistics
import sys

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF only exposes the legacy `fitz` name
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF "
                 f"(see .claude/skills/requirements.txt).")

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "restore-headings" / "scripts"))
_stderr, sys.stderr = sys.stderr, open(os.devnull, "w")  # its archive warning; main() gives ours
try:
    from detect_headings import mostly_words, normalize  # noqa: E402
finally:
    sys.stderr.close()
    sys.stderr = _stderr

# ONS_ARCHIVE_DIR overrides the default checkout-relative path -- set it when
# the ons-website PDFs live somewhere else on this machine (they come from
# the private esnible/ons-website repo, not this one, so the path varies).
PDF_DIR = pathlib.Path(
    os.environ.get("ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")
).expanduser()
MD_DIR = HERE.parents[4] / "jons"

# --- tuned defaults -------------------------------------------------------
# EDGE: points two lines' left edges may differ by and still be one column
#   of items. The scans wobble by a point or two; a paragraph indent is 20+.
# COL_GAP: fraction of the page width. Text-layer fragments on one baseline
#   further apart than this are two columns, not one line.
# MAX_BETWEEN: lines an item may run to between one label and the next.
# SLACK: points of room a line may leave at its end over and above the next
#   line's first word and a space, before the break counts as deliberate.
#   STRONG adds this fraction of the measure, for breaks with no label to
#   back them up (a short line inside an item): a ragged-right
#   typescript leaves a few characters of room on half its lines.
# K / LEAD / SNAP: Markdown matching -- see MdIndex.
EDGE, COL_GAP, MAX_BETWEEN, SLACK, STRONG = 6.0, 0.18, 12, 4.0, 0.15
K, LEAD, SNAP = 7, 2, 3
DEBUG = False

# --- labels ---------------------------------------------------------------


def _to_roman(n):
    out = ""
    for v, s in ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= v:
            out, n = out + s, n - v
    return out


ROMAN = {_to_roman(n): n for n in range(1, 40)}
LABEL_RE = re.compile(
    r"(?P<open>\()?(?P<lab>\d{1,3}[A-Za-z]|\d{1,3}|[ivxIVX]{1,6}|[ivxl1]{2,6}|[A-Za-z])"
    r"(?P<close>[.):])(?=\s+\S)")
# The text layer's `lA Coins bearing ...`: a digit+letter label whose `1`
# came back `l` or `I` and whose colon was lost.
BARE_KEY_RE = re.compile(r"(?P<lab>[lI1]|\d{1,2})(?P<let>[A-H])(?=\s+[A-Z])")
REST_RE = re.compile(r"\s*[\w\"'‘“(\[*]")


def parse_label(text, ocr=False):
    """(candidates, label) for a label opening `text`, else None.

    A candidate is (kind, value). `i` is both roman 1 and the letter i, so a
    label can carry several; the run that takes it settles which. With
    `ocr`, a lone `l` or `I` may also be the digit 1."""
    m = LABEL_RE.match(text)
    if m:
        lab, close = m["lab"], m["close"]
        if m["open"] and close != ")":
            return None
        key = re.fullmatch(r"\d{1,3}[A-Za-z]", lab)
        if close == ":" and not key:
            return None
        rest = text[m.end():]
        if not REST_RE.match(rest):
            return None
        # `A. K. Narain`: initials, not a label
        if len(lab) == 1 and lab.isupper() and close == "." \
                and re.match(r"\s*[A-Z]\.", rest):
            return None
        low, cands = lab.lower(), set()
        if lab.isdigit():
            cands.add(("n", int(lab)))
        elif key:
            cands.add(("k", int(lab[:-1]) * 100 + ord(low[-1]) - 96))
        else:
            case = "u" if lab.isupper() else "l"
            if low in ROMAN:
                cands.add(("r", ROMAN[low]))
            if len(lab) == 1:
                cands.add(("a" + case, ord(low) - 96))
            if ocr and lab in ("l", "I"):
                cands.add(("n", 1))
        if ocr and not any(k[0] == "r" for k in cands) \
                and len(lab) > 1 and re.fullmatch(r"[ivxl1]+", lab) \
                and re.sub(r"[l1]", "i", lab) in ROMAN:
            cands.add(("r", ROMAN[re.sub(r"[l1]", "i", lab)]))
        return (frozenset(cands), m.group(0)) if cands else None
    if ocr:
        m = BARE_KEY_RE.match(text)
        if m:
            n = 1 if m["lab"] in "lI" else int(m["lab"])
            return frozenset({("k", n * 100 + ord(m["let"].lower()) - 96)}), m.group(0)
    return None


def follows(prev, cur, kind=None):
    """The kind under which `cur` is the label after `prev`, else None."""
    for k, v in prev:
        if kind and k != kind:
            continue
        nxt = {v + 1}
        if k == "k":  # 1A -> 1B, and 1B -> 2A
            nxt.add((v // 100 + 1) * 100 + 1)
        if any(k2 == k and v2 in nxt for k2, v2 in cur):
            return k
    return None


def label_norm(label):
    """A label as normalize() spells it, with the text layer's l/I for 1."""
    s = normalize(label)[0]
    return s


# --- the scan -------------------------------------------------------------


TAB_LABEL_RE = re.compile(r"\(?(\d{1,3}|[ivx]{1,5}|[a-h])[.)]?$")


def tab_label(ws, charw):
    """A label the text layer kept only as a word followed by a tab."""
    if len(ws) < 2 or not TAB_LABEL_RE.fullmatch(ws[0][4]):
        return None
    if ws[1][0] - ws[0][2] < 3 * charw + 4:
        return None
    return parse_label(ws[0][4].rstrip(".)") + ". " + ws[1][4], ocr=True)


BARE_ROMAN_RE = re.compile(r"(?P<lab>[IVX]{1,5}|[ivx]{2,5})(?=\s+[A-Z])")


def bare_roman(text):
    """A roman label whose full stop the text layer lost, as ONS_130's
    `I The silver 100 kurus piece` / `II The silver 1 lira`. Alone it is
    worthless -- `I think` -- so label_runs() keeps a run of these only when
    the numbers count up from one line to the next."""
    m = BARE_ROMAN_RE.match(text)
    if m and m["lab"].lower() in ROMAN:
        return frozenset({("r", ROMAN[m["lab"].lower()])}), m["lab"]
    return None


def page_lines(page):
    """The page's lines as a reader sees them, per column, in reading order.

    Built from word boxes so that each line knows its widest internal gap (a
    table row has one) and the width of its first word (what the line above
    would have had to fit to make the break a wrap)."""
    width = page.rect.width
    frags = {}
    for x0, y0, x1, y1, word, block, line, _ in page.get_text("words"):
        frags.setdefault((block, line), []).append((x0, y0, x1, y1, word))
    frags = sorted(frags.values(), key=lambda ws: (min(w[1] for w in ws),
                                                   min(w[0] for w in ws)))
    lines = []
    for ws in frags:
        y0 = min(w[1] for w in ws)
        x0, x1 = min(w[0] for w in ws), max(w[2] for w in ws)
        for ln in reversed(lines[-4:]):
            if abs(ln["y0"] - y0) <= 2.5 and x0 - ln["x1"] < COL_GAP * width \
                    and ln["x0"] - x1 < COL_GAP * width:
                ln["words"].extend(ws)
                ln["x0"], ln["x1"] = min(ln["x0"], x0), max(ln["x1"], x1)
                break
        else:
            lines.append({"y0": y0, "x0": x0, "x1": x1, "words": list(ws)})
    for ln in lines:
        ws = sorted(ln["words"])
        ln["y1"] = max(w[3] for w in ws)
        ln["text"] = " ".join(w[4] for w in ws)
        chars = sum(len(w[4]) for w in ws)
        ln["charw"] = sum(w[2] - w[0] for w in ws) / chars if chars else 5.0
        ln["tab"] = tab_label(ws, ln["charw"])
        gaps = [b[0] - a[2] for a, b in zip(ws, ws[1:])]
        if gaps and (ln["tab"] or parse_label(ws[0][4] + " x", ocr=True)):
            gaps = gaps[1:]  # `1.    The coin looks ...`: a tab after the label
        ln["gap"] = max(gaps, default=0.0)
        ln["first"] = ws[0][2] - ws[0][0]
        ln["col"] = 0 if ln["x0"] < 0.45 * width else 1
    long_x1 = [l["x1"] for l in lines if len(l["text"]) >= 40]
    columns = []
    for col in (0, 1):
        cl = sorted((l for l in lines if l["col"] == col), key=lambda l: l["y0"])
        if not cl:
            continue
        own = sorted(l["x1"] for l in cl if len(l["text"]) >= 40)
        ref = own if len(own) >= 4 else sorted(long_x1)
        if not ref:
            continue
        right = ref[int(len(ref) * 0.9)]
        lefts = sorted(l["x0"] for l in cl if len(l["text"]) >= 40) or [cl[0]["x0"]]
        deltas = [b["y0"] - a["y0"] for a, b in zip(cl, cl[1:]) if 0 < b["y0"] - a["y0"] < 40]
        leading = statistics.median(deltas) if deltas else 12.0
        for l in cl:
            l["right"], l["measure"], l["leading"] = right, right - lefts[0], leading
        columns.append(cl)
    return columns


def room(a, b, strong=False):
    """True when line `a` stops with room left for line `b`'s first word."""
    need = b["first"] + 2 * b["charw"] + SLACK
    if strong:
        need += STRONG * a["measure"]
    return a["right"] - a["x1"] > need


def tabular(ln):
    return ln["gap"] > 4 * ln["charw"] + 6


def label_runs(lines):
    """Runs of lines whose labels count up at one left edge.

    Returns dicts with `members` (line indices, items and the lines between
    them), `labels` (indices of the labelled lines) and `kind`."""
    parsed, bare = [None] * len(lines), set()
    for i, ln in enumerate(lines):
        if tabular(ln) or len(ln["text"]) < 4:
            continue
        lab = parse_label(ln["text"], ocr=True) or ln["tab"]
        if not lab:
            lab = bare_roman(ln["text"])
            if lab:
                bare.add(i)
        if lab:
            parsed[i] = lab
    runs = []
    for i, lab in enumerate(parsed):
        if not lab:
            continue
        x = lines[i]["x0"]
        best = None
        for run in runs:
            j = run["labels"][-1]
            if abs(lines[j]["x0"] - x) > EDGE or i - j > MAX_BETWEEN + 1:
                continue
            between = range(run["members"][-1] + 1, i)
            if any(lines[b]["x0"] < x - EDGE for b in between):
                continue  # text back at a smaller indent ended the list
            if (i in bare or j in bare) and i - j != 1:
                continue  # a bare numeral is a label only on the next line
            kind = follows(parsed[j][0], lab[0], run["kind"])
            if kind:
                best = (run, kind)
        if best:
            run, kind = best
            run["kind"] = kind
            run["members"].extend(range(run["members"][-1] + 1, i + 1))
            run["labels"].append(i)
        else:
            runs.append({"members": [i], "labels": [i], "kind": None})
    out = []
    for run in runs:
        if len(run["labels"]) < 2:
            continue
        # the last item's own lines, as long as the longest item before it
        labs = run["labels"]
        longest = max(b - a for a, b in zip(labs, labs[1:])) - 1
        hang = {round(lines[m]["x0"]) for m in run["members"] if m not in labs}
        x = lines[labs[-1]]["x0"]
        j = labs[-1]
        while longest > 0 and j + 1 < len(lines):
            nxt = lines[j + 1]
            if parsed[j + 1] or nxt["y0"] - lines[j]["y0"] > 1.6 * nxt["leading"]:
                break
            if not (abs(nxt["x0"] - x) <= EDGE or any(abs(nxt["x0"] - h) <= EDGE for h in hang)):
                break
            j += 1
            longest -= 1
            run["members"].append(j)
        run["parsed"] = {i: parsed[i] for i in labs}
        out.append(run)
    return out


# --- the Markdown ---------------------------------------------------------

DROP_RE = re.compile(r"<!--.*?-->|<[^>\n]+>|\]\([^)\s]*\)")
IAL_RE = re.compile(r"^\s*\{:.*\}\s*$")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}\.)\s+")
HEAD_RE = re.compile(r"^\s{0,3}#{1,6}\s")
FENCE_RE = re.compile(r"^\s*```")


class MdIndex:
    """The Markdown as one normalized string, mapped back to rows.

    Lines of the scan are placed by voting: every K-character chunk of a
    line's normalized text that occurs in the Markdown proposes where the
    line starts, and the best-supported start wins, preferring one at or
    after the previous line's. The text layer and the Markdown were OCR'd
    separately, so whole-line matching fails exactly where the list is.
    """

    def __init__(self, text):
        self.rows = text.split("\n")
        chars, where, self.kind, self.first = [], [], [], []
        in_fence = in_comment = False
        for r, line in enumerate(self.rows):
            kind = "text"
            if FENCE_RE.match(line):
                in_fence, kind = not in_fence, "fence"
            elif in_fence:
                kind = "fence"
            elif not line.strip():
                kind = "blank"
            elif IAL_RE.match(line):
                kind = "ial"
            elif line.lstrip().startswith("|"):
                kind = "table"
            elif HEAD_RE.match(line):
                kind = "heading"
            elif ITEM_RE.match(line):
                kind = "item"
            keep = line
            if in_comment:
                end = keep.find("-->")
                if end < 0:
                    keep = ""
                else:
                    keep, in_comment = " " * (end + 3) + keep[end + 3:], False
            start = keep.find("<!--")
            if start >= 0 and keep.find("-->", start) < 0:
                keep, in_comment = keep[:start], True
            keep = DROP_RE.sub(lambda m: " " * len(m.group(0)), keep)
            if kind == "ial":
                keep = ""
            first = None
            for col, ch in enumerate(keep):
                if ch.isalnum():
                    if first is None:
                        first = len(chars)
                    chars.append(ch.lower())
                    where.append((r, col))
            if first is None and kind == "text":
                kind = "comment"  # nothing left once the markup is gone
            self.kind.append(kind)
            self.first.append(first)
        self.norm, self.where = "".join(chars), where
        self.index = {}
        for i in range(len(self.norm) - K + 1):
            self.index.setdefault(self.norm[i:i + K], []).append(i)

    def locate(self, needle, cursor=0):
        """Normalized index where `needle` starts in the Markdown, or None."""
        if len(needle) < K + 2:
            return None
        step = 2 if len(needle) < 30 else 3
        offsets = list(range(0, len(needle) - K + 1, step))
        hits = {}
        for o in offsets:
            at = self.index.get(needle[o:o + K], ())
            if len(at) > 40:
                continue
            for p in at:
                hits.setdefault(p - o, []).append(o)
        if not hits:
            return None
        keys = sorted(hits)
        scored = []
        for k in keys:
            near = [o for k2 in keys if abs(k2 - k) <= 4 for o in hits[k2]]
            scored.append((len(near), k))
        need = max(2, len(offsets) // 4)
        good = [(n, k) for n, k in scored if n >= need]
        if not good:
            return None
        best = max(good)
        # A repeated line (`Reverse: As no. 3.`, six times in ONS_130) matches
        # everywhere equally well; the copy to take is the next one ahead.
        fwd = [(n, k) for n, k in good if k >= cursor - 50]
        if fwd and max(fwd)[0] >= 0.6 * best[0]:
            top = max(n for n, _ in fwd)
            n, k = min(((n, k) for n, k in fwd if n >= 0.8 * top), key=lambda c: c[1])
        else:
            n, k = best
        # the start the earliest matching chunk implies: a label the two
        # OCRs read differently sits at the front, and shifts nothing after it
        cluster = [(o, k2) for k2 in keys if abs(k2 - k) <= 4 for o in hits[k2]]
        return max(0, min(cluster)[1])

    def has_label(self, at, want):
        """Whether the Markdown has a label where a line placed at `at` starts.

        On a row of its own, any label will do -- the two OCRs read labels
        differently (`lA` / `1A:`, `ili.` / `iii.`), and an ordered item's
        marker is its label. Inside a row, `want` itself has to sit at the
        match or just before it: the match starts at the first chunk both
        OCRs agree on, which can be just past a label too short to make one.
        """
        r = self.where[at][0]
        if at - self.first[r] <= LEAD:
            row = self.rows[r]
            if self.kind[r] == "item" and re.match(r"\s*\d{1,9}\.\s", row):
                return True
            return bool(parse_label(re.sub(r"^\s*[-*+]\s+", "", row).lstrip(), ocr=True))
        alts = {want, re.sub(r"^[li]", "1", want), re.sub(r"[l1]", "i", want)}
        return any(self.norm[at - len(a) - k:at - k] == a for a in alts for k in (0, 1)) \
            or any(self.norm[at:at + len(a)] == a for a in alts)

    def at(self, b):
        """(row, col) of normalized index b."""
        return self.where[b]

    def boundary(self, a, alen, b):
        """What the Markdown has between a line placed at `a` (`alen`
        normalized characters long) and the next line, placed at `b`."""
        if a is None or b is None or not a < b <= a + alen * 1.5 + 80:
            return "UNPLACED", b
        r, _ = self.where[b]
        # a line the Markdown starts on a new row, minus a label it dropped,
        # is placed a character or two before that row
        for d in range(1, SNAP + 1):
            if b + d < len(self.where) and self.where[b + d][0] != r \
                    and b - self.first[r] > LEAD:
                b = b + d
                r = self.where[b][0]
                break
        if b - self.first[r] <= LEAD:
            if self.kind[r] == "item":
                return "ITEM", b
            if self.kind[r] in ("table", "heading", "fence"):
                return "BLOCK", b
            p = r - 1
            if p < 0 or self.kind[p] in ("blank", "ial", "comment", "heading",
                                         "table", "fence"):
                return "PARA", b
            if re.search(r"<br\s*/?>\s*$", self.rows[p]):
                return "BR", b
            return "FLAT", b
        pr, pc = self.where[b - 1]
        if pr == r and re.search(r"<br\s*/?>", self.rows[r][pc:self.where[b][1]]):
            return "BR", b
        return "FLAT", b


# --- screen ---------------------------------------------------------------


def judge(lines, members, labels, parsed, md, cursor):
    """(verdict, detail dict, new cursor) for one run."""
    locs, lens = {}, {}
    for i in members:
        needle = normalize(lines[i]["text"])[0]
        lens[i] = len(needle)
        locs[i] = md.locate(needle, cursor)
        if locs[i] is not None:
            cursor = locs[i]
    flat = notlist = unplaced = checked = glued = 0
    missing, starts = [], {}
    for a, b in zip(members, members[1:]):
        is_label = b in labels
        if not is_label and not room(lines[a], lines[b], strong=True):
            continue  # a wrap inside an item
        checked += 1
        cls, at = md.boundary(locs[a], lens[a], locs[b])
        starts[b] = at
        if DEBUG:
            where = md.where[at][0] + 1 if at is not None else "?"
            print(f"      {cls:8} md {where}: {lines[b]['text'][:60]!r}")
        if cls == "UNPLACED":
            unplaced += 1
        elif cls == "FLAT":
            flat += 1
            glued += is_label
        elif is_label and cls in ("PARA", "BR"):
            notlist += 1
    for i in labels:
        at = starts.get(i, locs[i])
        want = label_norm(parsed[i][1]) if parsed else ""
        if at is not None and want and not md.has_label(at, want):
            missing.append(parsed[i][1].strip())
    placed = [locs[i] for i in members if locs[i] is not None]
    if placed:
        cursor = min(placed)  # a run nested inside this one is judged next
    rows = (md.where[min(placed)][0] + 1, md.where[max(placed)][0] + 1) if placed else None
    if glued:
        verdict = "FLATTENED"
    elif flat:
        verdict = "RUN-ON"
    elif notlist:
        verdict = "NOT-LIST"
    elif not checked or unplaced * 2 > checked:
        verdict = "UNPLACED"
    else:
        verdict = "OK"
    return verdict, {"rows": rows, "missing": missing, "glued": glued, "inner": flat - glued}, cursor


def screen_file(stem, md_path, loose):
    pdf_path = PDF_DIR / f"{stem}.pdf"
    md = MdIndex(md_path.read_text(encoding="utf-8"))
    found, cursor = [], 0
    with fitz.open(pdf_path) as doc:
        for pno, page in enumerate(doc):
            for lines in page_lines(page):
                for run in label_runs(lines):
                    members, labels, parsed = run["members"], run["labels"], run["parsed"]
                    verdict, detail, cursor = judge(lines, members, labels, parsed, md, cursor)
                    sel = [lines[m] for m in members]
                    found.append({
                        "verdict": verdict, "page": pno,
                        "rect": (min(l["x0"] for l in sel), min(l["y0"] for l in sel),
                                 max(l["x1"] for l in sel), max(l["y1"] for l in sel)),
                        "labels": [parsed[i][1].strip() for i in labels],
                        "text": sel[0]["text"], **detail})
    return found


REPORTED = ("FLATTENED", "NOT-LIST")
LOOSE = ("RUN-ON",)


def describe(f):
    labs = f["labels"]
    span = f"{labs[0]}..{labs[-1]} ({len(labs)})" if labs else "no labels"
    rows = f"md {f['rows'][0]}-{f['rows'][1]}" if f["rows"] else "md ?"
    x0, y0, x1, y1 = f["rect"]
    out = (f"  {f['verdict']:9} p{f['page']:<3} {rows:12} rect={x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}"
           f"  {span}  {f['text'][:50]!r}")
    if f["verdict"] in ("FLATTENED", "RUN-ON"):
        out += (f"\n{'':14}{f['glued']} item(s) glued to the one before, "
                f"{f['inner']} short line(s) run on inside items")
    if f["missing"] and f["verdict"] in REPORTED + LOOSE:
        out += f"\n{'':14}label(s) not in the Markdown: {' '.join(f['missing'])}"
    return out


def cmd_screen(args):
    stems = stems_of(args)
    status = 0
    for stem in stems:
        md_path = pathlib.Path(args.md) if args.md else MD_DIR / f"{stem}.md"
        if not (PDF_DIR / f"{stem}.pdf").exists() or not md_path.exists():
            print(f"{stem}: no PDF or no Markdown")
            continue
        found = screen_file(stem, md_path, args.loose)
        shown = REPORTED + (LOOSE if args.loose else ())
        counts = {}
        for f in found:
            v = f["verdict"] if f["verdict"] in shown + ("OK", "UNPLACED") else "OK"
            counts[v] = counts.get(v, 0) + 1
        todo = sum(counts.get(v, 0) for v in shown)
        tail = "  ".join(f"{v} {counts[v]}" for v in shown + ("OK", "UNPLACED") if v in counts)
        print(f"{stem}: {len(found)} run(s) | {tail or 'none'} -- "
              + (f"{todo} to look at" if todo else "nothing outstanding"))
        for f in found:
            if f["verdict"] in shown or args.verbose:
                print(describe(f))
        status |= bool(todo)
    return status


def cmd_rows(args):
    out = []
    for stem in args.stems:
        md_path = pathlib.Path(args.md) if args.md else MD_DIR / f"{stem}.md"
        if not (PDF_DIR / f"{stem}.pdf").exists() or not md_path.exists():
            print(f"# {stem}: no PDF or no Markdown", file=sys.stderr)
            continue
        for f in screen_file(stem, md_path, args.loose):
            if f["verdict"] not in REPORTED + (LOOSE if args.loose else ()):
                continue
            x0, y0, x1, y1 = f["rect"]
            where = f"line {f['rows'][0]}" if f["rows"] else f"p{f['page']}"
            labs = f"{f['labels'][0]}..{f['labels'][-1]}" if f["labels"] else ""
            out.append(f"{stem}\t{where} {f['verdict']} {labs}".rstrip()
                       + f"\t{f['page']}\t@{x0 - 4:.0f},{y0 - 3:.0f},{x1 + 4:.0f},{y1 + 3:.0f}")
    print("\n".join(out))
    return 1 if out else 0


# --- lint -----------------------------------------------------------------

LABELLED_IAL_RE = re.compile(r"^\s*\{:[^}]*\.labelled\b[^}]*\}\s*$")
BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
def lint_file(path):
    rows = path.read_text(encoding="utf-8").split("\n")
    kinds, in_fence = [], False
    for line in rows:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            kinds.append("fence")
        elif in_fence:
            kinds.append("fence")
        elif not line.strip():
            kinds.append("blank")
        elif LABELLED_IAL_RE.match(line):
            kinds.append("labelled-ial")
        elif IAL_RE.match(line):
            kinds.append("ial")
        elif line.lstrip().startswith(("|", "<!--")) or HEAD_RE.match(line):
            kinds.append("skip")
        elif BULLET_RE.match(line):
            kinds.append("bullet")
        elif ITEM_RE.match(line):
            kinds.append("item")
        else:
            kinds.append("text")
    found = []

    def chains(entries, link):
        """Group (row, cands, label) entries into runs that count up."""
        runs = []
        for e in entries:
            for run in reversed(runs):
                kind = follows(run["last"][1], e[1], run["kind"])
                if kind and link(run["last"], e):
                    run.update(kind=kind, last=e)
                    run["rows"].append(e)
                    break
            else:
                runs.append({"kind": None, "last": e, "rows": [e]})
        return [r["rows"] for r in runs if len(r["rows"]) >= 2]

    # LINED: label-led rows that are not list items
    plain = []
    for r, line in enumerate(rows):
        if kinds[r] != "text":
            continue
        lab = parse_label(line.lstrip())
        if lab and not (lab[1].strip()[:-1].isdigit() and lab[1].strip().endswith(".")):
            plain.append((r, lab[0], lab[1].strip(), len(line) - len(line.lstrip())))

    def near(a, b):
        between = [k for k in range(a[0] + 1, b[0]) if kinds[k] not in ("blank",)]
        return b[0] - a[0] <= 12 and len(between) <= 4 and abs(a[3] - b[3]) <= 1 \
            and all(kinds[k] in ("text", "ial") for k in between)
    for run in chains(plain, near):
        found.append((run[0][0], "LINED", f"{run[0][2]}..{run[-1][2]} ({len(run)})",
                      rows[run[0][0]]))

    # UNMARKED and IAL
    for r, line in enumerate(rows):
        if kinds[r] == "labelled-ial":
            nxt = r + 1
            if r > 0 and kinds[r - 1] != "blank":
                found.append((r, "IAL", "no blank line above, so it attaches to the paragraph", line))
            if nxt >= len(rows) or kinds[nxt] != "bullet":
                found.append((r, "IAL", "no bullet item under it", line))
                continue
            indent = len(BULLET_RE.match(rows[nxt]).group(1))
            k = nxt
            while k < len(rows) and kinds[k] != "blank" or (
                    k + 1 < len(rows) and kinds[k] == "blank" and kinds[k + 1] == "bullet"
                    and len(BULLET_RE.match(rows[k + 1]).group(1)) == indent):
                if kinds[k] == "bullet" and len(BULLET_RE.match(rows[k]).group(1)) == indent:
                    if not parse_label(BULLET_RE.match(rows[k]).group(2)):
                        found.append((k, "IAL", "item has no label, and its bullet is hidden",
                                      rows[k]))
                k += 1
    bullets = []
    for r, line in enumerate(rows):
        if kinds[r] != "bullet":
            continue
        m = BULLET_RE.match(line)
        lab = parse_label(m.group(2))
        if lab and re.fullmatch(r"[A-Z]\.", lab[1].strip()) \
                and re.match(r"[A-Z]\.\s+[A-Z][a-z]", m.group(2)):
            continue  # an initial: `- R. Gobl, The Roman ...`
        if lab:
            bullets.append((r, lab[0], lab[1].strip(), len(m.group(1))))

    def adjacent(a, b):
        return a[3] == b[3] and b[0] - a[0] <= 8 and all(
            kinds[k] in ("bullet", "blank", "text") for k in range(a[0] + 1, b[0]))
    for run in chains(bullets, adjacent):
        top = run[0][0] - 1
        while top >= 0 and kinds[top] in ("bullet", "text") and \
                BULLET_RE.match(rows[top] if kinds[top] == "bullet" else "") is not None:
            top -= 1
        if top < 0 or kinds[top] != "labelled-ial":
            found.append((run[0][0], "UNMARKED", f"{run[0][2]}..{run[-1][2]} ({len(run)})",
                          rows[run[0][0]]))

    found.sort()
    return found


def cmd_lint(args):
    status, total = 0, 0
    for target in args.files:
        path = pathlib.Path(target)
        if not path.suffix:
            path = MD_DIR / f"{target}.md"
        found = lint_file(path)
        total += len(found)
        for r, verdict, what, line in found:
            print(f"{path}:{r + 1}: {verdict:8} {what}  {line.strip()[:70]!r}")
        status |= bool(found)
    print(f"total: {total}")
    return status


# --- main -----------------------------------------------------------------


def stems_of(args):
    if args.all:
        return sorted(f.stem for f in MD_DIR.glob("*.md") if (PDF_DIR / f"{f.stem}.pdf").exists())
    if not args.stems:
        sys.exit("give one or more stems, or --all")
    if args.md and len(args.stems) != 1:
        sys.exit("--md takes exactly one stem")
    return args.stems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint", help="Markdown only: labelled lines that are not list items")
    p.add_argument("files", nargs="+", help="jons/X.md, or a stem")
    p.set_defaults(func=cmd_lint)
    for name, func, help_text in (("screen", cmd_screen, "scan against Markdown"),
                                  ("rows", cmd_rows, "crop_sheets.py rows for the findings")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("stems", nargs="*", help="e.g. ONS_130")
        p.add_argument("--md", help="read this Markdown file instead (one stem only)")
        p.add_argument("--loose", action="store_true",
                       help="also report RUN-ON: short lines run together inside items")
        if name == "screen":
            p.add_argument("--all", action="store_true", help="every jons/*.md that has a PDF")
            p.add_argument("-v", "--verbose", action="store_true", help="also list OK and UNPLACED runs")
            p.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
        p.set_defaults(func=func)
    args = ap.parse_args()
    global DEBUG
    DEBUG = getattr(args, "debug", False)
    if not PDF_DIR.is_dir() and args.cmd != "lint":
        print(f"warning: PDF archive {PDF_DIR} does not exist -- set ONS_ARCHIVE_DIR "
              "to the ons-website static/archive checkout", file=sys.stderr)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
