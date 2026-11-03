#!/usr/bin/env python3
"""Fold Arabic Presentation Forms back to ordinary Arabic.

The two Presentation Forms blocks -- `U+FB50-FDFF` and `U+FE70-FEFF` -- are
legacy compatibility codepoints that encode a letter *together with its
contextual shape*. Correct Arabic text never needs them: which form a letter
takes is the renderer's job, decided from its neighbours. Stored text that
uses them is readable only by accident, and is mojibake to every tool that
expects Arabic:

    as stored          folded
    ازﻜﺎﺠﻮار            ازكاجوار
    اﻟﻟﻪ               الله
    وﺻﻴﻒ               وصيف

**They are not an OCR artifact.** Every affected file is ONS_186 or later and
none is earlier; `classify_source.py` calls the worst of them BORN-DIGITAL at
3,500-6,200 characters a page. They come out of the publisher's own
typesetting software, which emits presentation forms into the PDF text layer,
and `pdfmd` copies them faithfully. None of the ~190 scanned-era files has a
single one. Since every new issue is born-digital, new issues are precisely
the ones that will keep producing them -- which is why this is a screen and
not a one-off sweep.

## Why not NFKC

`unicodedata.normalize("NFKC", text)` over a whole file would fold these
correctly and also destroy two things this corpus depends on:

- `½` becomes `1⁄2`, and `fix-ocr`'s "Currency symbols that are not currency"
  section exists to *restore* `½` from a misread `¥`;
- superscripts `¹²³` become `123`, and the corpus holds 1,788 Unicode
  superscripts that `fix-ocr` says to leave alone (`⁶` alone 398 times).

So the fold is restricted twice over: a character is touched only if it is in
one of the two blocks **and** NFKC actually changes it. The second test is
not redundant. `﴿` and `﴾` (U+FD3E/FD3F, ornate parenthesis) sit inside the
first block but are real punctuation with no decomposition, and NFKC leaves
them as they are; the block test alone would report them as findings.

## Ligatures expand, and that is correct

Six of the 126 forms this corpus uses decompose to more than one character:

    ﻻ  -> لا     (351x)   lam with alef
    ﷲ  -> الله   (148x)   the Allah ligature, to the word itself
    ﻷ  -> لأ      (10x)
    ﻼ  -> لا       (9x)
    ﴏ  -> صر       (1x)
    ﶊ  -> محم      (1x)

All six are right. A file could in principle hold `U+FDFA`, which decomposes
to the seven words of the *salla llahu alayhi wa-sallam* formula; that
expansion is also correct, merely verbose, and `scan` prints any mapping
longer than four characters so it is never a surprise.

## HTML comments are left alone

`<!-- script-ok ... -->`, `<!-- OCR: ... -->` and the rest quote a bad
reading on purpose: that is their evidence. Rewriting one would destroy the
record, the same way `fix-ocr` warns against rewriting `€` inside a marker.
No comment in the corpus currently holds a foldable character, so this
carve-out protects nothing today -- it is here because the operation is a
bulk rewrite and the markers are the audit trail.

Usage:
    detect_presentation_forms.py scan  ONS_224 [ONS_225 ...]
    detect_presentation_forms.py scan  --all
    detect_presentation_forms.py apply ONS_224 [ONS_225 ...]

`scan` exits non-zero when there is something to fold.
"""
import argparse
import pathlib
import re
import sys
import unicodedata

MD_DIR = pathlib.Path(__file__).resolve().parents[4] / "jons"
BLOCKS = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
LONG_MAPPING = 4          # a decomposition longer than this is printed in full


# Arabic proper, Arabic Supplement, Arabic Extended-A, and the two
# Presentation Forms blocks. Used only by the apply-time invariant.
ARABIC = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
          (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def non_arabic(text):
    """`text` with every Arabic character removed."""
    return "".join(c for c in text
                   if not any(lo <= ord(c) <= hi for lo, hi in ARABIC))


def foldable(ch):
    """True for a presentation form that NFKC actually rewrites."""
    if not any(lo <= ord(ch) <= hi for lo, hi in BLOCKS):
        return False
    return unicodedata.normalize("NFKC", ch) != ch


def spans_to_keep(text):
    """(start, end) of every HTML comment, which is never rewritten."""
    return [(m.start(), m.end()) for m in COMMENT_RE.finditer(text)]


def fold(text):
    """Return (folded text, characters changed, mappings used).

    Every character outside the two blocks is copied through untouched, so
    nothing but a presentation form can move.
    """
    keep = spans_to_keep(text)
    out, changed, used = [], 0, {}
    i = 0
    for start, end in keep + [(len(text), len(text))]:
        while i < start:
            ch = text[i]
            if foldable(ch):
                sub = unicodedata.normalize("NFKC", ch)
                out.append(sub)
                changed += 1
                used[ch] = sub
            else:
                out.append(ch)
            i += 1
        out.append(text[start:end])          # the comment, verbatim
        i = end
    return "".join(out), changed, used


def report(stem, text, verbose):
    body_changed = fold(text)[1]
    in_comments = sum(1 for s, e in spans_to_keep(text)
                      for ch in text[s:e] if foldable(ch))
    tokens = [w for w in re.findall(r"\S+", COMMENT_RE.sub(" ", text))
              if any(foldable(c) for c in w)]
    if not body_changed and not in_comments:
        if verbose:
            print(f"{stem}: clean")
        return 0
    print(f"{stem}: {body_changed} character(s) to fold in {len(tokens)} token(s)"
          + (f"; {in_comments} left alone inside comments" if in_comments else ""))
    folded, _, used = fold(text)
    long = {c: s for c, s in used.items() if len(s) > LONG_MAPPING}
    for ch, sub in sorted(long.items()):
        print(f"  U+{ord(ch):04X} {ch} expands to {len(sub)} characters: {sub}")
    if verbose:
        seen = set()
        for w in tokens:
            f = fold(w)[0]
            if f != w and f not in seen:
                seen.add(f)
                print(f"  {w}  ->  {f}")
                if len(seen) >= 12:
                    break
    return body_changed


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("scan", "apply"))
    ap.add_argument("stems", nargs="*", metavar="ONS_224")
    ap.add_argument("--all", action="store_true", help="every .md file in jons/")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="show sample tokens, and name the clean files")
    args = ap.parse_args()

    stems = list(args.stems)
    if args.all:
        stems += sorted(p.stem for p in MD_DIR.glob("*.md"))
    if not stems:
        sys.exit("no files: name a stem or pass --all")

    total = 0
    for stem in stems:
        md = MD_DIR / f"{stem}.md"
        if not md.exists():
            print(f"{stem}: no Markdown at {md}", file=sys.stderr)
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            print(f"{stem}: not UTF-8 ({exc})", file=sys.stderr)
            continue
        n = report(stem, text, args.verbose)
        total += n
        if args.cmd == "apply" and n:
            folded, changed, _ = fold(text)
            # Nothing outside Arabic may have moved. Comparing the texts
            # with the *foldable* characters removed does not test that: a
            # folded character has become ordinary Arabic, which is not
            # foldable, so it survives the strip on one side and not the
            # other. Strip Arabic entirely from both instead -- what is left
            # is the Latin, the markup and the punctuation, and it must be
            # identical.
            assert non_arabic(text) == non_arabic(folded), \
                f"{stem}: text outside Arabic moved"
            # And the fold must be idempotent: nothing foldable may remain.
            assert fold(folded)[1] == 0, f"{stem}: fold left work behind"
            md.write_text(folded, encoding="utf-8")
            print(f"  wrote {md} ({changed} character(s) folded)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
