# Symbols the typewriter never had

*A `fix-ocr` reference.* Read it when `grep -nE '¥|€|®'` over the file reports
a hit. The Hard constraints, Workflow and Verification steps that govern every
fix here are in [`../SKILL.md`](../SKILL.md) — which is also where an *above*
or a *below* in the text points, wherever this file does not hold what it
names.

## Currency symbols that are not currency

A currency symbol in this corpus is far more often a misread glyph than a
price, because the symbols the OCR engine reaches for are shapes the
typewriter never had. Treat both of these as suspect on sight, then settle
each one by rendering the page — the Hard constraints apply here as
everywhere, so none of these is a from-context fix.

- **`¥` is suspect everywhere.** Of 36 in the corpus, 2 were real. It stands
  most often for **`½`**, the typewriter's half-fraction glyph: `¥%` →
  `½` (ONS_052, confirmed against the scan), `AR ¥ unit` and `¥% unit` →
  `½ unit` (ONS_078), `*¥2* abazi` → `½ abazi` (ONS_Supplement_197, where
  half-abazi is a real Georgian denomination). It also stands in for a
  letter: `Powys S¥22 5BX` → `SY22 5BX`, `Priissykkuria,¥Tünze` → `Frunze`.
  The rest sit inside already-garbled plate, Chinese or Arabic runs, where
  the `¥` is a symptom and the line belongs to another skill. It is genuine
  only as a book price in a recent issue's publications notice — `¥ 1800`
  (Bank of Japan, ONS_148), `CN¥ 368` (ONS_248).
- **`€` cannot predate the currency.** The symbol dates from 1996 and the
  euro itself from 1999, so it is certainly wrong in `IS_*`, `OP_*`,
  `ONS_0*` and `ONS_1[0-3]*`, and worth a look anywhere before `ONS_14*`.
  In ONS_124 it is a Greek lunate epsilon in a mint legend (`€MH CIC`), not
  money at all. In issues after 1999 a euro price is ordinary — check the
  issue date before touching one.


## A registered sign is a footnote digit

`®` is never the registered trademark sign in this corpus. 218 occurrences
across 47 files, and not one of them is genuine -- the recent issues, where a
product trademark could legitimately appear, carry it only inside mojibake
Arabic runs. What it stands for depends on where it sits:

- **A superscript footnote marker, after a word or a full stop** (~93, the
  common prose case): `an agreement®`, `...the Sichuan Rupee.®`, `points
  out®`. Restore one as `agreement<sup>6</sup>`, not `6`. (The corpus's older
  repairs wrote 1,788 of these as Unicode superscripts, `¹` alone 398 times;
  new work uses `<sup>`, and leaves the existing Unicode ones as they are.)
  **The digit is not fixed, so there is no blanket substitution.** ONS_109
  alone reads `®` as ⁶ three times and ⁸ once, two of them on facing pages:
  `Japanese⁶ private castings` but `0.75 tael string⁸`. Render each one. The
  same file's other markers are garbled in their own ways (`!` for ¹, `?` for
  ², `\>` for ⁵), so the footnote list on the page is a useful cross-check
  once the render gives you the digit.
- **Debris inside a wrecked foreign-script or figure run** (~70): `ÚD®Ïv`,
  `# DESIGN **®** **® ®**`. The `®` is a symptom of the wreck, not a defect of
  its own -- that line belongs to `transcribe-foreign-script` or to
  `detect-missing-figures`, and fixing the symbol alone achieves nothing.
- **A misread `@` in an e-mail address** (8): `e-mail album®sonic net`,
  `E-mail: ®home.com`.

**Never rewrite any of these symbols inside an HTML comment.** The OCR skills
record their own evidence there, and that includes quoting the bad reading:
`IS_021` carries `<!-- script-ok ... reason=... (OCR had €°3 and 6-3) -->`,
where the `€` is the point of the sentence. A blanket sweep over the file
destroys the note. The same goes for `<!-- OCR: ... -->` placeholders.
