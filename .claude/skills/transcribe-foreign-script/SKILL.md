---
name: transcribe-foreign-script
description: Find Arabic, Devanagari, or Chinese-character OCR garble in a `jons/` Markdown file — either a raw unflagged run of foreign-script noise, or an existing `<!-- OCR: ... -->` placeholder that defers to "the source PDF" without anyone having opened it — then render the corresponding PDF page and transcribe the legend by eye. Only applies to running body text: a single legend embedded in a paragraph. Inserts a corroborated reading as verified, or a plausible-but-uncorroborated reading flagged for further verification (with a cspell pass/fail note); a plate or grid of hand-drawn coin/seal facsimiles is artwork, not text, and is skipped regardless of legibility. Use when the user asks to fix, transcribe, or recover a foreign-script legend or caption, or to revisit old `<!-- OCR -->` placeholders now that the PDF can be rendered and read.
---

# transcribe-foreign-script

`pdfmd --ocr auto --lang eng+ara` reads Latin-script prose reliably enough for `fix-ocr` to patch the remainder letter by letter. It does not read hand-lettered Arabic, Devanagari, or Chinese-character legends at all reliably — the result is either a run of nonsense codepoints sitting in the Markdown (sometimes even misparsed as a heading), or, in about half the corpus's `<!-- OCR: -->` comments, a placeholder someone wrote saying the PDF is needed, without the PDF ever actually being opened.

This skill is for that second kind of failure specifically. It is not a variant of `fix-ocr`: `fix-ocr` corrects letter-level garble using the extracted text layer and cspell — a text-only, pattern-matching task. Recovering a foreign-script legend requires rendering the page as an image and reading it visually, the same "trust pixels, not the text layer" move `detect-missing-tables` makes for tables. Do not point `fix-ocr` at this kind of garble; it has no mechanism for it and will correctly refuse.

## Lessons this skill encodes

On `IS_004`, a first pass wrote `<!-- OCR: Arabic-script obverse legend; source PDF required for accurate script -->` in place of a garbled line — without opening the PDF. Once the PDF was actually rendered, the legend (`اکبر شاه بادشاه غازی سکه مبارک`) was not only legible but matched, word for word, the English transliteration already printed on the very next line (`Obv. Akbar Shah Badshah Ghazi, sikka mubarak`). The comment was not a defensible judgment call — it was an unverified excuse. **A placeholder that says "the PDF is required" is only honest once the PDF has actually been opened and found wanting.**

A later pass on the same file overcorrected in the opposite direction: it ran Tier 2 on `IS_004`'s "Coin Inscriptions"/"Copper Coins" plate — ~35 hand-drawn facsimiles of individual coins, each one a picture of a specific physical specimen, arranged in a numbered grid — and guessed a reading for each one, as if the plate were 35 short lines of body text. It isn't. A plate like this is artwork: the author's own note beside it ("I must apologise for any inaccuracies in the drawings which are entirely due to my poor draughtsmanship") says the drawings were never meant as an accurate letter-for-letter record in the first place. Legibility was never the right test for whether to transcribe it. **Only guess at running body text; treat a plate of drawings as an image, full stop, the same way `detect-missing-tables` treats artwork in a table cell.**

That same pass also invented visible structure the source doesn't have: an English methodology note above the transcriptions ("Guessed transcriptions below are best-effort readings..."), `Obv.`/`Rev.` labels on stamps that print no such labels, and a Markdown-numbered-list format that put each catalog number *before* its Arabic reading when the plate prints the number *after* the drawing. None of that belongs in visible text — a reader of the rendered Markdown should see something that looks like the page, not an annotated report about the page. **Insert only what the page shows, in the order and position it shows it; everything else — labels you inferred, reasoning, methodology — goes in an HTML comment.**

## Hard constraints

- **First, decide whether this is body text or a drawing — layout, not legibility, is the test.** A single legend embedded in a paragraph (following or preceding ordinary prose, at normal line height, one instance illustrating what the surrounding text describes) is body text: the guess-or-corroborate policy below applies. A grid of several small numbered items — a plate of hand-drawn coin facsimiles standing in for photographs, a catalog of stamps or seals, anything whose purpose is "here is a picture of specimen #N" rather than "here is a sentence to read" — is artwork, not text, no matter how clearly individual strokes can be made out. Skip transcription entirely for a drawing and mark it `script-deferred` (see Markers), the same way `detect-missing-tables` marks a `*[figure]*` cell. When unsure, look at what surrounds the item: prose paragraphs and `Obv.`/`Rev.` lines mean body text; a bare grid of catalog numbers with no sentences means a plate.
- **Corroborate when you can; guess — visibly, flagged — when you can't.** *(Body text only — see above.)* Accept a reading as verified (`script-ok`) only when something independent confirms it: a transliteration printed on the same page, a matching form elsewhere in the file, a citable reference work. When nothing corroborates it but the render still supports a plausible reading, insert that reading anyway rather than leaving the page with no attempt at all — mark it `script-guess` (see Markers) with a comment that flags it as unverified and reports whether its words pass or fail cspell (`spellcheck` subcommand). A guess is a real transcription attempt, not a shrug: read the image as carefully as you would a corroborated legend: the difference between `script-ok` and `script-guess` is what backs the reading up, not how much effort went into reading it.
- **Visible Markdown must approximate what the PDF page actually shows — nothing else.** Insert only the transcribed script itself, in the page's own order and position: a catalog number that follows the drawing in the source follows it in the Markdown too, not a Markdown-list-style number prefix. Don't add a label like `Obv.`/`Rev.` unless the source literally prints that label next to the content — most of this corpus's stray legends don't (the already-labeled Section I/IV style entries elsewhere in `IS_004` are a different case, pre-existing in the source, not something this skill adds). Every explanation belongs in an HTML comment instead, never in the visible line: which block is obverse vs. reverse when the source doesn't label it, why a reading was accepted or not, corroboration reasoning, confidence, a methodology note about the pass as a whole. A reader looking at the rendered Markdown should see something that reads like the page, not a report about the page.
- **`script-deferred` — no text inserted — covers two different cases; say which.** Either the content is a plate of drawings rather than body text (see above — this holds regardless of legibility), or it's body text that doesn't support even a plausible guess: genuinely illegible at the available resolution, no legible strokes to read at all. Don't conflate them in the reason — "this is artwork" and "this is text I can't read" call for different follow-up later.
- **Never delete a run of foreign-script or garbled text without a replacement**, per `fix-ocr`'s own rule — substitute a reading (verified or guessed) or an honest, specific comment.
- **A `script-deferred` comment must say what was tried.** Not "source PDF required" in the abstract — which page was rendered, what is actually on it, and why it's being skipped (a plate of drawings, or body text where not even a guess was possible). See the Markers section below for the shape.
- **Reading the render is a job for a stronger model than the rest of the workflow needs.** Misreading cursive Arabic or a smudged Devanagari numeral is easy and hard to catch later, so do the actual look-and-transcribe step as an `Agent` call with `model: "opus"`, not inline on whatever model is running the screen/render/edit mechanics. Give that agent the rendered PNG, the candidate line, and the surrounding corroborating text, and ask it to report a reading either way — confirmed, or its best plausible guess — rather than only reporting confirmed readings.
- **Mark every candidate you resolve, one way or another** (see Markers below), so a clean screen stays clean instead of re-flagging verified transcriptions, or guesses, as garble on every future run.
- Do not touch surrounding prose beyond the candidate line itself. This skill corrects one script passage at a time, like `fix-ocr` corrects one letter-level error at a time.

## Workflow

### Tier 0 — screen

```
python3 .claude/skills/transcribe-foreign-script/scripts/detect_script_garble.py screen IS_004 [IS_005 ...]
```

Reports two kinds of finding, per file:

- **`COMMENT`** — an existing `<!-- OCR: ... -->` placeholder whose text mentions script/legend/transliteration/mirror/glyph keywords. 68 of the corpus's ~148 `<!-- OCR: -->` comments currently match; each is a candidate for a second look now that rendering is on the table.
- **`RAW`** — a run of Arabic, Hebrew, Devanagari, or CJK codepoints sitting outside any HTML comment, i.e. undocumented garble nobody has flagged yet (the `IS_004` line-92 case before it was fixed).

A run under 2 characters is not reported — a single stray glyph in English prose is `fix-ocr`'s "delete as noise" case, not a transcription job.

Exit status is `0` only when nothing is outstanding, so it scripts over the corpus the same way `detect-missing-tables screen` does. Pass `--no-raw` to judge only the comment backlog.

### Tier 1 — locate and render

For each candidate, find which PDF page it came from, then look at it:

```
python3 .../detect_script_garble.py locate IS_004 --line 92
python3 .../detect_script_garble.py render IS_004 --page 4 --dpi 300 --out /tmp/p5.png   # then Read the image
```

`locate` pulls the alphabetic words of 5+ letters from a few lines around the candidate and ranks PDF pages by how many appear in that page's text layer — the same trick as manually grepping the PDF for a distinctive nearby phrase, generalized. It is a ranking, not a certainty: garbled surrounding text yields fewer usable words, so widen `--window` or check the runner-up page if the top match's score looks weak. `render` takes an optional `--clip x0 y0 x1 y1` (PDF points) to zoom into just the legend once you know roughly where it sits on the page.

**Before doing anything else with the render: is this body text or a drawing?** (See Hard constraints.) A plate or grid of numbered hand-drawn facsimiles goes straight to `script-deferred` — skip Tier 2 entirely, no matter how legible it looks. Only proceed to Tier 2 for an item that reads as running text: a legend inline with surrounding prose, at normal paragraph scale.

### Tier 2 — transcribe, corroborate or guess, insert

*(Body text only — a plate of drawings was already routed to `script-deferred` in Tier 1 and doesn't reach this step.)*

1. Spawn an `Agent` call with `model: "opus"` carrying the rendered image, the candidate line, and enough surrounding Markdown to show any nearby gloss. Ask it for a reading and, separately, whether anything corroborates it — a transliteration on the page, a matching form elsewhere in the file, a citable reference. Ask it to still report its best plausible reading even when nothing corroborates it, and to say explicitly when the image doesn't support even a guess.
2. **Confirmed** (something corroborates it): replace the candidate line's content with the corrected reading — Unicode script text only, positioned and labeled exactly as the page shows it (see the visible-Markdown constraint above), not a transliteration and not an invented `Obv.`/`Rev.` label the source doesn't print. Mark `script-ok`.
3. **Plausible but uncorroborated**: insert the guessed reading the same way, then run it through spellcheck:
   ```
   python3 .../detect_script_garble.py spellcheck "اکبر شاه بادشاه غازی سکه مبارک"
   ```
   Mark `script-guess`, with the spellcheck result in the marker (see Markers) — `pass` doesn't make a guess correct (a wrong-but-real word still passes), and `fail` doesn't make it wrong (real corpus vocabulary is still missing from the dictionaries sometimes), but both are useful signal for whoever verifies it next.
4. **No plausible reading at all**: leave the line as-is (or the run being replaced), and write a `script-deferred` comment naming what was tried and why even a guess wasn't possible (see Hard constraints above) — not a generic "source PDF required."
5. Re-run `screen`; the finding should move to `RESOLVED`, `GUESSED`, or `DEFERRED`. Unlike `RESOLVED`/`DEFERRED`, `GUESSED` lines print on every `screen` run (not just `-v`) — they're unverified content sitting in the corpus, not settled business.

## Markers

Same shape as `detect-missing-tables`' `table-ok` / `table-deferred`, and read by `find_candidates()` in the script — a marker comment applies to the nearest preceding non-blank content line:

```
اکبر شاه بادشاه غازی سکه مبارک
<!-- script-ok reason=transcribed from PDF p.5 hand-lettered legend; confirmed against the "Obv." transliteration on the same page -->

طلسم نامعلوم كلمة غريبة
<!-- script-guess page=9 rect=60,410,520,460 spellcheck=fail:طلسم reason=body-text legend in the reign-summary paragraph, no adjacent transliteration on this page to check it against; read directly from strokes at 400dpi -->

<!-- OCR: Arabic-script coin legends; source PDF plate required for accurate transcription -->
<!-- script-deferred page=6 rect=80,150,540,780 reason=not body text -- a plate of ~35 hand-drawn coin facsimiles arranged as a numbered catalog grid, each a picture of a specimen rather than a sentence; the author's own note calls the drawings imprecise ("poor draughtsmanship"), so treat as artwork regardless of how legible individual strokes are -->
```

- **`script-ok`** — transcribed and verified. Counted as `RESOLVED`.
- **`script-guess`** — body text, transcribed, plausible, but **not** independently confirmed. The `spellcheck=` field records the `spellcheck` subcommand's verdict: `pass` (all words recognized by the corpus's Arabic/Persian/numismatic dictionaries — not proof of correctness, a wrong-but-real word still passes) or `fail:<words>` (the listed words are unrecognized — not proof of error, real corpus vocabulary is sometimes still missing from the dictionaries, and Devanagari/CJK aren't meaningfully spellcheckable at all so expect `fail` there regardless of quality). Counted as `GUESSED` — printed on every `screen` run, not just `-v`, since it is unverified content, not settled business.
- **`script-deferred`** — no text inserted. Two distinct reasons land here (say which in the comment): the content is a plate of drawings rather than body text (see Hard constraints — the `IS_004` coin-inscriptions plate above), or it's body text illegible at any available resolution. Counted as `DEFERRED`, the standing worklist of what's left.

Without a marker, an inserted reading (verified or guessed) is indistinguishable from unverified garble to the screen — it is still a run of foreign-script codepoints — so it re-flags as `RAW` forever. Always mark what you resolve, guess, or defer.

**When the transcribed content is a reconstructed table (columns like image/native script/transliteration), leave a blank line between the table's last row and its marker.** GitHub's renderer needs a table set off by blank lines on *both* sides — `detect-missing-tables`' own governors-table fix on `IS_005` covered the "comment directly before a table" direction; a marker directly after a table with no blank line is the same bug from the other side, and `IS_006`'s 14 reconstructed tables hit it. `find_candidates()` in the script tolerates exactly one blank line here — a marker separated from its table by a blank still resolves every row in it, not just the last one — so this costs nothing but the blank line itself.

### `rect=` — recording where on the page, not just which page

`page=N` alone is ambiguous when several deferred regions share one page — `IS_005` page 12 (0-based) holds four catalog sections *and* an unrelated already-`table-deferred` distribution table below them. Add `rect=x0,y0,x1,y1` (PDF points, page-relative, same convention as `detect-missing-tables`' `*[figure]*` rects) so a later pass can jump straight to `render`'s `--clip` instead of re-deriving the region:

```
<!-- script-deferred page=12 rect=0,352,596,425 reason=page rendered and inspected while building the Type/Governor/Reign skeleton; ... -->
```

This is a **coarse bounding region for the whole deferred section**, not a tight or exact box — generous enough that `render --page N --clip x0 y0 x1 y1` reliably shows the full section with a little margin on either side, not a claim of pixel-perfect boundaries. Getting it right takes real verification, not a one-shot estimate:

1. Search the page for a distinctive anchor unique to the section — a full section-title word (`page.search_for("JIRM")`) works far better than a 2-3 letter row-code prefix like `"KB"` or `"AN"`, which matches dozens of false positives elsewhere on the page.
2. Expect most such searches to fail outright on this corpus. Backfilling `IS_005`'s 13 sections found a clean, unique hit for only 2 of ~15 section-title searches attempted (`JIRM`, `BAMIYAN`) — this corpus's embedded PDF text layer is unreliable even for printed English words (see Known Limits), so most rects had to come from row-level anchors (e.g. `"KS 1"`, `"W 1"`) or from interpolating between two confirmed neighbors' positions.
3. **Render the resulting clip and look at it before trusting it.** Interpolated estimates can be wrong in a way that isn't a rounding error: on `IS_005`, two interpolated rects (`BAMIYAN`, `GHARJISTAN`) landed 90-190pt off and rendered the *wrong section's content entirely* (the unrelated distribution table) rather than just cropping tight. A rect that hasn't been rendered and checked is a guess, not a coordinate.

## Known limits

- **cspell needs both `@cspell/dict-ar` and `@cspell/dict-fa-ir` installed globally, and both wired into `cspell.config.yaml`'s `import:` and `dictionaries:` lists, to clear a correct transcription.** This corpus's legends are Mughal-era Perso-Arabic, not Modern Standard Arabic: `ar` alone recognized `عالم` but not `غازی`/`مبارک`/`اکبر` (Persian KEHEH `ک` and FARSI YEH `ی` letterforms instead of Arabic `ك`/`ي`) or `بادشاه` (a Persian word, absent from any Arabic dictionary regardless of letterform). Adding `fa-ir` closed the letterform gap; `بادشاه` itself still needed adding to `islamic-numismatics.txt` as corpus vocabulary, same as any other recurring proper term. Devanagari and CJK are not meaningfully spellcheckable by cspell at all — don't expect a dictionary fix there.
- **`locate`'s page ranking degrades with the surrounding text's own OCR quality.** If the words immediately around a candidate are themselves garbled, there may be too few distinctive tokens to rank pages confidently — widen `--window`, or fall back to manually searching the PDF for a phrase you can read cleanly.
- **The embedded PDF text layer (what `page.search_for()`/`page.get_text()` read) is a separate, generally worse OCR pass than the one that produced the `.md` file**, and this applies to English words too, not just foreign script — searching `IS_005`'s pages for 15 different printed section-title words found a clean match for only 2 of them. Don't expect `search_for()` on an exact phrase to succeed; if it fails, that's the corpus, not a typo in your query.
- **Corroboration is not always available for body text.** Many legends in this corpus have no adjacent transliteration (unlike the `IS_004` Section I/IV cases, which happened to). That's the normal `script-guess` case, not a reason to defer — see Hard constraints. Reserve `script-deferred` for body text that doesn't support a plausible reading, or for content that isn't body text at all (a plate of drawings — see the layout test in Hard constraints, which comes first and is not about corroboration).
- **`spellcheck` pass/fail is weak evidence, not a verdict.** It only tells you whether the guessed words are already-known vocabulary in the corpus's dictionaries — a real word used in the wrong place still passes, and correct-but-rare corpus vocabulary can still fail. Treat it as one more data point for whoever reviews a `script-guess` later, not as a promotion path to `script-ok` on its own.
- **Mirrored/reversed text** (several existing `<!-- OCR: ... mirrored ... -->` comments describe sideways-printed or right-to-left-flipped page content) is a layout problem as much as a script problem; render the page and check whether flipping the clip horizontally before reading it helps, rather than trying to read it as printed.
