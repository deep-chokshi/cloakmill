# Held-out evaluation expectations

These files are the complete expected observations and identity links for the
synthetic corpora under `examples/synthetic/corpora/`.

**Engine-inaccessible:** detection, identity resolution, transforms, and pipeline
runtime code must never import or load this directory. Eval harnesses and tests
may read it.

The 10k `expected_observations.jsonl` blob is gitignored (see `DIGESTS.json` for
its SHA-256). Regenerate with `uv run python -m scripts.synthetic_corpus --size 10k`.

See `docs/development/synthetic-eval-corpora.md`.
