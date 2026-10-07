#!/usr/bin/env python3
"""Find text `pdfmd` read off a mirrored scan, so every word came out
spelled backwards.

A handful of pages in this corpus were scanned flipped. The OCR engine still
found the lines and still read the words left to right in the right order,
but each word's glyphs are mirrored, so it transcribed every word reversed:

    dna \\_ niJ taerg liated dna dehsilbup 5 ynaM tnereiffd
    -> and ... in great detail and published 5 ... different

This matters because it does not look recoverable. `dehsilbup` reads as pure
noise, so a fix-ocr pass sees it, correctly judges it un-guessable under the
Hard constraints (it cannot be deleted -- over 12 characters -- and must not
be invented), reports it as residual garble, and ticks the file off. ONS_100
went through exactly that way and stayed broken. The text is in fact fully
recoverable: reverse each token and the English comes back.

cspell does not save you here either. It flags most of the run, which is how
the pass knew the words were unknown, but it cannot say *why*, and a few
reversed words are real tokens forwards -- `dna` matches DNA, `ynaM` and
`niJ` pass too -- so even a zero-unknowns gate would leave some behind.

## The decode

Word order is preserved; only the letters within each word are reversed. So
the repair is per-token, not a reversal of the whole line:

    eb ,gnitseretni dna I tup edisa seno taht erew .lausunu
    -> be interesting, and I put aside ones that were unusual.

Note the punctuation travels with the word and has to be moved back by hand
(`,gnitseretni` -> `interesting,`), which is why this script reports rather
than rewrites. Confirm every restored passage against the page render before
editing -- the same rule as any other fix-ocr repair.

## Detection

A token counts as evidence when its reverse is a common English word and the
token itself is not. Two on one line is enough: ordinary prose does not
produce that by accident, and mirrored prose always carries common words.

The word list is built in rather than read from /usr/share/dict/words, which
is absent on many machines and, worse, makes the test too loose when it is
present: it lacks plurals, so `dies`, `dots`, `parts` and `maps` all look
like reversals of `seid`, `stod`, `strap` and `spam` and every catalogue
table in the corpus lights up.

Usage:
    detect_mirrored_text.py scan ONS_100
    detect_mirrored_text.py scan jons/*.md

Exit status is 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""

import re
import sys
from pathlib import Path

# Common English words whose reversal is not itself a word. Mirrored prose
# always carries several; clean prose carries none reversed. Short entries
# matter most -- `eht`, `dna`, `fo`, `saw` are the giveaways -- but the long
# ones make a single line conclusive on its own.
COMMON = {
    "the", "and", "that", "this", "with", "were", "was", "from", "have",
    "been", "which", "for", "not", "but", "his", "her", "they", "all",
    "one", "out", "who", "had", "has", "can", "will", "would", "there",
    "their", "what", "about", "than", "then", "them", "these", "those",
    "some", "more", "other", "into", "over", "only", "also", "such",
    "when", "where", "after", "before", "first", "very", "much", "most",
    "many", "made", "make", "same", "each", "both", "between", "under",
    "being", "because", "although", "however", "while", "during",
    "great", "detail", "published", "decided", "prepare", "manuscript",
    "oriental", "different", "unusual", "aside", "going", "called",
    "cover", "types", "located", "none", "illustrated", "reading",
    "circular", "legend", "satisfactory", "side", "book", "trade",
    "interesting", "ones", "put", "coins", "coin", "mint", "struck",
    "silver", "copper", "gold", "known", "found", "given", "above",
    "below", "number", "years", "year", "early", "later", "part",
    "though", "through", "another", "little", "large", "small", "good",
    "well", "just", "like", "time", "even", "back", "down", "still",
    "seen", "says", "said", "note", "notes", "name", "names", "used",
    "lord", "king", "reign", "date", "dated", "type", "obverse",
    "reverse", "weight", "legends", "letters", "word", "words",
}

# Words that read as another word backwards, so they are evidence of
# nothing. Three-letter pairs are the bulk of them -- `saw`/`was`,
# `now`/`won`, `ton`/`not`, `pot`/`top` -- and the length floor below
# handles those wholesale; these are the longer ones that reverse into a
# word COMMON happens to hold.
BOTH_WAYS = {"trap", "traps", "emit", "emits", "eton"}

# The reversed reading must be this long to count. Below it, ordinary
# English collides with itself constantly: `saw` is not a mirrored `was`,
# and three of those on a page would convict any clean file.
MIN_LEN = 4

TOKEN = re.compile(r"[A-Za-z]{2,}")


def evidence(line):
    """Tokens on this line that are a common word spelled backwards."""
    out = []
    for t in TOKEN.findall(line):
        low = t.lower()
        if low in COMMON or low in BOTH_WAYS or len(low) < MIN_LEN:
            continue
        if low[::-1] in COMMON:
            out.append(t)
    return out


def decode(line):
    """Reverse each token in place, leaving everything else where it is."""
    return TOKEN.sub(lambda m: m.group(0)[::-1], line)


def scan(path, threshold=2):
    """Lines carrying `threshold` or more *distinct* reversed words.

    Distinct matters: a foreign-language passage trips the raw count on one
    word repeated -- ONS_177's Italian says `neve` (snow) twice, which
    reverses to `even`. Mirrored English never looks like that; it brings a
    varied reversed vocabulary, because every word on the line is reversed.
    """
    findings = []
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        ev = evidence(line)
        if len({t.lower() for t in ev}) >= threshold:
            findings.append((n, ev, line.strip(), decode(line).strip()))
    return findings


def resolve(arg):
    p = Path(arg)
    if not p.exists() and "/" not in arg and not arg.endswith(".md"):
        p = Path("jons") / f"{arg}.md"
    return p


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    if len(args) < 2 or args[0] != "scan":
        print(__doc__)
        return 2

    rc = 0
    for arg in args[1:]:
        path = resolve(arg)
        if not path.exists():
            print(f"no such file: {path}")
            rc = max(rc, 2)
            continue
        findings = scan(path)
        if not findings:
            if len(args) == 2:
                print(f"{path}: clean")
            continue
        rc = 1
        for n, ev, raw, dec in findings:
            print(f"{path}:{n}: MIRRORED  {len(ev)} reversed token(s): "
                  f"{', '.join(ev[:6])}")
            print(f"    as OCR'd: {raw[:150]}")
            print(f"    decoded : {dec[:150]}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
