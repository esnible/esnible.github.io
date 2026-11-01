---
name: restore-headings
description: Find section headings that `pdfmd` folded into the body text of a `jons/` Markdown file, and headings it invented where the scan has none. Use when a file's headings render in the wrong place -- glued to the end of a paragraph, or missing their emphasis -- or when checking a file against its PDF for structure rather than for spelling or tables.
---

# Restoring headings `pdfmd` lost

The source PDFs are typewritten scans. A section head is set on its own line,
separated from the paragraphs around it by extra leading, and marked either by
underlining it with the typewriter's underscore key or by typing it in capitals.

`pdfmd` frequently loses the line break and the mark together. The head is
appended to the tail of the paragraph above it, so it renders mid-sentence:

```
... widens their appeal to students and collectors alike. Historical Summary
```

That is the failure this skill finds. It is **not** the flattened-table failure
`detect-missing-tables` screens for -- no table is involved, and the
escaped-pipe fingerprint never fires on it. A file can pass `screen` with
`nothing outstanding` and still have every heading in the wrong place.

```
detect_headings.py scan IS_001            # report, change nothing
detect_headings.py scan IS_001 -v         # include what the Markdown got right
detect_headings.py fix  IS_001            # rewrite the Markdown
detect_headings.py rows IS_001            # the findings a render has to settle
```

There is a **second screen** in this skill, `detect_section_heads.py`, which
asks a different question and needs no PDF. Two defects are invisible to
"find a line set apart on the page, then ask what the Markdown did with it":
a standing section head (`Lists Received`, `Other News`) glued into the
paragraph beside it, and a byline promoted to a heading (`# GPH`). See
"Two defects the set-apart question cannot reach", below. On a file whose
text layer is broken it is the only screen that works at all.

`scan` exits non-zero when there is something to fix.

`rows` writes `file<TAB>label<TAB>page<TAB>anchor` for the findings `fix`
will not apply on its own -- the unsafe splits, the heads the scan has and
the Markdown lacks, and the candidates the shape test found alone -- and
pipes straight into the shared sheet builder:

```
detect_headings.py rows ONS_120 | grep -v '^#' > rows.tsv
python3 .claude/skills/shared/crop_sheets.py sheets --rows rows.tsv --out ONS_120-head
```

One image for five findings instead of five renders. The rows carry their
own page, so a two-word head (`fig. 2`, `Beischlage`) is found by searching
that page rather than by matching words across the whole file.

`UNMATCHED` is left out of `rows` on purpose: its text matches no line of
the scan and is mostly not words, so no crop settles it. Those are a
flattened table's cells wearing a `#`, and they belong to
`restructure-flattened-md` -- which is most of what a catalogue-heavy file
reports. ONS_166 counts 95 such findings and 55 of them are that; the 40
left are what a render can decide. `--include-unmatched` crops them anyway.

## Why four signals

No single measurement decides. Each of these is necessary and none is
sufficient:

| Signal | What it means | Why it is not enough alone |
|:--- |:--- |:--- |
| **set apart (gap)** | clear space above *and* below, and the line stops short of the right margin | a short body line between two figures looks identical |
| **set apart (shape)** | no extra leading at all, but the three-line shape of a head: a short line, a paragraph's last line above it, a full-measure line below | about half of what it adds beyond the gap test is a head; the rest are run-in labels and closing notes |
| **underline** | a long contiguous ink run under the line's own x-extent, **minus** the same measurement taken in the margin to its right | a scan streak running clear across the page scores as high as a real underline |
| **capitals** | an all-capitals line | how these typewriters mark a head when they do not underline it (`NOTE`, `BIBLIOGRAPHY`) |
| **bold** | the OCR text layer flags the line's characters bold, end to end | some scans mis-tag a whole page's body text bold too, so this is only trusted where that is not happening (see below) |

Being set apart makes a line a *candidate*. An underline, capitals, or bold
makes a candidate a *head*. A candidate that is none of these wants the
paragraph break but no marker.

A line reaches candidacy by **either** route. The gap test is the stronger
evidence and is what `fix` acts on; the shape test exists because some heads
have no gap to find. ONS_109's `ONS News` and `Notes` sit flush in the text
block -- 9.1-11.5pt of leading against the 13.8pt the gap test wants -- on a
page whose text layer tagged nothing, so heading, body line and article title
all come back Times-Roman 9.0 with `bold=0.00`. Neither of the other signals
exists there; the shape is all that is left, and it is what a reader uses.

Because that evidence is weaker, **a candidate found only by shape is reported
but never written** without `--include-shape`. The report tags each finding
`[gap]` or `[shape]` so the difference is visible. Confirm a `[shape]` finding
against a render before applying it.

Its other effect is defensive, and is the reason to leave it on. A head the
gap test cannot see never reaches the PDF->Markdown pass, so a correct `##` in
the Markdown falls through to the Markdown->PDF pass, finds no head evidence,
and is reported `OVERSET` -- marker to be *removed*. Over six files the shape
test stopped two such removals, both verified on the page: ONS_130's
`More ONS News` (bold) and OP_017's `Class C` (underlined).

The pages carry no vector drawings (`get_drawings() == []`), so the underline is
found in pixels, the same way `detect_tables.py` finds ruling lines.

The margin control is the part that is easy to leave out and expensive to omit.
On IS_001 page 12 the line `September 1971` sits over a page-wide scan streak
and scores 0.37 under the text -- but 0.37 in the margin too. Real underlines
stop where the text stops: they score 0.90+ under the text against ~0.00 beside
it.

Bold is read straight off the span flags PyMuPDF reports for the OCR text
layer, not measured in pixels, so it needs no render and no DPI. Newsletters
from `ONS_131` on print heads in a bold proportional face with no underline at
all, which the underline test is structurally blind to -- it looks for ink
under the line, and bold prints none. Discovered the hard way: an earlier pass
ran `fix` across `ONS_130`-`139` without reading the report first, and because
every one of those headings is `OVERSET` under underline/capitals alone, `fix`
demoted nearly every section heading in all ten files to plain text before the
diff was caught and reverted. Bold closes that hole for the files it is
reliable on -- but see the reliability gate below; it is not reliable on
every file, and the discipline of reading `scan` before trusting `fix` still
applies.

Bold is not treated as self-evidently reliable, because it fails the same way
a scan streak fools the underline test: some pages' whole text layer comes
back bold, not just the heads on it. Before bold is used at all on a page, the
page's own long (10+ character), not-set-apart lines are checked -- if more
than `--bold-noise` (default 0.15) of them score over 50% bold, the page's
body text is bold too and the signal is switched off for every line on that
page, heads included, falling back to underline and capitals alone. Checked
across the first 40 PDFs in the archive, roughly a quarter of pages trip this
gate.

## Both directions, because each finds what the other cannot

| Direction | Verdict | Meaning |
|:--- |:--- |:--- |
| PDF → Markdown | `FOLDED` | the scan sets this head apart; the Markdown appended it to the paragraph above |
| | `FOLDED-PLAIN` | set apart but *not* marked as a head, and still appended |
| | `FLAT` | on its own line already, but with no marker |
| | `LOST` | a head with no counterpart in the Markdown at all |
| Markdown → PDF | `OVERSET` | the Markdown marks it as a head; the scan does not |
| | `UNMATCHED` | the Markdown marks it as a head, and its text matches no line of the scan at all |

Without the second direction, `## The attribution: and chronology of some of the
coins described in this` -- an ordinary sentence promoted to a heading, and cut
in half by the line break -- is invisible, because there is no set-apart PDF
line to start from.

`UNMATCHED` is what `OVERSET` cannot see: a heading that is not in the scan
at all. It is almost always garble -- a borderless table OCR'd one column at
a time, whose lines happened to start with `#` (`IS_020`'s catalogue became
`## Qa'itbay " " Reign 841-842 842-857 ...` and `#8 © EF EEE + Ww`). Headings
shorter than 4 letters (`## by`) are too short to match and are not reported.

A verdict may carry a suffix, and a suffixed verdict is **reported but never
applied** -- see "Splits that are refused" below.

`fix` repairs `FOLDED`, `FLAT`, and `OVERSET`. `UNMATCHED` is reported only and
counted as "to review", not "to fix": dropping the marker would leave the garble
behind, so it goes to `restructure-flattened-md` (a flattened table) or
`fix-ocr`. `LOST` is reported only: inserting
a head means choosing both its wording and its position, and the wording comes
from the garbled OCR layer (`B I B L I O G R A P H Y`). Read the render and add
it by hand. `FOLDED-PLAIN` needs `--include-plain`, because a wrong call there
puts a paragraph break into running text.

## Two defects the set-apart question cannot reach

Everything above starts from the scan: find a line **set apart on the page**,
then ask what the Markdown did with it. Two common defects are invisible to
that question, and `detect_section_heads.py` -- a second screen in this skill,
which needs no PDF -- is what finds them.

```
detect_section_heads.py scan ONS_152            # report, change nothing
detect_section_heads.py scan --all              # sweep jons/
detect_section_heads.py scan ONS_152 -v         # show the rejected matches too
detect_section_heads.py rows ONS_152            # the findings a render settles
detect_section_heads.py fix  ONS_152            # rewrite the Markdown
```

**A standing section head glued into a neighbouring block.** The newsletters
run the same section heads issue after issue -- `Lists Received`, `Other
News`, `Auction News`, `From the Editor`, `New and Recent Publications` -- and
`pdfmd` routinely glues one to the tail of the paragraph above it or to the
head of the bold run-in below it. `detect_headings.py` does not report these:
the Markdown line the head folded into matches the page's own head line only
in part, so the fuzzy match lands on the paragraph instead. On ONS_152 it
detected 23 set-apart lines and reported `FOLDED 1 OVERSET 8 LOST 7 OK 3`, and
not one finding was `Other News`, `Lists Received` or `Auction News`, all three
of which are plainly bold and set apart on that page.

**A byline promoted to a heading.** A short right-justified set of initials at
the foot of an article becomes an `# H1`: `# GPH` (ONS_152's conference
reporter), `# M.B.` (ONS_153's, Muriel Broome signing her husband's obituary).
The page *does* set those apart, so `detect_headings.py` matches them against
the Markdown's `# GPH`, finds a heading, and reports `OK`. It has no test for
the reverse error -- a line correctly read as set apart, but which is a byline
rather than a head. Seven other files set the same `GPH` as running text
(ONS_129's `...April 25-26, 1992. GPH`), which is what the rest of the corpus
does.

### Why a closed vocabulary instead of a measurement

These are the only two findings in the skill that need no render to detect,
and the reason is the vocabulary. `Lists Received` written that way, in this
corpus, is a section head; it is not a phrase that turns up in a sentence. So
the screen can work from the Markdown alone and reserve the render for
settling the handful of candidates it is not sure about.

That is only true of heads whose wording is distinctive. `Articles`, `Notes`,
`References`, `Introduction` and `Bibliography` are all common heads here too
and all deliberately **out** of the vocabulary: each is an ordinary English
word that appears in running prose ("the articles in this issue"), so no
casing or position test separates head from mention and the screen would be
mostly false positives. Those stay with `detect_headings.py`, where the
evidence is the page.

Three rules keep the vocabulary from turning into coincidence:

| Rule | What it drops |
|:--- |:--- |
| **head-casing** -- every significant word of the match starts with a capital | `he wrote many articles and several book reviews, mainly in Dutch`, `a short obituary was published by K. M. MacKenzie`, and the contents lines set in sentence case (`ONS news - meetings: Oxford, Leiden`) |
| **reject rules** | a head named rather than used (`found under "Members News" on page 2`), a contents entry (it ends in its page number, or carries dot leaders), and a bibliography's own sub-head, which puts the colon inside the emphasis run (`**Obituaries:**` among ONS_152's seven) -- a heading, but at `###` under the section it divides, not the newsletter's own section level |
| **position** | see below -- a cut is applied only where there is exactly one place to put it |

### Where the head sits decides the verdict

`prose` here means alphanumeric text outside the markup.

| Verdict | Shape | Cuts |
|:--- |:--- |---:|
| `GLUED-END` | prose before, nothing after, and the prose closes a sentence | 1 |
| `GLUED-RUNIN` | nothing before, prose after | 1 |
| `GLUED-BOTH` | prose both sides, head set off in an emphasis run of its own | 2 |
| `GLUED-HEADING` | already a heading, and it holds a second head after the first | 1 |

Reported, never applied:

| Verdict | Refused because |
|:--- |:--- |
| `GLUED-END-OPEN`, `GLUED-BOTH-OPEN` | the prose before the head does not close a sentence, so the cut may sever one. A real head does reach here -- `...at these meetings will be badly missed JL **Members News**` signs off with initials and no stop -- and so does a mid-sentence mention, so a render decides. |
| `GLUED-COMPOUND` | the head shares an emphasis run with the text after it, so the repair has to re-close the emphasis on both sides of the cut and then decide what the remainder is. Sometimes the remainder is a sub-head wanting promotion rather than un-emphasising: `**OBITUARY Dr Jarmila Štěpková (7.1.1926-12.10.1997)**`. |
| `GLUED-HEADING-JOINED` | two heads in one heading with a conjunction between them -- `## Lists Received and Auction News` -- where the scan may well print one combined head, and a cut leaves a dangling `and`. |
| `GLUED-END-INRUN` | the head ends the line, but the delimiter after it closes a run that opened earlier rather than one of the head's own. Taking it with the heading leaves that run unclosed and the rest of the file in bold: `**New Members** *UK Region European Region* **Revised Addresses Obituary**`. |
| `GLUED-MID` | prose both sides and no emphasis run around the head. Not the dead end it looks: sampled, about four in five are real, and most of those are the compound shape `GLUED-PAIR` now handles. What is left is a bibliography entry (`...issued 1984) KM Obituary Nun Pere, NI 17, 73 (1984)...`) or a contents listing the reject rules missed. |
| `BYLINE` | dropping the marker is a one-character edit, but deciding the line *is* a byline needs the page. `# AV` is as likely to be the metal as anyone's initials. |

`fix` writes the first four and nothing else. It makes **one cut per line**: a
second head on a line the first cut moved is re-screened on the next run,
against the text as it then stands.

### The byline shape, and the two shapes next to it

Dotted initials (`# M.B.`, `# B.N.H.`) are distinctive enough to stand alone.
Bare capitals (`# GPH`, `# SLG`) have exactly the shape of a catalogue's
column heads and rarity grades, so three further tests apply, and between them
they cut 249 candidates to 21:

- **vocabulary** -- the column heads (`REF`, `SIZE`, `MINT`, `AH`, `RY`, ...),
  the rarity grades (77 `RRR` headings and 57 `RR` across the corpus), the
  bibliography sigla, and the short all-capitals strings that are words rather
  than initials (`NEWS`, `NOTE`, `COIN`).
- **uniqueness within the file** -- a byline is a signature and appears once. A
  flattened table's cell text repeats; ONS_247 sets `RRR` as a heading dozens
  of times.
- **density within the file** -- above four bare-capital candidates the file is
  a catalogue, and every candidate in it is table debris. ONS_247 reports 54
  and ONS_245 52; ONS_152 and ONS_153 reported one each, and both were real
  bylines.

Two neighbouring shapes stay out of scope deliberately, because their fix is
different:

- **flattened table headers as headings** -- `# REF`, `# SIZE`, `# AH` and
  similar, around 120 of them concentrated in ONS_166 and ONS_174-ONS_219.
  They come from catalogue tables `pdfmd` flattened and belong to
  `restructure-flattened-md`.
- **bibliography sigla as headings** -- ONS_219 alone has eight (`HDSL`,
  `HYCD`, `MDBL`, `SHM`, `SSM`, `SZP`, `YCBS`, `YS`), the abbreviation keys of
  a reference list. Same visual shape as a byline, different fix.

### Settling the review findings

`rows` emits the three-column form, with no page -- this screen never opens the
PDF, so it does not know one, and `crop_sheets.py` then searches every page for
the anchor. That is what these findings want anyway: which page the line sits
on is part of the question.

```
detect_section_heads.py rows ONS_166 > rows.tsv
python3 .claude/skills/shared/crop_sheets.py sheets --rows rows.tsv --out ONS_166-sec
```

A `BYLINE`'s own text is two to four characters, far too little for a fuzzy
word match, so its anchor is the line above it -- the tail of the article the
initials sign.

### Checking the findings against the scan

Every one of the 45 findings `fix` would write across eleven files --
ONS_150, 151, 155, 157, 159, 164, 166, 183, 190, 194 and 200 -- was checked
against the scan, four ways, and all 45 are real heads. No false positive was
found.

| How it was settled | n |
|:--- |---:|
| the text layer has the head on a line of its own, marked (underlined, capitals or bold) | 25 |
| the text layer has it on a line of its own, unmarked -- a 12-to-27-character line standing alone is a head whatever the mark test says | 4 |
| the text layer folded it the same way the Markdown did, and the head's own words are visible in the folded line (`...had ever Lists Received`, `By Nick Rhodes From the Editor`) | 8 |
| the text layer extracts as garbage, so the page was rendered and read | 8 |

The third row is the reason this screen exists. Where the PDF's own text layer
lost the line break, `detect_headings.py` cannot see the head set apart in
either direction, at any threshold -- there is no set-apart line in the
geometry to find. The fourth row is worse: ONS_159, ONS_166 and ONS_183 have a
broken `ToUnicode` map, so `page.get_text()` returns control
characters and scrambled letters. Every text-layer screen in this repo is blind on those files --
`detect_headings.py`, and `crop_sheets.py`'s anchor matching with it -- while
`pdfmd --ocr auto` re-OCR'd the page image and read the words correctly. On a
file like that this Markdown-only screen is the only one that works.

`fix` only moves structure, so the word stream is the audit, the same one
`detect_headings.py` uses:

```python
w = lambda t: re.findall(r'[A-Za-z0-9]+', t)
w(old) == w(new)   # False means text was lost, duplicated, or split mid-word
```

Over the whole corpus that is 163 cuts in 86 files with the word stream
preserved in every one. It is worth running, not a formality: it caught the
cut column being measured against the line with its `## ` stripped and then
used against the line with it still on, which turned `## ONS News Obituaries`
into `## ONS Ne` plus `### ws Obituaries` in three files.

### Settling the `-OPEN` findings against the scan

`GLUED-END-OPEN` and `GLUED-BOTH-OPEN` are refused for one reason: the prose
before the head does not close a sentence, so the cut might sever one. That
is a question about the page, and `corroborate_heads.py` answers it without a
render and without a reader:

```
corroborate_heads.py report ONS_189 ONS_191      # what the scan says
corroborate_heads.py rows   ONS_189 ONS_191 > c.tsv
detect_section_heads.py fix --corroborated c.tsv ONS_189 ONS_191
```

It asks the PDF text layer whether the head stands on a short line of its
own -- `CONFIRMED` when it is also marked, `OWN-LINE` when it is not, and an
8-to-27 character line standing alone is a head whatever the mark test says.
`rows` emits those two and nothing else; `fix --corroborated` then cuts the
named head on the named line, and only that.

Measured over the corpus: of 61 `-OPEN` findings, 25 settled this way, 21 sit
in files whose text layer is broken (ONS_160-ONS_185), 13 matched no line,
and the rest need a page.

Three things to know before trusting it:

- **The match can land on the wrong page.** `locate_in_pdf` takes the best
  ratio anywhere in the file, so a head that also appears in the issue's own
  contents listing can match that instead. ONS_189's `Other News` matched
  `Other news 4` on page 32 while the real head sits on page 4. A match whose
  line ends in a page number is reported `SUSPECT-CONTENTS`; read the report
  rather than piping `rows` straight into `fix`.
- **The rows go stale between passes.** They name a line number, and the
  first cut on a line moves everything below it, so a line carrying two heads
  needs the rows regenerated before the second pass. ONS_189's line 42 holds
  both `Other News` and `Auction News` and took two rounds.
- **No underline probe.** No pixmap is taken, so on the pre-ONS_131 issues --
  which underline their heads rather than printing them bold -- `NO-LINE` and
  `UNMARKED` mean "not settled here", not "not a head".

A row names the head as well as the line, because settling one head says
nothing about another on the same line.

### How much of the corpus this is

Measured over `jons/` as it stands: nothing left for `fix` to write, and 125
findings reported for a reader -- 35 `GLUED-COMPOUND`, 34 `GLUED-END-OPEN`,
27 `GLUED-MID`, 21 `BYLINE`, 5 `GLUED-HEADING-JOINED`, and one each of
`GLUED-RUNIN-PREFIX`, `GLUED-BOTH-OPEN` and `GLUED-END-INRUN`. It reported
164 writable findings when it was written; those were swept over six batches,
`GLUED-PAIR` took 16 more, and `corroborate_heads.py` settled 25 of the
`-OPEN` findings against the scan.

The same discipline as the rest of this skill applies, and for the same
reason: read `scan` before running `fix`, and never sweep `fix` across the
corpus.

**What the vocabulary cannot reach.** A section head this screen knows is one
the newsletters print issue after issue. An article's *own* sub-heads are
arbitrary -- ONS_152's bibliography divides into `Numismatic Monographs:`,
`Articles on Islamic numismatics:`, `Annual Work Reports:` and four more, each
bold and set apart on the page, two of them folded into the end of the
paragraph above. No vocabulary reaches those, and `detect_headings.py`
reported only two of the seven, both as `LOST`, because the fuzzy match wants
the head to account for most of its Markdown line and these lines are long
paragraphs. They were restored by hand. Between the two screens there is
still a gap here, and it is the harder half of the problem.

## Matching the two OCR layers

The PDF text layer and the Markdown were OCR'd separately and disagree --
`ORIEOTAL` against `ORIENTAL` -- so a head is matched fuzzily. Three rules keep
that from turning into coincidence:

- **Two anchors only.** A head either starts its Markdown line or was appended
  to the end of one. A match floating in the middle of a paragraph is a
  coincidence. Allowing the middle is what let `B I B L I O G R A P H Y` match
  the words `Bibliography of hoards` inside a numbered reference.
- **Locality.** The matched pieces must sit together, within about 1.4x the
  head's length. Summing scattered blocks lets a long paragraph "contain" any
  short head.
- **Document order.** Both files run in the same order, so a match at or after
  the previous head's row wins ties. Without this the bibliography subhead
  `Historical` on page 11 matches `## Historical Summary` back on page 1 with a
  perfect score, and the real head goes unreported.

A `start` match must also account for most of its line. That is what stops the
heading `# NOTE` from matching the body line `Note: Up to twenty small marks
may occur...`.

## Splits that are refused

A `FOLDED` fix cuts a Markdown line in two. Two kinds of cut are always wrong,
and both were found by sweeping `fix` across the corpus and auditing the result:

| Suffix | Refused because |
|:--- |:--- |
| `-MIDWORD` | the cut lands inside a word. It turned `# ORIENTAL NUMISMATIC SOCIETY INFORMATION SHEET` into `# ORIEN` plus `## TAL NUMISMATIC SOCIETY INFORMATION SHEET`. |
| `-LOWER` | the head starts lower-case and was cut out of running prose, so it is a sentence tail, not a head: `(see` / `appendix).`, `I have now developed a` / `classific-`, `to an accuracy of 0 02 of a` / `millimeter`. |

`-LOWER` has one deliberate exception: a **by-line** cut from a title, such as
`# THE COINAGE OF COOCH BEHAR` / `by N.G. Rhodes`. What is left behind there is
a heading rather than a sentence, so the cut is right. The exception requires
the remainder to be both marked *and* at most `TITLE_LEN` (60) characters --
a paragraph that has picked up a stray `#` is still a paragraph, and letting
the marker alone vouch for it is exactly what cut `millimeter` loose.

## Auditing a fix

`fix` only ever moves structure, so the word stream is the check:

```python
w = lambda t: re.findall(r'[A-Za-z0-9]+', t)
w(old) == w(new)   # False means text was lost, duplicated, or split mid-word
```

Across a 53-file sweep this caught the one mid-word split immediately. It does
**not** catch a cut made at a legitimate word boundary in the wrong place, so
also check for headings the sweep created that begin lower-case:

```
git diff <before> -- jons/ | awk '/^\+\+\+ b\// {f=substr($2,3)}
                                  /^\+## / {t=substr($0,5)
                                             if (t ~ /^[a-z]/) print f": "t}'
```

## Tuning

- `--min-underline` (default 0.45) -- ink run under a line, over the line's own
  width. Scans differ: IS_001's heads score 0.90+, IS_003's running heads score
  0.42 and need `--min-underline 0.40`. Check the render before lowering it.
- `--min-margin` (default 0.25) -- how far that run must beat the margin
  control. Lowering this re-admits scan streaks.
- `--gap` (default 1.4) -- blank space above and below, in multiples of the
  page's own median leading. IS_001's heads clear 1.9x against 1.0x for ordinary
  interline spacing.
- `--width` (default 0.75) -- longest a head may be, as a fraction of the page's
  body measure.
- `--no-shape` -- require the gap test, disabling the shape route entirely.
- `--include-shape` (`fix` only) -- also apply what only the shape test found.
  Off by default; see above.
- `--min-ratio` (default 0.72) -- similarity before two lines count as the same
  text.
- `--min-bold` (default 0.9) -- fraction of a line's own characters the OCR
  layer must flag bold before it counts as a bold head. Real heads come back
  1.00; nothing seen scoring under 0.75 was a real head.
- `--bold-noise` (default 0.15) -- fraction of a page's long body lines that
  may score over 50% bold before the bold signal is distrusted for that whole
  page. Lowering this makes more pages fall back to underline/capitals only;
  raising it re-admits pages whose body text itself OCR'd bold.
- `--marker` (default `##`) -- what `fix` prefixes a head with.

## Scope

Tuned and verified against IS_001, which is typewritten prose. Run `scan` and
read it before running `fix`; never sweep `fix` across the corpus.

On catalogue-heavy files -- IS_003, IS_005, IS_007 -- the report is noisier, for
two reasons worth knowing:

- A **table rule** sits under a line of cells exactly the way an underline sits
  under a head, and the margin control does not always separate them. Expect
  `LOST` findings whose text is table debris (`o. 1 . 0 80`).
- Ruler names in a catalogue are set in capitals that the OCR mangles into mixed
  case (`MANSTJR I ibn miH`), so the capitals test misses them and they report as
  `OVERSET`.

Both are false positives to read past, not defects to fix blindly.

The same discipline applies to bold. The noise gate catches a page whose
*whole* text layer OCR'd bold, but not a page that is merely inconsistent --
a masthead block of names and addresses, say, where some run-in labels are
genuinely bold and most body text is not, scoring under the gate's threshold
without every bold line on the page being a head. `ONS_072`'s page 1 (a
regional-secretaries masthead) is like this. Read `scan`'s report, including
the `bold=` column, before trusting an `OVERSET`-to-`OK` flip on a page like
that -- the gate reduces false positives, it does not eliminate the need to
read the report.

## Verification

The tool was written after five heading errors in IS_001 were found by hand.
Run against the file as it stood before those repairs, it reproduces all five
with the same verdicts, and finds four more that the manual pass missed --
including a `BIBLIOGRAPHY` head absent from the Markdown entirely.

After a `fix`, check that only structure moved:

```python
w = lambda t: re.findall(r'[A-Za-z0-9]+', t)
w(old) == w(new)   # True unless you also edited text by hand
```
