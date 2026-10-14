#!/usr/bin/env python3
"""Find quotation marks `pdfmd` split into runs of two and three, and the
superscript ordinals and footnote markers it read as quote runs.

A typewritten double quote scans badly. On these pages pdfmd routinely reads
one printed `"` as two or three marks, so a book title comes out

    4.  '""Chopmarks" by F. M. Rose, Dallas 1987
           ^^^ the page prints `"Chopmarks"`

Eleven runs in ONS_111 alone were this, and the corpus holds 3,657 runs of
two or more marks across 127 files. **That census is not one defect**, which
is why a warning on every illogical quote combination is the wrong screen:
about a quarter of the runs are not quotes at all (see *Superscripts* below),
and plenty of the mixed ones are correct text -- in `("'Abd Allah ibn
Ibrahim")` the inner `'` is the ʿayn of the name.

## The pairing rule

Pair each opening mark with its closing mark and report the spans where the
two disagree. That is what makes `'""Chopmarks"` nonsense, and it is
decidable from the text alone -- a render is needed only to settle what the
page actually prints. To keep the output a worklist rather than a census:

  * **Scope is the paragraph.** Pairing across the whole file desynchronises:
    one unclosed ʿayn (`'Abd` occurs 578 times in opener position) throws off
    every pair after it, which turns 726 findings into 7,669. Inside a pipe
    table the scope is the cell, for the same reason.
  * **Apostrophes are not quotes.** An intra-word `'` (`Tabari's`, 22,975 of
    them) and a possessive after an `s` (`Mauryans'`, 3,762) are dropped.
    A trailing `'` after any other letter is kept, because it is usually a
    gloss closing (`'Gokul'`, `'pzwt'`): only 22% of the corpus's 17,418
    trailing apostrophes follow an `s`, and dropping them all left openers
    with no closer to pair against.
  * **A `'` at the inner edge of a run, before a transliterated name, is a
    ʿayn** (`("'Abd`, `"'Ali`) and is dropped from the run. The name list is
    built in below, derived from the corpus.
  * **A run right after a digit is a superscript**, not a quote. It has to
    leave the pairing or `the 13"'` mis-pairs with a real quote two clauses
    later; it is reported under its own verdict instead.
  * **Curly marks are normalised** before comparing, so a correct `“...”`
    pair balances (256 of them do).
  * **A nested quotation's two closers are correct text** (`the Name
    "Safi""`, `*yagbu* 'chief of a clan'"`) and are not reported, where the
    second mark demonstrably belongs to a quotation open at that point.
  * **A span over 300 characters is a desynchronised pairing**, not a
    defect, and is dropped: all 33 of them are an opener whose own closer
    the screen missed, running on to the next quotation.
  * **Single-vs-single disagreements are off by default.** `'A' ... "B"`
    nesting, ʿayn the name list misses and `'quoted phrase'` all live in that
    bucket, and turning it on adds 1,083 spans of much poorer precision.
    `--include-single` does that.

That leaves 664 spans across 99 files, against 24,188 pairs that balance --
a 3% defect rate; it read 726 before ONS_165's worklist was worked off.
A span whose surroundings are shot through with OCR
wreckage (`j ^ ' *\\J^* \\}• • •`) is reported as `WRECK` only under
`--include-wrecks`: the quote marks there are a symptom, and the line belongs
to `transcribe-foreign-script` or `restructure-flattened-md`.

## A `''` that closes nothing is often a question mark

Working ONS_165's worklist turned up a defect the pairing itself cannot see.
A printed `?` scans as `''` on these pages, so a rhetorical question ends up
looking like a stray quote run:

    Are we really meant to believe this''      ->  ... believe this?
    read the name ... as "Muhammad''",         ->  "Muhammad?",
    In AH 568 and 56(9 or 7'')                 ->  56(9 or 7?)

ONS_165 carried 15, one of them in a sentence that goes on to say *with
question-mark i.e. he was not sure*. The PDF's own text layer reads `''`
there too -- both OCR passes make the same mistake -- so only the page image
settles it, and `triage_percent.py`'s text-layer shortcut does not help.

The screen reports a `''` that **closes nothing** (the pairing consumed no
opener for it), sits right after a lowercase letter, and is followed by the
next sentence or the end of the line: 231 of them across 38 files. A `''`
that does close a quotation is a `QUOTES` span instead, and the two never
report the same run.

## Superscripts: a quarter of the runs are not quotes

993 runs sit immediately after a digit, and they are OCR'd superscript
ordinals and footnote markers:

    the 14'''  All-Russian Numismatic Conference   ->  14th
    30""  November                                 ->  30th
    the 33'"''  International Archaeometry Conf.   ->  33rd
    7'''  century Byzantine coins                  ->  7th

This is the `®` class of #209 in another costume, and it cuts both ways:

  * **A digit before the run does not prove an ordinal.** ONS_111 p5 prints
    `...perpetuate his sovereignty 828".` -- a plain closing quote after a
    year, verified on the render. `10 3/8" x 7 3/8''` is an inch mark, and
    `AH 40(7'' or 6'')` is a footnote marker on a date.
  * **What the marker stands for depends on where it sits.** `'''` is `th`
    after 14, `rd` after 33, and a footnote digit after a word.

So the script splits the class in two. A run is an **ordinal** when the word
after it says so -- a century word, a month, `c.`/`cent`, `year`, `regnal`,
`anniversary`, `edition`, `standard`, `International`, or a connector with a
century word just beyond it -- and the number is small enough to be one. 533
runs in 28 files qualify, and `ordinals` emits them as an `apply_edits.py`
batch:

    detect_quote_pairs.py ordinals ONS_162 > edits.txt
    python3 apply_edits.py jons/ONS_162.md edits.txt          # dry run
    python3 apply_edits.py jons/ONS_162.md edits.txt --write

The suffix comes from the number (14 -> th, 33 -> rd, 21 -> st, 11-13 -> th)
and the restoration is **plain `14th`**, which is how this corpus writes an
ordinal: 3,599 plain `Nth` forms against not one superscript `ᵗʰ`. Superscript
*digits* stay the convention for footnote markers (1,817 of those), so a
marker the screen reports as `check` is restored as `⁶`, read off the render
like any other -- never from a blanket substitution.

The emitted batch is a candidate list, not evidence. Confirm a sample of each
page against the render before `--write`, the same rule `punct_candidates.py`
follows.

Usage:
    detect_quote_pairs.py scan ONS_111
    detect_quote_pairs.py scan jons/*.md
    detect_quote_pairs.py scan --include-single --include-wrecks ONS_165
    detect_quote_pairs.py ordinals ONS_162          # apply_edits.py batch

Exit status is 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""

import re
import sys
from pathlib import Path

QUOTE_CHARS = "\"'‘’“”"
QRUN = re.compile(f"[{QUOTE_CHARS}]+")
WORDCH = re.compile(r"[A-Za-z0-9]")
ASCII_QUOTE = {"‘": "'", "’": "'", "“": '"', "”": '"'}

# Transliterated name elements that carry a word-initial ʿayn (or alif) in
# this corpus, so a `'` before one is part of the word and not a quote mark.
# Derived by counting every token that follows a `'` in opener position --
# after whitespace, `(`, or another quote mark -- and keeping the Arabic and
# Persian name elements. The English words in that same list (`'The` 508,
# `'All` 262, `'Coins` 74) are quoted phrases and must NOT be here, or a real
# `'"'The Gondopharid Countermark"'` stops being reported.
AYN_NAMES = (
    "Abbas", "Abbasid", "Abbasids", "Abd", "Abdallah", "Abdullah", "Abu",
    "Adil", "Adl", "Adud", "Ain", "AIT", "Al", "Ala", "Alam", "Alamat",
    "abbasidischen", "AIT", "Ain", "Alamgir", "Alf", "Ali", "Alim", "All",
    "AlT", "Am",
    "Amr", "Ayn", "Aziz", "Id", "Imad",
    "Iraq", "Isa", "Izz", "Ubaid", "Ubayd", "Umar", "Umayyad", "Umayyads",
    "Uthman",
)
AYN_RE = re.compile(r"(?:%s)\b" % "|".join(AYN_NAMES), re.IGNORECASE)

MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)
CENTURY_WORDS = ("century", "centuries", "cent", "cents")
# Nouns that make the number before them an ordinal. `part` is left out on
# purpose: `11/16"' part silver` reads as an ordinal fraction but the page may
# print `11/16 part`, so it stays a `check`.
ORDINAL_NOUNS = (
    "anniversary", "regnal", "year", "day", "edition", "standard",
    "international", "colloquium", "conference", "congress", "session",
)
CONNECTORS = ("and", "or", "to")
# Beyond this, a mismatched pair is a desynchronised pairing rather than a
# defect: the opener's real closer was missed, so the span runs on to the next
# quotation. Measured -- every one of the 33 spans over this length was a term
# gloss or an article title whose closer the screen had not recognised, while
# 88% of all findings are under 120 characters.
MAX_SPAN = 300
# Garble that travels with the marker and must be swallowed by the edit:
# `98''^ year`, `23'''^August`. `*` is excluded -- it closes an italic span
# (`*2"'^*`), and eating it would unbalance the emphasis.
MARKER_TAIL = "^\\"


def norm(run):
    return "".join(ASCII_QUOTE.get(c, c) for c in run)


def mask(text, pattern, flags=0):
    """Blank every match, keeping the file's offsets (and line numbers)."""
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                  text, flags=flags)


def readable(path):
    """The file with HTML comments and fenced code blanked out.

    The OCR skills quote bad readings inside `<!-- ... -->` on purpose --
    `<!-- script-ok ... (OCR had €°3) -->` -- so a screen that reads them
    reports the evidence as the defect.
    """
    text = path.read_text(encoding="utf-8")
    text = mask(text, r"<!--.*?-->", re.S)
    return mask(text, r"(?ms)^```.*?^```")


def scopes(text):
    """(offset, text) for each pairing scope: a paragraph, or a table cell."""
    out = []
    pos = 0
    # The separator is captured rather than assumed two characters long: a
    # blank line carrying spaces, or a run of three, drifts the offsets
    # otherwise, and every finding after it reports the wrong line.
    for k, part in enumerate(re.split(r"(\n[ \t]*\n)", text)):
        if k % 2 == 0:
            if re.search(r"(?m)^\s*\|", part):
                # a pipe table: pair inside one cell, never across the row
                cell = pos
                for piece in re.split(r"([|\n])", part):
                    if piece not in ("|", "\n"):
                        out.append((cell, piece))
                    cell += len(piece)
            else:
                out.append((pos, part))
        pos += len(part)
    return out


def quote_tokens(text):
    """[(offset, run, kind)] for the quote marks in one scope.

    kind is `O` (opener), `C` (closer), `SUP` (a run after a digit) or `?`.
    """
    toks = []
    for m in QRUN.finditer(text):
        run = norm(m.group(0))
        start, end = m.span()
        before = text[start - 1] if start else " "
        after = text[end] if end < len(text) else " "

        if len(run) == 1 and run == "'":
            if WORDCH.match(before) and WORDCH.match(after):
                continue                      # Tabari's
            if before in "sS" and not WORDCH.match(after):
                continue                      # Mauryans'
            # Any OTHER letter before a trailing `'` is kept, because it is
            # usually the closer of a gloss (`'Gokul'`, `'pzwt'`) and not a
            # possessive: only 22% of the corpus's 17,418 trailing
            # apostrophes follow an `s`. Dropping them all cost the pairing
            # its closers and left 87 spans running on into the next
            # quotation; 33 still do, and MAX_SPAN drops those.
        if len(run) >= 2 and before.isdigit():
            toks.append((start, run, "SUP"))
            continue
        if run.endswith("'") and AYN_RE.match(text[end:]):
            run = run[:-1]                    # ("'Abd -> opener `("`, then ʿayn
            if not run:
                continue
        opener = not WORDCH.match(before) and (WORDCH.match(after) or after in "([")
        closer = bool(WORDCH.match(before)) or before in ".,;:!?)]"
        toks.append((start, run, "O" if opener else ("C" if closer else "?")))
    return toks


def is_wreck(span):
    """True when the span sits in OCR wreckage rather than prose.

    ONS_161's `j ^ ' *\\J^* \\}• • • *'Q'" '^"*` pairs two marks that
    disagree, but the quotes are a symptom of the wreck, not a defect of
    their own.
    """
    if sum(span.count(c) for c in "^\\•}{~<>") >= 3:
        return True
    solid = [c for c in span if not c.isspace()]
    return bool(solid) and sum(c.isalpha() for c in solid) < 0.5 * len(solid)


def still_open(toks, i, mark):
    """True when `mark` opened a quotation before token i and never closed."""
    for k in range(i - 1, -1, -1):
        if toks[k][1] != mark:
            continue
        if toks[k][2] == "C":
            return False
        if toks[k][2] == "O":
            return True
    return False


def is_nested_close(toks, i, j, inner):
    """True when the closing run is two marks each doing their own job.

    Nesting puts two closers side by side, and the run that results is
    correct text, not a split mark:

        "A Coin Bearing the Name "Safi""          inner opened inside the span
        "the title *yagbu* 'chief of a clan'"     outer still open outside it

    Both need evidence. Without the first test `"...site report''"` would be
    excused too, and that one is a `"` the OCR split; without the second,
    every `"triratna"'` would be read as nesting.
    """
    opener, closer = toks[i][1], toks[j][1]
    if len(opener) != 1 or len(closer) != 2:
        return False
    if closer.endswith(opener):                 # inner opened inside the span
        return bool(re.search(f"{re.escape(closer[0])}(?=[A-Za-z0-9])", inner))
    if closer.startswith(opener):               # outer opened before the span
        return still_open(toks, i, closer[1])
    return False


def pairs_of(toks):
    """[(opener index, closer index)] left to right; unclosed openers pair with
    nothing, which is what keeps one stray mark from shifting everything after
    it."""
    out, i = [], 0
    while i < len(toks):
        if toks[i][2] != "O":
            i += 1
            continue
        j = next((k for k in range(i + 1, len(toks)) if toks[k][2] == "C"), None)
        if j is None:
            break
        out.append((i, j))
        i = j + 1
    return out


def quote_findings(text, include_single=False):
    """[(offset, opener, closer, span, wreck)] for mismatched quote spans."""
    found = []
    for base, scope in scopes(text):
        toks = quote_tokens(scope)
        for pair in pairs_of(toks):
            opener, closer = toks[pair[0]], toks[pair[1]]
            if opener[1] == closer[1] and (len(opener[1]) == 1 or opener[1] == '"'):
                continue                      # balanced
            if len(opener[1]) == 1 and len(closer[1]) == 1 and not include_single:
                continue
            span = scope[opener[0]:closer[0] + len(closer[1])]
            if len(span) > MAX_SPAN:
                continue
            if is_nested_close(toks, *pair,
                               span[len(opener[1]):-len(closer[1])]):
                continue
            found.append((base + opener[0], opener[1], closer[1], span,
                          is_wreck(scope[max(0, opener[0] - 20):
                                         closer[0] + len(closer[1]) + 20])))
    return found


# A `''` that closes nothing, right after a lowercase letter, with the next
# sentence starting after it. On these scans that is a question mark: ONS_165
# alone carried 15, among them `"Muhammad''"` in a sentence that goes on to
# say *with question-mark i.e. he was not sure*.
QUESTION_AT = re.compile(r"''(?=\s+[\"'(*A-Z]|\s*$)")


def question_findings(text):
    """[(offset, word, context)] for a `''` the page may print as `?`."""
    found = []
    for base, scope in scopes(text):
        toks = quote_tokens(scope)
        used = {k for pair in pairs_of(toks) for k in pair}
        for k, (off, run, _kind) in enumerate(toks):
            if k in used or run != "''" or not off or not scope[off - 1].islower():
                continue
            if not QUESTION_AT.match(scope, off):
                continue
            word = re.search(r"[A-Za-z-]+$", scope[:off])
            found.append((base + off, word.group(0) if word else "",
                          scope[max(0, off - 60):off + 16]))
    return found


def suffix(n):
    if n % 100 in (11, 12, 13):
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def ordinal_reading(text, start, end):
    """(number, suffix, old, new) when the run at [start:end) is an ordinal.

    The decision is the word after the run, never the digit alone -- see the
    module docstring on `828".` and `7 3/8''`.

    `old` and `new` carry that word with them (`16''' century` ->
    `16th century`), because the edit must fire only where the evidence is.
    A bare `16'''` sweeps every other run with the same shape in the file,
    and 30 of those across 13 files are footnote markers, not ordinals.
    """
    digits = re.search(r"(\d+)$", text[:start])
    if not digits:
        return None
    tail = end
    while tail < len(text) and text[tail] in MARKER_TAIL:
        tail += 1
    rest = text[tail:tail + 60]
    word = re.match(r"\s*([A-Za-z]+|[-–])", rest)
    if not word:
        return None
    tok = word.group(1)
    low = tok.lower()
    n = int(digits.group(1))

    ordinal = False
    if low in CENTURY_WORDS or (low == "c" and not rest[word.end():].startswith("/")):
        ordinal = n <= 21                     # no 24th century in this corpus
    elif tok in MONTHS:
        ordinal = n <= 31
    elif low in ORDINAL_NOUNS or tok in ("C", "International", "All-Russian"):
        ordinal = n <= 99
    elif low in CONNECTORS or tok in ("-", "–"):
        # `6"' and 8"' century`, `8'''-10"' c. AD`: the century word is just
        # beyond the connector. Without it, `AH 1147/1734'' to 1164` is a
        # footnote marker on a date, not an ordinal.
        beyond = rest[word.end():word.end() + 40]
        ordinal = n <= 21 and bool(
            re.search(r"\b(?:%s)\b|\bc[./\s]" % "|".join(CENTURY_WORDS),
                      beyond, re.IGNORECASE))
    if not ordinal:
        return None
    stop = tail + word.end()
    old, new = text[digits.start(1):stop], f"{n}{suffix(n)}{text[tail:stop]}"
    if "\n" in old:
        return None                           # the evidence is on the next line
    return n, suffix(n), old, new


def superscript_findings(text):
    """[(offset, run, reading, context)] for every quote run after a digit."""
    found = []
    for base, scope in scopes(text):
        for off, run, kind in quote_tokens(scope):
            if kind != "SUP":
                continue
            end = off + len(run)
            reading = ordinal_reading(scope, off, end)
            ctx = scope[max(0, off - 28):end + 32]
            found.append((base + off, run, reading, ctx))
    return found


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def one_line(s):
    return re.sub(r"\s+", " ", s).strip()


def resolve(arg):
    p = Path(arg)
    if not p.exists() and "/" not in arg and not arg.endswith(".md"):
        p = Path("jons") / f"{arg}.md"
    return p


def scan(path, include_single=False, include_wrecks=False, quiet_clean=False):
    text = readable(path)
    quotes = quote_findings(text, include_single)
    sups = superscript_findings(text)
    questions = question_findings(text)
    shown = [q for q in quotes if include_wrecks or not q[4]]
    wrecks = len(quotes) - len(shown)
    ordinals = sum(1 for s in sups if s[2])

    if not shown and not sups and not questions:
        if not quiet_clean:
            print(f"{path}: clean")
        return 0

    rows = [(off, "q", rest) for off, *rest in shown]
    rows += [(off, "s", rest) for off, *rest in sups]
    rows += [(off, "?", rest) for off, *rest in questions]
    for off, kind, f in sorted(rows, key=lambda r: r[0]):
        n = line_of(text, off)
        if kind == "q":
            opener, closer, span, wreck = f
            tag = "QUOTES-WRECK" if wreck else "QUOTES"
            print(f"{path}:{n}: {tag}  opener `{opener}` vs closer `{closer}`")
            print(f"    {one_line(span)[:150]}")
        elif kind == "?":
            word, ctx = f
            print(f"{path}:{n}: QUESTION  `''` closing nothing after "
                  f"`{word}` -- the page may print `?`; render it")
            print(f"    {one_line(ctx)[:150]}")
        else:
            run, reading, ctx = f
            if reading:
                _, _, old, new = reading
                print(f"{path}:{n}: SUPERSCRIPT  ordinal  `{old}` -> `{new}`")
            else:
                print(f"{path}:{n}: SUPERSCRIPT  check  `{run}` -- render the page: "
                      f"ordinal, footnote marker or a real quote?")
            print(f"    {one_line(ctx)[:150]}")

    note = (f"-- {len(shown)} mismatched span(s), {len(sups)} superscript "
            f"run(s), {len(questions)} unclosed `''`")
    if ordinals:
        note += f" ({ordinals} readable as ordinals: `ordinals` emits the batch)"
    if wrecks:
        note += (f"; {wrecks} span(s) in OCR wreckage suppressed "
                 f"(--include-wrecks) -- those lines belong to "
                 f"transcribe-foreign-script")
    print(note)
    return 1


def emit_ordinals(path):
    """Print an `apply_edits.py` batch for the runs that read as ordinals."""
    text = readable(path)
    edits = {}
    for off, run, reading, ctx in superscript_findings(text):
        if not reading:
            continue
        _, _, old, new = reading
        edits.setdefault(old, new)
    if not edits:
        print(f"# {path}: no ordinal superscripts found")
        return 0
    raw = path.read_text(encoding="utf-8")
    print(f"# {path}: {len(edits)} ordinal superscript(s) read as `N` + suffix")
    print(f"# Confirm a sample against the page render before --write.")
    for old, new in edits.items():
        count = raw.count(old)
        if count != text.count(old):
            # `apply_edits.py` replaces plain text, and the OCR skills quote
            # bad readings inside `<!-- ... -->` on purpose. Hand-edit this
            # one rather than sweeping the file.
            print(f"# {old} => {new}  -- SKIPPED: also occurs inside an "
                  f"HTML comment; edit the prose occurrence by hand")
            continue
        print(f"{old} => {new}" + (f" => {count}" if count != 1 else ""))
    return 1


def main(argv):
    flags = {a for a in argv[1:] if a.startswith("-")}
    args = [a for a in argv[1:] if not a.startswith("-")]
    unknown = flags - {"--include-single", "--include-wrecks"}
    if len(args) < 2 or args[0] not in ("scan", "ordinals") or unknown:
        print(__doc__)
        return 2

    rc = 0
    for arg in args[1:]:
        path = resolve(arg)
        if not path.exists():
            print(f"no such file: {path}")
            rc = max(rc, 2)
            continue
        if args[0] == "ordinals":
            rc = max(rc, emit_ordinals(path))
        else:
            rc = max(rc, scan(path,
                              include_single="--include-single" in flags,
                              include_wrecks="--include-wrecks" in flags,
                              quiet_clean=len(args) > 2))
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:          # piped into `head`, which is expected
        sys.exit(1)
