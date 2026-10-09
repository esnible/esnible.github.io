#!/usr/bin/env python3
"""Find paragraphs `pdfmd` severed at a physical line break in a `jons/` file.

The source PDFs are typewritten scans. `pdfmd` sometimes reads a single
physical line of a paragraph as its own block, so the sentence is cut in two
by a `\\n\\n` and the halves render as separate paragraphs:

```
Andre Raymond, quoting Venture de Paradis, stated that there existed a regulation forbidding the production of

Piastres or Grush in Egypt and the Barbary States ...
```

`clean-ocr-formatting` used to screen for this with one regex,
`([a-z,;:])\\n\\n([a-z])` -- the break is only caught when the text after it
starts lowercase. Across ONS_047, ONS_049, ONS_050 and ONS_051 that missed
every real instance: the continuation started with a capitalised proper noun
(`Piastres`, `Maharajah`), a year (`1716`), or an OCR'd dash (`- Hebert`).
Matching on what follows the break is the wrong test.

What the four of them have in common is the line *before* the break: it ends
mid-clause, with no terminal punctuation. So that is the signal here, and the
rules below are the ways a line can prove it was cut rather than ended:

  * `severed`      -- the line ends on a function word (`of`, `in`, `and`,
                      `the`, ...) or a comma. English sentences do not end
                      that way, so the line was cut. This holds no matter
                      what follows, which is why the capitalised-continuation
                      cases land here.
  * `severed`      -- the text after the break starts lowercase, which
                      cannot begin a paragraph.
  * `fake-list`    -- the text after the break starts `- `, so Markdown
                      renders it as a bullet. Unordered markers interrupt a
                      paragraph even without the blank line, so the dash is
                      OCR residue standing in for something else and has to
                      be read off the scan. Whether the blank line goes too
                      depends on what the dash turns out to be, and it cuts
                      both ways in practice: ONS_049's was an em dash mid
                      sentence and ONS_051's the initial of
                      `Raymond J. Hebert`, both of which need the break
                      collapsed as well -- but every dash in ONS_051's
                      `Recent Publications` was the initial of a new
                      bibliography entry (`- W. Wiggins` for `K. W. Wiggins`,
                      `- B. Coole` for `A. B. Coole`), where the blank line
                      is a real entry boundary and only the marker was wrong.
  * `hyphen-split` -- the line ends on a hyphenated word fragment, so the
                      halves join into one word with no space.

A line ending in `.`, `!`, `?` or `:` is never flagged. A paragraph may well
end there, and nothing in the text can tell a real boundary from a cut one,
so those stay invisible to this script by design.

`--loose` adds the two weak cases, both of which turn on something this
script cannot settle from the text alone:

  * the continuation is capitalised and the line ends on a word that could
    have closed a sentence. Indistinguishable from the untagged headings and
    masthead lines these files are full of (`June 1977`, `Newsletter Editor
    Dr. M. B. Mitchiner Europe ...`).
  * the continuation opens on a bare number. A year opens a sentence often
    enough in this corpus to make the rule unsafe: ONS_049's `... Spink's
    NC., May 1977, 201 Books` / `1977 Lists of Books for sale have ...` is a
    real paragraph break whose actual defect is the `Books` heading glued to
    the line above -- `restore-headings`' job, not this one.

Both are off by default because a screen that cries wolf on every file is a
screen nobody runs.

A glued heading is worth knowing about generally: it leaves the line above it
ending on a noun with no punctuation, which looks a lot like a cut. If a
finding's `prev` tail reads as a section title, send it to `restore-headings`
rather than collapsing the break.

Usage:
    detect_severed_paragraphs.py scan ONS_049
    detect_severed_paragraphs.py scan jons/ONS_049.md jons/ONS_050.md
    detect_severed_paragraphs.py scan jons/*.md --loose
    detect_severed_paragraphs.py fix  ONS_050

`fix` collapses one newline for `severed` and `hyphen-split` findings only --
`fake-list` needs the dash decided by eye against the PDF, and `--loose`
findings need a human to say whether the paragraph break is real, so `fix`
refuses both and says so.

Exit status is 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""

import re
import sys
from pathlib import Path

# A sentence cannot end on these, so a line that does was cut mid-clause.
# Words that *can* close a sentence are deliberately absent: `that`, `this`,
# `all`, `such`, `more`, `no`, `not`, `her`, `there`, `then`, `so` and friends
# all end sentences in ordinary prose, and including them trades this rule's
# precision for nothing. `above`, `below` and `each` were in this set and came
# out for the same reason: the corpus ends sentences on them constantly -- `the
# coins discussed above`, `their contents are listed below`, `at $30-35 each`
# -- and across 84 corpus findings on those three tails all but two were a
# paragraph ending exactly where it should.
FUNCTION_TAILS = {
    # articles and determiners
    "a", "an", "the", "its", "their", "our", "your", "my", "whose",
    "every", "both",
    # coordinators and subordinators
    "and", "or", "but", "nor", "because", "although", "though", "unless",
    "whereas", "while", "whilst", "whether", "if", "than", "as", "that's",
    # prepositions
    "of", "in", "on", "at", "to", "by", "for", "with", "from", "into",
    "onto", "upon", "under", "over", "beneath", "beside",
    "besides", "between", "among", "amongst", "during", "about", "after",
    "before", "through", "throughout", "without", "within", "against",
    "across", "along", "around", "behind", "beyond", "despite", "except",
    "inside", "outside", "since", "toward", "towards", "until", "via",
    "concerning", "regarding", "including", "per",
    # relatives and interrogatives taking a complement
    "which", "who", "whom", "when", "where",
    # auxiliaries and copulas
    "is", "are", "was", "were", "be", "been", "being", "am", "has", "have",
    "had", "having", "does", "did", "will", "would", "shall", "should",
    "may", "might", "must", "can", "could", "cannot",
}

# Trailing marks that close a sentence without ending the line's last token:
# quotes, brackets, emphasis, and the superscript footnote digits this corpus
# prints after a cited name (`Raymond²`).
CLOSERS = "\"'’”»)]}*_¹²³⁰⁴⁵⁶⁷⁸⁹"
TERMINAL = ".!?:"

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
FENCE_RE = re.compile(r"^\s*```")
IAL_RE = re.compile(r"^\s*\{:")
BULLET_RE = re.compile(r"^\s{0,3}([-*+])\s+\S")
OL_RE = re.compile(r"^\s{0,3}\d{1,9}[.)](\s|$)")
# `a) Flowered silver lumps` / `b) Arakan silver coins` -- a lettered list,
# which pdfmd leaves unmarked so Markdown renders it as prose. The item starts
# lowercase, which would otherwise read as a continuation.
LETTER_OL_RE = re.compile(r"^\s{0,3}[a-z][.)]\s")
# `* * *Fig. 17. ...` -- the marker is followed by more emphasis junk, so it
# is leftover per-word asterisks (step 2's job), not a bullet.
JUNK_MARKER_RE = re.compile(r"^\s{0,3}[-*+]\s+[-*+_]")
# Two or more ` - ` separators in one line: a borderless list or family tree
# pdfmd flattened, where the dashes are structure rather than a cut sentence.
# `restructure-flattened-md` owns those; collapsing a break inside one would
# only cement the damage.
FLATTENED_RE = re.compile(r"\S\s+-\s+\S.*\S\s+-\s+\S")
# A year or a short bare number opening the continuation: `1716 when a ...`.
YEAR_RE = re.compile(r"^\s*\d")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*$")
# A hyphenated fragment: `manu-`, `Muzaf-`. Not ` -` (a quote intro) and not
# an em/en dash.
HYPHEN_TAIL_RE = re.compile(r"[A-Za-z]{2}-$")

# --- entry boundaries that imitate a cut sentence ----------------------------
# A `\n\n` inside the footnote apparatus, the officers masthead or a numbered
# bibliography is a real entry boundary. The tails that prove a cut -- a comma,
# a preposition -- occur inside those entries as often as in prose, so the
# strict rules fire on them anyway; these shapes are how the text itself shows
# the gap is structural. Collapsing one runs two entries into one paragraph.

# A footnote marker pdfmd read as punctuation -- `^`, `°`, `©`, a superscript
# digit -- behind the quotes and asterisks it also invents around it:
# `"^ Yet another document`, `*'^* Obverse figure`, `© Pakhomov: Coins of`.
NOTE_MARKER_RE = re.compile(r"^[\s\"'*_\\\[({]{0,6}[\^°©¹²³⁰⁴⁵⁶⁷⁸⁹]")
# A note number opening a block, followed by the capital that starts the
# note's text: `8 For illustrations`, `52Album 1976`, `5 Bombay Consultations`.
# The capital is what separates a note from a number that merely continues the
# sentence above -- `100 pieces of "Borneo iron bullet money"` and `15 to 20
# minutes duration` go on reading as prose, and a four-digit year (`1996 And,
# finally`) is not a note number at all.
NOTE_NUM_RE = re.compile(r"^\s*\d{1,3}(?:\s+|(?=[A-Z]))[A-Z]")
# Two or more `Label:` groups in one line -- the officers masthead and the
# subscription block, which pdfmd runs together (`Annual Subscription Ds:
# £6.00 ... South Asia: Mr. P. P. Kulkarni,`). `restructure-flattened-md`
# owns the shape; the blank lines inside it are entry boundaries.
LABEL_RUN_RE = re.compile(r"[A-Z][A-Za-z.&'\- ]{2,24}:(?=\s)")
# `*General*: Mr. R. Senior,` / `*Europe*: Mr. J. Lingen,` -- the masthead and
# the hoard indexes run one entry per line, each closing on the comma that
# would otherwise prove a cut.
ENTRY_LABEL_RE = re.compile(r"^\s*[*_]{0,2}[A-Z][A-Za-z.&'\- ]{0,34}[*_]{0,2}\s*[*_]{0,2}:\s")
# A coin-description field opening the continuation: `Rev. Temple containing
# Sankh shell`, `*reverse -* the coins of type C`. The catalogue prints obverse
# and reverse as separate lines, so the blank line between them is the layout,
# not a cut -- and the field name is a noun, so the line above it ends on one.
CATALOGUE_FIELD_RE = re.compile(
    r"^\s*[*_]{0,2}(Obv|Rev|Obverse|Reverse|Margin|Exergue"
    r"|Weight|Wt|Dia|Diameter|Metal)\b", re.I)


def is_prose(line):
    """True when the line is body text -- not structure pdfmd or a sibling
    skill owns (headings, tables, figure markers, comments, IALs, the
    `[Original PDF]` header)."""
    s = line.strip()
    if not s:
        return False
    if HEADING_RE.match(line) or IAL_RE.match(line) or FENCE_RE.match(line):
        return False
    if s.startswith("|") or s.startswith("<!--") or s.startswith("["):
        return False
    if s.startswith("*[") or s.startswith("---"):
        return False
    return True


def strip_closers(text):
    return text.rstrip().rstrip(CLOSERS).rstrip()


def heading_like(line):
    """True when the line reads as a heading pdfmd marked with emphasis
    instead of `#` -- `**3.** ***Nandipada*** **Type**`.

    Short, no comma, and no terminal punctuation. Only used to suppress the
    weaker rules: a heading does not end on `and` or `of` either, so the
    function-word rule stays in force above this.
    """
    bare = re.sub(r"[*_]", "", line).strip()
    if not bare or len(bare) > 60:
        return False
    return "," not in bare and not bare[-1] in TERMINAL


def bold_title_continuation(nxt):
    """True when the continuation opens on an emphasis-marked title rather
    than on prose resuming -- `**Table 1. Obverse and Reverse Combinations**`
    under a paragraph cut at `both from`. pdfmd marks these titles with `**`
    instead of `#`, so `is_prose` lets them through and the function-word rule
    above claims the gap. Only the *first* span is tested: a prose
    continuation does not open on a bold heading.
    """
    m = re.match(r"\s*\*\*(.+?)\*\*(.*)$", nxt)
    if not m or not heading_like(m.group(1)):
        return False
    span, rest = m.group(1), m.group(2).lstrip()
    # A title opens on a capital or a number. `**period prior to the**
    # Arakanese era` is emphasised prose, and the sentence above it really
    # was cut.
    if not (span[:1].isupper() or span[:1].isdigit()):
        return False
    # Prose resuming after an emphasised phrase carries on in lower case --
    # `**The phases** of coin circulation`, `**1203** to **1215 / 1785**`.
    # A title is followed by the next title, or by nothing.
    if rest[:1].islower():
        return False
    return True


def ends_terminally(text):
    """True when the line ends the way a paragraph legitimately ends."""
    core = strip_closers(text)
    if not core:
        return True
    if core[-1] in TERMINAL:
        return True
    # `He writes: -` / `He writes: —` -- a dash set off by a space introduces
    # the quoted block below it, so the break after it is real.
    if core[-1] in "-–—" and (len(core) < 2 or core[-2] == " "):
        return True
    return False


def last_word(text):
    m = WORD_RE.search(strip_closers(text))
    if not m:
        return ""
    word = m.group(0)
    # A lone capital ends a variety label, a series letter or an initial
    # (`as in Variety A`, `{BN, series 6 A)`, `Tarzhima A`), never the article
    # `a` -- and `a` is the only one-letter member of FUNCTION_TAILS.
    if len(word) == 1 and word.isupper():
        return ""
    # An all-capitals token is a legend fragment, a mint name or an acronym,
    # never the function word it lowercases to -- `**KRMAN-AN**` is not the
    # article, and `*A spec IS*` is not the copula.
    if len(word) > 1 and word.isupper():
        return ""
    # `May` with a capital is the month. Of the corpus's seven, four were an
    # index column of month abbreviations or a date heading above a
    # programme, where collapsing the break ran two unrelated rows together;
    # the two genuine ones (`by the end of May` + `1739`) are the price of
    # not making those four.
    if word == "May":
        return ""
    # A letter a digit runs straight into is a type label, not a word at all:
    # `this one is Type 1a` ends on `1a`, and reading its `a` as the article
    # claimed the paragraph had been cut.
    if m.start() > 0 and strip_closers(text)[m.start() - 1].isdigit():
        return ""
    return word.lower()


def blocks(lines):
    """(start, end) line indices for each run of consecutive prose lines.

    A run ends at a blank line or at any non-prose line, so a gap that spans
    a figure marker, a table or a comment is never read as a severed
    paragraph -- only a gap of pure blank lines between two prose runs.
    """
    out, start = [], None
    for i, l in enumerate(lines):
        if is_prose(l):
            if start is None:
                start = i
        elif start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(lines) - 1))
    return out


def gap_is_blank(lines, a, b):
    return all(lines[k].strip() == "" for k in range(a + 1, b))


def lone_bullet(lines, i, end):
    """True when the bullet at line i has no sibling bullet in its block --
    a real list has more than one item, OCR residue stands alone."""
    for k in range(i + 1, end + 1):
        if BULLET_RE.match(lines[k]):
            return False
    return True


def is_entry_boundary(prev, nxt):
    """True when the blank line separates two entries of the footnote
    apparatus, the masthead or a numbered bibliography -- a real boundary that
    the cut-sentence rules would otherwise claim."""
    if NOTE_MARKER_RE.match(nxt):
        return True
    # The continuation opens a numbered note, so it is the apparatus starting
    # rather than the sentence resuming -- wherever the real continuation went,
    # it is not here, and collapsing would run prose into a footnote.
    if NOTE_NUM_RE.match(nxt):
        return True
    if ENTRY_LABEL_RE.match(prev) and ENTRY_LABEL_RE.match(nxt):
        return True
    if len(LABEL_RUN_RE.findall(prev)) >= 2 or len(LABEL_RUN_RE.findall(nxt)) >= 2:
        return True
    if CATALOGUE_FIELD_RE.match(nxt):
        return True
    if bold_title_continuation(nxt):
        return True
    return False


def scan(path, loose=False):
    lines = path.read_text(encoding="utf-8").split("\n")
    runs = blocks(lines)
    findings = []  # (line_no, severity, label, message)

    for (s1, e1), (s2, e2) in zip(runs, runs[1:]):
        if not gap_is_blank(lines, e1, s2):
            continue
        prev, nxt = lines[e1], lines[s2]
        gap_line = e1 + 2  # 1-based line number of the blank line itself

        if OL_RE.match(nxt) or LETTER_OL_RE.match(nxt):
            continue  # a numbered or lettered list, not a continuation

        if is_entry_boundary(prev, nxt):
            continue

        tail = last_word(prev)
        terminal = ends_terminally(prev)

        if HYPHEN_TAIL_RE.search(strip_closers(prev)) and nxt[:1].islower():
            findings.append((
                gap_line, "ERROR", "hyphen-split",
                f"word split across the break: {prev.strip()[-32:]!r} + "
                f"{nxt.strip()[:32]!r} -- join into one word, no space"))
            continue

        if (not terminal and BULLET_RE.match(nxt)
                and lone_bullet(lines, s2, e2)
                and not JUNK_MARKER_RE.match(nxt)
                and not FLATTENED_RE.search(nxt)
                and not heading_like(prev)):
            marker = BULLET_RE.match(nxt).group(1)
            findings.append((
                gap_line, "ERROR", "fake-list",
                f"`{marker} ` after the break renders as a bullet and "
                f"interrupts the paragraph: {prev.strip()[-32:]!r} + "
                f"{nxt.strip()[:40]!r} -- read the marker off the scan, then "
                f"see whether the break is a cut sentence or a real boundary"))
            continue

        if not terminal and tail in FUNCTION_TAILS:
            findings.append((
                gap_line, "ERROR", "severed",
                f"line ends on {tail!r}, which cannot end a sentence: "
                f"{prev.strip()[-40:]!r} + {nxt.strip()[:32]!r}"))
            continue

        if not terminal and strip_closers(prev).endswith((",", ";")):
            findings.append((
                gap_line, "ERROR", "severed",
                f"line ends mid-clause on a comma: {prev.strip()[-40:]!r} + "
                f"{nxt.strip()[:32]!r}"))
            continue

        if not terminal and nxt[:1].islower():
            findings.append((
                gap_line, "ERROR", "severed",
                f"continuation starts lowercase, which cannot begin a "
                f"paragraph: {prev.strip()[-40:]!r} + {nxt.strip()[:32]!r}"))
            continue

        if heading_like(prev):
            continue  # an emphasis-marked heading, not a cut paragraph

        if loose and not terminal and YEAR_RE.match(nxt):
            findings.append((
                gap_line, "WARN", "maybe-severed",
                f"continuation starts on a bare number -- a severed clause, or "
                f"a year opening a new sentence? {prev.strip()[-40:]!r} + "
                f"{nxt.strip()[:32]!r}"))
            continue

        if loose and not terminal:
            findings.append((
                gap_line, "WARN", "maybe-severed",
                f"no terminal punctuation, capitalised continuation -- a real "
                f"paragraph break or an untagged heading? "
                f"{prev.strip()[-40:]!r} + {nxt.strip()[:32]!r}"))

    return findings


def sub_rule(label, msg):
    """Which of the three `severed` tests fired, by the reason it reports.

    They are one label in the report but three different claims, and a
    corpus sweep measured them wildly apart: the function-word tail is
    ~97% precise, the comma tail ~63%, the lower-case continuation ~29%.
    `fix` takes only the first by default, so the weak two cannot ride
    along with the strong one.
    """
    if label != "severed":
        return label
    if msg.startswith("line ends on"):
        return "tail"
    if msg.startswith("line ends mid-clause on a comma"):
        return "comma"
    return "lower"


DEFAULT_FIX_RULES = ("tail", "hyphen-split")


def fix(path, rules=DEFAULT_FIX_RULES):
    """Collapse the blank line for the mechanically-safe findings."""
    findings = scan(path, loose=False)
    safe = {n for n, _, lab, msg in findings if sub_rule(lab, msg) in rules}
    refused = [(n, sub_rule(lab, msg)) for n, _, lab, msg in findings
               if sub_rule(lab, msg) not in rules]
    if not safe:
        print(f"{path}: nothing to collapse")
    else:
        lines = path.read_text(encoding="utf-8").split("\n")
        # Drop the blank lines bottom-up so earlier indices stay valid.
        for n in sorted(safe, reverse=True):
            idx = n - 1
            if lines[idx].strip() == "":
                del lines[idx]
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"{path}: collapsed {len(safe)} break(s) at "
              f"{', '.join(str(n) for n in sorted(safe))}")
    why = {
        "fake-list": "needs the dash read off the scan before the break can "
                     "be collapsed",
        "comma": "a comma tail is a real paragraph end about a third of the "
                 "time (an OCR'd full stop) -- decide this one by eye",
        "lower": "a lower-case continuation is usually a catalogue field, "
                 "not prose resuming -- decide this one by eye",
    }
    for n, lab in refused:
        print(f"{path}:{n}: left for you -- {lab} "
              f"{why.get(lab, 'is not in the requested rule set')}")
    return 1 if refused else 0


def resolve(arg):
    path = Path(arg)
    if not path.exists() and "/" not in arg and not arg.endswith(".md"):
        path = Path("jons") / f"{arg}.md"
    return path


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    loose = "--loose" in argv
    rules = DEFAULT_FIX_RULES
    for a in argv[1:]:
        if a.startswith("--rules="):
            rules = tuple(x for x in a.split("=", 1)[1].split(",") if x)
    if len(args) < 2 or args[0] not in ("scan", "fix"):
        print(__doc__)
        return 2

    mode, targets = args[0], args[1:]
    rc = 0
    for arg in targets:
        path = resolve(arg)
        if not path.exists():
            print(f"no such file: {path}")
            rc = max(rc, 2)
            continue

        if mode == "fix":
            rc = max(rc, fix(path, rules))
            continue

        findings = scan(path, loose=loose)
        if not findings:
            if len(targets) == 1:
                print(f"{path}: clean")
            continue
        rc = max(rc, 1)
        findings.sort()
        for n, sev, label, msg in findings:
            print(f"{path}:{n}: {sev}  [{label}] {msg}")

    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
