# Repository conventions

## Git workflow

- Never push directly to `main`. This repo's history is meant to be a series of PR-linked commits (see the `(#NN)` suffixes in `git log`) — a direct push to `main` has no PR description attached to it, which breaks that record.
- Do not open a pull request (`gh pr create` or otherwise) until the user explicitly asks for it. Let the user decide when a PR is merged.
- Pushing follow-up commits to a branch that **already has an open PR** is fine without asking (e.g. addressing review comments).
- Ask before starting a feature branch and committing locally.

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
