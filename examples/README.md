# Synthetic examples

All examples in this directory are fictional and safe to redistribute. They describe intended product behavior, not the output of an implemented pipeline.

[`synthetic/identity-preview.json`](synthetic/identity-preview.json) is the source content for the README's before/after illustration. Names, organizations, account references, and addresses are illustrative. `.example` domains are reserved for examples.

[`synthetic/corpora/`](synthetic/corpora/) holds deterministic eval-v1 raw corpora (1k / 10k CSV, JSON, and TXT). Held-out expected observations stay under `tests/fixtures/eval/` — see [synthetic eval corpora](../docs/development/synthetic-eval-corpora.md).

Never add real enterprise exports, personal identifiers, credentials, original-to-synthetic mapping vaults, or customer-derived reproductions here.
