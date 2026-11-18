# Behavioral tests

Python behavioral tests live under `unit/`, `integration/`, and `acceptance/` as features land. CI runs lint, formatting, packaging, imports, and `pytest`. Passing checks do not claim that end-to-end pseudonymization works. The separate Step 1 prototype has workflow tests in `prototypes/workspace/model.test.mjs`, covering authored fictional interactions rather than a privacy engine.

Current coverage:

- `unit/domain/` — F01 immutable artifact/part/locator/observation contracts, serialization round-trips, locator bound rejection, and domain import isolation.

Use synthetic fixtures exclusively. Prefer reserved example domains (for example `acme.example`). Never commit enterprise data, secrets, or source-to-synthetic mappings.

Test observable contracts: identity consistency, ambiguous-match abstention, source-location correctness, referential integrity, private-field exclusion, and RL task invariants. Avoid tests that merely reproduce implementation details or check that an empty package exists.
