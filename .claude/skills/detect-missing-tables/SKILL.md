---
name: detect-missing-tables
description: Find bordered tables that exist in a source PDF under `~/personal/src/ons-website/static/archive/` but were flattened into prose by `pdfmd`, leaving the `jons/` Markdown file with no table where one belongs — then optionally rebuild the table from the existing OCR layer and insert it at the right place. Use when the user suspects a table is missing from an OCR'd Markdown file, asks to check a file or the corpus for dropped tables, or asks to restore a table from a PDF.
---

# detect-missing-tables

`pdfmd --ocr auto` (see `scripts/build.sh`) does not emit Markdown tables for the bordered tables in this corpus. It flattens them into running prose: column headers run together on one line, then cell text interleaved across columns. The result reads as garble but is not letter-level OCR damage, so `fix-ocr` cannot help and must not be pointed at it.

This skill finds those gaps and, when asked, rebuilds the table. It is the only skill here that **adds** lines to a corpus file — the line-break invariant enforced by `fix-ocr` deliberately does not apply.

## The fact that determines the approach

**These PDFs are scans.** Every page is one full-page image plus an OCR text layer, with `page.get_drawings() == []`. Table borders exist only as pixels.

So every vector-based table finder — pdfplumber's `lines`/`lattice` strategies, Camelot lattice mode, PyMuPDF's `find_tables()` — returns **zero tables on every file in this corpus**. Do not reach for them and do not conclude from their silence that a file has no tables. Detection must work on rendered pixels, which is what the bundled script does.

## Hard constraints

- **`MISSING` and `UNKNOWN` are not the same.** `UNKNOWN` means the screen could not locate an anchor and therefore has *no opinion*; the table may well be present. Never report an `UNKNOWN` to the user as a missing table, and never rebuild one without first rendering the page and confirming by eye.
- **Never trust `rows_ruled`.** Interior horizontal rules are frequently absent in this corpus — rows are often separated by whitespace alone. Column counts come from vertical rules and are dependable; row counts must come from clustering text.
- **Never insert Tier-2 output unverified.** The reconstructed cells come from the same OCR layer that produced the garbled prose, so they carry the same errors. Render the page, read the table, and correct the cells against the image before inserting.
- **Never delete the flattened prose you are replacing without reading it first.** It sometimes holds text the OCR word layer lost — on `IS_001` page 3 it has `WEIGHT` and `Rare` right where the word layer garbles both. Prefer replacing it in the same edit that inserts the table, so nothing is silently dropped.
- **Never drop a figure annotation.** The `*[figure]*` placeholder is the only signal to a reader that artwork is missing, and the comment beside it is the only record of where that artwork is in the PDF. The text next to them is a caption, not the cell's content.
- Do not change the surrounding file. Fixing letter-level garble elsewhere is `fix-ocr`'s job, in a separate pass.

## Workflow

### Tier 0 — screen (default; start here and usually stop here)

```
python3 .claude/skills/detect-missing-tables/scripts/detect_tables.py screen IS_001 [IS_002 ...]
```

Costs ~60 ms/page. Exit status is `0` when nothing needs attention and `1` when any `MISSING` or `UNKNOWN` is found, so it scripts over the corpus:

```
python3 .../detect_tables.py screen $(ls jons/*.md | xargs -n1 basename | sed 's/\.md$//')
```

Output is per detected grid:

- `PRESENT` — a pipe table already follows the anchor. Nothing to do.
- `MISSING` — anchor located in the Markdown, no table near it. **This is the only positive finding.**
- `UNKNOWN` — no usable caption above the grid, or the anchor did not match. Needs a human look; it is not evidence of a problem.

If a file reports `MISSING 0` and you are content to leave `UNKNOWN`s alone, stop. That is the intended cheap path.

### Tier 1 — confirm before doing any work

For each `MISSING`, render the page and look at it. This is not optional: it is how you learn the true row and column counts, catch a page-layout false positive, and see which cells span columns.

```python
import fitz
fitz.open(PDF)[PAGE].get_pixmap(dpi=110).save("/tmp/page.png")   # then Read the image
```

`grids` prints the geometry the detector inferred, for comparison against what you see:

```
python3 .../detect_tables.py grids IS_001 --page 3
```

### Tier 2 — rebuild and insert

```
python3 .../detect_tables.py cells IS_001 --page 3
```

This buckets the OCR words into columns using the vertical rules, groups them into rows, and prints pipe-table lines. On `IS_001` page 3 it recovers the header and both data rows correctly.

Then:

1. Correct every cell against the rendered page. Expect residual OCR errors — that same table yields `T'/EIGHT (grains)` for `WEIGHT (grains)` and `Its re` for `Rare`.
2. **Read the flattened prose you are about to replace — it is often the better source.** On `IS_001` page 3 the prose has `WEIGHT` and `Rare` correct where the word layer garbles both, and carries the spanning row intact. Take structure from `cells`, text from whichever source is cleaner, and settle disputes against the image.
3. Repair spanning cells by hand. A cell spanning several columns smears across them; on `IS_001` page 3 the row "Quarters and eighths of type 2 exist as round coins with only one mark" arrives split across five columns. Markdown has no colspan, so put the sentence in one cell and leave the rest blank.
4. Leave the `*[figure]*` placeholders and their coordinate comments in place (see below).
5. Add the `|:--- |` separator row after the header.
6. Insert at the anchor line the screen reported, immediately after the heading, and remove the flattened prose the table replaces.
7. Re-run `screen` on the file; the finding should flip to `PRESENT`.

## Figures in cells

Many tables in this corpus put coin drawings in cells rather than text. Because each page is one flat scan, a figure is not an embedded image object — `page.get_images()` returns only the page scan itself. A figure is detected instead as **ink that no OCR word accounts for**: the cell is rendered, every recognised word box is masked out, and what remains is measured.

A cell holding a figure is annotated with two parts:

```
*[figure]* <!-- figure page=3 rect=441.4,373.9,520.1,405.8 -->
```

- **`*[figure]*` renders.** A reader of the Markdown sees that artwork is missing rather than silently reading a caption as if it were the whole cell.
- **The HTML comment does not render** and records where the artwork lives in the source PDF, so it never has to be located again.

The rect is `x0,y0,x1,y1` in **PDF points**, page-relative. Points rather than pixels deliberately: they are DPI-independent, so the stored rect stays valid no matter how the page is later rendered. Detection runs at 110 dpi, but the same rect extracts cleanly at any resolution:

```python
import fitz
fitz.open(pdf)[3].get_pixmap(dpi=350, clip=fitz.Rect(441.4, 373.9, 520.1, 405.8)) \
   .save("figure.png")
```

The rect hugs the artwork — ink projections are trimmed so scanner speckle does not inflate it — and the placeholder is positioned before or after the caption to match the page, since artwork usually sits above its caption but not always.

Both parts are greppable corpus-wide:

```
grep -rn "\[figure\]" jons/          # every cell awaiting artwork
grep -rn "<!-- figure page=" jons/   # with extractable coordinates
```

Leave both in the inserted table. They are the only trace that the cell held anything beyond its caption text.

Two things to know when reading them:

- **A figure decides which row a cell belongs to.** Where rows are separated by whitespace rather than a rule, a figure sitting between two rows' text lines is easy to attribute to the wrong row by eye. The detector assigns it by cell geometry — on `IS_001` page 3 the two coin symbols belong to row 2 (`Wheel-mark or bent-bar type of Gandhara`), not row 1, because they align with row 2's other cells.
- **The count is conservative, and the reason is specific.** OCR frequently hallucinates tokens *on top of* artwork — `iU`, `WW`, `Sx#x` sit over `IS_001` page 5's obverse marks. Those bogus words are masked out like any other, taking the figure's ink with them, so the cell reads as text-only. On page 5 this cost 9 of 31 figure cells their rect. Treat an unmarked cell as unconfirmed rather than proven text-only, and check dense pages against the image. Where the image shows artwork the detector missed, emit `<!-- figure page=N -->` with no rect rather than inventing coordinates.
- **Reject hairline rects.** A band that includes the table's own ruling picks the rule up as figure ink and yields a rect a point or two tall. Filter on `bbox.height`.

Tune with `min_frac` / `min_px` in `cell_has_figure()` if a particular scan needs it; raise them when speckle in a dirty scan produces marks on plainly empty cells.

## Anchors

The anchor is the text immediately above the grid, reduced to its last few words of four or more letters. It does double duty: it is how the screen decides whether a table is missing, and it is where the rebuilt table gets inserted.

A good anchor is a real caption — `['EARLY', 'JANAPADA', 'ISSUES']` for `IS_001` page 3, which resolves to the `# 1 EARLY JANAPADA ISSUES` heading. A bad anchor is the table's own header row; the script flags these as weak and refuses to match on them, because words like `REVERSE` and `NOTES` match many lines. Tables that start at the top of a page have no text above them at all and yield no anchor. Both cases surface as `UNKNOWN`.

## Tuning, and the trap to avoid

Defaults in the script: `THRESH=185`, `MIN_FRAC=0.12`, `EDGE=0.02`, `SMEAR=2`, `DPI=110`.

- **`MIN_FRAC` must stay low.** It is the fraction of the *page* a rule must span to be a candidate. A table often covers well under half its page — the `IS_001` JANAPADA table spans about 38% of its page height — so a threshold of, say, 0.40 makes it *impossible* for that table's vertical rules to ever qualify, and the page silently reports zero tables. Grid coherence is enforced by the extent-overlap test in `find_tables()`, not by this threshold. Lower it, don't raise it.
- **`THRESH` around 185 is stable.** At 160 page-edge scan artifacts survive edge-filtering and inflate the rule count.
- **`DPI` 110 and 150 find the same grids** on the files tested; 110 is 2.5× cheaper, so screen at 110.
- **`SMEAR`** ORs each row/column with its ±2 neighbours so a slightly skewed scan still yields one long run instead of many short ones. Heavily skewed scans need deskewing first.
- **`--min-cols` defaults to 3** to suppress multi-column *page layouts* being read as tables — the `ONS_246` contents page is a 2-column layout that would otherwise register. Pass `--min-cols 2` when you specifically want genuine two-column tables, and expect layout noise.

## Two tables on one page

The detector groups all mutually-overlapping rules on a page into **one** grid. A page carrying two stacked tables therefore reports a single grid with a blended, meaningless column count — `IS_001` page 7 holds `5 SEMI-AUTONOMOUS MAURYAN CITIES` and `6 ? POST-MAURYAN PERIOD` and reports "9 cols", which matches neither (both are 10).

Suspect this whenever a page renders with more than one caption, or the reported column count disagrees with the image. Separate the tables by clustering the **vertical** rules on their y-extents; do not split on the largest horizontal-rule gap, which lands inside a table whose rows are tall rather than between the two tables.

The second table may also be invisible to the page-level scan. On that page its dividers are only partial-height, so no `min_frac` setting finds them. Re-run rule detection on a clip of that band alone, with the threshold taken against the **band** height rather than the page:

```python
pm = page.get_pixmap(dpi=150, colorspace=fitz.csGRAY, clip=band)
# ... then require runs >= 0.35 * pm.height
```

That recovered its 9 rules and showed it shares the first table's column grid exactly, with two cells merged.

## Known limits

- **Recall is not complete.** The extent-overlap test drops some real tables; `IS_001` page 4 has a visible table that the detector does not report. A clean screen is evidence, not proof.
- **Dense, noisy scans defeat Tier 2.** `IS_003` page 14 is a catalogue page whose reconstructed cells are unusable. Reconstruct by hand from the rendered image in those cases.
- The screen only knows about *bordered* tables. Tables laid out with whitespace alone have no rules to find and are invisible to it.
