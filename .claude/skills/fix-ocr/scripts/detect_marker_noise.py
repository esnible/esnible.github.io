#!/usr/bin/env python3
"""Find the caret-class noise glyphs no other screen can see.

`detect_quote_pairs.py` owns this corpus's OCR'd superscripts -- the footnote
markers and ordinals pdfmd reads as a run of quote marks (`14'''`, `425''`).
But it anchors every finding on a quote character: `^` reaches it only as
`MARKER_TAIL`, the garble swallowed *after* a quote run. Where the scan's
superscript came through as a bare caret with no quote mark anywhere near
it, the pairing never sees it, and the file screens clean:

    In a forthcoming monograph^ I suggest that the reverse deities...
    Sikander 'Adil Shah surrendered to the Emperor.^ Thereafter he...

`transcribe-foreign-script`'s screen does know these glyphs -- its
`LATIN_NOISE_CHARS` is `^\\<>±«»¬°·•` -- but it is looking for a *run* of
them (four consecutive noise tokens at 15% of the line, beside an
`Obv.`/`Rev.` gloss), because its job is a legend pdfmd read as Latin. One
caret in sixty words of English prose is not that, and LATIN is kept out of
its exit status in any case. So nothing reports these.

Two shapes, both of them the glyph standing where a printed character was:

- **MARKER** -- a caret at the end of a word, before a capital. The scan
  prints a superscript footnote number; the corpus restores one as a Unicode
  superscript digit (`⁶`), read off the page, exactly as for the `®` and
  `''` markers. 447 of them in 41 files.
- **GLYPH** -- a caret or an angle bracket *between two letters*, which is a
  letter or a diacritic the OCR lost: `Öl^er` for Ölçer, `ak^e` for akçe,
  `be^hk` for beşlik, `'O^ene'` for Ozene, `Weh-Andew^Sabuhr`, and in
  ONS_163 a whole file's worth of `\\>` for `y` (`Arab-B\\>zantine`,
  `Uma\\>\\>ad`, `b\\> telephone`). 430 in 44 files.

Standalone angle brackets are **not** reported unless you ask for them with
`--angles`. Measured over the corpus, most are legitimate: comparison
operators in alloy tables (`Cu >70`, `As < 0.5`), `->` arrows in a flattened
family tree, and ONS_226's own stated convention, `In inscriptions \\< \\>
represents visible`. 1,291 of them across 75 files, too few of them defects
to put in a worklist.

    detect_marker_noise.py scan ONS_158
    detect_marker_noise.py scan jons/*.md --angles
    detect_marker_noise.py rows ONS_158          # crop_sheets.py rows

A hit sitting inside a run of garble is tagged WRECK and reported as a lead
rather than counted: it is a legend pdfmd read as Latin, and it belongs to
`transcribe-foreign-script`, not here. 485 of the 1,362 hits are those.

**This screen settles nothing.** Which digit a marker was, and which letter
a glyph ate, are both readable only off the scan -- see fix-ocr's Hard
constraints -- so it writes no edits and emits no `apply_edits.py` batch.

Exit 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MD_DIR = REPO_ROOT / "jons"

# `^` and `¬` only. The rest of `LATIN_NOISE_CHARS` is excluded on measured
# grounds: `«»` are balanced 393/384 across 56 files and are the French and
# German quotation marks the corpus's own passages use, `±` is a weight
# tolerance, `°` a degree or a footnote marker the `®` pass already owns,
# and `·`/`•` are bullets.
MARKER_CHARS = r"\^¬"
# ... plus the angle brackets for the between-letters shape, where a `>` is
# never a comparison: `Arab-B\>zantine`. kramdown's `\>` escape counts.
GLYPH_CHARS = MARKER_CHARS + r"<>"
# A marker is glued to what it annotates and followed by the next sentence,
# a quotation, or a parenthesis -- the same evidence `detect_quote_pairs`
# reads for its `''` runs, minus the quote character.
MARKER_RE = re.compile(rf"[A-Za-z0-9)\]'\"](\\?[{MARKER_CHARS}])"
                       rf"(?=\s+[\"'(*A-Z“])")
GLYPH_RE = re.compile(rf"[A-Za-z](\\?[{GLYPH_CHARS}])(?=[A-Za-z])")
ANGLE_RE = re.compile(r"\\?[<>]")
# Inline HTML and kramdown autolinks: `<br>` would otherwise read as a GLYPH
# every time a `<br>` separates two words (`legend.<br>Central`).
MARKUP_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>"
                       r"|<https?://[^>\s]*>"
                       r"|<[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+>")
# A `>` opening a line is a blockquote, not garble.
BLOCKQUOTE_RE = re.compile(r"^\s*>+")
# A finding whose neighbourhood carries this many other wreck characters is
# inside a legend pdfmd read as Latin. The character set and the threshold
# are `detect_quote_pairs.wrecked()`'s, so the two screens agree on what a
# wreck is. The window is wider than that function's span, because this
# screen matches one glyph where the pairing matches a whole quoted run: at
# 40 characters 134 more hits route to `transcribe-foreign-script` than at
# 20, and all ten of the hand-checked diacritic findings (`Ol^er`, `ak^e`,
# `B\>zantine`, `Andew^Sabuhr`, ...) still read as GLYPH. At 60 two of them
# stop.
WRECK_CHARS = "^\\•}{~<>"
WRECK_MIN = 3
WRECK_WINDOW = 40


def resolve(arg):
    p = pathlib.Path(arg)
    return p if p.suffix == ".md" else MD_DIR / f"{arg}.md"


def blank(text, pattern, flags=0):
    """Blank every match, keeping the file's offsets (and line numbers)."""
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                  text, flags=flags)


def readable(path):
    """The file with comments, fenced code and inline markup blanked out.

    The OCR skills quote bad readings inside `<!-- ... -->` on purpose --
    `<!-- script-ok ... (OCR had €°3) -->` -- so a screen that reads them
    reports the evidence as the defect.
    """
    text = path.read_text(encoding="utf-8")
    text = blank(text, r"<!--.*?-->", re.S)
    text = blank(text, r"(?ms)^```.*?^```")
    text = blank(text, MARKUP_RE.pattern)
    return blank(text, r"(?m)" + BLOCKQUOTE_RE.pattern)


def wrecked(text, start, end):
    """True when the glyph sits in a run of garble, not in English prose."""
    window = text[max(0, start - WRECK_WINDOW):end + WRECK_WINDOW]
    others = sum(window.count(c) for c in WRECK_CHARS) - (end - start)
    return others >= WRECK_MIN


def findings(text, angles=False):
    """[(offset, tag, glyph)] sorted by offset; WRECK ones tagged, not dropped."""
    out = {}
    for tag, pattern in (("MARKER", MARKER_RE), ("GLYPH", GLYPH_RE)):
        for m in pattern.finditer(text):
            start, end = m.span(1)
            out[start] = (start,
                          "WRECK" if wrecked(text, start, end) else tag,
                          m.group(1))
    if angles:
        for m in ANGLE_RE.finditer(text):
            out.setdefault(m.start(), (m.start(), "ANGLE", m.group(0)))
    return [out[k] for k in sorted(out)]


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def anchor_at(text, offset, glyph):
    """The words leading up to the glyph, for `crop_sheets.py` to place."""
    return " ".join(text[max(0, offset - 160):offset + len(glyph)].split())


def reported(found):
    """The findings that count: a WRECK or an ANGLE is a lead, not a verdict."""
    return [f for f in found if f[1] in ("MARKER", "GLYPH")]


def cmd_scan(path, angles=False, quiet_clean=False):
    text = readable(path)
    found = findings(text, angles)
    counts = {t: sum(1 for f in found if f[1] == t)
              for t in ("MARKER", "GLYPH", "WRECK", "ANGLE")}
    if not found:
        if not quiet_clean:
            print(f"{path.stem}: no marker or glyph noise")
        return 0
    leads = ", ".join(f"{counts[t]} {t.lower()} lead(s)"
                      for t in ("WRECK", "ANGLE") if counts[t])
    print(f"{path.stem}: {counts['MARKER']} marker(s), {counts['GLYPH']} glyph(s)"
          + (f" | {leads}" if leads else ""))
    for off, tag, glyph in found:
        print(f"  {tag:7} md line {line_of(text, off)}: "
              f"{anchor_at(text, off, glyph)[-58:]!r}")
    return 1 if reported(found) else 0


def cmd_rows(path, angles=False):
    """`file<TAB>label<TAB>anchor`, the form `shared/crop_sheets.py` takes.

    Leads are left out: a WRECK goes to `transcribe-foreign-script`, which
    renders the whole legend rather than one glyph, and an ANGLE is as often
    a comparison operator as a defect.
    """
    text = readable(path)
    rows = [f"{path.stem}\t{tag} line {line_of(text, off)}"
            f"\t{anchor_at(text, off, glyph)}"
            for off, tag, glyph in reported(findings(text, angles))]
    print("\n".join(rows))
    return 1 if rows else 0


def main(argv):
    flags = {a for a in argv[1:] if a.startswith("-")}
    args = [a for a in argv[1:] if not a.startswith("-")]
    if len(args) < 2 or args[0] not in ("scan", "rows") or flags - {"--angles"}:
        print(__doc__)
        return 2
    angles = "--angles" in flags
    rc = 0
    for arg in args[1:]:
        path = resolve(arg)
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            rc = max(rc, 2)
            continue
        if args[0] == "rows":
            rc = max(rc, cmd_rows(path, angles))
        else:
            rc = max(rc, cmd_scan(path, angles, quiet_clean=len(args) > 2))
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:          # piped into `head`, which is expected
        sys.exit(1)
