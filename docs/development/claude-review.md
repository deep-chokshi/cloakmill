# Claude code and security review

CloakMill uses three of Anthropic's standard GitHub Actions workflows, unchanged
except for pinned versions and a Dependabot skip. All three bill to the
repository's Anthropic API key. None of them approves, blocks, or merges a pull
request; they only post comments.

| Workflow | Runs when | What it does |
| --- | --- | --- |
| [claude-code-review.yml](../../.github/workflows/claude-code-review.yml) | A PR is opened, pushed to, reopened, or marked ready | Runs Anthropic's official `code-review` plugin, which posts an inline comment per verified issue or one summary comment when it finds none |
| [claude-security-review.yml](../../.github/workflows/claude-security-review.yml) | A PR is opened, pushed to, or reopened | Runs [`anthropics/claude-code-security-review`](https://github.com/anthropics/claude-code-security-review), which posts inline comments on vulnerable lines |
| [claude.yml](../../.github/workflows/claude.yml) | A PR comment, review comment, review, or issue mentions `@claude` | Claude answers in that thread, for example `@claude review` or `@claude explain this change` |

## Setup

1. The [Claude GitHub App](https://github.com/apps/claude) is installed on the
   repository. The code review and `@claude` workflows authenticate as this app.
2. The repository has an `ANTHROPIC_API_KEY` Actions secret from the
   [Claude Console](https://platform.claude.com). Use a secret, not a variable,
   and never paste the key into source, a PR, an issue, or chat.
3. The workflows must be on `main`. Until they are:
   - `@claude` comments get no reply, because GitHub always runs comment-triggered
     workflows from the default branch.
   - The code review job on the PR that adds or edits its workflow logs
     "Action skipped due to workflow validation". The app's token exchange only
     trusts workflow files that match `main`.
   - The security review already runs on that PR.

## What to expect

- **Code review runs once per PR.** The plugin stops when Claude has already
  commented on the PR, and it skips drafts, closed PRs, and trivial or automated
  changes. To review again after new pushes, comment `@claude review`. That
  comment is answered by `claude.yml`, a general Claude session rather than the
  plugin.
- **Security review runs once per PR.** Later pushes are skipped by the action's
  cache. Setting `run-every-commit: true` scans every push, at more cost and with
  more false positives.
- **Security model.** The action's built-in default, Claude Opus 4.1, is retired,
  so the workflow sets `claude-model: claude-opus-5-5`. The action's extra
  Claude-based false-positive filter validates the key against a retired model
  and falls back to its rule-based filter, so its findings may be noisier.
- **`@claude` can change code.** `claude.yml` has `contents: write`, so a comment
  such as `@claude fix this` can push commits to the PR branch. Only users with
  write access can trigger it, and bot comments are ignored.
- **Project rules.** The code-review plugin checks changes against `CLAUDE.md`
  files. CloakMill keeps its rules in `AGENTS.md`, which the plugin does not read.
- **Dependabot PRs are skipped.** Dependabot runs receive no repository secrets.
- **Untrusted input.** The security action is not hardened against prompt
  injection, and both review workflows read PR content. Run them only on PRs from
  trusted contributors; the repository is private and forks get no secrets.

## Cost and data

Each PR normally uses one code review and one security review, and each
`@claude` comment starts another session. All of it bills to the API key; set
spend limits in the Claude Console. Actions are pinned to commit SHAs and
Dependabot proposes updates. The `code-review` plugin is installed from
Anthropic's marketplace at run time and is not pinned.

These development services send repository content to Anthropic. They do not
change CloakMill's intended offline runtime. Only synthetic data belongs in this
repository.

## Troubleshooting

| Symptom | Diagnosis |
| --- | --- |
| `@claude` gets no reply | The workflow must be on `main`, the comment must contain `@claude`, and the commenter needs write access. |
| Code review logs "Action skipped due to workflow validation" | Expected on a PR that adds or edits the workflow. It works after the change reaches `main`. |
| No code review on later pushes | The plugin reviews once per PR. Comment `@claude review`. |
| Security review skipped on later pushes | The action's per-PR cache. Expected unless `run-every-commit` is on. |
| Authentication or billing failure | Check the key, its workspace, its credit, and account spend limits. |
| A `claude` check suite stays queued | That is the hosted Code Review service, which needs a Claude Team or Enterprise plan and is not enabled here. It does not affect these workflows. |

References: [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions),
[claude-code-action security](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md),
and [Claude Code security review](https://github.com/anthropics/claude-code-security-review).
