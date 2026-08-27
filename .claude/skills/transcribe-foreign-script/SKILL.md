---
name: transcribe-foreign-script
description: Find Arabic, Devanagari, or Chinese-character OCR garble in a `jons/` Markdown file — either a raw unflagged run of foreign-script noise, or an existing `<!-- OCR: ... -->` placeholder that defers to "the source PDF" without anyone having opened it — then render the corresponding PDF page and transcribe the legend by eye. Inserts a corroborated reading as verified, or a plausible-but-uncorroborated reading flagged for further verification (with a cspell pass/fail note); only leaves the page untranscribed when even a guess isn't obtainable. Use when the user asks to fix, transcribe, or recover a foreign-script legend or caption, or to revisit old `<!-- OCR -->` placeholders now that the PDF can be rendered and read.
---

# transcribe-foreign-script

`pdfmd --ocr auto --lang eng+ara` reads Latin-script prose reliably enough for `fix-ocr` to patch the remainder letter by letter. It does not read hand-lettered Arabic, Devanagari, or Chinese-character legends at all reliably — the result is either a run of nonsense codepoints sitting in the Markdown (sometimes even misparsed as a heading), or, in about half the corpus's `<!-- OCR: -->` comments, a placeholder someone wrote saying the PDF is needed, without the PDF ever actually being opened.

This skill is for that second kind of failure specifically. It is not a variant of `fix-ocr`: `fix-ocr` corrects letter-level garble using the extracted text layer and cspell — a text-only, pattern-matching task. Recovering a foreign-script legend requires rendering the page as an image and reading it visually, the same "trust pixels, not the text layer" move `detect-missing-tables` makes for tables. Do not point `fix-ocr` at this kind of garble; it has no mechanism for it and will correctly refuse.

## The lesson this skill encodes

On `IS_004`, a first pass wrote `<!-- OCR: Arabic-script obverse legend; source PDF required for accurate script -->` in place of a garbled line — without opening the PDF. Once the PDF was actually rendered, the legend (`اکبر شاه بادشاه غازی سکه مبارک`) was not only legible but matched, word for word, the English transliteration already printed on the very next line (`Obv. Akbar Shah Badshah Ghazi, sikka mubarak`). The comment was not a defensible judgment call — it was an unverified excuse. **A placeholder that says "the PDF is required" is only honest once the PDF has actually been opened and found wanting.**

## Hard constraints

- **Corroborate when you can; guess — visibly, flagged — when you can't.** Accept a reading as verified (`script-ok`) only when something independent confirms it: a transliteration printed on the same page, a matching form elsewhere in the file, a citable reference work. When nothing corroborates it but the render still supports a plausible reading, insert that reading anyway rather than leaving the page with no attempt at all — mark it `script-guess` (see Markers) with a comment that flags it as unverified and reports whether its words pass or fail cspell (`spellcheck` subcommand). A guess is a real transcription attempt, not a shrug: read the image as carefully as you would a corroborated legend: the difference between `script-ok` and `script-guess` is what backs the reading up, not how much effort went into reading it.
- **`script-deferred` — no text inserted — is now the narrower case.** Use it only when the image doesn't support even a plausible guess: genuinely illegible at the available resolution, no legible strokes to read at all, or (as with a large multi-item plate) more individual items than can be read and flagged one by one in the time available. Say which of these it was.
- **Never delete a run of foreign-script or garbled text without a replacement**, per `fix-ocr`'s own rule — substitute a reading (verified or guessed) or an honest, specific comment.
- **A `script-deferred` comment must say what was tried.** Not "source PDF required" in the abstract — which page was rendered, what is actually on it, and why not even a guess was possible. See `IS_004` lines 158/162 for the shape.
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

### Tier 2 — transcribe, corroborate or guess, insert

1. Spawn an `Agent` call with `model: "opus"` carrying the rendered image, the candidate line, and enough surrounding Markdown to show any nearby gloss. Ask it for a reading and, separately, whether anything corroborates it — a transliteration on the page, a matching form elsewhere in the file, a citable reference. Ask it to still report its best plausible reading even when nothing corroborates it, and to say explicitly when the image doesn't support even a guess.
2. **Confirmed** (something corroborates it): replace the candidate line's content with the corrected reading (Unicode script text, not a transliteration — the corpus already carries transliterations separately, as `Obv.`/`Rev.` lines). Mark `script-ok`.
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

كسل نيد الجرنت
<!-- script-guess page=6 rect=120,300,340,360 spellcheck=fail:كسل,الجرنت reason=one of ~35 hand-lettered stamps; no per-stamp transliteration to corroborate against, read directly from strokes at 400dpi -->

<!-- OCR: Arabic-script coin legends; source PDF plate required for accurate transcription -->
<!-- script-deferred page=6 rect=80,600,520,780 reason=rendered at 400dpi and inspected: ink present but strokes not distinguishable into letters at any available resolution -->
```

- **`script-ok`** — transcribed and verified. Counted as `RESOLVED`.
- **`script-guess`** — transcribed, plausible, but **not** independently confirmed. The `spellcheck=` field records the `spellcheck` subcommand's verdict: `pass` (all words recognized by the corpus's Arabic/Persian/numismatic dictionaries — not proof of correctness, a wrong-but-real word still passes) or `fail:<words>` (the listed words are unrecognized — not proof of error, real corpus vocabulary is sometimes still missing from the dictionaries, and Devanagari/CJK aren't meaningfully spellcheckable at all so expect `fail` there regardless of quality). Counted as `GUESSED` — printed on every `screen` run, not just `-v`, since it is unverified content, not settled business.
- **`script-deferred`** — no text inserted; not resolvable, not even a guess (or not worth the cost — see the `IS_004` copper-coins plate: dozens of stamps, ink present but strokes too indistinct to read even without corroboration). Counted as `DEFERRED`, the standing worklist of what's left.

Without a marker, an inserted reading (verified or guessed) is indistinguishable from unverified garble to the screen — it is still a run of foreign-script codepoints — so it re-flags as `RAW` forever. Always mark what you resolve, guess, or defer.

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
- **Corroboration is not always available.** Many legends in this corpus have no adjacent transliteration (unlike the `IS_004` cases, which happened to). That's the normal `script-guess` case, not a reason to defer — see Hard constraints. Reserve `script-deferred` for when the image itself doesn't support a plausible reading, not merely when nothing else confirms it.
- **`spellcheck` pass/fail is weak evidence, not a verdict.** It only tells you whether the guessed words are already-known vocabulary in the corpus's dictionaries — a real word used in the wrong place still passes, and correct-but-rare corpus vocabulary can still fail. Treat it as one more data point for whoever reviews a `script-guess` later, not as a promotion path to `script-ok` on its own.
- **Mirrored/reversed text** (several existing `<!-- OCR: ... mirrored ... -->` comments describe sideways-printed or right-to-left-flipped page content) is a layout problem as much as a script problem; render the page and check whether flipping the clip horizontally before reading it helps, rather than trying to read it as printed.
