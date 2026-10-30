# Behavioral tests

The Python core has no data-processing implementation or behavioral test suite yet. CI checks lint, formatting, packaging, and imports; it does not claim that pseudonymization works. The separate Step 1 prototype has workflow tests in `prototypes/workspace/model.test.mjs`, covering authored fictional interactions rather than a privacy engine.

When a feature is introduced, add tests under `unit/`, `integration/`, or `acceptance/` according to its scope. Use synthetic fixtures exclusively.

Test observable contracts: identity consistency, ambiguous-match abstention, source-location correctness, referential integrity, private-field exclusion, and RL task invariants. Avoid tests that merely reproduce implementation details or check that an empty package exists.
