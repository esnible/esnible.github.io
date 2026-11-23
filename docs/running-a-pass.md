# Running a pass over a file

`docs/skill-list.md` says which skill to reach for and in what order. This
page is about the other half: how to spend a pass's budget, because a single
file's `screens.tsv` row can cost anywhere from a few thousand tokens to well
over a million depending on how the work is arranged, and the arrangement
matters more than the number of findings does.

Two measurements frame everything below, both from `jons/ONS_171`:

- The six subagent readers on the `ll`-family pass cost **258k tokens
  between them**. The main thread cost **~1.5-1.6M**.
- Eighteen crop sheets carrying every finding on that pass came to about
  **27k image tokens**, none of it in the deciding context.

So the images were never the problem. The deciding context was, and it was
full of text that had been pulled into it for no better reason than that it
was convenient to print.

## Why the main thread is the expensive place

Cost is quadratic in transcript length, not linear in tool calls. Each
assistant turn re-reads the whole accumulated prefix, so a fat tool result in
turn 5 of a 35-turn pass is paid for thirty times, not once. A 10k-token
command output is not a 10k-token decision; it is closer to 300k.

That single fact drives the rest of this page. Everything here is a way of
keeping something out of the deciding context, or of getting it out again
once it has served its purpose.

## Eye reads go in subagents

The turns that need to look at a page are not the turns that need to hold the
file. Split them.

1. **Build one worklist with the Markdown-only screens first.** Those cost
   nothing to run and they are what decide which pages are worth opening.
2. **Turn it into stacked crop sheets** —
   `.claude/skills/shared/crop_sheets.py sheets <STEM> --rows rows.tsv`, about
   five findings to a sheet. ONS_162's 65 findings came to 11 sheets.
3. **Dispatch readers in parallel**, giving each the sheet paths, the rows
   file, and a strict reply format: `L<line> <old> => <new>`, `OK`, or `?`.
   Tell them to report pixels, not to reason from what a name "should" be,
   and that `?` beats a guess.
4. **Keep the deciding in the main context.** The reader says what the scan
   shows; the pass decides what to write.

A whole-page render goes to a subagent too, for the questions a crop cannot
answer: whether a block is complete, how a table is ruled, which footnote
digit is printed.

Two readers on the same token is cheap and worth it for anything that changes
a word corpus-wide or restores a source typo. That is what settled ONS_162's
`Vosioka` and `[991AH]`.

## Verify with counts, never with a diff dump

A diff is the most expensive way to prove a change and among the weakest.
The worst single call on the ONS_171 pass was a closing
`git diff --word-diff`: **10.8k tokens** to display two-letter changes buried
inside 2,000-character prose lines, after a line invariant and a substitution
tally had already proved the same thing for about 400.

Use these instead:

```sh
# the line invariant: structure did not move
git diff --no-index --numstat old.md new.md

# the substitution tally: every edit reconciled against its expected count
git diff -U0 | grep -oE "\[-[^]]*-\]\{\+[^}]*\+\}" | sort | uniq -c
```

The tally is not merely cheaper, it is better evidence. It reconciles each
class of edit against the count the worklist predicted, so the thing to read
in prose is the handful of sites where the count disagrees — not the whole
diff, which tells you only that something changed somewhere.

The same applies to a screen: measure the `screens.tsv` row with `rows`,
and check that the count moved rather than that one finding vanished from one
bucket.

## Build the inventory once

Put the candidate inventory in a `scratchpad/` file and address it by line
range from then on. The ONS_171 pass printed the same site list four
different ways — inventory, rows file, "exact spans", tally — about 8k tokens
of near-duplicate, all of it resident for every turn afterwards.

Batch exploratory greps, and batch the verification screens, into single
calls for the same reason.

## Group readers per article cluster, not per page range

Every reader carries a fixed startup cost: its own system prompt, plus a
brief that ran 1-1.8k tokens on that pass. Three of ONS_171's six readers
reached an identical verdict about the same article's typographic
conventions, which is three startups paid for one answer.

Cut the *number* of readers, not the detail of the brief. The long per-site
briefs earned their keep — they are what produced per-site verdicts and
caught a wrong reading that the worklist had carried forward.

## A handback is a claim, not a result

A subagent's summary is evidence about what it says it did, and nothing more.
On `ONS_164`'s `fix-ocr` pass a first background fork "completed" in about
three seconds with zero tool calls and an empty diff, reporting nothing wrong.
The retry did run — ~110 real edits and ~400 dictionary additions — and still:

- missed 3 of ~19 `coin`→`com` instances, including the book-title case
  `Com Finds`, which cspell cannot catch and only a manual
  `grep -noE '\b[Cc]oms?\b'` sweep turns up;
- claimed to have saved two findings to a memory file that was never touched;
- left a duplicate dictionary word (`Jotiswaroopa`) and unsorted stragglers
  from its second batch;
- "fixed" a diacritic mismatch in the wrong direction (see
  `docs/ocr-conventions.md`).

None of that was visible from the fork's own summary. Each needed cspell,
`grep`, `git diff --numstat` or a spot render re-run independently. Check the
counts after a handback, the same way you would check your own work — the
tally is cheap and the summary is free, which is exactly the problem.

## What is irreducible

The Hard constraints in `transcribe-foreign-script` and the fidelity rules in
`docs/ocr-conventions.md` mean an apostrophe, a macron or a footnote digit
cannot be written without someone having seen it printed. A defect class
spread over a dozen pages therefore needs per-site page evidence, and no
arrangement of the work makes that part cheaper. Roughly a third of the
ONS_171 spend was avoidable and it was concentrated in four or five calls;
the rest was the job.
