---
name: restore-headings
description: Find section headings that `pdfmd` folded into the body text of a `jons/` Markdown file, and headings it invented where the scan has none. Use when a file's headings render in the wrong place -- glued to the end of a paragraph, or missing their emphasis -- or when checking a file against its PDF for structure rather than for spelling or tables.
---

# Restoring headings `pdfmd` lost

The source PDFs are typewritten scans. A section head is set on its own line,
separated from the paragraphs around it by extra leading, and marked either by
underlining it with the typewriter's underscore key or by typing it in capitals.

`pdfmd` frequently loses the line break and the mark together. The head is
appended to the tail of the paragraph above it, so it renders mid-sentence:

```
... widens their appeal to students and collectors alike. Historical Summary
```

That is the failure this skill finds. It is **not** the flattened-table failure
`detect-missing-tables` screens for -- no table is involved, and the
escaped-pipe fingerprint never fires on it. A file can pass `screen` with
`nothing outstanding` and still have every heading in the wrong place.

```
detect_headings.py scan IS_001            # report, change nothing
detect_headings.py scan IS_001 -v         # include what the Markdown got right
detect_headings.py fix  IS_001            # rewrite the Markdown
```

`scan` exits non-zero when there is something to fix.

## Why three signals

No single measurement decides. Each of these is necessary and none is
sufficient:

| Signal | What it means | Why it is not enough alone |
|:--- |:--- |:--- |
| **set apart** | clear space above *and* below, and the line stops short of the right margin | a short body line between two figures looks identical |
| **underline** | a long contiguous ink run under the line's own x-extent, **minus** the same measurement taken in the margin to its right | a scan streak running clear across the page scores as high as a real underline |
| **capitals** | an all-capitals line | how these typewriters mark a head when they do not underline it (`NOTE`, `BIBLIOGRAPHY`) |

Being set apart makes a line a *candidate*. An underline or capitals makes a
candidate a *head*. A candidate that is neither wants the paragraph break but
no marker.

The pages carry no vector drawings (`get_drawings() == []`), so the underline is
found in pixels, the same way `detect_tables.py` finds ruling lines.

The margin control is the part that is easy to leave out and expensive to omit.
On IS_001 page 12 the line `September 1971` sits over a page-wide scan streak
and scores 0.37 under the text -- but 0.37 in the margin too. Real underlines
stop where the text stops: they score 0.90+ under the text against ~0.00 beside
it.

## Both directions, because each finds what the other cannot

| Direction | Verdict | Meaning |
|:--- |:--- |:--- |
| PDF → Markdown | `FOLDED` | the scan sets this head apart; the Markdown appended it to the paragraph above |
| | `FOLDED-PLAIN` | set apart but *not* marked as a head, and still appended |
| | `FLAT` | on its own line already, but with no marker |
| | `LOST` | a head with no counterpart in the Markdown at all |
| Markdown → PDF | `OVERSET` | the Markdown marks it as a head; the scan does not |

Without the second direction, `## The attribution: and chronology of some of the
coins described in this` -- an ordinary sentence promoted to a heading, and cut
in half by the line break -- is invisible, because there is no set-apart PDF
line to start from.

A verdict may carry a suffix, and a suffixed verdict is **reported but never
applied** -- see "Splits that are refused" below.

`fix` repairs `FOLDED`, `FLAT`, and `OVERSET`. `LOST` is reported only: inserting
a head means choosing both its wording and its position, and the wording comes
from the garbled OCR layer (`B I B L I O G R A P H Y`). Read the render and add
it by hand. `FOLDED-PLAIN` needs `--include-plain`, because a wrong call there
puts a paragraph break into running text.

## Matching the two OCR layers

The PDF text layer and the Markdown were OCR'd separately and disagree --
`ORIEOTAL` against `ORIENTAL` -- so a head is matched fuzzily. Three rules keep
that from turning into coincidence:

- **Two anchors only.** A head either starts its Markdown line or was appended
  to the end of one. A match floating in the middle of a paragraph is a
  coincidence. Allowing the middle is what let `B I B L I O G R A P H Y` match
  the words `Bibliography of hoards` inside a numbered reference.
- **Locality.** The matched pieces must sit together, within about 1.4x the
  head's length. Summing scattered blocks lets a long paragraph "contain" any
  short head.
- **Document order.** Both files run in the same order, so a match at or after
  the previous head's row wins ties. Without this the bibliography subhead
  `Historical` on page 11 matches `## Historical Summary` back on page 1 with a
  perfect score, and the real head goes unreported.

A `start` match must also account for most of its line. That is what stops the
heading `# NOTE` from matching the body line `Note: Up to twenty small marks
may occur...`.

## Splits that are refused

A `FOLDED` fix cuts a Markdown line in two. Two kinds of cut are always wrong,
and both were found by sweeping `fix` across the corpus and auditing the result:

| Suffix | Refused because |
|:--- |:--- |
| `-MIDWORD` | the cut lands inside a word. It turned `# ORIENTAL NUMISMATIC SOCIETY INFORMATION SHEET` into `# ORIEN` plus `## TAL NUMISMATIC SOCIETY INFORMATION SHEET`. |
| `-LOWER` | the head starts lower-case and was cut out of running prose, so it is a sentence tail, not a head: `(see` / `appendix).`, `I have now developed a` / `classific-`, `to an accuracy of 0 02 of a` / `millimeter`. |

`-LOWER` has one deliberate exception: a **by-line** cut from a title, such as
`# THE COINAGE OF COOCH BEHAR` / `by N.G. Rhodes`. What is left behind there is
a heading rather than a sentence, so the cut is right. The exception requires
the remainder to be both marked *and* at most `TITLE_LEN` (60) characters --
a paragraph that has picked up a stray `#` is still a paragraph, and letting
the marker alone vouch for it is exactly what cut `millimeter` loose.

## Auditing a fix

`fix` only ever moves structure, so the word stream is the check:

```python
w = lambda t: re.findall(r'[A-Za-z0-9]+', t)
w(old) == w(new)   # False means text was lost, duplicated, or split mid-word
```

Across a 53-file sweep this caught the one mid-word split immediately. It does
**not** catch a cut made at a legitimate word boundary in the wrong place, so
also check for headings the sweep created that begin lower-case:

```
git diff <before> -- jons/ | awk '/^\+\+\+ b\// {f=substr($2,3)}
                                  /^\+## / {t=substr($0,5)
                                             if (t ~ /^[a-z]/) print f": "t}'
```

## Tuning

- `--min-underline` (default 0.45) -- ink run under a line, over the line's own
  width. Scans differ: IS_001's heads score 0.90+, IS_003's running heads score
  0.42 and need `--min-underline 0.40`. Check the render before lowering it.
- `--min-margin` (default 0.25) -- how far that run must beat the margin
  control. Lowering this re-admits scan streaks.
- `--gap` (default 1.4) -- blank space above and below, in multiples of the
  page's own median leading. IS_001's heads clear 1.9x against 1.0x for ordinary
  interline spacing.
- `--width` (default 0.75) -- longest a head may be, as a fraction of the page's
  body measure.
- `--min-ratio` (default 0.72) -- similarity before two lines count as the same
  text.
- `--marker` (default `##`) -- what `fix` prefixes a head with.

## Scope

Tuned and verified against IS_001, which is typewritten prose. Run `scan` and
read it before running `fix`; never sweep `fix` across the corpus.

On catalogue-heavy files -- IS_003, IS_005, IS_007 -- the report is noisier, for
two reasons worth knowing:

- A **table rule** sits under a line of cells exactly the way an underline sits
  under a head, and the margin control does not always separate them. Expect
  `LOST` findings whose text is table debris (`o. 1 . 0 80`).
- Ruler names in a catalogue are set in capitals that the OCR mangles into mixed
  case (`MANSTJR I ibn miH`), so the capitals test misses them and they report as
  `OVERSET`.

Both are false positives to read past, not defects to fix blindly.

## Verification

The tool was written after five heading errors in IS_001 were found by hand.
Run against the file as it stood before those repairs, it reproduces all five
with the same verdicts, and finds four more that the manual pass missed --
including a `BIBLIOGRAPHY` head absent from the Markdown entirely.

After a `fix`, check that only structure moved:

```python
w = lambda t: re.findall(r'[A-Za-z0-9]+', t)
w(old) == w(new)   # True unless you also edited text by hand
```
