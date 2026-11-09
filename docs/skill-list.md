# Project skills

This repository's `jons/` corpus is OCR'd from scanned Oriental Numismatic Society publications by `pdfmd --ocr auto` (see `scripts/build.sh`). That pipeline reads typewritten English prose well, but it has no notion of figures, tables, columns, fonts, or hand-lettered foreign script — so each class of damage it leaves behind has its own skill. The skills below live in `.claude/skills/`; they are invoked by name when the matching defect is suspected, and they are designed to compose: most structural passes are typically followed by `fix-ocr` for the remaining letter-level cleanup.

## Detection skills

These look at the rendered PDF page rather than (or alongside) the Markdown, catching problems that leave no trace in the text itself.

- **detect-missing-figures** — Finds maps, graphs, drawings, coin photographs, and plates on a source-PDF page that the Markdown has no `figure` (or `script-*` / `table-*`) marker for. `pdfmd` either drops a drawing without a trace or OCRs its labels into garbage text; because it works from the rendered page, this skill catches what no Markdown-side screen can see. A `figure-unchecked` marker, left by another skill's pass when it had the render open and saw a figure it was not there to work, is reported as a `FLAGGED` page and never suppresses `MISSING`.
- **detect-missing-tables** — Finds bordered tables in the source PDF that `pdfmd` flattened into interleaved prose, leaving the Markdown with no table where one belongs, and can optionally rebuild the table from the existing OCR layer and insert it at the right place. The flattened result reads as garble but is not letter-level OCR damage, so `fix-ocr` must not be pointed at it.
- **flag-unruled-catalogs** — Distinguishes an isolated foreign-script legend (fine for `transcribe-foreign-script` to handle one line at a time) from a sustained, whitespace-aligned catalog table with no ruled borders, which no skill can safely process automatically. It exists to prevent a costly mistake: blindly running transcription Tier 2 over dozens of catalog rows that are really one table.

## Repair skills

Each of these rebuilds one structure or fixes one class of damage that `pdfmd` left behind.

- **fix-ocr** — The workhorse: finds and corrects letter-level OCR errors in a `jons/` Markdown file — garbled characters, real-word confusions cspell cannot see, suspect glyphs (`¥` is usually `½`), and even passages pdfmd read mirrored so every word is spelled backwards. It treats errors as mechanical OCR mistakes, not authorial typos, and is typically the final pass after a structural repair. Two of its screens need no render and so cost nothing to run — `detect_dropped_punct.py` for the issues whose text layer dropped nearly every sentence-ending period, and `detect_marker_noise.py` for the garble traces no other screen sees -- the characters and short strings pdfmd leaves standing where the scan printed something else, listed in `traces.tsv` and extended by adding a row, with `glyph-ok` / `glyph-deferred` to retire one the scan shows is really printed — and both are measured into `docs/screens.tsv` as the `punctuation` and `markers` rows. A third Markdown-only screen, `detect_confused_glyphs.py` (the `glyphs` row), finds the confusions that land *on a word* and so hide from cspell entirely: a diacritic read as a capital (`al-JalTl` for `al-Jalīl`, `MansQr` for `Mansūr` — 15,180 findings across 199 files, and the whole `ONS_16*`-`ONS_20*` run is affected), a hyphen read away (`IndoAfghan`), a digit read as a letter in a slot where only a number fits (`1010-1 Oil` is `1010-1011`, and `Oil` is in every dictionary), a lost range dash (`AD 17191748`), and a bracket standing in for a letter (`t)pe`). `glyph-ok` retires one the scan shows is really printed. Its sixth label is off by default and keeps its own `variants` row, because it is a standing backlog rather than a defect list: one name spelled two ways in one file, differing in its diacritics (`Nizamshahï` x26 beside `Nizāmshāhī` x2) — 4,355 groups across 138 files, invisible to cspell once the dictionaries hold both forms. That pair says only that the file disagrees with itself, never which form is right, so it goes to a render; two conventions in one issue are sometimes genuine.
- **clean-ocr-formatting** — Repairs three OCR layout artifacts that travel together: per-word asterisks from letter-spaced text (`*word *`), words split with internal spaces (`Numi smat i c`), and paragraphs severed mid-sentence by a stray blank line. Usually followed by `fix-ocr` for the remaining single-word errors.
- **reconstruct-scrambled-md** — Rebuilds a file whose source PDF had a two-column layout that `pdfmd` read across instead of down, interleaving the columns mid-word. This is a structural failure, not garble, and needs reconstruction rather than word-level fixes.
- **restore-headings** — Recovers section headings that `pdfmd` folded into the body text (glued to the end of a paragraph, or missing their emphasis) and removes headings it invented where the scan has none.
- **restore-lists** — Finds lists that do not render as lists — items `pdfmd` glued into one paragraph, labelled lines kramdown joins into prose (`i. ...<br>`, `a) ...`, `(1) ...`), and items whose labels the OCR dropped — by reading the scan for lines at one left edge whose labels count up. Restores them to Markdown lists, with `{: .labelled}` bullets for any label kramdown cannot number.
- **restore-italics** — Restores italic passages — book and journal titles, foreign terms, run-in masthead labels — that the source PDF's text layer records but the Markdown lost, because `pdfmd` re-OCR'd the page image and never saw the fonts.
- **transcribe-foreign-script** — Finds Arabic, Devanagari, or Chinese-character garble (or stale `<!-- OCR: ... -->` placeholders that never actually opened the PDF), renders the source page, and transcribes the legend by eye, inserting a corroborated reading as verified (`script-ok`), a plausible one for further checks (`script-guess`), or — when the script was legible in a `fix-ocr` tile but the page was never rendered — an unverified one as `script-unchecked`, which is the one marker that keeps a file off a clean screen until someone confirms it. Two of its four screens find legends that carry no foreign codepoints at all, because `pdfmd` read the script as Latin letters (`LATIN`) or as a heap of carets (`CARET`); a lone caret is a footnote marker about half the time, so `CARET` wants a cluster and leaves the singletons to fix-ocr's `markers` screen. Only applies to legends in running text; plates of facsimiles are artwork and are skipped.
- **restructure-flattened-md** — The coordinating pass for everything else `pdfmd` flattened into prose: family trees, borderless tables, hand-drawn maps, plates, and underlined bibliography titles. It owns none of the other skills' jobs and defers each hard sub-problem to the skill that does it; use it when `detect-missing-tables screen` reports flattened lines but no missing bordered tables.

## Maintenance skills

- **clean-dictionary** — Audits the project spellcheck allowlists (`dictionaries/{chinese,islamic,indian}-numismatics.txt`) and removes OCR garble that earlier fix-ocr runs incorrectly added, since every such entry permanently masks that garble corpus-wide. It preserves legitimate numismatic terms and proper names, and only removes entries — the unmasks get reported for a later fix-ocr run.

## Order of operations

Letter-level garble is the damage a reader spots unaided in the bare
Markdown; structural damage is not, which is why `fix-ocr` is the skill most
often asked for and why it is the easiest one to run too early. Run it first
and much of its work has to be done twice, because **three of the screens
cannot see damage that another kind of damage is hiding.**

Work a single file in this order. `survey.py show --file <STEM>` prints its
outstanding screens in it.

1. **Structure, read off the page** — `reconstruct-scrambled-md` (column
   order first; nothing below is meaningful if the text is interleaved), then
   `detect-missing-tables` / `restructure-flattened-md`, `restore-headings`,
   `restore-lists`, `detect-missing-figures`.
2. **Script** — `transcribe-foreign-script`.
3. **Content** — `clean-ocr-formatting`, then `fix-ocr`: letters, then
   markers, then punctuation.
4. **Re-measure** — `survey.py run <STEM> --refresh`. Structural work moves
   line numbers and exposes findings that were not visible before.

### Why that order, from ONS_162

Each of these cost a second pass over the same pages:

- **Script before markers.** Five footnote markers in the Chaghatayid article
  sat *inside* Arabic garble. `detect_marker_noise.py` works on the Markdown,
  so it could not see them until `transcribe-foreign-script` had cleared the
  legends around them.
- **Lists before markers.** The supplement's footnote block has 64 entries.
  A marker inventory run on the unsplit block found **four** — the rest were
  mid-line, glued behind the previous entry's text, where a scan for a trace
  at a token's end cannot reach. `restore-lists` puts every label at a line
  start first.
- **Tables before everything.** A "Literature" block had been turned into a
  spurious three-row pipe table by an earlier pass, with two of its items
  also left duplicated as prose underneath. `fix-ocr` read the table's
  contents as ordinary prose and corrected words inside a structure that
  should not have existed.
- **Punctuation last.** `punct_candidates.py --apply` is explicitly a
  run-once pass — it keeps no record of a candidate you looked at and
  rejected, so a second run restores every mark you removed. Spend it after
  the structure is settled, not before.

### The one genuine cycle

Numbering the footnote list needs the body's footnote markers, which is
`fix-ocr`'s work; splitting the list needs the page, which is
`restore-lists`'. Neither can finish alone.

They are the same evidence read twice. One careful read of the note pages
yields the body markers *and* the list labels together, and the two
cross-check each other — in ONS_162 the body markers ran 1-64 with no gaps,
which is what confirmed the split was right. When a file has footnotes, read
the note blocks and the body markers in a single pass and let both skills
consume the result.

### The pattern worth remembering

A screen cannot report damage that destroys the feature it keys on.
`restore-lists` anchors on labels (`1.`, `i.`, `a)`) and so is blind to a list
whose labels the OCR destroyed; `fix-ocr`'s post-apply sweeps filter out
`www|http|@` and so are blind to the e-mail addresses that lost their periods
along with the prose. Both are open issues. When a screen calls a file clean
that you have reason to doubt, ask what it keys on and whether the damage
eats it.
