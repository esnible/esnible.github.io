#!/usr/bin/env python3
"""Find the glyph confusions that land on a word, and so hide from cspell.

Five shapes, one cause: `pdfmd` read a diacritic, a digit, a bracket or a
dash as something else, and landed on a token the spellchecker has no
objection to -- or on a non-word whose *shape* says more than its letters do.

- CAPITAL  a capital letter inside a lowercase word. Nothing in English prose
           puts a capital after a lowercase letter, so the shape alone is the
           finding. Two things make it, and the detail says which is likelier:
           a misread diacritic (`diacritic?` -- in ONS_162 the OCR read every
           macron-i as `T` and every macron-u as `Q`, giving `al-JalTl` for
           `al-Jalīl` and `MansQr` for `Mansūr`), or a hyphen read away
           (`hyphen?` -- `IndoAfghan` for `Indo-Afghan`). cspell flags some of
           the first kind and none of the second.
- NUMERIC  a token of digit-lookalike letters sitting where only a number
           belongs. `Ilaq 401/1010-1 Oil` is `1010-1011`, and `Oil` is in
           every English dictionary, so no spellcheck will ever flag it. What
           flags it is the slot, not the word.
- RUN      an undivided run of digits that a lost range dash welded together:
           `AD 17191748` for `AD 1719-1748`, `monet 388404 gg.` for `388-404`.
- WELD     a number and a word with the space gone: `726-727in Samarqand`,
           `(AH1068-1118`, `the 2cash denomination` (which is `2-cash`).
- PAREN    a bracket standing in for a letter: `Shaha)T` for `Shāhajī`,
           `t)pe` for `type`, `b)een` for `been`; or a token whose bracket
           nothing on the line closes, `(1920 - 1950J` for `(1920 - 1950)`.

Every verdict is a candidate, not evidence. Hard constraints still apply: a
case fix, a punctuation fix and a digit fix each need the page. `rows` emits
`crop_sheets.py` rows so a file's worth can be settled on two or three sheets
instead of a render apiece.

A finding the scan has shown to be really printed is retired inline, with the
same marker `detect_marker_noise.py` uses -- `<!-- glyph-ok JaGaDa reason=the
article transliterates Kannada with interior capitals on purpose -->`. The
marker settles every occurrence of the tokens it names on its own line.

    detect_confused_glyphs.py scan ONS_162
    detect_confused_glyphs.py scan jons/*.md --only CAPITAL --quiet
    detect_confused_glyphs.py rows ONS_162 > rows.tsv
"""

import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

LABELS = ("CAPITAL", "NUMERIC", "RUN", "WELD", "PAREN")

# Letters this corpus's OCR swaps with digits. Kept deliberately tight: `T`,
# `D` and `A` are each a plausible digit shape in the abstract, but including
# them turns every British postcode (`CT21 6DD`, `BA6 8SA`) and half the
# countermark table (`A12`, `2xAB`) into a finding.
LOOKALIKE = "OoIlJiSsBZqg"
DIGIT_OF = {
    "O": "0", "o": "0", "I": "1", "l": "1", "J": "1", "i": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2", "q": "9", "g": "9",
}

# All-lookalike tokens that are ordinary English next to a number, or genuine
# notation. These are what the slot test alone cannot clear.
NUMERIC_STOP = {
    "is", "in", "it", "if", "so", "sin", "sis", "ibis", "bis", "oz", "lb",
    "lbs", "gs", "ibid", "op", "loc", "nos", "no", "ii", "iii", "ll", "ss",
    "gg", "i", "l", "s", "b", "o", "g", "j", "z", "obv", "ob",
}

# Addresses, telephone numbers and ISBNs are full of digit runs that mean
# nothing of the kind.
RUN_CONTEXT = re.compile(
    r"tel\b|tel:|fax|phone|e-?mail|ISBN|ISSN|P\.?\s?O\.?\s+Box|\+\+|"
    r"price|\$|£|US\$|NLG|DM\b|account|VAT|postcode",
    re.I,
)

# camelCase that is somebody's real orthography rather than a lost hyphen.
CAPITAL_STOP = re.compile(
    r"^(?:Mc|Mac|O')[A-Z]|^[ei][A-Z][a-z]|GmbH|PhD|MPhil|LLD|"
    r"^[A-Za-z]*(?:Bay|Mail|Bid|Shop|Card|Pay|Net|Web|Tube)$"
)

# Era and reference abbreviations that weld onto a number. Units and the
# page-count `p` are deliberately absent: this corpus writes `33mm`, `182p.`
# and `3.5gms` unspaced as a matter of course, so they are notation rather
# than a lost space, and including them cost six false findings per file.
WELD_WORDS = re.compile(
    r"^(?:AH|AD|BC|CE|BCE|RY|Ry|Nr|No|fig|Fig|pl|Pl|vol|Vol|in|of|and|cash)$"
)


def _strip_comments(line):
    """Drop HTML comments: the OCR skills quote bad readings in their own
    markers on purpose, and a screen that read them would report its own
    evidence as the defect."""
    return re.sub(r"<!--.*?-->", "", line)


def _glyph_ok(raw):
    """Tokens and labels this line's own inline marker has already settled."""
    settled = set()
    for m in re.finditer(r"glyph-ok\s+([^\s][^\n]*?)(?=\s+reason=|\s*-->|$)", raw):
        for part in re.split(r"[,\s]+", m.group(1)):
            if part:
                settled.add(part.strip())
    return settled


def _plausible_split(run):
    """Splits of a welded digit run into two numbers that could be a range."""
    out = []
    for cut in range(2, len(run) - 1):
        left, right = run[:cut], run[cut:]
        if left[0] == "0" or right[0] == "0":
            continue
        if len(left) == len(right) and int(right) > int(left):
            out.append(f"{left}-{right}")            # 1719-1748
        elif len(right) == 2 and len(left) >= 3:
            out.append(f"{left}-{right}")            # 1638-39
        elif len(right) == len(left) + 1 and int(right) > int(left):
            out.append(f"{left}-{right}")            # 991-1411
    return out


def _capital_kind(tok):
    """Which confusion a mid-word capital is likelier to be."""
    inner = re.findall(r"(?<=[A-Za-z'])[A-Z]", tok)
    if len(inner) > 1:
        # `JaGaDa`, `TiVaRa`: alternating caps are usually a transliteration
        # convention the article states. `TTmQr` lands here too, so this is a
        # look-at-it verdict rather than a skip.
        return "convention?"
    m = re.search(r"[a-z]([A-Z][a-z]*)", tok)
    tail = m.group(1) if m else ""
    # A hyphen read away leaves a whole word standing after the capital; a
    # misread diacritic leaves a letter or two.
    return "hyphen?" if len(tail) >= 4 else "diacritic?"


def scan_text(text):
    """Yield (label, lineno, token, detail, context) for one file's text."""
    for lineno, raw in enumerate(text.split("\n"), 1):
        line = _strip_comments(raw)
        if not line.strip():
            continue
        settled = _glyph_ok(raw)

        def emit(label, m, detail):
            tok = m.group(0)
            if tok in settled or label in settled:
                return None
            return (label, lineno, tok, detail, _ctx(line, m))

        # --- CAPITAL: a capital letter after a lowercase one -------------
        # The trailing run is `*`, not `+`: `AlT` and `yT` put the capital
        # last, and they are this file's commonest finding by a wide margin.
        for m in re.finditer(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z']*\b", line):
            tok = m.group(0)
            if CAPITAL_STOP.search(tok) or tok in settled:
                continue
            got = emit("CAPITAL", m, _capital_kind(tok))
            if got:
                yield got

        # --- NUMERIC: letters where only digits belong -------------------
        for m in re.finditer(r"(?<![\w'\\])[0-9A-Za-z]{2,6}(?![\w'])", line):
            tok = m.group(0)
            letters = [c for c in tok if c.isalpha()]
            if not letters or any(c not in LOOKALIKE for c in letters):
                continue
            if re.fullmatch(r"\d+s", tok):
                continue                     # a decade: `1980s`, `630s`
            if re.fullmatch(r"[A-Z]\d{1,2}[a-z]?", tok):
                continue                     # a catalogue label: `B2`, `A5a`
            decoded = "".join(DIGIT_OF.get(c, c) for c in tok)
            if any(c.isdigit() for c in tok):
                # mixed digits and lookalikes: high precision, no slot test
                got = emit("NUMERIC", m, f"-> {decoded}")
                if got:
                    yield got
                continue
            if tok in NUMERIC_STOP or tok.lower() in NUMERIC_STOP:
                continue
            before, after = line[max(0, m.start() - 8):m.start()], line[m.end():m.end() + 8]
            if not (re.search(r"\d[\s\-/.(]*$", before) or re.match(r"[\s\-/.)]*\d", after)):
                continue                     # not in a numeric slot
            detail = f"-> {decoded}"
            # A range whose right side is shorter than its left, with the
            # candidate directly after it, reconstructs exactly: the
            # `1010-1 Oil` shape, and the strongest evidence available
            # without opening the page.
            rng = re.search(r"(\d+)-(\d+)\s*$", before)
            if rng and len(rng.group(2)) < len(rng.group(1)):
                joined = rng.group(2) + decoded
                if len(joined) == len(rng.group(1)):
                    detail = f"-> {rng.group(1)}-{joined} (range completes)"
            got = emit("NUMERIC", m, detail)
            if got:
                yield got

        # --- RUN: a range dash the OCR dropped ---------------------------
        if not RUN_CONTEXT.search(line):
            for m in re.finditer(r"(?<![\d.\-/])\d{6,8}(?![\d\-/])", line):
                splits = _plausible_split(m.group(0))
                if splits:
                    got = emit("RUN", m, " | ".join(splits[:3]))
                    if got:
                        yield got

        # --- WELD: a number and a word with the space gone ---------------
        for m in re.finditer(r"\b(?:([A-Za-z]{1,4})(\d{2,4})|(\d{1,4})([A-Za-z]{1,4}))\b", line):
            pre, post = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
            if not WELD_WORDS.match(pre):
                continue
            if re.fullmatch(r"\d+(?:st|nd|rd|th)", m.group(0)):
                continue
            got = emit("WELD", m, f"-> {pre} {post}" if m.group(1) else f"-> {post} {pre}")
            if got:
                yield got

        # --- PAREN: a bracket standing in for a letter -------------------
        for m in re.finditer(r"\b[A-Za-z]+[()][A-Za-z]+\b", line):
            tok = m.group(0)
            if tok.count("(") == tok.count(")"):
                continue                     # a real parenthesis: `mint(s)`
            span = line[max(0, m.start() - 30):m.end() + 30]
            if span.count("(") == span.count(")"):
                continue                     # the line closes it: `Shan(TiVaRa)ma`
            got = emit("PAREN", m, "bracket for a letter?")
            if got:
                yield got

        # A token that closes nothing and a line that opens something: the
        # bracket came through as a letter. `(1920 - 1950J` is `(1920 - 1950)`.
        if line.count("(") > line.count(")"):
            for m in re.finditer(r"\b\d{2,4}[A-Za-z]\b", line):
                # only the shapes that actually resemble a bracket: `S` for a
                # digit is a NUMERIC finding, not this one
                if m.group(0)[-1] in "JjlI":
                    got = emit("PAREN", m, f"-> {m.group(0)[:-1]})  (unclosed `(` on line)")
                    if got:
                        yield got


def _ctx(line, m):
    s = line[max(0, m.start() - 42):m.end() + 42]
    return re.sub(r"\s+", " ", s).strip()


def _resolve(arg):
    if os.path.sep in arg or arg.endswith(".md"):
        return arg
    return os.path.join(REPO, "jons", arg + ".md")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scan", "rows"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--only", action="append", default=None, choices=LABELS,
                    help="report only these labels")
    ap.add_argument("--skip", action="append", default=[], choices=LABELS,
                    help="suppress these labels")
    ap.add_argument("--quiet", action="store_true", help="per-file counts only")
    args = ap.parse_args()

    paths = []
    for a in args.files:
        paths.extend(sorted(glob.glob(a)) if any(c in a for c in "*?[") else [_resolve(a)])

    total, found_any = {}, 0
    for path in paths:
        try:
            text = open(path, encoding="utf-8").read()
        except OSError as e:
            print(f"{path}: {e}", file=sys.stderr)
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        found = [f for f in scan_text(text)
                 if (args.only is None or f[0] in args.only) and f[0] not in args.skip]
        words = len(re.findall(r"\b\w+\b", text)) or 1
        counts = {}
        for label, lineno, tok, detail, ctx in found:
            counts[label] = counts.get(label, 0) + 1
            total[label] = total.get(label, 0) + 1
            if args.cmd == "rows":
                print(f"{stem}\tline {lineno} {tok}\t{ctx}")
            elif not args.quiet:
                print(f"{stem}:{lineno}  {label:7s} {tok:22s} {detail:34s} ...{ctx}...")
        found_any += len(found)
        if args.cmd == "scan" and (len(paths) > 1 or args.quiet):
            summary = " ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "clean"
            print(f"{stem}: {summary}   ({1000.0 * len(found) / words:.2f} per 1000 words)")

    if args.cmd == "scan" and len(paths) > 1:
        print("\nTOTAL " + " ".join(f"{k} {v}" for k, v in sorted(total.items())))
    return 1 if found_any else 0


if __name__ == "__main__":
    sys.exit(main())
