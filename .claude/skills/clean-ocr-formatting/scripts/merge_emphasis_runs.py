#!/usr/bin/env python3
"""Put one emphasis span around an italic phrase where `pdfmd` put one around
every word of it.

Where the scan sets a title or a quoted passage in italic, `pdfmd` sometimes
carries the emphasis across but marks it a word at a time:

```
*Fig 5* *Egyptian glass weight 1* *19* *g* *18* *mm*
```

The reader's problem is not that this is ugly. Half of it does not render as
emphasis at all. CommonMark will not close a span on a space, so `*word *`
comes out of kramdown as the literal text `*word *`, and across the corpus
**35,868 asterisks reach the rendered page** that way, in 153 files. The
degenerate spans are worse than literal: `* *` alone on a line renders as a
bullet list whose item is `*`, and `**  **` renders as a horizontal rule, so
13 files carry 23 rules nobody set.

Three transformations, in this order, per line:

  padding   `*word *` -> `*word* `. The space moves outside the markers, which
            is what makes the span render at all.
  empty     `* *`, `**  **` -> the whitespace they stood in. There is no text
            to emphasise, and what they do render as is never wanted.
  merge     `*a* *b*` -> `*a b*`, for two spans of the same marker with only
            whitespace between them.

The merge is the one worth arguing about, and the argument is that it cannot
change what a reader sees: `<em>a</em> <em>b</em>` and `<em>a b</em>` set the
same words in the same face. So the risk is not mis-rendering, it is only
whether the source now claims one phrase where the page set two side by side
-- a pair of table cells, two captions in a row. That claim is invisible in
the rendering and costs nothing downstream, where a `*` in the wrong place
inside a *word* would cost plenty.

What it will not touch:

  * a span holding `[`, `]`, `<`, `>`, `|` or a backtick. `*[figure]*` is the
    marker `detect-missing-figures` writes and `*Obv.* *[figure]*` must stay
    two spans; the rest are table and HTML syntax.
  * a span with any `*` inside it, so nesting (`**bold *it* bold**`) is left
    alone whole.
  * an escaped `\\*`, so IS_026's `\\*\\*\\*\\*` rule survives.
  * a gap with anything but whitespace in it. `*A* and *B*` are two titles
    with a roman `and` between them, `*a*, *b*` two words with a roman comma,
    and `*Gharn* ā *ta*` a word split by a diacritic the OCR set in another
    face -- that last one is a real defect, and `fix-ocr`'s, not this one's.

Usage:

    merge_emphasis_runs.py scan ONS_185          # report, change nothing
    merge_emphasis_runs.py scan jons/*.md        # corpus sweep
    merge_emphasis_runs.py scan ONS_185 -v       # print every line it changes
    merge_emphasis_runs.py fix  ONS_185

Every write is checked first: the line's text with all emphasis markers
removed and runs of whitespace collapsed has to come out identical, or the
line is left alone and reported as REFUSED. Exit status is 0 when there is
nothing to do, 1 otherwise.
"""

import argparse
import pathlib
import re
import sys

# A span: 1-3 asterisks, no asterisk inside, closed by the same run. The
# `(?!\*)` after the marker is what stops `**bold *it* bold**` being read as
# an empty `*` span at its first two characters.
SPAN = re.compile(r"(?<![\\*])(\*{1,3})(?!\*)([^*\n]*)\1(?!\*)")
# Characters that mean the span belongs to something else -- a figure or
# `[mark]` placeholder, a table rule, inline HTML, code.
OWNED = re.compile(r"[\[\]<>|`]")
WS = re.compile(r"[ \t]{2,}")
INDENT = re.compile(r"^[ \t]*")


def find_spans(line):
    out, pos = [], 0
    while True:
        m = SPAN.search(line, pos)
        if not m:
            return out
        out.append(m)
        pos = m.end()


def rewrite(line):
    """The line with its emphasis runs merged, or the line unchanged."""
    indent = INDENT.match(line).group(0)
    body = line[len(indent):]
    ms = [m for m in find_spans(body) if not OWNED.search(m.group(2))]
    if not ms:
        return line

    groups, cur = [], [ms[0]]
    for a, b in zip(ms, ms[1:]):
        if a.group(1) == b.group(1) and not body[a.end():b.start()].strip():
            cur.append(b)
        else:
            groups.append(cur)
            cur = [b]
    groups.append(cur)

    out = []

    def space():
        """A separator, unless one is already there or the line has not begun."""
        if out and not out[-1][-1:].isspace():
            out.append(" ")

    pos = 0
    for g in groups:
        between = body[pos:g[0].start()]
        if between:
            # a separator this pass already emitted is not doubled
            out.append(between.lstrip(" \t")
                       if out and out[-1][-1:].isspace() else between)
        # Whitespace inside the markers is what stops the span rendering, so it
        # moves outside rather than being dropped: `*word *` -> `*word* `.
        head, tail = g[0].group(2), g[-1].group(2)
        text = " ".join(" ".join(m.group(2).split()) for m in g).strip()
        if head[:1].isspace():
            space()
        if text:
            out.append(g[0].group(1) + text + g[0].group(1))
            if tail[-1:].isspace():
                space()
        else:
            space()                       # an empty span is the gap it stood in
        pos = g[-1].end()
    rest = body[pos:]
    out.append(rest.lstrip(" \t") if out and out[-1][-1:].isspace() else rest)

    # `indent` already holds whatever the line began with, so anything the
    # rebuild leaves in front of the body is residue from a span that used to
    # sit there -- and a space pushed to the front of `11. Ashmolean` makes
    # kramdown read a list item where there was prose (ONS_240).
    rebuilt = indent + "".join(out).lstrip(" \t")
    return rebuilt if rebuilt.strip() else ""


def settle(line, limit=6):
    """`rewrite` until the line stops changing.

    One pass can expose a merge the pass before it could not see: dropping an
    empty span from `*Mark A* ** ** *Mark B*` leaves two spans that are now
    adjacent. Over the corpus a second pass finds more in 33 files, a third
    finds none.
    """
    for _ in range(limit):
        new = rewrite(line)
        if new == line:
            break
        line = new
    return line


def words(text):
    """The line as a reader sees it: no emphasis markers, one space a gap."""
    return " ".join(text.replace("*", "").split())


def process(path, verbose=False, write=False):
    lines = path.read_text(encoding="utf-8").split("\n")
    changed, refused, out = [], [], []
    for n, line in enumerate(lines, 1):
        new = settle(line)
        if new == line:
            out.append(line)
            continue
        if words(new) != words(line):
            refused.append((n, line, new))
            out.append(line)
            continue
        changed.append((n, line, new))
        out.append(new)

    if changed and write:
        path.write_text("\n".join(out), encoding="utf-8")
    verb = "merged" if write else "mergeable"
    if changed or refused:
        print(f"{path}: {len(changed)} line(s) {verb}"
              + (f", {len(refused)} REFUSED" if refused else ""))
    if verbose:
        for n, old, new in changed:
            print(f"  {n}:\n    - {old[:150]}\n    + {new[:150]}")
    for n, old, new in refused:
        print(f"  {n}: REFUSED -- the text would change, so the line is left alone"
              f"\n    - {old[:150]}\n    + {new[:150]}")
    return 1 if (changed or refused) else 0


def resolve(arg):
    p = pathlib.Path(arg)
    if not p.exists() and "/" not in arg and not arg.endswith(".md"):
        p = pathlib.Path("jons") / f"{arg}.md"
    return p


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "fix"):
        p = sub.add_parser(name)
        p.add_argument("stems", nargs="+", help="e.g. ONS_185, or jons/*.md")
        p.add_argument("-v", "--verbose", action="store_true",
                       help="print every line that changes")
    args = ap.parse_args(argv[1:])

    rc = 0
    for stem in args.stems:
        path = resolve(stem)
        if not path.exists():
            print(f"no such file: {path}")
            rc = max(rc, 2)
            continue
        rc = max(rc, process(path, args.verbose, args.cmd == "fix"))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
