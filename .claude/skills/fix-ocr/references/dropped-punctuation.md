# Files that lost their punctuation wholesale

*A `fix-ocr` reference.* Read it when `detect_dropped_punct.py scan` returns
WHOLESALE or ISOLATED. The Hard constraints, Workflow and Verification steps
that govern every fix here are in [`../SKILL.md`](../SKILL.md) — which is also
where an *above* or a *below* in the text points, wherever this file does not
hold what it names.

Some issues' PDF text layers dropped nearly every sentence-ending period (and many colons and decimal points): the file reads `…types Whereas…`, `17 30` for `17.30`, `No A7 2` for `No. A7.2`. Rendering each spot by hand does not scale to hundreds of marks, and the PDF text layer cannot help because it is missing them too.

**First, find out whether this is such a file** — the tell needs no PDF, so this is a `docs/screens.tsv` row (`punctuation`) rather than something to notice by eye:

```
python3 .claude/skills/fix-ocr/scripts/detect_dropped_punct.py scan <STEM>
python3 .claude/skills/shared/survey.py show --screen punctuation    # the worklist
```

A dropped period leaves a lowercase word butted straight against a capitalised sentence opener — `(c 155-169) The last great monarch`, `is discussed in detail Few will have`. Measured over the corpus that shape fires 0.01 times per 1000 words where the punctuation survived and 4-6 times per 1000 where it did not, so the screen's verdict is reliable: **WHOLESALE** (42 files, the scanned issues from ONS_119 and ONS_141-202) sends you to `punct_candidates.py` below; **ISOLATED** (43 files, nine candidates or fewer each) is a handful of ordinary spots that crop sheets settle one at a time. The screen proposes no edits — capitalisation is context, and Hard constraints forbid supplying a mark from context.

The same pass drops the **possessive apostrophe** with the periods, and that one is invisible to everything else: `punct_candidates.py` aligns on `.,;:!?`, so an apostrophe is outside the marks it compares at all, and cspell sees two real words either side of the space.

```
...Curator of South Asian Coins in the Museum s Department of Coins...
...the thirty sultanis which Pijnacker s dragoman had to pay...
```

486 across 61 files, 38 of which the screen already calls WHOLESALE — which is what says it is the same damage and not a habit of the typists. They report as `POSSESSIVE` beside the `SENTENCE` findings, but the rate and the verdict count `SENTENCE` alone: both thresholds were measured on that shape, and the empty gap that justifies the cut is its gap. The one false positive worth knowing is the Belgian dealer's company form, `Jean Elsen s.a.`, which the screen excludes by rule; a transliterated Russian title (`Mednye monety s izobrazheniem`) stays in and is settled on the page like any other candidate.

For a WHOLESALE file, run a second, independent OCR over the renders and align it against the Markdown:

```
python3 .claude/skills/fix-ocr/scripts/punct_candidates.py <path> [--pages 2-9]
```

It prints one candidate per line — `<path>:LINE:COL  md 'types'  page 'types.'  pN  --clip x0 y0 x1 y1` — for every aligned word whose trailing punctuation differs. The `COL` matters: a token is routinely not unique on its line, and `from region to region. Some` has two slots for one finding. Tesseract's reading is a candidate list, not evidence. Decimal points inside numbers (`17 30`, `2-4 1 1`) do not show up as trailing punctuation — grep for digit-space-digit runs and render those separately, and the same for the possessive apostrophes, which this alignment does not compare at all.

**Do not read the file page by page. Let the script place the safe class and read only what it cannot settle:**

```
python3 .claude/skills/fix-ocr/scripts/punct_candidates.py <path> --apply            # dry run
python3 .claude/skills/fix-ocr/scripts/punct_candidates.py <path> --apply --write --sheet-rows rows.tsv
python3 .claude/skills/shared/crop_sheets.py sheets <STEM> --rows rows.tsv           # then Read the sheets
```

`--apply` places only what is unambiguous — the Markdown has no trailing mark, the page has exactly one `.` or `:`, and the page's word is the Markdown's with that mark on the end and nothing else changed — then re-aligns and prints the rest. **EXTRA** is the row that matters: the Markdown now has a mark the page does not, so tesseract read a speck or a mark landed in the wrong slot. **MISSING** is the classes `--apply` does not touch — marks against emphasis markers, `,` against `;`, a mark after an opening bracket. Settle both from the crop sheets, then apply with `apply_edits.py` as usual.

Measured on ONS_157's 810 candidates, `--apply` reproduces 420 of the 450 placements a hand pass made, adds 48 the hand pass had missed, disagrees with it nowhere, and leaves 91 rows for the eye. That is three or four crop sheets against the twenty page renders the hand pass read.

**Run `--apply` once.** It holds no record of a finding you looked at and rejected, so a second run puts back every mark you removed — on ONS_156 it restored all three specks (`of. archaeologists`, `an. attempted`, `would. only`) that the sweeps had just caught. Decide the flags up front, including `--emphasis`, and if you do need a second pass, re-check the sweeps against the snapshot from *before* the first one rather than the file as it now stands.

`--emphasis` also places a mark after a trailing `*`, `_` or backtick. It is off by default because the mark could belong inside the markup, but on the scans sampled so far it does not: ONS_156 sets `INJ 8.`, `ONS Newsletter.`, `...from Kasur.` and `...invasion of India.` all with the full stop upright after the italic. It is worth about half the residue — 102 of ONS_156's 165 rows.

**Reading the page render is not enough on its own, which is why the loop is this way round.** Over ONS_158's 1,590 candidates, every one of its 37 pages was rendered and read, and 53 bad edits still got through; ONS_157 took 4 from 20 pages read. In both cases the re-alignment is what caught them, and it costs nothing. Reading every page is the expensive half of the pass and the ineffective half. Two mechanical sweeps after applying catch what the eye does not, and both must come back empty before the pass is done:

```
# a mark glued inside a word: a short candidate token (`V`, `p`, `No`, `so`)
# matched as a substring of a longer one -- `V.iatkin`, `quart.er`, `Hussein:ites`.
# The letter after the mark may be upper case: ONS_159 lost `INDO-GR.EEKS` to a
# narrower version of this grep that required a lowercase one.
grep -nE '[A-Za-z]+[.:;,][A-Za-z]+' "<path>" | grep -vE 'www|http|\.com|\.net|@'

# a period before a lowercase word: tesseract read a speck on the scan as a
# full stop -- `the silver. crisis`, `in order. to advertise`
grep -nE '[a-z]\.\s+[a-z]{2,}' "<path>"

# a mark between two words in capitals: it looks exactly like a sentence end,
# so neither grep above can see it -- ONS_159's masthead became
# `# ORIENTAL NUMISMATIC. SOCIETY`
grep -nE '\b[A-Z]{2,}[.:;,][[:space:]]+[A-Z]{2,}\b' "<path>"
```

The third grep is narrow on purpose. A period inserted before an ordinary
capitalised word is **indistinguishable from a real sentence end** by any
mechanical test, so nothing catches that one but the page: `PL. Gupta`
survived all three greps on ONS_159 and is `P.L. Gupta` on the scan. That is
the residual risk of leaning on the sweeps instead of reading every page, and
it is the reason a file worked that way should say so.

Both greps hit legitimate text too (`Op. cit`, `Hung. ducats`, an e-mail, and the odd full stop the scan really does print mid-sentence), so diff them against the same grep over the pre-pass snapshot and look only at what the pass introduced. Of ONS_158's 53, 31 were specks, 18 were substring matches, and 4 were specks on pages whose single candidate looked safe.
