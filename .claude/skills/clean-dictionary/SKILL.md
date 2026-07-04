---
name: clean-dictionary
description: Audit the project spellcheck dictionaries (`dictionaries/{chinese,islamic,indian}-numismatics.txt`) and remove entries that are OCR garble incorrectly added by earlier fix-ocr runs. Preserves legitimate words — terms found in online language dictionaries, numismatic specialist references, and proper names of places and scholars. Use when the user asks to clean, audit, prune, or validate the dictionaries, or when a garbled word is discovered to be masked by a dictionary entry.
---

# clean-dictionary

The three dictionaries under `dictionaries/` are allowlists for cspell over the `jons/` OCR corpus. Earlier fix-ocr sessions sometimes added OCR garble to them instead of fixing the source text (e.g. `fiir` for the German `für`, `bntish` for `British`, `Tiibingen` for `Tübingen`). Every such entry permanently masks that garble corpus-wide. Your job is to find and remove those entries — and only those. This skill touches only the dictionary files; the corpus under `jons/` is read-only context here, and the garble a removal unmasks gets reported for a later fix-ocr run, not fixed.

## Hard constraints

- **Verify before removing.** The mechanical heuristics below only generate *candidates*. Never remove an entry on a heuristic hit alone — every removal needs a positive identification of what the garble is a corruption of, confirmed against the corpus context where the word occurs.
- **When uncertain, keep the entry** and list it in the report. A wrongly-kept garble can be caught later; the report makes it visible. A wrongly-removed legitimate term silently breaks spellcheck on files already marked done.
- **Removals are whole-line deletions.** Never edit a word in place. If the corrected form belongs in the dictionary (a legitimate specialist term the corpus uses), add it as a separate line in alphabetical order within the correct section.
- **Preserve the file structure**: `#` section comments, one word per line, existing ordering of untouched lines.
- **Never edit files under `jons/`.** Reading them for context is essential; changing them is fix-ocr's job, not this skill's. Removing an entry resurfaces its corpus occurrences as cspell errors — that is expected. Report those locations so a follow-up fix-ocr run can repair them.

## What counts as invalid

An entry is garble if it is a mechanical corruption of an identifiable real word. The corpus-wide OCR confusions, written here as **garble → true form**:

- `ri` misread as `n` — `matenal` → `material`, `Smimova` → `Smirnova` (via `rn`→`m`)
- `li` misread as `h` — `pubhshed` → `published`, `Anatoha` → `Anatolia`
- `m` ↔ `rn`, `ni`; `u` ↔ `ii`, `n`; `cl` ↔ `d`; `l` ↔ `I` ↔ `1`
- **`ü` misread as `ii` or `u`** in German/Turkish/Wade-Giles words — `fiir` → `für`, `Hsiian` → `Hsüan`, `Kiirkman` → `Kürkman`, `Porzellanmiinzen` → `Porzellanmünzen`. Other dropped diacritics (`ö`→`o`, `ä`→`a`) follow the same pattern but need care: many romanizations legitimately drop diacritics (`Tubingen` appears in English text; `Tiibingen` never does). The `ii` digraph is the reliable garble signature.
- Doubled/dropped letters and merged words (two words fused into one token).

An entry is legitimate — **keep it** — if any of these holds:

1. It appears in a general language dictionary (English, or the source language for German/Dutch/Turkish/French titles quoted in the corpus). Check Wiktionary or an equivalent via WebSearch.
2. It is a numismatic specialist term: a denomination, mint name, dynasty, era name, or transliteration. Verify against numismatic references (Numista, Zeno.ru, Forum Ancient Coins glossaries, published catalogue names findable via WebSearch).
3. It is the proper name of a scholar, place, or historical figure (Wikipedia, library catalogues, journal mastheads).
4. It is a deliberate historical or archaic spelling quoted by the corpus (e.g. 17th-century Dutch coin names like `stuyver`, `rijcxdaler`). The corpus context makes these obvious: they appear inside quoted source material.

**Beware of OCR-echo false positives in web results.** A garbled token often gets search hits because *other* OCR'd scans online contain the same garble. A hit only validates a word if the source is edited text (a dictionary, an article, a catalogue), not a scanned document. `bntish` has plenty of Google hits; it is still garble.

## Workflow

1. **Generate candidates mechanically.** Run all of these; union the results.

   Reverse-confusion scan (fast; uses the system word list as a first-pass oracle — its hits still need judgment, and it misses proper-noun garble):

   ```bash
   python3 - <<'EOF'
   import re, glob
   eng = {w.strip().lower() for w in open('/usr/share/dict/words')}
   subs = [('n','ri'),('h','li'),('rn','m'),('m','rn'),('ii','u'),('u','ii'),('ni','m'),('cl','d')]
   for path in sorted(glob.glob('dictionaries/*.txt')):
       for line in open(path):
           w = line.strip()
           if not w or w.startswith('#') or w.lower() in eng: continue
           for a,b in subs:
               for mo in re.finditer(a, w.lower()):
                   v = w.lower()[:mo.start()] + b + w.lower()[mo.end():]
                   if len(v) > 4 and v in eng:
                       print(f"{path}: {w} -> {v}"); break
   EOF
   ```

   Diacritic-drop signature (every hit is a strong candidate):

   ```bash
   grep -n "ii" dictionaries/*.txt | grep -v "^[^:]*:#"
   ```

   Cross-dictionary duplicates (not garble, but misfiled per fix-ocr's one-dictionary rule — report or consolidate):

   ```bash
   grep -hv "^#" dictionaries/*.txt | grep -v "^$" | sort | uniq -d
   ```

2. **Verify each candidate.** In order of cost:
   - **Corpus context first**: `grep -rn "\b<word>\b" jons/` and read the surrounding sentence. This usually settles it — garble reads as a broken English/German word in context; a legitimate term reads as a name or denomination.
   - **`cspell trace`** to learn why a word currently passes: `cspell --config cspell.config.yaml trace "<word>"` shows which dictionary carries it. (Run checks of raw words from a directory *without* the project config in scope, or cspell will auto-discover `cspell.config.yaml` and consult the very dictionaries you are auditing.)
   - **WebSearch** for anything corpus context doesn't settle, per the legitimacy tests above.

3. **Remove confirmed garble.** Delete the entry's line with `Edit` (quote the neighbouring lines to make `old_string` unique). If the corrected form is a legitimate specialist term the corpus uses and it isn't already in a dictionary (`grep -inx "<word>" dictionaries/*.txt`), add it alphabetically to the correct section.

4. **Report** in three groups, terse: (a) entries removed, each with its identified true form and the `jons/` files (with line numbers) where the now-unmasked garble occurs, so a follow-up fix-ocr run can repair them; (b) entries kept despite heuristic hits, with the verification that cleared them; (c) entries left in place as uncertain, for human review. Include cross-dictionary duplicates found in (b) or their consolidation in (a). A final `cspell --config cspell.config.yaml --no-progress "jons/*.md"` run is useful for compiling (a)'s locations — but do not edit those files.

## What NOT to do

- Don't remove an entry just because it looks strange — the dictionaries exist precisely because the corpus is full of strange-but-real words.
- Don't trust search-engine hit counts; check that hits come from edited text, not other OCR scans.
- Don't "normalize" legitimate romanization variants (`Maurya`/`Mauryan`, `Karshapana`/`Kārṣāpaṇa`, diacritic-less `Tubingen` in English prose) — variant spellings are not garble.
- Don't reorder or reformat dictionary sections beyond the specific removals and insertions.
- Don't edit any file under `jons/` — read them for context only. Resurfaced cspell flags belong in the report, not in this skill's diff.
- Don't batch unrelated removals into one `Edit` call — one entry per edit so the diff is auditable.
