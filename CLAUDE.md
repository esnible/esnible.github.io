# Repository conventions

## Git workflow

- Never push directly to `main`. Always create a feature branch, push it, and open a pull request via `gh pr create`. This repo's history is meant to be a series of PR-linked commits (see the `(#NN)` suffixes in `git log`) — a direct push to `main` has no PR description attached to it, which breaks that record.
- Let the user decide when a PR is merged; opening it is normally as far as you should go without being asked.
