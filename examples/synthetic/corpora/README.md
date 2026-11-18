# Synthetic evaluation corpora (`eval-v1`)

Raw CSV / JSON / TXT inputs for CloakMill measurement harnesses. Generated
deterministically by `scripts/synthetic_corpus/`. See
[synthetic eval corpora](../../../docs/development/synthetic-eval-corpora.md).

Held-out expected observations and identity links live under
`tests/fixtures/eval/` and must never be imported by detection or other runtime
packages.
