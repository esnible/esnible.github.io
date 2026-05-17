---
name: fix-ocr
description: Find and correct OCR errors in a Markdown file from the `jons/` corpus (Oriental Numismatic Society Information Sheets). The text is OCR'd from English-language PDFs that often contain rare Chinese, Islamic, or Indian numismatic terms and occasional stray Arabic glyphs. Use when the user asks to clean up, proofread, or fix OCR in a `.md` file.
---

# fix-ocr

You are correcting OCR errors in a Markdown file produced by `pdfmd --ocr auto --lang eng+ara` (see `scripts/build.sh`). The text is English numismatic content. Errors are mechanical OCR mistakes, not authorial typos — treat them as such.

## Inputs

The user names a Markdown file, usually under `jons/`. If no path is given, ask once.

## Workflow

1. **Read the target file** in full so you have the surrounding context for every change.

2. **Run cspell** against the file using the project config:

   ```
   cspell --config cspell.config.yaml --no-progress --no-summary --unique --words-only "<path>" | sort -u
   ```

   This yields the unique unknown words. The project dictionaries (`dictionaries/{chinese,islamic,indian}-numismatics.txt`) already cover most legitimate terms, so anything that surfaces is either an OCR error or a numismatic term that should be dictionary-added.

3. **Classify each unknown word** by re-reading the line it appears on:
   - **OCR garble** — fix it via `Edit`. See "Common OCR error patterns" below.
   - **Legitimate numismatic term** — append to the appropriate dictionary (see "Dictionary updates").
   - **Proper noun the dictionaries don't cover** (modern scholar, place name, etc.) — also append to the closest-matching dictionary.
   - **Genuinely ambiguous** — leave it, and list it at the end for the user.

   Use the file's overall subject (Chinese vs. Islamic vs. Indian) to bias judgment. The first paragraphs of the file usually make this obvious; the `IS_###.md` numbering is not a reliable signal.

4. **Also scan for OCR errors cspell will NOT catch.** Spellcheck only flags non-words. Many OCR errors are real words used wrongly, or punctuation/whitespace glitches. Do a targeted re-read for the patterns in "Beyond spellcheck" below.

5. **Apply edits with the `Edit` tool**, one change at a time. For each edit:
   - Quote enough surrounding context that `old_string` is unique.
   - Never change quoted historical spellings or transliterations you cannot verify — when unsure, leave it.
   - Do not edit inside fenced code blocks, inline code (`` ` ``), URLs, or image references. The corpus rarely contains these, but check before editing.

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
- `(ce ` → `(c. `; `e` ↔ `.`

### Punctuation and stray glyphs
- `Indias` (no period) → `India.` — sentence-final period dropped after a capital
- Random Arabic / Hebrew glyphs in English paragraphs (e.g., `ف`, `(٠`) — delete. These come from `--lang eng+ara`. **Only delete a non-Latin glyph when it is clearly noise inside English prose.** If the file is discussing Arabic legends or transliterations and the glyph belongs there, leave it.
- Stray pipe characters (`|`, `\|`) inside running prose — usually delete.
- `—`, `~`, `--` runs left over from page breaks — collapse to a single em dash or remove.
- Sentence-initial garbage tokens like a lone `nem` at the top of a file — delete.

### Numbers that look like words
- Long runs of digits in the middle of a sentence (e.g., `511868515 that the first two`) are OCR'd images or stamps. Replace with `[illegible]` only if the user has asked for that style; otherwise leave a HTML comment `<!-- OCR: 511868515 -->` near the spot and remove the noise from the prose.

## Beyond spellcheck

After cspell-driven fixes, re-scan the file for these patterns, which cspell cannot detect because the tokens are valid English words or punctuation:

- **Sentence-final `e` for `.`** — `coinagee`, `B.Ce`, `(ce`. The final `e` is a misread period.
- **Doubled lowercase `e` after a name** — `Ashoka'se`, `Mauryans'e` → `Ashoka's`, `Mauryans'`.
- **Run-on caused by a dropped period** — look for a lowercase word immediately followed by a capitalized one with no period, e.g., `coinage The trend`. Insert the period if context warrants.
- **`am` vs. `an`** when followed by a vowel — `am other` → `an other` or `another` per context.
- **`(c.` vs. `(ce`** in regnal date parens.
- **Hard line breaks inside sentences.** The OCR output uses `\n\n` to separate physical lines on the page. If a paragraph has been split mid-sentence (line ends with a lowercase word and no punctuation, next line starts with a lowercase word), join them. **Do not** merge across actual paragraph boundaries.

## Dictionary updates

Three dictionaries live under `dictionaries/`:

- `chinese-numismatics.txt` — Wade-Giles romanized place names, dynasty/era names, scholars (e.g., `Hangchow`, `Tsung`, `Reischauer`).
- `islamic-numismatics.txt` — Arabic transliterations, mint names, rulers.
- `indian-numismatics.txt` — Sanskrit/Prakrit terms, dynasties, scholars (e.g., `Karshapana`, `Magadha`).

When a surfaced word is a legitimate term:

1. Pick the dictionary that matches the file's subject. If the file is about Indian punchmarked coinage, terms go to `indian-numismatics.txt`. A scholar named in passing in a Chinese-numismatics article still goes into `chinese-numismatics.txt`.
2. Find the right section comment in the file (`# Chinese place names`, `# Scholars of...`, etc.) and append the new word **in alphabetical order within its section**. If no section fits, append it under a new comment heading at the end.
3. Preserve case as it appears in the text (e.g., `Karshapana` not `karshapana`), and add a lowercase variant too if the text uses it both ways.
4. Do not add transliterated glyphs that contain only non-Latin characters — cspell's `ar` dictionary handles Arabic.
5. After appending, re-run cspell to confirm the term no longer surfaces.

## Verification

After all edits and dictionary updates, run cspell once more and confirm that the remaining unknown words are intentional (foreign-language glosses, proper nouns the user does not want dictionary-added, etc.). Report those in the final summary.

## Update the TODO tracker

After verification passes, check the box for this file in `jons/spellcheck-todo.md`. The entry looks like `[ ] [Information Sheet 01](IS_001.md)` — change `[ ]` to `[x]`. If the file is not listed there (rare — only for newly-added files), add it under "Files not in the published archive" at the bottom of that page.

## What NOT to do

- Don't rewrite prose for style — only fix OCR errors.
- Don't change British spellings to American or vice versa.
- Don't "correct" historical or transliteration variants (e.g., `Maurya` vs. `Mauryan`, `Karshapana` vs. `Kārṣāpaṇa`).
- Don't touch headings, image alt text, or front matter unless they contain obvious OCR garble.
- Don't batch many unrelated edits into a single `Edit` call — one logical fix per call so the user can audit the diff.
- Don't add words to multiple dictionaries to be safe — pick the right one.
