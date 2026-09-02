# Repository conventions

## Git workflow

- Never push directly to `main`. This repo's history is meant to be a series of PR-linked commits (see the `(#NN)` suffixes in `git log`) — a direct push to `main` has no PR description attached to it, which breaks that record.
- Do not open a pull request (`gh pr create` or otherwise) until the user explicitly asks for it. Let the user decide when a PR is merged.
- Pushing follow-up commits to a branch that **already has an open PR** is fine without asking (e.g. addressing review comments).
- Ask before starting a feature branch and committing locally.
