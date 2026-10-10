#!/usr/bin/env python3
"""Apply a batch of in-line OCR fixes to a Markdown file, all or nothing.

Edits file format, one per line:

    old text => new text
    old text => new text => 3        # optional expected match count

Blank lines are ignored, and so is a line starting with `#` that carries no
` => ` separator -- that is a comment. A line that starts with `#` AND has a
separator is an edit, not a comment: Markdown headings begin with `#`, and
silently dropping `## Arab- Byzantine => ## Arab-Byzantine` is how a heading
fix goes missing from a batch without a word (it happened on ONS_109). The
trade is that a comment containing ` => ` is now read as an edit and fails
the match check -- loudly, which is the point.

Every `old` must match the file exactly the expected number of times (default
1); an `old` that matches 0 or 2+ times is usually a sign it needs more
context. Neither side may contain a line break, and the file's line count must
be unchanged afterwards -- the fix-ocr line-break invariant. If any edit fails
a check, nothing is written.

    python3 apply_edits.py jons/ONS_147.md edits.txt          # dry run: show word diffs
    python3 apply_edits.py jons/ONS_147.md edits.txt --write  # apply
"""
import argparse
import difflib
import sys


def is_comment(raw):
    """A `#` line is a comment only when it holds no edit separator."""
    return raw.startswith("#") and " => " not in raw


def parse(path):
    edits = []
    for n, raw in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
        if not raw.strip() or is_comment(raw):
            continue
        parts = raw.split(" => ")
        if len(parts) == 3 and parts[2].strip().isdigit():
            edits.append((n, parts[0], parts[1], int(parts[2])))
        elif len(parts) == 2:
            edits.append((n, parts[0], parts[1], 1))
        else:
            sys.exit(f"{path}:{n}: expected 'old => new' or 'old => new => COUNT'")
    return edits


def word_diff(old, new):
    ow, nw = old.split(" "), new.split(" ")
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ow, nw, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append(f"{' '.join(ow[i1:i2])!r} -> {' '.join(nw[j1:j2])!r}")
    return "; ".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("edits")
    ap.add_argument("--write", action="store_true", help="write the file (default: dry run)")
    args = ap.parse_args()

    text = open(args.md, encoding="utf-8").read()
    nlines = text.count("\n")
    bad = 0
    parsed = parse(args.edits)
    for n, old, new, want in parsed:
        got = text.count(old)
        if got != want:
            hint = ("  (this `#` line was read as an edit, not a comment)"
                    if old.startswith("#") else "")
            print(f"SKIP {args.edits}:{n}: {got} match(es), expected {want}: {old!r}{hint}")
            bad += 1
            continue
        if old == new:
            print(f"SKIP {args.edits}:{n}: old and new are identical")
            bad += 1
            continue
        line = text[: text.index(old)].count("\n") + 1
        print(f"{args.md}:{line}: {word_diff(old, new)}" + (f"  (x{want})" if want > 1 else ""))
        text = text.replace(old, new)
    if text.count("\n") != nlines:
        sys.exit("ABORT: line count changed; nothing written")
    if bad:
        sys.exit(f"ABORT: {bad} edit(s) failed; nothing written")
    # Print the count so a line the parser dropped is visible: compare it
    # against the number of edits you wrote.
    if args.write:
        open(args.md, "w", encoding="utf-8").write(text)
        print(f"written; {len(parsed)} edit(s) applied")
    else:
        print(f"dry run; {len(parsed)} edit(s) ready, re-run with --write to apply")


if __name__ == "__main__":
    main()
