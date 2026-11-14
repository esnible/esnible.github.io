#!/usr/bin/env python3
"""Record each source-PDF page boundary permanently in the Markdown.

Nothing in this repo can say which page a Markdown line came from without
paying for it. `locate_on_page.py` does it properly by OCRing every page with
tesseract, about four seconds a page. `crop_sheets.py` and `quote_crops.py`
place a finding by matching anchor words against the PDF's text layer, which
-- as `crop_sheets.py` says of itself -- is "garbled in exactly the places a
screen reports", so the placement fails precisely where it is needed. And
every screen that wants to report a page number has to redo one of the two.

A boundary written into the file is computed once and then simply read:

    ...the last great monarch of the line <!-- page-start page=13 -->

**One marker per boundary, start-only.** Page N runs from its marker to the
next one, or to the end of the file. End markers would double the insertions
and leave two things to keep consistent.

## Why the marker goes on the end of an existing line

Tested against this repo's kramdown 2.4.0:

* In prose both placements are invisible. A comment on its own line *inside* a
  paragraph does not split the paragraph.
* **A comment on its own line inside a pipe table destroys the table.**
  kramdown stops parsing it and emits the whole thing as one paragraph of
  literal `|` characters. Much of this corpus is tables somebody rebuilt by
  hand, so that rules out the own-line form as a blanket rule.
* A comment appended to a table *row* adds a phantom column.

So the marker is appended to a line, and `safe_line()` keeps it off the lines
where that would show: table rows, fenced code, headings, and any line already
carrying a comment that could swallow it.

Appending also leaves the **line count** alone, which matters more than it
sounds. `apply_edits.py` refuses any change to a file's line count, and
`fix-ocr`'s verification gate is `added == deleted` against the pre-pass
snapshot. A scheme that inserted lines would be at odds with every other skill
in the repo for as long as it existed.

## What makes this safe to run over 264 files

`apply` proves itself the way `detect_presentation_forms.py apply` does: the
file with every `page-start` marker stripped back out must be **byte-identical**
to the file before the pass, and the line count must be unchanged. The pass
cannot quietly reword anything, because the only edit it is capable of making
is one it can undo exactly.

## Where it refuses

The alignment is between the Markdown's words and the PDF text layer's words,
in order, so it fails wherever the Markdown is not that text in that order:

* **NO-TEXT-LAYER** -- ONS_177, ONS_197, OP_014 carry a page image nobody
  OCR'd into the PDF. There are no words to align against at all.
* **OUT-OF-ORDER** -- a file whose pages are bound out of reading order, or
  that `reconstruct-scrambled-md` has yet to repair, cannot carry a monotonic
  marker scheme. It is reported, not marked. (A census of the corpus's
  existing `page=N` markers found 11 files whose anchors already run
  backwards; these are the same files.)
* a boundary the alignment cannot place within `--slack` words is skipped
  individually, and counted, rather than guessed at.

Born-digital issues (ONS_186 onward) are the easy case rather than a refusal:
the text layer *is* the source, so their boundaries are exact.

    page_markers.py scan ONS_158
    page_markers.py scan --all
    page_markers.py apply ONS_158
    page_markers.py apply ONS_158 --write

Importers get `page_of(stem)`, a dict from Markdown line number to page, read
from the markers if they are there and computed if they are not.
"""
import argparse
import collections
import difflib
import os
import re
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:  # pymupdf < 1.24 installed itself as `fitz`
    try:
        import fitz as pymupdf
    except ImportError as exc:
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")

PDF_DIR = Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()
REPO_ROOT = Path(__file__).resolve().parents[3]
MD_DIR = REPO_ROOT / "jons"

MARKER_RE = re.compile(r" ?<!-- page-start page=(\d+)(?: [a-z]+=[-\d]+)* -->")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
WORD_RE = re.compile(r"[0-9A-Za-zÀ-ɏ]+")
# A line the marker must not be appended to, and why.
UNSAFE = (
    (re.compile(r"^\s*\|"), "table row"),
    (re.compile(r"^\s*#"), "heading"),
    (re.compile(r"^\s*(```|~~~)"), "code fence"),
    (re.compile(r"^\s*$"), "blank"),
    (re.compile(r"-->\s*$"), "ends in a comment"),
    (re.compile(r"<!--(?!.*-->)"), "unclosed comment"),
)


# One page boundary. `md`/`pdf` are the two readings of the same spot, printed
# side by side so a placement that landed on the wrong words is obvious before
# anybody opens a render -- the habit `locate_on_page.py` established.
Boundary = collections.namedtuple(
    "Boundary", "page line word note pdf md")


def norm(word):
    return word.lower()


def md_words(text):
    """[(normalised word, line number)] for the Markdown, comments removed.

    A marker or an `<!-- OCR: ... -->` note is this toolchain talking, not the
    page, so its words must not take part in the alignment.
    """
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        bare = COMMENT_RE.sub(" ", line)
        out += [(norm(m.group()), n) for m in WORD_RE.finditer(bare)]
    return out


def pdf_words(pdf):
    """([normalised word], [first word index of each page], page count)."""
    words, starts = [], []
    with pymupdf.open(pdf) as doc:
        for page in doc:
            starts.append(len(words))
            words += [norm(m.group())
                      for m in WORD_RE.finditer(page.get_text())]
        return words, starts, doc.page_count


def fenced(text):
    """Line numbers that sit inside a fenced code block."""
    inside, out = False, set()
    for n, line in enumerate(text.split("\n"), 1):
        if re.match(r"^\s*(```|~~~)", line):
            inside = not inside
            out.add(n)
        elif inside:
            out.add(n)
    return out


def safe_line(lines, fences, want):
    """The nearest line to `want` a marker may be appended to.

    Returns (line number, offset from `want`, reason it moved) or None.
    """
    for delta in range(0, 6):
        for n in ({want - delta, want + delta} if delta else {want}):
            if not 1 <= n <= len(lines) or n in fences:
                continue
            line = lines[n - 1]
            why = next((w for rx, w in UNSAFE if rx.search(line)), None)
            if why is None:
                return n, n - want, None
    return None


def align(stem, slack):
    """Where each page begins in the Markdown.

    Returns (findings, verdict, page count). A finding is
    (page, line, word offset in the line, note) with line None when the
    boundary could not be placed.
    """
    md = MD_DIR / f"{stem}.md"
    pdf = PDF_DIR / f"{stem}.pdf"
    if not md.exists():
        return [], f"NO-MARKDOWN {md}", 0
    if not pdf.exists():
        return [], f"NO-PDF {pdf}", 0

    text = md.read_text(encoding="utf-8")
    mw = md_words(text)
    pw, starts, npages = pdf_words(pdf)
    if len(pw) < 50:
        return [], "NO-TEXT-LAYER", npages

    # An order-preserving correspondence between the two word sequences. The
    # text layer is a second, independent OCR of the same page, so the two
    # disagree word by word -- but they disagree locally, and the matching
    # blocks between the disagreements are enough to carry a page boundary
    # across. autojunk drops the words common enough to match anywhere.
    sm = difflib.SequenceMatcher(None, [w for w, _ in mw], pw)
    blocks = sm.get_matching_blocks()

    snip = lambda seq, i: " ".join(seq[i:i + 7])
    findings = []
    for page in range(1, npages):             # page 0 starts at the top
        want = starts[page]
        pdf_snip = snip(pw, want)
        if want >= len(pw):                   # a page with no text of its own
            findings.append(Boundary(page, None, 0, "page carries no text",
                                     pdf_snip, ""))
            continue
        # Anchor on the first word of *this page* that actually aligns, and
        # never on a word from the next one. Both halves are paid for:
        #
        # Taking the start of the next matching block wherever the page's own
        # words did not align quietly hands this page the next page's first
        # line -- ONS_158's plate page 17, whose caption garble matches
        # nothing, came out pointing at page 18's opening sentence.
        #
        # Demanding the page's very first word align is the opposite failure.
        # `get_text()` returns the running header and the folio, which the
        # Markdown drops, so the page's first word is the one least likely to
        # be in it: born-digital ONS_190, whose text layer *is* the source,
        # placed 1 boundary of 48 under that rule.
        end = starts[page + 1] if page + 1 < len(starts) else len(pw)
        hit = into = None
        for j in range(want, min(want + slack, end)):
            b = next((b for b in blocks
                      if b.size and b.b <= j < b.b + b.size), None)
            if b:
                hit, into = b.a + (j - b.b), j - want
                break
        if hit is None or hit >= len(mw):
            room = min(want + slack, end) - want
            findings.append(Boundary(
                page, None, 0,
                f"no aligned word in this page's first {room}", pdf_snip, ""))
            continue
        line = mw[hit][1]
        first = next(i for i, (_, l) in enumerate(mw) if l == line)
        note = f"anchored {into} words into the page" if into else None
        findings.append(Boundary(page, line, hit - first, note, pdf_snip,
                                 snip([w for w, _ in mw], hit)))

    placed = [f for f in findings if f[1]]
    backwards = sum(1 for a, b in zip(placed, placed[1:]) if b[1] < a[1])
    verdict = "OUT-OF-ORDER" if backwards else "SCAN"
    return findings, verdict, npages


ANCHOR_RE = re.compile(r"<!--\s*(?!page-start)[a-z-]+[^>]{0,80}?page=(\d+)")


def anchors(text):
    """[(line, page)] for the page= markers other passes already left.

    The corpus carries about 2,750 of these -- `figure page=6`,
    `script-ok page=12`, `table-ok page=3` -- each placed in position by
    somebody who had the render open. They cover only 27% of pages on
    average, so they are no substitute for the alignment; what they are is a
    free test of it, in the 144 files that have any.
    """
    return [(n, int(m.group(1)))
            for n, line in enumerate(text.split("\n"), 1)
            for m in [ANCHOR_RE.search(line)] if m]


def cross_check(text, findings):
    """Compare the computed boundaries against the existing anchors.

    Returns (agree, disagree, inconclusive), where a disagreement is an
    anchor naming page P that falls outside the lines the alignment gives
    page P. A page whose own boundary was skipped is still checked, against
    the nearest known boundaries either side -- weaker, but it still catches
    a boundary that landed a page out.
    """
    placed = sorted((b.page, b.line) for b in findings if b.line)
    placed.insert(0, (0, 1))
    agree, unknown, bad = 0, 0, []
    for line, page in anchors(text):
        lo = max((l for p, l in placed if p <= page), default=None)
        hi = min((l for p, l in placed if p > page), default=None)
        if lo is None or hi is None:
            unknown += 1
        elif lo <= line < hi:
            agree += 1
        else:
            said = next((p for p, l in reversed(placed) if l <= line), None)
            bad.append((line, page, lo, hi, said))
    return agree, bad, unknown


def marker(page, word_off, line_off):
    extra = ""
    if word_off:
        extra += f" word={word_off}"
    if line_off:
        extra += f" line={line_off:+d}"
    return f" <!-- page-start page={page}{extra} -->"


def place(text, findings, slack_lines=True):
    """Return (new text, [(page, line)] written, [(page, why)] skipped)."""
    lines = text.split("\n")
    fences = fenced(text)
    written, skipped, edits = [], [], {}
    for b in findings:
        if b.line is None:
            skipped.append((b.page, b.note))
            continue
        spot = safe_line(lines, fences, b.line)
        if spot is None:
            skipped.append((b.page, "no safe line within 5"))
            continue
        n, line_off, _ = spot
        if n in edits:
            skipped.append((b.page, f"line {n} already carries page {edits[n]}"))
            continue
        edits[n] = b.page
        lines[n - 1] += marker(b.page, b.word, line_off)
        written.append((b.page, n))
    return "\n".join(lines), written, skipped


def strip(text):
    """`text` with every page-start marker removed."""
    return MARKER_RE.sub("", text)


def page_of(stem, slack=40):
    """Markdown line number -> page, from the markers if present."""
    text = (MD_DIR / f"{stem}.md").read_text(encoding="utf-8")
    at = {}
    for n, line in enumerate(text.split("\n"), 1):
        m = MARKER_RE.search(line)
        if m:
            at[n] = int(m.group(1))
    if not at:
        findings, verdict, _ = align(stem, slack)
        if verdict not in ("SCAN", "OUT-OF-ORDER"):
            raise ValueError(f"{stem}: {verdict}")
        at = {b.line: b.page for b in findings if b.line}
    out, page = {}, 0
    for n in range(1, len(text.split("\n")) + 1):
        page = at.get(n, page)
        out[n] = page
    return out


def report(stem, findings, verdict, npages, verbose):
    placed = [b for b in findings if b.line]
    skipped = [b for b in findings if not b.line]
    if verdict not in ("SCAN", "OUT-OF-ORDER"):
        print(f"{stem}: {verdict}")
        return 0
    text = (MD_DIR / f"{stem}.md").read_text(encoding="utf-8")
    agree, bad, unknown = cross_check(text, findings)
    checked = (f"  anchors {agree} agree"
               + (f", {len(bad)} DISAGREE" if bad else "")
               + (f", {unknown} inconclusive" if unknown else "")
               if agree + len(bad) + unknown else "")
    print(f"{stem}: {verdict}  {npages} pages  "
          f"{len(placed) + 1} placed  {len(skipped)} skipped{checked}")
    for line, page, lo, hi, said in bad:
        print(f"    line {line} says page {page}; the alignment gives that "
              f"line to page {said} (page {page} is lines {lo}-{hi - 1})")
    if not verbose:
        return len(skipped) + len(bad)
    for b in findings:
        where = (f"line {b.line}" + (f" word {b.word}" if b.word else "")
                 if b.line else f"SKIP  {b.note}")
        print(f"    page {b.page:>3} -> {where}")
        # Both readings of the boundary. They are two OCRs of the same words,
        # so they differ; what says the placement is wrong is them being
        # different *words*, not differently spelled ones.
        print(f"        pdf : {b.pdf}")
        if b.md:
            print(f"        md  : {b.md}")
    return len(skipped) + len(bad)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("scan", "apply"))
    ap.add_argument("stems", nargs="*", metavar="ONS_158")
    ap.add_argument("--all", action="store_true", help="every .md in jons/")
    ap.add_argument("--write", action="store_true",
                    help="with apply: write the file (default is a dry run)")
    ap.add_argument("--replace", action="store_true",
                    help="with apply: strip the existing markers and "
                         "recompute, instead of refusing an already-marked file")
    ap.add_argument("--slack", type=int, default=40, metavar="N",
                    help="how many words of alignment gap a boundary may sit "
                         "behind before it is skipped (default 40)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="one line per boundary")
    args = ap.parse_args()

    stems = list(args.stems)
    if args.all:
        stems += sorted(p.stem for p in MD_DIR.glob("*.md"))
    if not stems:
        sys.exit("no files: name a stem or pass --all")

    outstanding = 0
    for stem in stems:
        findings, verdict, npages = align(stem, args.slack)
        outstanding += report(stem, findings, verdict, npages,
                              args.verbose or args.cmd == "apply")
        if args.cmd != "apply":
            continue
        if verdict != "SCAN":
            print(f"  refusing to mark: {verdict}")
            continue

        md = MD_DIR / f"{stem}.md"
        before = md.read_text(encoding="utf-8")
        # Appending to a line that already carries a marker is not something
        # `safe_line` can rescue: it would move to the neighbouring line and
        # leave the file with two markers for one boundary. A second run
        # starts from the stripped text instead.
        if MARKER_RE.search(before):
            if not args.replace:
                print("  already marked: pass --replace to recompute")
                continue
            before = strip(before)
        after, written, skipped = place(before, findings)

        # The only edit this pass can make is one it can take back exactly.
        assert strip(after) == before, f"{stem}: text outside the markers moved"
        assert after.count("\n") == before.count("\n"), \
            f"{stem}: line count changed"
        assert place(strip(after), findings)[0] == after, \
            f"{stem}: the pass is not idempotent"

        print(f"  {len(written)} marker(s), {len(skipped)} skipped"
              f"{'' if args.write else '  (dry run)'}")
        for page, why in skipped:
            print(f"    page {page:>3} not marked: {why}")
        if args.write:
            md.write_text(after, encoding="utf-8")
            print(f"  wrote {md}")
    return 1 if outstanding else 0


if __name__ == "__main__":
    sys.exit(main())
