#!/usr/bin/env python3
"""Find foreign-script OCR garble in `jons/` Markdown files and help locate +
render the corresponding PDF page so it can be read visually.

pdfmd's `--lang eng+ara` pass reads Arabic, Devanagari, and Chinese-character
legends about as well as it reads bordered tables -- which is to say, not at
all reliably. Two failure shapes show up in this corpus:

  1. A raw run of non-Latin codepoints left sitting in otherwise-English
     prose or in a line pdfmd mistook for a heading (IS_004 line 92 before
     this was fixed: `# \\| كبر شأه em  eA  po  kj,ix`).
     Nothing marks these -- they just look like noise.
  2. A `<!-- OCR: ... -->` placeholder a previous pass already left, saying
     the source PDF is needed -- without anyone having actually opened it.
     68 of the corpus's ~148 `<!-- OCR: -->` comments mention script/legend/
     translit/mirror/glyph keywords and are candidates for a second look now
     that this skill exists.

Usage:
    detect_script_garble.py screen IS_001 [IS_002 ...]     # Tier 0
    detect_script_garble.py locate IS_004 --line 92        # Tier 1a
    detect_script_garble.py render IS_004 --page 4 --out /tmp/p.png   # Tier 1b

Requires PyMuPDF (no OCR/vision libraries -- reading the render is a job for
a vision-capable model, not this script).
"""
import argparse
import pathlib
import re
import sys

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover
    sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")

PDF_DIR = pathlib.Path("~/personal/src/ons-website/static/archive").expanduser()
MD_DIR = pathlib.Path(__file__).resolve().parents[4] / "jons"

# Unicode blocks for scripts that actually show up in this corpus (Arabic /
# Perso-Arabic legends, Devanagari numerals and legends, Chinese characters).
# Hebrew is included because it shares blocks with Arabic in some OCR fonts'
# confusion tables, not because the corpus discusses Hebrew coins.
SCRIPT_BLOCKS = {
    "Arabic": "؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿",
    "Hebrew": "֐-׿",
    "Devanagari": "ऀ-ॿ",
    "CJK": "一-鿿㐀-䶿",
}
FOREIGN_RE = re.compile("[" + "".join(SCRIPT_BLOCKS.values()) + "]+")

# Comments already left by a previous pass that are worth a second look now
# that rendering + a vision model are in scope. Deliberately narrower than
# "any <!-- OCR: -->" -- most of those are numeric image noise or maps/
# histograms that no amount of PDF-reading recovers as text, and are not
# this skill's problem.
COMMENT_KEYWORDS = re.compile(
    r"script|legend|translit|mirror|devanagari|nagari|"
    r"chinese charact|perso-arabic|glyph|calligra|hebrew",
    re.I,
)
OCR_COMMENT_RE = re.compile(r"<!--\s*OCR:.*?-->")
MARKER_RE = re.compile(r"<!--\s*script-(ok|deferred)\b(?:[^>]*?reason=(.*?))?\s*-->")

MIN_CHARS = 2  # shorter runs are lone stray glyphs -- fix-ocr's job (delete), not a transcription job


def resolve(stem):
    return PDF_DIR / f"{stem}.pdf", MD_DIR / f"{stem}.md"


def _strip_fenced(lines):
    """Yield (index, line, in_code) so callers can skip fenced code blocks."""
    in_code = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code = not in_code
            yield i, line, True
            continue
        yield i, line, in_code


def find_candidates(lines):
    """Return (comment_candidates, raw_candidates, resolved, deferred) as
    lists/sets of 0-based line indices, each with a reason string."""
    comment_candidates, raw_candidates = [], []
    resolved, deferred = set(), set()
    prev_content_idx = None
    for i, line, in_code in _strip_fenced(lines):
        stripped = line.strip()
        if not stripped:
            continue
        m = MARKER_RE.search(line)
        if m:
            target = prev_content_idx
            if target is not None:
                (resolved if m.group(1) == "ok" else deferred).add(target)
            continue
        if in_code:
            prev_content_idx = i
            continue

        oc = OCR_COMMENT_RE.search(line)
        if oc and COMMENT_KEYWORDS.search(oc.group(0)):
            comment_candidates.append((i, oc.group(0)[:100]))

        # Foreign-script runs *outside* any HTML comment on the line -- an
        # OCR comment already documents the ones inside comments; a run
        # sitting bare in rendered prose is the undocumented case.
        visible = re.sub(r"<!--.*?-->", "", line)
        for run in FOREIGN_RE.findall(visible):
            if len(run) >= MIN_CHARS:
                raw_candidates.append((i, stripped[:100]))
                break

        prev_content_idx = i

    return comment_candidates, raw_candidates, resolved, deferred


def cmd_screen(args):
    needs_attention = False
    for stem in args.stems:
        pdf_path, md_path = resolve(stem)
        if not md_path.exists():
            print(f"{stem}: no Markdown at {md_path}")
            continue
        lines = md_path.read_text(encoding="utf-8").splitlines()
        comment_c, raw_c, resolved, deferred = find_candidates(lines)

        def open_items(cands):
            return [(i, why) for i, why in cands if i not in resolved and i not in deferred]

        open_comment = open_items(comment_c)
        open_raw = [] if args.no_raw else open_items(raw_c)
        n_open = len(open_comment) + len(open_raw)
        if n_open:
            needs_attention = True
        status = "nothing outstanding" if not n_open else f"{n_open} to review"
        print(
            f"{stem}: {len(comment_c)} flagged comment(s), {len(raw_c)} raw run(s) | "
            f"RESOLVED {len(resolved)}  DEFERRED {len(deferred)} -- {status}"
        )
        for i, why in open_comment:
            print(f"  COMMENT  md line {i + 1}: {why!r}")
        for i, why in open_raw:
            print(f"  RAW      md line {i + 1}: {why!r}")
    sys.exit(1 if needs_attention else 0)


def _distinctive_words(lines, center, window=4, min_len=5):
    lo, hi = max(0, center - window), min(len(lines), center + window + 1)
    words = set()
    for line in lines[lo:hi]:
        for w in re.findall(r"[A-Za-z]{%d,}" % min_len, line):
            words.add(w.lower())
    return words


def cmd_locate(args):
    pdf_path, md_path = resolve(args.stem)
    lines = md_path.read_text(encoding="utf-8").splitlines()
    idx = args.line - 1
    words = _distinctive_words(lines, idx, window=args.window)
    if not words:
        sys.exit("no distinctive words found near that line -- widen --window")
    doc = fitz.open(pdf_path)
    scores = []
    for pno, page in enumerate(doc):
        text = page.get_text().lower()
        hits = sum(1 for w in words if w in text)
        if hits:
            scores.append((hits, pno))
    scores.sort(reverse=True)
    print(f"searched {len(words)} distinctive word(s): {', '.join(sorted(words))}")
    for hits, pno in scores[:5]:
        print(f"  page {pno} (0-based): {hits}/{len(words)} words matched")
    if not scores:
        print("  no page matched -- the surrounding text may itself be OCR garble; widen --window")


def cmd_render(args):
    pdf_path, _ = resolve(args.stem)
    doc = fitz.open(pdf_path)
    page = doc[args.page]
    clip = fitz.Rect(*args.clip) if args.clip else None
    page.get_pixmap(dpi=args.dpi, clip=clip).save(args.out)
    print(f"saved {args.out} (page {args.page}, dpi {args.dpi}{', clipped' if clip else ''})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("screen")
    p.add_argument("stems", nargs="+")
    p.add_argument("--no-raw", action="store_true", help="skip raw foreign-run detection, comment-flagged only")
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("locate")
    p.add_argument("stem")
    p.add_argument("--line", type=int, required=True, help="1-based md line number of the candidate")
    p.add_argument("--window", type=int, default=4, help="md lines each side to pull distinctive words from")
    p.set_defaults(func=cmd_locate)

    p = sub.add_parser("render")
    p.add_argument("stem")
    p.add_argument("--page", type=int, required=True, help="0-based PDF page index")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--clip", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_render)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
