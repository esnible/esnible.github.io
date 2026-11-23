# Repository conventions

## Git workflow

- Never push directly to `main`. This repo's history is meant to be a series of PR-linked commits (see the `(#NN)` suffixes in `git log`) — a direct push to `main` has no PR description attached to it, which breaks that record.
- Do not open a pull request (`gh pr create` or otherwise) until the user explicitly asks for it. Let the user decide when a PR is merged.
- Pushing follow-up commits to a branch that **already has an open PR** is fine without asking (e.g. addressing review comments).
- Ask before starting a feature branch and committing locally.

## Commits

- Every commit carries two trailers, sign-off first:

  ```
  Signed-off-by: Ed Snible <esnible@acm.org>
  Co-Authored-By: Claude <model> <noreply@anthropic.com>
  ```

- The **author** email is `esnible@acm.org` too — pass
  `--author="Ed Snible <esnible@acm.org>"` rather than relying on
  `git config`, which on some checkouts holds a stale address. Every commit
  on `main` is authored that way. Sign-off emails in older history alternate
  between two addresses, so `git log` alone is ambiguous; `acm.org` is the
  answer.

## Working the `jons/` OCR corpus

- `docs/skill-list.md` — which skill owns which defect, and the order to run
  them in.
- `docs/running-a-pass.md` — how to arrange a pass so it doesn't cost a
  million tokens: eye reads go in subagents, **verify with counts and
  tallies, never with a diff dump**, build the candidate inventory once.
- `docs/ocr-conventions.md` — what a reading gets written back under:
  fidelity to the source, footnote apparatus, masthead structure.
- `docs/pdf-sources.md` — which issues are born-digital rather than scanned,
  and what that changes.
