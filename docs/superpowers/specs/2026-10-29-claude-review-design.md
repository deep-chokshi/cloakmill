# Claude review workflow design

The owner requested an API-backed GitHub Actions review after the separate hosted Claude review remained queued. Use the official `anthropics/claude-code-action`, pinned to a reviewed commit, with the repository Actions secret `ANTHROPIC_API_KEY`.

Ready, same-repository pull requests run on opening, new commits, reopening, and becoming ready. A manual workflow accepts a PR number after this configuration reaches the default branch. Drafts, forks, and bot-triggered automatic runs are excluded. Resolve and validate the target through GitHub before exposing the API key to the action.

Check out the base revision at the workspace root and the immutable target head under `pr-head/`. The reviewer reads the diff and source, then posts a summary identifying the head SHA, workflow run, findings, and review limits. It does not execute project scripts or fix code. A postflight check requires an explicit result comment; successful action execution alone is insufficient.

Use the job-scoped `GITHUB_TOKEN` with code-read and PR-comment permissions, avoiding the hosted Claude app's token exchange. Keep full model output disabled, cancel superseded reviews, and bound time, turns, and estimated API spend. These controls do not make untrusted content safe to execute or establish a privacy guarantee. Development review sends repository content to Anthropic; the intended product runtime remains offline.

Deliver this configuration in a separate setup PR. The owner supplies the API key and controls merging. Validate the workflow locally and inspect hosted CI, but report the API review as untested until credentials are available and a review actually completes. Do not merge the UI PR or begin Step 2 as part of setup.
