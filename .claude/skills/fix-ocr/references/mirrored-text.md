# Mirrored text: every word spelled backwards

*A `fix-ocr` reference.* Read it when `detect_mirrored_text.py scan` reports a
hit. The Hard constraints, Workflow and Verification steps that govern every
fix here are in [`../SKILL.md`](../SKILL.md) — which is also where an *above*
or a *below* in the text points, wherever this file does not hold what it
names.

```
scripts/detect_mirrored_text.py scan ONS_100
scripts/detect_mirrored_text.py scan jons/*.md
```

On a few pages pdfmd read the text layer mirrored. It still found the lines
and still kept the words in their printed order, but transcribed each one
letter-for-letter backwards:

```
dna \_ niJ taerg liated dna dehsilbup 5 ynaM tnereiffd
-> and ... in great detail and published as many different
```

**Why this needs a script rather than an eye.** It does not look
recoverable. `dehsilbup` reads as pure noise, so a pass sees it, correctly
judges it un-guessable under the Hard constraints -- too long to delete,
forbidden to invent -- reports it as residual garble, and calls the file
done. That is exactly how ONS_100 passed a full pass and stayed broken. The
text was recoverable the whole time.

cspell does not rescue you. It flags most of the run, which is how the pass
knew the words were unknown, but it cannot say *why*, and a few reversed
words are real tokens forwards -- `dna` matches DNA, and `ynaM` and `niJ`
pass too -- so even a zero-unknowns gate leaves some behind.

**Repairing it.** Word order is preserved, so the decode is per-token, not a
reversal of the whole line. Punctuation travels with the word and has to be
moved back by hand (`,gnitseretni` -> `interesting,`), and digits are not
reversed at all (`th6` for `6th`, `6581` for `1856`), which is why the
script reports rather than rewrites. Two further things to expect:

- **pdfmd often lays the mirrored run out as a pipe table.** Rebuilding that
  into prose changes the line count, so it falls outside this skill's
  line-break invariant -- it is a `restructure-flattened-md` repair that
  happens to be triggered here.
- **Text next to the run may simply be missing.** Both ONS_029 and IS_029
  lost their quotation's opening clause entirely, and ONS_053's fragment
  lost its heading block. Restore from the render, and check the sentence
  actually starts somewhere.

Mark the repair with an `<!-- OCR: ... -->` note saying the passage was
mirrored and naming the page it was restored from. Describe the garble
rather than quoting it, or the quoted tokens become cspell unknowns of their
own.
