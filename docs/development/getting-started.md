# Development setup

This sets up the source repository for contributors. It does not install a functioning pseudonymization product, CLI, connector, or offline appliance.

## Prerequisites

- Python 3.12 or newer; the default development interpreter is 3.12.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or newer.
- Git.

## Set up and verify

```bash
git clone https://github.com/deep-chokshi/cloakmill.git
cd cloakmill
uv sync --locked
make check
make build
```

The repository is private initially; cloning requires access granted by its owner.

`make check` runs Ruff lint, Ruff formatting verification, and a package import. `make build` creates a wheel and source distribution under `dist/`. No Python pipeline behavioral tests exist yet; pytest is available for the first implemented core feature.

The [Step 1 UI prototype](../../prototypes/workspace/README.md) runs independently with a localhost HTTP server. Its sample workflow model can be checked with `node --test prototypes/workspace/model.test.mjs` using Node.js 22 or newer. This does not test a production privacy engine.

## Available commands

| Command | Purpose |
| --- | --- |
| `make setup` | Create the locked development environment |
| `make check` | Lint, format verification, and import check |
| `make format` | Format Python source |
| `make build` | Build distributable package artifacts |
| `uv run pytest` | Run behavioral tests once they are introduced |

## Development connectivity versus product deployment

[Claude code review, security review, and `@claude`](claude-review.md) run as
GitHub Actions with an owner-supplied Anthropic API secret. See that guide for
setup, behavior, cost, and troubleshooting.

Initial dependency resolution and installation use package indexes. This development workflow is not an air-gapped installer. The product deployment goal requires a separately built offline bundle containing approved dependencies, models, OCR assets, and licenses, followed by installation and execution checks with external networking disabled.

## Local data

Keep experimental input in `local/`, `imports/`, or `data/`; outputs in `outputs/` or `exports/`; model assets in `models/`; and identity registries in `vault/`. These root directories are ignored. Ignore rules are an accidental-commit guard, not a security boundary. Review every staged diff before committing.

Do not load real customer data until the relevant feature, access controls, and evaluation procedure have been reviewed.
