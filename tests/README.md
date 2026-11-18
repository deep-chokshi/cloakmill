# Behavioral tests

Python behavioral tests live under `unit/`, `integration/`, and `acceptance/` as features land. CI runs lint, formatting, packaging, imports, and `pytest`. Passing checks do not claim that end-to-end pseudonymization works. The separate Step 1 prototype has workflow tests in `prototypes/workspace/model.test.mjs`, covering authored fictional interactions rather than a privacy engine.

Current coverage:

- `unit/domain/` — F01 immutable artifact/part/locator/observation contracts, serialization round-trips, locator bound rejection, and domain import isolation.
- `unit/detection/` — F05 CloakMill-owned recognizers, catalog scheduling, observation validation (bounds/overlap/dedupe), and DiscoveryEngine determinism; asserts no Presidio import.
- `integration/detection/` — multi-part discovery smoke on synthetic text/fields plus optional `examples/synthetic/identity-preview.json` smoke.
- `unit/identity/` — F06 strong-anchor merges, first-name abstention, shared-mailbox separation, contradiction preservation, and held-out-eval import isolation.
- `acceptance/identity/` — synthetic held-out link fixtures with wrong-merge rate reporting for accept / abstain / shared-mailbox cases.

Use synthetic fixtures exclusively. Prefer reserved example domains (for example `acme.example`). Never commit enterprise data, secrets, or source-to-synthetic mappings.

Test observable contracts: identity consistency, ambiguous-match abstention, source-location correctness, referential integrity, private-field exclusion, and RL task invariants. Avoid tests that merely reproduce implementation details or check that an empty package exists.
