# Garble traces: the characters pdfmd leaves behind

*A `fix-ocr` reference.* Read it when `detect_marker_noise.py scan` reports a
trace. The Hard constraints, Workflow and Verification steps that govern every
fix here are in [`../SKILL.md`](../SKILL.md) — which is also where an *above*
or a *below* in the text points, wherever this file does not hold what it
names.

A **trace** is a literal character or short string the OCR left standing
where the scan printed something else — a caret for a superscript footnote
number, a guillemet for a quotation mark it could not place, an escaped
asterisk closing a run of quote marks. The screen above pairs on quote
characters, so `^` reaches it only as `MARKER_TAIL`, the garble swallowed
*after* a quote run. Where the printed superscript came through as a bare
caret with no quote mark anywhere near it, nothing in `docs/screens.tsv` sees
it, and the file screens clean on all five rendering screens:

```
In a forthcoming monograph^ I suggest that the reverse deities...
Sikander 'Adil Shah surrendered to the Emperor.^ Thereafter he...
```

`transcribe-foreign-script`'s screen does know these glyphs — its
`LATIN_NOISE_CHARS` is `^\<>±«»¬°·•` — but it wants a *run* of four such
tokens at 15% of the line beside an `Obv.`/`Rev.` gloss, because its job is a
legend pdfmd read as Latin. One caret in sixty words of English prose is not
that, and LATIN is kept out of its exit status in any case.

```
python3 .claude/skills/fix-ocr/scripts/detect_marker_noise.py scan <STEM>
python3 .claude/skills/fix-ocr/scripts/detect_marker_noise.py rows <STEM>
python3 .claude/skills/fix-ocr/scripts/detect_marker_noise.py list
```

**The traces live in `.claude/skills/fix-ocr/traces.tsv`, not in the code.**
Each row gives the literal (or a `re:` pattern where a literal will not do),
a name, the shapes that count for it, and a note saying why it is there and
what the measurement was. When a new trace turns up, add a row — that is the
intended way to extend this screen, and it needs no code change. Today's list
is `^`, `¬`, `«`, `»`, the quote-run-plus-`\*` superscript, and `<` `>`.

Every occurrence of every listed trace is reported, classified by position:

- **MARKER** — at a word's end. The scan prints a superscript footnote
  number, so this restores exactly as the `®` of `suspect-symbols.md` and
  the `''` of `quote-pairs.md` do:
  `<sup>6</sup>`, with the digit read off the page and cross-checked against
  the footnote list. 1,003 in 50 files. A footnote reference falls wherever
  its claim ends, so what follows may be a new sentence or just the next word
  (`Joe Cribb^ supported this view`). pdfmd also sets the superscript as a
  quote run closed by an escaped asterisk — `an astronomic sign"\*` for
  `sign⁴`. `detect_quote_pairs` skips a single quote mark unless asked,
  because on its own a `"` is usually just a quotation; the trailing `\*` is
  what makes it a marker, and is what the pairing never looks at. 275 of
  those were unreported anywhere, in 45 files. Some are question marks on the
  page rather than markers (`just one has survived"\*` is `survived?`) — the
  render says which.
- **GLYPH** — *between two letters*, which is a letter or a diacritic the OCR
  lost: `Öl^er` for Ölçer, `ak^e` for akçe, `be^hk` for beşlik, `'O^ene'` for
  Ozene, and in ONS_163 a whole file's worth of `\>` for `y`
  (`Arab-B\>zantine`, `Uma\>\>ad`, `b\> telephone`). 424 in 43 files.
- **LOOSE** — every other position. **This is where most of the garble is**,
  and an earlier version of this screen, which knew only the two shapes
  above, had no name for it. ONS_155 screened clean carrying 18: `fax:
  -^-^-33` for `++33` (a digit on either side), `**YZD**^8.` for a footnote
  digit glued to its caret, `4^0` for `400`, `(Crusaders) ^ Jerusalem` (a
  space in front), `*almati^,*` (a comma behind). Not one was a false
  positive the narrowness had bought. **Assume a trace is garble until the
  scan says otherwise** — read it, do not reason about it.

A hit inside a run of garble is tagged **WRECK** and reported as a lead, not
counted — that is a legend for `transcribe-foreign-script`, which renders the
whole thing rather than one glyph.

**Routing a WRECK is not reading it, and the tag is not a reason to skip the
crop.** The threshold counts wreck characters in a 40-character window; it
says the neighbourhood is noisy, nothing about how hard the spot is. ONS_155's
line 723 sat as a WRECK through a whole pass:

```
A possible full reading is •^\[êTTcT. The ^ could be the final letter of Dalpat.
```

Two Devanagari words in English prose, with the article's own gloss beside
them — one crop settled it as `डलपत` and `त`, and showed a third line,
`सञज for सिंहजी`, that the OCR had dropped altogether. What made it look like
somebody else's problem was the tag, plus a sentence nearby that said
"Devanagari", which is the article talking, not the scan. Before handing a
WRECK off, check whether it is a flattened legend (dozens of tokens, no
English around it) or a few glyphs inside a sentence. The second kind is a
crop, and a crop you can read is a reading you owe the file.

Angle brackets count only in the GLYPH shape; elsewhere most are legitimate —
comparison operators in alloy tables (`Cu >70`, `As < 0.5`), `->` arrows in a
flattened family tree, and ONS_226's own stated convention, `In inscriptions
\< \> represents visible` — 1,291 across 75 files, too few of them defects to
put in a worklist. `--all` reports them anyway. `--only=<name>` and
`--skip=<name>` narrow a run to particular traces.

## Settling a trace that really is printed

Some traces are genuinely on the page: the corpus's own French and German
passages use guillemets, and ONS_226 states a convention for angle brackets.
Once the scan has been read, say so inline so the screen stops asking and the
next pass does not read the same spot again:

```
stamp a small indentifying «chop-mark» unto the surface
<!-- glyph-ok « page=5 reason=the scan prints French guillemets round the
author's own quoted term; both halves present and balanced -->
```

`glyph-ok` settles every occurrence of the traces it names on its own line.
Name several with commas (`glyph-ok «,»`), by the literal or by the name
`traces.tsv` gives it (`glyph-ok guillemet-open`). `glyph-deferred` is its
sibling for one that was looked at and could not be resolved: it is reported
as a lead rather than a verdict, so the line stays on a worklist without
counting against a clean screen. Both carry `page=` and `reason=` like the
`script-*` markers, and for the same purpose — the next person should be able
to tell *checked and real* from *never checked*.

A trace quoted inside a comment is not reported, because the OCR skills quote
bad readings in their markers on purpose and a screen that read them would
report its own evidence as the defect. The header counts them anyway
(`19 hidden in comments`): otherwise a trace could leave this screen by being
quoted in a marker's reason string rather than by being fixed.
