# What a reading gets written back under

`docs/skill-list.md` says which skill finds which defect. This page says what
the repair is supposed to look like once it is found — the corpus conventions
that no screen can check, accumulated from files the user has taken through by
hand (`ONS_046`, `ONS_051`, `ONS_056`, `ONS_065`-`ONS_073`, `ONS_076`,
`ONS_082-083`, `ONS_164`, `IS_027`).

The governing rule is **fidelity to the page, not to correctness**. `pdfmd
--ocr auto` runs an English language model over the image, and that model
silently improves what it reads. Every rule below is a consequence.

## Fidelity

- **Restore the source's own typos.** When a render and the PyMuPDF text layer
  agree that the page prints `walikng`, `Darmstat` or `Husan Shah`, write
  that — not the OCR's cleaned-up `walking`, `Darmstadt`, `Husain`. These stay
  flagged by cspell by design; **do not add them to a dictionary**, which
  would mask the same string everywhere else in the corpus.
- **German titles in the typescript often lack umlauts** (`Goldmunzen`,
  `Falschungen`). That is the source. Don't "restore" ä/ö/ü.
- **Keep the authors' own inconsistencies**, e.g. `(contd.)` beside
  `(cont.d)` in one bibliography.
- **A divider the author printed is not table residue.** Where the source
  prints `‖` mid-translation (OCR'd as `\|\|`, e.g. "the O‖ne"), that is the
  author's typographic convention inside already-correct English. Leave it,
  even though it trips `lint_structure.py`'s stray-`\|` check forever.

### Diacritics cut both ways

The same "the engine normalised it" pattern runs in the opposite direction on
a professionally typeset page. Where the scan is not 1970s typescript and
prints scholarly diacritics, the OCR's English LM strips them: `ONS_073`'s
Hennequin article ("Denominations on contemporary Arab coinage") came out
`girsan / gurus / fulus / darahim / dananir / nisf` where the page prints
`ġiršān / ġurūš / fulūs / darāhim / danānīr / niṣf` — ġ dot-above, š caron,
ā/ū/ī macron, ṣ underdot. Restore what the page prints (render and zoom to
read the marks), including `-an` → `-ān` where the macron is there and *not*
where it isn't, then add the diacritic forms to `islamic-numismatics.txt`.

`fix-ocr`'s `detect_confused_glyphs.py` (the `glyphs` row of
`docs/screens.tsv`) covers only the case where the OCR turned a mark into a
*letter* — `ī`→`T`, `ū`→`Q`, surfacing as a capital inside a lowercase word
(`al-JalTl`, `MansQr`). It does **not** cover a mark the OCR simply dropped,
which leaves a clean real word (`gurus` for `ġurūš`) that is invisible to
every screen. Keep suspecting that in typeset Arabic/Persian transliteration.

**One issue can legitimately mix two conventions for the same names**, when a
table was typeset differently from the prose around it. `ONS_164`'s
TIRMIDH/BALKH succession table prints full macrons — Mas'ūd, Khusrūshāh,
Ibrāhīm, Arslān, Khāqān, Tafghāch — while the surrounding Fedorov article's
typed prose uses a simplified `ü`-for-ū convention (Mas'üd, Khusrüshah,
Ibrahim, Arslan) for the very same rulers. Both are what the page prints. A
pass that normalises one to the other is working from internal consistency
rather than from the render, and is wrong by this repo's own rule — one
`fix-ocr` run stripped that table's macrons to match the prose and had to be
reverted. Re-render the specific page before judging a diacritic mismatch to
be an error.

## Structures the newsletters repeat

### The masthead

The ONS newsletter masthead is a **flattened two-column table**: Secretary
General / Newsletter Editor / Annual Subscription down the left, Regional
Secretaries (General Section / Europe / UK. and Eire / North America) down the
right. The whole `ONS_042`–`ONS_070`+ run leaves it as two or three run-on
prose lines. Rebuilt (done on `ONS_066`, `ONS_069`, matching the `ONS_065`
layout), it is:

- the `Newsletter number NN — Month Year` line (em dash) pulled out above
  everything;
- two headerless `|  |  |` pipe tables, label | name, colons stripped from the
  right-hand labels;
- `Regional Secretaries:` as a plain line between the two tables;
- every section and article heading the mash buried split out
  (`## New Regional Secretary`, `## Members news`, `## <article title>` +
  `*by Author*`).

Render PDF page 0 to disentangle it. Two letter-level fixes recur:
`Mr. -  -  Broome` → `Mr. M. R. Broome`, and `H.F1.` → `H.Fl.` (clean forms
confirmed in `ONS_047`, `ONS_049`, `ONS_060`).

Two interactions to expect, neither a defect:

- `restore-headings scan` will report the rebuilt bold-only heads as
  `OVERSET`. That is its documented false positive for heads with no underline
  or capitals, not a signal to revert.
- **A rebuilt masthead's run-in label italics go.** The page sets the
  left-hand labels bold-italic and the right-hand ones bold roman, but once
  the two pipe tables encode that distinction the cells are written plain
  (confirmed on `ONS_051` and `ONS_056`). So a `restore-italics` pass run
  *before* the rebuild adds a `*Newsletter Editor*` the rebuild then removes.
  Do the restructure first, or expect to drop it.

### "Some recent publications" bibliographies

These flatten into run-on prose. The early newsletters rebuild as a bulleted
list, one entry per line, per `ONS_065`:

```
- *Surname, Init.*, title, venue, date, pages
```

with `*Papers*` / `*Books*` as bold-italic sub-labels. Author names are
italic in the source. Restore initials the OCR word-layer drops (`Hebert,` →
`*Hebert, J.*`, confirmed by render).

Later newsletters keep the list as flowed paragraphs with no bullets — one
entry per blank-line-separated line. There the `restore-italics` job is to
wrap **the attribution span through the comma before the title**:
`*Auge, C., Curiel, R. and Le Rider, G.,*`, `*Morris, G. B. (editor),*`,
corporate authors and all. Italic is the default; `ONS_071` was left
non-italic to match its file, `ONS_073` had them restored. Ask only if the
file is a mess.

The OCR routinely **merges two entries onto one physical line**
(`… London 1980 Becht, G. H., …`). Split at the point the render shows a new
flush-left author, and do it in the `restructure` pass — `fix-ocr`'s
line-break invariant forbids it later.

A reference-key list (`References:`, then `Y. …` `1. …` `2. …`) rebuilds as
the `Y.` line as a paragraph followed by a blank-line-separated ordered list
with 3-space-indented continuations — the same shape as a footnote list.

### Numbered specimen catalogues

`ONS_076`'s Wiggins catalogue of seven Qandahar rupees set the shape: the same
blank-line-separated `1.`–`n.` ordered list with 3-space-indented continuation
lines. A per-entry hand-lettered Arabic margin legend becomes a 3-space-
indented headerless `|  |  |` pipe table nested in the list item, followed
immediately — no blank line — by its `<!-- script-guess … -->`.
`lint_structure.py` tolerates the indented table. Keep the page's own
lowercasing (`illustrated as Fig. I`).

### Coin-description blocks

In the Islamic and Indian articles (`ONS_071` Deyell & Goron is the model) a
catalogue entry flattens into: a dimension line read as a bogus heading
(`## AV, 31 mm …`), a `# Reverse.` / run-on `Obverse.` label pair, a wall of
reversed Arabic interleaved with clean printed transliteration, a
`## Margins: …` line, then the footnotes. Rebuild as:

- a plain dimension line;
- `*[figure]*` for the coin drawings;
- the legend as a label line (`Reverse.`) plus a headerless `|  |` pipe table
  of `| <arabic> | <transliteration> |`.

Use `script-ok` when the page prints the transliteration right beside the
hand-lettering, as Deyell does; `script-guess` otherwise, and `script-guess`
even on a side-by-side block when **one** Arabic word is missing from the
printed transliteration (on `ONS_073`, جلوس / *julus*). An author's
hand-lettered legend reproduction with no printed transliteration at all
(Speight and Goron on `ONS_071` p3) is still body text to transcribe, not a
plate — `script-guess spellcheck=fail` — and visible divider strokes stay as
`|` on the non-table line.

A short side-by-side `Obv.`/`Rev.` legend pair rebuilds as a three-column
headerless table, `| Obv. | <translit> | <arabic> |`.

Two-column footnote lists (`1 2 5 6 7 | 3 4`) flatten to one logical `1.`–`n.`
sequence.

### Footnotes

Body reference markers are superscript-digit glyphs appended to the word
(`Kappelhof⁷`, `specimen²`), which the OCR turns into a stray `'`, `?` or
`\*`. The footnote list is numbered paragraphs, `1. …` `2. …`, and the OCR
drops the marginal numbers entirely. Both halves have to be read off a render
of the page — the superscripts in the body and the left-margin numbers in the
list. See `ONS_046` and `IS_027`.

## Foreign script inside a rebuilt structure

- **An inline hand-drawn legend set mid-sentence** (the Nagari coin legends in
  `ONS_082-083`'s Dhar prose) gets the standard script transcribed inline for
  the author's own romanised reading, plus a `<!-- script-guess -->`. Because
  the marker's target is the previous content line, split the sentence into its
  own one-line paragraph with the comment immediately after it and no blank
  line between. `lint_structure.py` then WARNs "non-Latin glyph in an English
  prose line"; that WARN is expected here.
- **Hand-lettered CJK legend rows**, which `pdfmd` tends to emit as bogus
  `# ` Arabic headings, get standard Han in a headerless `|  |` pipe table
  plus `script-guess`.
- **`spellcheck=` by script.** `spellcheck=n/a` for a verifiable CJK idiom
  (状元及第, 江山共老), `spellcheck=fail` for an unverifiable string. cspell
  ignores CJK entirely; Devanagari tokens (संवत, सरकार) do flag, and that is
  expected — don't dictionary-add them.

## Figures

When `pdfmd` emits no marker at all for a plate, the chosen form is a bare
marker with no coordinates, leaving the rect for a later pass:

```
*[figure]* <!-- figure page=N -- caption -->
```

`ONS_082-083` was done that way. `ONS_081` used estimated `rect=` values
instead; ask which the file should get.
