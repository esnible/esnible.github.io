# Repository conventions

## Git workflow

- Never push directly to `main`. Always create a feature branch and push that. This repo's history is meant to be a series of PR-linked commits (see the `(#NN)` suffixes in `git log`) — a direct push to `main` has no PR description attached to it, which breaks that record.
- Do not open a pull request (`gh pr create` or otherwise) until the user explicitly asks for it. Creating the branch, committing, and pushing the branch is fine without asking; once the branch is pushed and ready, stop and tell the user — they will ask for the PR when they want it. Let the user decide when a PR is merged.
