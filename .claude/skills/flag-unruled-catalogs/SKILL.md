---
name: flag-unruled-catalogs
description: Tell an isolated foreign-script legend (fine for transcribe-foreign-script to handle one line at a time) apart from a sustained, unruled catalog table (dozens of coin-type entries typed in whitespace-aligned columns with no ruled borders, which neither transcribe-foreign-script nor detect-missing-tables can safely process automatically). Use before running transcribe-foreign-script's Tier 2 on a file with many raw foreign-script hits, or when a file's OCR reads as a long run of interleaved Latin/Arabic (or Devanagari/Chinese) noise that might be a flattened reference catalogue rather than prose.
---

# flag-unruled-catalogs

This skill exists because of a mistake almost made on `IS_005`: `transcribe-foreign-script screen` correctly found 80 raw foreign-script line hits between md lines 442 and 701, and the obvious next step looked like running that skill's Tier 2 (render a page, spawn an Opus call per legend, require corroboration from an adjacent gloss) 80 times. That would have been wrong. Rendering the actual page showed a single continuous catalog table — `Type | Caliph/Governor | Obv. field | Bismillah ending | Around Obv. type (12/6/3/9) | Rev. field | Around Rev. type (12/6/3/9)` — repeated across at least nine mint-town sections, typed with whitespace column alignment and no ruled borders at all. `detect-missing-tables` never flagged it either, because its detector works on pixel rules and this page has none (`page_grid()` reports `raw h=0 v=0`).

So there is a real gap between the two existing skills: `detect-missing-tables` can't see whitespace-only tables, and `transcribe-foreign-script`'s per-line corroboration model doesn't scale to (and isn't safe on) dozens of table cells that mostly have no adjacent gloss to check against. This skill's only job is telling the two situations apart *before* you commit effort to the wrong one.

## What this skill deliberately does not do

Two different automated approaches to actually detecting the table's rows and columns were tried and both failed on this corpus:

1. **Recurring absolute word x-positions across a sliding window of lines.** This fires on ordinary justified prose too — a paragraph's left margin is itself a "recurring x-position" shared by nearly every line, and normal word-wrap coincidentally produces 2-3 more shared positions often enough to clear a naive threshold. On `IS_005`, a plain-prose page (page 3) scored *higher* than the real table page (page 10).
2. **Abnormally large intra-line whitespace gaps as candidate column separators.** This is the standard technique for whitespace-delimited tabular text, and it failed here because it assumes one table row = one text line. This corpus's rows don't: a single logical row's Arabic legend routinely stacks across 2-3 separate visual lines within one row, interleaved with mostly-blank cells (`-`, a ditto mark, a single symbol), so there often aren't two words on the same line to measure a gap between.

Do not reach for either of these without a genuinely new idea for handling multi-line, sparsely-populated rows — that is a real, unsolved sub-problem, not a tuning issue. This skill sidesteps it entirely by not attempting row/column detection at all.

## A landmine for anyone tempted to detect script presence from the PDF directly

While testing approach 2, the same table's Arabic legend came back from PyMuPDF's `page.get_text()`/`get_text("words")` as Latin mojibake (`dJJ y4> >^J`), not Arabic Unicode. **This PDF's embedded text layer is a different, separate OCR pass from the one `pdfmd --ocr auto --lang eng+ara` produced into the `jons/` Markdown** — the embedded layer appears not to recognize Arabic at all and substitutes lookalike Latin glyphs, while `pdfmd` re-OCRs the page image itself and gets real Arabic codepoints (which is what ended up, still garbled, in the `.md` file).

Practical consequence: `transcribe-foreign-script`'s `locate` command still works, because it only searches `page.get_text()` for distinctive **English** words, and the embedded layer's English recognition is fine. But nothing in this family of skills should search `page.get_text()` for non-Latin Unicode expecting to find a real signal — it won't be there even where the PDF page plainly shows Arabic script. The only trustworthy source of actual foreign-script Unicode in this corpus is the already-OCR'd `.md` text.

## What this skill does instead

```
python3 .claude/skills/flag-unruled-catalogs/scripts/cluster_script_density.py screen IS_005 [IS_004 ...]
```

It re-derives the same raw foreign-script line hits `transcribe-foreign-script screen` reports (duplicated logic, not imported — these skills stand alone), then clusters hits that are within `--gap` (default 12) Markdown lines of each other. A cluster of 5 or more hits (`CATALOG_THRESHOLD`) is reported as `CATALOG`; smaller clusters are `isolated` (pass `-v` to list them). Exit status is `0` only when no `CATALOG` cluster remains unaddressed, matching the sibling skills' convention.

```
IS_005: 80 raw hit(s) in 2 cluster(s) -- 1 catalog cluster(s), 1 isolated
  CATALOG   md lines 442-670  (77 hits) -- likely an unruled table; render and reconstruct by hand,
            do not run transcribe-foreign-script Tier 2 line-by-line on this
```

Sanity-checked against ~40 files in the corpus: the 5-hit/12-line defaults produce a believable mix of small isolated clusters and larger catalog clusters across many `IS_###` files (several score in the 5-30 hit range, a few — `IS_012`, `IS_018` — considerably higher), rather than either never firing or flagging everything. Treat these as reasonable starting defaults, not as validated ground truth — nobody has checked each flagged file's actual page layout the way `IS_005` page 10 was checked by eye.

## What to do with each verdict

- **`isolated`** — hand it to `transcribe-foreign-script` as normal; a cluster this small is very likely one caption-and-gloss pair or a couple of independent short legends, the shape that skill's Tier 2 is built for.
- **`CATALOG`** — do not run `transcribe-foreign-script` Tier 2 line-by-line on it. Instead:
  1. Check `detect-missing-tables screen` on the same file first — it's possible part of the region already has a ruled sub-table that skill knows about, or a `table-deferred` marker explaining why it was left alone (as happened with the small 3-hit cluster adjacent to `IS_005`'s already-`DEFERRED` page-12 table).
  2. Render the likely page range with `transcribe-foreign-script`'s `render` subcommand (use its `locate` subcommand first to find the pages, keeping in mind `locate`'s ranking is only as good as the surrounding English OCR — see that skill's own known limits).
  3. Read the table structure off the rendered image by hand — column headers, row boundaries, which mint/ruler section you're in. There is no automated shortcut for this step right now (see above).
  4. Reconstruct it as a Markdown table using the same discipline `detect-missing-tables` already applies to its hardest cases (`IS_003` TABLE 3 is the precedent: when full transcription isn't verifiable, restore the legible skeleton — section headings, ruler names, provinces — and mark the untranscribed catalog body with the entry range it covers, rather than inventing cell contents nobody can check).
  5. Once real table cells exist, hand any Arabic/foreign-script content inside them to `transcribe-foreign-script`'s normal corroboration-required Tier 2 — a cell's neighboring English column (a governor's name, a ruler's name) is often exactly the corroborating gloss that skill's hard constraints require, even though the flattened prose version had none.
  6. Re-run this skill's `screen`; a properly reconstructed table's Arabic should now live inside pipe-table cells, which changes the line-clustering shape (likely to nothing, since well-formed table rows are far denser in non-garbled structure than the flattened version was).

## Known limits

- **This is a triage tool, not a fix.** It never edits a file or claims a `CATALOG` region is resolved — there is no marker convention here (unlike `table-ok`/`script-ok`) because this skill makes no claim worth marking; the actual claim belongs to whichever of `detect-missing-tables` or `transcribe-foreign-script` eventually handles the reconstructed content.
- **The 5-hit / 12-line defaults are a starting point, not a validated boundary.** A genuinely dense multi-legend paragraph could clear the threshold without being a table, and a table with very sparse Arabic content (many blank/ditto cells) could stay under it. Check the render before trusting the label either way.
- **Row/column geometry for whitespace tables remains unsolved here.** If someone picks this problem back up, the two dead ends documented above (absolute x-position recurrence, intra-line gap detection) are worth knowing about before spending time reproducing them; the real obstacle is multi-line, sparsely-populated rows, not the column-alignment concept itself.
