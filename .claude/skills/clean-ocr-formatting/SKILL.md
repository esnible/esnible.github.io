---
name: clean-ocr-formatting
description: Strip OCR-introduced per-word asterisks (`*word *` or `**word **`) and rejoin words split with internal spaces (e.g., `Numi smat i c` → `Numismatic`, `re lat i vely` → `relatively`). Use when an OCR'd Markdown file has whole passages wrapped in per-word emphasis marks, or has letter-spaced words that the OCR engine read as separate tokens. Typically followed by the `fix-ocr` skill to clean up remaining single-word OCR errors.
---

# clean-ocr-formatting

This skill handles two OCR artifacts that show up together when the source PDF used letter-spaced text or per-character styling (common with title styling, italic body text, or laser-printed pre-1980 typescripts):

1. **Per-word asterisks** — every word wrapped in `*word *` or `**word **` instead of one span enclosing the phrase.
2. **Word-internal spaces** — `Numi smat i c` for `Numismatic`; `re lat i vely` for `relatively`.

These usually appear together in the same passage; a heavy letter-spaced italic block produces both at once.

## Inputs

The user names a Markdown file, usually under `jons/`. If no path is given, ask once.

## Workflow

1. **Read the file** and identify the affected line ranges. The artifact is almost always localised to one section or page — not the whole document. Quote the start and end lines back to the user before editing if the range is non-obvious.

2. **Strip per-word asterisks** in the affected range.

   First, preview the change by dumping to stdout (do NOT edit in place yet):

   ```
   sed -n '<start>,<end>p' "<path>" | sed -E 's/\*+//g; s/  +/ /g'
   ```

   Inspect the output. If it reads cleanly, apply with `sed -i` and a backup:

   ```
   sed -i.bak -E '<start>,<end> { s/\*+//g; s/  +/ /g; }' "<path>"
   ```

   Diff `<path>` against `<path>.bak`. If correct, `rm <path>.bak`. If wrong, `mv <path>.bak <path>` to revert.

   If the range has mixed legitimate formatting (a real `*emphasis*` span you want to keep), use `Edit` line by line instead — never blanket-strip in that case.

3. **Rejoin word-internal spaces** one fragment at a time. No regex is safe across the board, because not every short token should be merged. For each broken phrase:

   - Read the surrounding sentence so you can judge what the original word should be.
   - Run cspell to surface broken fragments:
     ```
     cspell --config cspell.config.yaml --no-progress --no-summary --unique --words-only "<path>" | sort -u
     ```
   - Try joining adjacent fragments and verify the result is a real word.
   - Apply via `Edit`, quoting enough surrounding context that `old_string` is unique.

4. **Re-run cspell** when done. Remaining unknowns should be proper nouns or numismatic terms — hand those off to the `fix-ocr` skill for normal classification and dictionary updates.

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

## What NOT to do

- Don't blanket-strip asterisks from the whole file — only the affected ranges. Legitimate `*emphasis*` or `**bold**` elsewhere must survive.
- Don't merge tokens that already form valid English (`to be` is two words, not `tobe`).
- Don't change British spellings or rare transliterations — defer those to the user or to the `fix-ocr` skill.
- Don't touch fenced code blocks, inline code, URLs, image references, or front matter.
- Don't run destructive `sed -i` without a `.bak` and a post-edit diff check — the changes are far-reaching and easy to over-apply.
