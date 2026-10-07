---
name: clean-ocr-formatting
description: Repair three OCR layout artifacts in a `jons/` Markdown file -- per-word asterisks (`*word *` or `**word **`), words split with internal spaces (`Numi smat i c` → `Numismatic`), and paragraphs severed mid-sentence by a stray blank line where `pdfmd` read one physical line of the scan as its own block (including the case where the continuation begins with an OCR'd dash that Markdown then renders as a bullet). Use when an OCR'd file has passages wrapped in per-word emphasis marks, letter-spaced words, a sentence that breaks off mid-clause and resumes in the next paragraph, or a one-item bullet list that is really the middle of a sentence. Typically followed by the `fix-ocr` skill to clean up remaining single-word OCR errors.
---

# clean-ocr-formatting

This skill handles three OCR artifacts that show up together when the source PDF used letter-spaced text or per-character styling (common with title styling, italic body text, or laser-printed pre-1980 typescripts):

1. **Per-word asterisks** — every word wrapped in `*word *` or `**word **` instead of one span enclosing the phrase.
2. **Word-internal spaces** — `Numi smat i c` for `Numismatic`; `re lat i vely` for `relatively`.
3. **Severed paragraphs** — a physical line of the source PDF becomes its own Markdown "paragraph" with a `\n\n` after it, so one paragraph breaks into blocks that stop mid-clause. The tell is the line *before* the break (it ends with no terminal punctuation), not the capitalisation of what follows.

These usually appear together in the same passage; a heavy letter-spaced italic block produces all three at once.

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
   | `fake-list` | the continuation starts `- `, so Markdown renders a bullet | collapse **and** restore the dash — see below |
   | `hyphen-split` | the line ends on a hyphenated fragment (`Muzaf-`) | join into one word, no space; `fix` does it |
   | `maybe-severed` | `--loose` only: no terminal punctuation but the continuation is capitalised or a bare number | read it and decide by hand |

   **Why only one newline?** In CommonMark, `\n\n` is a paragraph break but a
   single `\n` inside a paragraph is a soft break that renders as a space.
   Removing one newline preserves the file's line-by-line structure (useful in
   diffs) while letting the text reflow as one paragraph. `fix` does this;
   when editing by hand, do the same rather than joining both lines into one.

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

   **Two findings that are not this bug.** Both look like severed paragraphs
   and belong to other skills:

   - a **glued heading** leaves the line above ending on a noun with no
     punctuation (`...Spink's NC., May 1977, 201 Books` / `1977 Lists of
     Books for sale...`). The paragraph break is real; the defect is `Books`
     being stuck to the line above → `restore-headings`.
   - a **flattened list or family tree** is full of ` - ` separators, where
     the dashes are structure, not a cut sentence → `restructure-flattened-md`.
     The script already skips lines with two or more ` - ` runs for this
     reason; if one slips through, don't collapse it.

   **Never** apply this pass to fenced code blocks, tables, real lists,
   headings, front matter, or verse where line breaks are semantic. The
   script skips all of these, which is the main reason to prefer it over a
   regex over the whole file.

4. **Rejoin word-internal spaces** one fragment at a time. No regex is safe across the board, because not every short token should be merged. For each broken phrase:

   - Read the surrounding sentence so you can judge what the original word should be.
   - Run cspell to surface broken fragments:
     ```
     cspell --config cspell.config.yaml --no-progress --no-summary --unique --words-only "<path>" | sort -u
     ```
   - Try joining adjacent fragments and verify the result is a real word.
   - Apply via `Edit`, quoting enough surrounding context that `old_string` is unique.

5. **Re-run cspell** when done. Remaining unknowns should be proper nouns or numismatic terms — hand those off to the `fix-ocr` skill for normal classification and dictionary updates.

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
- Don't collapse a break the script labelled `fake-list` or `maybe-severed` without looking at it. `fake-list` needs the dash read off the scan; `maybe-severed` is ambiguous by construction, and legitimate one-line paragraphs (table-of-contents entries, short bibliographic fields, untagged headings, masthead lines) live in that category.
- Don't widen the detection by matching on what follows the break. That was the old regex's mistake: it cost the skill every real instance in ONS_047, ONS_049, ONS_050 and ONS_051, because a severed line's continuation is capitalised about as often as not.
