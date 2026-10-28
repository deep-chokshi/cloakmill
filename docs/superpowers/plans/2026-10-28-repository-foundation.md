# Repository Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current session. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Establish a verified, private GitHub repository with a product-facing README, extensible Python package structure, and Apache-2.0 licensing.

**Architecture:** One dependency-light Python package in `src/cloakmill/`, with separate public presentation, architecture documentation, development guidance, and community configuration. Product capabilities remain planned until implemented and independently verified.

**Tech Stack:** Python 3.12+, uv, Hatchling, Ruff, pytest, GitHub Actions, Markdown, SVG.

---

### Task 1: Record the repository contract

**Files:**
- Create: `docs/superpowers/specs/2026-10-28-repository-foundation-design.md`
- Create: `docs/superpowers/plans/2026-10-28-repository-foundation.md`

- [x] Confirm the destination and visibility from the user's response: `deep-chokshi/cloakmill`, private.
- [x] Initialize `main` and configure `252443133+deep-chokshi@users.noreply.github.com` locally.
- [x] Commit the reviewed foundation design and this execution plan.

### Task 2: Establish the package and developer workflow

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `.gitattributes`, `Makefile`
- Create: `src/cloakmill/__init__.py`, `src/cloakmill/py.typed`
- Create: package initializers under `domain/`, `connectors/`, `formats/`, `detection/`, `identity/`, `transforms/`, `validation/`, `pipeline/`
- Create: `tests/README.md`, `examples/README.md`, `examples/synthetic/identity-preview.json`
- Create: `docs/development/getting-started.md`, `docs/development/project-structure.md`

- [x] Set Python `>=3.12`, Apache-2.0 metadata, no runtime dependencies, dynamic Hatch version, and a `src/cloakmill` wheel target.
- [x] Use this package version declaration:

```python
"""CloakMill: an offline enterprise-data pseudonymization project."""

__version__ = "0.1.0.dev0"
```

- [x] Add development dependencies Ruff and pytest; generate `uv.lock` through `uv lock`.
- [x] Add `make setup`, `make check`, `make format`, and `make build` targets using locked uv environments.
- [x] Document separate connected development and future air-gapped product packaging; do not describe the source scaffold as an offline distribution.
- [x] Validate with `uv sync --locked`, `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, and `uv build`.

### Task 3: Create the product introduction and architecture references

**Files:**
- Create: `README.md`, `docs/assets/hero.svg`, `docs/assets/identity-preview.svg`, `docs/assets/license.svg`
- Create: `docs/architecture/overview.md`, `docs/ROADMAP.md`

- [x] Introduce the intended product, target audience, consistent synthetic identities, preserved context, and offline deployment goal.
- [x] Label both the illustrative example and unimplemented features explicitly; show the current repository foundation as available.
- [x] Keep architecture internals and setup commands out of the marketing README.
- [x] Document the two-pass pipeline, mapping namespaces, source-format boundaries, local-model constraints, and privacy/utility release gates in the architecture reference.
- [x] Parse and render the SVG assets and verify local document links.

### Task 4: Add licensing, contribution, and CI configuration

**Files:**
- Create: `LICENSE`, `NOTICE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `AGENTS.md`
- Create: `docs/licensing.md`, `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/feature_request.yml`, `.github/ISSUE_TEMPLATE/config.yml`, `.github/pull_request_template.md`, `.github/workflows/ci.yml`

- [x] Download the unmodified license from `https://www.apache.org/licenses/LICENSE-2.0.txt`.
- [x] Use `Copyright 2026 CloakMill contributors` in NOTICE; document software/data/model licensing boundaries.
- [x] Provide synthetic-only issue instructions and private vulnerability-reporting guidance.
- [x] Configure read-only CI permissions, Python 3.12 and 3.13 validation, locked dependency sync, Ruff checks, builds, and package import checks.
- [x] Pin third-party GitHub Actions to inspected commit SHAs and add automated action-update configuration.
- [x] Validate community forms, workflow configuration, package artifacts, and ignored data paths before committing.

### Task 5: Create and verify the private remote

**Remote:** `deep-chokshi/cloakmill`

- [x] Review the staged file list and diff; commit the verified repository foundation.
- [x] Create the private repository using `gh repo create deep-chokshi/cloakmill --private --source=. --remote=origin --push`.
- [x] Set the product description and relevant repository topics.
- [x] Verify visibility, default branch, remote URL, and pushed commit through `gh repo view` and the GitHub API.
- [x] Inspect the first hosted CI run, repair any genuine setup failures, and report its observed result.


## Completion evidence

- Repository: https://github.com/deep-chokshi/cloakmill; visibility verified as private; default branch `main`.
- GitHub recognizes the Apache License 2.0. Repository description and topics are configured.
- Local lint, formatting, wheel/source builds, and a clean-environment wheel import passed on Python 3.12.
- Local document links, synthetic JSON, SVG syntax/rendering, distribution license contents, and ignored private-data paths were verified.
- README previews were inspected at desktop and mobile widths with all images loaded and no horizontal overflow. GitHub-rendered navigation anchors, images, and alt text were checked through the authenticated API.
- The initial CI workflow exposed an invalid job-level `runner` context. Moving the temporary-directory variable to its executing step fixed workflow validation.
- Hosted lint, formatting, builds, and clean-environment wheel imports passed on Python 3.12 and 3.13: https://github.com/deep-chokshi/cloakmill/actions/runs/40668969489.
- This completes the repository foundation. Detection, connectors, transformation, CLI, review UI, and air-gapped product bundles remain planned.
