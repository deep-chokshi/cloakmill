# Working in CloakMill

## Product and repository state

CloakMill is an offline enterprise-data pseudonymization project in early development. Read `docs/architecture/overview.md` and `docs/ROADMAP.md` before introducing behavior. This repository is private initially; do not change visibility or publish packages/releases without an explicit owner request.

## Implementation boundaries

- Keep the Python core in `src/cloakmill/`; shared contracts live in `domain/`.
- Add runtime dependencies when a concrete implemented feature needs them.
- Keep detection, identity resolution, synthetic profile assignment, native writing, and verification separate.
- Accepted entity graphs and frozen mapping snapshots define reproducible transformation behavior.
- Runtime processing must meet the intended air-gapped deployment model. Development tools and hosted CI may use the network; do not confuse those environments.
- Never claim connector coverage, native fidelity, privacy guarantees, performance, or a working CLI without evidence.

## Data and communication

- Use synthetic fixtures only. Never commit enterprise data, secrets, source-to-synthetic mappings, model weights, or customer-derived examples.
- Use reserved example domains. Keep sensitive payloads out of logs and workflow metadata.
- Keep the root README product-facing. Put developer setup and architectural internals under `docs/`.
- Mark planned capabilities clearly; do not make illustrative visuals appear to be real product output.

## Verification

Run `make check` and `make build` for package changes. Add meaningful behavioral tests when implementing features; do not create tests that only check scaffolding. Inspect staged diffs and report local verification separately from hosted CI.
