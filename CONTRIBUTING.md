# Contributing to CloakMill

CloakMill is in early development. The most useful contributions now are well-scoped design feedback, synthetic edge cases, evaluation methods, and the first implementation milestones in the [roadmap](docs/ROADMAP.md).

## Start here

1. Read the [architecture](docs/architecture/overview.md) and [project map](docs/development/project-structure.md).
2. For a new component or behavior change, open a feature request describing the problem and proposed contract before building a large change.
3. Set up the repository using the [developer guide](docs/development/getting-started.md).
4. Work on a focused branch from `develop`, add meaningful behavioral tests for implemented features, and run `make check` and `make build`.
5. Open a pull request into `develop` explaining the observable change, its limitations, and the verification performed.

The repository is public. Publishing packages and releases remains the owner's decision.

## Branches

- `develop` is where work lands. Branch from it and open pull requests into it.
- `main` only receives pull requests from `develop`. A GitHub ruleset blocks direct pushes, force pushes, and deletion for everyone, including the owner.
- The **Main only accepts develop** check is required, so a pull request into `main` from anything but this repository's `develop` cannot merge. It runs from `main`, so a pull request cannot change its own check.
- Pull requests from outside contributors wait for a maintainer to approve their CI run. Claude does not run on them, so maintainers review them by hand.

## Safe examples only

Use fictional data and reserved example domains. Never include raw customer exports, personal identifiers from real people, secrets, mapping vaults, model weights, private incident details, or customer-derived reproductions in issues, pull requests, logs, or screenshots. Ignore rules do not replace a staged-diff review.

## Design expectations

- Keep identity resolution separate from deterministic replacement.
- Preserve source locators and evidence for every transformation decision.
- Make ambiguity explicit; do not invent identity links.
- Treat parsing and native rewriting as separate responsibilities.
- Declare unsupported content and reject unsafe partial processing.
- Keep runtime processing compatible with the offline product goal.
- Avoid premature dependencies and unsupported scale or privacy claims.

## Tests and verification

The foundation has no implemented pipeline or behavioral tests yet. Introduce tests with the first feature, using synthetic fixtures. Check actual privacy, identity, structural, or task invariants instead of mirroring implementation logic. Report local checks and hosted CI results separately.

## License and conduct

Contributions are accepted under [Apache-2.0](LICENSE), without a separate CLA or DCO requirement. Follow the [code of conduct](CODE_OF_CONDUCT.md). Report vulnerabilities according to [SECURITY.md](SECURITY.md).
