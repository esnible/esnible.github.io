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
                      cases land here. `cut_tail` reads the tail three ways:
                      the word itself, the word the OCR garbled (`Coins of
                      Kirman ot` + `78 bear the names`, ONS_171, where `ot`
                      is `of` and the rule could not see it), and the last
                      *two* words where one alone proves nothing (`his
                      vocation was not` + `'pure' archaeology`, ONS_171 --
                      `not` ends sentences, `was not` does not).
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
  * `fake-ol`      -- the same defect one character over: the text after the
                      break starts `1252. `, so kramdown renders an ordered
                      list and the paragraph is interrupted by a number that
                      is really a page or a year in the citation the break
                      cut (`(Kochnev 1997, 282/1248,` + `1252. And it was
                      ...`). Two guards used to hide these. This script
                      skipped every `N.` continuation outright, on the sound
                      ground that it is usually a real list; and
                      `fix_list_starts.rb` stamps the false list with
                      `{: start="1252"}`, which `is_prose` rejects, so the
                      gap stopped being pure blank and the pair never reached
                      a rule at all. `fake_ol()` earns the finding instead of
                      skipping it -- see its docstring for the tests a
                      finding has to pass and the corpus numbers.
                      Reported, never fixed.
  * `hyphen-split` -- the line ends on a hyphenated fragment and the line
                      below carries on the same token, so the halves join
                      into one with no space. Two shapes qualify: a word cut
                      at its hyphen continuing in lower case (`manu-` +
                      `facture`), and a *number* range cut at its dash
                      continuing in digits (`the Yemen 1006-` + `1054H`,
                      ONS_111). The numeric half is certain rather than
                      probable: a range's two ends cannot sit in different
                      paragraphs, and all 78 in the corpus are dates, page
                      ranges, weights or catalogue numbers.
  * `hyphen-cap`   -- the same cut, but the continuation is capitalised:
                      `pre-` + `Islamic`, `Rukn al-` + `Dunia`, `Arab-` +
                      `Byzantine`. Usually a hyphenated compound or a name,
                      and 39 of them across 28 files -- but about one in
                      twelve is not. The three in the corpus that are not
                      show the shapes to watch: a heading glued below the
                      cut (`number XVII-` + `A Copper Paisa from Kangra by
                      ...`), OCR noise standing where a word was (`IT-` +
                      `Finally`), and a fragment whose completion the OCR
                      lost altogether (`the mono-` + `For the standard`).
                      Reported, never fixed.
  * `paren-split`  -- the line leaves a bracket open and the continuation
                      opens with the matching closer: `... of the same date
                      (AH` + `1200/Ry.4). The coin shows ...` (ONS_109).
                      Alone among these rules the proof is mechanical rather
                      than a judgement about English -- a paragraph cannot
                      end inside a parenthesis, and a continuation cannot
                      begin by closing one that was never opened. The two
                      halves have to agree, which is what keeps a dropped
                      `)` elsewhere in the file out of it. `fake-list` keeps
                      precedence over this rule: a `- ` continuation renders
                      as a bullet whether or not the blank line goes, so the
                      bracket evidence must not route it to `fix`.
                      A `[` or `]` with letters hard against it on both
                      sides is read through first: it is OCR garble for a
                      letter, not punctuation (`Khari\\]ite` for
                      `Kharijite`), and left standing it makes the line's
                      bracket count untrustworthy so the rule stands down.
                      That is what hid ONS_171's `(Tabari` + `II.647 = tr.
                      XXI.8),` -- a textbook `paren-split` sixty characters
                      down the line from the garble that blinded it.
  * `margin-cut`   -- the line above runs to the column margin. Every rule
                      here but this one proves the cut from the words at the
                      break; this one proves it from the shape of the page,
                      and needs no English at all. A paragraph's last line
                      stops where the sentence stopped; a line pdfmd cut
                      stops where the column did. Where a page was read one
                      physical line to a block -- ONS_171's lines 18-82 run
                      47 to 68 characters while the rest of the file runs
                      200 to 950 -- a `\\n\\n` carries no information and this
                      is the only evidence there is. Measured against the
                      second OCR of ONS_171 it called all twelve breaks in
                      that region right, six cuts and six real boundaries.
                      Corpus-wide it is 624 findings in 135 files, median 2
                      to a file, and a read of 42 of them found 13 cuts --
                      42% once `attributed_entry` has taken the contents
                      lists out, which is still why this is WARN, not ERROR,
                      and never fixed. What is left to get wrong is mostly
                      the glued heading, which is one more reason to run
                      `restore-headings` first: a heading pdfmd left in the
                      body reaches the margin exactly as a cut line does.
  * `paren-far`    -- the same shape, but the bracket closes more than
                      `PAREN_SPAN` characters from where it opened. Corpus-
                      wide, 363 of the 370 are under that and read as one
                      citation or gloss; the seven above it are a stray `)`
                      closing a `(` the OCR dropped half a page earlier, and
                      four of those seven are two unrelated paragraphs.
                      Reported, never fixed.

A line ending in `.`, `!`, `?` or `:` is never flagged (`paren-split`
included: an open bracket is strong evidence, but a line that both closes its
sentence and leaves a bracket hanging has lost a `)` to the OCR, which is
`fix-ocr`'s business, not a severed paragraph). A paragraph may well
end there, and nothing in the text can tell a real boundary from a cut one,
so those stay invisible to this script by design.

`margin-cut` keeps that rule, and it is the one place where keeping it has a
measured cost. A full stop the OCR read for a comma hides a cut behind
terminal punctuation -- ONS_171's `he moved to Tashkent.` + `Uzbekistan. to
continue his studies` is a cut whose line runs to 60 of a 63-character
column, and the margin would have caught it. Letting terminal tails through
adds 798 corpus findings, and a read of them is mostly paragraphs that ended
where they should: in justified prose, a line that ends a sentence near the
margin is the commonest thing on the page. So the cost stays unpaid.

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
`fake-list` needs the dash decided by eye against the PDF, `fake-ol` needs the
number read and its `{: start=}` IAL deleted along with the break, and
`--loose` findings need a human to say whether the paragraph break is real, so
`fix` refuses all three and says so.

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

# A function word the OCR garbled, so the tail test above cannot see it.
# Deliberately tiny. The wider table this started as was a mistake: `m` ->
# `in` fires on every transliterated name the corpus ends a line with
# (`Ibrahīm`, `Karīm`, `qrīm`), and `lor` -> `for` on the acronym `IOR`.
# What is left is the one substitution that cannot be anything else -- `f`
# read as `t`, `l` or `i` -- on a two-letter token that is not an English
# word. Corpus-wide it adds three findings and all three are cuts
# (ONS_171's `Coins of Kirman ot` + `78`, ONS_173's `(Asiatic Society ot` +
# `Bangladesh)`, ONS_179's `the old exchange rate ot` + `160 old pice`).
OCR_TAILS = {"ot": "of", "ol": "of", "oi": "of"}

# `not` stays out of FUNCTION_TAILS because sentences end on it all the time
# (`whether the mint was Dar al-Islam or not`). After an auxiliary it cannot:
# `was not`, `do not`, `had not` all still owe a complement. The pair is the
# discriminator, not the word, which is why this needs the last *two* words.
NEGATED_AUX = {
    "is", "are", "was", "were", "be", "been", "being", "am", "has", "have",
    "had", "does", "did", "do", "will", "would", "shall", "should",
    "may", "might", "must", "can", "could",
}

# Trailing marks that close a sentence without ending the line's last token:
# quotes, brackets, emphasis, and the superscript footnote digits this corpus
# prints after a cited name (`Raymond²`).
CLOSERS = "\"'’”»)]}*_¹²³⁰⁴⁵⁶⁷⁸⁹"
TERMINAL = ".!?:"

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
FENCE_RE = re.compile(r"^\s*```")
IAL_RE = re.compile(r"^\s*\{:")
# `{: start="1252"}` -- what `fix_list_starts.rb` writes above an ordered list
# that does not begin at 1. On a false list it is the stamp of the defect, and
# because `is_prose` rejects every `{:` line it also *hides* it: the IAL ends
# the prose run, so the gap below a severed citation is no longer pure blank
# and the pair never reaches a rule. Read through it, for `fake-ol` only.
START_IAL_RE = re.compile(r"^\s*\{:\s*start=\"\d+\"\}\s*$")
BULLET_RE = re.compile(r"^\s{0,3}([-*+])\s+\S")
OL_RE = re.compile(r"^\s{0,3}\d{1,9}[.)](\s|$)")
# The ordered marker kramdown actually honours: digits, a full stop, a space.
# `1)` is not a list marker in kramdown (see `restore-lists`), so a `N)`
# continuation cannot be a false list -- it renders as the prose it is.
OL_DOT_RE = re.compile(r"^\s{0,3}(\d{1,9})\.(?:\s|$)")
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
# The same cut through a number: `1006-`, `pp. 109-`, `13.12-`.
NUM_TAIL_RE = re.compile(r"\d-$")
# A month name ending the line, for `fake-ol` alone: `... issued on 20 December`
# + `1999. Circulating coins ...`. A month cannot end a sentence when the next
# thing is a four-figure year, which makes this the one cut `fake-ol` proves
# mechanically rather than by judgement about English. `May` is the only
# ambiguous name (`the date may` + `1983. ...`) and FUNCTION_TAILS already
# holds it, so the function-word test claims those before this one is reached.
MONTH_TAIL_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September"
    r"|October|November|December)$", re.I)
BRACKETS = {"(": ")", "[": "]", "{": "}"}
BRACKET_CHARS = set(BRACKETS) | set(BRACKETS.values())
# A square bracket a word runs straight through -- `Khari\]ite`, `Ibn al]Athir`
# -- is the OCR's reading of a letter, not punctuation. pdfmd escapes the
# bracket because Markdown would otherwise take it for link syntax, and the
# backslash is optional here only because the escaping is not always applied.
# Round brackets are deliberately not read through: `D (ii)l` and `(1)41` are
# real labels in this corpus whose closer a letter or digit follows, and
# masking those *invents* an unclosed opener (ONS_166, ONS_192).
GARBLE_BRACKET_RE = re.compile(r"(?<=[A-Za-z])(\\?)[\[\]](?=[A-Za-z])")
# How long a parenthesis may run, opener to closer, and still read as one.
# What this corpus brackets across a line break is a citation (`(Kochnev` +
# `1997, 279-281)`), a date, or a legend's translation -- 368 of the 376
# corpus findings measure under 250 characters end to end. Above it the
# pattern is a stray `)` well down the page closing a `(` the OCR dropped
# half a paragraph earlier, so the two halves have nothing to do with
# each other.
PAREN_SPAN = 250

# --- the column margin -------------------------------------------------------
# Every rule above proves the cut from the *words* at the break. Where pdfmd
# read a page one physical line to a block, there is a second proof that needs
# no English at all: a paragraph's last line stops where the sentence stopped,
# and a line pdfmd cut stops where the column did. So a block whose last line
# reaches the right margin was not ended by its author.
#
# `W`, the column width in characters, is read off the file rather than
# assumed -- the corpus runs from typewritten single columns to printed
# three-column pages. It is the *mode* of the nearby line lengths, not a
# percentile: in a line-per-block region almost every line is full-width by
# construction, so the mode is the margin, while a percentile is dragged up by
# the blocks where pdfmd did join two lines.
MARGIN_W_MIN, MARGIN_W_MAX = 35, 110
MARGIN_WINDOW = 40      # prose lines either side to estimate W over
MARGIN_SAMPLES = 10     # below this there is no column to speak of
MARGIN_FULL = 0.80      # how near the margin counts as reaching it
# Above this the line is two physical lines pdfmd joined, and the measurement
# stops meaning anything: W carries about a character of slack per line, so by
# the fifth the error is most of a word. ONS_171's `pre-eminent specialist in
# mediaeval` + `Central Asian numismatics` is a real cut on a 121-character
# line, and it is out of reach here for exactly that reason.
MARGIN_SCOPE = 1.35

# What a line has to look like before the margin is allowed to speak for it.
# The signal is sound but the corpus is full of regions where a line per block
# is the *real* structure -- contents lists, bibliographies, plates, catalogue
# rows of weights and die axes -- and there the margin proves nothing. Ungated
# the rule reports 5723 breaks and is unusable; gated it reports 704.
MARGIN_MIN_WORDS = 7
MARGIN_MAX_NUMBERS = 3
NUMBER_TOKEN_RE = re.compile(r"\d[\d.,/-]*")
PLAIN_RE = re.compile(r"<!--.*?-->")

# The one shape `running_prose` cannot throw out, and two thirds of what the
# margin rule got wrong before this: the newsletter contents list and the
# article byline. Both are a title that runs the full width of the column and
# closes on who wrote it, so every test above passes and the line below --
# the next title, or the article itself -- reads as the sentence resuming.
#
# `NAME` is a Unicode letter class, not `[A-Za-z]`: the corpus attributes to
# `Ludovic Liétard` and `Möngke Qaan` as readily as to `R. C. Senior`.
_NAME = r"[A-Z][^\W\d_]*\.?"
# `by R. C. Senior`, `by Dr Russel Haque`, `by Russel Haque & Nicholas Rhodes`,
# `by M. Fedorov 16` (the contents page number trails the name). Two name
# tokens are required, which is what keeps an ordinary cut mid-sentence out:
# `a paper published by John` + `Smith in 1980` offers only one.
BY_AUTHOR_RE = re.compile(
    rf"\bby\s+{_NAME}(?:\s+(?:&|and|{_NAME}))+\s*\d{{0,4}}[.,]?$")
# `(I. Paghava)`, `(A. Akopyan)`, `(with S. Godbole)`. An initial with its stop
# is required: a bare `(Glenn)` is how ONS_184's obituary runs a maiden name
# into the surname below it (`Sister Susan (Glenn)` + `Benton and children`),
# and that is a cut.
PAREN_AUTHOR_RE = re.compile(
    r"\(\s*(?:with\s+)?(?:[A-Z]\.\s*)+[A-Z][A-Za-z'’-]+\s*\)[.,]?$"
    r"|\(\s*with\s+[A-Z][A-Za-z.'’-]*(?:\s+[A-Z][A-Za-z.'’-]*)*\s*\)[.,]?$")
# `Warden, W. B. jr., A short note ...`, `Schjoth, Fr., The currency of ...`.
# Surname, comma, *initial with a stop* -- the abbreviation is what makes this
# a bibliography entry rather than prose. Without it the rule would claim
# ONS_203's `Mudra, Vol. I, Coin` + `Study Circle, Calcutta`, which is a cut.
BIBLIOGRAPHY_START_RE = re.compile(
    r"^\s*[A-Z][A-Za-z'’-]+,\s+(?:[A-Z]\.|[A-Z][a-z]{1,3}\.)")

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

    Three asterisks count as well. pdfmd marks a run-in head `***Reviews***`
    as readily as `**Reviews**`, and reading the inner pair as the emphasis
    left the span starting on a `*`, which failed the capital test below and
    let the title through as prose (ONS_163).
    """
    m = re.match(r"\s*(\*{2,3})(.+?)\1(.*)$", nxt)
    if not m or not heading_like(m.group(2)):
        return False
    span, rest = m.group(2).strip("*_ "), m.group(3).lstrip()
    if not span:
        return False
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
    # A letter something else runs straight into is not a word at all, and
    # WORD_RE will have sliced it out of the middle of one. Two ways that
    # happens: a digit, where `this one is Type 1a` ends on `1a` and reading
    # its `a` as the article claimed the paragraph had been cut; and a letter
    # outside ASCII, where the regex cannot start the match on it, so a
    # transliteration comes back as its own last syllable -- `Ibrahīm` as
    # `m`, `MamünT` as `nt`, `Karīm` as `m`. The corpus ends lines on those
    # names constantly, and the fragments are exactly the shapes `OCR_TAILS`
    # would otherwise repair into function words.
    if m.start() > 0 and strip_closers(text)[m.start() - 1].isalnum():
        return ""
    return word.lower()


def mask_garble(text):
    """Blank out bracket characters that are OCR garble for a letter.

    Two tests, and the second one matters as much as the first. A square
    bracket a word runs through is garble *only if nothing in the line
    answers it*: `kidara kusha\\[na\\]/ ala` (ONS_230) is a scholarly
    restoration whose `[` also has letters hard against it, and masking the
    opener alone orphaned the closer and stood the rule down on a break it
    had been finding. So pair the brackets off first and read through the
    leftovers only.

    Length-preserving, so the offsets `opener_distance` and the `paren-far`
    span are measured in stay the offsets of the real line.
    """
    stack, matched = [], set()
    for i, ch in enumerate(text):
        if ch in BRACKETS:
            stack.append(i)
        elif ch in BRACKETS.values() and stack:
            if BRACKETS[text[stack[-1]]] == ch:
                matched.add(stack.pop())
                matched.add(i)
    out = list(text)
    for m in GARBLE_BRACKET_RE.finditer(text):
        i = m.end() - 1
        if i not in matched:
            out[i] = "x"
    return "".join(out)


def cut_tail(text):
    """The tail that proves this line was cut mid-clause, or `''`.

    Three readings, in order of how directly the proof sits on the page:
    the last word is a function word; it is a function word the OCR garbled;
    or the last *two* words are a pair that cannot close a sentence even
    though the final one could on its own. Returns the phrase to report.
    """
    word = last_word(text)
    if word in FUNCTION_TAILS:
        return repr(word)
    if OCR_TAILS.get(word) in FUNCTION_TAILS:
        return f"{word!r} (OCR of {OCR_TAILS[word]!r})"
    if word == "not":
        prior = re.findall(r"[A-Za-z][A-Za-z'’]*", strip_closers(text))[-2:]
        if len(prior) == 2 and prior[0].lower() in NEGATED_AUX:
            return repr(f"{prior[0].lower()} not")
    return ""


def unclosed_bracket(text):
    """The bracket this line leaves open, or `''`.

    A closer with nothing to match is OCR debris -- a dropped opener, or a
    `)` standing in for a footnote marker -- and makes the whole line's
    bracket count untrustworthy, so the rule stands down rather than guess.
    """
    stack = []
    for ch in text:
        if ch in BRACKETS:
            stack.append(ch)
        elif ch in BRACKETS.values():
            if not stack or BRACKETS[stack[-1]] != ch:
                return ""
            stack.pop()
    return stack[-1] if stack else ""


def opener_distance(text):
    """How far back from the end of the line the unclosed bracket sits."""
    stack = []
    for i, ch in enumerate(text):
        if ch in BRACKETS:
            stack.append(i)
        elif ch in BRACKETS.values() and stack:
            stack.pop()
    return len(text) - stack[-1] if stack else 0


def closes_bracket(nxt, closer):
    """True when the continuation's first bracket is the one `prev` left open.

    Requiring it to come *first* is what separates a cut sentence from a
    paragraph that merely happens to contain brackets of its own.
    """
    for ch in nxt:
        if ch in BRACKET_CHARS:
            return ch == closer
    return False


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


def gap_is_start_ial(lines, a, b):
    """True when the gap is blank lines plus exactly one `{: start="N"}`."""
    seen = 0
    for k in range(a + 1, b):
        if lines[k].strip() == "":
            continue
        if seen == 0 and START_IAL_RE.match(lines[k]):
            seen = 1
            continue
        return False
    return seen == 1


def lone_bullet(lines, i, end):
    """True when the bullet at line i has no sibling bullet in its block --
    a real list has more than one item, OCR residue stands alone."""
    for k in range(i + 1, end + 1):
        if BULLET_RE.match(lines[k]):
            return False
    return True


def lone_ol(lines, runs, j, n):
    """True when the ordered item opening block `j` has no sibling item.

    `lone_bullet` looks only inside the block, which is enough for a bullet
    list: kramdown keeps its items in one block. An ordered list in this
    corpus is routinely one item *per block* -- IS_010's footnotes 17, 19, 21
    are three blocks and render as three `<ol>`s -- so a sibling has to be
    looked for in the neighbouring blocks as well, and mid-line, since a
    flattened list carries `2.` inside the first item's text.
    """
    for k in (j - 1, j + 1, j + 2):
        if 0 <= k < len(runs):
            m = OL_DOT_RE.match(lines[runs[k][0]])
            if m and abs(int(m.group(1)) - n) <= 3:
                return False
    s, e = runs[j]
    for k in range(s, e + 1):
        for m in re.finditer(r"(?:^|\s\s)(\d{1,4})\.\s", lines[k]):
            if (k, m.start()) != (s, 0) and abs(int(m.group(1)) - n) <= 3:
                return False
    return True


def printed_width(line):
    """How wide the line sat on the page: its text without pdfmd's markup."""
    return len(PLAIN_RE.sub("", line).replace("*", "").replace("_", "")
               .replace("\\", "").strip())


def running_prose(line):
    """True when the line is running prose rather than a row of something.

    A contents entry, a bibliography line, a plate caption and a catalogue
    row all sit one to a block legitimately, and all of them reach the margin
    as readily as prose does. None of them survives all three tests.
    """
    text = PLAIN_RE.sub("", line)
    if "*" in text or "_" in text or "|" in text:
        return False
    if len(re.findall(r"[A-Za-z][A-Za-z'’-]+", text)) < MARGIN_MIN_WORDS:
        return False
    return len(NUMBER_TOKEN_RE.findall(text)) <= MARGIN_MAX_NUMBERS


def attributed_entry(prev, nxt):
    """True when the break is a contents entry, a byline or a bibliography
    line rather than a cut -- the shapes the margin cannot speak for."""
    text = PLAIN_RE.sub("", prev).rstrip()
    if BY_AUTHOR_RE.search(text) or PAREN_AUTHOR_RE.search(text):
        return True
    return bool(BIBLIOGRAPHY_START_RE.match(PLAIN_RE.sub("", nxt)))


def column_width(widths, lo, hi):
    """The modal printed width over `widths[lo:hi]`, or 0 if there is no column.

    `widths` is the full list of (index, width) for the file's prose lines;
    `lo`/`hi` bound the window in that list.
    """
    sample = [w for _, w in widths[lo:hi] if MARGIN_W_MIN <= w <= MARGIN_W_MAX]
    if len(sample) < MARGIN_SAMPLES:
        return 0
    return max(range(MARGIN_W_MIN, MARGIN_W_MAX + 1),
               key=lambda c: sum(1 for w in sample if c - 5 <= w <= c + 5))


def reaches_margin(width, w):
    """True when a single printed line of width `width` ran to the margin `w`."""
    if not w or width > MARGIN_SCOPE * w or width < 0.3 * w:
        return False
    return width / w >= MARGIN_FULL


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


def fake_ol(lines, runs, j, prev, nxt, gap_line, loose):
    """A severed citation whose continuation opens on a number kramdown reads
    as an ordered-list marker.

    The sibling of `fake-list`, and the same claim: the marker interrupts the
    paragraph whether or not the blank line is a real boundary, so the render
    is wrong either way and only the scan can say what the number is. The
    difference is that a `- ` continuation is never a real list in this corpus
    while `N. ` usually is, so this rule has to earn the finding:

      * the line above ends mid-clause. Four tails qualify, and the corpus
        splits almost evenly between the first three: a comma or semicolon
        (35), a function word (28), a number cut at its dash (28), and a
        month name with a four-figure year opening the continuation (8).
        The month tail is the only one of the four that is mechanical rather
        than a judgement about English -- `... issued on 20 December` +
        `1999. Circulating coins ...` cannot be a sentence that ended, since
        a date needs its year. A line that ends on `.`, `!`, `?` or `:` is
        passed over here as everywhere else in this script.
      * no sibling item sits beside it (`lone_ol`). A real list has a
        neighbour; a severed citation stands alone between two prose runs.
      * the number is not `1`. A list restarts at 1 and a running citation
        does not, and this one test is what separates the two: without it the
        rule reported ONS_169's `1. Triveni ...`, ONS_179's `1. The
        Bhagamoya Inscription` and ONS_200's `1. The palaeography ...`, every
        one of them a real list introduced by a comma or a semicolon. With
        it, the `1.` cases are held back for `--loose`.

    Measured over `jons/*.md`: of the ordered-marker continuations that reach
    this rule about two thirds pass straight over on terminal punctuation, and
    **99 findings survive in 40 files** (101 with `--loose`). 86 of the 99 are
    corroborated without reading anything -- 45 open on a number within 30 of
    one at the end of the line above (`271/1126-` + `1128.`), 36 on a year,
    5 on a lower-case word that cannot begin a paragraph -- leaving 13 for an
    eye, of which nine are as plain as the rest (`read the date on the coin
    as` + `1202.`, `Pp.89-` + `164.`).

    Never fixed, for three reasons visible in those 99. The number has to be
    read off the scan. The `{: start="N"}` above it has to go with the break,
    and this script's `fix` can only collapse a newline. And four findings are
    not a severed sentence at all: ONS_162's `28. Palmer 1993` is a real
    footnote item whose *previous* item was cut, so collapsing would glue two
    notes together; ONS_182's and OP_014's are garble; ONS_197's `83.` is
    another note boundary.
    """
    m = OL_DOT_RE.match(nxt)
    if not m or ends_terminally(prev) or heading_like(prev):
        return None
    n = int(m.group(1))
    core = strip_closers(prev)
    if core.endswith((",", ";")):
        why = "ends mid-clause on a comma"
    elif cut_tail(prev):
        why = f"ends on {cut_tail(prev)}, which cannot end a sentence"
    elif NUM_TAIL_RE.search(core):
        why = "ends on a number cut at its dash"
    elif MONTH_TAIL_RE.search(core) and 1400 <= n <= 2100:
        why = "ends on a month name and the continuation opens on a year"
    else:
        return None
    if not lone_ol(lines, runs, j, n):
        return None
    if n == 1 and not loose:
        return None
    severity, hedge = ("ERROR", "") if n != 1 else (
        "WARN", " -- but the marker is `1.`, where a real list would start")
    return (
        gap_line, severity, "fake-ol",
        f"`{n}. ` after the break renders as an ordered list and interrupts "
        f"the paragraph, whose line above {why}: {prev.strip()[-40:]!r} + "
        f"{nxt.strip()[:40]!r}{hedge} -- read the number off the scan "
        f"(usually a year or a page in the citation above), then see whether "
        f"the break is a cut sentence or a real boundary")


def scan(path, loose=False):
    lines = path.read_text(encoding="utf-8").split("\n")
    runs = blocks(lines)
    findings = []  # (line_no, severity, label, message)

    # Printed width of every prose line, in file order, for the margin rule.
    widths = [(i, printed_width(l)) for i, l in enumerate(lines) if is_prose(l)]
    width_at = {i: w for i, w in widths}
    order = {i: k for k, (i, _) in enumerate(widths)}

    for j, ((s1, e1), (s2, e2)) in enumerate(zip(runs, runs[1:])):
        blank_gap = gap_is_blank(lines, e1, s2)
        # A `{: start="N"}` in the gap is read through for `fake-ol` alone.
        # Every other rule ends in a collapsed newline, and collapsing one
        # here would have to delete the IAL too -- which `fix` cannot do.
        if not blank_gap and not gap_is_start_ial(lines, e1, s2):
            continue
        prev, nxt = lines[e1], lines[s2]
        gap_line = e1 + 2  # 1-based line number of the blank line itself

        if OL_RE.match(nxt) or LETTER_OL_RE.match(nxt):
            f = fake_ol(lines, runs, j + 1, prev, nxt, gap_line, loose)
            if f:
                findings.append(f)
            continue  # otherwise a numbered or lettered list, not a continuation

        if not blank_gap:
            continue

        if is_entry_boundary(prev, nxt):
            continue

        tail_proof = cut_tail(prev)
        terminal = ends_terminally(prev)

        core = strip_closers(prev)
        if NUM_TAIL_RE.search(core) and nxt[:1].isdigit():
            findings.append((
                gap_line, "ERROR", "hyphen-split",
                f"number range split across the break: {prev.strip()[-32:]!r} + "
                f"{nxt.strip()[:32]!r} -- join, no space"))
            continue

        if HYPHEN_TAIL_RE.search(core) and nxt[:1].islower():
            findings.append((
                gap_line, "ERROR", "hyphen-split",
                f"word split across the break: {prev.strip()[-32:]!r} + "
                f"{nxt.strip()[:32]!r} -- join into one word, no space"))
            continue

        if HYPHEN_TAIL_RE.search(core) and nxt[:1].isupper():
            findings.append((
                gap_line, "ERROR", "hyphen-cap",
                f"hyphenated fragment, capitalised continuation: "
                f"{prev.strip()[-32:]!r} + {nxt.strip()[:32]!r} -- usually one "
                f"compound to join, but read it: a heading, OCR noise or a lost "
                f"completion looks the same"))
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

        mprev, mnxt = mask_garble(prev), mask_garble(nxt)
        opener = unclosed_bracket(mprev) if not terminal else ""
        if opener and closes_bracket(mnxt, BRACKETS[opener]):
            span = opener_distance(mprev) + mnxt.index(BRACKETS[opener])
            near = span <= PAREN_SPAN
            findings.append((
                gap_line, "ERROR", "paren-split" if near else "paren-far",
                f"{opener!r} is left open and the continuation closes it"
                + ("" if near else f", {span} characters away") + ": "
                f"{prev.strip()[-40:]!r} + {nxt.strip()[:32]!r}"))
            continue

        if not terminal and tail_proof:
            findings.append((
                gap_line, "ERROR", "severed",
                f"line ends on {tail_proof}, which cannot end a sentence: "
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

        # The margin rule, and it has to be reached before the heading bail
        # below: a full-width line in a narrow column is short enough that
        # `heading_like` claims it (ONS_171's `...in Rambam`, 55 characters
        # against a 63-character column, is a cut and reads as a title).
        # `running_prose` is what keeps real headings out instead -- they do
        # not run to seven words.
        if (not terminal and "<!--" not in prev
                and running_prose(prev) and running_prose(nxt)
                and not attributed_entry(prev, nxt)):
            k = order[e1]
            w = column_width(widths, max(0, k - MARGIN_WINDOW),
                             k + MARGIN_WINDOW + 1)
            if reaches_margin(width_at[e1], w):
                findings.append((
                    gap_line, "WARN", "margin-cut",
                    f"the line above runs to the {w}-character column margin "
                    f"({width_at[e1]} characters), so the page ended it and "
                    f"not its author: {prev.strip()[-40:]!r} + "
                    f"{nxt.strip()[:32]!r} -- read it: a contents entry or a "
                    f"glued heading reaches the margin too"))
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


DEFAULT_FIX_RULES = ("tail", "hyphen-split", "paren-split")


def fix(path, rules=DEFAULT_FIX_RULES):
    """Collapse the blank line for the mechanically-safe findings."""
    findings = scan(path, loose=False)
    safe = {n: sub_rule(lab, msg) for n, _, lab, msg in findings
            if sub_rule(lab, msg) in rules}
    refused = [(n, sub_rule(lab, msg)) for n, _, lab, msg in findings
               if sub_rule(lab, msg) not in rules]
    if not safe:
        print(f"{path}: nothing to collapse")
    else:
        lines = path.read_text(encoding="utf-8").split("\n")
        # Drop the blank lines bottom-up so earlier indices stay valid.
        for n in sorted(safe, reverse=True):
            idx = n - 1
            if lines[idx].strip() != "":
                continue
            del lines[idx]
            if safe[n] != "hyphen-split":
                continue
            # A hyphen join has to close up: leaving the halves on two lines
            # renders `1006- 1054H`, since Markdown makes a space of the
            # newline. Every other rule wants the soft break kept.
            if idx and idx < len(lines):
                lines[idx - 1] = lines[idx - 1].rstrip() + lines[idx].lstrip()
                del lines[idx]
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"{path}: collapsed {len(safe)} break(s) at "
              f"{', '.join(str(n) for n in sorted(safe))}")
    why = {
        "fake-list": "needs the dash read off the scan before the break can "
                     "be collapsed",
        "fake-ol": "needs the number read off the scan, and the `{: start=}` "
                   "IAL above it removed with the break -- which this `fix` "
                   "cannot do, since it only ever collapses a newline",
        "comma": "a comma tail is a real paragraph end about a third of the "
                 "time (an OCR'd full stop) -- decide this one by eye",
        "lower": "a lower-case continuation is usually a catalogue field, "
                 "not prose resuming -- decide this one by eye",
        "hyphen-cap": "a capitalised continuation after a hyphen is a compound "
                      "about eleven times in twelve; the twelfth is a glued "
                      "heading or a lost word, so read it",
        "margin-cut": "is evidence from the shape of the page rather than "
                      "from the words -- it says the line was cut, not that "
                      "the sentence was, so read it against the scan",
        "paren-far": "the bracket closes so far down that the two halves are "
                     "probably unrelated -- check the opener really belongs "
                     "to this sentence before collapsing",
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
