#!/usr/bin/env python3
"""Find the marks an OCR pass dropped, from the Markdown alone.

`punct_candidates.py` repairs this class, but it costs a 300-dpi render and a
tesseract pass over every page, so nothing runs it speculatively -- and
nothing told you which files need it. The skill's own trigger is "when a
sample paragraph shows this", which means the defect is found by whoever
happens to read the file. ONS_158 sat in `docs/screens.tsv` with five clean
screens and 200 dropped periods.

The tell needs no PDF: a dropped period leaves a lowercase word butted
straight against a capitalised sentence opener.

    ...sequence of Junnar runs Satavahanas...     (c 155-169) The last great
    ...is discussed in detail Few will have...    rupees The usual couplet

Measured over the 264 files in `jons/`, that shape fires 0.01 times per 1000
words on files whose punctuation survived and 4-6 times per 1000 on files
whose punctuation did not: a 400-fold gap with nothing in it, because the
damage is wholesale when it happens at all. 42 files are above the line, and
they are the scanned issues from ONS_119 and ONS_141-202; from ONS_186 the
PDFs are born-digital (see `classify_source.py`) and carry the publisher's
own punctuation. Another 43 files sit below it with nine candidates or
fewer -- ordinary spots, and real ones: a crop settles each.

The same pass drops the possessive apostrophe with the periods, and that one
no other screen can see at all: `punct_candidates.py` aligns on `.,;:!?`, so
an apostrophe is outside the marks it compares, and cspell sees two real
words either side of the space.

    ...Curator of South Asian Coins in the Museum s Department of Coins...
    ...the thirty sultanis which Pijnacker s dragoman had to pay...

486 of those across 61 files, and 38 of the 61 are files this screen already
calls WHOLESALE -- which is what says it is the same damage and not a habit
of the typists. They report as POSSESSIVE and are listed with the rest, but
the rate and the verdict count the SENTENCE shape alone: both thresholds were
measured on it, and the gap that justifies the cut is its gap.

    detect_dropped_punct.py scan ONS_158
    detect_dropped_punct.py scan jons/*.md
    detect_dropped_punct.py rows ONS_158          # crop_sheets.py rows

`scan` prints a verdict per file and names the tool that settles it:

    ONS_158: WHOLESALE  200 candidate(s), 4.71 per 1000 words
      -> run punct_candidates.py; crop sheets do not scale to this many
    ONS_226: ISOLATED   9 candidate(s), 0.52 per 1000 words
      SENTENCE   md line 223: 'presented in Figure 3. vii There are slight'
      POSSESSIVE md line 445: 'broken down as follows: Cask s'

**This screen settles nothing.** It reads capitalisation and spacing, and
fix-ocr forbids supplying a mark from context (see Hard constraints) -- only
a render is evidence. So it writes no edits and emits no `apply_edits.py` batch: it says
which files to point the rendering tools at, and in what order. A WHOLESALE
file goes to `punct_candidates.py`; an ISOLATED one is a handful of crops
through `shared/crop_sheets.py`.

Exit 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MD_DIR = REPO_ROOT / "jons"

# Capitalised words that open a sentence far more often than they open
# anything else. Kept deliberately short: every addition widens the net on
# 200 clean files as much as on the 41 damaged ones.
OPENERS = (
    "The This These Those It They There He She We However Hence Thus "
    "Therefore Both Few Most Some Although Nevertheless Moreover Furthermore "
    "Unfortunately Perhaps Indeed Also"
).split()
# ... of which these also open a title the corpus cites in running prose:
# `in his book The coins of the Dutch`, `visiting in quick succession The
# Hague`, `Some New (?) Standing Caliph`. A sentence opener is followed by a
# lowercase word (`The main part`, `This book presents`) and a cited title
# almost never is, so for these the next word has to be lowercase. That one
# condition removed 20 of the 58 false hits measured on the clean files.
TITLEABLE = set("The This These Those Both Few Most Some".split())
OPEN_RE = re.compile(r"\b([a-z]{3,}) +(" + "|".join(OPENERS) + r")\b( +(\S+))?")
# Words that legitimately precede a capital with no period between them --
# function words and the verbs this corpus introduces a title with. `of`,
# `in`, `at`, `by`, `to`, `as` and the rest of the two-letter prepositions
# are already excluded by the `{3,}` above, which is most of the work.
PRECEDES_CAPITAL = set("""
see and the for from with into near over upon via per not nor but than that
which when where while after before since until about among across against
like such both also was were are been being has have had does did
called named titled entitled published edited vol ed eds pub cit ibid viz etc
read reads says said wrote write writes note notes cf
book booklet website pamphlet journal volume magazine paper article catalogue
contact courtesy renamed publishing using succession alternatively
""".split())

# Above this many candidates per 1000 words a file has lost its punctuation
# wholesale rather than in spots. The measured gap runs from 1.09 (ONS_164,
# the least damaged of the damaged) down to 0.72, and the files below it
# carry single figures of candidates each.
WHOLESALE_RATE = 1.0
# ... or this many candidates outright, whatever the rate: ONS_197 is a
# 48,000-word issue with 35 of them and no text layer at all, so its rate
# (0.72) understates a file that is damaged throughout. Nothing else below
# the rate threshold has more than 9.
WHOLESALE_COUNT = 25
# A quoted translation of a coin legend is printed without punctuation on
# purpose, and capitalises the divine pronoun: `"God is alone God is eternal
# He begets not"`. Six files' worth of false hits sit inside such a span.
QUOTED_RE = re.compile(r"[\"“”](?:[^\"“”\n]|\n(?!\s*\n)){0,600}?"
                       r"[\"“”]")

# The same files lose the possessive apostrophe with the periods: `the Museum
# s Department`, `Pijnacker s dragoman`, `not a ship s carpenter`. No other
# screen can see it -- `punct_candidates.py` only tracks `.,;:!?`, so the
# apostrophe is outside the marks it aligns on at all, and cspell sees two
# real words. 505 across 62 files, 38 of which this screen already calls
# WHOLESALE, which is what says it is the same damage rather than a habit of
# the typists.
POSSESSIVE_RE = re.compile(r"\b[A-Za-z]{3,}( s)\b")
# `Jean Elsen s.a.`, `Jean Elsen & ses Fils s.A.` -- the Belgian dealer's
# company form, 19 of the 505 and the only false positive worth excluding by
# rule. One more class stays in and has to be settled on the page like any
# other candidate: a transliterated Russian title, where `s` is the
# preposition (`Mednye monety s izobrazheniem luchnika`). An `s` inside an
# italic span is *not* a tell -- those 50 are overwhelmingly real possessives
# in cited article titles (`Harun al-Rashid s wife strikes coins`).
COMPANY_RE = re.compile(r"\bs\.\s*[ap]\.", re.I)


def resolve(arg):
    p = pathlib.Path(arg)
    return p if p.suffix == ".md" else MD_DIR / f"{arg}.md"


def readable(path):
    """The file with HTML comments and fenced code blanked out, offsets kept.

    The OCR skills quote bad readings inside `<!-- ... -->` on purpose, so a
    screen that reads them reports the evidence as the defect.
    """
    text = path.read_text(encoding="utf-8")
    for pattern, flags in ((r"<!--.*?-->", re.S), (r"(?ms)^```.*?^```", 0)):
        text = re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                      text, flags=flags)
    return text


def findings(text):
    """[(offset, end, kind)] for each dropped-mark candidate, in file order.

    `offset` is where the shape starts and `end` where it finishes, so the
    anchor covers the whole of it however many spaces the OCR left inside.
    `kind` is SENTENCE (a dropped full stop) or POSSESSIVE (a dropped
    apostrophe).
    """
    quoted = [m.span() for m in QUOTED_RE.finditer(text)]
    out = []
    for m in OPEN_RE.finditer(text):
        before, opener, after = m.group(1), m.group(2), m.group(4) or ""
        if before in PRECEDES_CAPITAL:
            continue
        if opener in TITLEABLE and after[:1].isupper():
            continue
        if any(a <= m.start() < b for a, b in quoted):
            continue
        out.append((m.start(), m.end(2), "SENTENCE"))
    for m in POSSESSIVE_RE.finditer(text):
        if COMPANY_RE.match(text, m.start(1) + 1):
            continue
        out.append((m.start(), m.end(1), "POSSESSIVE"))
    return sorted(out)


def verdict(text):
    """(verdict, findings, rate per 1000 words).

    The rate -- and so the verdict -- counts SENTENCE findings only. Both
    thresholds were measured on that shape alone, and the POSSESSIVE shape is
    four times rarer and spread differently, so folding it in would move the
    rate without the empty gap that justifies the cut. It still reports, and
    still needs the same page render to settle it.
    """
    found = findings(text)
    sentences = [f for f in found if f[2] == "SENTENCE"]
    words = len(text.split()) or 1
    rate = len(sentences) / words * 1000
    if not found:
        return "CLEAN", found, rate
    wholesale = rate >= WHOLESALE_RATE or len(sentences) >= WHOLESALE_COUNT
    return ("WHOLESALE" if wholesale else "ISOLATED"), found, rate


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def anchor_at(text, end):
    """The words leading up to the candidate, for `crop_sheets.py` to place."""
    return " ".join(text[max(0, end - 170):end].split())


def cmd_scan(path, quiet_clean=False):
    text = readable(path)
    tag, found, rate = verdict(text)
    if tag == "CLEAN":
        if not quiet_clean:
            print(f"{path.stem}: no dropped-period candidates")
        return 0
    print(f"{path.stem}: {tag}  {len(found)} candidate(s), "
          f"{rate:.2f} per 1000 words")
    if tag == "WHOLESALE":
        print("  -> run punct_candidates.py; crop sheets do not scale to "
              "this many")
        return 1
    print("  -> settle each against a page crop (shared/crop_sheets.py); "
          "never from the capitalisation alone")
    for off, end, kind in found:
        print(f"  {kind:10} md line {line_of(text, off)}: "
              f"{anchor_at(text, end)[-58:]!r}")
    return 1


def cmd_rows(path):
    """`file<TAB>label<TAB>anchor`, the form `shared/crop_sheets.py` takes.

    Every candidate is a row, including a WHOLESALE file's, so that
    `survey.py show --screen punctuation` sorts the corpus by how much
    punctuation each file is missing. The label says WHOLESALE on those, and
    the comment line says what to do instead of building the sheets.
    """
    text = readable(path)
    tag, found, _rate = verdict(text)
    if tag == "WHOLESALE":
        print(f"# {path.stem}: lost its punctuation wholesale -- "
              f"run punct_candidates.py, not crop sheets")
    for off, end, kind in found:
        label = f"{tag} {kind} line {line_of(text, off)}"
        print(f"{path.stem}\t{label}\t{anchor_at(text, end)}")
    return 1 if found else 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    if len(args) < 2 or args[0] not in ("scan", "rows"):
        print(__doc__)
        return 2
    rc = 0
    for arg in args[1:]:
        path = resolve(arg)
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            rc = max(rc, 2)
            continue
        if args[0] == "rows":
            rc = max(rc, cmd_rows(path))
        else:
            rc = max(rc, cmd_scan(path, quiet_clean=len(args) > 2))
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:          # piped into `head`, which is expected
        sys.exit(1)
