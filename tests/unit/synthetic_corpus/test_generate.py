"""Behavioral tests for deterministic synthetic eval corpora (F02)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from scripts.synthetic_corpus.constants import RESERVED_EMAIL_DOMAINS, SIZES
from scripts.synthetic_corpus.generate import CorpusSpec, generate_corpus, write_corpus
from scripts.synthetic_corpus.schema import validate_identity_link, validate_observation

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_CORPORA = REPO_ROOT / "examples" / "synthetic" / "corpora"
FIXTURES_EVAL = REPO_ROOT / "tests" / "fixtures" / "eval"
SRC_ROOT = REPO_ROOT / "src" / "cloakmill"


def test_corpus_specs_cover_required_sizes() -> None:
    assert set(SIZES) == {"1k", "10k"}
    assert SIZES["1k"] == 1_000
    assert SIZES["10k"] == 10_000


@pytest.mark.parametrize("size_key", ["1k", "10k"])
def test_generation_is_deterministic(size_key: str) -> None:
    spec = CorpusSpec.for_size(size_key)
    first = generate_corpus(spec)
    second = generate_corpus(spec)
    assert first["digest_doc"] == second["digest_doc"]
    assert first["expected_observations_text"] == second["expected_observations_text"]
    assert first["expected_links_text"] == second["expected_links_text"]
    for path, content in first["raw_files"].items():
        assert content == second["raw_files"][path]


@pytest.mark.parametrize("size_key", ["1k", "10k"])
def test_committed_raw_digests_match_regeneration(size_key: str) -> None:
    spec = CorpusSpec.for_size(size_key)
    generated = generate_corpus(spec)
    committed = json.loads((EXAMPLES_CORPORA / "eval-v1" / size_key / "DIGESTS.json").read_text())
    assert committed["files"] == generated["digest_doc"]["files"]

    for relative in ("raw/contacts.csv", "raw/messages.json", "raw/notes.txt", "manifest.json"):
        on_disk = (EXAMPLES_CORPORA / "eval-v1" / size_key / relative).read_text(encoding="utf-8")
        digest = __import__("hashlib").sha256(on_disk.encode("utf-8")).hexdigest()
        assert digest == committed["files"][relative]


def test_one_k_expected_fixtures_match_regeneration() -> None:
    spec = CorpusSpec.for_size("1k")
    generated = generate_corpus(spec)
    expected_dir = FIXTURES_EVAL / "eval-v1" / "1k"
    assert (expected_dir / "expected_observations.jsonl").read_text(encoding="utf-8") == generated[
        "expected_observations_text"
    ]
    assert (expected_dir / "expected_identity_links.jsonl").read_text(
        encoding="utf-8"
    ) == generated["expected_links_text"]


def test_ten_k_expected_digests_match_without_committing_observations() -> None:
    """10k observations are large; digests are the committed golden values."""
    spec = CorpusSpec.for_size("10k")
    generated = generate_corpus(spec)
    committed = json.loads((FIXTURES_EVAL / "eval-v1" / "10k" / "DIGESTS.json").read_text())
    assert committed["files"] == generated["digest_doc"]["files"]
    # Identity links are small enough to keep in-tree.
    assert (FIXTURES_EVAL / "eval-v1" / "10k" / "expected_identity_links.jsonl").read_text(
        encoding="utf-8"
    ) == generated["expected_links_text"]
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "tests/fixtures/eval/eval-v1/10k/expected_observations.jsonl" in gitignore


@pytest.mark.parametrize("size_key", ["1k", "10k"])
def test_scenarios_and_schema_present(size_key: str) -> None:
    generated = generate_corpus(CorpusSpec.for_size(size_key))
    manifest = generated["manifest"]
    assert set(manifest["scenarios"]) >= {
        "repeated_people",
        "shared_first_name_ambiguity",
        "shared_mailbox_operators",
        "email_ownership_change",
    }
    assert manifest["held_out"]["engine_accessible"] is False
    assert manifest["observation_count"] > 0
    assert manifest["identity_link_count"] > 0

    decisions = {link["expected_decision"] for link in generated["links"]}
    assert "accept" in decisions
    assert "abstain_review" in decisions
    assert "keep_separate" in decisions

    for obs in generated["observations"][:50]:
        validate_observation(obs)
        assert obs["schema_version"] == "provisional-f01-v1"
        assert "artifact" in obs and "part" in obs and "evidence_locator" in obs
    for link in generated["links"]:
        validate_identity_link(link)


@pytest.mark.parametrize("size_key", ["1k", "10k"])
def test_only_reserved_example_domains(size_key: str) -> None:
    generated = generate_corpus(CorpusSpec.for_size(size_key))
    blob = "\n".join(generated["raw_files"].values())
    domains = {d.rstrip(".") for d in re.findall(r"@([A-Za-z0-9.-]+)", blob)}
    assert domains
    assert domains <= set(RESERVED_EMAIL_DOMAINS)
    assert all(d.endswith(".example") for d in domains)


def test_engine_inaccessible_marker_exists() -> None:
    marker = FIXTURES_EVAL / "ENGINE_INACCESSIBLE"
    assert marker.is_file()
    text = marker.read_text(encoding="utf-8")
    assert "never import" in text.lower() or "must never" in text.lower()


def test_runtime_packages_do_not_import_eval_fixtures() -> None:
    """Detection and sibling runtime packages must not reference held-out fixtures."""
    forbidden = re.compile(
        r"fixtures(?:/|\\|\.)eval|tests\.fixtures\.eval|ENGINE_INACCESSIBLE|"
        r"expected_observations|expected_identity_links"
    )
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if forbidden.search(source):
            offenders.append(str(path.relative_to(REPO_ROOT)))
        # Also reject AST imports that pull tests.fixtures
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and (node.module.startswith("tests.fixtures") or "fixtures.eval" in node.module)
            ):
                offenders.append(str(path.relative_to(REPO_ROOT)))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "fixtures.eval" in alias.name or alias.name.startswith("tests.fixtures"):
                        offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_write_corpus_round_trip(tmp_path: Path) -> None:
    spec = CorpusSpec.for_size("1k")
    examples_root = tmp_path / "corpora"
    fixtures_root = tmp_path / "eval"
    written = write_corpus(spec=spec, examples_root=examples_root, fixtures_root=fixtures_root)
    assert (written["corpus_dir"] / "raw" / "contacts.csv").is_file()
    assert (written["expected_dir"] / "expected_observations.jsonl").is_file()
    assert (fixtures_root / "ENGINE_INACCESSIBLE").is_file()
    again = generate_corpus(spec)
    assert again["digest_doc"] == written["digest_doc"]
