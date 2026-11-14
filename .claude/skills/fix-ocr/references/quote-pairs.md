# The marks pdfmd read as quotation marks

*A `fix-ocr` reference.* Read it when `detect_quote_pairs.py scan` reports a
hit. The Hard constraints, Workflow and Verification steps that govern every
fix here are in [`../SKILL.md`](../SKILL.md) — which is also where an *above*
or a *below* in the text points, wherever this file does not hold what it
names.

## A quotation mark the OCR split in two

```
python3 .claude/skills/fix-ocr/scripts/detect_quote_pairs.py scan "<path>"
```

A typewritten `"` scans badly, and pdfmd routinely reads one printed mark as
two or three. ONS_111's publications notice came out `'""Chopmarks"` where
the page prints `"Chopmarks"`, and eleven runs in that one file were the
same defect.

**Do not screen for "an illogical quote combination".** A run of two or more
marks fires 3,657 times across 127 files, and that census is three different
things: about a quarter are not quotes at all (see the next section), and
plenty of the mixed ones are correct text -- the inner `'` in `("'Abd Allah
ibn Ibrahim")` is the ʿayn of the name. What is decidable from the text
alone is **opener ≠ closer**: pair each opening mark with its closer and
report the spans where the two disagree, or where either is a run. That is
664 spans across 99 files against 24,188 pairs that balance, and the script
already drops the classes that look like the defect without being it --
apostrophes, ʿayn, nested closings (`...the Name "Safi""`), runs after a
digit, and spans long enough to mean the pairing desynchronised rather than
that the quotes disagree.

**Settling a whole file by eye instead of one render at a time:**

```
python3 .claude/skills/fix-ocr/scripts/quote_crops.py <STEM>
```

writes `<STEM>-quotes.html` -- one row per finding, the Markdown line with
the run highlighted beside the band of the scan it came from, located by
matching the words before the mark against the page's text layer. Open it
next to the editor and work down the list; `--only quotes` (or
`superscript`, `question`) splits a long one into batches, and `--dpi 450`
enlarges the crops. A row whose words the OCR mangled, or whose phrase
repeats on several pages, says so and shows no image rather than showing
the wrong part of the scan -- so check that the Markdown and the crop are
the same sentence before trusting either. This is the cheap way to settle a
file when a person is doing the reading; it rewrites nothing.

Before either, check what the source is:

```
python3 .claude/skills/fix-ocr/scripts/classify_source.py scan <STEM>...
```

`SCAN` is the ordinary case -- a page image with an OCR layer behind it,
where every mark in the Markdown is a guess a render can settle.
`BORN-DIGITAL` is not: from ONS_186 (1998) onward the PDF carries the
publisher's own text, 57 files in all, so its punctuation was never OCR'd
and reading it off a page render is the wrong tool -- the quote screen may
still report runs there, but they are a different defect with a different
remedy. `NO-TEXT-LAYER` (ONS_177, ONS_197, OP_014) is a scan nobody OCR'd
into the PDF: nothing can locate words on those pages, so a crop sheet
cannot be built at all. `quote_crops.py` refuses both unless passed
`--anyway`.

`detect_quote_pairs.py rows <STEM>` writes the same findings as
`file<TAB>label<TAB>anchor` for that builder, leaving out the ordinals the
batch writes. Use it when a file has findings from more than one screen: a
quote run and a heading on the same page then share one band instead of
costing two images.

The locating and the stacking are not quote-specific, so they live in
`.claude/skills/shared/crop_sheets.py`, which any screen can call with a
label and an anchor per finding:

```
printf 'line 94 heading\tMichael Willis, Who built\n' |
  python3 .claude/skills/shared/crop_sheets.py sheets ONS_166
```

A row may name its own file (`file<TAB>label<TAB>anchor`), which puts the
last few findings of a dozen files onto one sheet instead of one sheet
apiece.

`--stack` is the same crops for an agent doing the reading: labelled JPEG
sheets (`<STEM>-quotes-1.jpg`, ...) of five findings each instead of one
HTML page, with the Markdown printed to stdout, where text is cheap. Marks
in the same printed paragraph share a band. A file's worth of evidence then
costs two or three images rather than a render apiece -- ONS_053's fourteen
findings came to three sheets, and every one of them turned out to be the
same split `"`.

**The pair decides *that* it is wrong; only the render decides what it should
be.** The marks the OCR split do not tell you what was printed, and the
answer is not always a quotation mark at all: ONS_051's `''A Study of Holkar
State coinage"'` is a review heading that the page prints with no quotes
whatsoever. The Hard constraints apply here exactly as they do to any other
punctuation fix.

Three readings that are correct text, and must be left alone when you meet
them in the output:

- **a ʿayn inside a quotation** -- `("'Abd Allah ibn Ibrahim")`, `"'am"
  instead of "sanah"` (IS_018, where the file's own `script-ok` note records
  the عام). The script suppresses the names it knows; add to `AYN_NAMES`
  when a new one surfaces.
- **a nested quotation closing** -- `"...the title *yagbu* 'chief of a
  clan'"` and `"A Coin Bearing the Name "Safi""`. Two closers side by side
  are each doing their own job.
- **an inch mark** -- `10 3/8" x 7 3/8''` in a book description.


## A `''` that closes nothing is a question mark

The screen's third verdict, and the one ONS_165's worklist turned up: a
printed `?` scans as `''` on these pages, so a rhetorical question ends up
looking like a stray quote run.

```
Are we really meant to believe this''   ->  ... believe this?
as "Muhammad''", with question-mark     ->  "Muhammad?", with question-mark
In AH 568 and 56(9 or 7'')              ->  56(9 or 7?)
A fals of AH394''(B D Kochnev           ->  A fals of AH 394? (B. D. Kochnev
```

231 across 38 files, worst in the review articles of `ONS_15*`-`ONS_17*`,
where the author argues with other numismatists a question at a time.
ONS_165 alone had 15, one of them inside a sentence that goes on to say
*with question-mark i.e. he was not sure*.

**The PDF text layer repeats the error**, so `triage_percent.py`'s
text-layer shortcut cannot settle these -- both OCR passes read the same
`''`. Render each one. A `''` after a digit is a `SUPERSCRIPT` hit instead
(see below) and is just as often a `?`: `(404'')` is `(404?)`, `425''` is
`425?`.


## A quote run after a digit is a superscript

993 of those runs sit immediately after a digit, and they are OCR'd
superscript ordinals and footnote markers -- the `®` class of
`suspect-symbols.md` in another costume:

```
the 14'''  All-Russian Numismatic Conference   ->  14th
30""  November                                 ->  30th
the 33'"''  International Archaeometry Conf.   ->  33rd
7'''  century Byzantine coins                  ->  7th
```

**A digit before the run does not prove an ordinal**, so there is no
skip-after-a-digit rule either. ONS_111 p5 prints `...perpetuate his
sovereignty 828".` -- a plain closing quote after a year -- and ONS_120 p5
prints `"Capitalism and Material life 1400-1800", Braudel`, both verified on
the render. `AH 40(7'' or 6'')` is a footnote marker on a date.

What settles it is the word *after* the run, which is why the screen splits
the class in two:

- **`ordinal`** -- a century word, a month, `c.`/`cent` (but not `c/m`, which
  is a countermark), `year`, `regnal`, `anniversary`, `edition`, `standard`,
  `International`, or a connector with a century word just beyond it
  (`19"' and 20''' centuries`). 533 runs across 28 files. The suffix comes
  from the number -- 14 → th, 33 → rd, 21 → st, 11-13 → th -- and the
  restoration is **plain `14th`**: this corpus writes 3,599 ordinals that
  way and not one as `14ᵗʰ`. `ordinals` emits them as an `apply_edits.py`
  batch:

  ```
  python3 .claude/skills/fix-ocr/scripts/detect_quote_pairs.py ordinals <STEM> > edits.txt
  python3 .claude/skills/fix-ocr/scripts/apply_edits.py "<path>" edits.txt          # dry run
  python3 .claude/skills/fix-ocr/scripts/apply_edits.py "<path>" edits.txt --write
  ```

  Each edit carries the word that proved it -- `16''' century => 16th
  century`, not `16''' => 16th` -- so it fires only where the evidence is;
  a bare edit would sweep the footnote markers of the same shape elsewhere
  in the file, and 30 runs across 13 files are exactly that. The batch is
  still a candidate list, not evidence: confirm a sample per page against
  the render before `--write`, the same rule `punct_candidates.py` follows.

- **`check`** -- the other 344. Render each one. A footnote marker restores
  as `<sup>6</sup>`, the convention for new work (the 1,817 Unicode `⁶`
  already in place stay), and **the digit is not fixed** -- read it off the page and cross-check it against the footnote
  list, exactly as for the `®` of `suspect-symbols.md`.
