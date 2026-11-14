# A diacritic read as a capital, a digit read as a letter

*A `fix-ocr` reference.* Read it when `detect_confused_glyphs.py scan` reports
a finding. The Hard constraints, Workflow and Verification steps that govern
every fix here are in [`../SKILL.md`](../SKILL.md) — which is also where an
*above* or a *below* in the text points, wherever this file does not hold what
it names.

```
python3 .claude/skills/fix-ocr/scripts/detect_confused_glyphs.py scan <STEM>
python3 .claude/skills/fix-ocr/scripts/detect_confused_glyphs.py rows <STEM> > rows.tsv
python3 .claude/skills/shared/survey.py show --screen glyphs      # the worklist
```

Six shapes with one cause: the OCR read a diacritic, a digit, a bracket or a
dash as something else, and landed somewhere no spellcheck can follow. This is
the `glyphs` row of `docs/screens.tsv`; it reads the Markdown alone, so it
costs milliseconds and needs no render. **13,976 findings across 199 files**,
and on ONS_162 — a file that had already been through a full fix-ocr pass —
61 of its 67 `CAPITAL` hits were real defects that every other screen had
walked past.

- **`CAPITAL`** — a capital letter inside a lowercase word. Nothing in
  English prose puts a capital after a lowercase letter, so the *shape* is the
  finding, and that is what makes it catch two unrelated defects at once. The
  detail says which is likelier. `diacritic?` is a macron the OCR read as a
  letter: in ONS_162 **every `ī` came through as `T` and every `ū` as `Q`** —
  `al-JalTl` for `al-Jalīl`, `MansQr` for `Mansūr`, `UdgTr` for `Udgīr`,
  `falQs` for `falūs`, `ghazJ` for `ghāzī`. `hyphen?` is a hyphen read away,
  leaving a whole word standing after the capital — `IndoAfghan`,
  `nonCeylonese`, `preAurangzeb`, `alMalik`. cspell flags some of the first
  kind and **none** of the second, because `alMalik` is not a word it has an
  opinion about and `IndoAfghan` tokenises into two it likes.

  The `T`-for-`ī` confusion is not one file's accident. ONS_168 carries 1,547
  findings of it (`AlT` 322 times, `TegTn` 314, `IbrahTm` 97), ONS_165 1,445,
  and the whole `ONS_16*`-`ONS_20*` run is affected. The per-1000-word rate is
  the verdict: the corpus median is 0.16, the 90th percentile 2.20, and a file
  above about 2 has a *systematic* diacritic confusion rather than a few spots.

  **A render settles which diacritic, and it is worth asking for.** The OCR
  normalises inconsistently: ONS_162 printed the same name as `MansQr` four
  times and `Mansür` sixteen, and the page turned out to print `ū` in all
  twenty. Fixing only the flagged four would have left the file with two
  spellings of one name — so when a render shows the mark, apply it to every
  occurrence in that article, not just the ones the screen flagged.

- **`DIGIT`** — the mirror of `NUMERIC`: a digit standing in for a **letter**,
  inside a word. `R6misch` is `Römisch`, `K6ln` is `Köln`, `t5wn` is `town`,
  `Fran9ois` is `François`, `su7erain` is `suzerain`, `Kolbj0rn` is
  `Kolbjørn`. **cspell never reports these as themselves** — it splits the
  token on the digit and reports the *fragment*, so `R6misch` surfaces as
  `misch` and `$engun` as `engun`: innocuous-looking strings that get written
  off among a scanned file's 1,600 unknowns. That is how ONS_168 shipped
  `R6misch` and `K6ln` through a full fix-ocr pass (#263). 139 findings across
  43 files.

  Three constraints keep it clean, each paid for by a measurement:

  - **the digit must be interior**, letters on both sides. A leading or
    trailing digit is overwhelmingly real here — `6DD` and `0X14` in a
    postcode, `B578` and `BH126` in a catalogue, `8g`, `2nd`. ONS_168's
    `4ydin` for `Aydın` is the price of that cut, and it is worth paying.
  - **two or more lowercase letters must follow it**, which is what separates
    a word from a catalogue label: `K6ln` and `t5wn` keep their tail, `B2a`,
    `A5a`, `BH126A` and `H2O` lose theirs.
  - **exactly one digit.** Allowing a run adds 24 hits across nine more files
    and every one is `WELD`'s job — `A19and`, `I984pp`, `PMC579var`.

  The detail offers candidate letters rather than one decode, because the
  readings cluster by digit in a way you would not guess from shape: this
  corpus's scans turn **cedillas and umlauts into digits** as readily as `o`
  into `0` — `9`→`ç` (`Fran9ois`, `carrega9ao`), `6`→`ö`/`ó` (`K6ln`,
  `Hist6rico`), `0`→`ø` (`J0rgen`, `m0nter`), `7`→`z`, `4`→`t`, `3`→`a`. Both
  `5` and `8` go to `o` often enough (`t5wn`, `t8wn`) that guessing a single
  letter would be wrong as often as right. The page settles it.

  **One file is nearly a quarter of the class and is not this screen's
  business:** ONS_Supplement_197's 31 hits are inside a Georgian-script
  bibliography pdfmd garbled wholesale, where every token is noise. Retire the
  block with `glyph-ok DIGIT` on the line rather than reading them one by one.

- **`NUMERIC`** — a token of digit-lookalike letters sitting where only a
  number belongs. **This is the answer to "the garble is a dictionary word".**
  `Ilaq 401/1010-1 Oil` is `1010-1011`; `Oil` is in every English dictionary
  and no spellcheck will ever flag it, in this file or any other. What flags
  it is not the word but the **slot**: stop asking *is this a word* and ask
  *is a number the only thing that can go here*. Two sub-rules:

  - a token mixing digits with letters that are **only** digit-lookalikes
    (`OoIlJiSsBZqg`) — `I0I0-I012`, `J971`, `199S`, `8S-89`, `40I`. High
    precision, no slot test needed. The lookalike set is deliberately tight:
    adding `T`, `D` or `A` turns every British postcode (`CT21 6DD`) and half
    the countermark table (`A12`, `2xAB`) into a finding.
  - a token of **nothing but** lookalike letters, which needs the slot —
    adjacent to a digit run, and not one of the ordinary English words that
    legitimately follow a number (`is`, `in`, `ii`, `gg`, `oz`). `Oil` lives
    here.

  Decoding the token to digits gives the candidate reading, and one shape
  corroborates itself: **a range whose right side is shorter than its left,
  with the candidate directly after it.** `1010-1` + `Oil`→`011` rebuilds
  `1010-1011` exactly, and the screen says `(range completes)` when it does.
  That is the strongest evidence available without opening the page — but it
  is still a candidate, and Hard constraints still want the render.

- **`RUN`** — an undivided digit run a lost range dash welded together:
  `AD 17191748` for `AD 1719-1748`, `monet 388404 gg.` for `388-404`,
  `(10151042 AD)` for `(1015-1042 AD)`, `struck in 163839` for `1638-39`. The
  screen reports the plausible splits (equal halves ascending, or a two-digit
  continuation) and suppresses lines carrying a telephone, fax, ISBN or price
  context, where long digit runs mean nothing of the kind. Every one of
  ONS_162's six was real. On the scans these are almost always a hyphen that
  fell at a **line break**, which is why the OCR lost it and why the render
  shows it plainly.

- **`WELD`** — a number and a word with the space gone: `726-727in Samarqand`,
  `(AH1068-1118`, `the 2cash denomination` (which is `2-cash`). Units and page
  counts are deliberately **not** in the word list: this corpus writes `33mm`,
  `182p.` and `3.5gms` unspaced as a matter of course. Expect a fair number of
  these to be the typist's own, not the OCR's — ONS_162's `727in`, `991AH` and
  `AH1068` are all printed solid on the page.

- **`PAREN`** — a bracket standing in for a letter: `Shaha)T` for `Shahajī`,
  `t)pe` for `type`, `b)een` for `been`, `San)ar` for `Sanjar`. A bracket the
  token or the line balances is somebody's real parenthesis and is skipped —
  `mint(s)`, and ONS_162's `Shan(TiVaRa)ma`, which is printed exactly so. The
  screen also reads the other direction: a line with an unclosed `(` and a
  token ending in `J`, `l`, `I` or `j` is a bracket read as a letter, which is
  how `(1920 - 1950J` turns back into `(1920 - 1950)`.

- **`VARIANT`** — one name spelled two ways in one file, differing in its
  diacritics. **Off by default; ask for it with `--only VARIANT`**, and it has
  its own `variants` row in `docs/screens.tsv`. This is the other half of the
  diacritic problem: `CAPITAL` catches a mark the OCR read as a *letter*
  (`MansQr`), and this catches one it read as a *different mark*, or dropped.
  ONS_162 carried `Nizamshahï` 26 times beside `Nizāmshāhī` twice, and
  `Burhanpür` beside `Burhānpūr`; once the dictionaries hold both forms,
  neither is a cspell unknown and nothing else in the toolchain sees it.
  4,355 groups across 138 files.

  It is a separate row from `glyphs` because the two mean different things.
  The six labels above reach zero on a finished file. This one does not — a
  corpus that spells one name two ways in half its files has a standing
  backlog, and folding it into the same exit status would mean no file ever
  screens clean again.

  **The pair says only that the file disagrees with itself, never which form
  is right**, so it reports each form at its first occurrence rather than
  every occurrence — put them on one crop sheet and compare them side by
  side. Two conventions in one issue can be genuine: ONS_164 prints macrons in
  a succession table typeset separately from the prose around it, and
  normalising that to match was the wrong fix.

  **The decisive test is two forms close enough to share a crop.** ONS_162's
  Deccan article was settled by one band: line 455 prints the macron form and
  the umlaut form of the same dynasty name three words apart, and the page
  sets both with identical glyphs — which is what proves the umlaut is a
  degraded macron rather than a second convention. Reach for a pair in one
  sentence before a pair on facing pages.

  **Converting the flagged form does not license sweeping its ASCII
  siblings.** The same article prints one `Quṭbshahi` with no macron a single
  line from `Quṭbshāhī`, so the bare spellings are not all degraded. Read
  them or leave them; they stay on the `variants` worklist either way.

**Retire a finding the scan shows is real**, with the same inline marker
`detect_marker_noise.py` uses, so the screen stops asking and the next pass
does not read the same spot twice:

```
reads *JaGa* or *JaGaDa.* <!-- glyph-ok JaGaDa,TiVaRa,SuGa,JaGa reason=the
Kadamba article transliterates Telugu-Kanarese legends with interior capitals
on purpose; confirmed on the scan beside the article's own gloss -->
```

`glyph-ok` settles every occurrence of the tokens it names on its own line,
and a label (`glyph-ok WELD`) settles the whole class there. Name the token,
not just the class, when only one word on the line is genuine.

**Describe the readings in a marker; do not quote them.** cspell reads inside
HTML comments, so a marker that lists the forms it rejected turns every one of
them into a fresh unknown — ONS_162's first attempt at the note above added
twenty-one, including `macroned` and `underdots` from the prose of the reason
string itself. Say "the page carries dots below certain consonants that this
file drops", not the words with the dots on them.
