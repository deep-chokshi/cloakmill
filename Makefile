.PHONY: setup check format build

setup:
	git config core.hooksPath .githooks
	uv sync --locked

check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked python -c "import cloakmill; print(cloakmill.__version__)"

format:
	uv run --locked ruff format .

build:
	uv build --no-sources
