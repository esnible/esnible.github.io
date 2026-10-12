---
name: restore-italics
description: Restore italic passages -- book and journal titles, foreign terms, the masthead's run-in labels -- that the source PDF's text layer records and the `jons/` Markdown lost, because `pdfmd` re-OCR'd the page image and never saw the fonts. Use when a file's bibliography reads as plain prose, when a title or a transliterated term that is italic in the scan is unmarked in the Markdown, or when checking a file against its PDF for emphasis rather than for spelling, tables or headings.
---

# Restoring italics `pdfmd` dropped

The archive PDFs were OCR'd by ABBYY, which assigns a real font face per span
rather than one flat font. Book titles, foreign terms and the masthead's
run-in labels come back as `Times-Italic`, `*Times New Roman-BoldItalic-*`,
`*Cambria-BoldItalic-*`:

```
1. Whitehead, R.B. Catalogue of the Coins in the Punjab Museum Lahore. Vol. III
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ Times-Italic
```

`pdfmd` re-OCRs the page image and never sees any of it. On ONS_111 the text
layer carries 35 italic runs, 14 of them real text, and the Markdown carries
one `*...*` -- so both its bibliographies read as flat prose.

```
detect_italics.py scan ONS_111            # report, change nothing
detect_italics.py scan ONS_111 -v         # include PRESENT and NOISE
detect_italics.py fix  ONS_111            # wrap the MISSING spans
```

`scan` exits non-zero when there is something to fix. A file takes about a
second; the worst in the corpus (ONS_230, 477 runs against 400 paragraphs)
takes 45, all of it in the fuzzy match.

## This is not the mangled-emphasis problem

On 112 of the 268 files `pdfmd` *did* carry emphasis across -- as per-word
asterisks, `*word *` around every word of the passage. There the italics are
not missing, they are mangled, and that is `clean-ocr-formatting`'s job.
`scan` says so when it sees more than 20 such spans in a file, and `fix`
refuses to write there until they are cleaned, because the "is this span
already emphasised?" test cannot be trusted on a file carpeted with stray
asterisks. The two skills are complementary: clean the asterisks first, then
screen for what is still missing.

## Signals, and what each one cannot do

| Signal | What it means | Why it is not enough alone |
|:--- |:--- |:--- |
| **span flags** | `flags & 2`, or `italic` in the font name -- the same span data `detect_headings.py` reads bold off, one bit over | ABBYY tags unreadable glyph soup italic as readily as prose: 21 of ONS_111's 35 runs are `IVi-`, `J:>`, `2=T` |
| **run joining** | adjacent italic spans are one run, and a run that reaches the end of a line and continues at the start of the next is one run | joining is a guess -- two italic titles on consecutive lines look identical to one that wrapped, so the unjoined pieces are kept and retried |
| **fuzzy match** | the run is located in the Markdown by text, never by position | the text layer and the Markdown are separate OCR passes and disagree (`Umayad` for `Umayyad`, `Coins m the` for `Coins in the`) |
| **capitals** | which words are capitalised, as a tie-break | only decides between matches that already agree on their letters |

Position is not available at all. The Markdown came from a different pass over
the same page, so nothing in it maps back to a span's coordinates -- this is
the constraint `flag-unruled-catalogs` documents from the other direction,
where the embedded layer reads Arabic as Latin mojibake and `pdfmd` does not.

## Verdicts

| | |
|:--- |:--- |
| `MISSING` | italic in the scan, plain in the Markdown, located cleanly. The only one `fix` writes. |
| `PRESENT` | already emphasised. Nothing to do; `-v` to see them. |
| `PARTIAL` | emphasis already overlaps part of the span, or an emphasis run is open across it. |
| `AMBIGUOUS` | two lines match about as well, or one line repeats the run's own words. `song-pei` occurs 14 times in ONS_111 line 187 and the span cannot say which one is italic. |
| `UNSAFE` | located, but the span cannot be wrapped -- it lands inside a comment, a table cell, or an existing marker. |
| `LOST` | no match in the Markdown. Usually the passage is garbled past matching; occasionally `pdfmd` dropped it. |
| `NOISE` | the run is not words. Counted, never matched. |

Only `MISSING` is ever written, because a wrong call here is silent: a `*` in
the wrong place reads as ordinary prose, and nothing downstream flags it. The
other verdicts are for a human with the page open.

## Thresholds

All on the command line; the defaults are tuned in the script's header with
the evidence for each number.

- `--min-ratio` (0.85) -- how much of a run must be found in a Markdown line
  before the two count as the same text. It has to tolerate two disagreeing
  OCR passes, so it cannot be 1.0.
- `--margin` (0.10) -- how far the best match must beat the second best before
  it is trusted rather than reported `AMBIGUOUS`.
- `--pair-repeats` (off) -- a title cited k times in the scan matches k places
  in the Markdown equally well, and every one of them is `AMBIGUOUS` on the
  margin test. Both files are the same publication in the same order, so when
  the counts agree exactly this pairs them off in document order: on ONS_134
  it turns 4 of the 10 review items into fixes, correctly (`Numismatic Digest`
  p6/p8 to lines 292/364, `Xinjiang Tuzhi` twice on p8 to lines 383/396). Off
  by default, because the counts agreeing is evidence and not proof -- one bad
  match, or one citation the Markdown lost, shifts the whole assignment by one
  and writes every marker in the wrong place.
- `--italic-noise` (0.5) -- fraction of a page's own characters that may be
  italic before the page is judged mis-tagged and dropped whole. The same gate
  `detect_headings.py` applies to bold, for the same failure.
- `DENSITY` (0.80, in the script) -- the matched letters over the span of
  Markdown they are spread across. This is what stops a match from annexing a
  neighbouring word: ONS_125's garbled `The World oflslanr` matches
  `The World of Islam4 provided` at 0.88 on letters, and wrapping that
  italicises `provided`.

## What it gets wrong

**The boundary, by a word.** ABBYY sometimes runs an italic span one word past
where the italics stop on the page. ONS_111 p7 reads `In his *Siamese
porcelain and other tokens*, Ramsden names...` and the text layer gives the
run as `Siamese porcelain and other tokens. Ramsden`, so `fix` italicises the
author's name along with the title. This cannot be screened out by rule: a
title that legitimately continues past a full stop is common in this corpus
(`Catálogo de Monedas de Plata Columnarias y de Busto. Ceca de Potosi`), so a
"trim the tail after the last stop" rule would break more than it fixed. Read
the diff.

Measured on ONS_111 against the rendered pages: 14 of 14 proposed spans are
genuinely italic in print, and 13 of 14 have the right boundary.

## What NOT to do

- Don't run `fix` on a file whose per-word asterisks have not been cleaned --
  that is `clean-ocr-formatting`'s job, and `fix` refuses it for a reason.
- Don't trust `fix` on a new file without reading the diff. The same
  discipline `restore-headings` learned the expensive way applies here: the
  script proposes, the render decides.
- Don't correct the OCR of the text it wraps -- not the title's spelling, not
  the author's. `fix-ocr` owns the words; this skill owns the markers only.
- Don't resolve an `AMBIGUOUS` or `PARTIAL` by lowering `--margin` until it
  becomes `MISSING`. Open the page and decide.
- Don't add emphasis the text layer does not record because a title "ought to"
  be italic. Many are genuinely roman in print -- ONS_111 sets `Spink
  Numismatic Circular` in roman two lines above an italic `Münzen der
  Rasuliden`.
