# Synthetic corpus `eval-v1-10k`

Fictional raw inputs for CloakMill evaluation. Reserved `.example` domains only.

- `raw/contacts.csv` — structured contacts with repeated people and ownership rows
- `raw/messages.json` — message threads with cross-mentions and shared mailboxes
- `raw/notes.txt` — free-text notes with ambiguous first-name mentions
- `manifest.json` / `DIGESTS.json` — provenance and SHA-256 digests

Held-out expected observations and identity links are **not** stored here.
They live under `tests/fixtures/eval/` and must never be imported by detection code.

Regenerate with:

```bash
uv run python -m scripts.synthetic_corpus --size 10k
```
