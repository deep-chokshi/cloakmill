# Behavioral tests

CI checks lint, formatting, packaging, and imports; it does not claim that pseudonymization works. The separate Step 1 prototype has workflow tests in `prototypes/workspace/model.test.mjs`, covering authored fictional interactions rather than a privacy engine.

Python behavioral tests live under `unit/`, `integration/`, or `acceptance/` as features land. Use synthetic fixtures exclusively.

`unit/synthetic_corpus/` covers deterministic regeneration of the eval-v1 1k / 10k corpora and the engine-inaccessible boundary for `fixtures/eval/`. See [synthetic eval corpora](../docs/development/synthetic-eval-corpora.md).

Test observable contracts: identity consistency, ambiguous-match abstention, source-location correctness, referential integrity, private-field exclusion, and RL task invariants. Avoid tests that merely reproduce implementation details or check that an empty package exists.
