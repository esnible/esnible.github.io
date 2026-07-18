---
name: fix-ocr
description: Find and correct OCR errors in a Markdown file from the `jons/` corpus (Oriental Numismatic Society publications — `IS_###` Information Sheets, `ONS_###` newsletters and journals, `OP_###` occasional papers, and a few bare-numbered files). The text is OCR'd from English-language PDFs that often contain rare Chinese, Islamic, or Indian numismatic terms and occasional stray Arabic glyphs. Use when the user asks to clean up, proofread, or fix OCR in a `.md` file.
---

# fix-ocr

You are correcting OCR errors in a Markdown file produced by `pdfmd --ocr auto --lang eng+ara` (see `scripts/build.sh`). The text is English numismatic content. Errors are mechanical OCR mistakes, not authorial typos — treat them as such.

## Hard constraints

These override every other instruction in this skill. If a fix would violate one of them, leave the text as-is.

- **Never remove or merge line breaks.** Preserve every line break exactly as OCR'd, including hard breaks that fall mid-sentence. Never join two lines, even when a sentence is split across them.
- **Never change capitalization.** Leave every letter's case exactly as OCR'd. Do not capitalize sentence starts or proper nouns, and do not lowercase anything.
- **Never add punctuation.** Do not insert a period, comma, dash, apostrophe, or any other mark — not even to close a sentence or restore a mark the OCR appears to have dropped. You may delete stray punctuation glyphs that are clearly OCR noise; you may not add any.
- **Never delete a run of more than 12 consecutive characters.** A pure deletion — replacing text with nothing — may span at most 12 characters. To remove a longer run (OCR'd image digits, page-break garbage, a corrupted passage), you must substitute something in its place: a corrected reading, or an HTML comment such as `<!-- OCR: ... -->`. If you cannot supply a replacement, leave the run as-is and list it for the user.

Within these limits, still fix letter-level OCR garble: wrong letters, doubled or dropped letters, digit/letter swaps, and stray non-Latin glyphs.

## Inputs

The user names a Markdown file, usually under `jons/`. If no path is given, ask once.

## Workflow

1. **Read the target file** in full so you have the surrounding context for every change.

2. **Run cspell** against the file using the project config. Use the positional output as your working list — it gives `line:col` for every occurrence, so you can jump straight to each one and you won't miss repeats:

   ```
   cspell --config cspell.config.yaml --no-progress "<path>"
   ```

   For the summary at the end, the deduplicated form is handy:

   ```
   cspell --config cspell.config.yaml --no-progress --no-summary --unique --words-only "<path>" | sort -u
   ```

   The project dictionaries (`dictionaries/{chinese,islamic,indian}-numismatics.txt`) already cover most legitimate terms, so anything that surfaces is either an OCR error or a numismatic term that should be dictionary-added. Occurrence count is a useful signal: a token that appears several times spelled identically is probably a legitimate term; a one-off is more likely garble.

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

### Punctuation and stray glyphs
- Random Arabic / Hebrew glyphs in English paragraphs (e.g., `ف`, `(٠`) — delete. These come from `--lang eng+ara`. **Only delete a non-Latin glyph when it is clearly noise inside English prose.** If the file is discussing Arabic legends or transliterations and the glyph belongs there, leave it.
- Stray pipe characters (`|`, `\|`) inside running prose — usually delete.
- `—`, `~`, `--` runs left over from page breaks — delete the stray run. Do not replace it with an em dash or any other mark; adding punctuation is forbidden.
- Sentence-initial garbage tokens like a lone `nem` at the top of a file — delete.

### Numbers that look like words
- Long runs of digits in the middle of a sentence (e.g., `511868515 that the first two`) are OCR'd images or stamps. Replace with `[illegible]` only if the user has asked for that style; otherwise leave a HTML comment `<!-- OCR: 511868515 -->` near the spot and remove the noise from the prose.

## Beyond spellcheck

After cspell-driven fixes, re-scan the file for patterns cspell cannot detect because the tokens are valid English words or punctuation. Start with a mechanical grep pass — these are known corpus confusions, and grep is more reliable than re-reading:

```
grep -nE ' amd | tbe | tne | arid | Mc\. [A-Z]| am [aeiou]| 1n | 0f ' "<path>"
```

(`arid` for `and`, `Mc.` for `Mr.` before a surname, `1n`/`0f` for `in`/`of`.) Every hit needs judgment — `arid` is also a real word — so check each in context before editing. Extend this list when a new real-word confusion surfaces in the corpus.

Then re-read for the patterns grep can't pin down:

- **Doubled trailing letter** — `coinagee` → `coinage`, `dependenciese` → `dependencies`. Remove the spurious letter; never replace it with a period, even if the sentence then looks unfinished.
- **Doubled lowercase `e` after a name** — `Ashoka'se`, `Mauryans'e` → `Ashoka's`, `Mauryans'`.
- **Trailing `e` that is really a dropped period** — tokens like `B.Ce` or `(ce` where the `e` is a misread `.`. Leave these untouched: removing the `e` leaves an incomplete token, and adding the period is forbidden.
- **`am` vs. `an`** when followed by a vowel — `am other` → `an other` or `another` per context.

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

1. **Check the line-break invariant mechanically.** Every fix is an in-line substitution, so the diff must not change the file's line structure:

   ```
   git diff --numstat "<path>"
   ```

   Added lines must equal deleted lines. If they differ, a line break was merged or a line was deleted — find and undo that change before anything else.

2. **Run cspell once more** and confirm that the remaining unknown words are intentional (foreign-language glosses, proper nouns the user does not want dictionary-added, etc.). Report those in the final summary.

## Update the TODO tracker

After verification passes, check the box for this file in `jons/spellcheck-todo.md`. Entries live inside Markdown tables organized by year — a cell looks like `| [ ] [Newsletter No. 152](ONS_152.md) |` — so quote the checkbox together with the link text to make the edit unique, and change `[ ]` to `[x]`. If the file is not listed there (rare — only for newly-added files), add it under the "Files not in the published archive" section at the bottom of that page.

## What NOT to do

- Don't remove or merge line breaks — preserve every line break, including mid-sentence ones.
- Don't change the capitalization of any letter.
- Don't add punctuation of any kind, even to finish a sentence or restore a mark the OCR dropped.
- Don't delete a run of more than 12 consecutive characters without supplying a replacement — leave it and report it instead.
- Don't rewrite prose for style — only fix OCR errors.
- Don't change British spellings to American or vice versa.
- Don't "correct" historical or transliteration variants (e.g., `Maurya` vs. `Mauryan`, `Karshapana` vs. `Kārṣāpaṇa`).
- Don't touch headings, image alt text, or front matter unless they contain obvious OCR garble.
- Don't batch many unrelated edits into a single `Edit` call — one logical fix per call so the user can audit the diff. (`replace_all` on one recurring identical misreading is fine.)
- Don't add words to multiple dictionaries to be safe — pick the right one.
