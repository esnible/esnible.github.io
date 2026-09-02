# Repository conventions

## Git workflow

- Never push directly to `main`. This repo's history is meant to be a series of PR-linked commits (see the `(#NN)` suffixes in `git log`) — a direct push to `main` has no PR description attached to it, which breaks that record.
- Do work on a feature branch and commit locally, but **do not push the branch to GitHub**. Creating the branch and committing is fine without asking; pushing is not. Once the branch is committed and ready, stop and tell the user — they will ask for the PR when they want it, and the push happens then.
- Pushing follow-up commits to a branch that **already has an open PR** is fine without asking (e.g. addressing review comments). The rule is: never be the one to first publish a branch or open a PR.
- Do not open a pull request (`gh pr create` or otherwise) until the user explicitly asks for it. Let the user decide when a PR is merged.
