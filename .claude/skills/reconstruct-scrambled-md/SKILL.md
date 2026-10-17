---
name: reconstruct-scrambled-md
description: Rebuild a Markdown file in the `jons/` corpus whose source PDF has a two-column layout that `pdfmd --ocr auto` scrambled into single-column text (mid-paragraph or mid-word interleaving between the left and right columns). Use when a file's OCR is not just letter-level garble but reads as nonsense because column order was lost — check the source PDF layout before reaching for this skill instead of `fix-ocr`. Also covers PDFs whose pages are bound out of reading order, where an article stops mid-sentence at a page boundary and resumes pages later. Typically followed by `fix-ocr` for remaining letter-level cleanup.
---

# reconstruct-scrambled-md

You are rebuilding a Markdown file whose source PDF used a two-column (or multi-column) layout that `pdfmd --ocr auto --lang eng+ara` (see `scripts/build.sh`) flattened by reading across columns instead of down them — producing text where the end of a left-column line is followed by a fragment of the right column, then back to the left column, etc. This is a different failure mode from ordinary OCR garble and needs structural reconstruction, not word-level fixes.

## Recognizing the problem

Before using this skill, confirm the file actually has this failure mode rather than plain OCR garble:

1. Read a page or two of the target `.md` file. Column-scrambled text reads as genuinely incoherent — sentences cut off mid-word and resume with unrelated content — not just misspelled.
2. Find the source PDF, typically at `~/personal/src/ons-website/static/archive/<basename>.pdf` (matching the `.md` filename, e.g. `ONS_216.md` → `ONS_216.pdf`). The PDFs come from the private `esnible/ons-website` repo and this path varies by machine — if it's not there, check for a `$ONS_ARCHIVE_DIR` override (the same env var the `detect-missing-tables`, `restore-headings`, and `transcribe-foreign-script` scripts read) or ask the user where their checkout lives.
3. Sample it with `pdftotext -layout <pdf> - | sed -n '1,80p'` and compare against the `.md` file's opening. If `pdftotext -layout` reads coherently in proper column order and the `.md` file does not, this skill applies.

If `pdftotext -layout` is *also* garbled (rare — happens with some scanned-image PDFs), this skill's primary method won't work; fall back to the image-transcription method throughout instead (see "Image fallback" below).

## Workflow

1. **Extract clean text.** Run `pdftotext -layout <pdf> -` and use it as the primary source of truth for reading order. This tool is column-aware for this corpus and reliably outputs text in correct top-to-bottom, left-column-then-right-column order.

2. **Look for a contents page.** Multi-article issues (`ONS_###` newsletters/journals) often carry a "Contents of Journal NNN" page. Extract it first and use it as a checklist of expected articles, in order — cross-checking your reconstruction against it at the end catches missed or misordered articles (this has caught real omissions in past reconstructions).

3. **Rebuild the Markdown file structurally**, replacing the scrambled prose with the correctly-ordered text while preserving this repo's existing conventions:
   - Keep the same page-break markers, heading levels, and front matter style already used in the file (or, if the whole file is being replaced, follow the conventions in a recently-completed sibling file of the same type, e.g. another `ONS_2##.md`).
   - Reproduce paragraph and line breaks as they naturally fall in the extracted text; don't invent structure the source doesn't have.
   - For large files (40+ pages), split the work across parallel sub-agents by article or contiguous page range, then assemble and reconcile the pieces yourself — this has scaled well for 50+ page issues. Give each sub-agent the same source PDF, its specific page/article range, and these instructions. Make sure each sub-agent actually finishes and writes output before treating its section as done; check its result rather than assuming success.

4. **Give catalogue tables extra scrutiny.** Dense coin-catalogue articles (entry number + description + commentary, often under mint-name subheadings) are the highest-risk content: column reflow can misattribute a caption or commentary block to the wrong entry number, or reorder entries relative to their mint heading. For every catalogue table:
   - Confirm entries are in ascending/expected sequence.
   - Confirm each caption/commentary paragraph is attached to the entry it visually belongs to in the PDF, not just the next one in `pdftotext`'s output order.
   - When column layout is ambiguous, render the page as an image (see below) and check directly rather than guessing from extracted text alone.

5. **Handle redactions.** If the source PDF has ONS-editorial redactions (contact details, addresses, member names), replace with an italicized note matching existing convention, e.g. `*(names redacted in the source document)*` or `*(contact details redacted in the source document)*` — do not fabricate content to fill the gap.

6. **Handle mojibake and image-only content (image fallback).** Some pages don't extract cleanly via `pdftotext -layout`:
   - **Mojibake** — custom embedded fonts with no usable cmap can make `pdftotext` output garbage glyphs, most often in Arabic legend transcriptions. Try direct image transcription first:
     ```
     pdftoppm -png -r 250 -f <page> -l <page> <pdf> <prefix>
     ```
     then read the resulting PNG and transcribe by eye. If still illegible even at higher resolution (try `-r 600`), replace with a note like `*(Arabic legend not transcribed – custom font)*` rather than fabricating.
   - **Image-only pages** (scanned photos, captions embedded in images) — render as PNG and transcribe directly, or run `ocrmypdf --force-ocr --language eng+ara --sidecar <file>` for a fresh OCR pass on just that page.
   - Never fabricate a plausible-looking reading when the source is genuinely illegible — leave a note or an `<!-- OCR: ... -->` comment instead, per `fix-ocr`'s hard constraints (which also apply here).

7. **Verify structural integrity.**
   - Re-read the reconstructed file start to finish; confirm it reads coherently as continuous prose/tables with no leftover scrambled fragments.
   - If a contents page was found in step 2, confirm every listed article appears, in order, with a matching heading.
   - Spot-check a handful of catalogue entries and any article containing non-Latin script against rendered page images, especially where the reconstruction required stitching together sub-agent outputs.

8. **Hand off to `fix-ocr`.** Structural reconstruction usually leaves ordinary letter-level OCR garble behind (wrong letters, digit/letter swaps, stray glyphs) — run the `fix-ocr` skill on the file next to clean that up and update the numismatic dictionaries (`dictionaries/{chinese,islamic,indian}-numismatics.txt`). Don't duplicate that workflow here; this skill's job is getting the words in the right order, not spelling them correctly.

## Variant: pages bound out of reading order

A different reading-order failure: every page reads correctly on its own, but the PDF holds the pages in the wrong sequence, so `pdfmd` stitched whole pages together in the wrong order. ONS_120 bound its pages 0, 1, 2, 3, 4, 5, 6, 7 where the reading order is 0, 1, 4, 5, 2, 3, 6, 7 (most likely sheets scanned in the wrong order). The workflow above does not apply. `pdftotext` reads in the same PDF order, so it reproduces the error and cannot be the source of truth, and nothing inside a page needs rebuilding.

**Recognizing it.** Look for a seam: an item that stops mid-sentence at the bottom of a page and runs into an unrelated passage with no blank line between them (ONS_120's Coin Atlas item: `…coinage traditions of the Mediterranean, India, China and Islam, as the` / `Distribution of legend the same as Grabar no. 55…`), with the missing half turning up elsewhere, also glued to the wrong neighbour. `clean-ocr-formatting`'s severed-paragraph screen does not catch this, because the seam is a single newline rather than a blank line. To confirm, render the pages either side of each seam and check that the continuation really sits at the top of the page you think it does.

**Fixing it.**

1. Work out the true page order from the seams. Every seam should close up: the last line of each page continues on the first line of the next. A footnote, figure caption or byline that now sits with the article it belongs to is a second check.
2. Move whole page blocks with a short script, not with `Edit`. Assert the start and end line of each block before cutting, then assert the result keeps every line of the input (a `Counter` of lines, allowing for any blank separators you added). Then re-run `detect_severed_paragraphs.py scan` and `scripts/fix_list_starts.rb`: moving a block can split or join an ordered list.
3. Leave `page=N` markers alone. They name the PDF page, not where the block sits in the file, so they stay correct after the move.
4. Re-read each moved article's comments. A `script-ok` / `figure` reason written while the article was split in two may describe it wrongly. ONS_120's HIMS note said the entry had no coin photograph, because the photograph was on the misplaced page.

## Known pitfall: page-break splitting drops content

If you split `pdftotext -layout` output into per-page chunks (e.g., by form-feed character) to hand out to sub-agents, be aware that on two-column pages `pdftotext -layout` can place left- and right-column text that straddles a page boundary onto the same physical line — a naive split on the form-feed can silently drop that line's content. After assembling sub-agent output, diff the total word count or spot-check page-boundary regions against the source PDF/image to catch this; when in doubt, render the boundary page as an image and confirm nothing was lost.

## What NOT to do

- Don't run the column workflow on a file whose pages are merely bound out of order — move whole page blocks as described under "Variant: pages bound out of reading order" instead.
- Don't reach for this skill on ordinary OCR garble where the reading order is already correct — that's `fix-ocr`'s job, and applying structural reconstruction there is wasted work and risks introducing line-break changes `fix-ocr` forbids.
- Don't fabricate content for illegible or unrecoverable passages — use an explicit note or `<!-- OCR: ... -->` comment.
- Don't skip the contents-page cross-check on multi-article issues when one exists — it is the cheapest way to catch a missed or misordered article.
- Don't treat a sub-agent's completion report as proof of correctness — check its actual diff/output, especially at page-range boundaries.
- Don't commit or open a PR as part of this skill — reconstruction leaves changes in the working tree for review; committing is a separate, explicit step the user asks for.
