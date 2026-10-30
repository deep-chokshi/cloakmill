# Project structure

One Python distribution keeps shared identity and transformation contracts together while the product is young. The subpackages are boundaries, not implemented services.

```text
cloakmill/
├── src/cloakmill/
│   ├── domain/          Shared records, locators, evidence, policy contracts
│   ├── connectors/      Offline source/export readers
│   ├── formats/         Parsers and native-format writers
│   ├── detection/       Rules and local-model observations
│   ├── identity/        Resolution, aliases, mapping snapshots, synthetic profiles
│   ├── transforms/      Transformation planning and deterministic patch application
│   ├── validation/      Privacy, structural, and task-utility checks
│   └── pipeline/        Job coordination and release manifests
├── tests/               Synthetic behavioral tests as features land
├── apps/review-ui/      Next.js frontend foundation; fictional sample backend only
├── examples/synthetic/  Redistributable illustrative examples
├── prototypes/workspace/ Fictional, clickable UX reference; separate from the app
├── docs/
│   ├── assets/          Repository-local product visuals
│   ├── architecture/    System design and architectural boundaries
│   ├── development/     Contributor setup and repository map
│   └── superpowers/     Dated specifications and execution plans
├── .github/             CI, contribution templates, dependency update configuration
├── pyproject.toml       Package, build, lint, and test configuration
└── uv.lock              Committed development dependency resolution
```

## Dependency direction

```mermaid
flowchart TB
    Pipeline[Pipeline coordination] --> Adapters[Connectors and format adapters]
    Pipeline --> Detection[Detection]
    Pipeline --> Identity[Identity and mappings]
    Pipeline --> Transforms[Transformation]
    Pipeline --> Validation[Validation]
    Adapters --> Domain[Shared domain contracts]
    Detection --> Domain
    Identity --> Domain
    Transforms --> Domain
    Validation --> Domain
```

- `domain` must not import adapters, model runtimes, or pipeline orchestration.
- Detection produces evidence; it does not assign synthetic values.
- Identity resolution owns canonical links and mapping snapshots.
- Format writers apply approved patches; they do not invent identities.
- Validation must be able to reject a candidate output independently of its writer.
- Pipeline coordination passes opaque references rather than copying sensitive text into job histories.

Introduce persistent storage adapters when the first registry needs them. The
Next.js frontend now lives in `apps/review-ui/`, with a server-only fictional data
adapter and App Router screens. Python processing remains in `src/cloakmill/`.
Avoid empty service scaffolds and databases ahead of their first consumer.

The Step 1 prototype in `prototypes/workspace/` is a static design artifact with a native Node-tested workflow model. It is not the production frontend, a dependency of the Python core, or an implemented enterprise-data processor.
