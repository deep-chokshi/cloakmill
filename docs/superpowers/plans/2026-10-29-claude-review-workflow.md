# Claude Review Workflow Implementation Plan

> **For agentic workers:** Use the executing-plans skill to implement this plan inline, with verification before committing.

**Goal:** Add automatic and manually rerunnable Claude reviews using an owner-supplied Actions secret.

**Architecture:** A single workflow validates PR metadata, checks out base and head snapshots, invokes the official action, and verifies that a result comment was published. Setup and operational limits belong in development documentation.

**Tech Stack:** GitHub Actions YAML, GitHub CLI, jq, official Claude Code Action, actionlint.

---

- [x] Create `.github/workflows/claude-review.yml` with `pull_request` and `workflow_dispatch` triggers, scoped token permissions, concurrency, a secret-presence check, and immutable target resolution.
- [x] Add pinned checkouts and the official Claude action. Limit the reviewer to source inspection and PR comments, specify prototype scope, and require an explicit result for the reviewed head.
- [x] Add `docs/development/claude-review.md` covering the exact secret, activation, manual PR selection, limits, and diagnosis. Link it from `docs/development/getting-started.md`.
- [x] Run `/private/tmp/cloakmill-review-setup/actionlint -shellcheck= .github/workflows/claude-review.yml`. Exercise metadata rejection and result-verification paths with synthetic inputs; do not call the paid API without the configured secret.
- [ ] Run `make check` and `make build`; inspect the staged diff, commit, push, and open a separate draft setup PR. Inspect hosted CI and attach the PR to this chat.
- [ ] Update the stale review monitor to recognize the new setup and report the remaining owner actions without treating silence or CI success as a completed review.

Local verification: actionlint 1.7.12 passed; 24 synthetic scenarios executed the actual workflow shell steps, covering target acceptance/rejection, missing/present secrets, explicit result requirements, and a head change during review. `make check` and `make build` passed. No live Anthropic review was attempted because the API secret was absent.
