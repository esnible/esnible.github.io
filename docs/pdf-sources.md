# What the source PDFs actually are

Most of this repo's tooling assumes a scanned page: a raster image of 1970s
typescript with an OCR text layer laid over it, where a defect in the
Markdown is an OCR misread and the scan is the authority. For about a quarter
of the corpus that assumption is wrong. Those files are born-digital, their
defects are extraction damage rather than misreads, and the screens that key
on garble mean something different there.

Measured 2026-11-16 over all 278 PDFs in `$ONS_ARCHIVE_DIR`, page by page. A
page counts as scanned when a full-page raster image carries the page's text
on top of it.

## The boundary

- **Born-digital: `ONS_186` – `ONS_252`**, plus `ONS_Supplement_193` and
  `ONS_Supplement_205`. Zero scanned pages in any of them.
- **Three exceptions inside that range.** `ONS_197` is 48 image pages out of
  48 with **no text layer at all**; `ONS_201` and `ONS_202` are full scans
  with an OCR layer, like the older issues.
- **Everything `ONS_185` and below is scanned**, as are all `IS_*`, all
  `OP_*`, and the bare-numbered files `12`–`20` (image-only, no text layer).
  `ONS_177` also has no text layer.
- **Plate pages are not scanned pages.** `ONS_204`, `ONS_206`, `ONS_207` and
  `ONS_209` are born-digital text with many image-only plates — 20 of
  `ONS_204`'s 32 pages. The file is born-digital; the plates are artwork.

## What it changes

On `ONS_186` and up, don't reach for a by-eye render first. The PDF's own
text layer is authoritative there, and it is usually enough to settle a
finding on its own — which is a different workflow from the scanned half,
where the text layer is a second, generally worse OCR pass (see
`transcribe-foreign-script`'s Known limits).

A `glyphs` or `markers` finding on a born-digital file is therefore a
question about extraction, not about reading. `ONS_191`'s `CAPITAL` hits are
the two shapes that question takes: lost line-break hyphens (`alIkhshid` is
`al-Ikhshid`) and real Georgian transliteration in the
`qarTuli`/`javaxiSvili` convention, where the capital is the author's. Both
are `glyph-ok` cases, not fixes.

## The Spink adverts decode rather than re-OCR

The full-page Spink adverts — `ONS_237` p27, `ONS_239` p27, `ONS_251` p35 and
others like them — embed fonts with no usable `ToUnicode` map. Their text
extracts as a **+31 character shift**: `$0/4*(/` is `CONSIGN`. That is
decodable, not garble, and re-OCRing the page to recover it is wasted work.
