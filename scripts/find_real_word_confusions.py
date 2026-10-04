#!/usr/bin/env python3
"""List likely real-word OCR confusions for review.

cspell only flags non-words, so an OCR misreading that happens to land on a
real English word -- `modem` for `modern`, the `rn`->`m` confusion -- passes
the spellcheck in every file, forever. This script hunts for more of them.

For every word in the corpus it applies the glyph confusions the OCR engine is
known to make (see fix-ocr's "Common OCR error patterns") and keeps the
variants that are themselves words in the corpus. A pair is reported when

  * the project's cspell config lets the suspect through -- otherwise the
    ordinary spellcheck already catches it -- and
  * the variant is a dictionary word, and
  * the variant is at least --ratio times as common in the corpus as the
    suspect.

A suspect cspell lets through is usually a real word, but it may also be a
non-word shorter than cspell's `minWordLength` (4 by default), which cspell
never checks at all: `thc`, `ncw`, `hke` are invisible to it. The report tags
those "short non-word" to tell the two apart.

The corpus is narrow (oriental numismatics), so corpus frequency is a strong
signal: `modern` is a common word here and `modem` has no business appearing.
A systematic misreading can be surprisingly frequent, though -- before it was
fixed, `modem` stood at roughly one in eight occurrences of `modern` -- so keep
--ratio low and let the review do the filtering. For the same reason the report
lists the commonest suspects first, not the most lopsided ratios.

OCR garble keeps the capitalization of the word it garbles, so a pair whose two
sides are capitalized differently -- `Ali` is a name nearly every time it
appears, `ah` almost never -- is two different words, and is dropped.
--include-proper keeps those pairs.

Every hit is a candidate, not a verdict (`clay` is not always a garbled
`day`). Vet each one as fix-ocr's "Known real-word OCR confusions" describes
before adding it to the `flagWords` list in cspell.config.yaml. Words already
in `flagWords` are rejected by cspell and so drop out of the report. A pair
you have vetted and decided not to pursue goes in
scripts/real_word_confusions_reviewed.txt so later runs skip it.

Usage:
    # Print the review list for the whole corpus.
    scripts/find_real_word_confusions.py jons/*.md

    # Stricter threshold, more example lines per pair.
    scripts/find_real_word_confusions.py --ratio 20 --examples 10 jons/*.md
"""

import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile

# Glyph sequences the OCR engine confuses, each tried in both directions.
CONFUSIONS = [
    ("rn", "m"),
    ("nm", "m"),
    ("ri", "n"),
    ("ii", "n"),
    ("ii", "u"),
    ("li", "h"),
    ("cl", "d"),
    ("vv", "w"),
    ("c", "d"),
    ("c", "e"),
    ("h", "b"),
]

# A run of letters. Tokens containing non-ASCII letters (transliterations such
# as `Shāh`, Arabic legends) are skipped: the confusions above are about Latin
# glyphs, and cspell's English dictionaries do not cover those tokens anyway.
WORD = re.compile(r"[^\W\d_]+")

# Characters of context shown either side of each example occurrence.
CONTEXT = 40

# A word capitalized (`Ali`, not `ALI` or `ali`) in at least this share of its
# occurrences is taken to be a proper noun...
PROPER_SHARE = 0.9

# ...provided it has at least this many occurrences that are not all capitals.
# Below that there is too little to go on: a lone sentence-initial `Carly` for
# `Early` must not count as a name.
PROPER_SAMPLE = 5

# Pairs already vetted and set aside, one `suspect->variant` per line.
REVIEWED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "real_word_confusions_reviewed.txt")


def words(line):
    """Yield (match, lowercased word) for each ASCII word in *line*."""
    for m in WORD.finditer(line):
        if m.group().isascii():
            yield m, m.group().lower()


def read_reviewed(path):
    """Return the set of (suspect, variant) pairs listed in *path*."""
    pairs = set()
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            suspect, sep, variant = (s.strip().lower() for s in line.partition("->"))
            if not (sep and suspect and variant):
                sys.exit(f"{path}:{lineno}: expected suspect->variant, got {line!r}")
            pairs.add((suspect, variant))
    return pairs


def variants(word):
    """Yield (variant, rule) for each single confusion applied to *word*."""
    for a, b in CONFUSIONS:
        for old, new in ((a, b), (b, a)):
            start = word.find(old)
            while start != -1:
                yield word[:start] + new + word[start + len(old):], f"{old}->{new}"
                start = word.find(old, start + 1)


def is_proper(word, capitalized, cased):
    """Return whether *word* is a proper noun, or None if it is too rare to tell.

    *capitalized* counts each word's occurrences with an initial capital and
    *cased* its occurrences not in all capitals (a heading's `ALI` says nothing
    either way).
    """
    if cased[word] < PROPER_SAMPLE:
        return None
    return capitalized[word] >= PROPER_SHARE * cased[word]


def flagged_by_cspell(candidates, config):
    """Return the subset of *candidates* that cspell reports as an issue."""
    result = subprocess.run(
        ["cspell", "lint", "--config", config, "--no-progress", "--no-summary",
         "--words-only", "--unique", "stdin"],
        input="\n".join(sorted(candidates)) + "\n",
        capture_output=True, text=True)
    # cspell exits 1 when it finds issues; anything else is a real failure.
    if result.returncode not in (0, 1):
        sys.exit(f"cspell failed:\n{result.stderr}")
    return {w.lower() for w in result.stdout.split()}


def non_words(candidates, config):
    """Return the subset of *candidates* that are not dictionary words.

    Unlike flagged_by_cspell() this also judges words shorter than cspell's
    `minWordLength`, by layering an override on top of *config*.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as f:
        f.write(f"import:\n  - {os.path.abspath(config)!r}\nminWordLength: 1\n")
        f.flush()
        return flagged_by_cspell(candidates, f.name)


def snippet(line, m):
    """Return *line* trimmed to CONTEXT characters either side of match *m*."""
    start = max(m.start() - CONTEXT, 0)
    end = min(m.end() + CONTEXT, len(line))
    return ("..." if start else "") + line[start:end].strip() + ("..." if end < len(line) else "")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", metavar="FILE", nargs="+",
                        help="Markdown files to scan")
    parser.add_argument("--ratio", type=float, default=5,
                        help="report a pair when the variant is at least this many times "
                             "as common as the suspect (default 5)")
    parser.add_argument("--min-length", type=int, default=3,
                        help="ignore suspects shorter than this (default 3)")
    parser.add_argument("--examples", type=int, default=3,
                        help="example lines to print per pair (default 3)")
    parser.add_argument("--config", default="cspell.config.yaml",
                        help="cspell config to check words against (default cspell.config.yaml)")
    parser.add_argument("--reviewed", default=REVIEWED,
                        help="file of vetted suspect->variant pairs to skip "
                             "(default scripts/real_word_confusions_reviewed.txt)")
    parser.add_argument("--include-proper", action="store_true",
                        help="keep pairs where only one side is a proper noun")
    args = parser.parse_args(argv)

    try:
        reviewed = read_reviewed(args.reviewed)
    except OSError as e:
        sys.exit(f"{args.reviewed}: {e}")

    lines = {}
    counts = collections.Counter()
    capitalized = collections.Counter()
    cased = collections.Counter()
    for path in args.files:
        try:
            with open(path, encoding="utf-8") as f:
                lines[path] = f.read().splitlines()
        except OSError as e:
            print(f"{path}: {e}", file=sys.stderr)
            continue
        for line in lines[path]:
            for m, w in words(line):
                counts[w] += 1
                if not m.group().isupper():
                    cased[w] += 1
                    capitalized[w] += m.group()[0].isupper()

    pairs = collections.defaultdict(dict)  # suspect -> {variant: rule}
    for word, n in counts.items():
        if len(word) < args.min_length:
            continue
        for variant, rule in variants(word):
            if counts[variant] >= args.ratio * n:
                pairs[word].setdefault(variant, rule)

    caught = flagged_by_cspell(set(pairs), args.config)
    unreal = non_words(set(pairs) | {v for vs in pairs.values() for v in vs}, args.config)
    skipped_reviewed = skipped_proper = 0
    for word in list(pairs):
        if word in caught:
            del pairs[word]
            continue
        for variant in list(pairs[word]):
            if variant in unreal:
                del pairs[word][variant]
            elif (word, variant) in reviewed:
                del pairs[word][variant]
                skipped_reviewed += 1
            elif not args.include_proper:
                proper = {is_proper(w, capitalized, cased) for w in (word, variant)}
                if proper == {True, False}:
                    del pairs[word][variant]
                    skipped_proper += 1
        if not pairs[word]:
            del pairs[word]

    examples = collections.defaultdict(list)
    for path, file_lines in lines.items():
        for lineno, line in enumerate(file_lines, 1):
            for m, w in words(line):
                if w in pairs:
                    examples[w].append(f"{path}:{lineno}: {snippet(line, m)}")

    # Commonest suspects first: a confusion the OCR engine makes systematically
    # recurs, and fixing it pays off most. Sorting by ratio instead buries
    # those, since their own frequency keeps the ratio down.
    report = sorted(((counts[w], counts[v] / counts[w], w, v, rule)
                     for w, vs in pairs.items() for v, rule in vs.items()),
                    reverse=True)
    for _, ratio, word, variant, rule in report:
        kind = ", short non-word" if word in unreal else ""
        print(f"{word} -> {variant}  [{rule}{kind}]  "
              f"{word} {counts[word]}, {variant} {counts[variant]} ({ratio:.0f}x)")
        for example in examples[word][:args.examples]:
            print(f"    {example}")
        if len(examples[word]) > args.examples:
            print(f"    (+{len(examples[word]) - args.examples} more)")
    print(f"{len(report)} pair(s) for review; skipped {skipped_reviewed} already reviewed, "
          f"{skipped_proper} proper noun vs. common word", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
