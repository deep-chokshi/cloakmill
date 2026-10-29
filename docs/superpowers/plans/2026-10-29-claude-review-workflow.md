# Claude Review Workflow Implementation Plan

> Superseded on 2026-10-29. The workflow, publisher script, schema, and tests this plan created were removed in favor of Anthropic's standard workflows; see [Claude code and security review](../../development/claude-review.md).

> **For agentic workers:** Use the executing-plans skill to implement this plan inline, with verification before committing.

**Goal:** Add automatic and manually rerunnable Claude reviews using an owner-supplied Actions secret.

**Architecture:** A single workflow validates PR metadata, checks out base and head snapshots, invokes the official action, and verifies that a result comment was published. Setup and operational limits belong in development documentation.

The initial implementation below is superseded by the structured-review revision in the design spec. The owner configured the API key; a live run exposed permission denials and no posted result. The revised implementation runs the bundled code and security commands, transfers structured results, and publishes through a separate job.

**Tech Stack:** GitHub Actions YAML, GitHub CLI, jq, official Claude Code Action, actionlint.

---

- [x] Create `.github/workflows/claude-review.yml` with `pull_request` and `workflow_dispatch` triggers, scoped token permissions, concurrency, a secret-presence check, and immutable target resolution.
- [x] Add pinned checkouts and the official Claude action. Limit the reviewer to source inspection and PR comments, specify prototype scope, and require an explicit result for the reviewed head.
- [x] Add `docs/development/claude-review.md` covering the exact secret, activation, manual PR selection, limits, and diagnosis. Link it from `docs/development/getting-started.md`.
- [x] Run `/private/tmp/cloakmill-review-setup/actionlint -shellcheck= .github/workflows/claude-review.yml`. Exercise metadata rejection and result-verification paths with synthetic inputs; do not call the paid API without the configured secret.
- [x] Run `make check` and `make build`; inspect the staged diff, commit, push, and open a separate draft setup PR. Inspect hosted CI and attach the PR to this chat.
- [x] Update the stale review monitor to recognize the new setup and report the remaining owner actions without treating silence or CI success as a completed review.

Local verification: actionlint 1.7.12 passed; 24 synthetic scenarios executed the actual workflow shell steps, covering target acceptance/rejection, missing/present secrets, explicit result requirements, and a head change during review. `make check` and `make build` passed. No live Anthropic review was attempted because the API secret was absent.

Delivery: [draft setup PR #2](https://github.com/deep-chokshi/cloakmill/pull/2). [Hosted CI](https://github.com/deep-chokshi/cloakmill/actions/runs/40766146908) passed on Python 3.12 and 3.13 for implementation commit `3241f97`. The Claude job correctly skipped the draft; this is not a live review result. The existing monitor's prompt now recognizes the setup PR and its owner-controlled activation, preserving its already-paused status.

## Structured-review revision

- [x] Write failing publisher and SDK-result regression tests, then implement the validated result collector and GitHub review publisher under `.github/scripts/`.
- [x] Run `/code-review` and `/security-review` separately using `--json-schema`, read-only analysis credentials, exact base/head context, and explicit prototype scope.
- [x] Transfer only structured findings to a separate PR-write job; publish a neutral review with validated inline anchors and fail on findings or incomplete results.
- [x] Run the publisher tests in foundation CI, update development documentation, and validate YAML, Python lint/format, tests, and build locally.
- [ ] Push the fix on PR #2 and verify a live rerun completes both review commands and publishes the current-head GitHub review. Verify findings against source and fix genuine defects before declaring the check clear.
