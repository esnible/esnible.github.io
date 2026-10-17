---
name: detect-missing-figures
description: Find maps, graphs, drawings, coin photographs and plates on a source-PDF page that the `jons/` Markdown file has no `figure` (or `script-*` / `table-*`) marker for — figures `pdfmd` dropped silently or OCR'd into garbage text that no other screen notices. Works from the rendered page, not the Markdown, so it catches problems that leave no trace in the text. Use when checking a file or the whole corpus for unmarked figures, when a rendered file seems to be missing artwork, or as a sweep for problems the other detection scripts can't see.
---

# detect-missing-figures

`pdfmd --ocr auto` (see `scripts/build.sh`) has no notion of a figure. On a scanned page it either drops a drawing without trace — OP_015's hand-drawn distribution map left nothing at all in the Markdown — or OCRs its labels into garbage text: OP_015's four line graphs came out as `1,70- 1,60- 1,50 1,40'` glued to a paragraph, plus two bogus `#` headings. The Markdown-side screens (`lint_structure.py`, `detect_headings.py`) catch some of the garbage; nothing in the Markdown can reveal a figure that left no text behind.

## How it works

The PDFs are scans: one image per page plus an OCR text layer, no vector drawings. The script renders each page at 50 dpi, erases every word box the text layer knows about, and clusters the ink that is left. Ink that no word accounts for is a figure, a rule, or scan dirt. A page is **figure-like** when its unexplained-ink clusters are large enough, and the Markdown's markers are checked for that page:

```
python3 .claude/skills/detect-missing-figures/scripts/detect_figures.py screen OP_015
python3 .claude/skills/detect-missing-figures/scripts/detect_figures.py screen ONS_146 ONS_147 -v
python3 .claude/skills/detect-missing-figures/scripts/detect_figures.py screen --all > figs.txt
python3 .claude/skills/detect-missing-figures/scripts/detect_figures.py screen OP_015 --md draft.md
```


### The cheap path

`rows` writes `file<TAB>label<TAB>page<TAB>@x0,y0,x1,y1` for the findings a
person has to look at, and this screen measures its own regions, so the row
carries the rect rather than words to search for:

```
detect_figures.py rows ONS_120 > rows.tsv
python3 .claude/skills/shared/crop_sheets.py sheets --rows rows.tsv --out ONS_120-figs
```

One sheet of stacked bands instead of a render per finding. A band taller
than 900px is scaled down whole, which answers *is this figure in the
Markdown* but not *what does it say*; raise `--max-band`, or crop that one
region at a higher `--dpi`, when the answer needs reading.

| Verdict | Meaning |
|---|---|
| `MISSING` | figure-like ink, and no `figure` / `script-*` / `table-*` marker names this page |
| `COVERED` | a marker names this page (shown with `-v`) |
| `UNCOVERED` | a region of a `COVERED` page that no marker's `rect=` overlaps — always shown, never counted into `MISSING` or the exit status |
| `RULED` | unmarked, but the ink is mostly thin straight rules — a bordered table or frame, `detect-missing-tables`' job (shown with `-v`, not counted) |

Each region prints a `rect=x0,y0,x1,y1` in PDF points, ready for `detect_script_garble.py render <STEM> --page N --clip x0 y0 x1 y1` (write the four numbers out; zsh does not split a variable). Exit status is 1 when anything is `MISSING`. Pages are 0-based, as in every `page=N` marker. The script needs PyMuPDF and numpy, and reads PDFs from `$ONS_ARCHIVE_DIR`. A full `--all` run takes about 2.5 minutes.

## Accuracy

Calibrated on the files that already have `figure` markers: it finds about 90% of marked figure pages. In a sample of the unmarked pages it flags in those files, about three in four were real unmarked figures — coin photos, maps, hand-drawn legends. The rest are:

- **Hand-drawn or hand-lettered tables**: the lettering is ink with no word box.
- **Dense text pages** where the OCR layer missed some lines, so their ink looks unexplained.
- **The masthead logo** is skipped only when it is small and in the top fifth of page 0. Other logos and ornaments will show up.

It misses:
- A second, unmarked figure on a page whose markers do not all carry a `rect=` — the page counts as covered. Give every marker on a page its `rect=` and the screen will report the regions none of them covers (see below).
- Small or faint drawings: symbol rows, pale photos, very thin line art.
- Drawings with OCR junk words on top of them. The script erases those word boxes too, and loses the ink.

A `MISSING` is therefore a page to look at, not a finding. **Always render the page before acting.**

## Second figures on a covered page

A page's markers cover the whole page unless every one of them carries a
`rect=`. When they all do, the screen compares each figure region against
them and reports any the rects miss as `UNCOVERED`.

This is a lead, not a verdict, and it does not touch the exit status. The ink
it reports is unexplained, which on a scan means a figure *or* a line of text
the OCR layer missed — and nothing here separates the two, because the text
the layer missed has no word boxes either, so counting words inside a region
tells you nothing.

Corpus-wide it reports **61 regions on 27 pages across 18 files**, 31 of them
at the page-scale threshold the `MISSING` verdict uses. Four of those pages
were rendered:

| page | what it was |
|:--- |:--- |
| `ONS_097` p3 | **real** — the Siamese amulet photographed obverse and reverse, unmarked; the page's one marker covers the Jalnapur rupee lower down |
| `ONS_109` p3 | **real** — the Farrukhsiyar 1/8 and 1/16 enlargements, unmarked beside the Arkat double rupee |
| `ONS_109` p5 | **real** — three Hims folles drawn under their heading, unmarked above the Eiraku-tsuho rubbings |
| `OP_014` p4 | false — a handwritten page; the "figure" is the handwriting |
| `ONS_096` p3 | false — a typed paragraph the OCR layer skipped |

About the same hit rate as `MISSING` itself, in other words, and for the same
reason. `ONS_109`'s two were invisible until that file's markers were given
rects.

So: adding `rect=` to a marker buys recall on its page and costs some noise
there. Worth doing on a file you are working through; not worth a corpus-wide
campaign. 44% of the corpus's 2,378 markers carry one today.

## Acting on a MISSING page

1. Render the page (or the `--clip` region) and look.
2. If it is a figure, add a marker at the point in the text where the figure sits, in the corpus form:

   ```
   *[figure]* <!-- figure page=N -- what it shows; transcribed labels or key if any -->
   ```

   Follow it with the printed caption as its own paragraph, if there is one.
3. Remove any garbage text pdfmd made from the figure — axis ticks, map labels, `#` lines built from them. `fix-ocr`'s 12-character deletion limit does not apply to this, but read what you delete: real prose is sometimes glued to it (OP_015 line 99).
4. If it is a table, hand it to `detect-missing-tables` or `restructure-flattened-md`; if a legend in a foreign script, `transcribe-foreign-script`.
5. Re-run the screen; the page should now read `COVERED`.

A marker whose page shows no figure at all (ONS_136 `page=3`, whose photograph is elsewhere) is `check-markers`' business (`detect_script_garble.py check-markers <STEM>`), not this screen's.

## What NOT to do

- Don't add a marker without rendering the page — the screen is a lead, not evidence.
- Don't mark logos, printers' ornaments, decorative rules, or scan dirt as figures.
- Don't treat `COVERED` as proof that every figure on the page is marked — it only ever meant "something on this page is marked". Give the page's markers rects if you want the rest of it checked.
- Don't act on an `UNCOVERED` region without rendering it. Two of the five rendered so far were text the OCR layer missed, not artwork.
