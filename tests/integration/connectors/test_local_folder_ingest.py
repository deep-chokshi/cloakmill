"""Behavioral integration tests for F04 local-folder admission and coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cloakmill.connectors import (
    AdmissionDisposition,
    AdmissionLimits,
    AdmissionReason,
    scan_local_folder,
)
from cloakmill.domain import CoverageState, FieldPathLocator, SurfaceKind
from cloakmill.pipeline import ingest_local_folder


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _synthetic_tree(root: Path) -> None:
    _write(
        root / "records" / "people.json",
        json.dumps(
            {
                "people": [
                    {
                        "name": "Maya Shah",
                        "email": "maya@acme.example",
                        "account": "AC-104",
                    }
                ]
            },
            indent=2,
        ),
    )
    _write(
        root / "records" / "orders.csv",
        "order_id,owner_email,note\n"
        "ORD-1,maya@acme.example,Rush delivery\n"
        "ORD-2,lee@acme.example,Hold at desk\n",
    )
    _write(
        root / "notes" / "readme.txt",
        "Synthetic fixture for CloakMill local ingest. Contact ops@acme.example.\n",
    )
    _write(root / "secrets" / "token.txt", "not-a-real-secret\n")
    _write(root / "binary" / "photo.bin", b"\x00\x01\x02\xff")


def test_synthetic_folder_import_produces_inventory_and_coverage(tmp_path: Path) -> None:
    root = tmp_path / "synthetic-export"
    _synthetic_tree(root)

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets/**",),
        limits=AdmissionLimits(max_depth=5, max_file_bytes=1024 * 1024),
    )

    paths = {entry.relative_package_path: entry for entry in result.inventory}
    assert "records/people.json" in paths
    assert "records/orders.csv" in paths
    assert "notes/readme.txt" in paths
    # Directory-prefix exclusions inventory the directory and skip descent.
    assert "secrets" in paths
    assert paths["secrets"].disposition is AdmissionDisposition.EXCLUDED
    assert paths["secrets"].coverage_state is CoverageState.EXCLUDED
    assert "secrets/token.txt" not in paths
    assert paths["binary/photo.bin"].disposition is AdmissionDisposition.QUARANTINED
    assert paths["binary/photo.bin"].reason is AdmissionReason.UNSUPPORTED_TYPE

    assert result.coverage.totals[CoverageState.PROCESSED.value] >= 3
    assert result.coverage.totals[CoverageState.EXCLUDED.value] >= 1
    assert result.coverage.totals[CoverageState.FAILED.value] >= 1

    media_types = {artifact.media_type for artifact in result.artifacts}
    assert "application/json" in media_types
    assert "text/csv" in media_types
    assert "text/plain" in media_types

    assert any(part.surface_kind is SurfaceKind.STRUCTURED_FIELD for part in result.parts)
    assert any(part.surface_kind is SurfaceKind.TEXT for part in result.parts)
    assert any(
        isinstance(part.original_locator, FieldPathLocator)
        and part.original_locator.path[:1] == ("people",)
        for part in result.parts
    )


def test_symlink_escape_is_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    outside = tmp_path / "outside.txt"
    _write(outside, "escape\n")
    root.mkdir()
    _write(root / "ok.txt", "inside\n")
    (root / "escape.txt").symlink_to(outside)

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    by_path = {entry.relative_package_path: entry for entry in result.inventory}

    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert by_path["escape.txt"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["escape.txt"].reason is AdmissionReason.SYMLINK_ESCAPE
    assert by_path["escape.txt"].coverage_state is CoverageState.FAILED


def test_symlink_inside_root_is_admitted(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    target = root / "nested" / "target.txt"
    _write(target, "linked-inside\n")
    (root / "alias.txt").symlink_to(target)

    scan = scan_local_folder(root)
    by_path = {entry.relative_package_path: entry for entry in scan.inventory}
    assert by_path["alias.txt"].disposition is AdmissionDisposition.ADMITTED
    assert by_path["nested/target.txt"].disposition is AdmissionDisposition.ADMITTED


def test_oversized_file_is_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    _write(root / "small.txt", "ok\n")
    _write(root / "huge.txt", "x" * 200)

    result = ingest_local_folder(
        root,
        limits=AdmissionLimits(max_file_bytes=50),
        access_scope="project:syn-demo",
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["small.txt"].disposition is AdmissionDisposition.ADMITTED
    assert by_path["huge.txt"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["huge.txt"].reason is AdmissionReason.OVERSIZED


def test_max_depth_exceeded_is_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    deep = root / "a" / "b" / "c"
    _write(deep / "leaf.txt", "too-deep\n")
    _write(root / "top.txt", "ok\n")

    result = ingest_local_folder(
        root,
        limits=AdmissionLimits(max_depth=1),
        access_scope="project:syn-demo",
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["top.txt"].disposition is AdmissionDisposition.ADMITTED
    # max_depth=1 admits root and one subdirectory level; a/b/c is depth 2.
    assert by_path["a/b/c"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["a/b/c"].reason is AdmissionReason.MAX_DEPTH_EXCEEDED
    assert "a/b/c/leaf.txt" not in by_path


def test_corrupt_json_is_quarantined_as_parse_failed(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    _write(root / "broken.json", "{not-json")

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    entry = next(item for item in result.inventory if item.relative_package_path == "broken.json")
    assert entry.disposition is AdmissionDisposition.QUARANTINED
    assert entry.reason is AdmissionReason.PARSE_FAILED
    assert entry.coverage_state is CoverageState.FAILED
    assert result.artifacts == ()
    assert result.parts == ()


def test_release_facing_structures_omit_absolute_paths(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    _synthetic_tree(root)
    absolute_root = str(root.resolve())

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets/**",),
    )
    payload = result.release_facing_json()
    assert absolute_root not in payload
    assert str(tmp_path.resolve()) not in payload

    parsed = json.loads(payload)
    for entry in parsed["inventory"]:
        rel = entry["relative_package_path"]
        assert not rel.startswith("/")
        assert ".." not in rel.split("/")
        assert "private_integrity_digest" not in entry
    for entry in parsed["coverage"]["entries"]:
        assert not entry["relative_package_path"].startswith("/")
        assert "private_integrity_digest" not in entry

    # Private digests remain available on the process inventory, not release JSON.
    admitted = [
        entry for entry in result.inventory if entry.disposition is AdmissionDisposition.ADMITTED
    ]
    assert admitted
    assert all(entry.private_integrity_digest for entry in admitted)


def test_integrity_digest_matches_bytes(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    content = b'{"email": "maya@acme.example"}\n'
    _write(root / "one.json", content)

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    artifact = result.artifacts[0]
    assert artifact.private_integrity_digest.startswith("sha256:")
    assert result.admitted_payloads[0].payload == content
    assert result.admitted_payloads[0].digest == artifact.private_integrity_digest


def test_directory_symlink_escape_is_not_descended(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    _write(outside_dir / "secret.txt", "nope\n")
    root.mkdir()
    (root / "escape_dir").symlink_to(outside_dir)
    _write(root / "ok.txt", "yes\n")

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    paths = {entry.relative_package_path for entry in result.inventory}
    assert "escape_dir" in paths
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["escape_dir"].reason is AdmissionReason.SYMLINK_ESCAPE
    assert "escape_dir/secret.txt" not in paths
    assert "ok.txt" in paths


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("rows.jsonl", "application/x-ndjson"),
        ("rows.csv", "text/csv"),
    ],
)
def test_jsonl_and_csv_extract_parts(tmp_path: Path, filename: str, media_type: str) -> None:
    root = tmp_path / "pkg"
    if filename.endswith(".jsonl"):
        body = '{"email":"maya@acme.example"}\n{"email":"lee@acme.example"}\n'
    else:
        body = "email,role\nmaya@acme.example,owner\nlee@acme.example,member\n"
    _write(root / filename, body)

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    assert len(result.artifacts) == 1
    assert result.artifacts[0].media_type == media_type
    assert len(result.parts) >= 2


def test_symlink_loop_is_quarantined_not_fatal(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    _write(root / "ok.txt", "inside\n")
    loop = root / "loop.txt"
    loop.symlink_to(loop)

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert by_path["loop.txt"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["loop.txt"].reason is AdmissionReason.SYMLINK_CYCLE


def test_directory_symlink_is_not_descended(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    _write(root / "data.json", '{"email":"maya@acme.example"}\n')
    (root / "l1").symlink_to(root)
    (root / "l2").symlink_to(root)

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["data.json"].disposition is AdmissionDisposition.ADMITTED
    assert by_path["l1"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["l1"].reason is AdmissionReason.DIRECTORY_SYMLINK
    assert by_path["l2"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["l2"].reason is AdmissionReason.DIRECTORY_SYMLINK
    # One admission only — directory symlinks must not re-read data.json.
    assert len(result.admitted_payloads) == 1
    assert len(result.artifacts) == 1


def test_directory_symlink_cannot_bypass_file_exclusion(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    _write(root / "secrets" / "token.txt", "not-a-real-secret\n")
    (root / "a_alias").symlink_to(root / "secrets")

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets/token.txt",),
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["a_alias"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["a_alias"].reason is AdmissionReason.DIRECTORY_SYMLINK
    assert by_path["secrets/token.txt"].disposition is AdmissionDisposition.EXCLUDED
    assert "a_alias/token.txt" not in by_path
    assert result.admitted_payloads == ()
    assert result.artifacts == ()


def test_deep_json_recursion_is_parse_failed(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    depth = 5000
    _write(root / "deep.json", "[" * depth + "]" * depth)
    _write(root / "ok.txt", "still-scanned\n")

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["deep.json"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["deep.json"].reason is AdmissionReason.PARSE_FAILED
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert result.artifacts and all(a.media_type == "text/plain" for a in result.artifacts)


def test_symlink_into_excluded_target_is_excluded(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    _write(root / "secrets" / "token.txt", "not-a-real-secret\n")
    root.mkdir(exist_ok=True)
    (root / "alias.txt").symlink_to(root / "secrets" / "token.txt")

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets/**",),
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["secrets"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["alias.txt"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["alias.txt"].reason is AdmissionReason.EXPLICIT_EXCLUSION
    assert result.admitted_payloads == ()
    assert result.artifacts == ()


def test_empty_json_key_is_encoded_and_extracted(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    _write(
        root / "empty-key.json",
        json.dumps({"": {"email": "maya@acme.example", "ssn": "123-45-6789"}}),
    )

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    assert len(result.artifacts) == 1
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["empty-key.json"].coverage_state is CoverageState.PROCESSED
    paths = [
        part.original_locator.path
        for part in result.parts
        if isinstance(part.original_locator, FieldPathLocator)
    ]
    assert ("$empty_key", "email") in paths
    assert ("$empty_key", "ssn") in paths


def test_ragged_csv_emits_positional_extra_cells(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    _write(
        root / "ragged.csv",
        "email,role\nmaya@acme.example,owner,123-45-6789\n",
    )

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    assert len(result.artifacts) == 1
    paths = [
        part.original_locator.path
        for part in result.parts
        if isinstance(part.original_locator, FieldPathLocator)
    ]
    assert ("rows", 0, "email") in paths
    assert ("rows", 0, "role") in paths
    assert ("rows", 0, 2) in paths


def test_backslash_filename_is_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    spoofed = root / "secrets\\token.txt"
    spoofed.write_text("not-a-real-secret\n", encoding="utf-8")
    _write(root / "ok.txt", "fine\n")

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets/**",),
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert "secrets%5Ctoken.txt" in by_path
    assert by_path["secrets%5Ctoken.txt"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["secrets%5Ctoken.txt"].reason is AdmissionReason.PATH_TRAVERSAL
    assert "secrets/token.txt" not in by_path
    assert all("\\" not in entry.relative_package_path for entry in result.inventory)


def test_normalize_rejects_backslash_spoofing() -> None:
    from cloakmill.connectors.admission import normalize_relative_package_path

    with pytest.raises(ValueError, match="backslash"):
        normalize_relative_package_path(r"secrets\token.txt")
