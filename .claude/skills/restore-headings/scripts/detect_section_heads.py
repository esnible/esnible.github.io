#!/usr/bin/env python3
"""Find the newsletters' standing section heads glued into a neighbouring block,
and author bylines that `pdfmd` promoted to headings.

Companion to `detect_headings.py`, and deliberately a separate screen, because
it asks a different question and needs no PDF.

`detect_headings.py` starts from the scan: it finds a line *set apart on the
page* and asks whether the Markdown has it as a heading. Two common defects sit
outside that question, and it reports neither:

  1. A standing section head (`Lists Received`, `Other News`, `Auction News`,
     `From the Editor`, ...) glued either to the tail of the preceding paragraph
     or to the head of the following bold run-in. The screen misses these
     because the Markdown line it folds into matches the page's own line only
     in part, and the fuzzy match lands on the paragraph rather than the head.
     Measured over the corpus: 100 of them across 56 files, none reported.

  2. An author's initials promoted to a heading -- `# GPH`, `# M.B.`. The page
     *does* set those apart (they are right-justified at the foot of an
     article), so the screen matches them against the Markdown's `# GPH`, finds
     a heading, and reports `OK`. It has no test for the reverse error: a line
     correctly identified as set apart, but which is a byline rather than a
     head.

Both are decidable from the Markdown alone, which is what this screen does. A
closed vocabulary is the evidence: in this corpus these phrases, written
head-cased, are section heads and not prose. Three rules keep that from turning
into coincidence -- head-casing, which is what separates the head `Book
Reviews` from the prose `several book reviews, mainly in Dutch`; the reject
rules below, which drop quotations and contents listings; and the position
rules, which apply a cut only where there is exactly one place to put it.

Usage:
    detect_section_heads.py scan ONS_152 [ONS_153 ...]  # report, change nothing
    detect_section_heads.py scan --all                  # sweep jons/
    detect_section_heads.py scan ONS_152 -v             # show rejects too
    detect_section_heads.py rows ONS_152                # crop_sheets.py rows
    detect_section_heads.py fix  ONS_152                # rewrite the Markdown

`scan` exits non-zero when there is something to fix. Needs no PDF, no
PyMuPDF, and no numpy.
"""
import argparse
import pathlib
import re
import sys

MD_DIR = pathlib.Path(__file__).resolve().parents[4] / "jons"

# --- the vocabulary -------------------------------------------------------
# The newsletters' standing section heads, taken from the corpus's own heading
# lines rather than invented: every entry here appears as a `#` heading
# somewhere in jons/ (`ONS News` 58 times, `New and Recent Publications` 42,
# `Other News` 39, `Lists Received` 17, `Auction News` 16, ...).
#
# Deliberately NOT in this list, though they are also common heads:
# `Articles`, `Notes`, `References`, `Introduction`, `Bibliography`,
# `Conclusion`, `Obverse`, `Reverse`. Each is an ordinary English word that
# turns up in running prose ("the articles in this issue", "see notes below"),
# so the head-casing test cannot separate head from mention and the screen
# would be mostly false positives.
SECTION_HEADS = (
    "ONS News",
    "Other News",
    "Members News",
    "Members' News",
    "From the Editor",
    "Lists Received",
    "Auction News",
    "Book Reviews",
    "New and Recent Publications",
    "Some Recent Publications",
    "Obituary",
    "Obituaries",
)

HEAD_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(h).replace(r"\ ", r"\s+") for h in SECTION_HEADS)
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Words inside a head that a typesetter leaves lower-case. Everything else in a
# head-cased phrase starts with a capital; that is the whole test.
MINOR_WORDS = {"and", "the", "of", "to", "for", "from", "in", "on", "a", "an"}

# --- the byline shape -----------------------------------------------------
# A heading whose entire content is two to four capitals, or dotted initials:
# `# GPH`, `# M.B.`, `# B.N.H.`, `# SLG`. Two neighbouring shapes look
# identical and are excluded by vocabulary, because their fix is different:
#
#   table headers  -- `# REF`, `# SIZE`, `# MINT`, `# AH`, `# RY` and friends,
#                     around 120 of them, the column heads of catalogue tables
#                     `pdfmd` flattened. They belong to
#                     `restructure-flattened-md`.
#   reference sigla -- `# HDSL`, `# HYCD`, `# SHM`, ..., the abbreviation keys
#                     of a bibliography. ONS_219 alone has eight.
#
# Neither vocabulary can be recognised by shape, so both are listed.
DOTTED_RE = re.compile(r"^(?:[A-Z]\.){2,4}$|^(?:[A-Z]\.){1,3}[A-Z]$")
PLAIN_RE = re.compile(r"^[A-Z]{2,4}$")
ROMAN_RE = re.compile(r"^(?:X{0,3})(?:IX|IV|V?I{0,3})$")
TABLE_HEAD_WORDS = {
    "REF", "SIZE", "MINT", "AH", "RY", "AD", "AE", "AR", "AV", "WT", "DIE",
    "OBV", "REV", "NO", "TYPE", "DATE", "YEAR", "WGT", "DIAM", "DEN", "KM",
    "CAT", "PL", "FIG", "VAR", "QTY", "MM", "GM", "GR", "ND", "NM", "ILL",
    # Rarity grades, which are a catalogue's densest column by far: 77 `RRR`
    # and 57 `RR` headings across the corpus, nearly all of them in the
    # ONS_174-ONS_247 catalogue files.
    "R", "RR", "RRR", "S", "VF", "EF", "VG", "UNC", "FDC", "GF", "GVF",
}
SIGLA_WORDS = {"HDSL", "HYCD", "MDBL", "SHM", "SSM", "SZP", "YCBS", "YS"}
# Short all-capitals strings that are words or abbreviations in their own
# right, and read as a legitimate heading rather than anyone's initials.
NOT_BYLINES = {
    "ONS", "EIC", "VOC", "BMC", "CE", "BCE", "NEWS", "NOTE", "NOTES", "LIST",
    "MAP", "MAPS", "TEXT", "PLATE", "OK", "AND", "THE", "OF", "SEE", "ADD",
    "ERR", "NB", "PS", "PP", "VOL", "NOS", "IBID", "ETC", "MS", "MSS",
    "BY", "COIN", "LINE", "ITEM", "PAGE", "FROM", "NEW",
}
# Above this many bare-capital candidates, the file is a flattened catalogue
# and the whole class belongs to `restructure-flattened-md`. ONS_247 reports
# 54 and ONS_245 52, almost all of them rarity grades and column heads;
# ONS_152 and ONS_153 reported one each, and both were real bylines.
MAX_PLAIN_PER_FILE = 4

SKIP_LINE = ("|", "<!--", "> ", "```", "    ")
MARKER_RE = re.compile(r"^(#{1,6})\s+")
EMPH_RE = re.compile(r"^[*_]+|[*_]+$")
# An emphasis delimiter closing the text before the head / opening the text
# after it. `[*_]{1,3}` covers `*`, `**` and `***`, all three of which the
# corpus uses on these run-in labels.
OPEN_EMPH_RE = re.compile(r"[*_]{1,3}\s*$")
CLOSE_EMPH_RE = re.compile(r"\s*[*_]{1,3}")

# --- verdicts -------------------------------------------------------------
#
# Where the head sits on the line decides the verdict, because it decides how
# many cuts the repair needs and whether there is any doubt about where they
# go. `prose` below means alphanumeric text outside the markup.
#
# GLUED-END       prose before, nothing after: the head was appended to the
#                 tail of the paragraph above it, and the prose closes a
#                 sentence, so the one cut needed is not in doubt.
#                 `...notes, a glossary and a bibliography. **Lists Received**`
# GLUED-RUNIN     nothing before, prose after: the head opens the line and the
#                 section's first paragraph follows it on the same line.
#                 `**Lists Received** Stephen Album (PO Box 7386, ...`
# GLUED-BOTH      prose both sides, and the head is set off in an emphasis run
#                 of its own -- so it is a head between two paragraphs `pdfmd`
#                 ran together, not a phrase inside one. Two cuts.
#                 `...mostly provenanced coins. **Lists Received** 5. Volume 28`
# GLUED-HEADING   the line is already a heading and holds a second head after
#                 the first, or a marked run after it.
#                 `## ONS News **From the Editor**`
# BYLINE          a heading whose whole content is initials.  `# GPH`
#
# Reported, never applied:
# GLUED-END-OPEN  GLUED-END / GLUED-BOTH, but the prose before the head does
# GLUED-BOTH-OPEN not close a sentence, so cutting there may sever one. A real
#                 head often follows the previous contributor's initials with
#                 no stop (`...will be badly missed JL **Members News**`), and
#                 a mid-sentence mention reaches here too, so a render decides.
# GLUED-COMPOUND  the head shares an emphasis run with the text after it, so
#                 the repair has to re-close the emphasis on both sides of the
#                 cut and then decide what the remainder is. Sometimes the
#                 remainder is a sub-head that wants promoting rather than
#                 un-emphasising: `**OBITUARY Dr Jarmila Stepkova (1926-1997)**`
# GLUED-MID       prose both sides and no emphasis run around the head, so
#                 nothing on the line says it is a head at all. This is where
#                 the remaining false positives collect -- a bibliography entry
#                 (`...issued 1984) KM Obituary Nun Pere, NI 17, 73 (1984)...`)
#                 or a contents listing whose page numbers the reject rules did
#                 not catch.
FIXABLE = ("GLUED-END", "GLUED-RUNIN", "GLUED-BOTH", "GLUED-HEADING")
REVIEW = ("GLUED-END-OPEN", "GLUED-BOTH-OPEN", "GLUED-COMPOUND",
          "GLUED-HEADING-JOINED", "GLUED-MID", "BYLINE")
# Longest run of prose that may precede a head inside a heading line before the
# line is read as a flattened contents page rather than a heading.
HEADING_PROSE = 40
ORDER = FIXABLE + REVIEW
# BYLINE is review-only on purpose. Dropping the marker is a one-character
# edit, but deciding it IS a byline needs the page: `# AV` is as likely to be
# the metal as anyone's initials, and only a render separates them.


def head_cased(text):
    """True when every significant word of `text` starts with a capital.

    This is the test that does the most work. The vocabulary alone matches the
    prose `he wrote many articles and several book reviews, mainly in Dutch`
    and `a short obituary was published by K. M. MacKenzie`; requiring the
    match to be written the way a head is written drops both. ALL CAPS passes
    trivially, which is what `MEMBERS' NEWS` needs.
    """
    words = [w for w in re.split(r"[^A-Za-z']+", text) if w]
    if not words:
        return False
    for i, w in enumerate(words):
        if i and w.lower() in MINOR_WORDS:
            continue
        if not w[0].isupper():
            return False
    return True


def rejected(line, m):
    """Why this match is not a folded head, or None.

    Three shapes account for nearly all of what head-casing alone lets
    through, and all three are quotation rather than section head.
    """
    before, after = line[: m.start()], line[m.end():]
    # A head named in prose rather than used: `found under "Members News" on
    # page 2 of this newsletter`.
    if before.rstrip().endswith(('"', "'", "“", "‘", "(", "[")):
        return "quoted"
    if after.lstrip().startswith(('"', "”", "’")) and '"' in before:
        return "quoted"
    # A bibliography's own sub-head, which is a heading but not this
    # screen's kind of heading. ONS_152's `## Bibliography` runs seven of
    # them, each with the colon inside the emphasis run -- `**Numismatic
    # Monographs:**`, `**Editorial work:**`, `**Obituaries:**` -- and on the
    # page each is bold on a line of its own, exactly as `Bibliography`
    # itself is. They belong at `###` under the section they divide, which
    # is `detect_headings.py`'s job and a reader's; promoting one to the
    # newsletter's own section level would say that the issue has an
    # Obituaries section here, when what it has is a list of obituary
    # notices published elsewhere. The colon is the tell: a standing section
    # head never carries one.
    if re.match(r"\s*:\s*[*_]{1,3}", after) and OPEN_EMPH_RE.search(before):
        return "runin-label"
    # A contents listing: the entry ends in its page number. `Obituary - Lance
    # Dane (S. Bhandare) 1`, `ONS News - meetings, members' news, ... etc 2`.
    if re.search(r"[\s.,;)]\d{1,3}[\s.,]*$", line.rstrip()):
        return "contents"
    # Dot leaders, the other way a contents line is set. Four dots, not
    # three: three is how this OCR renders the ellipsis that elides a
    # member's name, and `**Members News**...) is currently researching
    # the life of John Prinsep` is a folded head, not a contents entry.
    if re.search(r"\.{4,}|…", line):
        return "contents"
    return None


def head_matches(text):
    """Vocabulary hits in `text` that are written the way a head is written."""
    out = []
    for m in HEAD_RE.finditer(text):
        if head_cased(m.group(0)):
            out.append(m)
    return out


def _closes_sentence(text):
    """True when `text` ends somewhere a paragraph may be cut.

    The emphasis delimiter that opens the head's own run is stripped
    first: in `...a glossary and a bibliography. **Lists Received**` the
    text before the head ends in `**`, and testing that literally reports
    every properly-marked run-in label as an unsafe cut.
    """
    return bool(re.search(r"[.!?:;)\]}’\"]\s*$", text.rstrip().rstrip("*_ ")))


def classify_line(line):
    """[(verdict, match, base, note), ...] for one Markdown line.

    `base` is where `content` starts inside `line`, so a match's own offset
    can be turned back into a column of the file. Getting that wrong is how
    an early version cut `## ONS News Obituaries` into `## ONS Ne` plus
    `### ws Obituaries`: the match was found in the line with its `## `
    stripped, and the column was then used against the line with it still on.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(SKIP_LINE):
        return []
    marker = MARKER_RE.match(stripped)
    content = MARKER_RE.sub("", stripped, count=1) if marker else stripped
    base = (len(line) - len(line.lstrip())) + (len(stripped) - len(content))
    bare = EMPH_RE.sub("", EMPH_RE.sub("", content)).strip().rstrip(".:")

    found = []
    matches = head_matches(content)
    if not matches:
        return []

    # The line IS the head, marked or not -- nothing to do. `More ONS News` and
    # `MEMBERS NEWS AND REQUESTS` are legitimate compound heads and count here
    # too: what matters is that the line carries no body text.
    if marker and len(matches) == 1:
        rest = (content[: matches[0].start()] + content[matches[0].end():])
        if len(re.sub(r"[^A-Za-z0-9]", "", rest)) <= 12:
            return []
    if not marker and len(matches) == 1 and bare.lower() == matches[0].group(0).lower():
        # Its own line but unmarked -- that is detect_headings.py's FLAT, whose
        # evidence is on the page. Not this screen's business.
        return []

    for m in matches:
        why = rejected(content, m)
        if why:
            found.append((f"reject:{why}", m, base, ""))
            continue
        before = content[: m.start()]
        after = content[m.end():]
        if marker:
            # A heading that holds a second head after the first, or a marked
            # run after it: `## ONS News Obituaries`,
            # `## ONS News **From the Editor**`. The cut goes at the *second*
            # head, so the first one is not itself a finding.
            if m is matches[0]:
                continue
            prose_before = re.sub(r"[^A-Za-z0-9]", "", before)
            # A heading is short. A flattened contents page carrying a `#` is
            # not, and a cut in the middle of one is meaningless:
            # `# CONTENTS OF JOURNAL 208 Page Obituaries for Nicholas Rhodes
            # New Secretary General ONS meeting ...`
            if len(prose_before) > HEADING_PROSE:
                found.append(("GLUED-MID", m, base, "inside a long heading"))
                continue
            # What sits between the two heads decides whether they are two
            # heads or one. Nothing, or an emphasis delimiter, and `pdfmd` ran
            # two heads together. A conjunction, and the scan may well print
            # one combined head -- `## Lists Received and Auction News` --
            # where a cut would leave a dangling `and`.
            gap = content[matches[matches.index(m) - 1].end(): m.start()]
            if re.sub(r"[^A-Za-z0-9]", "", gap):
                found.append(("GLUED-HEADING-JOINED", m, base,
                              f"joined by {gap.strip()!r}"))
                continue
            found.append(("GLUED-HEADING", m, base, ""))
            continue
        prose_before = re.sub(r"[^A-Za-z0-9]", "", before)
        prose_after = re.sub(r"[^A-Za-z0-9]", "", after)
        # Is the head wearing emphasis of its own? Measured locally, from the
        # delimiters either side of the match, rather than by pairing every
        # `*` on the line: `**Lists Received** 5. Volume 28` and
        # `**OBITUARY Dr Jarmila Stepkova (1926-1997)** Curator of...` differ
        # only in whether a delimiter closes immediately after the head.
        opened = bool(OPEN_EMPH_RE.search(before))
        closed = bool(CLOSE_EMPH_RE.match(after))
        if opened and not closed:
            found.append(("GLUED-COMPOUND", m, base,
                          "shares an emphasis run with the text after it"))
            continue
        if not prose_after:
            if not prose_before:
                continue
            found.append(("GLUED-END" if _closes_sentence(before)
                          else "GLUED-END-OPEN", m, base, ""))
            continue
        if not prose_before:
            found.append(("GLUED-RUNIN", m, base, ""))
            continue
        if opened and closed:
            found.append(("GLUED-BOTH" if _closes_sentence(before)
                          else "GLUED-BOTH-OPEN", m, base, ""))
            continue
        found.append(("GLUED-MID", m, base, ""))
    return found


def classify_bylines(md_lines):
    """Headings whose whole content is initials.

    Dotted initials (`M.B.`, `B.N.H.`) are distinctive enough to stand on
    their own. Bare capitals (`GPH`, `SLG`) have the same shape as a
    catalogue's column heads and rarity grades, so three further tests apply,
    each of them measured rather than assumed:

    - **vocabulary** -- the column heads, the rarity grades, the bibliography
      sigla, and the short all-capitals strings that are words rather than
      initials.
    - **uniqueness within the file** -- a byline is a signature and appears
      once. A flattened table's cell text repeats: ONS_247 sets `RRR` as a
      heading dozens of times over.
    - **density within the file** -- above MAX_PLAIN_PER_FILE candidates the
      file is a catalogue, and every candidate in it is table debris for
      `restructure-flattened-md` rather than a byline for this screen.
    """
    candidates, counts = [], {}
    for row, line in enumerate(md_lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        content = MARKER_RE.sub("", stripped, count=1)
        bare = EMPH_RE.sub("", EMPH_RE.sub("", content)).strip()
        dotted = bool(DOTTED_RE.match(bare))
        if not dotted and not PLAIN_RE.match(bare):
            continue
        candidates.append((row, bare, dotted))
        counts[bare] = counts.get(bare, 0) + 1

    plain_n = sum(1 for _, _, dotted in candidates if not dotted)
    out = []
    for row, bare, dotted in candidates:
        plain = bare.replace(".", "")
        if plain in TABLE_HEAD_WORDS:
            out.append(("reject:table-head", row, bare))
        elif plain in SIGLA_WORDS:
            out.append(("reject:siglum", row, bare))
        elif plain in NOT_BYLINES:
            out.append(("reject:abbreviation", row, bare))
        elif dotted:
            out.append(("BYLINE", row, bare))
        elif ROMAN_RE.match(bare):
            out.append(("reject:roman", row, bare))
        elif counts[bare] > 1:
            out.append(("reject:repeated", row, bare))
        elif plain_n > MAX_PLAIN_PER_FILE:
            out.append(("reject:catalogue", row, bare))
        else:
            out.append(("BYLINE", row, bare))
    return out


def analyse(md_lines):
    found = []
    for row, line in enumerate(md_lines):
        for verdict, m, base, note in classify_line(line):
            found.append({"verdict": verdict, "row": row,
                          "col": base + m.start(),
                          "text": m.group(0), "note": note, "line": line})
    for verdict, row, bare in classify_bylines(md_lines):
        found.append({"verdict": verdict, "row": row, "col": 0,
                      "text": bare, "note": "", "line": md_lines[row]})
    found.sort(key=lambda f: (ORDER.index(f["verdict"])
                              if f["verdict"] in ORDER else len(ORDER),
                              f["row"]))
    return found


# --- reporting and repair -------------------------------------------------

def report(stem, found, verbose):
    counts = {}
    for f in found:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    open_n = sum(n for v, n in counts.items() if v in FIXABLE)
    review_n = sum(n for v, n in counts.items() if v in REVIEW)
    shown = [v for v in ORDER if v in counts]
    tail = "  ".join(f"{v} {counts[v]}" for v in shown)
    rej = sum(n for v, n in counts.items() if v.startswith("reject:"))
    print(f"{stem}: {tail or 'none'}  -- {open_n} to fix"
          + (f", {review_n} to review" if review_n else "")
          + (f" ({rej} rejected)" if rej and verbose else ""))
    for f in found:
        if f["verdict"].startswith("reject:") and not verbose:
            continue
        note = f"  -- {f['note']}" if f["note"] else ""
        print(f"  {f['verdict']:15s} line {f['row'] + 1:5d} {f['text']!r}{note}")
        print(f"{'':22s}{f['line'].strip()[:100]!r}")
    return open_n


def rows(stem, found, md_lines):
    """`file<TAB>label<TAB>anchor` for each finding a render has to settle.

    The three-column form, with no page: this screen never opens the PDF, so
    it does not know one, and `crop_sheets.py` then searches every page for
    the anchor. That is what these findings want anyway -- which page the line
    sits on is part of the question.

    A BYLINE's own text is two to four characters, far too little for a fuzzy
    word match, so its anchor is the line above it: the tail of the article
    the initials sign.
    """
    out = []
    for f in found:
        if f["verdict"] not in REVIEW:
            continue
        if f["verdict"] == "BYLINE":
            prev = ""
            for row in range(f["row"] - 1, -1, -1):
                if md_lines[row].strip():
                    prev = md_lines[row].strip()
                    break
            anchor = f"{prev[-110:]} {f['text']}".strip()
        else:
            anchor = f["line"].strip()[:160]
        out.append(f"{stem}\tline {f['row'] + 1} {f['verdict']}\t{anchor}")
    return out


def apply(md_lines, found, marker):
    """Rewrite the Markdown. Returns (new lines, count applied).

    Only one cut per line: a second head on a line the first cut already moved
    is re-screened on the next run, against the text as it then stands.
    """
    edits = {}
    for f in found:
        if f["verdict"] in FIXABLE:
            edits.setdefault(f["row"], f)
    out, applied = [], 0
    for row, line in enumerate(md_lines):
        f = edits.get(row)
        if f is None:
            out.append(line)
            continue
        applied += 1
        before = line[: f["col"]]
        head_text = line[f["col"]: f["col"] + len(f["text"])]
        after = line[f["col"] + len(f["text"]):]
        # The head loses the emphasis it wore as a run-in label -- a heading
        # marks itself -- and keeps any other punctuation it carried, so the
        # word stream is untouched. The body keeps its own leading markup: a
        # `- ` or `- *` after the label is a real list, and stripping the dash
        # off `**New and Recent Publications** - * Moushegian, Kh, ...` would
        # take the list apart.
        lead = before.rstrip(" *_")
        body = after.lstrip(" *_")
        if f["verdict"] == "GLUED-END":
            # Nothing but markup follows the head, so it joins the heading.
            out.extend([lead, "", f"{marker} {(head_text + after).strip(' *_')}"])
        elif f["verdict"] == "GLUED-RUNIN":
            out.extend([f"{marker} {head_text}", "", body])
        elif f["verdict"] == "GLUED-BOTH":
            out.extend([lead, "", f"{marker} {head_text}", "", body])
        else:  # GLUED-HEADING
            depth = MARKER_RE.match(line.strip()).group(1)
            sub = depth + "#" if len(depth) < 6 else depth
            out.extend([before.rstrip(" *_"), "",
                        f"{sub} {(head_text + after).strip(' *_')}"])
    return out, applied


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("scan", "report, change nothing"),
                            ("rows", "emit crop_sheets.py rows for the "
                                     "findings a render has to settle"),
                            ("fix", "rewrite the Markdown in place")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("stems", nargs="*", metavar="ONS_152")
        p.add_argument("--all", action="store_true",
                       help="every .md file in jons/")
        p.add_argument("-v", "--verbose", action="store_true",
                       help="also show the matches the reject rules dropped")
        if name == "fix":
            p.add_argument("--marker", default="##",
                           help="what to prefix a cut-out head with "
                                "(default '##')")
    args = ap.parse_args()

    stems = list(args.stems)
    if args.all:
        stems += sorted(p.stem for p in MD_DIR.glob("*.md"))
    if not stems:
        sys.exit("no files: name a stem or pass --all")

    total = 0
    for stem in stems:
        md = MD_DIR / f"{stem}.md"
        if not md.exists():
            print(f"{stem}: no Markdown at {md}", file=sys.stderr)
            total += 1
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            print(f"{stem}: not UTF-8 ({exc})", file=sys.stderr)
            continue
        md_lines = text.split("\n")
        found = analyse(md_lines)
        if args.cmd == "rows":
            r = rows(stem, found, md_lines)
            if r:
                print("\n".join(r))
            continue
        if not found and not args.verbose and len(stems) > 1:
            continue
        open_n = report(stem, found, args.verbose)
        if args.cmd == "fix" and open_n:
            new, applied = apply(md_lines, found, args.marker)
            if applied:
                md.write_text("\n".join(new), encoding="utf-8")
                print(f"  wrote {md} ({applied} line(s) changed)")
        total += open_n
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
