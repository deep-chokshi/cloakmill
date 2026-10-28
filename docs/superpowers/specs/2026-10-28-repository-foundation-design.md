# CloakMill repository foundation

Date: 2026-10-28

## Scope and decisions

Create the repository foundation for the offline pseudonymization platform designed in the preceding architecture discussion. The user requested the project structure, a polished product-facing README, open-source licensing, and a GitHub repository. The selected destination is `deep-chokshi/cloakmill`, **private initially**. Repository visibility must remain private unless the owner explicitly requests publication.

This foundation does not implement detection, identity resolution, transformation, a CLI, or a review application. The README must distinguish the repository's current state from planned product capabilities. Do not publish packages or manufacture installation, benchmark, compliance, customer, or production-readiness claims.

## Repository shape

Use one Python distribution with a `src/` layout rather than multiple independently versioned services. Reserve focused packages for the domain model, source connectors, file adapters, detection, identity resolution, transformations, validation, and pipeline coordination. Keep these packages dependency-light until their implementations are designed. A review frontend can be added as `apps/review-ui/` when needed; do not create a frontend scaffold now.

Use uv for environment and dependency locking, Hatchling for builds, Ruff for linting/formatting, and pytest for future behavioral tests. Validate the foundation through formatting, linting, package builds, and clean-environment imports. Do not add tests that only restate empty package declarations.

## Public presentation

The root README is a product introduction. It includes a custom SVG hero, a clearly labeled illustrative before/after graphic, the intended audience, product goals, current development status, the first milestone, and contribution links. Technical architecture, developer commands, and package responsibilities belong under `docs/`.

Use repository-local visuals so the introduction does not depend on a badge service. Avoid fabricated product screenshots or unsupported claims. Include accessible image descriptions. No company logos, customer endorsements, star counts, or performance numbers.

## Licensing and contribution

Use the unmodified Apache License 2.0 from the Apache Software Foundation, an SPDX identifier in package metadata, and a project NOTICE. Explain that source datasets, processed data, and separately licensed model weights are outside the software license. Contributions use the same outbound license without a new CLA or DCO requirement.

Add contribution instructions, a security policy, a code of conduct, issue forms, a pull-request template, and minimal CI. Public issue forms must prohibit uploading private datasets, secrets, or mapping vaults. Use GitHub private vulnerability reporting if available; do not invent a security contact address.

## GitHub setup

Initialize `main`, configure a repository-local GitHub no-reply commit email, create the requested private repository, push the verified foundation, and set a concise product description and relevant topics. Preserve any unexpected existing remote rather than overwriting it. Do not publish a release or change organization/account settings.

## Verification and acceptance

- The README clearly identifies planned capabilities and the current scaffold state.
- Every local Markdown and image link resolves.
- SVG files parse and render without missing or clipped labels.
- The official Apache license is present verbatim.
- uv resolves a committed lockfile; Ruff checks and formatting pass.
- A wheel and source distribution build successfully; a clean environment imports the wheel.
- All repository fixtures are synthetic; private local data and keys are ignored.
- The GitHub repository exists at the selected destination, is private, and its default branch matches the local pushed commit.
- GitHub CI results are reported from observed checks, without equating local verification with hosted results.
