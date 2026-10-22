#!/usr/bin/env python3
"""Find foreign-script OCR garble in `jons/` Markdown files and help locate +
render the corresponding PDF page so it can be read visually.

pdfmd's `--lang eng+ara` pass reads Arabic, Devanagari, and Chinese-character
legends about as well as it reads bordered tables -- which is to say, not at
all reliably. Three failure shapes show up in this corpus:

  1. A raw run of non-Latin codepoints left sitting in otherwise-English
     prose or in a line pdfmd mistook for a heading (IS_004 line 92 before
     this was fixed: `# \\| كبر شأه em  eA  po  kj,ix`).
     Nothing marks these -- they just look like noise.
  2. A `<!-- OCR: ... -->` placeholder a previous pass already left, saying
     the source PDF is needed -- without anyone having actually opened it.
     68 of the corpus's ~148 `<!-- OCR: -->` comments mention script/legend/
     translit/mirror/glyph keywords and are candidates for a second look now
     that this skill exists.
  3. The same legend read as *Latin* letters rather than as script, so a
     codepoint test cannot see it at all (ONS_158 line 199:
     `<(^ ^,>4JU / ^\\ ^^\\y J / **diij-oooi ( o b v )**`). That is the LATIN
     verdict below -- a lead, not a verdict, and kept out of the exit status.
  4. The same again, but with the Latin letters too sparse for LATIN's
     consecutive-run test and the carets heaped up instead (ONS_159 line 442:
     `Obverse in the field AJ Ay;, *^/o^^j* AUI/ÜI AJI ^/j`). That is the
     CARET verdict -- also a lead, also out of the exit status. 145 of them
     in 35 files, against LATIN's 79 in 31.

Usage:
    detect_script_garble.py screen IS_001 [IS_002 ...]     # Tier 0
    detect_script_garble.py locate IS_004 --line 92        # Tier 1a
    detect_script_garble.py render IS_004 --page 4                 # Tier 1b
    detect_script_garble.py spellcheck "اکبر شاه"           # Tier 2 helper
    detect_script_garble.py check-markers [ONS_140 ...]     # verify figure/script page=N markers

Requires PyMuPDF (no OCR/vision libraries -- reading the render is a job for
a vision-capable model, not this script) and, for `spellcheck`, `cspell` on
PATH (npm install --global cspell -- see fix-ocr's own setup).
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24.3
except ImportError:  # older PyMuPDF only exposes the legacy `fitz` name
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        sys.exit(f"missing dependency: {exc}. Needs PyMuPDF.")

# ONS_ARCHIVE_DIR overrides the default checkout-relative path -- set it when
# the ons-website PDFs live somewhere else on this machine (they come from
# the private esnible/ons-website repo, not this one, so the path varies).
PDF_DIR = pathlib.Path(
    os.environ.get("ONS_ARCHIVE_DIR", "~/personal/src/ons-website/static/archive")
).expanduser()
if not PDF_DIR.is_dir():
    print(f"warning: PDF archive {PDF_DIR} does not exist -- set ONS_ARCHIVE_DIR "
          "to the ons-website static/archive checkout", file=sys.stderr)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MD_DIR = REPO_ROOT / "jons"
CSPELL_CONFIG = REPO_ROOT / "cspell.config.yaml"

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
MARKER_RE = re.compile(r"<!--\s*script-(ok|deferred|guess)\b(?:[^>]*?reason=(.*?))?\s*-->")

MIN_CHARS = 2  # shorter runs are lone stray glyphs -- fix-ocr's job (delete), not a transcription job


# --- the LATIN verdict -------------------------------------------------------
# pdfmd does not always leave an Arabic legend as Arabic codepoints. On plenty
# of pages it reads the script as Latin letters and punctuation instead --
# ONS_158 line 199 came out `<(^ ^,>4JU / ^\ ^^\y J / **diij-oooi ( o b v )**`
# -- and a codepoint test is structurally blind to that. That file screened
# clean while five body-text legends sat in it untranscribed.
#
# A bare "run of unpronounceable tokens" test is not usable as a replacement.
# Measured across the corpus it flags 1,642 lines, and ~88% of them belong to
# somebody else: 923 already carry real codepoints (RAW has them), 336 are
# Latin-Extended -- either legitimate diacritics (`Nasir al-din Mahmud` with
# its macrons) or broken-cmap mojibake -- 133 are C0 control bytes from a dead
# font cmap (that is issue #222's defect, with a different remedy), and 53 are
# Cyrillic bibliography, which is not a defect at all.
#
# Three things narrow it to something workable:
#
#   * tokens of those other kinds never count towards a run, so a mojibake run
#     stops qualifying while a correctly accented word merely ends a run;
#   * the noisy tokens must be a real share of the line, not four in eighty,
#     which is what ordinary prose throws up by chance;
#   * a side label or a gloss -- `Obv.`/`Rev.`, `legend`, `(= `, "Which means"
#     -- must sit within one content line, because that is how a coin legend is
#     printed here, and it is also what makes a reading corroborable
#     (`script-ok`) rather than a guess.
#
# That leaves 80 lines across 32 files, around four in five of them real. It is
# a lead and never a verdict, so LATIN is reported but deliberately kept out of
# the exit status -- the same way detect_figures treats UNCOVERED and RULED.
# A file whose only finding is LATIN still screens clean.

# Characters that mark a token as some *other* defect, so it neither counts as
# noise nor is worth reporting here: C0 controls and Latin-Extended (dead font
# cmap, or a real diacritic), Cyrillic, box-drawing (a flattened table drawn in
# ASCII art), and the fraction/superscript/AE notation this corpus uses for
# denominations and metals, which is correct text.
LATIN_OTHER_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\u00c0-\u024f\u1e00-\u1eff\u0400-\u04ff"
    "\u2500-\u257f\u00bc-\u00be\u00b9\u00b2\u00b3\u2070-\u209f\u2150-\u215f"
    "\u00c6\u00e6]"
)
LATIN_NOISE_CHARS = set("^\\<>\u00b1\u00ab\u00bb\u00ac\u00b0\u00b7\u2022")
LATIN_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\u2019-]*[.,;:)?!]?$")
LATIN_PUNCT_RE = re.compile(r"^[-\u2013\u2014/()\[\]{},.;:'\"*_]+$")
# The side labels and glosses a printed legend sits beside. `o b v` catches the
# letter-spaced form pdfmd produces when it reads `(obv)` off a scan.
LATIN_GLOSS_RE = re.compile(
    r"\(=\s|which means|\bobv\b|\brev\b|\bobverse\b|\breverse\b|\blegend\b|"
    r"\binscription\b|\bcountermark\b|\bo\s+b\s+v\b|\br\s+e\s+v\b",
    re.I,
)
LATIN_MIN_RUN = 4       # consecutive noise tokens, punctuation skipped over
LATIN_MIN_DENSITY = 0.15  # share of the line's countable tokens that are noise
LATIN_GLOSS_WINDOW = 1  # content lines each side that may carry the gloss

# --- the CARET verdict -------------------------------------------------------
# The LATIN run test needs four *consecutive* noise tokens, and a legend read
# as Latin does not reliably give it four: ONS_159 line 442 is
# `Obverse in the field AJ Ay;, *^/o^^j* AUI/ÜI AJI ^/j`, where `AJ` and `AJI`
# read as ordinary words and `AUI/UEI` carries a Latin-Extended `Ü`, so the run
# breaks twice and the line screens clean with an Arabic legend in it.
#
# What that line does have is carets in a heap. Measured over the corpus's
# 5,978 carets, nearest-neighbour distance is strongly bimodal: 47.1% have
# another caret within 9 characters, 34.4% sit 100+ characters from the next
# one, and the middle is nearly empty. The two humps are two different
# defects. An *isolated* caret is usually a footnote marker or a lost
# diacritic -- of ONS_158's 137 carets, resolved one by one off the page, 69
# were superscript digits, `<sup>` markers, letters or a question mark, and
# only ~56 were Arabic -- which is why this test requires a cluster and
# `fix-ocr/scripts/detect_marker_noise.py` owns the singletons.
#
# A cluster is CARET_MIN carets with no more than CARET_GAP characters between
# neighbours. The gap sits in the dead zone between the humps, so it is not a
# tuned number: 15, 25 and 40 all land within 3% of each other.
CARET_GAP = 25
CARET_MIN = 3


def _latin_token_kind(tok):
    t = tok.strip("*_`")
    if not t or LATIN_PUNCT_RE.match(t):
        return "skip"  # a `/` between a legend's lines must not break the run
    if LATIN_OTHER_RE.search(t) or FOREIGN_RE.search(t):
        return "clean"
    if any(c in LATIN_NOISE_CHARS for c in t):
        return "noise"
    if LATIN_WORD_RE.match(t) or re.search(r"\d", t):
        return "clean"
    return "noise" if len(t) <= 6 else "clean"


def _latin_line_is_noisy(stripped):
    """True when the line carries a dense run of Latin gibberish."""
    tokens = stripped.split()
    if len(tokens) < LATIN_MIN_RUN:
        return False
    run = best = noisy = counted = 0
    for tok in tokens:
        kind = _latin_token_kind(tok)
        if kind == "skip":
            continue
        counted += 1
        if kind == "noise":
            run += 1
            noisy += 1
        else:
            run = 0
        best = max(best, run)
    if counted < LATIN_MIN_RUN or best < LATIN_MIN_RUN:
        return False
    return noisy / counted >= LATIN_MIN_DENSITY


def _caret_cluster(stripped):
    """(size, start, end) of the longest run of carets <= CARET_GAP apart."""
    offs = [i for i, c in enumerate(stripped) if c == "^"]
    best = (0, 0, 0)
    run = []
    for k, off in enumerate(offs):
        run = run + [off] if k and off - offs[k - 1] <= CARET_GAP else [off]
        if len(run) > best[0]:
            best = (len(run), run[0], run[-1])
    return best


def _caret_snippet(stripped, start, end, width=100):
    """The line around the cluster, not its first `width` characters.

    A LATIN line is noise end to end, so its first 100 characters are a fair
    sample of it. A caret cluster is often a short burst a long way into a
    paragraph of ordinary English, and the first 100 characters of that line
    show the reviewer nothing at all.
    """
    pad = max(0, (width - (end - start + 1)) // 2)
    lo, hi = max(0, start - pad), min(len(stripped), end + 1 + pad)
    return (("..." if lo else "") + stripped[lo:hi]
            + ("..." if hi < len(stripped) else ""))


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
    """Return (comment_candidates, raw_candidates, latin_candidates,
    caret_candidates, resolved, deferred, guessed) as lists/sets of 0-based
    line indices, each with a reason string."""
    comment_candidates, raw_candidates = [], []
    latin_pre = []   # noisy lines, before the gloss-window test below
    caret_pre = []   # caret clusters, likewise
    content = []     # (index, stripped) for every non-blank, non-marker line
    resolved, deferred, guessed = set(), set(), set()
    marker_bucket = {"ok": resolved, "deferred": deferred, "guess": guessed}
    prev_content_idx = None
    # table_block: the run of pipe-table-row indices actively being built (a
    # genuine gap -- a blank line or other content -- ends it, same as real
    # GFM table syntax). last_table_block: the most recently *finished* run,
    # kept around through blank lines so a marker separated from its table by
    # one (GitHub's renderer wants that separation -- see the rect= note)
    # still resolves every row in it, not just the last one. Real new content
    # (not blank, not a marker) clears both, so a marker further down the
    # file can't reach back past unrelated lines to an old table.
    table_block = []
    last_table_block = []
    for i, line, in_code in _strip_fenced(lines):
        stripped = line.strip()
        if not stripped:
            if table_block:
                last_table_block = table_block
                table_block = []
            continue
        m = MARKER_RE.search(line)
        if m:
            target = prev_content_idx
            if target is not None:
                bucket = marker_bucket[m.group(1)]
                if table_block and table_block[-1] == target:
                    bucket.update(table_block)
                elif last_table_block and last_table_block[-1] == target:
                    bucket.update(last_table_block)
                else:
                    bucket.add(target)
            continue
        content.append((i, stripped))
        if in_code:
            prev_content_idx = i
            table_block = []
            last_table_block = []
            continue

        is_table_row = stripped.startswith("|")
        if is_table_row and table_block and table_block[-1] == prev_content_idx:
            table_block.append(i)
        elif is_table_row:
            table_block = [i]
        else:
            table_block = []
            last_table_block = []

        oc = OCR_COMMENT_RE.search(line)
        if oc and COMMENT_KEYWORDS.search(oc.group(0)):
            comment_candidates.append((i, oc.group(0)[:100]))

        # Foreign-script runs *outside* any HTML comment on the line -- an
        # OCR comment already documents the ones inside comments; a run
        # sitting bare in rendered prose is the undocumented case.
        visible = re.sub(r"<!--.*?-->", "", line)
        has_foreign = False
        for run in FOREIGN_RE.findall(visible):
            if len(run) >= MIN_CHARS:
                raw_candidates.append((i, stripped[:100]))
                has_foreign = True
                break

        # A line RAW already owns is not a LATIN finding -- reporting it twice
        # would just inflate the count. Nor is a pipe-table row, an IAL, or a
        # line carrying a marker comment: a figure marker's prose reads as
        # noise to this test and is not a legend.
        reportable = (not has_foreign and not is_table_row
                      and not stripped.startswith("{:")
                      and "<!--" not in stripped)
        if reportable and _latin_line_is_noisy(stripped):
            latin_pre.append((i, stripped[:100]))
        # A line LATIN already has is not reported twice; the whole point of
        # this test is the legends its consecutive-run requirement drops.
        elif reportable:
            size, lo, hi = _caret_cluster(stripped)
            if size >= CARET_MIN:
                caret_pre.append((i, _caret_snippet(stripped, lo, hi)))

        prev_content_idx = i

    # The gloss may be on the legend's own line (`Obv. ... Rev. ...`) or in the
    # paragraph beside it -- a legend set on its own line with "Which means ..."
    # under it is the commonest shape in this corpus.
    at = {idx: k for k, (idx, _) in enumerate(content)}

    def with_gloss(pre):
        out = []
        for i, why in pre:
            k = at.get(i)
            if k is None:
                continue
            lo = max(0, k - LATIN_GLOSS_WINDOW)
            hi = min(len(content), k + LATIN_GLOSS_WINDOW + 1)
            if any(LATIN_GLOSS_RE.search(content[j][1]) for j in range(lo, hi)):
                out.append((i, why))
        return out

    return (comment_candidates, raw_candidates, with_gloss(latin_pre),
            with_gloss(caret_pre), resolved, deferred, guessed)


def cmd_screen(args):
    needs_attention = False
    for stem in args.stems:
        pdf_path, md_path = resolve(stem)
        if not md_path.exists():
            print(f"{stem}: no Markdown at {md_path}")
            continue
        lines = md_path.read_text(encoding="utf-8").splitlines()
        (comment_c, raw_c, latin_c, caret_c,
         resolved, deferred, guessed) = find_candidates(lines)
        handled = resolved | deferred | guessed

        def open_items(cands):
            return [(i, why) for i, why in cands if i not in handled]

        open_comment = open_items(comment_c)
        open_raw = [] if args.no_raw else open_items(raw_c)
        open_latin = [] if args.no_latin else open_items(latin_c)
        open_caret = [] if args.no_caret else open_items(caret_c)
        # LATIN and CARET are leads, not verdicts -- around one in five and
        # around one in eight respectively is something else -- so neither
        # ever counts towards "to review" or the exit status. A file whose
        # only findings are leads still screens clean.
        n_open = len(open_comment) + len(open_raw)
        if n_open:
            needs_attention = True
        status = "nothing outstanding" if not n_open else f"{n_open} to review"
        leads = ""
        if latin_c and not args.no_latin:
            leads += f", {len(latin_c)} latin run(s)"
        if caret_c and not args.no_caret:
            leads += f", {len(caret_c)} caret cluster(s)"
        print(
            f"{stem}: {len(comment_c)} flagged comment(s), {len(raw_c)} raw run(s){leads} | "
            f"RESOLVED {len(resolved)}  GUESSED {len(guessed)}  DEFERRED {len(deferred)} -- {status}"
        )
        # GUESSED lines are content-added-but-unverified -- surface them every
        # run, not just under -v, so a "plausible guess" doesn't quietly
        # become the permanent reading nobody double-checks.
        for i in sorted(guessed):
            print(f"  GUESS    md line {i + 1}: {lines[i].strip()[:100]!r}")
        for i, why in open_comment:
            print(f"  COMMENT  md line {i + 1}: {why!r}")
        for i, why in open_raw:
            print(f"  RAW      md line {i + 1}: {why!r}")
        for i, why in open_latin:
            print(f"  LATIN    md line {i + 1}: {why!r}")
        for i, why in open_caret:
            print(f"  CARET    md line {i + 1}: {why!r}")
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


# The `page=N` markers check-markers verifies -- figure and script-ok/guess/
# deferred. N is the 0-based PDF page index (what `render --page` takes),
# never the printed folio or a 1-based count. table-ok/deferred use the same
# convention but are skipped: they sit after the table they retire, beside the
# next page's text, so nearby words point at the wrong page. detect_tables.py
# `screen` is the check for those.
PAGE_MARKER_RE = re.compile(
    r"<!--\s*(figure|script-ok|script-guess|script-deferred)\s+page=(\d+)")


def cmd_check_markers(args):
    """Check that each `page=N` marker sits next to text found on PDF page N.

    Scores pages by distinctive words (5+ letters) from the marker line and a
    few lines around it, counting only words that occur on at most
    --max-pages pages so boilerplate doesn't vote. Verdicts:
      ok        page N scores at least as well as any other page
      OFF-BY-1  page N-1 beats page N -- the marker was written 1-based or
                from the printed folio
      MISMATCH  some other page wins
      RANGE     N is past the last page (certainly not 0-based)
      weak      too little matching text to judge either way
    """
    stems = args.stems or sorted(p.stem for p in MD_DIR.glob("*.md"))
    counts = {}
    flagged = False
    for stem in stems:
        pdf_path, md_path = resolve(stem)
        if not pdf_path.exists() or not md_path.exists():
            continue
        lines = md_path.read_text(encoding="utf-8").splitlines()
        marks = [(i, m.group(1), int(m.group(2)))
                 for i, line in enumerate(lines) for m in PAGE_MARKER_RE.finditer(line)]
        if not marks:
            continue
        doc = fitz.open(pdf_path)
        texts = [page.get_text().lower() for page in doc]
        for i, kind, n in marks:
            words = _distinctive_words(lines, i, window=args.window)
            words = {w for w in words
                     if 0 < sum(w in t for t in texts) <= args.max_pages}
            scores = [sum(w in t for w in words) for t in texts]
            if n >= len(texts):
                verdict = "RANGE"
            else:
                top = max(scores)
                if top < args.min_hits:
                    verdict = "weak"
                elif scores[n] >= top:
                    verdict = "ok"
                elif n >= 1 and scores[n - 1] == top:
                    verdict = "OFF-BY-1"
                else:
                    verdict = "MISMATCH"
            counts[verdict] = counts.get(verdict, 0) + 1
            if verdict in ("OFF-BY-1", "MISMATCH", "RANGE") or (args.verbose and verdict == "weak"):
                flagged = flagged or verdict != "weak"
                best = max(range(len(texts)), key=lambda p: scores[p])
                here = scores[n] if n < len(texts) else "-"
                print(f"{verdict:8} {stem}:{i + 1}  {kind} page={n}  "
                      f"(page {n} scored {here}, best page {best} scored {scores[best]})")
    print("summary: " + "  ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    sys.exit(1 if flagged else 0)


def cmd_spellcheck(args):
    """Check a guessed reading against the corpus's cspell config (ar/fa-ir
    dictionaries + islamic/chinese/indian-numismatics word lists). Used to
    fill in a script-guess marker's `spellcheck=` field -- this does not
    decide whether a guess is *correct*, only whether its words are already
    known vocabulary, which is one input to how much to trust the guess."""
    text = " ".join(args.text) if args.text else sys.stdin.read()
    # cspell silently reports "0 files checked" for a path outside the repo
    # (e.g. the system /tmp) -- the scratch file has to live inside the repo
    # tree for cspell to see it at all.
    fd, tmp_path = tempfile.mkstemp(suffix=".md", dir=str(MD_DIR), prefix=".spellcheck_scratch_")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        result = subprocess.run(
            ["cspell", "--config", str(CSPELL_CONFIG), "--no-progress", tmp_path],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        sys.exit("cspell not found on PATH -- npm install --global cspell (see fix-ocr's own setup)")
    finally:
        pathlib.Path(tmp_path).unlink(missing_ok=True)
    unknown = re.findall(r"Unknown word \((.+?)\)", result.stdout + result.stderr)
    if unknown:
        print(f"fail:{','.join(unknown)}")
        sys.exit(1)
    print("pass")
    sys.exit(0)


def default_render_path(stem, page, dpi, clip):
    """Name a render after exactly what it shows, so parallel agents never share
    a path unless they want the identical image -- in which case sharing it is
    harmless. A fixed name like /tmp/p.png lets one agent's page overwrite
    another's between the write and the Read."""
    name = f"p{page}-{dpi}"
    if clip:
        name += "-" + "_".join(str(round(v)) for v in clip)
    return pathlib.Path(tempfile.gettempdir()) / "ons-render" / stem / f"{name}.png"


def cmd_render(args):
    pdf_path, _ = resolve(args.stem)
    doc = fitz.open(pdf_path)
    page = doc[args.page]
    clip = fitz.Rect(*args.clip) if args.clip else None
    out = pathlib.Path(args.out) if args.out else default_render_path(args.stem, args.page, args.dpi, args.clip)
    out.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=args.dpi, clip=clip).save(str(out))
    print(f"saved {out} (page {args.page}, dpi {args.dpi}{', clipped' if clip else ''})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("screen")
    p.add_argument("stems", nargs="+")
    p.add_argument("--no-raw", action="store_true", help="skip raw foreign-run detection, comment-flagged only")
    p.add_argument("--no-latin", action="store_true",
                   help="skip the LATIN leads (script pdfmd read as Latin gibberish)")
    p.add_argument("--no-caret", action="store_true",
                   help="skip the CARET leads (script pdfmd read as a heap of carets)")
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("locate")
    p.add_argument("stem")
    p.add_argument("--line", type=int, required=True, help="1-based md line number of the candidate")
    p.add_argument("--window", type=int, default=4, help="md lines each side to pull distinctive words from")
    p.set_defaults(func=cmd_locate)

    p = sub.add_parser("check-markers", help="verify figure/script-* page=N markers point at the right 0-based PDF page")
    p.add_argument("stems", nargs="*", help="default: every jons/*.md")
    p.add_argument("--window", type=int, default=4, help="md lines each side to pull distinctive words from")
    p.add_argument("--max-pages", type=int, default=3, help="ignore words found on more PDF pages than this")
    p.add_argument("--min-hits", type=int, default=2, help="best page needs this many hits to judge")
    p.add_argument("-v", "--verbose", action="store_true", help="also list weak (unjudgeable) markers")
    p.set_defaults(func=cmd_check_markers)

    p = sub.add_parser("spellcheck")
    p.add_argument("text", nargs="*", help="the guessed reading (or pipe it via stdin)")
    p.set_defaults(func=cmd_spellcheck)

    p = sub.add_parser("render")
    p.add_argument("stem")
    p.add_argument("--page", type=int, required=True, help="0-based PDF page index")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--clip", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--out", help="default: $TMPDIR/ons-render/<STEM>/p<PAGE>-<DPI>[-<CLIP>].png -- read the path it prints")
    p.set_defaults(func=cmd_render)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
