#!/usr/bin/env python3
"""Find the garble traces no other screen can see.

A *trace* is a literal character or short string pdfmd leaves behind where
the scan printed something else: a caret for a superscript footnote number,
a guillemet for a quotation mark it could not place, an escaped asterisk
closing a run of quote marks. They are listed in `../traces.tsv`, one per
line, and the list is meant to grow -- a new trace needs an entry, not a
code change.

`detect_quote_pairs.py` owns this corpus's OCR'd superscripts where they
came through as a run of quote marks (`14'''`, `425''`). But it anchors
every finding on a quote character, so a scan's superscript that arrived as
a bare caret with no quote mark near it is invisible to it, and the file
screens clean:

    In a forthcoming monograph^ I suggest that the reverse deities...
    Sikander 'Adil Shah surrendered to the Emperor.^ Thereafter he...

`transcribe-foreign-script`'s screen knows these glyphs too -- its
`LATIN_NOISE_CHARS` is `^\\<>±«»¬°·•` -- but both of its caret tests want
several of them at once, beside an `Obv.`/`Rev.` gloss: LATIN wants four
consecutive noise tokens at 15% of the line, and CARET wants three carets
within 25 characters of each other. Both are looking for a legend pdfmd read
as Latin. One caret in sixty words of English prose is not that -- and that
division is measured, not assumed: ONS_158's 137 carets, resolved one by one
off the page, came out 69 markers and diacritics to ~56 Arabic, so neither
screen can have the other's half. Nothing but this one reports the singletons.

## Shapes

Every occurrence gets a shape, and `traces.tsv` says which shapes count for
which trace:

- **MARKER** -- at a word's end. The scan prints a superscript footnote
  number; new work restores one as `<sup>6</sup>`, read off the page, exactly
  as for the `®` and `''` markers. What follows a marker is the rest of the
  document -- a new sentence, a quotation, a parenthesis, or just the next
  word, because a footnote reference falls wherever its claim ends
  (`Joe Cribb^ supported this view`, `Hodivala^ in a note on this`).
  Requiring a capital after it, as the first cut of this screen did, missed
  222 of these in 40 files.
- **GLYPH** -- between two letters, which is a letter or a diacritic the OCR
  lost: `Öl^er` for Ölçer, `ak^e` for akçe, `be^hk` for beşlik, `'O^ene'` for
  Ozene, `Weh-Andew^Sabuhr`, and in ONS_163 a whole file's worth of `\\>` for
  `y` (`Arab-B\\>zantine`, `Uma\\>\\>ad`, `b\\> telephone`).
- **LOOSE** -- every other position. This is the bucket the earlier,
  shape-only version of this screen had no name for, and it is where most of
  what it missed lived. ONS_155 screened clean carrying 18 of them:
  `fax: -^-^-33` for `++33` (a digit on both sides), `**YZD**^8.` for a
  footnote digit glued to its caret, `4^0` for `400`, `(Crusaders) ^
  Jerusalem` (a space in front), `*almati^,*` (a comma behind). None was a
  false positive the narrowness had bought.
- **WRECK** -- a hit sitting in a run of garble. Reported as a lead rather
  than counted: it is a legend pdfmd read as Latin, and it belongs to
  `transcribe-foreign-script`, not here.

## Settling a trace that is really printed

Some traces are genuinely on the page -- the corpus's own French and German
passages use guillemets, and `ONS_226` states a convention for angle
brackets. Once the scan has been read, record it inline so the screen stops
asking:

    <!-- glyph-ok « page=5 reason=the scan prints French guillemets round
    the author's own quoted term -->

`glyph-ok` settles every occurrence of the traces it names on its own line;
name several with commas (`glyph-ok «,»`), by the literal or by the name
`traces.tsv` gives it (`glyph-ok guillemet-open`). `glyph-deferred` is its
sibling for a trace that was looked at and could not be resolved -- it is
reported, like a WRECK, as a lead rather than a verdict, so the line stays on
a worklist without counting against a clean screen.

**This screen settles nothing by itself.** Which digit a marker was, and
which letter a glyph ate, are both readable only off the scan -- see
fix-ocr's Hard constraints -- so it writes no edits and emits no
`apply_edits.py` batch.

    detect_marker_noise.py scan ONS_158
    detect_marker_noise.py scan jons/*.md --all        # default-off shapes too
    detect_marker_noise.py scan ONS_155 --only=caret
    detect_marker_noise.py scan jons/*.md --skip=guillemet-open,guillemet-close
    detect_marker_noise.py rows ONS_158                # crop_sheets.py rows
    detect_marker_noise.py list                        # the trace table

A trace quoted inside an HTML comment is not reported -- the OCR skills quote
bad readings in their markers on purpose, and a screen that read them would
report its own evidence as the defect. The header counts them anyway
("3 hidden in comments"), because otherwise a trace could leave this screen
by being quoted in a marker's reason string rather than by being fixed.

Exit 0 when nothing is found, 1 otherwise (sibling-skill convention).
"""
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MD_DIR = REPO_ROOT / "jons"
TRACES_TSV = pathlib.Path(__file__).resolve().parent.parent / "traces.tsv"

SHAPES = ("MARKER", "GLYPH", "LOOSE")
# A marker is glued to what it annotates; what follows is the next word, a
# quotation, or a parenthesis. A letter straight after is a GLYPH instead.
MARKER_BEFORE = re.compile(r"[A-Za-z0-9)\]'\".,;:!?]\Z")
MARKER_AFTER = re.compile(r"\A\s+[\"'(*A-Za-z“]")
LETTER_BEFORE = re.compile(r"[A-Za-z]\Z")
LETTER_AFTER = re.compile(r"\A[A-Za-z]")
# Inline HTML and kramdown autolinks: `<br>` would otherwise read as a GLYPH
# every time a `<br>` separates two words (`legend.<br>Central`).
MARKUP_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>"
                       r"|<https?://[^>\s]*>"
                       r"|<[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+>")
# A `>` opening a line is a blockquote, not garble.
BLOCKQUOTE_RE = re.compile(r"^\s*>+")
# `<!-- glyph-ok «,» page=5 reason=... -->`, read off the raw text because
# `readable()` blanks the comment it lives in.
SETTLE_RE = re.compile(r"<!--\s*glyph-(ok|deferred)\s+(\S+)")
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


class Trace:
    """One row of `traces.tsv`."""

    def __init__(self, raw, name, shapes, note):
        self.raw, self.name, self.note = raw, name, note
        self.shapes = frozenset(SHAPES if shapes.strip() == "all" else
                                (s.strip().upper() for s in shapes.split(",")))
        bad = self.shapes - set(SHAPES)
        if bad:
            raise ValueError(f"{name}: unknown shape(s) {sorted(bad)}")
        if raw.startswith("re:"):
            self.body, self.literal = raw[3:], None
        else:
            # Only `\t` and `\\` are escapes, so the column can hold a tab.
            # Everything else is the literal text, non-ASCII included.
            self.literal = re.sub(r"\\(.)", lambda m: "\t" if m.group(1) == "t"
                                  else m.group(1), raw)
            self.body = re.escape(self.literal)
        # Runs collapse into one finding, and a kramdown escape in front of
        # the trace is part of it: `\^`, `^^`, `\>\>`.
        self.re = re.compile(rf"(?:\\?(?:{self.body}))+")

    def __str__(self):
        return self.literal if self.literal is not None else self.raw


def load_traces(path=TRACES_TSV):
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            raise SystemExit(f"{path}:{n}: want 4 tab-separated fields")
        out.append(Trace(*(p.strip() if i else p for i, p in enumerate(parts[:4]))))
    return out


def resolve(arg):
    p = pathlib.Path(arg)
    return p if p.suffix == ".md" else MD_DIR / f"{arg}.md"


def blank(text, pattern, flags=0):
    """Blank every match, keeping the file's offsets (and line numbers)."""
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                  text, flags=flags)


def quoted(text):
    """Comment *bodies* and fenced code blanked; `<!--` and `-->` kept.

    A trace in here is one somebody wrote down on purpose -- the OCR skills
    quote bad readings in their markers -- so it is not a defect. It is
    counted all the same, because otherwise a trace could leave this screen
    by being quoted in a marker's reason string rather than by being fixed.
    The delimiters stay visible so a comment's own `<` and `>` are not
    mistaken for something a person wrote down.
    """
    text = blank(text, r"(?<=<!--).*?(?=-->)", re.S)
    return blank(text, r"(?ms)^```.*?^```")


def readable(text):
    """The text with comments, fenced code and inline markup blanked out.

    Inline markup goes too, but it is structure rather than a hiding place:
    `<br>` would read as a GLYPH every time it separated two words
    (`legend.<br>Central`), and every `<sup>6</sup>` this skill writes would
    read as two angle-bracket traces.
    """
    text = blank(text, r"<!--.*?-->", re.S)
    text = blank(text, r"(?ms)^```.*?^```")
    text = blank(text, MARKUP_RE.pattern)
    return blank(text, r"(?m)" + BLOCKQUOTE_RE.pattern)


def wrecked(text, start, end):
    """True when the trace sits in a run of garble, not in English prose."""
    window = text[max(0, start - WRECK_WINDOW):end + WRECK_WINDOW]
    own = sum(text.count(c, start, end) for c in WRECK_CHARS)
    return sum(window.count(c) for c in WRECK_CHARS) - own >= WRECK_MIN


def shape_of(text, start, end):
    before, after = text[max(0, start - 1):start], text[end:end + 2]
    if LETTER_BEFORE.search(before) and LETTER_AFTER.match(after):
        return "GLYPH"
    if MARKER_BEFORE.search(before) and MARKER_AFTER.match(text[end:end + 3]):
        return "MARKER"
    return "LOOSE"


def settled_lines(raw, traces):
    """{line number: {trace: "SETTLED" or "DEFERRED"}}, keyed by name and literal."""
    by_name = {t.name: str(t) for t in traces}
    out = {}
    for m in SETTLE_RE.finditer(raw):
        line = raw.count("\n", 0, m.start()) + 1
        tag = "SETTLED" if m.group(1) == "ok" else "DEFERRED"
        for word in m.group(2).split(","):
            if word:
                out.setdefault(line, {})[by_name.get(word, word)] = tag
    return out


def findings(raw, traces, every=False):
    """[(offset, end, tag, trace, text)] sorted by offset.

    `tag` is a shape, or WRECK / SETTLED / DEFERRED. Only the shapes count.
    """
    text = readable(raw)
    unquoted = quoted(raw)
    settled = settled_lines(raw, traces)
    hidden = 0
    out = {}
    for trace in traces:
        for m in trace.re.finditer(raw):
            start, end = m.span()
            if unquoted[start:end] != raw[start:end]:   # quoted in a marker
                if shape_of(raw, start, end) in trace.shapes or every:
                    hidden += 1
                continue
            if text[start:end] != raw[start:end]:       # inline markup
                continue
            shape = shape_of(text, start, end)
            if shape not in trace.shapes and not every:
                continue
            line = raw.count("\n", 0, start) + 1
            vouched = settled.get(line, {})
            if str(trace) in vouched:
                tag = vouched[str(trace)]
            elif wrecked(text, start, end):
                tag = "WRECK"
            else:
                tag = shape
            out.setdefault(start, (start, end, tag, trace, m.group(0)))
    return [out[k] for k in sorted(out)], text, hidden


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def anchor_at(text, offset, end):
    """The words leading up to the trace, for `crop_sheets.py` to place.

    It stops at the trace: what follows a trace is often more garble, which
    is the last thing a page-matching anchor wants.
    """
    return " ".join(text[max(0, offset - 160):end].split())


def around(text, offset, end, before=46, after=14):
    """The trace with context on both sides, for a human reading the scan."""
    lo = text.rfind("\n", 0, offset) + 1
    hi = text.find("\n", end)
    hi = len(text) if hi < 0 else hi
    return " ".join(text[max(lo, offset - before):min(hi, end + after)].split())


def reported(found):
    """The findings that count: a WRECK or a settled trace is not a verdict."""
    return [f for f in found if f[2] in SHAPES]


def cmd_scan(path, traces, every=False, quiet_clean=False):
    raw = path.read_text(encoding="utf-8")
    found, text, hidden = findings(raw, traces, every)
    counts = {}
    for f in found:
        counts[f[2]] = counts.get(f[2], 0) + 1
    live = reported(found)
    if not live and not found and not hidden:
        if not quiet_clean:
            print(f"{path.stem}: no garble traces")
        return 0
    notes = [f"{counts[t]} settled" for t in ("SETTLED",) if counts.get(t)]
    if hidden:
        notes.append(f"{hidden} hidden in comments")
    leads = [f"{counts[t]} {t.lower()} lead(s)"
             for t in ("WRECK", "DEFERRED") if counts.get(t)]
    head = f"{path.stem}: {len(live)} trace(s)"
    if notes:
        head += " | " + ", ".join(notes)
    if leads:
        head += " | " + ", ".join(leads)
    print(head)
    for off, end, tag, trace, hit in found:
        if tag == "SETTLED":
            continue
        print(f"  {tag:8} {trace.name:15} md line {line_of(text, off)}: "
              f"{around(text, off, end)!r}")
    return 1 if live else 0


def cmd_rows(path, traces, every=False):
    """`file<TAB>label<TAB>anchor`, the form `shared/crop_sheets.py` takes.

    Leads are left out: a WRECK goes to `transcribe-foreign-script`, which
    renders the whole legend rather than one glyph.
    """
    raw = path.read_text(encoding="utf-8")
    found, text, _ = findings(raw, traces, every)
    rows = [f"{path.stem}\t{tag} {trace.name} line {line_of(text, off)}"
            f"\t{anchor_at(text, off, end)}"
            for off, end, tag, trace, _hit in reported(found)]
    print("\n".join(rows))
    return 1 if rows else 0


def cmd_list(traces):
    for t in traces:
        print(f"{str(t):10} {t.name:16} {','.join(sorted(t.shapes)).lower():18}"
              f" {t.note[:60]}")
    return 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    flags = [a for a in argv[1:] if a.startswith("-")]
    every = "--all" in flags or "--angles" in flags   # --angles: old spelling
    picked = {v for f in flags if f.startswith("--only=")
              for v in f[len("--only="):].split(",")}
    skipped = {v for f in flags if f.startswith("--skip=")
               for v in f[len("--skip="):].split(",")}
    bad = [f for f in flags if f not in ("--all", "--angles")
           and not f.startswith(("--only=", "--skip="))]
    if not args or args[0] not in ("scan", "rows", "list") or bad:
        print(__doc__)
        return 2
    traces = load_traces()
    if picked:
        traces = [t for t in traces if t.name in picked or str(t) in picked]
        if not traces:
            print(f"no trace matches --only={','.join(sorted(picked))}",
                  file=sys.stderr)
            return 2
    traces = [t for t in traces if t.name not in skipped and str(t) not in skipped]
    if args[0] == "list":
        return cmd_list(traces)
    if len(args) < 2:
        print(__doc__)
        return 2
    rc = 0
    for arg in args[1:]:
        path = resolve(arg)
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            rc = max(rc, 2)
            continue
        if args[0] == "rows":
            rc = max(rc, cmd_rows(path, traces, every))
        else:
            rc = max(rc, cmd_scan(path, traces, every, quiet_clean=len(args) > 2))
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:          # piped into `head`, which is expected
        sys.exit(1)
