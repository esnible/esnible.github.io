#!/usr/bin/env python3
"""Find the glyph confusions that land on a word, and so hide from cspell.

Six shapes, one cause: `pdfmd` read a diacritic, a digit, a bracket or a
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
- DIGIT    the mirror of NUMERIC: a digit standing in for a *letter*, inside
           a word. `R6misch` is `Römisch`, `t5wn` is `town`, `Fran9ois` is
           `François`, `su7erain` is `suzerain`. cspell never reports these as
           themselves -- it splits the token on the digit and reports the
           fragment, so `R6misch` surfaces as `misch` and `KJiunak`'s
           neighbour `$engun` as `engun`: innocuous-looking strings that get
           written off among a scanned file's 1,600 unknowns. Nothing else
           looked at the shape, which is why ONS_168 shipped `R6misch` and
           `K6ln` through a full fix-ocr pass (#263).
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
import collections
import glob
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

LABELS = ("CAPITAL", "DIGIT", "NUMERIC", "RUN", "WELD", "PAREN", "VARIANT")

# `VARIANT` is off by default, and the reason is the exit status. The other
# six can all reach zero on a file -- every finding is either fixed or
# carries a `glyph-ok` marker -- so a clean exit means something. VARIANT
# cannot: a corpus that spells one name two ways in 138 files has a standing
# backlog, not a defect list, and folding it into the same gate would mean no
# file ever screens clean again. Ask for it with `--only VARIANT`; it has its
# own `variants` row in `docs/screens.tsv`.
DEFAULT_LABELS = ("CAPITAL", "DIGIT", "NUMERIC", "RUN", "WELD", "PAREN")

# Letters this corpus's OCR swaps with digits. Kept deliberately tight: `T`,
# `D` and `A` are each a plausible digit shape in the abstract, but including
# them turns every British postcode (`CT21 6DD`, `BA6 8SA`) and half the
# countermark table (`A12`, `2xAB`) into a finding.
LOOKALIKE = "OoIlJiSsBZqg"
DIGIT_OF = {
    "O": "0", "o": "0", "I": "1", "l": "1", "J": "1", "i": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2", "q": "9", "g": "9",
}

# The other direction: a digit the OCR put where a letter belongs. Measured
# over the 264 files in `jons/`, the readings cluster hard by digit and they
# are *not* the shape-alikes you would guess -- this corpus's scans turn
# cedillas and umlauts into digits as readily as they turn `o` into `0`:
#
#   9 -> ç   carrega9ao, Fran9ois, negocia9ao        (Portuguese and French)
#   6 -> ö   K6ln, R6misch, Hist6rico                (German and Spanish)
#   0 -> o   m0nter, J0rgen, Kolbj0rn                (Danish and Norwegian ø)
#   7 -> z   su7erain, az7am, A7iz
#   5 -> s   Na5ir, Nu5rat        ... but t5wn is `town`
#   8 -> o   t8wn, r8my, x8no
#   4 -> t   Kwan4ung, with4he
#   3 -> a   Kh3qan, Shilah3ra
#   2 -> g   eni2matic
#
# So the detail offers candidates rather than one decode: 5 and 8 both go to
# `o` often enough that guessing a single letter would be wrong as often as
# right. The page settles it, as it does for every other label here.
LETTER_OF = {
    "0": "o|ø|O", "1": "l|i|I", "2": "z|g", "3": "a|e", "4": "t|A",
    "5": "s|o", "6": "ö|ó|b", "7": "z|t", "8": "o|B", "9": "ç|g",
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

        # --- DIGIT: a digit where only a letter belongs ------------------
        # Three constraints, each paid for by a measurement over `jons/`:
        #
        # - the digit must be *interior*, letters on both sides. A leading or
        #   trailing digit is overwhelmingly real here -- `6DD` and `0X14` in
        #   a postcode, `B578` and `BH126` in a catalogue, `8g`, `2nd`.
        #   ONS_168's `4ydin` (for `Aydın`) is the price of that cut, and it
        #   is worth paying: relaxing it floods the countermark tables.
        # - at least two *lowercase* letters must follow it. This is what
        #   separates a word from a catalogue label: `K6ln` and `t5wn` keep
        #   their tail, `B2a`, `A5a`, `BH126A` and `H2O` lose theirs.
        # - exactly one digit. Allowing a run adds 24 hits across 9 more
        #   files and they are all WELD's job, not this one -- `A19and`,
        #   `I984pp`, `PMC579var`, `Diam24mmWt`.
        #
        # What is left is 139 findings in 43 files with almost nothing false
        # in it; the shape is narrow enough that the digit itself is the
        # evidence.
        for m in re.finditer(r"\b[A-Za-z]+(?<![0-9])([0-9])(?![0-9])[a-z]{2,}[A-Za-z']*\b", line):
            got = emit("DIGIT", m, f"{m.group(1)} -> {LETTER_OF[m.group(1)]} ?")
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


def _skeleton(word):
    """The word with every diacritic stripped, lowercased."""
    d = unicodedata.normalize("NFD", word)
    return "".join(c for c in d if not unicodedata.combining(c)).lower()


def scan_variants(text):
    """One name spelled two ways in one file, differing in its diacritics.

    This is the screen for the other half of the diacritic problem. CAPITAL
    catches a mark the OCR read as a *letter* (`MansQr`); this catches a mark
    it read as a *different mark*, or dropped -- `Nizamshahï` 26 times beside
    `Nizāmshāhī` twice, `Burhanpür` beside `Burhānpūr`. Neither form is a
    cspell unknown once the dictionaries carry both, so nothing else sees it.

    **The pair says only that the file disagrees with itself, never which form
    is right.** Two conventions in one issue can be genuine: ONS_164 prints
    macrons in a succession table that was typeset separately and the typed
    prose around it does not, and "normalising" that to match was the wrong
    fix. So this reports the forms side by side for one render, which is also
    why it anchors a row at each form rather than at every occurrence.
    """
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    groups = collections.defaultdict(lambda: collections.defaultdict(list))
    for lineno, raw in enumerate(body.split("\n"), 1):
        for m in re.finditer(r"[^\W\d_][\w'’]{3,}", raw, re.UNICODE):
            w = m.group(0)
            groups[_skeleton(w)][w].append((lineno, m))

    for forms in groups.values():
        if len(forms) < 2:
            continue
        # a pure case difference is not this defect
        if len({f.lower() for f in forms}) < 2:
            continue
        # at least one form must actually carry a diacritic
        if not any(unicodedata.normalize("NFD", f) != f for f in forms):
            continue
        tally = ", ".join(f"{f} x{len(v)}" for f, v in
                          sorted(forms.items(), key=lambda kv: -len(kv[1])))
        raw_lines = text.split("\n")
        for form, occs in forms.items():
            lineno, m = occs[0]
            settled = _glyph_ok(raw_lines[lineno - 1]) if lineno <= len(raw_lines) else set()
            if form in settled or "VARIANT" in settled:
                continue
            yield ("VARIANT", lineno, form, tally,
                   _ctx(body.split("\n")[lineno - 1], m))


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
                    help="report only these labels (VARIANT is only ever reported "
                         "when asked for by name)")
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
        want = args.only or [l for l in DEFAULT_LABELS if l not in args.skip]
        gen = scan_text(text) if set(want) - {"VARIANT"} else iter(())
        found = [f for f in gen if f[0] in want and f[0] not in args.skip]
        if "VARIANT" in want:
            found += [f for f in scan_variants(text) if f[0] not in args.skip]
        found.sort(key=lambda f: (f[1], f[0]))
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
