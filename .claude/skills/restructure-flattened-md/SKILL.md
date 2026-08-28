---
name: restructure-flattened-md
description: Rebuild the non-prose structures in a `jons/` Markdown file that `pdfmd --ocr auto` flattened into running text -- genealogical family trees, whitespace-aligned borderless tables, hand-drawn maps, plates of coin facsimiles, and underlined bibliography titles -- and delete the 2-4 column Markdown tables pdfmd invents from caption-and-drawing layouts. Use when `detect-missing-tables screen` reports `FLATTENED n line(s)` but `MISSING 0 UNKNOWN 0` (the residue is not a bordered table), or when a file reads coherently as prose but its diagrams, maps, and side-by-side lists have collapsed into garble. This is a coordinating pass over `detect-missing-tables`, `restore-headings`, `flag-unruled-catalogs`, `transcribe-foreign-script`, and `fix-ocr`; it owns none of their jobs and defers each hard sub-problem to the skill that does.
---

# restructure-flattened-md

`pdfmd --ocr auto --lang eng+ara` reads typewritten English prose well enough that
`fix-ocr` can patch the rest letter by letter. It does badly on anything that is
**not** a paragraph: a hand-drawn genealogy, a table whose columns are aligned with
spaces instead of ruled with ink, a sketch-map with labels scattered across it, a
plate of coin drawings with hand-lettered legends. Each of these collapses into a
run of interleaved tokens that reads as noise -- and, unlike a bordered table,
`detect-missing-tables` cannot rebuild it, because there are no pixel rules to find.

This skill is the playbook for that residue. It was written after `IS_007`, whose
whole front matter and 11-page catalogue were in this state: two family trees (one
OCR'd right-to-left with every name reversed), two borderless tables run together
into prose, three body paragraphs interleaved with map labels, a page of coin
drawings, an underlined bibliography, and two Markdown tables `pdfmd` had invented
out of a caption-and-drawing layout. None of it was a missing bordered table.

## When this skill applies

Run `detect-missing-tables screen` first (it is the cheap entry point):

```
python3 .claude/skills/detect-missing-tables/scripts/detect_tables.py screen IS_009
```

This skill applies when that screen reports **`FLATTENED n line(s)` with `MISSING 0
UNKNOWN 0`** -- i.e. `pdfmd` left an escaped-pipe fingerprint (`\|` in a non-table
line), but there is no bordered table anywhere near it. Render the pages the
flattened lines map to and confirm what you are looking at is one or more of:

- a **genealogical / dynastic tree** (underlined names, `=` marriage links, vertical
  descent strokes);
- a **borderless table** -- rows and columns held by whitespace alone, no ink rules
  (`page_grid()` would report `raw h=0 v=0`);
- a **hand-drawn map** with labels dropped into the surrounding column of body text;
- a **plate of hand-drawn coin / seal facsimiles** -- a numbered grid of drawings,
  each standing in for a photograph;
- a **spurious Markdown table** `pdfmd` built from a caption beside a drawing, or from
  a single catalogue entry, or from a map's bounding rectangle (2-4 columns, cell
  text that is really one sentence smeared across them);
- **bibliography or catalogue titles** that were underlined on the typewriter and
  lost the underline (they render as plain text now). This one produces no `\|`
  fingerprint -- it rides along because it is the same page and the same rebuild;
  `restore-headings`'s underline detector is what surfaces it independently.

`detect-missing-tables`'s `FLATTENED` check is purely textual, so a `table-ok` /
`table-deferred` marker will **not** clear it -- and there is no marker of this
skill's own. The only thing that makes the fingerprint go away is actually removing
the `\|`, which means doing the restructure. Where a structure genuinely cannot be
rebuilt (an illegible plate), it becomes a `*[figure]*` placeholder or an
`<!-- OCR: ... -->` comment instead -- both of which also remove the `\|`.

## Hard constraints

These are inherited from the skills this one coordinates. If a rebuild would violate
one, stop and hand that piece to the owning skill instead.

- **Visible Markdown must approximate what the page shows -- its own content, order,
  and labels, nothing else.** Transcribe what is printed, in the position it is
  printed. Inferred structure, methodology, "this block is the obverse", corroboration
  reasoning -- all of it goes in an HTML comment, never in a visible line. A reader of
  the rendered Markdown should see something that reads like the page, not a report
  about the page. (This is `transcribe-foreign-script`'s rule and the
  `transcription-visible-output-fidelity` project memory.)
- **Read the flattened prose before you delete it.** It sometimes carries a word the
  OCR word-layer lost -- on `IS_001` page 3 the flattened text has `WEIGHT` and `Rare`
  correct where the word layer garbles both. Replace it in the same edit that inserts
  the rebuilt structure, so nothing is dropped silently.
- **Never drop a `*[figure]*` placeholder or its `<!-- figure page=N ... -->`
  comment.** The placeholder is the only signal to a reader that artwork is missing;
  the comment is the only record of where it lives in the PDF. Caption text beside a
  drawing is a caption, not the drawing's content.
- **Don't fabricate.** A conjectural genealogy stays conjectural: preserve every name
  and its rough position, do not invent a parent-child link the scan does not draw.
  An illegible legend gets a flagged guess or an honest comment (per
  `transcribe-foreign-script`), never a confident invention.
- **Don't fix letter-level garble in the surrounding prose.** That is `fix-ocr`'s
  pass, run afterward. The exception is a stray non-Latin glyph sitting *inside* a
  region you are already rebuilding -- delete it there, since you are rewriting the
  line anyway.
- **This is a large, cross-cutting change to one file.** Use plan mode: enumerate
  every flattened structure as a checklist, and get the user to sign off on the list
  and on the technique choices (tree rendering, catalogue scope, one PR vs. split)
  before editing. `IS_007` went through plan mode with an explicit 8-item list.

## Workflow

### Tier 0 -- screen

```
python3 .claude/skills/detect-missing-tables/scripts/detect_tables.py screen  <STEM>
python3 .claude/skills/restore-headings/scripts/detect_headings.py    scan    <STEM>
```

If the flattened region carries Arabic / Devanagari / Chinese script, also:

```
python3 .claude/skills/transcribe-foreign-script/scripts/detect_script_garble.py screen <STEM>
python3 .claude/skills/flag-unruled-catalogs/scripts/cluster_script_density.py  screen <STEM>
```

`FLATTENED n` + `MISSING 0 UNKNOWN 0` is the signature this skill exists for. A
non-zero `restore-headings` count is expected -- the flattened regions are full of
map labels and tree names OCR'd as `# HEADING` lines.

### Tier 1 -- inventory (render, classify, plan)

1. Map every flattened line to a PDF page and **render that page**:

   ```python
   import pymupdf
   pymupdf.open(PDF)[PAGE].get_pixmap(dpi=140).save("/tmp/p.png")   # then Read it
   ```

   Crop and re-render at 300+ dpi for a genealogy's connector lines or a legend.

2. Classify each structure against the list in *When this skill applies*. When a
   dense foreign-script run could be either an unruled catalogue or a plate of
   drawings, let `flag-unruled-catalogs` decide before you commit effort:
   `CATALOG` -> rebuild as a table; a numbered grid of drawings -> `*[figure]*`.

3. Write the checklist -- one line per structure, with its page, its md line range,
   and the technique from Tier 2. Enter plan mode with it. Ask the user about
   anything genuinely open (see `AskUserQuestion` uses on `IS_007`): tree container,
   how far to take a long catalogue, whether to compute `rect=` coordinates for
   figures or use bare markers, one PR or several.

### Tier 2 -- restructure

Do the whole file in one branch / one PR. Per structure type:

**Genealogical / dynastic tree** -> a **fenced code block** (` ``` `), monospace,
box-drawing corners (`┌ ┬ ┐ ├ ┼ ┤ └ ┴ ┘ │ ─`). Preface it with an HTML comment
naming the source and calling it schematic. Preserve every name and its rough
printed position; do not assert links the drawing does not show. Keep names as the
typewriter set them (no scholarly diacritics the source could not type). A fenced
block is the default because it holds 2-D alignment exactly and is never reflowed;
a blockquote -- considered for `IS_007` and rejected -- still gets line-wrapped by
some renderers. Shape (the outer indent here stands in for the ``` fence):

    <!-- family tree of X; schematic reconstruction of the hand-drawn chart on PDF page N -->

        RULER   c.1714-1750
              │
        ┌─────┴─────┐
      SON A       SON B

**Borderless table** (whitespace columns) -> a real Markdown pipe table with a
`|:--- |` separator. Read row alignment off the **rendered image**, not the
`cells` output -- there are no rules for `cells` to bucket against. A blank cell
where a column has no entry in that row. If the layout is multi-up (e.g. three
`Name | Dates` pairs side by side to save paper, as in `IS_003` page 12), flatten
it to the *logical* single-column shape, not the typographic one.

**Hand-drawn map** -> a `*[figure]*` placeholder for the map, and the body
paragraphs that were interleaved with its labels rebuilt as clean prose. The label
interleaving is `reconstruct-scrambled-md`'s failure mode -- use its method
(`pdftotext -layout` for reading order, image fallback where that is also garbled)
for the paragraph text, and treat the map itself as artwork.

**Plate of coin / seal facsimiles** -> one `*[figure]*` placeholder for the plate
(or one per row if the page renders them in distinct bands). Do **not** transcribe
the legends -- `transcribe-foreign-script` skips plates on purpose, "layout, not
legibility, is the test". Keep any numbered catalogue text that belongs *with* the
plate as prose or a table beside the marker.

**Spurious `pdfmd` table** -> delete it, keep (or restore from the render) the
prose it was built from. Tell it from a genuine flattened borderless table by the
render: a real table has aligned columns on the page; a spurious one is one
caption, or one catalogue entry, or a rectangle's four sides, chopped into cells.

**Underlined titles** (bibliography, standard-catalogue lists) -> Markdown
`*italics*`. Correct only the OCR of the title itself against the render; leave the
surrounding sentence and the author's own spellings (including period typos) alone.

**Stray non-Latin glyphs** inside any region you are rewriting -> delete. Elsewhere
in the file, leave them for `fix-ocr`.

**Bogus `# HEADING` lines** inside the flattened regions (map labels, tree names,
`# f`, `# ¥`) -> remove them as you replace the region. For headings folded into
body text *outside* these regions, run `restore-headings fix` separately.

### Verify

```
python3 .claude/skills/restructure-flattened-md/scripts/lint_structure.py jons/<STEM>.md
python3 .claude/skills/detect-missing-tables/scripts/detect_tables.py screen <STEM>
grep -nP '[\x{0600}-\x{06FF}\x{0750}-\x{077F}\x{0900}-\x{097F}\x{FB50}-\x{FDFF}\x{FE70}-\x{FEFF}\x{200E}\x{200F}]' jons/<STEM>.md
npx cspell lint jons/<STEM>.md
```

- `lint_structure.py` catches the mechanical defects a big rewrite introduces:
  a `#` heading with no blank line around it, a pipe table split by a stray blank
  line, an unbalanced ` ``` ` fence, a `*[figure]*` with no companion comment, and
  any `\|` left outside a table row.
- `detect-missing-tables screen` should now read `FLATTENED 0`, exit `0`.
- Note the cspell delta (before vs. after). Greek legend words, correct book
  titles, and deliberately source-faithful typos are expected to remain flagged;
  say so in the summary rather than dictionary-adding them here.
- Render the rebuilt file (GitHub preview or `grip`) and read it end to end: trees
  monospace, tables the right width, catalogue readable coin by coin, no leftover
  scrambled fragments.
- Hand off to `fix-ocr` for the remaining letter-level garble in the prose.

## Boundaries with the skills this coordinates

| Sub-problem | Owning skill | This skill's part |
|:--- |:--- |:--- |
| A **bordered** table `pdfmd` flattened | `detect-missing-tables` | none -- run it; this skill is for what its `FLATTENED` signal catches *after* `MISSING`/`UNKNOWN` are clear |
| `*[figure]*` placeholder convention, `rect=` extraction | `detect-missing-tables` | reuse it verbatim for maps and plates |
| Column-order scramble across a page/file | `reconstruct-scrambled-md` | use its method for map-adjacent paragraphs; don't reconstruct a whole two-column file here |
| Headings folded into body text, file-wide | `restore-headings` | remove only the bogus headings *inside* flattened regions; run `restore-headings fix` for the rest |
| Is this dense script a catalogue or a plate? | `flag-unruled-catalogs` | run it before rebuilding a foreign-script region |
| Reading a legend off a render (corroborate or flagged-guess) | `transcribe-foreign-script` | hand it each legend that ends up inside a rebuilt cell; it also tells you to skip plates |
| Letter-level OCR garble in prose | `fix-ocr` | the pass *after* this one; only touch glyphs inside regions being rewritten |

## Markers

This skill introduces **no marker of its own**. Restructuring a flattened structure
removes the `\|` fingerprint, so `detect-missing-tables screen` reports
`FLATTENED 0` on its own once the work is done. If the same page also carries a
genuine `detect-missing-tables` `MISSING` / `UNKNOWN` finding, retire *that* with
*that* skill's `table-ok` / `table-deferred`. If a legend inside a rebuilt cell
can't be read, use `transcribe-foreign-script`'s `script-ok` / `script-guess` /
`script-deferred`.

## Known limits

- **A conjectural genealogy cannot be rendered faithfully in ASCII.** The 1970s
  charts route connector lines in ways box-drawing characters approximate at best.
  The code block needs every name in roughly its printed position and clearly
  labelled schematic -- pixel-accurate edge routing is not the goal, and chasing it
  is wasted effort.
- **Row alignment in a borderless table is read by eye.** There is no `cells`
  equivalent without rules; `flag-unruled-catalogs` documents why automated
  row/column detection stays unsolved on this corpus.
- **The `FLATTENED` screen has no page granularity.** It reports line numbers, not
  pages, and cannot be silenced by a marker. A file is only clean here once every
  flattened structure is actually rebuilt.
- **Not a detector.** Like `flag-unruled-catalogs`, this skill makes no claim worth
  marking -- it is a procedure for turning a confirmed pile of flattened structures
  into a document. The recall question ("did the screen catch every flattened
  structure?") belongs to `detect-missing-tables` and `restore-headings`.

## What NOT to do

- Don't run this on a file whose `FLATTENED` residue *is* a bordered table -- that
  is `detect-missing-tables` Tier 2.
- Don't transcribe a plate of drawings. Layout decides, not legibility.
- Don't invent genealogical links, `Obv.`/`Rev.` labels the source doesn't print,
  or a methodology note in visible text.
- Don't add scholarly diacritics to names a 1970s typewriter set in plain ASCII.
- Don't fix surrounding prose for spelling or style -- that is `fix-ocr`, next pass.
- Don't commit or open a PR as part of the skill unless the user asks; leave the
  rebuilt file in the working tree for review.
