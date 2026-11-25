#!/usr/bin/env python3
"""Find block boundaries `pdfmd` lost, by asking a second encoding of the same PDF.

The defect is the mirror of the one `detect_severed_paragraphs.py` screens for.
There, one paragraph of the scan arrives as two Markdown blocks. Here, two
blocks of the scan arrive as one: `pdfmd` dropped the blank line between them,
so whatever stood on its own on the page -- a section head, a contributor's
signature, the next entry of a bibliography, the next item of a list -- is
swallowed by the body paragraph beside it and renders mid-sentence.

    ... and he will be remembered for a long time. Joergen Clauson-Kaas
    Annual General Meeting The AGM will take place on Saturday 25 May 2002 ...

Four blocks of ONS_171 page 3 in two Markdown ones. Nothing in that text is
misspelled, no table is involved, no heading marker is in the wrong place, and
no screen that reads the Markdown alone reports a thing: the evidence for the
boundary is the *whitespace on the page*, and the whitespace is what was lost.

## Why a second encoding, and not the page

`restore-headings` answers this from the PDF, by measuring leading and looking
for a line set apart. That works, and it is the only thing that works on a file
with no second encoding -- but it is a measurement with a threshold, it needs a
render, and it only ever looks for *heads*. A signature and a bibliography entry
are set apart on the page exactly as a head is, and that screen has no verdict
for either.

A second pass of a different OCR engine over the same PDF has already made the
whole judgement, for every block on every page, and written the answer down as
newlines. Where the two encodings disagree about whether a blank line belongs
somewhere, one of them is wrong, and the disagreement is free to compute: align
the two token streams and read off the boundaries.

This is not the usual appeal to a second opinion. The second encoding is wrong
about plenty -- it reads `Barner` as `Earner`, glues `Joergen Clauson-Kaas` onto
the head below it, and splits a bibliography entry in half at a line break. None
of that matters, because it is not being trusted about *words*. It is being
asked one question, about layout, that it answers from the same pixels and that
our encoding does not answer at all.

## What it costs to be wrong

Every finding is a place to *insert* a blank line. Inserting one where the scan
has none breaks a paragraph in half -- which is the defect
`detect_severed_paragraphs.py` exists to find, so a mistake here lands in
another screen's lap rather than disappearing. That is the reason this script
only reports and never writes: see the confidence tiers below.

## Running it

    detect_lost_boundaries.py scan ONS_171          # find the second encoding
    detect_lost_boundaries.py scan ONS_171 --all    # include the OPEN tier
    detect_lost_boundaries.py scan ONS_171 --second path/to/other.md
    detect_lost_boundaries.py rows ONS_171          # file<TAB>class<TAB>line<TAB>anchor

`rows` is for counting and for piping to an editor, **not** for
`crop_sheets.py`: its third field is a line in the Markdown, where the other
skills' rows carry a page of the scan. This screen never opens the PDF and so
has no page to give. Settling an `OPEN` finding against the scan means
finding the page yourself, from the nearest `<!-- page-start -->` above the
reported line.

`scan` exits non-zero when there is something to fix, and exits 0 with
`no second encoding` when there is nothing to compare against -- so it is safe
to put in a pass that runs over the whole corpus.

Second encodings are looked for at `$ONS_SECOND_DIR/<stem>/<stem>.ou.md`,
with `ONS_SECOND_DIR` defaulting to `~/personal/ocr-junk`.

## Confidence tiers

CLEAN   the text before the boundary closes a sentence, and the text after it
        opens one. Both encodings agree about where the sentence ends; they
        disagree only about whether a blank line follows it. Nothing else
        produces that shape, and these are what to act on.

OPEN    the text before the boundary does not close a sentence. Usually the
        second encoding is the one at fault, having broken a block at a line
        break of its own -- ONS_171's `Bartold, V. V. 1964. "Tsermoinali pri
        dvore uzbetskikh / khanov v XVII v."` is one block split into two.
        But a real head often follows a signature with no stop (`...will be
        badly missed JL  **Members News**`), so the tier is reported under
        `--all` rather than dropped. Settle these on the page.

Alignment itself is also a source of error, and is guarded separately: a
boundary is only reported when the tokens on *both* sides of it sit inside the
same matched run, so a boundary that falls in a region where the two OCRs
disagree about the words is passed over rather than guessed at.

## The class, and who owns the repair

The class is read off the second encoding's own markup and shape, because it
already decided what the block was. It routes the finding; it does not fix it.

HEAD    the second encoding made it a heading (`### References`).
        -> `restore-headings`, which knows what marker the corpus gives a head
           at that level and will check it against the scan.
BYLINE  the block is a personal name, or opens `By ...`.
        -> `restore-headings`; a byline is not a heading and wants no marker.
LIST    the block opens with a list marker, or with a label the corpus's lists
        use (`1.`, `i.`, `a)`, `(3)`).
        -> `restore-lists`.
BIBL    the block has the shape of a bibliography entry -- a surname, initials
        and a year -- and most files have dozens in a row.
        -> `restore-lists`, which owns the line-per-entry repair.
PROSE   an ordinary paragraph break with nothing to mark it.
        -> this skill; insert the blank line and nothing else.
"""
import argparse
import difflib
import os
import pathlib
import re
import sys

MD_DIR = pathlib.Path(__file__).resolve().parents[4] / "jons"
SECOND_DIR = pathlib.Path(
    os.environ.get("ONS_SECOND_DIR", "~/personal/ocr-junk")
).expanduser()

# Letters, digits and the apostrophes the corpus's transliterations use. Case is
# folded and everything else dropped, so the two encodings' disagreements about
# punctuation, emphasis markers and bracketing cost nothing in the alignment.
WORD_RE = re.compile(r"[0-9A-Za-zÀ-ɏĀ-ſ'’]+")
# Blanked rather than deleted, so every surviving token keeps its true offset
# and the line numbers reported are the ones in the file.
#
# `<sup>60</sup>` is in this list because its tags are *words* to the
# tokeniser, and a footnote reference the second encoding renders differently
# therefore puts two phantom `sup` tokens into the seam and takes the
# alignment guard down with it. ONS_171's article on Kharijite coinage ends
# `...coins of 'Abd al-Malik.<sup>60</sup>` with the `References` head glued
# to it, and that was exactly the boundary this screen could not see.
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
TAG_RE = re.compile(r"</?[a-zA-Z][^<>]*>")
BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
# How far the two encodings' token counts may drift across a boundary before
# the alignment is no longer trusted to say where in our file it falls. Four
# covers the disagreements that actually occur at a seam -- a substituted word,
# a footnote reference one encoding tokenises and the other does not, a page
# number one of them kept -- without letting a boundary wander into the next
# sentence.
SEAM_SLACK = 4

# --- the sentence-close test ---------------------------------------------
# What may stand at the end of the prose before a boundary for the cut to be
# CLEAN. The closing quotes and brackets follow the stop rather than replace it
# (`...coins".`), and `---` is the horizontal rule `pdfmd` leaves where a page
# break fell, which is a stronger block boundary than any full stop.
SENTENCE_END_RE = re.compile(r"(?:[.!?:][\"')\]”’]?|---|—)\s*$")
# A footnote reference stands between the stop and the boundary, and its tags
# are blanked by the time this is tested, so what is left of
# `...al-Malik.<sup>60</sup>` is a stop, some spaces and a bare number. Taking
# the number off and asking again is safe because a run of digits that is
# *not* a footnote reference is part of the sentence and has no stop in front
# of it -- `...a tanga of thirty dinars` and `...t. 1, 1967, Tashkent` both
# end in words, and `...cost 100 tillas` in a word after the digits.
FOOTNOTE_REF_RE = re.compile(r"\s*\d{1,3}\s*$")
# Markup that opens the block *below* the cut and so must not be read as part
# of the sentence above it: emphasis delimiters, a heading marker, a bullet.
EMPH_OPEN_RE = re.compile(r"[*_#>\s]+$")

# --- the classes ---------------------------------------------------------
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
LIST_RE = re.compile(
    r"^(?:[-*+•]\s"                     # a bullet
    r"|\d{1,3}[.)]\s"                        # 1.  1)
    r"|\(\d{1,3}\)\s"                        # (1)
    r"|[ivxlIVXL]{1,5}[.)]\s"                # i.  iv)
    r"|[a-zA-Z][.)]\s"                       # a)  A.
    r")"
)
# `Surname, A. B. 1963.` and `Surname, Iu. E. 1970.` -- the form every
# bibliography in the corpus uses, and the one the second encoding puts one to
# a block. The year is what separates it from an ordinary sentence that happens
# to open with a name. Initials run to three letters because the corpus's
# Russian transliterations need them: `Iu.`, `Kh.`, `Ch.`, `Shch.`.
BIBL_RE = re.compile(
    r"^(?:"
    r"[A-Z][\w'’-]+(?:\s+[a-z]{2,4})?,\s*"       # Surname,  /  van Surname,
    r"(?:[A-Z][a-z]{0,3}\.?\s*){1,4}"            # A. B.  /  Iu. E.
    r"[“\"(]?\s*\d{4}[a-z]?\b"                   # 1963  1963a
    r"|"
    # The sigla form, where a keyword stands in for the author and the whole
    # entry is cited by it: `History 1955. Istoriia uzbekskoi SSR...`,
    # `Materialy 1933. ...`. The stop after the year is what keeps an ordinary
    # sentence (`Khiva 1873 was annexed...`) out.
    r"[A-Z][\w'’-]{2,}\s+\d{4}[a-z]?\s*[.,]"
    r")"
)
# A signature: two to four capitalised words and nothing else in the block.
# `Vladimir N. Nastich`, `Joergen Clauson-Kaas`, `T.D. Yih`.
#
# Two capitalised words alone are not enough, because a short section head has
# exactly that shape and the second encoding promotes both: `### Index
# Islamicus` and `#### The Truth` are heads, not anyone's name. So the block
# has to carry a mark a name carries and a head does not -- a dotted initial,
# a hyphenated or apostrophised surname, or a third word -- which is also what
# separates `Vladimir N. Nastich` from `The Truth`. The cost is the plain
# two-word signature (`Karan Singh`), which comes back HEAD; it is the right
# way round, since a head wrongly called a name loses its marker, and a name
# wrongly called a head gets one a reviewer can see and strike.
NAME_WORD_RE = r"(?:[A-Z]\.?|[A-Z][a-zà-ÿ]+(?:[-'’][A-Z]?[a-z]+)*)"
BYLINE_RE = re.compile(
    r"^(?=[^\n]*(?:[A-Z]\.|[A-Za-z][-'’][A-Z]|(?:\s\S+){2,}))"
    r"(?:[Bb]y\s+)?(?:%s\.?\s+){1,3}%s$" % (NAME_WORD_RE, NAME_WORD_RE))


def blank(match):
    """Spaces of the same length, with the newlines left where they were.

    Both halves matter. Equal length keeps every later token's offset true, so
    the reported line numbers are the file's own. Keeping the newlines matters
    because a `<!-- source-typo ... -->` note runs over several lines, and
    flattening those to spaces silently shifted every finding below it up by
    as many lines -- ONS_171's masthead was reported at L1141 for a boundary
    that is at L1167.
    """
    return re.sub(r"[^\n]", " ", match.group(0))


def load(path):
    """File text with comments, images and tags blanked, offsets preserved."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    for pattern in (COMMENT_RE, IMAGE_RE, TAG_RE):
        text = pattern.sub(blank, text)
    return text


def tokenise(text):
    return [(m.group(0).lower(), m.start(), m.end())
            for m in WORD_RE.finditer(text)]


def block_starts(text, tokens):
    """Token indices that open a block, each with the raw text of that block.

    A block opens after a blank line. The raw text runs to the next blank line
    and is what the class is read from, so the second encoding's own markers --
    its `###`, its bullets -- are still there to be seen.
    """
    starts = {}
    for i in range(1, len(tokens)):
        gap = text[tokens[i - 1][2]:tokens[i][1]]
        if not BLANK_LINE_RE.search(gap):
            continue
        # The block's text begins at the start of the token's own line, which is
        # where any marker sits, and ends at the next blank line.
        line_start = text.rfind("\n", 0, tokens[i][1]) + 1
        end = BLANK_LINE_RE.search(text, tokens[i][2])
        starts[i] = text[line_start:end.start() if end else len(text)].strip()
    return starts


# A hanging-indent entry's run-in label: a short capitalised phrase closed by a
# stop, with the entry's first sentence running on after it. `Sultan Haji Khan
# b. Ilbars. Came from Yangi Shahr...`, `Juchi. Was proclaimed Khan of Khiva...`
# This is never trusted on its own -- `Nadir left a governor there. The
# authority...` has the same shape and is two sentences of ordinary prose. See
# `promote_label_runs`.
# The lowercase particles are listed rather than allowed as a class, because
# `[a-z]+` here would match the second sentence of any paragraph (`Nadir left a
# governor there. The authority...`) and the shape would stop meaning anything.
# These are the ones a name in this corpus is built from: `Husain Qulī b.
# Abulek b. Yādgār.`, `Dost Khan b. Bujuga`, `'Abd Allah`, `van der Wis`.
_NAME = r"[A-Z'‘][\w'’‘ʿʾāīūēōḥṣṭẓḍġñ-]*"
_PARTICLE = r"(?:b|bin|ibn|al|el|van|von|der|de|da|du|le)\.?"
RUNIN_LABEL_RE = re.compile(
    r"^(?:(?:%s|%s)\.?\s+){0,7}%s"
    r"(?:\s*\([^)]{2,30}\))?[.:]\s+[A-Z]" % (_NAME, _PARTICLE, _NAME)
)
# How many of them have to fall in a row before the shape is believed. The
# Khiva and Janid ruler lists run to twenty-odd entries each; two sentences of
# prose that happen to look like a label never run to three.
LABEL_RUN = 3


def promote_label_runs(findings):
    """Reclassify PROSE findings that repeat the run-in-label shape as LIST.

    One block opening `Name. Sentence...` says nothing -- that is also what the
    second sentence of a paragraph looks like once you cut in front of it. A
    run of them says the page is set as a hanging-indent list, one entry per
    ruler or per coin type, and `pdfmd` ran the whole list into one paragraph.
    ONS_171's `LIST OF THE RULERS OF THE KHIVA KHANATE` is twenty-six entries
    on one page, and arrives as a single block: the repetition is the only
    evidence left that it was ever a list, because our encoding lost the bold
    labels that the page sets them in.
    """
    run = []
    for finding in findings + [None]:
        # Emphasis delimiters come off first. The page sets these labels in
        # bold, and our encoding kept it -- but the run that opens the bold
        # sits back at the top of the glued paragraph, so what survives at the
        # cut is a stray closing `**` in the middle of the label:
        # `Husain Quli b.** ***Abulek b. Yadgar.*** Was proclaimed khan...`.
        # Their being there at all is more evidence for the reading, not less.
        opens = re.sub(r"[*_]+", "", finding["opens"]) if finding else ""
        if (finding is not None and finding["class"] == "PROSE"
                and RUNIN_LABEL_RE.match(opens)):
            run.append(finding)
            continue
        if len(run) >= LABEL_RUN:
            for member in run:
                member["class"] = "LIST"
        run = []
    return findings


def classify(block_text):
    """Which skill owns the repair, read off the second encoding's own block."""
    heading = HEADING_RE.match(block_text)
    body = heading.group(1).strip() if heading else block_text
    first_line = body.split("\n", 1)[0].strip()
    if heading:
        # A heading whose content is a name is still a byline, and the second
        # encoding promotes them freely -- `### Joergen Clauson-Kaas`.
        return "BYLINE" if BYLINE_RE.match(first_line) else "HEAD"
    if LIST_RE.match(first_line):
        return "LIST"
    if BIBL_RE.match(first_line):
        return "BIBL"
    if len(first_line) <= 48 and BYLINE_RE.match(first_line.rstrip(".")):
        return "BYLINE"
    return "PROSE"


def closes_sentence(prose):
    """Does the prose running up to the boundary close a sentence?

    The text handed in runs to the *start* of the first token after the
    boundary, so it carries the punctuation between the two -- which is the
    whole point, since that punctuation is the evidence. What it also carries
    is the opening delimiter of whatever follows: in `...(Bartold 1968, 422).
    *References*` the slice ends `422). *`. Those delimiters belong to the
    block below the cut, not to the sentence above it, so they come off first.
    """
    prose = EMPH_OPEN_RE.sub("", prose.rstrip()).rstrip()
    if SENTENCE_END_RE.search(prose):
        return True
    return bool(SENTENCE_END_RE.search(FOOTNOTE_REF_RE.sub("", prose)))


# A line a cut must not land in, because the blank line would destroy it: a
# table row, and a fence (inside one, a blank line is content).
UNCUTTABLE_RE = re.compile(r"^\s*(?:\||```|~~~)")


def joined_by_whitespace(text, cut):
    """True when the two sides of the cut are separated by whitespace.

    Our encoding runs two lost blocks together with a space between them --
    that is what losing the blank line looks like. So if there is no
    whitespace at the cut, our file did not join two blocks there and the
    alignment has put the cut in the wrong place. Refusing on that caught two
    classes of damage on ONS_171, neither of which the tier test could see
    because both come of markup the tokeniser is blind to:

      `p. 8f.<sup>2</sup>`  the `<sup>` tags are blanked before tokenising, so
                            `2` reads as the first word of a new block and the
                            cut lands inside the tag
      `Malwa .Muhammad`     the page has no space there at all
    """
    return cut > 0 and text[cut - 1].isspace()


def inside_open_run(text, cut):
    """True when an emphasis run opened before the cut and closes after it.

    Cutting there leaves the run unclosed and sets the rest of the file in
    bold. ONS_171 has `*Sultans of Malwa .Muhammad Shah II (.AH 917-22)*` --
    one run holding a heading and the entry under it -- and a blank line
    inside it turns two blocks into two broken ones. Splitting the run and
    re-closing both halves is a real repair, but it is a judgement about what
    the emphasis was for, so it is left to `restore-headings`.
    """
    block = text[text.rfind("\n\n", 0, cut) + 1:cut]
    singles = block.count("*") - 2 * block.count("**")
    return bool(block.count("**") % 2 or singles % 2 or block.count("_") % 2)
# An emphasis run's delimiters, taken from the end of the text before the cut.
TRAILING_EMPH_RE = re.compile(r"(?<![*_])([*_]{1,3})$")


def insert_at(text, pos):
    """Where the cut goes, given the first token after it.

    Not at `pos`. The markup that opens the new block sits in front of its
    first word, and cutting between the two tears it off: `...(Bartold 1968,
    422). *References*` broken at the `R` leaves `422). *` ending one block
    and `References*` opening the next, with the run unclosed and the rest of
    the file in italic.

    So the cut backs up over an emphasis run first -- but only one that
    *opens*. The same delimiters also appear closing a run that began earlier
    in the glued paragraph, and backing up over one of those causes exactly
    the damage it is meant to avoid. The two are told apart by what sits on
    each side: an opener is preceded by whitespace and followed immediately by
    its word, so it is still attached to `pos` when the whitespace before
    `pos` has not yet been crossed. `...and the bold ends** Next block` has a
    space between the delimiters and the word and is left alone; `died.
    **Husain Quli b.**` does not, and comes with the cut.

    Returns the offset of the new block's first character -- its markup, if it
    has any, otherwise its first word. The whitespace in front of that is the
    caller's to drop: leaving it would open every new block with a space.
    """
    run = TRAILING_EMPH_RE.search(text[:pos])
    if run and (run.start() == 0 or text[run.start() - 1] in " \t\n"):
        return run.start()
    return pos


def apply(stem, findings):
    """Insert a blank line at each finding. Returns (applied, refused).

    A blank line and nothing else. The class says a head or a list item is in
    there, but giving it a `##` or a `1.` is `restore-headings`' and
    `restore-lists`' work, done against the scan -- this pass only puts the
    block on its own, which is the precondition both of those screens need and
    neither can establish.

    Applied back to front, so that an earlier cut's two characters do not move
    every later one.
    """
    path = MD_DIR / f"{stem}.md"
    text = path.read_text(encoding="utf-8")
    applied, refused = [], []
    for finding in sorted(findings, key=lambda f: f["pos"], reverse=True):
        cut = insert_at(text, finding["pos"])
        line_start = text.rfind("\n", 0, cut) + 1
        why = None
        if UNCUTTABLE_RE.match(text[line_start:text.find("\n", cut)]):
            why = "cut lands in a table or a fence"
        elif not joined_by_whitespace(text, cut):
            why = "no whitespace at the cut -- the alignment is off by a token"
        elif inside_open_run(text, cut):
            why = "cut falls inside an open emphasis run"
        if why:
            refused.append((finding, why))
            continue
        left = text[:cut].rstrip(" \t")
        # The cut sometimes lands at the start of a continuation line, where
        # the newline that ends the line above is already there and a second
        # `\n\n` would leave two blank lines instead of one.
        text = left + ("\n" if left.endswith("\n") else "\n\n") + text[cut:]
        applied.append(finding)
    path.write_text(text, encoding="utf-8")
    return applied, refused


def find_second(stem, override=None):
    if override:
        path = pathlib.Path(override).expanduser()
        return path if path.is_file() else None
    path = SECOND_DIR / stem / f"{stem}.ou.md"
    return path if path.is_file() else None


def scan(stem, second_path):
    """Boundaries the second encoding has and ours lacks."""
    ours = load(MD_DIR / f"{stem}.md")
    theirs = load(second_path)
    ta, tb = tokenise(ours), tokenise(theirs)
    wa = [w for w, _, _ in ta]
    wb = [w for w, _, _ in tb]
    our_starts = set(block_starts(ours, ta))
    their_starts = block_starts(theirs, tb)

    # autojunk would treat a token appearing in more than 1% of the file as
    # noise and refuse to anchor on it, which on a 80k-token file throws away
    # every `the` and `of` -- the commonest anchors there are.
    matcher = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    aligned = {}
    for i, j, n in matcher.get_matching_blocks():
        for k in range(n):
            aligned[j + k] = i + k

    findings = []
    for j in sorted(their_starts):
        i = aligned.get(j)
        # The first token after the boundary has to be aligned, or we have no
        # idea where in our file the boundary falls.
        if i is None or i == 0:
            continue
        # Something before it has to be aligned too, or the boundary may belong
        # somewhere other than where the one matched token puts it. But the
        # test cannot be that the mapping is one-for-one across the seam,
        # because the seam is exactly where the two encodings disagree:
        #
        #   substituted  `coins of the Safavids. London`  is `Safavidis` there
        #   inserted     `al-Malik.<sup>60</sup> References` keeps the `60`,
        #                where the other encoding wrote `al-Malik.⁶⁰` and the
        #                superscript is not a token at all
        #
        # Each of those cost a real finding under a one-for-one rule. So the
        # test is a neighbourhood instead: find the nearest token before the
        # boundary that both encodings agreed on, require the two mappings to
        # stay in order and no more than SEAM_SLACK tokens apart, and let the
        # boundary be anywhere in between.
        anchor = next((k for k in range(j - 1, max(-1, j - 1 - SEAM_SLACK), -1)
                       if k in aligned), None)
        if anchor is None:
            continue
        previous = aligned[anchor]
        if not previous < i <= previous + SEAM_SLACK:
            continue
        # We have the boundary already if it falls anywhere in that window.
        if any(k in our_starts for k in range(previous + 1, i + 1)):
            continue
        before = ours[max(0, ta[i][1] - 110):ta[i][1]]
        tier = "CLEAN" if closes_sentence(before) else "OPEN"
        findings.append({
            "line": ours.count("\n", 0, ta[i][1]) + 1,
            # Offset of the first token after the cut. Reported for an applier
            # to work from -- but a cut goes *before* whatever markup opens the
            # new block, not here: `...422). *References*` has to break ahead
            # of the `*`, or the run is left open. See `insert_at`.
            "pos": ta[i][1],
            "tier": tier,
            "class": classify(their_starts[j]),
            # Our own text from the cut onwards, with its markup intact. The
            # class is read from the second encoding, but the label-run test
            # below needs the block as *we* hold it.
            "opens": ours[ta[i][1]:ta[i][1] + 140].split("\n")[0],
            "before": " ".join(wa[max(0, i - 7):i]),
            "after": " ".join(wa[i:i + 7]),
        })
    return promote_label_runs(findings)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=("scan", "rows", "fix"))
    parser.add_argument("stem")
    parser.add_argument("--second", help="path to the second encoding")
    parser.add_argument("--all", action="store_true",
                        help="report the OPEN tier too")
    args = parser.parse_args()

    second = find_second(args.stem, args.second)
    if second is None:
        if args.second:
            # An explicit path that is not there is a mistake, not an absence.
            sys.exit(f"no such file: {args.second}")
        if args.mode == "scan":
            print(f"{args.stem}: no second encoding "
                  f"(looked in {SECOND_DIR}/{args.stem}/)")
        return 0

    findings = scan(args.stem, second)
    shown = [f for f in findings if args.all or f["tier"] == "CLEAN"]

    if args.mode == "fix":
        # `--all` widens what `scan` prints; it must not widen what `fix`
        # writes. An OPEN finding is one where the second encoding is the
        # likelier of the two to be wrong, and it is settled on the page.
        clean = [f for f in findings if f["tier"] == "CLEAN"]
        applied, refused = apply(args.stem, clean)
        for f, why in refused:
            print(f"  REFUSED {f['class']:<7} L{f['line']:<5} {why}\n"
                  f"          ...{f['before']}  ||  {f['after']}...")
        print(f"{args.stem}: {len(applied)} blank line(s) inserted"
              + (f", {len(refused)} refused" if refused else "")
              + f"\n  markers not written: run restore-headings for the "
                f"{sum(1 for f in applied if f['class'] in ('HEAD', 'BYLINE'))}"
                f" HEAD/BYLINE and restore-lists for the "
                f"{sum(1 for f in applied if f['class'] in ('LIST', 'BIBL'))}"
                f" LIST/BIBL findings")
        return 0

    if args.mode == "rows":
        for f in shown:
            print(f"{args.stem}\t{f['class']}\t{f['line']}\t{f['after']}")
        return 1 if shown else 0

    by_class = {}
    for f in shown:
        by_class.setdefault(f["class"], []).append(f)
    for cls in ("HEAD", "BYLINE", "LIST", "BIBL", "PROSE"):
        for f in by_class.get(cls, []):
            print(f"  {f['class']:<7} {f['tier']:<5} L{f['line']:<5} "
                  f"...{f['before']}  ||  {f['after']}...")
    tally = "  ".join(f"{c} {len(by_class[c])}"
                      for c in ("HEAD", "BYLINE", "LIST", "BIBL", "PROSE")
                      if c in by_class)
    hidden = len(findings) - len(shown)
    print(f"\n{args.stem}: {len(shown)} boundary/ies lost"
          + (f" -- {tally}" if tally else "")
          + (f"  ({hidden} OPEN, hidden; --all to see)" if hidden else "")
          + f"\n  second encoding: {second}")
    return 1 if shown else 0


if __name__ == "__main__":
    sys.exit(main())
