# Synthetic evaluation corpora

Deterministic 1,000- and 10,000-record fictional corpora for measuring detection
recall, wrong merges, abstention, and review workload. They are **not** product
output and contain no real enterprise data.

## Layout

| Path | Role |
| --- | --- |
| `examples/synthetic/corpora/eval-v1/{1k,10k}/raw/` | Engine-visible inputs: CSV, JSON, TXT |
| `examples/synthetic/corpora/eval-v1/{1k,10k}/manifest.json` | Seed, sizes, scenario tags, digests of raw files |
| `tests/fixtures/eval/eval-v1/{1k,10k}/` | **Held-out** expected observations and identity links |
| `tests/fixtures/eval/ENGINE_INACCESSIBLE` | Marker: runtime packages must not load this tree |
| `scripts/synthetic_corpus/` | Generator (outside `src/cloakmill/` runtime hot path) |

Raw inputs intentionally include repeated people, shared first-name ambiguity,
shared-mailbox operators, and email ownership changes. Domains are reserved
`.example` addresses only.

Expected observation and identity-link JSON uses `schema_version:
provisional-f01-v1`, aligned with the planned F01 artifact / part / locator /
observation shapes. When domain contracts land, eval loaders can migrate onto
the real types without mixing expectations into detection code.

## Regenerate

From the repository root (no network required after `uv sync`):

```bash
uv sync --locked
uv run python -m scripts.synthetic_corpus              # both 1k and 10k
uv run python -m scripts.synthetic_corpus --size 1k
uv run python -m scripts.synthetic_corpus --size 10k
uv run python -m scripts.synthetic_corpus --json-summary
```

Regeneration must reproduce the SHA-256 digests in each corpus `DIGESTS.json`.
The 10k `expected_observations.jsonl` file is large and gitignored; regenerate
it locally when an eval harness needs the full held-out set. Digests for that
file remain committed so CI can verify determinism without storing the blob.

## Running checks

```bash
make check
uv run pytest tests/unit/synthetic_corpus -q
```

These tests confirm deterministic regeneration, reserved domains, scenario
coverage, provisional schema shape, and that `src/cloakmill/` does not reference
held-out fixture paths.

## Eval usage (later pipeline stages)

1. Point admission / detection only at `examples/synthetic/corpora/eval-v1/*/raw/`.
2. Compare engine observations to `tests/fixtures/eval/.../expected_observations.jsonl`
   from an eval harness or acceptance test — never from detection imports.
3. Score identity resolution against `expected_identity_links.jsonl`
   (`accept` / `abstain_review` / `keep_separate`).
4. Report missed detections, wrong merges, and unresolved / review rates per
   the [discovery architecture](../architecture/discovery-and-identity.md).

Do not commit source→synthetic mapping vaults, real PII, or customer-derived
reproductions alongside these corpora.
