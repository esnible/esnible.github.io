---
name: restore-lists
description: Find lists in a `jons/` Markdown file that do not render as lists -- items `pdfmd` glued into one paragraph (`1A: Coins ... 1341. 1B: Coins ...`), labelled lines or paragraphs kramdown joins or leaves as prose (`i. ...<br>` / `ii. ...`, `a) ...`, `(1) ...`), or items whose labels the OCR dropped altogether -- and restore them to Markdown list structure. Use when a file's numbered or lettered items read as running text, when a list on the scan is indented or set line by line and the Markdown is not, or when working the `lists` row of `docs/screens.tsv`.
effort: high
---

# Restoring lists

A list on the page is easy to see: each item starts a new line, at the same
left edge as the others, usually behind a label. `pdfmd` reads it as running
text, and the Markdown comes out in one of three shapes:

```
1A: Coins bearing the Islamic dates 1341 and 1341. 1B: Coins bearing ...
```
```
i. The silver 100 kurus piece, dated 1934. ...
ii. The silver 1 lira of 1940 and 1941, ...
```
```
The coins can be described as follows: Obv. 5 pellets in quartered square
in centre, ... Wt. 3.4g. Obv. As last, but 'Sa' is clearly visible. Wt. 1.7g. ...
```

The first is items glued into one paragraph. The second looks like a list in
the source and renders as **one paragraph**: kramdown has no list marker
for `i.`, and a single newline is a space. The third lost its labels
(`1.`-`8.`) altogether, so nothing in the Markdown says a list was ever
there. Every one of these was in ONS_130 after a clean-ocr pass had called
the file done.

## The convention

| On the page | In the Markdown |
|:--- |:--- |
| `1.` `2.` `3.` | an ordered list; `{: start="N"}` when it does not start at 1 (the repo's `scripts/fix_list_starts.rb` sets these) |
| any other label -- `1)`, `(1)`, `i.`, `(ii)`, `a)`, `A.`, `1A:`, `1(b)` | a `{: .labelled}` bullet list, with the printed label copied as the first text of each item |
| several printed lines inside **one** item (Obv. / Rev., Copper / Obverse / Reverse, an address) | `<br>` at the end of each line, continuation lines indented under the item |

```
The first series ... can be subdivided into two.

{: .labelled}
- 1A: Coins bearing the Islamic dates 1341 and 1341.
- 1B: Coins bearing the Anno Domini dates of 1926 and 1928.
```

`assets/main.scss` sets `ul.labelled { list-style: none; }`, so the label is
the only marker a reader sees. Without the stylesheet (GitHub's preview) the
list shows a bullet and the label, which is still a list.

Why bullets and not `{: type="i"}` on an ordered list: kramdown does render
`<ol type="i">`, but only for the five counter styles HTML has. `1A:`,
`1(b)`, `(4)` and `i)` have none, and an ordered list with a type puts `1.`
`2.` in the source where the page prints `i.` `ii.` -- the label is what
`fix-ocr` and cspell need to see, and what a reader checking the scan
compares. One form for every label is one form to lint.

**`<br>` is for line breaks inside an item, never for the boundary between
items.** The corpus used to write labelled lists as `<br>` lines (ONS_048,
ONS_106, ONS_111, IS_008, ONS_139); those render as one paragraph, and
`lint` reports them.

### kramdown traps

All tested against the kramdown and GFM parser Jekyll uses:

- **`1)` is not a list marker** in kramdown. 204 lines in 28 files open
  with `1)` or `(1)` and render as running paragraphs, which is why the
  convention sends every label but `N.` to `.labelled`.
- **An IAL needs a blank line above it.** Without one, `{: .labelled}`
  attaches to the paragraph above (`<p class="labelled">`) and the list
  renders with bullets.
- **A list inside a numbered item** needs a blank line after the item's
  text and four spaces of indent, IAL included:
  ```
  5.  The following lists have been received:

      {: .labelled}
      - i. Stephen Album — lists 77, 78, 79 and 80.
      - ii. Omar Hamidi ...
  6.  Available from the Indian Books Centre ...
  ```
- **A loose list** (blank lines between items) wraps each item in `<p>`.
  Harmless, and the right choice when items carry `<br>` lines, since it
  keeps them readable in the source.

## The screener

```
detect_lists.py lint ONS_130              # Markdown only, under a second for the corpus
detect_lists.py lint jons/*.md
detect_lists.py screen ONS_130            # scan against Markdown
detect_lists.py screen ONS_130 -v         # include OK and UNPLACED runs
detect_lists.py screen --all              # about 50 s for the corpus
detect_lists.py screen ONS_130 --loose    # add RUN-ON
detect_lists.py rows ONS_130 > rows.tsv   # crop_sheets.py rows
python3 .claude/skills/shared/crop_sheets.py sheets --rows rows.tsv --out ONS_130-lists
```

(`.claude/skills/restore-lists/scripts/detect_lists.py`; `screen` and `rows`
read PDFs from `$ONS_ARCHIVE_DIR`.) Each exits 1 when it reports anything.

### `lint`: the Markdown alone

| Verdict | What it means |
|:--- |:--- |
| `LINED` | two or more lines or paragraphs opening with labels that count up, which kramdown does not read as list items -- `1)`, `(a)`, `ii.`, `1A:`, with or without `<br>` |
| `UNMARKED` | a bullet list whose items open with labels, with no `{: .labelled}` above it, so it renders a bullet *and* a label |
| `IAL` | a `{: .labelled}` with no blank line above it, with no bullet item under it, or over an item with no label (its bullet is hidden, so nothing marks it) |

Corpus-wide: **106 `LINED` in 50 files, 2 `UNMARKED`**. Every `LINED` read
was a real list, including all the known `<br>` lists. `LINED` cannot see
the glued case: a Markdown-only check for labels counting up *inside* a line
was tried and dropped, because the corpus is full of enumerations the page
itself prints run in -- `Legends: (a) ... (b) ...`, `(1) ... (5)` inside a
bibliography entry -- and it reported 552 of them. Only the scan can tell
those from a flattened list, which is what `screen` is for.

### `screen`: the scan against the Markdown

It reads the scan's text layer for runs of two or more lines at one left
edge whose labels count up, with the lines of each item between them.
Labels are read the way the text layer garbles them: `lA` is 1A, `ili.` is
iii., `V.` follows `iv.`, a bare `1` followed by the typewriter's tab is 1.
(ONS_130's Thierry list), and `I` / `II` with the dots lost count as labels
on consecutive lines only, since one `I` alone is the pronoun. Each line is
placed in the Markdown, and each break the page makes is read off what the
Markdown has there.

| Verdict | What it means |
|:--- |:--- |
| `FLATTENED` | an item glued to the one before: the Markdown has no break where the page starts the next item. Labels the Markdown dropped are listed -- read them off the scan |
| `NOT-LIST` | every item starts its own line or paragraph, but not as a list item: labelled paragraphs, or `<br>` lines |
| `RUN-ON` | `--loose` only: the items are separate, but a short line inside one runs on into the next (ONS_130's Copper / Obverse / Reverse lines before they were given `<br>`) |
| `OK` / `UNPLACED` | `-v` only; `UNPLACED` is a run whose text layer and Markdown disagree too much to judge |

Corpus-wide: **699 `FLATTENED`, 102 `NOT-LIST` in 164 files** (279 `RUN-ON`
more with `--loose`, 278 `UNPLACED`).

**Precision, from two random samples read against renders or the
Markdown:** `FLATTENED` 24 of 26 real. Most are numbered endnotes and
reference lists glued into one paragraph, then catalogue entries run
together (`... p. 1233. 13. Mawsil, AR 2 dirhams ...`), then the short
lists this skill was written for. The two that were not: ONS_215's Georgian
references, already a list, mis-placed by their long non-Latin lines; and
ONS_219's numbered weights, a table whose number column was merged in
(still a defect, but `detect-missing-tables`'). `NOT-LIST` 10 of 14 real;
the misses were a table, a mis-match, a lone `(i)` paragraph with its `(ii)`
pages away, and a catalogue whose entries have figures between them.

What it does **not** look for: a list whose items carry no label. Short
lines at one left edge were tried as a signal and dropped. On these
justified typescripts they mostly find the narrow columns of two-column
pages (8,719 hits), and ONS_130's Bhutan list, which sits at the left
margin, is found by its labels anyway.

Other blind spots: a list set in two columns side by side reads as a table
(`detect-missing-tables`); runs on garbled catalogue pages come back
`UNPLACED`; a `FLATTENED` whose Markdown range spans hundreds of lines (`md
1114-1315`) had a line mis-placed, so search for the list's first words
instead of trusting the range.

## Workflow

1. `lint` and `screen` the file. For a corpus pass, take the next file from
   `survey.py show --screen lists`.
2. `rows` the file into `crop_sheets.py sheets` and read the sheet, or
   render one run with `detect_script_garble.py render <STEM> --page N
   --clip x0 y0 x1 y1` (the printed `rect=`).
3. Restore each list to the convention above. Read every label off the
   scan, including the ones `screen` says the Markdown dropped -- never
   number by guesswork, and never copy a label the OCR garbled (`lA`). Read
   also where each item ends: prose after a list often starts back at the
   margin and was glued onto the last item (ONS_130's "From the typology it
   is clear ..."), and a heading may be glued to the list's last line.
4. Edit with a script that asserts each substitution matches exactly once,
   or with `Edit`; keep a backup.
5. Run `scripts/fix_list_starts.rb jons/<STEM>.md` -- from the repo root,
   where that script lives, not from this skill's own `scripts/` (an
   ordered list split or moved renumbers from 1), `lint` and `screen`
   again, and
   `restructure-flattened-md/scripts/lint_structure.py`. Render the file
   with kramdown and look at the lists.
6. `survey.py run <STEM> --screens lists --refresh`.

## What NOT to do

- Don't listify a table. Rows with aligned columns are
  `detect-missing-tables`' business, even when the first column counts up.
- Don't listify a run-in enumeration the page prints inline (`Legends: (a)
  ... (b) ...`). The screen only reports labels that start lines on the
  page; check the render before acting on a borderline one.
- Don't turn an address, a signature block or a coin's Obv./Rev. lines into
  a list. Lines inside one item take `<br>`.
- Don't guess a dropped label, or "correct" one the page prints oddly
  (ONS_130's `1341 and 1341` stays as printed).
- Don't move notes or reference lists that `pdfmd` interleaved with body
  text as part of this pass -- that is `reconstruct-scrambled-md`'s
  pages-out-of-order variant or `restructure-flattened-md`. Restore the
  list where it already sits.
- Don't commit. Leave the changes in the working tree for review.
