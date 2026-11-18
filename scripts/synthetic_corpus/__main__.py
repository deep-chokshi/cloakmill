"""CLI: regenerate deterministic synthetic evaluation corpora."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import SIZES
from .generate import CorpusSpec, write_corpus


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate synthetic 1k/10k eval corpora and held-out expectations. "
            "Writes raw files under examples/synthetic/corpora/ and expectations "
            "under tests/fixtures/eval/ (engine-inaccessible)."
        )
    )
    parser.add_argument(
        "--size",
        choices=sorted(SIZES),
        action="append",
        dest="sizes",
        help="Corpus size to generate (repeatable). Default: both 1k and 10k.",
    )
    parser.add_argument(
        "--examples-root",
        type=Path,
        default=None,
        help="Override examples/synthetic/corpora output root.",
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=None,
        help="Override tests/fixtures/eval output root.",
    )
    parser.add_argument(
        "--json-summary",
        action="store_true",
        help="Print a JSON summary of digests to stdout.",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    examples_root = args.examples_root or (root / "examples" / "synthetic" / "corpora")
    fixtures_root = args.fixtures_root or (root / "tests" / "fixtures" / "eval")
    sizes = args.sizes or ["1k", "10k"]

    summaries: list[dict[str, object]] = []
    for size_key in sizes:
        spec = CorpusSpec.for_size(size_key)
        generated = write_corpus(
            spec=spec,
            examples_root=examples_root,
            fixtures_root=fixtures_root,
        )
        digest_doc = generated["digest_doc"]
        summaries.append(
            {
                "size_key": size_key,
                "source_version": spec.source_version,
                "corpus_dir": str(generated["corpus_dir"]),
                "expected_dir": str(generated["expected_dir"]),
                "observation_count": generated["manifest"]["observation_count"],
                "identity_link_count": generated["manifest"]["identity_link_count"],
                "files": digest_doc["files"],
            }
        )
        print(
            f"Wrote {spec.source_version}: "
            f"{generated['manifest']['observation_count']} observations, "
            f"{generated['manifest']['identity_link_count']} identity links",
            file=sys.stderr,
        )

    if args.json_summary:
        print(json.dumps({"corpora": summaries}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
