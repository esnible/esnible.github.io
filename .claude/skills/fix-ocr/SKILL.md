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

## Reading the scan without paying for it twice

Every image this skill asks for — a tile sheet, a crop sheet, a page render —
is read once and then rides along in the conversation for every turn that
follows. On a long file that compounding is the pass's largest cost: ONS_157
took thirty-six images, and most of them were still being carried at the end
of a job they had finished contributing to.

Two habits keep it down, and neither costs accuracy.

**Send the eye-work to a subagent.** Dispatch a worker with the sheet paths
and the question, and have it reply with a verdict list — tile ID, line, the
reading — rather than with the pictures. The images land in the worker's
context and are discarded with it, so a page costs what it costs once. Keep
the deciding here: the worker reports what the scan shows, this pass decides
what to write.

**Stack the findings before looking.** `shared/crop_sheets.py` cuts five or
six findings onto one labelled sheet, and `garble_tiles.py` does the same for
disputed words. Reaching for a render per finding is the habit to break —
`detect_script_garble.py render` is for the one candidate a sheet could not
place, not for the first forty.

A whole-page render still beats a stack of crops when the question is about
the page rather than a word — which footnote number is printed, how a table
is ruled, whether a legend is type-set or drawn. Reach for it then, and for a
file-wide question read the page at half scale, which is legible for body
text at a quarter of the tokens.

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

   Three of those classes have screens, and all three read the Markdown alone — no render, no PDF, milliseconds each. Run them before the re-read, because each is invisible to cspell *and* to the five rendering screens in `docs/screens.tsv`:

   ```
   python3 .claude/skills/fix-ocr/scripts/detect_dropped_punct.py scan "<path>"
   python3 .claude/skills/fix-ocr/scripts/detect_marker_noise.py scan "<path>"
   python3 .claude/skills/fix-ocr/scripts/detect_presentation_forms.py scan <STEM>
   ```

   The first says whether this file is one of the 42 that lost their sentence-ending periods wholesale (see `references/dropped-punctuation.md`); the second finds the bare `^` the quote screen cannot match. Neither writes anything: both report candidates for a render to settle, which is the only evidence Hard constraints allow.

   The third is different, and is the one screen in this skill allowed to write on its own evidence. It folds Arabic Presentation Forms — `U+FB50–FDFF`, `U+FE70–FEFF` — back to ordinary Arabic. Those codepoints encode a letter together with its contextual shape, which correct Arabic never needs; the publisher's typesetting software emits them into the PDF text layer and `pdfmd` copies them faithfully. **This is not OCR**: every affected file is born-digital and ONS_186 or later, and none of the ~190 scanned-era files has one. `apply` changes no word and makes no judgement — it replaces a letter's compatibility encoding with the letter, and asserts that the text with all Arabic removed is byte-identical before and after. Because every new issue is born-digital, new issues are the ones that keep producing these, so run it on each new file rather than treating the corpus sweep as finished:

   ```
   python3 .claude/skills/fix-ocr/scripts/detect_presentation_forms.py apply <STEM>
   ```

   Do **not** reach for `unicodedata.normalize("NFKC", text)` instead. It folds the same characters correctly and also turns `½` into `1⁄2` — which `references/suspect-symbols.md` exists to *restore* — and the corpus's 1,788 Unicode superscripts into digits.

   **Read the suspects off the scan, all at once.** The PDF's own text layer is a second OCR of the same page, independent of `pdfmd`'s, and where the two disagree is where the garble is. `garble_tiles.py` cuts every such word, plus a word of context either side, out of the page image at the scan's own pixels and packs the tiles onto one or two labelled sheets, so a whole file is two or three thousand image tokens instead of a render per word:

   ```
   python3 .claude/skills/fix-ocr/scripts/garble_tiles.py sheets <STEM>     # Read each sheet it prints
   python3 .claude/skills/fix-ocr/scripts/garble_tiles.py edits <STEM> replies.txt > edits.txt
   python3 .claude/skills/fix-ocr/scripts/apply_edits.py <path> edits.txt   # dry run, then --write
   ```

   A tile is a cspell hit the two OCRs do not spell alike, or a real word in the Markdown against a different real word in the text layer (the `modem`/`modern` class cspell cannot see). A non-word both OCRs read identically is left out as probably printed, and so is a correct Markdown word whose text-layer counterpart is a non-word. Pages whose text layer is font-encoded noise fall back to tesseract's boxes from `locate_on_page.py`'s cache, built on first use. Born-digital files are refused.

   **Run a second round with `--agreed --only-spell`.** On many scans `pdfmd` kept the PDF's own text layer rather than re-OCRing, so the two "OCRs" are one and their agreement proves nothing. ONS_159's first round tiled 158 words, and the second found 260 more lines of plain garble (`surpnsmg`, `stmck`, `wntten`) that both readings shared.

   Tiles are the scan's own pixels: cut straight from the embedded image when it is placed square, or rendered at the scan's own dpi when it is deskewed, and never enlarged unless `--zoom n` asks (each pixel drawn as an exact n-by-n block, at n² the image tokens). A 72-dpi scan gives 72-dpi tiles. Any crop you cut for yourself follows the same rule: no `resize` without `Image.NEAREST` and a whole-number factor, and no image over 1568 pixels on a side, which the API would shrink with interpolation before you see it. The manifest on stdout gives each tile's ID, line, the Markdown span between «», and the text layer's reading when it differs. Write replies only for the tiles whose print differs from the Markdown span. Silence accepts the span:

   ```
   a7 Sasaman
   a12 iam. => Diam.      # echoing the span makes `edits` refuse a reply written against an older manifest
   a30 ?                  # unreadable: left as OCR'd, listed for the user
   ```

   The reading replaces the whole span, so carry over any markup in it (`*`, `<sup>6</sup>`). A reply may also name a line instead of a tile, `L486 ^jJï => قلوغ`, for a reading the eye found beside a tile; its `old` must be on that line once. `edits` applies every reply to a copy and writes one whole-line edit per changed line, so several readings on one line cannot collide. Every Hard constraint still applies: a case or punctuation fix is allowed because the tile is the render. Check that the tile shows the same words as the context in the manifest. A tile placed by a misaligned text layer shows a neighbouring word, and the `pdf:` reading usually gives that away.

   **Write in everything you read; never leave a legible tile for another skill to look at again.** A foreign-script legend (Arabic, Persian, Greek, Pahlavi) goes in as its real codepoints, a superscript or footnote marker as `<sup>…</sup>` (never a Unicode superscript digit in new work). Unmarked foreign-script tokens are tiled for this reason, and a tile of a few glyphs is the cue to crop the whole legend at native pixels and read it. A reading nothing on the page corroborates still goes in, followed on the same line by an inline marker, so `transcribe-foreign-script`'s screen lists it for checking. Which marker depends on what you actually did, and from a tile it is almost always the third:

- `script-ok` when the article's own gloss or transliteration confirms the reading;
- `script-guess page=N spellcheck=… reason=…` when you rendered the page, read the strokes and ran `detect_script_garble.py spellcheck` on the result, and nothing corroborated it;
- **`script-unchecked page=N reason=…` when all you had was the tile** — no page render, no cspell, no corroboration search. That is the normal case here, and it is the right answer rather than a lesser one: a tile that plainly shows خاقان where the Markdown has `field:,jtil\>-.` has told you something, and leaving the garble in place throws it away. Name the tile and the span it replaced in the reason. `UNCHECKED` counts towards that screen's exit status, so the line stays on a worklist until somebody runs Tier 2 on it. Only a glyph the scan genuinely cannot resolve stays as OCR'd: reply `?`, or write `script-deferred` saying what was tried. The marker goes inline because an edit may not add a line, and the screen counts an inline marker against its own line.

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

### The classes with their own screen and their own reference

Six classes of defect are large enough to carry their own screen and their own
reference file. **Run the screens first — every one of them reads the Markdown
alone, so all six together cost milliseconds and not one render — and open a
reference only when its screen has something to say.** On a file where four of
them report zero, four of these are pages you never pay for.

| screen | what it finds | open when non-zero |
|---|---|---|
| `detect_mirrored_text.py scan <STEM>` | a page pdfmd read mirrored, every word transcribed backwards: `dehsilbup` is `published`. Reads as unrecoverable noise and is not | [`references/mirrored-text.md`](references/mirrored-text.md) |
| the `¥`, `€` and `®` grep under *Beyond spellcheck* | a symbol standing in for a shape the typewriter had: `¥` is usually `½`, `®` is always a footnote digit, `€` cannot predate 1999 | [`references/suspect-symbols.md`](references/suspect-symbols.md) |
| `detect_quote_pairs.py scan "<path>"` | one printed `"` read as two or three; a `''` that closes nothing and is a `?`; a quote run after a digit that is an ordinal or a footnote marker | [`references/quote-pairs.md`](references/quote-pairs.md) |
| `detect_marker_noise.py scan <STEM>` | the characters pdfmd leaves standing where the scan printed something else — `^` for a superscript, `«`, `¬`, a `\>` for a letter | [`references/garble-traces.md`](references/garble-traces.md) |
| `detect_dropped_punct.py scan <STEM>` | the 42 files whose text layer dropped nearly every sentence-ending period, and the 43 carrying an isolated handful | [`references/dropped-punctuation.md`](references/dropped-punctuation.md) |
| `detect_confused_glyphs.py scan <STEM>` | the confusions that land *on a word* and so hide from cspell: a diacritic read as a capital (`MansQr`), a digit read as a letter (`K6ln`), a welded range (`AD 17191748`), a bracket for a letter (`t)pe`) | [`references/confused-glyphs.md`](references/confused-glyphs.md) |

Not one of the six is settled from the Markdown. Each reference says what its
screen's findings mean and what evidence can settle them; the Hard constraints
above still decide what you are allowed to write.

### Numbers that look like words
- Long runs of digits in the middle of a sentence (e.g., `511868515 that the first two`) are OCR'd images or stamps. Replace with `[illegible]` only if the user has asked for that style; otherwise leave a HTML comment `<!-- OCR: 511868515 -->` near the spot and remove the noise from the prose.

## Files that lost their punctuation wholesale

Some issues' PDF text layers dropped nearly every sentence-ending period (and
many colons and decimal points): the file reads `…types Whereas…`, `17 30` for
`17.30`. Rendering each spot by hand does not scale to hundreds of marks, and
the PDF text layer cannot help because it is missing them too.

`detect_dropped_punct.py scan <STEM>` says whether this is such a file, and
the verdict is reliable — the shape fires 0.01 times per 1000 words where the
punctuation survived and 4-6 times where it did not. **WHOLESALE** (42 files)
sends you to `punct_candidates.py`; **ISOLATED** (43 files) is a handful of
spots that crop sheets settle one at a time.

The whole procedure — the second OCR and the alignment, what `--apply` may
place by itself, why it must be run only once, and the three sweeps that have
to come back empty before the pass is done — is in
[`references/dropped-punctuation.md`](references/dropped-punctuation.md).

## Beyond spellcheck

After cspell-driven fixes, re-scan the file for patterns cspell cannot detect because the tokens are valid English words or punctuation. Start with a mechanical grep pass — these are known corpus confusions, and grep is more reliable than re-reading:

```
grep -nE ' amd | tbe | tne | arid | Mc\. [A-Z]| am [aeiou]| 1n | 0f ' "<path>"
grep -nE '[a-z] m [a-z]{2,}' "<path>"
grep -nE '\b(ot|ol|tor)\b' "<path>"
grep -nE '(^|[^@.[:alnum:]])com([^.[:alnum:]/]|$)' "<path>"
```

(`arid` for `and`, `Mc.` for `Mr.` before a surname, `1n`/`0f` for `in`/`of`.)

**`f` read as `t` or `l`: `ot`/`ol` for `of`, `tor` for `for`.** The single
largest real-word class in this corpus and invisible to cspell, which has all
four in its bundled dictionaries -- `tor` is a rocky peak, `com` an
abbreviation. ONS_162 carried 37 `ot`, 11 `ol` and 12 `tor` through a full
fix-ocr pass without one of them surfacing. Every instance in that file was
`of` or `for`.

`com` belongs with them -- it is `coin` -- but only away from an address:
ten of ONS_162's twenty were `.com` or `@...com`. Match it as
`(?<![@.\w])\bcom\b(?![.\w/])`.

**A digit inside a short word.** `f1g` for `fig`. cspell skips any token
containing a digit, so a one-character substitution inside a word is silent
however obvious it looks. Cheap to screen:

```
grep -nE '\b[a-z]{1,4}[0-9][a-z]{1,4}\b' "<path>"
```

ONS_162 had two hits and both were real. Expect few, and expect them to have
survived everything else.

### A diacritic read as a capital, a digit read as a letter

```
python3 .claude/skills/fix-ocr/scripts/detect_confused_glyphs.py scan <STEM>
python3 .claude/skills/shared/survey.py show --screen glyphs      # the worklist
```

Six shapes with one cause: the OCR read a diacritic, a digit, a bracket or a
dash as something else, and landed somewhere no spellcheck can follow —
`al-JalTl` for `al-Jalīl`, `K6ln` for `Köln`, `1010-1 Oil` for `1010-1011`,
`AD 17191748` for `AD 1719-1748`, `t)pe` for `type`. This is the `glyphs` row
of `docs/screens.tsv`; it reads the Markdown alone, so it costs milliseconds
and needs no render, and it exits non-zero while anything is outstanding,
which is why Verification leans on it as the gate. **13,976 findings across
199 files**, and on ONS_162 — a file that had already been through a full
fix-ocr pass — 61 of its 67 `CAPITAL` hits were real defects every other
screen had walked past.

What each of the six labels means, which digit decodes to which letter, how to
tell a systematic diacritic confusion from a few spots, and how to retire a
finding the scan shows is really printed:
[`references/confused-glyphs.md`](references/confused-glyphs.md).

**A standalone `m` between two words is `in`.** It is the corpus's commonest
real-word confusion after `modem`, and it hides from everything: cspell has
no opinion on a one-letter token, and `rn`/`m` substitution never enters into
it. 530 instances across 41 files. ONS_162 alone had 13 -- `a brief pause m
the campaign`, `diamond mines m its territories`, `the name selim m the last
line`.

It stays in this grep list rather than going into `flagWords` because two of
those 13 were genuine and a blanket rule would have destroyed both: `the
uncial m with two dots within it`, where the letter itself is the subject,
and `situated at 2457 m above sea level`, where it is metres. Check what sits
either side -- a unit or a quoted letterform is real, anything else is `in`. Every hit needs judgment — `arid` is also a real word — so check each in context before editing. Extend this list when a new real-word confusion surfaces in the corpus.

Run the currency grep too, excluding the HTML comments that quote bad OCR on purpose:

```
grep -nE '¥|€|®' "<path>" | grep -v '<!--'
```

Write the alternation, not a bracket class: `grep -nE '[¥€]'` matches these
multi-byte glyphs a byte at a time and reports every line holding a `£`,
which gave 14 false hits on a file carrying neither symbol.

Every `¥` hit needs checking and most resolve to `½`; a `€` hit in a
pre-1999 issue is certainly wrong; every `®` is wrong, but what replaces it
varies. `references/suspect-symbols.md` has what each one usually stands
for.

Also run this one on its own — it needs no judgment on whether the backslash itself is garble, only on what to do with it:

```
grep -nE '\\[a-z]+' "<path>"
```

A backslash immediately before a lowercase letter is never a valid Markdown escape (CommonMark only allows escaping punctuation, e.g. `\*`, `\_`, `\|`) and never occurs elsewhere in this corpus, so every hit is OCR noise — commonly a misread diacritic, broken italic/reference marker, or part of a longer garbled run of letters and punctuation. Delete the backslash itself outright. Judge the token(s) it's embedded in the same way as any other garble: fix what you can read, and if the surrounding run is garbled beyond repair, leave it and report it (subject to the 12-character deletion limit in Hard constraints) rather than inventing a reading.

**A word split in two, where both halves are innocent.** `Bacharach, J L and
Aw ad H E` is `Bacharach, J.L. and Awad, H.E.` -- and nothing above sees it.
cspell passes `Aw` and `ad` because both are words; the split leaves no
trace character; and the surrounding reference reads plausibly enough that a
re-read slides over it. `clean-ocr-formatting` owns the obvious form
(`Numi smat i c`), but not the two-token case.

What does find it is the test this skill already mandates for unknown
proper nouns -- *does the file spell it correctly somewhere else?* -- applied
to pairs rather than to cspell's hit list. ONS_162 spells `Awad` correctly
sixty lines earlier.

```
python3 - "<path>" <<'EOF'
import re, sys
body = re.sub(r'<!--.*?-->', '', open(sys.argv[1]).read(), flags=re.S)
known = {w.lower() for w in re.findall(r'\b[A-Za-z]{4,}\b', body)}
seen = set()
for m in re.finditer(r'(?=\b([A-Za-z]{1,4}) ([A-Za-z]{1,4})\b)', body):
    a, b = m.groups()
    if len(a + b) >= 4 and (a + b).lower() in known and (a, b) not in seen:
        seen.add((a, b))
        print(f"{a} {b}  ->  {a+b}")
EOF
```

**The lookahead is load-bearing.** With an ordinary consuming match, `and Aw`
is tested first, eats the boundary, and `Aw ad` is never considered at all --
which is exactly how this was missed the first time. Zero-width matching lets
the candidate pairs overlap.

Expect around twenty candidates a file and only a handful real: `may be`,
`can not`, `web site`, `a part` are ordinary English that happens to join
into another word, and `The re` fires on every `The reading`. Judge each.
ONS_162's real hits were `Aw ad` -> `Awad` and `T his` -> `This`.

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
   scripts/detect_confused_glyphs.py scan <STEM>
   grep -nE '¥|€|®' "<path>" | grep -v '<!--'
   ```

   `detect_confused_glyphs.py` exits non-zero while anything is outstanding,
   so it doubles as the gate: a clean exit means no mid-word capital, no
   letter-for-digit, no welded range and no bracket-for-a-letter is left
   unsettled, either fixed or carrying a `glyph-ok` marker that says the scan
   prints it. It is the one screen here that catches defects cspell cannot
   see *because they are words* — see `references/confused-glyphs.md`.

   `detect_quote_pairs.py` reports five kinds of hit and none is settled
   from the text: a `QUOTES` span says the opener and closer disagree, a
   `SUPERSCRIPT` run says a quote run after a digit is an ordinal or a
   footnote marker, a `QUESTION` hit says a `''` closing nothing is probably
   a `?`, a `MARKER` hit says there are more marks after a period than
   the page prints -- a footnote marker folded into the closer, or a doubled
   closer, and only the render says which -- and a `QMARK` hit says a `?`
   that cannot end its sentence is a closing mark the scan misread. All five
   need the render before anything is edited — see
   `references/quote-pairs.md`.

   `SUPERSCRIPT ordinal` is the one hit the screen can also write: the
   `ordinals` subcommand emits an `apply_edits.py` batch for every run whose
   proving word it recognises (`16''' century`, `22"''July`, `3'" ed`,
   `May 31"`, `the early 6\\* century`), each edit carrying that word so it
   fires only where the evidence is. The `\\*` form is the same superscript
   set as an escaped asterisk rather than as quote marks; the screen reads
   it only where it resolves to an ordinal, because a `\\*` after a digit is
   as often a footnote marker, and those are settled one page at a time. Confirm a sample against a render, then apply the batch
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
