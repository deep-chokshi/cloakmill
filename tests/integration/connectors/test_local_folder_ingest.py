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


def test_symlink_inside_root_is_quarantined(tmp_path: Path) -> None:
    """File symlinks are refused to close TOCTOU between resolve and read."""
    root = tmp_path / "pkg"
    root.mkdir()
    target = root / "nested" / "target.txt"
    _write(target, "linked-inside\n")
    (root / "alias.txt").symlink_to(target)

    scan = scan_local_folder(root)
    by_path = {entry.relative_package_path: entry for entry in scan.inventory}
    assert by_path["alias.txt"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["alias.txt"].reason is AdmissionReason.FILE_SYMLINK
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
        assert "relative_package_path" not in entry
        assert "private_integrity_digest" not in entry
        assert "opaque_id" in entry
    for entry in parsed["coverage"]["entries"]:
        assert "relative_package_path" not in entry
        assert "private_integrity_digest" not in entry
        assert "opaque_id" in entry
    # Source path components must not leak into release-facing serialization.
    assert "people.json" not in payload
    assert "orders.csv" not in payload
    assert "readme.txt" not in payload
    assert "secrets" not in payload

    # Private digests remain available on the process inventory, not release JSON.
    admitted = [
        entry for entry in result.inventory if entry.disposition is AdmissionDisposition.ADMITTED
    ]
    assert admitted
    assert all(entry.private_integrity_digest for entry in admitted)
    assert all(entry.relative_package_path for entry in admitted)


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


def test_bare_directory_exclusion_covers_descendants_and_symlink_targets(
    tmp_path: Path,
) -> None:
    root = tmp_path / "pkg"
    _write(root / "secrets" / "token.txt", "not-a-real-secret\n")
    (root / "alias.txt").symlink_to(root / "secrets" / "token.txt")
    _write(root / "ok.txt", "fine\n")

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets",),
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["secrets"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["alias.txt"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert result.admitted_payloads and all(
        payload.relative_package_path == "ok.txt" for payload in result.admitted_payloads
    )


def test_non_utf8_text_is_parse_failed(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "notes.txt").write_bytes("SSN 123-45-6789".encode("utf-16"))
    _write(root / "ok.txt", "ascii-ok\n")

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["notes.txt"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["notes.txt"].reason is AdmissionReason.PARSE_FAILED
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert all(artifact.media_type == "text/plain" for artifact in result.artifacts)
    assert len(result.artifacts) == 1


def test_hard_link_to_excluded_file_is_excluded(tmp_path: Path) -> None:
    """Hard links outside an exclusion prefix must not admit the scoped-out inode."""
    root = tmp_path / "pkg"
    excluded = root / "secrets" / "token.txt"
    _write(excluded, "not-a-real-secret\n")
    root.mkdir(exist_ok=True)
    alias = root / "alias.txt"
    alias.hardlink_to(excluded)
    _write(root / "ok.txt", "fine\n")

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets/**",),
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["secrets"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["alias.txt"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["alias.txt"].reason is AdmissionReason.EXPLICIT_EXCLUSION
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert result.admitted_payloads and all(
        payload.relative_package_path == "ok.txt" for payload in result.admitted_payloads
    )
    assert all(artifact.media_type == "text/plain" for artifact in result.artifacts)
    assert len(result.artifacts) == 1


def test_exclusion_patterns_normalize_common_spellings(tmp_path: Path) -> None:
    """Leading ./ or / and trailing / must not silently no-op exclusions."""
    from cloakmill.connectors.local_folder import normalize_exclusion_pattern

    assert normalize_exclusion_pattern("./secrets/**") == "secrets/**"
    assert normalize_exclusion_pattern("/secrets/**") == "secrets/**"
    assert normalize_exclusion_pattern("secrets/") == "secrets"
    with pytest.raises(ValueError, match="backslash"):
        normalize_exclusion_pattern(r"secrets\**")

    root = tmp_path / "pkg"
    _write(root / "secrets" / "token.txt", "not-a-real-secret\n")
    _write(root / "ok.txt", "fine\n")

    for pattern in ("./secrets/**", "/secrets/**", "secrets/"):
        result = ingest_local_folder(
            root,
            access_scope="project:syn-demo",
            exclusions=(pattern,),
        )
        by_path = {entry.relative_package_path: entry for entry in result.inventory}
        assert by_path["secrets"].disposition is AdmissionDisposition.EXCLUDED, pattern
        assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED, pattern
        assert "secrets/token.txt" not in by_path
        assert all(
            payload.relative_package_path == "ok.txt" for payload in result.admitted_payloads
        ), pattern


def test_unreadable_excluded_tree_fails_closed_on_hard_links(tmp_path: Path) -> None:
    """If an excluded subtree cannot be enumerated, multiply-linked files are excluded."""
    root = tmp_path / "pkg"
    secrets = root / "secrets"
    secrets.mkdir(parents=True)
    excluded = secrets / "token.txt"
    _write(excluded, "not-a-real-secret\n")
    alias = root / "alias.txt"
    alias.hardlink_to(excluded)
    _write(root / "ok.txt", "fine\n")
    # Make the excluded directory unreadable so inode pre-scan cannot list children.
    secrets.chmod(0o000)
    try:
        result = ingest_local_folder(
            root,
            access_scope="project:syn-demo",
            exclusions=("secrets/**",),
        )
    finally:
        secrets.chmod(0o755)

    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["alias.txt"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert result.admitted_payloads and all(
        payload.relative_package_path == "ok.txt" for payload in result.admitted_payloads
    )


def test_file_open_uses_nofollow_against_symlink_swap(tmp_path: Path) -> None:
    """Admission reads through O_NOFOLLOW so a post-check symlink swap cannot escape."""
    root = tmp_path / "pkg"
    root.mkdir()
    target = root / "notes.txt"
    _write(target, "benign\n")
    outside = tmp_path / "outside-secret.txt"
    _write(outside, "should-not-admit\n")

    # Simulate TOCTOU: replace the regular file with an escaping symlink, then open.
    target.unlink()
    target.symlink_to(outside)

    result = ingest_local_folder(root, access_scope="project:syn-demo")
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["notes.txt"].disposition is AdmissionDisposition.QUARANTINED
    assert by_path["notes.txt"].reason in {
        AdmissionReason.FILE_SYMLINK,
        AdmissionReason.SYMLINK_ESCAPE,
    }
    assert result.admitted_payloads == ()
    assert result.artifacts == ()


def test_hard_link_to_excluded_backslash_named_file_is_excluded(tmp_path: Path) -> None:
    """Excluded-tree files with ``\\`` in the name must still contribute inodes."""
    root = tmp_path / "pkg"
    secrets = root / "secrets"
    secrets.mkdir(parents=True)
    # POSIX allows backslash in a filename; quarantine must not skip inode record.
    excluded = secrets / r"token\secret.txt"
    excluded.write_text("not-a-real-secret\n", encoding="utf-8")
    alias = root / "alias.txt"
    alias.hardlink_to(excluded)
    _write(root / "ok.txt", "fine\n")

    result = ingest_local_folder(
        root,
        access_scope="project:syn-demo",
        exclusions=("secrets/**",),
    )
    by_path = {entry.relative_package_path: entry for entry in result.inventory}
    assert by_path["secrets"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["alias.txt"].disposition is AdmissionDisposition.EXCLUDED
    assert by_path["alias.txt"].reason is AdmissionReason.EXPLICIT_EXCLUSION
    assert by_path["ok.txt"].disposition is AdmissionDisposition.ADMITTED
    assert result.admitted_payloads and all(
        payload.relative_package_path == "ok.txt" for payload in result.admitted_payloads
    )
    assert len(result.artifacts) == 1


def test_opaque_ids_are_hmac_keyed_per_scan(tmp_path: Path) -> None:
    """Opaque ids must not be offline-invertible path hashes."""
    root = tmp_path / "pkg"
    _write(root / "one.txt", "a\n")

    first = scan_local_folder(root)
    second = scan_local_folder(root)
    first_id = first.inventory[0].opaque_id
    second_id = second.inventory[0].opaque_id
    assert first_id.startswith("art-")
    assert second_id.startswith("art-")
    # Fresh job key per scan → same relative path yields different opaque ids.
    assert first_id != second_id
    # Within one scan the id is stable for the admitted payload pairing.
    assert first.admitted[0].opaque_id == first_id
