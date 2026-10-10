#!/usr/bin/env python3
"""Triage `%` in the jons/ corpus: real percentage, or an OCR'd fraction glyph?

`pdfmd` reads the fraction glyphs (1/2, 1/4, 3/4) as `%`, which no spellcheck
pass can catch -- `%` is a real character, and a token like `%4` looks like an
ordinary digit-bearing word. See ONS_104 (fixed by hand) for the pattern.

The source PDFs carry their own text layer from a SECOND, INDEPENDENT OCR pass
(whoever scanned the originals). It garbles fractions differently than pdfmd
did, and the two garbles do not collide:

    markdown   text layer   reading
    %4         14           1/4
    %          V2 / Vi      1/2
    %          1/4 / 1/2    (clean -- some scans kept the glyph)

So the text layer corroborates, for free, what would otherwise need a 300-dpi
page render per occurrence. It is NOT authoritative -- it is a second OCR with
its own errors (`tample` for `temple`) -- so this script only ever PROPOSES,
and marks anything it cannot decode for a human to render.

    python3 triage_percent.py                       # whole corpus
    python3 triage_percent.py ONS_104 ONS_078       # named stems
    python3 triage_percent.py --verdict FRACTION    # one bucket only
    python3 triage_percent.py --edits out.txt       # apply_edits.py batch

Verdicts:
    PERCENTAGE  the text layer shows a percent sign too -- leave alone
    URL         the `%` is percent-encoding inside a URL -- never edit
    GARBLE      the line is wrecked foreign-script debris, not prose --
                belongs to transcribe-foreign-script, not to this pass
    FRACTION    text layer decoded from a legible glyph; reading proposed
    WEAK        decoded from a dropped fraction bar (`14`) -- confirm first
    UNSURE      text layer found but its token is not in the decode table
    NOANCHOR    layer present but the phrase was not found -- render the page
    NOLAYER     the PDF has no text layer at all -- render the page
    NOPDF       the source PDF is not in ONS_ARCHIVE_DIR -- not assessed
"""
import argparse
import difflib
import glob
import os
import pathlib
import re
import sys

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError as exc:
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")

PDF_DIR = pathlib.Path(
    os.environ.get("ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")
).expanduser()
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MD_DIR = REPO_ROOT / "jons"

# How the originals' OCR pass renders each fraction glyph. Keys are matched
# case-sensitively against the token standing where the markdown has `%`.
# Only unambiguous forms belong here -- anything else should fall to UNSURE
# and get a render rather than a guess.
# How the originals' OCR pass renders each fraction glyph. Keys are matched
# against the token standing where the Markdown has `%`.
#
# DECODE holds readings that are legible on their face: the glyph survived
# intact, or the substitution is unambiguous (`V2` has no other reading).
DECODE = {
    "½": "½", "V2": "½", "Vi": "½", "Vz": "½", "'/2": "½", "1/2": "½",
    "l/2": "½", "y2": "½", "Yi": "½", "V-2": "½", "»/2": "½", "V&": "½",
    "¼": "¼", "1/4": "¼", "V4": "¼", "'/4": "¼", "l/4": "¼", "Va": "¼",
    "¾": "¾", "3/4": "¾", "%4": "¼",
    "⅓": "⅓", "1/3": "⅓", "⅔": "⅔", "2/3": "⅔", "⅛": "⅛", "1/8": "⅛",
}

# DECODE_WEAK holds readings that rest on an inference rather than a glyph:
# the fraction bar dropped out and the two digits ran together (`14` for ¼,
# `12` for ½). The mechanism is real -- ONS_104's `14` was confirmed against
# the page -- but `12` could equally be the number twelve under a slipped
# alignment, so these are reported separately and want a render or a
# plausibility check (weights, the article's own heading) before applying.
DECODE_WEAK = {
    "14": "¼", "12": "½", "34": "¾", "13": "⅓", "23": "⅔", "18": "⅛",
}

# Tokens that mean "this really is a percent sign" if the layer agrees.
PERCENT_TOKENS = {"%"}

# Below this share of the Markdown line's words matched on the page, the
# alignment is not trustworthy -- report NOANCHOR and let a human render,
# rather than propose a reading from a bad match.
MIN_RATIO = 0.55


def md_files(stems):
    if stems:
        return [MD_DIR / f"{s}.md" for s in stems]
    return sorted(pathlib.Path(p) for p in glob.glob(str(MD_DIR / "*.md")))


URL_RX = re.compile(r"(?:https?://|www\.|ftp://)\S+")

# A `%` standing as a column unit rather than a quantity: `| Copper % | Tin % |`
# heads an alloy-analysis table. The digit rule below cannot see these, because
# a word, not a number, precedes the sign.
UNIT_RX = re.compile(r"[A-Za-z]{3,}\s*%\s*(?:\||$)")


def is_unit_header(line, pos):
    if not line.lstrip().startswith("|"):
        return False
    return any(m.start() <= pos < m.end() for m in UNIT_RX.finditer(line))


def is_garble(line):
    """True when the line is a wrecked foreign-script region, not prose.

    `%` inside one of these is debris from the same wreck, not a fraction
    glyph: the line belongs to transcribe-foreign-script, not here. Measured
    on the share of characters that are neither ASCII text nor ordinary
    Markdown punctuation.
    """
    body = line.strip()
    if len(body) < 20:
        return False
    odd = sum(1 for c in body if not (32 <= ord(c) < 127) or c in "\\^`~")
    return odd / len(body) > 0.18


def url_spans(line):
    """Character ranges covered by URLs -- `%` there is percent-encoding."""
    return [(m.start(), m.end()) for m in URL_RX.finditer(line)]


def is_percentage(line, pos):
    """A digit immediately before `%` (allowing one space) means a percentage."""
    return bool(re.search(r"[\d.]\s?$", line[:pos]))


def _norm(tok):
    """Fold a token for alignment: case and punctuation differ between passes."""
    return re.sub(r"[^a-z0-9]", "", tok.lower())


class Layer:
    """The source PDF's own text layer, flattened to one string per page.

    Flattening matters: `pdfmd` joins a scan's physical lines into Markdown
    paragraphs, while the text layer keeps the hard line breaks. An anchor
    phrase that straddles a layer line break therefore matches no single
    layer line, but does match the flattened page. The scan's own line-wrap
    hyphens are stitched back up on the way (`light-\\nweight` -> `lightweight`,
    kept also as `light- weight` so either spelling can anchor).
    """

    def __init__(self, stem):
        self.pages = []       # (page_no, flattened text)
        self.has_layer = False
        path = PDF_DIR / f"{stem}.pdf"
        if not path.exists():
            self.missing = True
            return
        self.missing = False
        doc = pymupdf.open(path)
        for i in range(doc.page_count):
            raw = doc[i].get_text()
            if not raw.strip():
                continue
            flat = re.sub(r"-\n(?=\w)", "-", raw)      # keep the hyphen, drop the break
            flat = re.sub(r"\s+", " ", flat).strip()
            self.pages.append((i, flat))
        doc.close()
        self.has_layer = bool(self.pages)

    def align(self, md_line):
        """Align a Markdown line to its best-matching page, by word sequence.

        Regex anchoring on a few neighbouring words is not safe here: the two
        OCR passes disagree often enough that a short anchor silently matches
        some *other* place on the page, and the captured token is then a word
        fragment (`ha%e`, `%age`) rather than the fraction slot. Aligning the
        whole line with difflib instead makes the match auditable -- a low
        ratio is visible and can be rejected.

        Returns (page_no, md_tokens, page_tokens, opcodes, ratio) or None.
        """
        md_toks = md_line.split()
        if len(md_toks) < 4:
            return None
        norm_md = [_norm(t) for t in md_toks]
        best = None
        for page, text in self.pages:
            pg_toks = text.split()
            if not pg_toks:
                continue
            sm = difflib.SequenceMatcher(
                None, norm_md, [_norm(t) for t in pg_toks], autojunk=False)
            # Coverage of the MD LINE, not difflib's symmetric ratio: a 50-word
            # line against a 600-word page tops out near 0.15 on ratio(), which
            # says nothing about whether the line was found.
            matched = sum(b.size for b in sm.get_matching_blocks())
            cov = matched / len(norm_md)
            if not best or cov > best[4]:
                best = (page, md_toks, pg_toks, sm.get_opcodes(), cov)
        return best

    def token_at(self, alignment, md_index):
        """The layer token standing where md_tokens[md_index] stands."""
        page, md_toks, pg_toks, opcodes, ratio = alignment
        for tag, i1, i2, j1, j2 in opcodes:
            if not (i1 <= md_index < i2):
                continue
            if tag == "equal":
                j = j1 + (md_index - i1)
            elif tag == "replace":
                # proportional slot inside the replaced run
                span = max(i2 - i1, 1)
                j = j1 + min(j2 - j1 - 1, (md_index - i1) * (j2 - j1) // span)
            else:                      # delete: md token has no counterpart
                j = min(j1, len(pg_toks) - 1)
            if 0 <= j < len(pg_toks):
                lo, hi = max(0, j - 6), min(len(pg_toks), j + 7)
                return pg_toks[j], " ".join(pg_toks[lo:hi])
        return None


def triage(stems):
    rows = []
    for md in md_files(stems):
        if not md.exists():
            print(f"warning: {md} not found", file=sys.stderr)
            continue
        stem = md.stem
        layer = None
        for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            line = line.rstrip("\n")
            urls = url_spans(line)
            in_url = lambda i: any(a <= i < b for a, b in urls)
            garbled = is_garble(line)
            slots = []
            for m in re.finditer("%", line):
                if in_url(m.start()):
                    rows.append((stem, n, "URL", "", "", line, None, m.start()))
                elif is_unit_header(line, m.start()):
                    rows.append((stem, n, "PERCENTAGE", "", "", line, None, m.start()))
                elif garbled:
                    rows.append((stem, n, "GARBLE", "", "", line, None, m.start()))
                else:
                    # Everything else goes to the text layer, INCLUDING a `%`
                    # with a digit in front. That shortcut is not safe on its
                    # own: `7% Skar` is the Tibetan 7½ skar and `8% x 11 ins.`
                    # is a paper size, both of which it would wave through as
                    # percentages. The digit rule survives only as the
                    # fallback when alignment fails.
                    slots.append(m.start())
            if not slots:
                continue
            if layer is None:
                layer = Layer(stem)
            if not layer.has_layer:
                v = "NOPDF" if layer.missing else "NOLAYER"
                for pos in slots:
                    rows.append((stem, n, v, "", "", line, None, pos))
                continue
            al = layer.align(line)
            if not al or al[4] < MIN_RATIO:
                for pos in slots:
                    v = "PERCENTAGE" if is_percentage(line, pos) else "NOANCHOR"
                    rows.append((stem, n, v, "", "", line,
                                 al[0] if al else None, pos))
                continue
            page, md_toks, _pg, _ops, ratio = al
            # character offset -> token index, for each fraction slot
            offs, acc = [], 0
            for t in md_toks:
                i = line.index(t, acc)
                offs.append((i, i + len(t)))
                acc = i + len(t)
            for pos in slots:
                idx = next((k for k, (a, b) in enumerate(offs) if a <= pos < b), None)
                if idx is None:
                    rows.append((stem, n, "NOANCHOR", "", "", line, page, pos))
                    continue
                got = layer.token_at(al, idx)
                if not got:
                    v = "PERCENTAGE" if is_percentage(line, pos) else "NOANCHOR"
                    rows.append((stem, n, v, "", "", line, page, pos))
                    continue
                tok, ctx = got
                clean = tok.strip(".,;:()[]'\"")
                # `7½ Skar`, `(8½ x 11` -- the layer kept the glyph with its
                # leading digits attached. The Markdown `%` is that glyph.
                glyph = re.fullmatch(r"[^\w]*([\d.,]*)([½¼¾⅓⅔⅛])[^\w]*", clean)
                if glyph:
                    rows.append((stem, n, "FRACTION", clean, glyph.group(2),
                                 line, page, pos))
                elif clean in DECODE:
                    rows.append((stem, n, "FRACTION", clean, DECODE[clean], line, page, pos))
                elif clean in DECODE_WEAK:
                    rows.append((stem, n, "WEAK", clean, DECODE_WEAK[clean], line, page, pos))
                elif clean in PERCENT_TOKENS or re.fullmatch(r"[\d.,]*%[\d.,]*", clean):
                    rows.append((stem, n, "PERCENTAGE", clean, "", line, page, pos))
                elif is_percentage(line, pos) and not re.search(r"[½¼¾⅓⅔⅛]", clean):
                    # digit in front and the layer shows no fraction glyph
                    rows.append((stem, n, "PERCENTAGE", clean, "", line, page, pos))
                else:
                    rows.append((stem, n, "UNSURE", tok, "", line, page, pos))
    return rows


def excerpt(line, width=100):
    return line.strip()[:width]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stems", nargs="*", help="file stems, e.g. ONS_104 (default: all)")
    ap.add_argument("--verdict", help="show only this verdict")
    ap.add_argument("--edits", metavar="PATH",
                    help="write FRACTION rows as an apply_edits.py batch")
    ap.add_argument("--quiet", action="store_true", help="summary only")
    args = ap.parse_args()

    if not PDF_DIR.is_dir():
        print(f"warning: PDF archive {PDF_DIR} does not exist -- set "
              "ONS_ARCHIVE_DIR to the ons-website static/archive checkout",
              file=sys.stderr)

    rows = triage(args.stems)
    counts = {}
    for r in rows:
        counts[r[2]] = counts.get(r[2], 0) + 1

    if not args.quiet:
        cur = None
        for stem, n, verdict, tok, reading, line, page, pos in rows:
            if args.verdict and verdict != args.verdict:
                continue
            if verdict == "PERCENTAGE" and not args.verdict:
                continue
            if stem != cur:
                print(f"\n=== {stem} ===")
                cur = stem
            where = f"p{page}" if page is not None else "--"
            note = f"{tok!r} -> {reading}" if reading else (f"{tok!r} ?" if tok else "")
            print(f"  {n:5}  {verdict:10} {where:4} {note}")
            print(f"         {excerpt(line)}")

    if args.edits:
        outdir = pathlib.Path(args.edits)
        outdir.mkdir(parents=True, exist_ok=True)
        # group by (file, line): several fractions can share one line, and
        # apply_edits.py wants a single old => new per line.
        per_line, order = {}, []
        for stem, n, verdict, tok, reading, line, page, pos in rows:
            if verdict != "FRACTION":
                continue
            key = (stem, n)
            if key not in per_line:
                per_line[key] = (line, [])
                order.append(key)
            per_line[key][1].append((pos, reading))
        written = {}
        for key in order:
            stem, n = key
            line, subs = per_line[key]
            new_line = line
            # right to left, so earlier offsets stay valid
            for pos, reading in sorted(subs, reverse=True):
                end = pos + 1
                # `%4 rupee` -> `¼ rupee`: the stray 4 is part of the glyph
                if reading in "¼¾" and line[end:end + 1] == "4":
                    end += 1
                elif reading == "½" and line[end:end + 1] == "2":
                    end += 1
                start = pos
                # `¥%` is a doubled misread of the one glyph
                if line[max(0, pos - 1):pos] == "¥":
                    start -= 1
                new_line = new_line[:start] + reading + new_line[end:]
            written.setdefault(stem, []).append((n, line, new_line))
        for stem, items in written.items():
            path = outdir / f"{stem}.txt"
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"# {stem}: {len(items)} fraction glyph(s) read from "
                         f"the source PDF text layer\n")
                fh.write("# REVIEW EACH LINE, then:\n")
                fh.write(f"#   python3 apply_edits.py jons/{stem}.md "
                         f"{path} --write\n")
                for n, old_line, new_line in sorted(items):
                    fh.write(f"# line {n}\n{old_line} => {new_line}\n")
        print(f"\nwrote {len(written)} batch file(s) to {outdir}/", file=sys.stderr)

    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
