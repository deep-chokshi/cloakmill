# Claude code and security review

CloakMill uses three of Anthropic's standard GitHub Actions workflows. They are
unchanged except for pinned versions, a Dependabot skip, and the settings
described below. All three bill to the repository's Anthropic API key.
None of them approves, blocks, or merges a pull request; they only post comments.

| Workflow | Runs when | What it does |
| --- | --- | --- |
| [claude-code-review.yml](../../.github/workflows/claude-code-review.yml) | A PR is opened, pushed to, reopened, or marked ready | Runs Anthropic's official `code-review` plugin, which posts an inline comment per verified issue or one summary comment when it finds none |
| [claude-security-review.yml](../../.github/workflows/claude-security-review.yml) | A PR is opened, pushed to, or reopened | Runs [`anthropics/claude-code-security-review`](https://github.com/anthropics/claude-code-security-review), which posts inline comments on vulnerable lines |
| [claude.yml](../../.github/workflows/claude.yml) | The owner, a member, or a collaborator mentions `@claude` in a PR comment, review comment, review, or issue | Claude answers in that thread, for example `@claude review` or `@claude explain this change` |

## Setup

1. The [Claude GitHub App](https://github.com/apps/claude) is installed on the
   repository. The `@claude` workflow authenticates as this app and replies as
   `claude[bot]`. Both review workflows post as `github-actions[bot]`.
2. The repository has an `ANTHROPIC_API_KEY` Actions secret from the
   [Claude Console](https://platform.claude.com). Use a secret, not a variable,
   and never paste the key into source, a PR, an issue, or chat.
3. `claude.yml` must be on the default branch, because GitHub always runs comment-triggered
   workflows from the default branch. Both review workflows also run on a PR that
   adds or edits them.

## What to expect

- **Code review runs once per PR.** The plugin stops when the PR already has a
  review comment from it, and it skips drafts, closed PRs, and trivial or
  automated changes. To review again after new pushes, comment `@claude review`. That
  comment is answered by `claude.yml`, a general Claude session rather than the
  plugin.
- **Code review runs in the foreground.** The action ends a run at the first
  result, so background subagents are killed and the job goes green with nothing
  posted ([issue 1499](https://github.com/anthropics/claude-code-action/issues/1499)).
  The workflow sets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` to prevent this, and it
  has write access so the review can post. A green check alone does not prove a
  review ran; look for Claude's comment.
- **Security review runs on every push.** The workflow sets
  `run-every-commit: true`. Without it the action scans a PR once, and a failed
  first scan blocks every later one. Findings it already posted are not posted
  again. Once a PR has any security comment the action posts nothing new, so read
  the check, not the comments.
- **Security model.** The action sets up Node 18, so npm installs Claude Code
  2.1.197, the last release that runs on it. That release rejects Claude Opus
  5.5, so the workflow sets `claude-model: claude-opus-5`, tracked upstream in
  [issue 152](https://github.com/anthropics/claude-code-security-review/issues/152).
  The action's own default, Claude Opus 4.1, is retired. Its extra Claude-based
  false-positive filter validates the key against another retired model and falls
  back to its rule-based filter, so findings may be noisier.
- **The security check goes red on findings.** The action reports success when
  its scan fails and can skip posting new findings, so the workflow's last step
  fails the job unless the scan completed with no findings. The
  `security-review-results` artifact holds the details.
- **`@claude` can change code.** `claude.yml` has `contents: write`, so a comment
  such as `@claude fix this` can push commits to the PR branch. Only users with
  write access can trigger it, and bot comments are ignored.
- **Project rules.** The code-review plugin checks changes against `CLAUDE.md`
  files. The root `CLAUDE.md` points to `AGENTS.md`, where CloakMill keeps its
  rules. Bug finding does not depend on them, but rule checking does, and it
  enforces whatever is written. Update `AGENTS.md` in the PR that changes a rule;
  the PR template has a reminder.
- **Dependabot PRs are skipped.** Dependabot runs receive no repository secrets.
- **Untrusted input.** The security action is not hardened against prompt
  injection, and both review workflows read PR content. Fork PRs get no secrets,
  so both reviews skip them, and their CI waits for a maintainer's approval.
  `claude.yml` has write access and the API key, so it refuses fork PRs. Review
  those by hand. Mentions from anyone else do not start Claude.

## Cost and data

Each PR normally uses one code review and one security review per push, and
each `@claude` comment starts another session. All of it bills to the API key; set
spend limits in the Claude Console. Actions are pinned to commit SHAs and
Dependabot proposes updates. The `code-review` plugin is installed from
Anthropic's marketplace at run time and is not pinned.

These development services send repository content to Anthropic. They do not
change CloakMill's intended offline runtime. Only synthetic data belongs in this
repository.

## Troubleshooting

| Symptom | Diagnosis |
| --- | --- |
| `@claude` gets no reply | The workflow must be on the default branch, the comment must contain `@claude`, and the commenter needs write access. |
| No code review on later pushes | The plugin reviews once per PR. Comment `@claude review`. |
| Code review is green but posted nothing | Check that `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is still on the action step. The plugin also stops silently on changes it judges trivial. `show_full_output: true` shows the reason. |
| Security check is red | Read the job's errors. Findings are in the `security-review-results` artifact. For "did not complete", read `claudecode-error.log`; "does not support this model" means the model is newer than the action's Claude Code accepts. |
| Authentication or billing failure | Check the key, its workspace, its credit, and account spend limits. |
| A `claude` check suite stays queued | That is the hosted Code Review service, which needs a Claude Team or Enterprise plan and is not enabled here. It does not affect these workflows. |

References: [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions),
[claude-code-action security](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md),
and [Claude Code security review](https://github.com/anthropics/claude-code-security-review).
