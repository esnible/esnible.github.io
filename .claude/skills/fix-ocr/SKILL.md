---
name: fix-ocr
description: Find and correct OCR errors in a Markdown file from the `jons/` corpus (Oriental Numismatic Society publications — `IS_###` Information Sheets, `ONS_###` newsletters and journals, `OP_###` occasional papers, and a few bare-numbered files). The text is OCR'd from English-language PDFs that often contain rare Chinese, Islamic, or Indian numismatic terms and occasional stray Arabic glyphs. Covers letter-level garble, real-word confusions cspell cannot see, suspect glyphs (`¥` is usually `½`; `€` postdates most of the corpus), and passages pdfmd read mirrored so every word came out spelled backwards. Use when the user asks to clean up, proofread, or fix OCR in a `.md` file, or when a passage reads as unrecoverable noise and you want to know whether it is garbled or merely transformed.
---

# fix-ocr

You are correcting OCR errors in a Markdown file produced by `pdfmd --ocr auto --lang eng+ara` (see `scripts/build.sh`). The text is English numismatic content. Errors are mechanical OCR mistakes, not authorial typos — treat them as such.

## Hard constraints

These override every other instruction in this skill. If a fix would violate one of them, leave the text as-is.

- **Never remove or merge line breaks.** Preserve every line break exactly as OCR'd, including hard breaks that fall mid-sentence. Never join two lines, even when a sentence is split across them.
- **Never change capitalization from context; correct a letter's case only with the page image as evidence.** Do not capitalize sentence starts or proper nouns, and do not lowercase anything, on the strength of grammar, style, or what a name "should" look like — that is inventing, and stays forbidden. But case is as legible in a render as any other glyph, so a case fix rests on the same footing as `,`→`.` below: render the source page (same command as the punctuation bullet below), see which case is actually printed, and correct to it. Rendering is not part of this skill's default loop — reach for it only for a specific candidate. If you will not render, leave the case exactly as OCR'd and list it for the user.

  This matters because the OCR engine's English language model **normalises the typist's own forms into commoner ones**, and case is one of the things it normalises. Restoring the page means writing `Trans-oxine` where the OCR produced `Trans-Oxiana`, `Al Moravids` where it produced `Almoravids`, `Arab-sassanian` where it produced `Arab-Sassanian`. A case fix often travels with a letter fix in the same token; that is fine, provided the render is what decided both.
- **Never punctuate from context; add, change, or remove a mark only with the page image as evidence.** Do not touch punctuation on the strength of grammar, sentence flow, or what the sentence "needs" — inventing a mark the page does not show stays forbidden, and hallucinated sentence-ending periods are the exact failure this rule exists to stop. But a mark is as legible in a render as any other glyph. Once you have rendered the source page and seen the mark actually printed there, you may **insert** it (a dropped comma, the lost hyphen in `1-4`, the period in `B.C.`), **substitute** it (`.`↔`,`, `;`↔`:` — real glyph confusions, the shapes differ by a pixel or two), or **delete** it (a mark not on the page that is clearly OCR noise). From the render, each of these is a glyph fix like `rn`→`m`; from grammar or sentence flow alone it is inventing structure, and stays forbidden. Rendering is not part of this skill's default loop — reach for it only for a specific punctuation candidate (`python3 .claude/skills/transcribe-foreign-script/scripts/detect_script_garble.py render <STEM> --page N [--clip x0 y0 x1 y1]`, then Read the path it prints — never a fixed name like `/tmp/p.png`, which parallel agents overwrite; `N` is the 0-based PDF page index, not the printed folio; `locate <STEM> --line N` ranks which page a line came from; write the four `--clip` numbers out literally — zsh does not word-split `$CLIP` into four arguments). If you will not render, leave the punctuation exactly as OCR'd and list it for the user. A punctuation fix may change a line's character count but must never change the number of lines — it is still an in-line edit.
- **Never delete a run of more than 12 consecutive characters.** A pure deletion — replacing text with nothing — may span at most 12 characters. To remove a longer run (OCR'd image digits, page-break garbage, a corrupted passage), you must substitute something in its place: a corrected reading, or an HTML comment such as `<!-- OCR: ... -->`. If you cannot supply a replacement, leave the run as-is and list it for the user.

Within these limits, still fix letter-level OCR garble: wrong letters, doubled or dropped letters, digit/letter swaps, and stray non-Latin glyphs.

## Inputs

The user names a Markdown file, usually under `jons/`. If no path is given, ask once.

## Workflow

1. **Read the target file** in full so you have the surrounding context for every change, and **snapshot it** (`cp <path> <scratchpad>/<STEM>.before.md`) — the Verification step compares against this snapshot, not against git, because an earlier pass (e.g. `restructure-flattened-md`) may have left the file with uncommitted changes.

2. **Run cspell** against the file using the project config. Use the positional output as your working list — it gives `line:col` for every occurrence, so you can jump straight to each one and you won't miss repeats:

   ```
   cspell --config cspell.config.yaml --no-progress "<path>"
   ```

   For the summary at the end, the deduplicated form is handy:

   ```
   cspell --config cspell.config.yaml --no-progress --no-summary --unique --words-only "<path>" | sort -u
   ```

   The project dictionaries (`dictionaries/{chinese,islamic,indian}-numismatics.txt`) already cover most legitimate terms, so anything that surfaces is either an OCR error or a numismatic term that should be dictionary-added. Occurrence count is a useful signal: a token that appears several times spelled identically is probably a legitimate term; a one-off is more likely garble.

   This same pass also surfaces `Forbidden word (<word>) fix: (<correction>)` hits from `cspell.config.yaml`'s `flagWords` list — real English words (so the ordinary dictionary pass can't catch them) that are nonetheless never the intended reading anywhere in this corpus, e.g. `modem` for `modern` (OCR's `rn`↔`m` confusion, applied to a real word). Apply the suggested fix directly; these have already been verified corpus-wide, so they don't need the per-occurrence judgment step 3 describes. See "Known real-word OCR confusions" below for how the list is maintained.

3. **Classify each unknown word** by re-reading the line it appears on:
   - **OCR garble** — fix it via `Edit`. See "Common OCR error patterns" below.
   - **Legitimate numismatic term** — append to the appropriate dictionary (see "Dictionary updates").
   - **Proper noun the dictionaries don't cover** (modern scholar, place name, etc.) — also append to the closest-matching dictionary.
   - **Genuinely ambiguous** — leave it, and list it at the end for the user.

   **Before skipping a name or term as unverifiable, grep the file for a correctly-spelled variant.** A proper noun you can't confirm from outside knowledge can often be confirmed from inside the file: the same name spelled correctly elsewhere (OCR quality varies page to page) settles the question. Apply the common substitution patterns (`ri`↔`n`, `rn`↔`m`, etc.) to the suspect token and grep for the candidates — e.g., `Fredenc Soret` is confirmed garble when `Frederic Soret` appears two paragraphs later. Also check parallel constructions (sibling headings, list entries) for the intended reading — e.g., a heading `Collections between LOOO and 5 000` is confirmed as `1000` by the sibling headings `Collections with more than 10,000` and `Collections with less than 1,000` in the same file. This check is mandatory for every token headed for the "left alone" bucket that occurs more than once or names a person or place; only after it comes up empty may the token be skipped.

   Classify by the **article or paragraph the word appears in**, not the file as a whole. Single-topic files (most `IS_###` information sheets) have one subject throughout, but `ONS_###` newsletters mix Chinese, Islamic, and Indian articles in a single issue — a word from the Chinese-cash article and a word from the Mughal-mints article in the same file belong to different dictionaries. The surrounding article's subject is the signal; the file's numbering is not.

4. **Also scan for OCR errors cspell will NOT catch.** Spellcheck only flags non-words. Many OCR errors are real words used wrongly, or punctuation/whitespace glitches. Do a targeted re-read for the patterns in "Beyond spellcheck" below.

5. **Apply edits with the `Edit` tool**, one logical fix at a time. For each edit:
   - Quote enough surrounding context that `old_string` is unique.
   - When the **same misreading recurs identically** (e.g., a name misread the same way ten times), fix all occurrences in one call with `replace_all` — the audit trail is identical either way. Unrelated fixes still go one per call.
   - **Before using `replace_all`, check that `old_string` isn't a substring of a different, already-correct word** (e.g. `Burges` is a substring of `Burgess`) — `replace_all` will silently corrupt every such occurrence into a doubled letter (`Burgess` → `Burgesss`). Run `grep -n "<old_string>"` first and eyeball every hit, or add enough surrounding context to `old_string` that it can't match inside the longer word.
   - Never change quoted historical spellings or transliterations you cannot verify — when unsure, leave it. **This applies with extra force to any proper noun** — a person's name, a place or mint name, a dynasty or era name, a ruler's regnal name. Transliterated proper nouns routinely have more than one legitimate English spelling (`Kavad`/`Kawad`, `Karzi`/`Karsin`, `Maurya`/`Mauryan`), and archival material (correspondence, official records, mint-official rosters) can genuinely spell the same person or place inconsistently (clerks, transliteration drift, editorial variance). Two different spellings of a proper noun are therefore not on their own evidence of OCR error — including when one spelling is far more frequent, or "sounds more like" the expected name or place. Only merge two spellings of a proper noun when there's an actual visual-confusion mechanism (see "Common OCR error patterns" — e.g. `rn`↔`m`, `cl`↔`d`) tying the *specific* letters that differ, and even then prefer confirming against a bibliography entry, caption, or other independent occurrence in the same file over reasoning about which spelling is more plausible. Default to leaving both spellings exactly as OCR'd when that confirmation is absent.
   - Do not edit inside fenced code blocks, inline code (`` ` ``), URLs, or image references. The corpus rarely contains these, but check before editing.
   - For a large batch of confirmed fixes (typically the dropped-punctuation pass below), use `scripts/apply_edits.py` instead of hundreds of `Edit` calls. It takes a file of `old => new` lines (optionally `old => new => COUNT`), requires each `old` to match exactly the expected number of times, refuses any change to the line count, prints a word-level diff per edit, and writes nothing unless every edit passes and `--write` is given:

     ```
     python3 .claude/skills/fix-ocr/scripts/apply_edits.py <path> <scratchpad>/edits1.txt           # dry run
     python3 .claude/skills/fix-ocr/scripts/apply_edits.py <path> <scratchpad>/edits1.txt --write
     ```

     Keep each batch to one page or article so the dry-run diff stays reviewable.

6. **Update dictionaries** for legitimate terms (see "Dictionary updates" section).

7. **Report a diff-style summary** at the end: grouped lists of (a) corrections applied, (b) dictionary additions, (c) words left alone with the reason. Keep it terse.

## Common OCR error patterns

The OCR engine confuses visually similar characters. When deciding what an unknown token should be, prefer the substitution that makes sense in the surrounding sentence.

### Letter ↔ letter confusions
- `amd`, `ard`, `aud` → `and`
- `tbe`, `tne` → `the`
- `ot`, `oi` → `of` (in context)
- `0wing`, `Owiing` → `Owing`
- `cifference` → `difference`; `c` ↔ `d` in general
- `nm` ↔ `m`; `rn` ↔ `m`; `ii` ↔ `n` or `u`
- `cl` ↔ `d`; `vv` ↔ `w`
- `ijauryan` → `Mauryan`; `M` often degrades to `ij`, `lj`, or `1j`
- Word-final `e` becoming `ee` or `es` (e.g., `coinagee` → `coinage`, `dependenciese` → `dependencies`)

### Letter ↔ digit confusions
- `3.C.` → `B.C.` (capital B misread as 3)
- `5)` / `5l` → `54` or similar (digits and lowercase letters confuse)
- `lth` → `4th`; `l` and `4` swap
- `40O` → `400`; `O` ↔ `0`

### Punctuation and stray glyphs
- Random Arabic / Hebrew glyphs in English paragraphs (e.g., `ف`, `(٠`) — delete. These come from `--lang eng+ara`. **Only delete a non-Latin glyph when it is clearly noise inside English prose.** If the file is discussing Arabic legends or transliterations and the glyph belongs there, leave it.
- Stray pipe characters (`|`, `\|`) inside running prose — usually delete.
- `—`, `~`, `--` runs left over from page breaks — delete the stray run. Don't replace it with an em dash or any other mark unless a render of that spot shows one printed there.
- Sentence-initial garbage tokens like a lone `nem` at the top of a file — delete.
- A backtick printed for *ʿayn* (`` Sa`id ``, `` `Ali ``) — write it as `'` (`Sa'id`, `'Ali`). A bare backtick in Markdown opens inline code and swallows the text up to the next one.

### Mirrored text: every word spelled backwards

```
scripts/detect_mirrored_text.py scan ONS_100
scripts/detect_mirrored_text.py scan jons/*.md
```

On a few pages pdfmd read the text layer mirrored. It still found the lines
and still kept the words in their printed order, but transcribed each one
letter-for-letter backwards:

```
dna \_ niJ taerg liated dna dehsilbup 5 ynaM tnereiffd
-> and ... in great detail and published as many different
```

**Why this needs a script rather than an eye.** It does not look
recoverable. `dehsilbup` reads as pure noise, so a pass sees it, correctly
judges it un-guessable under the Hard constraints -- too long to delete,
forbidden to invent -- reports it as residual garble, and calls the file
done. That is exactly how ONS_100 passed a full pass and stayed broken. The
text was recoverable the whole time.

cspell does not rescue you. It flags most of the run, which is how the pass
knew the words were unknown, but it cannot say *why*, and a few reversed
words are real tokens forwards -- `dna` matches DNA, and `ynaM` and `niJ`
pass too -- so even a zero-unknowns gate leaves some behind.

**Repairing it.** Word order is preserved, so the decode is per-token, not a
reversal of the whole line. Punctuation travels with the word and has to be
moved back by hand (`,gnitseretni` -> `interesting,`), and digits are not
reversed at all (`th6` for `6th`, `6581` for `1856`), which is why the
script reports rather than rewrites. Two further things to expect:

- **pdfmd often lays the mirrored run out as a pipe table.** Rebuilding that
  into prose changes the line count, so it falls outside this skill's
  line-break invariant -- it is a `restructure-flattened-md` repair that
  happens to be triggered here.
- **Text next to the run may simply be missing.** Both ONS_029 and IS_029
  lost their quotation's opening clause entirely, and ONS_053's fragment
  lost its heading block. Restore from the render, and check the sentence
  actually starts somewhere.

Mark the repair with an `<!-- OCR: ... -->` note saying the passage was
mirrored and naming the page it was restored from. Describe the garble
rather than quoting it, or the quoted tokens become cspell unknowns of their
own.

### Currency symbols that are not currency

A currency symbol in this corpus is far more often a misread glyph than a
price, because the symbols the OCR engine reaches for are shapes the
typewriter never had. Treat both of these as suspect on sight, then settle
each one by rendering the page — the Hard constraints apply here as
everywhere, so none of these is a from-context fix.

- **`¥` is suspect everywhere.** Of 36 in the corpus, 2 were real. It stands
  most often for **`½`**, the typewriter's half-fraction glyph: `¥%` →
  `½` (ONS_052, confirmed against the scan), `AR ¥ unit` and `¥% unit` →
  `½ unit` (ONS_078), `*¥2* abazi` → `½ abazi` (ONS_Supplement_197, where
  half-abazi is a real Georgian denomination). It also stands in for a
  letter: `Powys S¥22 5BX` → `SY22 5BX`, `Priissykkuria,¥Tünze` → `Frunze`.
  The rest sit inside already-garbled plate, Chinese or Arabic runs, where
  the `¥` is a symptom and the line belongs to another skill. It is genuine
  only as a book price in a recent issue's publications notice — `¥ 1800`
  (Bank of Japan, ONS_148), `CN¥ 368` (ONS_248).
- **`€` cannot predate the currency.** The symbol dates from 1996 and the
  euro itself from 1999, so it is certainly wrong in `IS_*`, `OP_*`,
  `ONS_0*` and `ONS_1[0-3]*`, and worth a look anywhere before `ONS_14*`.
  In ONS_124 it is a Greek lunate epsilon in a mint legend (`€MH CIC`), not
  money at all. In issues after 1999 a euro price is ordinary — check the
  issue date before touching one.

### A registered sign is a footnote digit

`®` is never the registered trademark sign in this corpus. 218 occurrences
across 47 files, and not one of them is genuine -- the recent issues, where a
product trademark could legitimately appear, carry it only inside mojibake
Arabic runs. What it stands for depends on where it sits:

- **A superscript footnote marker, after a word or a full stop** (~93, the
  common prose case): `an agreement®`, `...the Sichuan Rupee.®`, `points
  out®`. The corpus already writes these as Unicode superscripts -- 1788 of
  them, `¹` alone 398 times -- so the restoration is `agreement⁶`, not `6`.
  **The digit is not fixed, so there is no blanket substitution.** ONS_109
  alone reads `®` as ⁶ three times and ⁸ once, two of them on facing pages:
  `Japanese⁶ private castings` but `0.75 tael string⁸`. Render each one. The
  same file's other markers are garbled in their own ways (`!` for ¹, `?` for
  ², `\>` for ⁵), so the footnote list on the page is a useful cross-check
  once the render gives you the digit.
- **Debris inside a wrecked foreign-script or figure run** (~70): `ÚD®Ïv`,
  `# DESIGN **®** **® ®**`. The `®` is a symptom of the wreck, not a defect of
  its own -- that line belongs to `transcribe-foreign-script` or to
  `detect-missing-figures`, and fixing the symbol alone achieves nothing.
- **A misread `@` in an e-mail address** (8): `e-mail album®sonic net`,
  `E-mail: ®home.com`.

**Never rewrite any of these symbols inside an HTML comment.** The OCR skills
record their own evidence there, and that includes quoting the bad reading:
`IS_021` carries `<!-- script-ok ... reason=... (OCR had €°3 and 6-3) -->`,
where the `€` is the point of the sentence. A blanket sweep over the file
destroys the note. The same goes for `<!-- OCR: ... -->` placeholders.

### A quotation mark the OCR split in two

```
python3 .claude/skills/fix-ocr/scripts/detect_quote_pairs.py scan "<path>"
```

A typewritten `"` scans badly, and pdfmd routinely reads one printed mark as
two or three. ONS_111's publications notice came out `'""Chopmarks"` where
the page prints `"Chopmarks"`, and eleven runs in that one file were the
same defect.

**Do not screen for "an illogical quote combination".** A run of two or more
marks fires 3,657 times across 127 files, and that census is three different
things: about a quarter are not quotes at all (see the next section), and
plenty of the mixed ones are correct text -- the inner `'` in `("'Abd Allah
ibn Ibrahim")` is the ʿayn of the name. What is decidable from the text
alone is **opener ≠ closer**: pair each opening mark with its closer and
report the spans where the two disagree, or where either is a run. That is
664 spans across 99 files against 24,188 pairs that balance, and the script
already drops the classes that look like the defect without being it --
apostrophes, ʿayn, nested closings (`...the Name "Safi""`), runs after a
digit, and spans long enough to mean the pairing desynchronised rather than
that the quotes disagree.

**Settling a whole file by eye instead of one render at a time:**

```
python3 .claude/skills/fix-ocr/scripts/quote_crops.py <STEM>
```

writes `<STEM>-quotes.html` -- one row per finding, the Markdown line with
the run highlighted beside the band of the scan it came from, located by
matching the words before the mark against the page's text layer. Open it
next to the editor and work down the list; `--only quotes` (or
`superscript`, `question`) splits a long one into batches, and `--dpi 450`
enlarges the crops. A row whose words the OCR mangled, or whose phrase
repeats on several pages, says so and shows no image rather than showing
the wrong part of the scan -- so check that the Markdown and the crop are
the same sentence before trusting either. This is the cheap way to settle a
file when a person is doing the reading; it rewrites nothing.

Before either, check what the source is:

```
python3 .claude/skills/fix-ocr/scripts/classify_source.py scan <STEM>...
```

`SCAN` is the ordinary case -- a page image with an OCR layer behind it,
where every mark in the Markdown is a guess a render can settle.
`BORN-DIGITAL` is not: from ONS_186 (1998) onward the PDF carries the
publisher's own text, 57 files in all, so its punctuation was never OCR'd
and reading it off a page render is the wrong tool -- the quote screen may
still report runs there, but they are a different defect with a different
remedy. `NO-TEXT-LAYER` (ONS_177, ONS_197, OP_014) is a scan nobody OCR'd
into the PDF: nothing can locate words on those pages, so a crop sheet
cannot be built at all. `quote_crops.py` refuses both unless passed
`--anyway`.

`--stack` is the same crops for an agent doing the reading: labelled JPEG
sheets (`<STEM>-quotes-1.jpg`, ...) of five findings each instead of one
HTML page, with the Markdown printed to stdout, where text is cheap. Marks
in the same printed paragraph share a band. A file's worth of evidence then
costs two or three images rather than a render apiece -- ONS_053's fourteen
findings came to three sheets, and every one of them turned out to be the
same split `"`.

**The pair decides *that* it is wrong; only the render decides what it should
be.** The marks the OCR split do not tell you what was printed, and the
answer is not always a quotation mark at all: ONS_051's `''A Study of Holkar
State coinage"'` is a review heading that the page prints with no quotes
whatsoever. The Hard constraints apply here exactly as they do to any other
punctuation fix.

Three readings that are correct text, and must be left alone when you meet
them in the output:

- **a ʿayn inside a quotation** -- `("'Abd Allah ibn Ibrahim")`, `"'am"
  instead of "sanah"` (IS_018, where the file's own `script-ok` note records
  the عام). The script suppresses the names it knows; add to `AYN_NAMES`
  when a new one surfaces.
- **a nested quotation closing** -- `"...the title *yagbu* 'chief of a
  clan'"` and `"A Coin Bearing the Name "Safi""`. Two closers side by side
  are each doing their own job.
- **an inch mark** -- `10 3/8" x 7 3/8''` in a book description.

### A `''` that closes nothing is a question mark

The screen's third verdict, and the one ONS_165's worklist turned up: a
printed `?` scans as `''` on these pages, so a rhetorical question ends up
looking like a stray quote run.

```
Are we really meant to believe this''   ->  ... believe this?
as "Muhammad''", with question-mark     ->  "Muhammad?", with question-mark
In AH 568 and 56(9 or 7'')              ->  56(9 or 7?)
A fals of AH394''(B D Kochnev           ->  A fals of AH 394? (B. D. Kochnev
```

231 across 38 files, worst in the review articles of `ONS_15*`-`ONS_17*`,
where the author argues with other numismatists a question at a time.
ONS_165 alone had 15, one of them inside a sentence that goes on to say
*with question-mark i.e. he was not sure*.

**The PDF text layer repeats the error**, so `triage_percent.py`'s
text-layer shortcut cannot settle these -- both OCR passes read the same
`''`. Render each one. A `''` after a digit is a `SUPERSCRIPT` hit instead
(see below) and is just as often a `?`: `(404'')` is `(404?)`, `425''` is
`425?`.

### A quote run after a digit is a superscript

993 of those runs sit immediately after a digit, and they are OCR'd
superscript ordinals and footnote markers -- the `®` class of the section
above in another costume:

```
the 14'''  All-Russian Numismatic Conference   ->  14th
30""  November                                 ->  30th
the 33'"''  International Archaeometry Conf.   ->  33rd
7'''  century Byzantine coins                  ->  7th
```

**A digit before the run does not prove an ordinal**, so there is no
skip-after-a-digit rule either. ONS_111 p5 prints `...perpetuate his
sovereignty 828".` -- a plain closing quote after a year -- and ONS_120 p5
prints `"Capitalism and Material life 1400-1800", Braudel`, both verified on
the render. `AH 40(7'' or 6'')` is a footnote marker on a date.

What settles it is the word *after* the run, which is why the screen splits
the class in two:

- **`ordinal`** -- a century word, a month, `c.`/`cent` (but not `c/m`, which
  is a countermark), `year`, `regnal`, `anniversary`, `edition`, `standard`,
  `International`, or a connector with a century word just beyond it
  (`19"' and 20''' centuries`). 533 runs across 28 files. The suffix comes
  from the number -- 14 → th, 33 → rd, 21 → st, 11-13 → th -- and the
  restoration is **plain `14th`**: this corpus writes 3,599 ordinals that
  way and not one as `14ᵗʰ`. `ordinals` emits them as an `apply_edits.py`
  batch:

  ```
  python3 .claude/skills/fix-ocr/scripts/detect_quote_pairs.py ordinals <STEM> > edits.txt
  python3 .claude/skills/fix-ocr/scripts/apply_edits.py "<path>" edits.txt          # dry run
  python3 .claude/skills/fix-ocr/scripts/apply_edits.py "<path>" edits.txt --write
  ```

  Each edit carries the word that proved it -- `16''' century => 16th
  century`, not `16''' => 16th` -- so it fires only where the evidence is;
  a bare edit would sweep the footnote markers of the same shape elsewhere
  in the file, and 30 runs across 13 files are exactly that. The batch is
  still a candidate list, not evidence: confirm a sample per page against
  the render before `--write`, the same rule `punct_candidates.py` follows.

- **`check`** -- the other 344. Render each one. A footnote marker restores
  as a Unicode superscript **digit** (`⁶`), which is this corpus's
  convention with 1,817 of them already in place, and **the digit is not
  fixed** -- read it off the page and cross-check it against the footnote
  list, exactly as for `®`.

### Numbers that look like words
- Long runs of digits in the middle of a sentence (e.g., `511868515 that the first two`) are OCR'd images or stamps. Replace with `[illegible]` only if the user has asked for that style; otherwise leave a HTML comment `<!-- OCR: 511868515 -->` near the spot and remove the noise from the prose.

## Files that lost their punctuation wholesale

Some issues' PDF text layers dropped nearly every sentence-ending period (and many colons and decimal points): the file reads `…types Whereas…`, `17 30` for `17.30`, `No A7 2` for `No. A7.2`. Rendering each spot by hand does not scale to hundreds of marks, and the PDF text layer cannot help because it is missing them too. When a sample paragraph shows this, run a second, independent OCR over the renders and align it against the Markdown:

```
python3 .claude/skills/fix-ocr/scripts/punct_candidates.py <path> [--pages 2-9]
```

It prints one candidate per line — `<path>:LINE  md 'types'  page 'types.'  pN  --clip x0 y0 x1 y1` — for every aligned word whose trailing punctuation differs. Tesseract's reading is a candidate list, not evidence. Confirm candidates against the render (the printed `--clip` is ready to paste into the render command; several per page), then apply the confirmed ones in batches with `apply_edits.py`. Tesseract's `.`/`,`/`;`/`:` readings have agreed with the render in nearly every spot-checked case, so once a page's sample agrees, confirming the rest of that page by viewing the page render is enough; any candidate where tesseract's letters also differ from the Markdown needs its own look. Decimal points inside numbers (`17 30`, `2-4 1 1`) do not show up as trailing punctuation — grep for digit-space-digit runs and render those separately.

## Beyond spellcheck

After cspell-driven fixes, re-scan the file for patterns cspell cannot detect because the tokens are valid English words or punctuation. Start with a mechanical grep pass — these are known corpus confusions, and grep is more reliable than re-reading:

```
grep -nE ' amd | tbe | tne | arid | Mc\. [A-Z]| am [aeiou]| 1n | 0f ' "<path>"
```

(`arid` for `and`, `Mc.` for `Mr.` before a surname, `1n`/`0f` for `in`/`of`.) Every hit needs judgment — `arid` is also a real word — so check each in context before editing. Extend this list when a new real-word confusion surfaces in the corpus.

Run the currency grep too, excluding the HTML comments that quote bad OCR on purpose:

```
grep -nE '¥|€|®' "<path>" | grep -v '<!--'
```

Write the alternation, not a bracket class: `grep -nE '[¥€]'` matches these
multi-byte glyphs a byte at a time and reports every line holding a `£`,
which gave 14 false hits on a file carrying neither symbol.

Every `¥` hit needs checking and most resolve to `½`; a `€` hit in a
pre-1999 issue is certainly wrong; every `®` is wrong, but what replaces it
varies. See *Currency symbols that are not currency* and *A registered sign
is a footnote digit* above for what each one usually stands for.

Also run this one on its own — it needs no judgment on whether the backslash itself is garble, only on what to do with it:

```
grep -nE '\\[a-z]+' "<path>"
```

A backslash immediately before a lowercase letter is never a valid Markdown escape (CommonMark only allows escaping punctuation, e.g. `\*`, `\_`, `\|`) and never occurs elsewhere in this corpus, so every hit is OCR noise — commonly a misread diacritic, broken italic/reference marker, or part of a longer garbled run of letters and punctuation. Delete the backslash itself outright. Judge the token(s) it's embedded in the same way as any other garble: fix what you can read, and if the surrounding run is garbled beyond repair, leave it and report it (subject to the 12-character deletion limit in Hard constraints) rather than inventing a reading.

Then re-read for the patterns grep can't pin down:

- **Doubled trailing letter** — `coinagee` → `coinage`, `dependenciese` → `dependencies`. Remove the spurious letter; don't replace it with a period because the sentence looks unfinished — only if a render shows the period.
- **Doubled lowercase `e` after a name** — `Ashoka'se`, `Mauryans'e` → `Ashoka's`, `Mauryans'`.
- **Trailing `e` that is really a dropped period** — tokens like `B.Ce` or `(ce` where the `e` is a misread `.`. Leave these untouched by default: removing the `e` leaves an incomplete token, and supplying a period from context alone is forbidden. Only if you render the page (see Hard constraints) and it plainly shows `B.C.` is correcting `e`→`.` allowed — it is then the same glyph fix as `,`→`.`.
- **`am` vs. `an`** when followed by a vowel — `am other` → `an other` or `another` per context.
- **Comma (or semicolon) where a sentence plainly ends** — `…both obverse and reverse, The meaning of…`. Do **not** fix these from context. Collect them, then resolve each by rendering that page (see the render command in Hard constraints): a printed period → correct the `,` to `.`; a printed comma → it is the authors' own typo, leave it and note it in the report. A page render is the only reliable evidence here, and the swap is 1-for-1 so it does not disturb the line-count invariant.
- **A spelling the engine normalised** — the OCR's English language model rewrites the typist's forms into commoner ones, in letters and in case alike, and cspell cannot flag the result because the result is a real word. `supereeded` comes back as `superseded`, `Ghengis` as `Genghis`, `Muhammaden` as `Muhammadan`, `Trans-oxine` as `Trans-Oxiana`, `Al Moravids` as `Almoravids`. Suspect it wherever a 1970s typescript reads *too* cleanly — a correctly-spelled modern form in an otherwise idiosyncratic document. Resolve exactly as above: render, and restore what the page prints, typos included. This is the pattern that makes the render worth reaching for on a file cspell calls clean.

## Known real-word OCR confusions

Some OCR errors land on a real English word, so no dictionary addition will ever make cspell flag them — the token spellchecks clean every time, in every file, forever. `modem` for `modern` is the corpus's clearest case: 100+ occurrences across three dozen files, always the `rn`↔`m` letter confusion (see "Common OCR error patterns" above), never the telecommunications device.

`cspell.config.yaml`'s `flagWords` list is where these go, as `wrong->right` entries. cspell then reports every occurrence as `Forbidden word (wrong) fix: (right)` in the ordinary step-2 pass, case-insensitively and with the found token's own capitalization echoed in the suggestion (`Modem` → `Modern`). This is a corpus-wide, context-free correction — the opposite of the "Beyond spellcheck" grep list below, whose entries (`arid`, `tbe`, `am [aeiou]`, ...) are patterns that still need per-occurrence judgment because the matched string is sometimes correct as printed.

Only add an entry here once you've checked every single occurrence in `jons/*.md` and confirmed none of them is a legitimate use of the word — the same bar as a dictionary addition below, just inverted (there it's "confident this spelling is always right"; here it's "confident this spelling is always wrong"):

```
grep -rhoE '.{30}\b<word>\b.{30}' jons/*.md | less     # read a sample of every hit in context
```

If even one occurrence turns out to be a genuine use, the word belongs in the "Beyond spellcheck" grep list instead (or nowhere), not here. After adding an entry, re-run cspell on an affected file to confirm it now reports as forbidden, then apply the fix the same way as any other confirmed batch (`replace_all` for a single file, or `apply_edits.py` — see step 5).

## Dictionary updates

Three dictionaries live under `dictionaries/`:

- `chinese-numismatics.txt` — Wade-Giles romanized place names, dynasty/era names, scholars (e.g., `Hangchow`, `Tsung`, `Reischauer`).
- `islamic-numismatics.txt` — Arabic transliterations, mint names, rulers.
- `indian-numismatics.txt` — Sanskrit/Prakrit terms, dynasties, scholars (e.g., `Karshapana`, `Magadha`).

When a surfaced word is a legitimate term:

1. **Only add a word you are confident is correct**, not merely plausible. A dictionary entry permanently masks that spelling corpus-wide — if a garbled token gets added, every future occurrence of the same garble sails through spellcheck. Borderline cases go in the "left alone" report instead.
2. **Check it isn't already there.** The dictionaries are large enough that duplicates — including a copy in the *wrong* dictionary — won't be caught by eye:

   ```
   grep -inx "<word>" dictionaries/*.txt
   ```

   If it's already in another dictionary, don't add a second copy; mention it in the report if it looks misfiled.
3. Pick the dictionary that matches the subject of the article the word appears in. If the article is about Indian punchmarked coinage, terms go to `indian-numismatics.txt`. A scholar named in passing in a Chinese-numismatics article still goes into `chinese-numismatics.txt`.
4. Find the right section comment in the file (`# Chinese place names`, `# Scholars of...`, etc.) and append the new word **in alphabetical order within its section**. If no section fits, append it under a new comment heading at the end.
5. Preserve case as it appears in the text (e.g., `Karshapana` not `karshapana`), and add a lowercase variant too if the text uses it both ways.
6. Do not add transliterated glyphs that contain only non-Latin characters — cspell's `ar` dictionary handles Arabic.
7. After appending, re-run cspell to confirm the term no longer surfaces.

## Verification

After all edits and dictionary updates:

1. **Check the line-break invariant mechanically.** Every fix is an in-line edit — even one that inserts or deletes a punctuation mark — so the diff against the step-1 snapshot must not change the file's line *structure*:

   ```
   git diff --no-index --numstat <scratchpad>/<STEM>.before.md "<path>"
   ```

   Added lines must equal deleted lines. If they differ, a line break was merged or a line was deleted — find and undo that change before anything else. (Plain `git diff --numstat` is only equivalent when the file had no uncommitted changes before this pass.)

2. **Run cspell once more** and account for every remaining unknown word
   *individually*. For each one, say which it is:

   - a foreign-language gloss, or a proper noun left out of the dictionary
     deliberately — fine, name it in the summary;
   - garble you could not read even from the render — fine, but it must
     carry an `<!-- OCR: ... -->` marker at that spot saying so;
   - anything else — not fine. Go back and fix it.

   **Do not call the file done while an unknown is merely "residual garble"
   you looked at once and gave up on.** That judgment is what let ONS_100
   through: its `dehsilbup`/`liated`/`taerg` run was flagged by cspell, read
   as unrecoverable noise, reported, and signed off — when the passage
   was mirrored text that reverses straight back into English. Before
   writing a word off, run `detect_mirrored_text.py` over the file, and ask
   whether the run is garbled *or* merely transformed. Transformed text is
   recoverable; garble is not, and the two look identical until you test.

3. **Run the mechanical screens** that catch what cspell structurally
   cannot, and resolve or explain each hit:

   ```
   scripts/detect_mirrored_text.py scan "<path>"
   scripts/detect_quote_pairs.py scan "<path>"
   grep -nE '¥|€|®' "<path>" | grep -v '<!--'
   ```

   `detect_quote_pairs.py` reports five kinds of hit and none is settled
   from the text: a `QUOTES` span says the opener and closer disagree, a
   `SUPERSCRIPT` run says a quote run after a digit is an ordinal or a
   footnote marker, a `QUESTION` hit says a `''` closing nothing is probably
   a `?`, a `MARKER` hit says two or more marks after a period are a closer
   with the footnote marker folded into it, and a `QMARK` hit says a `?`
   that cannot end its sentence is a closing mark the scan misread. All five
   need the render before anything is edited — see the sections above.

   `SUPERSCRIPT ordinal` is the one hit the screen can also write: the
   `ordinals` subcommand emits an `apply_edits.py` batch for every run whose
   proving word it recognises (`16''' century`, `22"''July`, `3'" ed`,
   `May 31"`), each edit carrying that word so it fires only where the
   evidence is. Confirm a sample against a render, then apply the batch
   instead of rendering each one.

## What NOT to do

- Don't remove or merge line breaks — preserve every line break, including mid-sentence ones.
- Don't change a letter's case from context — not to start a sentence, not to make a proper noun look the way you expect. Correcting case is allowed only when you have rendered the page and seen the case actually printed (see Hard constraints).
- Don't punctuate from context — not to finish a sentence, not to restore a mark the OCR "should" have kept. Adding, changing, or removing a mark is allowed only when you have rendered the page and seen what is actually printed (see Hard constraints).
- Don't delete a run of more than 12 consecutive characters without supplying a replacement — leave it and report it instead.
- Don't rewrite prose for style — only fix OCR errors.
- Don't change British spellings to American or vice versa.
- Don't "correct" historical or transliteration variants (e.g., `Maurya` vs. `Mauryan`, `Karshapana` vs. `Kārṣāpaṇa`).
- Don't touch headings, image alt text, or front matter unless they contain obvious OCR garble.
- Don't batch many unrelated edits into a single `Edit` call — one logical fix per call so the user can audit the diff. (`replace_all` on one recurring identical misreading is fine, and so is `apply_edits.py`, which keeps one line per fix and prints each one's diff.)
- Don't add words to multiple dictionaries to be safe — pick the right one.
