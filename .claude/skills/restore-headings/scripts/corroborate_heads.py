#!/usr/bin/env python3
"""Settle `detect_section_heads.py`'s `*-OPEN` findings against the scan.

`GLUED-END-OPEN` and `GLUED-BOTH-OPEN` are reported and never applied, for
one reason: the prose before the head does not close a sentence, so the cut
might sever one. That is a question about the page, and the page can answer
it -- which is what this does, without a render and without a human.

For each finding it asks the PDF text layer whether the head stands on a
short line of its own:

  CONFIRMED          on its own line and marked (capitals or bold). A head.
  OWN-LINE           on its own line, unmarked. Phase A of the ONS_243 sweep
                     established this is decisive on its own: an 8-to-27
                     character line standing alone is a head whatever the
                     mark test says.
  SUSPECT-CONTENTS   matched a line that ends in a page number, so the match
                     is probably a contents entry on another page rather
                     than the head. See the warning below.
  UNMARKED           a matching line exists, long, and unmarked.
  NO-LINE            no line matches. Usually means the text layer folded
                     the head the same way the Markdown did, which no
                     page-geometry screen can see; a render settles it.
  TEXT-LAYER-BROKEN  `get_text()` returns control characters. ONS_160 to
                     ONS_185 have a broken ToUnicode map, so every
                     text-layer screen in this repo is blind on them.

No pixmap is taken, so there is no underline probe: newsletters from
ONS_131 on print their heads bold with no underline at all, and for the
earlier issues a `NO-LINE` or `UNMARKED` verdict should be read as "not
settled here" rather than "not a head".

**The match can land on the wrong page.** `locate_in_pdf` searches every
page and takes the best ratio, so a head that also appears in the issue's
own contents listing can match that instead of itself. ONS_189's `Other
News` matched `Other news 4` on page 32 while the real head sits on page 4;
the finding was right and the evidence was not. The page-number test catches
that shape, but read the report rather than trusting the rows blindly.

Usage:
    corroborate_heads.py report ONS_189 [ONS_191 ...]   # the table above
    corroborate_heads.py rows   ONS_189 [ONS_191 ...]   # stem<TAB>line
    corroborate_heads.py report --all

`rows` emits only CONFIRMED and OWN-LINE, and feeds
`detect_section_heads.py fix --corroborated`.

Requires PyMuPDF. ONS_ARCHIVE_DIR must point at the PDF archive.
"""
import argparse
import os
import pathlib
import importlib.util
import re
import sys

SD = pathlib.Path(__file__).resolve().parent
MD_DIR = SD.parents[3] / "jons"
PDF_DIR = pathlib.Path(os.environ.get(
    "ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")).expanduser()

OPEN_VERDICTS = ("GLUED-END-OPEN", "GLUED-BOTH-OPEN")
SETTLED = ("CONFIRMED", "OWN-LINE")
OWN_LINE_MAX = 40          # longest a line may be and still read as a head
GARBAGE_MAX = 40           # control characters in the first pages before the
                           # text layer is judged unusable


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SD / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def settle(stem, dh, ds, fitz):
    md = MD_DIR / f"{stem}.md"
    if not md.exists():
        return [], f"{stem}: no Markdown at {md}"
    found = [f for f in ds.analyse(md.read_text(encoding="utf-8").split("\n"))
             if f["verdict"] in OPEN_VERDICTS]
    if not found:
        return [], None
    pdf = PDF_DIR / f"{stem}.pdf"
    if not pdf.exists():
        return [(f, "NO-PDF", "") for f in found], None

    pdf_lines = []
    with fitz.open(pdf) as doc:
        garbage = sum(1 for p in doc[:3] for ch in p.get_text()[:400]
                      if ord(ch) < 32 and ch not in "\n\t\r")
        if garbage > GARBAGE_MAX:
            return [(f, "TEXT-LAYER-BROKEN", "") for f in found], None
        for pno, page in enumerate(doc, start=1):
            lines = dh.visual_lines(page)
            dh.mark_set_apart(lines, dh.GAP, dh.WIDTH, True)
            dh.score_bold_reliability(lines, dh.BOLD_NOISE)
            for ln in lines:
                ln["page"] = pno
            pdf_lines.extend(lines)

    out = []
    for f in found:
        hit = dh.locate_in_pdf(pdf_lines, f["text"], 0.80)
        if hit is None:
            out.append((f, "NO-LINE", ""))
            continue
        ln, ratio = hit
        # The underline probe is deliberately switched off; see the docstring.
        mark = dh.is_head({**ln, "underline": 0.0, "margin": 0.0},
                          9.9, 9.9, dh.BOLD)
        detail = (f"p{ln['page']} {mark or 'plain':10s} "
                  f"bold={ln.get('bold', 0.0):4.2f} len={len(ln['text']):3d} "
                  f"{ln['text'][:46]!r}")
        if re.search(r"[\s.,;)]\d{1,3}\s*$", ln["text"]):
            out.append((f, "SUSPECT-CONTENTS", detail))
        elif len(ln["text"]) <= OWN_LINE_MAX:
            out.append((f, "CONFIRMED" if mark else "OWN-LINE", detail))
        else:
            out.append((f, "MARKED" if mark else "UNMARKED", detail))
    return out, None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("report", "rows"))
    ap.add_argument("stems", nargs="*", metavar="ONS_189")
    ap.add_argument("--all", action="store_true",
                    help="every .md file in jons/")
    args = ap.parse_args()

    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError as exc:
            sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")
    if not PDF_DIR.is_dir():
        sys.exit(f"PDF archive {PDF_DIR} does not exist -- set ONS_ARCHIVE_DIR")

    dh, ds = _load("detect_headings"), _load("detect_section_heads")
    stems = list(args.stems)
    if args.all:
        stems += sorted(p.stem for p in MD_DIR.glob("*.md"))

    tally, rows = {}, []
    for stem in stems:
        results, err = settle(stem, dh, ds, fitz)
        if err:
            print(err, file=sys.stderr)
            continue
        for f, verdict, detail in results:
            tally[verdict] = tally.get(verdict, 0) + 1
            if args.cmd == "rows":
                if verdict in SETTLED:
                    rows.append(f"{stem}\t{f['row'] + 1}\t{verdict}\t"
                                f"{f['text']}")
            else:
                print(f"{stem:8s} line {f['row'] + 1:5d} {f['verdict']:16s} "
                      f"{f['text']:28s} {verdict:17s} {detail}")
    if args.cmd == "rows":
        print("\n".join(rows))
    else:
        print("\n== " + "  ".join(f"{k} {v}" for k, v in
                                 sorted(tally.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
