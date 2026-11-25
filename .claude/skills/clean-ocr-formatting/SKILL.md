---
name: clean-ocr-formatting
description: Repair four OCR layout artifacts in a `jons/` Markdown file -- per-word asterisks (`*word *` or `**word **`), words split with internal spaces (`Numi smat i c` → `Numismatic`), paragraphs severed mid-sentence by a stray blank line where `pdfmd` read one physical line of the scan as its own block (including the case where the continuation begins with an OCR'd dash that Markdown then renders as a bullet), and the mirror of that -- two blocks of the scan run together into one, so a section head, a signature or a list item renders mid-sentence. Use when an OCR'd file has passages wrapped in per-word emphasis marks, letter-spaced words, a sentence that breaks off mid-clause and resumes in the next paragraph (including across an unclosed bracket), a one-item bullet list that is really the middle of a sentence, or a heading or byline swallowed by the paragraph beside it. Typically followed by the `fix-ocr` skill to clean up remaining single-word OCR errors.
---

# clean-ocr-formatting

This skill handles four OCR artifacts. The first three show up together when the source PDF used letter-spaced text or per-character styling (common with title styling, italic body text, or laser-printed pre-1980 typescripts); the fourth is independent of them and needs a second encoding of the PDF to see at all:

1. **Per-word asterisks** — every word wrapped in `*word *` or `**word **` instead of one span enclosing the phrase. Merged into one span per phrase by `scripts/merge_emphasis_runs.py`, never stripped: the emphasis is the page's and the Markdown is the only record of it.
2. **Word-internal spaces** — `Numi smat i c` for `Numismatic`; `re lat i vely` for `relatively`.
3. **Severed paragraphs** — a physical line of the source PDF becomes its own Markdown "paragraph" with a `\n\n` after it, so one paragraph breaks into blocks that stop mid-clause. The tell is the line *before* the break (it ends with no terminal punctuation), not the capitalisation of what follows.
4. **Lost block boundaries** — the mirror of 3. Two blocks of the scan arrive as one, because `pdfmd` dropped the blank line between them, so a section head, a signature, a bibliography entry or a list item renders in the middle of the paragraph beside it. There is no tell *in the Markdown*: the evidence was the whitespace on the page. Found by `scripts/detect_lost_boundaries.py`, which asks a second OCR of the same PDF where the blank lines went — see step 4.

The first three usually appear together in the same passage; a heavy letter-spaced italic block produces all three at once.

## Inputs

The user names a Markdown file, usually under `jons/`. If no path is given, ask once.

## Workflow

1. **Read the file** and identify the affected line ranges. The artifact is almost always localised to one section or page — not the whole document. Quote the start and end lines back to the user before editing if the range is non-obvious.

2. **Merge per-word asterisks into one span per phrase.** Use the script;
   it is mechanical and it checks itself.

   ```
   scripts/merge_emphasis_runs.py scan ONS_185      # report, change nothing
   scripts/merge_emphasis_runs.py scan ONS_185 -v   # print every line it changes
   scripts/merge_emphasis_runs.py fix  ONS_185
   scripts/merge_emphasis_runs.py scan jons/*.md    # corpus sweep
   ```

   It moves a span's padding outside its markers (`*word *` -> `*word* `),
   drops a span with nothing in it, and joins two spans of the same marker
   that have only whitespace between them, repeating until the line settles.

   **Do not strip the asterisks.** This step used to say
   `sed -E 's/\*+//g'`, which throws the emphasis away: the page sets those
   words in italic and the Markdown is the only record of it left, since
   `pdfmd` does not re-read the fonts. Merging keeps it.

   **What the asterisks were doing to the rendered page**, before this script
   existed: CommonMark will not close a span on a space, so `*word *` renders
   as the literal text `*word *`, and **35,868 asterisks reached the rendered
   corpus** that way across 153 files. The degenerate spans were worse than
   literal -- `* *` alone on a line renders as a bullet list whose item is
   `*`, and `**  **` as a horizontal rule, so 13 files carried 23 rules nobody
   set. After the pass: 4,802 asterisks left, and those are a different
   defect (a row of `***********` the newsletter really prints as a divider,
   and stray `*` standing in for a superscript footnote marker -- `fix-ocr`'s).

   **Why merging is safe.** `<em>a</em> <em>b</em>` and `<em>a b</em>` set the
   same words in the same face, so the merge cannot change what a reader
   sees. The only claim it adds is that the page set one phrase where it may
   have set two side by side -- two table cells, two captions in a row -- and
   that claim is invisible in the rendering. A `*` in the wrong place *inside*
   a word would not be, which is why nothing else is touched.

   Every write is checked: the line's text with all markers removed and
   whitespace collapsed has to come out identical, or the line is left alone
   and reported `REFUSED`. Over the corpus it merged 13,815 lines in 113 files
   with no refusals and no text changed.

   It will not touch a span holding `[`, `]`, `<`, `>`, `|` or a backtick
   (`*[figure]*` is `detect-missing-figures`' marker and `*Obv.* *[figure]*`
   must stay two spans), a span with a `*` inside it, an escaped `\*`, or a
   gap with anything but whitespace in it -- `*A* and *B*` are two titles with
   a roman `and` between them, and `*Gharn* ā *ta*` is a word split by a
   diacritic the OCR set in another face, which is `fix-ocr`'s.

   Run this **before** `restore-italics`: that skill refuses a file whose
   emphasis is mangled, because it cannot tell a missing italic from a
   mangled one.

3. **Collapse severed paragraphs.** Find them with the script, which reports
   a line number and a label per break:

   ```
   scripts/detect_severed_paragraphs.py scan ONS_049
   scripts/detect_severed_paragraphs.py scan jons/*.md        # corpus sweep
   scripts/detect_severed_paragraphs.py scan ONS_049 --loose  # add weak cases
   scripts/detect_severed_paragraphs.py fix  ONS_050          # safe labels only
   ```

   `scan` exits non-zero when there is something to fix. It needs no PDF, so
   it runs on the whole corpus in seconds.

   **Why a script and not the old regex.** This step used to screen with
   `perl -0777 -pe 's/([a-z,;:])\n\n([a-z])/$1\n$2/g'`, which only fires when
   the text *after* the break starts lowercase. On ONS_047, ONS_049, ONS_050
   and ONS_051 that matched none of the real breaks — the continuations began
   with a capitalised proper noun (`Piastres`, `Maharajah`), a year (`1716`),
   or an OCR'd dash (`- Hebert`). What those cases share is the line *before*
   the break: it stops mid-clause with no terminal punctuation. That is what
   the script tests, so the fix no longer depends on how the continuation
   happens to be capitalised.

   | Label | What it means | What the fix is |
   |:--- |:--- |:--- |
   | `severed` | the line ends on a function word (`of`, `in`, `and`, `the`) or a comma, or the continuation starts lowercase — none of which can end or begin a sentence | collapse one newline; `fix` does it |
   | `severed` | the same, where the tail needed reading before it could be recognised: a function word the OCR garbled (`Kirman ot` for `of`) or a two-word tail whose last word alone proves nothing (`was not`, `do not`) | collapse one newline; `fix` does it |
   | `fake-list` | the continuation starts `- `, so Markdown renders a bullet | collapse **and** restore the dash — see below |
   | `fake-ol` | the continuation starts `1252. `, so kramdown renders an ordered list — the number is a page or a year in the citation the break cut | collapse, delete the `{: start=}` IAL, and restore the number — see below |
   | `hyphen-split` | the line ends on a hyphenated fragment (`Muzaf-`) | join into one word, no space; `fix` does it |
   | `paren-split` | the line leaves a bracket open and the continuation closes it (`...of the same date (AH` / `1200/Ry.4). The coin...`) | collapse one newline; `fix` does it |
   | `paren-far` | the same, but the bracket closes more than 250 characters from where it opened | read it — usually two unrelated paragraphs |
   | `margin-cut` | WARN: the line above runs to the column margin, so the page ended it and not its author | read it and decide by hand; `fix` never touches it |
   | `maybe-severed` | `--loose` only: no terminal punctuation but the continuation is capitalised or a bare number | read it and decide by hand |

   **Why only one newline?** In CommonMark, `\n\n` is a paragraph break but a
   single `\n` inside a paragraph is a soft break that renders as a space.
   Removing one newline preserves the file's line-by-line structure (useful in
   diffs) while letting the text reflow as one paragraph. `fix` does this;
   when editing by hand, do the same rather than joining both lines into one.

   **An unclosed bracket is the one mechanical proof here.** Every other rule
   is a judgement about English and carries the error rate of one. A line that
   leaves a `(` open is not a line that ended, and a continuation that opens by
   closing it is not a paragraph that began — the two halves have to agree
   before the rule fires, which is what keeps a `)` the OCR dropped elsewhere
   out of it. Corpus-wide it finds **370 breaks in 83 files**, not one of which
   any other rule reported; a sample of 18 read against the page came back
   17 right, and the one wrong was `***Reviews***` run on to a members-news
   list, which is now suppressed as a bold title (the guard had only ever
   matched two asterisks). This was the defect ONS_109's
   `...of the same date (AH` / `1200/Ry.4). The coin shows...` sat on through
   four passes: the all-capitals `AH` is deliberately not read as a word, so
   the function-word rule could not see it, and the continuation opens on a
   digit, which is `--loose` only and off by default.

   **OCR debris elsewhere in the line used to blind it.** The rule stands
   down whenever a line holds a closer with nothing to match, on the sound
   ground that the bracket count is then untrustworthy. But a `[` or `]` a
   word runs straight through is not a bracket at all — it is the OCR's
   reading of a letter, which pdfmd escapes because Markdown would take it
   for link syntax. ONS_171's `Khari\]ite` (for `Kharijite`) sat sixty
   characters up the line from a textbook `paren-split`, `(Tabari` /
   `II.647 = tr. XXI.8),`, and cost the file the finding. `mask_garble`
   reads through those first. It pairs the brackets off before masking
   anything, because a scholarly restoration mid-word — ONS_230's
   `kidara kusha\[na\]/` — has letters hard against its opener too, and
   masking half of a matched pair orphans the other half and stands the
   rule down just the same. Round brackets are never read through: `D (ii)l`
   and `(1)41` are real labels whose closer a letter or digit follows.

   **`margin-cut` proves the cut from the page, not from the words.** Every
   other rule reads the English at the break and carries the error rate of a
   judgement about English. This one reads line *lengths*: a paragraph's last
   line stops where the sentence stopped, and a line `pdfmd` cut stops where
   the column did. It matters because `pdfmd` does not read a file one way
   throughout — ONS_171's lines 18-82 come back one physical scan line to a
   block, 47 to 68 characters each, while the rest of the file is a whole
   paragraph to a line at 200 to 950. In the first regime a `\n\n` carries no
   information at all and every tail rule is reading tea leaves; the column
   width is the only evidence on offer. ONS_171 screened **clean** while
   carrying nine severed paragraphs, and `--loose` answered with 202 WARNs.
   It now reports six findings, all six cuts.

   The width is measured off the file (the modal line length over a 40-line
   window, not a percentile — a percentile is dragged up by the blocks where
   `pdfmd` did join two lines), so it travels from typewritten single columns
   to printed three-column pages. Corpus-wide: **624 findings in 135 files,
   median 2 to a file**, and a read of 42 found 13 cuts. At 42% this is a
   WARN that sends you to the scan, never a fix.

   **It only speaks when the line is running prose.** A plate caption, a
   catalogue row of weights and die axes, a masthead line all sit one to a
   block legitimately and all reach the margin as readily as prose. The gate
   is three tests — no emphasis markup, at least seven words, at most three
   numbers — and it is doing most of the work: without it the rule reports
   5723 breaks and is unusable.

   **Two shapes get through that gate, and `attributed_entry` takes them
   out.** The newsletter contents list and the article byline are both a
   title that runs the full width of the column and closes on who wrote it —
   `by R. C. Senior`, `(I. Paghava)` — so every test above passes and the
   line below, the next title or the article itself, reads as the sentence
   resuming. Together with the bibliography entry (`Schjoth, Fr., The
   currency of ...` opening the continuation) they were two thirds of
   everything the rule got wrong. Suppressing them took 783 findings to 624
   and lifted a read of 42 from 31% to 42%; a read of 30 of the 159
   suppressed found no cut among them.

   The three tests are each narrower than they look, and deliberately:

   - `by` needs **two** name tokens. `a paper published by John` / `Smith in
     1980` is a cut and offers one.
   - a bracketed author needs an **initial with its stop**. ONS_184's
     obituary runs `by his wife Joyce, Sister Susan (Glenn)` into `Benton and
     children`, and a bare `(Glenn)` is a maiden name, not an attribution.
   - a bibliography entry needs the **abbreviation** after the surname's
     comma. ONS_203's `Mudra, Vol. I, Coin` / `Study Circle, Calcutta` is a
     cut, and `Surname, Capital` alone would have claimed it.

   **`paren-far` is where it stops being mechanical.** Beyond ~250 characters
   the opener and the closer are usually unrelated — a stray `)` down the page
   meeting a `(` the OCR dropped half a paragraph earlier (ONS_174, ONS_201,
   ONS_202). Seven of the 370 land there and `fix` refuses them.

   **`fake-list` keeps precedence over `paren-split`.** Five breaks match both
   — `(M. 287` / `- 298)`, `(November 1991` / `- January 1992)` — and the
   bracket does not change what has to happen: a `- ` renders as a bullet
   whether or not the blank line goes, so they stay in the label that sends
   you to the scan.

   **`fake-list` needs the scan, so `fix` refuses it.** An unordered marker
   interrupts a paragraph even without the blank line, so collapsing the break
   alone leaves the bullet rendering. The dash is standing in for something
   the OCR dropped, and only the page shows what. Read it off the render, then
   decide the break separately — the two questions are independent, and the
   answer differs even within one file:

   | On the scan | Then the blank line |
   |:--- |:--- |
   | ONS_049 `...Bombay - 'The Sultans of Gujerat, 1935"` / `- are coins struck in...` → an **em dash** mid-sentence | was a cut: collapse it |
   | ONS_051 `...regarding Chinese coins. Raymond` / `- Hebert of 6305...` → the **initial** of `Raymond J. Hebert` | was a cut: collapse it |
   | ONS_051 `Recent Publications`: `- W. Wiggins` → `K. W. Wiggins`, `- B. Coole` → `A. B. Coole`, `- H. Major` → `W. H. Major` | is a real entry boundary: **keep it**, fix only the marker |

   A whole bibliography can be initials read as dashes, so expect runs of
   these rather than one. Do **not** guess the initial from numismatic
   general knowledge: of five guessed from context before the page was
   rendered, `S. K. Bhatt`, `B. N. Mukherjee`, `K. W. Wiggins` and
   `A. B. Coole` were right but `W. H. Major` was not, and ONS_049's
   `K. Wiggins` is not the `K. W. Wiggins` of the same society's masthead.
   Render the page (`detect-missing-figures`' or `transcribe-foreign-script`'s
   render helper) and read it.

   An em dash restored at the start of a line is safe to leave there — `—` is
   not a Markdown bullet marker, so only `-`, `*` and `+` need moving.

   **`fake-ol` is the same bug one character over, and it was invisible until
   ONS_165.** The break cuts a citation, and the continuation happens to open
   on the next number in it, which kramdown reads as a list marker:

   ```
   ...cited on coins of AH 448-449 Barskhan (Kochnev 1997, 282/1248,

   {: start="1252"}
   1252. And it was Shams al-Daula Arslan-tegīn Nasr, to whom ...
   ```

   Two guards had kept every one of these off the report. The script skipped
   `N.` continuations outright — a defensible call, since most really are a
   list — and `scripts/fix_list_starts.rb` stamps the false list with
   `{: start="1252"}`, which `is_prose` rejects, so the gap was no longer pure
   blank and the pair never reached a rule at all. The repo's own tidy-up had
   made the defect well-formed. ONS_165 carried ten of them through a
   clean-ocr pass, a fix-ocr pass and a restore-lists pass without a single
   screen saying a word.

   The rule now earns the finding: the line above must end mid-clause, the
   item must have no sibling item beside it, and the number must not be `1`
   (a real list restarts at 1; a running citation does not — that one test is
   what keeps ONS_200's `1. The palaeography ...` and four more like it out,
   and it holds the `1.` cases back for `--loose`). Corpus-wide:
   **99 findings in 40 files**, 86 of them corroborated without reading
   anything — 45 open on a number within 30 of one at the end of the line
   above, 36 on a year, 5 on a lower-case word.

   Four tails count as ending mid-clause, and the corpus splits almost evenly
   between the first three: a comma or semicolon (35), a function word (28),
   a number cut at its dash (28), and a **month name** with a four-figure
   year opening the continuation (8). The month tail is the only one of the
   four that is mechanical rather than a judgement about English — `...
   issued on 20 December` / `1999. Circulating coins ...` cannot be a
   sentence that ended, because a date needs its year. `May` is the one
   ambiguous month name (`the date may` / `1983. ...`) and the function-word
   list already holds it, so those are claimed by the earlier test.

   `fix` refuses it, and not only because the number needs the scan: the
   `{: start=}` line has to be deleted along with the break, and `fix` can
   only ever collapse a newline. Repair it by hand — remove the IAL, collapse
   the break, and put the number back as the citation printed it. Then rerun
   `scripts/fix_list_starts.rb`, which will have nothing left to stamp.

   Four of the 99 are not this bug: ONS_162's `28. Palmer 1993` is a real
   footnote item whose *previous* item was cut (collapsing would glue two
   notes together), ONS_197's `83.` is another note boundary, and ONS_182's
   and OP_014's are garble. Read before collapsing, as always.

   **`grep -n '{: start=' jons/<STEM>.md` is a wider net than the rule, and
   costs nothing.** The repo's own tidy-up is what makes it work: because
   `fix_list_starts.rb` stamps every false list with an IAL, each instance
   leaves a marker that survives the conditions which blind the screen. On
   ONS_165 the screen found 8 of the 10; the grep found all 10. The two it
   missed show what those conditions are — one had a
   `<!-- script-ok ... -->` marker on its own line between the two halves, so
   the gap was not pure blank and no rule was reached; the other's line above
   ended `1335.`, and a line ending in a full stop is never flagged, by
   design.

   A legitimate list keeps its IAL too (ONS_165's p18 endnotes are
   `{: start="6"}`, and `restore-lists` counts 1,510 IALs across 166 files),
   so the grep is a **worklist, not a verdict** — read each hit, and the tell
   that it is the defect is the line *above* ending mid-clause. Run it
   alongside `scan`, read each junction off the scan, repair, then rerun
   `fix_list_starts.rb`: it should report `total: 0`, with the only IALs left
   belonging to real lists. Across ONS_165's ten the printed junction was
   always a `)` or a `,` where the OCR had put a full stop, and the *number*
   was never wrong — so what actually needs reading off the page is the
   punctuation.

   **Two findings that are not this bug.** Both look like severed paragraphs
   and belong to other skills:

   - a **glued heading** leaves the line above ending on a noun with no
     punctuation (`...Spink's NC., May 1977, 201 Books` / `1977 Lists of
     Books for sale...`). The paragraph break is real; the defect is `Books`
     being stuck to the line above → `restore-headings`.
   - a **flattened list or family tree** is full of ` - ` separators, where
     the dashes are structure, not a cut sentence → `restructure-flattened-md`
     for a tree, `restore-lists` for a list. A list `pdfmd` glued into one
     paragraph (`1A: ... 1341. 1B: ...`) or wrote as labelled lines leaves
     no severed paragraph for this script to find at all; `restore-lists`'
     screen reads it off the scan.
     The script already skips lines with two or more ` - ` runs for this
     reason; if one slips through, don't collapse it.

   **The corpus sweep is a worklist, not a batch job.** `scan jons/*.md`
   reports ~2800 `severed` findings. Hand-checking 126 of them in the files
   with three or fewer (and three random samples of 30 before that) put the
   rule's precision at **about 75-80%** -- so `fix` run across the whole
   corpus would collapse several hundred breaks that were never cut. Do not
   do it. Work file by file, read each finding, and collapse what you have
   read. Precision also tracks the file: the light files are mostly running
   prose and scan ~89% true, while the heaviest (ONS_210 with 201 findings,
   ONS_171 with 137) are heavy *because* their footnote apparatus and
   bibliographies are flattened, which is where the rule is weakest.

   The false positives that remain are the ones no regex settles, and each
   belongs to someone else:

   - a comma OCR'd from a full stop at a real paragraph end (`weighing
     approximately 1.0 grams,` / `The normal obverse consists of ...`) --
     indistinguishable from a cut, because `However,` + a capital is a true
     positive with the same shape. `fix-ocr` owns the comma.
   - a footnote marker OCR'd as quotes, so the line reads as ending on a
     preposition (`seems to be called for"'"`). The sentence did end.
   - prose whose continuation is the *next* block but one, because the
     apparatus got between them.
   - a severed heading (`The coin shown in` / `The Reverse`) --
     `restore-headings`.

   `is_entry_boundary` already suppresses the classes that *are* mechanical,
   all of them found by sweeping the corpus: a continuation that opens a
   numbered note (`8 For illustrations`, `52Album 1976`) or a footnote-marker
   glyph (`"^`, `©`, `*'^*`); a lettered list item (`a) Flowered silver
   lumps`); a coin-description field (`Rev. Temple containing`, `Weight
   3.31 g.`); and the officers masthead, where two `Label:` groups in a line
   mark it as the flattened directory `restructure-flattened-md` owns. Two
   tail words also came out of `FUNCTION_TAILS` -- see the note there on
   `above`, `below` and `each`.

   **Never** apply this pass to fenced code blocks, tables, real lists,
   headings, front matter, or verse where line breaks are semantic. The
   script skips all of these, which is the main reason to prefer it over a
   regex over the whole file.

4. **Restore lost block boundaries**, where `pdfmd` dropped the blank line
   *between* two blocks instead of inventing one inside a paragraph. This is
   step 3's defect read backwards, and it has its own script because it needs
   evidence step 3 does not have.

   ```
   scripts/detect_lost_boundaries.py scan ONS_171        # CLEAN tier only
   scripts/detect_lost_boundaries.py scan ONS_171 --all  # add the OPEN tier
   scripts/detect_lost_boundaries.py rows ONS_171        # file/class/line/anchor
   scripts/detect_lost_boundaries.py fix  ONS_171        # CLEAN tier only, always
   ```

   What it looks like. Four blocks of ONS_171 page 3 arriving as two:

   ```
   ... and he will be remembered for a long time. Joergen Clauson-Kaas

   Annual General Meeting The AGM will take place on Saturday 25 May 2002 ...
   ```

   A signature and two section heads have been swallowed by the paragraphs
   beside them. Nothing there is misspelled, no table is involved, no heading
   marker is in the wrong place, and **no screen that reads the Markdown alone
   reports a thing** — the evidence for the boundary is the whitespace on the
   page, and the whitespace is exactly what was lost. ONS_171 went through
   `restore-headings`, `restore-lists`, `detect-missing-tables` and `fix-ocr`
   with all fourteen of these in place and every screen clean.

   **Where the evidence comes from.** A second OCR of the same PDF, stored at
   `$ONS_SECOND_DIR/<stem>/<stem>.ou.md` (`ONS_SECOND_DIR` defaults to
   `~/personal/ocr-junk`). Align the two token streams with `difflib`, and
   every boundary the second encoding has and ours lacks is a finding.

   This is not an appeal to a second opinion about the text. The second
   encoding is wrong about plenty — it reads `Barner` as `Earner`, promotes a
   byline into the head below it, and splits a bibliography entry in half at a
   line break. None of that matters, because it is not being trusted about
   *words*. It is asked one question, about layout, that it answers from the
   same pixels and that our encoding does not answer at all.

   `scan` prints `no second encoding` and exits 0 where there is no second
   file, so it costs nothing in a corpus sweep. Where there is one it takes
   about 15 seconds on a 500 KB file, and needs no PDF and no render.

   | Tier | What it means | What to do |
   |:--- |:--- |:--- |
   | `CLEAN` | the prose before the boundary closes a sentence. Both encodings agree where the sentence ended; they disagree only about whether a blank line follows it | act on it |
   | `OPEN` | the prose before does not close a sentence. Usually the *second* encoding is at fault, having broken a block at a line break of its own. But a real head often follows a signature with no stop (`...By T.D. Yih` / `Introduction`), so it is reported under `--all` rather than dropped | settle on the page |

   The class routes the repair; it does not make it. It is read off the second
   encoding's own markup, because that encoding already decided what the block
   was:

   | Class | Owner |
   |:--- |:--- |
   | `HEAD` | `restore-headings` — it knows what marker the corpus gives a head, and will check it against the scan |
   | `BYLINE` | `restore-headings`; a byline is not a heading and wants no marker |
   | `LIST` / `BIBL` | `restore-lists` |
   | `PROSE` | this skill: insert the blank line and nothing else |

   **`fix` writes the CLEAN tier and nothing else**, and `--all` does not
   widen that — an `OPEN` finding is one where the second encoding is the
   likelier of the two to be wrong, and it is settled on the page. It inserts
   a blank line and *only* a blank line: the class says a head or a list item
   is in there, but giving it a `##` or a `1.` is `restore-headings`' and
   `restore-lists`' work, done against the scan. This pass only puts the
   block on its own, which is the precondition both of those screens need and
   neither can establish.

   Three guards refuse a cut, and all three were written after a pass on
   ONS_171 did the damage they describe:

   | Refusal | Why |
   |:--- |:--- |
   | the cut lands in a table row or a fence | the blank line would destroy it |
   | no whitespace at the cut | our encoding runs two lost blocks together *with a space* — that is what losing the blank line looks like. No whitespace means the alignment is off by a token. This is what the tier test cannot see, because the markup that fooled it is blanked before tokenising: `p. 8f.<sup>2</sup>` had `2` read as a new block's first word and the cut landed inside the tag |
   | the cut falls inside an open emphasis run | it would leave the run unclosed and the rest of the file in bold. ONS_171's `*Sultans of Malwa .Muhammad Shah II (.AH 917-22)*` is one run holding a heading and the entry under it; splitting the run and re-closing both halves is a real repair, but it is a judgement about what the emphasis was for, so it goes to `restore-headings` |

   **Verify the pass with counts, never with a diff dump.** A boundary pass is
   a whitespace-only change, and that is a property you can check exactly:
   the token multiset must be identical, the asterisk count must be
   identical, and the text must be unchanged after collapsing all whitespace.
   Also count the blocks whose emphasis delimiters do not balance — it must
   not rise — and the blocks opening with a space, which must be zero. Then
   run `detect_severed_paragraphs.py`, which is the real backstop: a cut that
   severed a paragraph is precisely what it reports, so its count must not
   rise either. On ONS_171 those checks caught two bugs a diff read had
   already passed over.

   **It leaves kramdown work behind, and that has to be finished.** Numbered
   bibliography and footnote entries that were mid-paragraph are now at line
   starts, where kramdown reads them as ordered-list items and renumbers them
   from 1. On ONS_171 the pass turned 11 of those warnings into 28. Run
   `scripts/fix_list_starts.rb --fix jons/<STEM>.md` afterwards and re-run
   `lint_structure.py`; it took the file to 0 errors and 1 warning.

   On ONS_171 against its `.ou.md`: **229 CLEAN findings** (`HEAD` 15,
   `BYLINE` 1, `LIST` 54, `BIBL` 51, `PROSE` 108) and 127 `OPEN`. A block of
   18 `LIST` findings was read against page 62 of the scan, which prints
   `LIST OF THE RULERS OF THE KHĪVA KHĀNATE` as a hanging-indent list of 26
   entries that our Markdown holds as one paragraph: all 18 were real.

   **Why the alignment guard is a neighbourhood and not an equality.** A
   boundary is only reported when the tokens around it sit in a matched run —
   but the seam is exactly where two OCRs disagree, so requiring the mapping
   to be one-for-one across it threw away real findings. `coins of the
   Safavids. London` is `Safavidis` in the other encoding, and
   `al-Malik.<sup>60</sup> References` keeps a `60` the other encoding wrote
   as `⁶⁰` and did not tokenise at all. Both were invisible until the test
   became "stay in order, and within `SEAM_SLACK` tokens".

   Three bugs worth not reintroducing, all of which made the screen quietly
   under-report rather than fail: blanking an HTML comment to spaces
   **without keeping its newlines** shifts every line number below a
   multi-line `<!-- source-typo -->` note; `<sup>` and `</sup>` are *words* to
   a tokeniser and put phantom `sup` tokens into a seam; and the text used to
   decide `CLEAN` has to run to the start of the next token, or it stops
   short of the full stop that is the whole point of the test.

5. **Rejoin word-internal spaces** one fragment at a time. No regex is safe across the board, because not every short token should be merged. For each broken phrase:

   - Read the surrounding sentence so you can judge what the original word should be.
   - Run cspell to surface broken fragments:
     ```
     cspell --config cspell.config.yaml --no-progress --no-summary --unique --words-only "<path>" | sort -u
     ```
   - Try joining adjacent fragments and verify the result is a real word.
   - Apply via `Edit`, quoting enough surrounding context that `old_string` is unique.

6. **Re-run cspell** when done. Remaining unknowns should be proper nouns or numismatic terms — hand those off to the `fix-ocr` skill for normal classification and dictionary updates.

## Common merge patterns

The OCR engine breaks letter-spaced words at fairly predictable points. Examples drawn from this corpus:

- `Numi smat i c` → `Numismatic`
- `re lat i vely` → `relatively`
- `Soci ety's` → `Society's`
- `News I etter` → `Newsletter` (also `I` → `l`)
- `pub I i shed` / `subsequent Iy pub I i shed` → `published` / `subsequently published`
- `chrono Iogi cal` → `chronological`
- `col Iect i on` → `collection`
- `Iect i on` → `lection` (suffix; check the word before)
- `descr i bes` → `describes`
- `domi nant` → `dominant`
- `i ncIud i ng` → `including`
- `cone Iudes` → `concludes`
- `i nfIuence` → `influence`
- `Ianguages` → `languages` (leading `I` → `l`)
- `Iogi cal` → `logical`
- `tant`, `impor` — fragments of `important`

Capital-I-for-lowercase-l is endemic in these passages — assume any leading `I` followed by a vowel is really `l` unless the word genuinely starts with `I`.

## Patterns to watch for beyond words

- **Spaces inside paired punctuation** — `( c )` → `(c)`, `Vol . I` → `Vol. I`
- **Number-letter splits** — `l 9 6 5` → `1965`, `2 9 0 p p` → `290 pp`
- **Roman numeral splits** — `x v i i` → `xvii`, `p i s` → `pis`, `5 p l s` → `5 pls`
- **Bibliographic abbreviations** — `R s . l O` → `Rs. 10` (digit confusion: `l` → `1`, `O` → `0`)
- **Mid-sentence paragraph breaks** — physical line breaks in the source PDF become `\n\n` separators. Screen for these with `scripts/detect_severed_paragraphs.py` rather than by eye; step 3 has the detail.

## What NOT to do

- Don't blanket-strip asterisks from the whole file — only the affected ranges. Legitimate `*emphasis*` or `**bold**` elsewhere must survive.
- Don't merge tokens that already form valid English (`to be` is two words, not `tobe`).
- Don't change British spellings or rare transliterations — defer those to the user or to the `fix-ocr` skill.
- Don't touch fenced code blocks, inline code, URLs, image references, or front matter.
- Don't run destructive `sed -i` without a `.bak` and a post-edit diff check — the changes are far-reaching and easy to over-apply.
- Don't collapse a break the script labelled `fake-list`, `fake-ol`, `paren-far`, `margin-cut` or `maybe-severed` without looking at it. `fake-list` needs the dash read off the scan and `fake-ol` the number; `margin-cut` says the *line* was cut, which is not yet a claim that the sentence was; `maybe-severed` is ambiguous by construction, and legitimate one-line paragraphs (table-of-contents entries, short bibliographic fields, untagged headings, masthead lines) live in both of those categories.
- Don't turn a `fake-ol` finding into a list. The number is not a label and there is no list to restore — the paragraph is cut and the marker is an accident of where the cut fell. Equally, don't reach for this rule on a list that is real but flattened: items the page prints at one left edge, with labels counting up, are `restore-lists`' business.
- Don't widen the detection by matching on what follows the break. That was the old regex's mistake: it cost the skill every real instance in ONS_047, ONS_049, ONS_050 and ONS_051, because a severed line's continuation is capitalised about as often as not.
