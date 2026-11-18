"""Bounded local-folder acquisition and admission for offline ingest."""

from __future__ import annotations

import fnmatch
import secrets
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cloakmill.connectors.admission import (
    AdmissionDisposition,
    AdmissionLimits,
    AdmissionReason,
    encode_unsafe_relative_path,
    media_type_for_relative_path,
    normalize_relative_package_path,
    opaque_id_for_relative_path,
    sha256_digest,
    suffix_is_allowed,
)
from cloakmill.connectors.inventory import InventoryEntry
from cloakmill.domain.enums import CoverageState


@dataclass(frozen=True, slots=True)
class AdmittedPayload:
    """Private admitted bytes keyed for later format extraction (not release-facing)."""

    opaque_id: str
    relative_package_path: str
    media_type: str
    digest: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class LocalFolderScanResult:
    """Admission outcome for one selected root. Absolute root stays process-local."""

    inventory: tuple[InventoryEntry, ...]
    admitted: tuple[AdmittedPayload, ...]


def _path_and_ancestors(relative_path: str) -> tuple[str, ...]:
    """Return the path and every ancestor prefix (``a/b/c`` → ``a/b/c``, ``a/b``, ``a``)."""
    parts = PurePosixPath(relative_path).parts
    return tuple("/".join(parts[:index]) for index in range(len(parts), 0, -1))


def _matches_exclusion(relative_path: str, patterns: Sequence[str]) -> bool:
    """Match exclusions against the path and every ancestor (resolved or lexical)."""
    candidates = _path_and_ancestors(relative_path)
    for pattern in patterns:
        for candidate in candidates:
            if fnmatch.fnmatchcase(candidate, pattern):
                return True
            # Directory-prefix style exclusions such as "secrets/**".
            if pattern.endswith("/**") and (
                candidate == pattern[:-3] or candidate.startswith(pattern[:-2])
            ):
                return True
            # Bare directory name excludes the directory and everything beneath it.
            if candidate == pattern or candidate.startswith(f"{pattern}/"):
                return True
    return False


def _coverage_for(
    disposition: AdmissionDisposition,
    reason: AdmissionReason,
) -> CoverageState:
    if disposition is AdmissionDisposition.ADMITTED and reason is AdmissionReason.OK:
        return CoverageState.PROCESSED
    if disposition is AdmissionDisposition.EXCLUDED:
        return CoverageState.EXCLUDED
    if reason is AdmissionReason.UNREADABLE:
        return CoverageState.UNAVAILABLE
    return CoverageState.FAILED


def _entry(
    *,
    relative_package_path: str,
    disposition: AdmissionDisposition,
    reason: AdmissionReason,
    id_key: bytes,
    media_type: str | None = None,
    byte_size: int | None = None,
    digest: str | None = None,
) -> InventoryEntry:
    return InventoryEntry(
        opaque_id=opaque_id_for_relative_path("art", relative_package_path, key=id_key),
        relative_package_path=relative_package_path,
        disposition=disposition,
        reason=reason,
        coverage_state=_coverage_for(disposition, reason),
        media_type=media_type,
        byte_size=byte_size,
        private_integrity_digest=digest,
    )


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _inode_identity(path: Path, *, follow_symlinks: bool = False) -> tuple[int, int] | None:
    """Return ``(st_dev, st_ino)`` for hard-link / cycle tracking."""
    try:
        stat = path.stat() if follow_symlinks else path.lstat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


def _dir_identity(path: Path) -> tuple[int, int] | None:
    return _inode_identity(path, follow_symlinks=True)


def _collect_excluded_inodes(
    root_path: Path,
    exclusion_patterns: Sequence[str],
) -> set[tuple[int, int]]:
    """Walk the tree and record inodes for every excluded path and descendant.

    Hard links outside an exclusion prefix share ``(st_dev, st_ino)`` with the
    scoped-out file; collecting those identities closes the bypass.
    """
    if not exclusion_patterns:
        return set()

    excluded: set[tuple[int, int]] = set()
    visited_dirs: set[tuple[int, int]] = set()

    def record(path: Path) -> None:
        identity = _inode_identity(path, follow_symlinks=False)
        if identity is not None:
            excluded.add(identity)
        # Also record the followed target so hard links to symlink targets match.
        if path.is_symlink():
            followed = _inode_identity(path, follow_symlinks=True)
            if followed is not None:
                excluded.add(followed)

    def walk(directory: Path, *, under_exclusion: bool) -> None:
        dir_id = _inode_identity(directory, follow_symlinks=False)
        if dir_id is None:
            return
        if dir_id in visited_dirs:
            return
        visited_dirs.add(dir_id)

        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError:
            return

        for child in children:
            try:
                raw_relative = child.relative_to(root_path).as_posix()
            except ValueError:
                continue

            # Backslash is a legal POSIX filename character. Do not skip inode
            # recording for those names — only admission/normalize rejects them.
            has_backslash = "\\" in raw_relative or any(
                "\\" in part for part in child.relative_to(root_path).parts
            )
            if has_backslash:
                matched = under_exclusion or _matches_exclusion(raw_relative, exclusion_patterns)
                if matched:
                    record(child)
                    if not child.is_symlink() and child.is_dir():
                        walk(child, under_exclusion=True)
                elif child.is_dir() and not child.is_symlink():
                    walk(child, under_exclusion=False)
                continue

            try:
                relative = normalize_relative_package_path(raw_relative)
            except ValueError:
                if under_exclusion:
                    record(child)
                    if not child.is_symlink() and child.is_dir():
                        walk(child, under_exclusion=True)
                continue

            matched = under_exclusion or _matches_exclusion(relative, exclusion_patterns)
            if matched:
                record(child)
                if child.is_symlink():
                    continue
                if child.is_dir():
                    walk(child, under_exclusion=True)
                continue

            if child.is_dir() and not child.is_symlink():
                walk(child, under_exclusion=False)

    walk(root_path, under_exclusion=False)
    return excluded


def scan_local_folder(
    root: Path | str,
    *,
    limits: AdmissionLimits | None = None,
    exclusions: Iterable[str] = (),
    access_scope: str = "project:local-ingest",
) -> LocalFolderScanResult:
    """Scan ``root`` with bounded recursion and admission gates.

    ``access_scope`` is accepted for call-site clarity; artifact scoping is
    applied later in the pipeline ingest step.
    """
    del access_scope  # used by pipeline; kept here for a stable connector signature
    limits = limits or AdmissionLimits()
    exclusion_patterns = tuple(exclusions)
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise NotADirectoryError(f"ingest root must be a directory: {root_path}")

    inventory: list[InventoryEntry] = []
    admitted: list[AdmittedPayload] = []
    visited_dirs: set[tuple[int, int]] = set()
    excluded_inodes = _collect_excluded_inodes(root_path, exclusion_patterns)
    # Process-local HMAC key for opaque ids; never exported release-facing.
    id_key = secrets.token_bytes(32)

    def visit(directory: Path, depth: int) -> None:
        identity = _dir_identity(directory)
        if identity is None:
            rel = directory.relative_to(root_path).as_posix()
            if rel and rel != ".":
                inventory.append(
                    _entry(
                        relative_package_path=rel,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.UNREADABLE,
                        id_key=id_key,
                    )
                )
            return
        if identity in visited_dirs:
            rel = directory.relative_to(root_path).as_posix()
            if rel and rel != ".":
                inventory.append(
                    _entry(
                        relative_package_path=rel,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.SYMLINK_CYCLE,
                        id_key=id_key,
                    )
                )
            return
        visited_dirs.add(identity)

        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError:
            rel = directory.relative_to(root_path).as_posix()
            if rel and rel != ".":
                inventory.append(
                    _entry(
                        relative_package_path=rel,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.UNREADABLE,
                        id_key=id_key,
                    )
                )
            return

        for child in children:
            try:
                raw_relative = child.relative_to(root_path).as_posix()
            except ValueError:
                inventory.append(
                    _entry(
                        relative_package_path=encode_unsafe_relative_path(child.name),
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.PATH_TRAVERSAL,
                        id_key=id_key,
                    )
                )
                continue

            # Quarantine backslash filenames before any rewrite/normalization.
            # Still record the inode when the path falls under an exclusion so a
            # hard-link alias cannot admit the scoped-out content.
            if "\\" in raw_relative or any(
                "\\" in part for part in child.relative_to(root_path).parts
            ):
                if _matches_exclusion(raw_relative, exclusion_patterns):
                    identity = _inode_identity(child, follow_symlinks=False)
                    if identity is not None:
                        excluded_inodes.add(identity)
                inventory.append(
                    _entry(
                        relative_package_path=encode_unsafe_relative_path(raw_relative),
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.PATH_TRAVERSAL,
                        id_key=id_key,
                    )
                )
                continue

            try:
                relative = normalize_relative_package_path(raw_relative)
            except ValueError:
                if _matches_exclusion(raw_relative, exclusion_patterns):
                    identity = _inode_identity(child, follow_symlinks=False)
                    if identity is not None:
                        excluded_inodes.add(identity)
                inventory.append(
                    _entry(
                        relative_package_path=encode_unsafe_relative_path(raw_relative),
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.PATH_TRAVERSAL,
                        id_key=id_key,
                    )
                )
                continue

            if _matches_exclusion(relative, exclusion_patterns):
                identity = _inode_identity(child, follow_symlinks=False)
                if identity is not None:
                    excluded_inodes.add(identity)
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.EXCLUDED,
                        reason=AdmissionReason.EXPLICIT_EXCLUSION,
                        id_key=id_key,
                    )
                )
                continue

            if depth > limits.max_depth:
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.MAX_DEPTH_EXCEEDED,
                        id_key=id_key,
                    )
                )
                continue

            if child.is_symlink():
                # strict=True fails closed on loops/dangling links across 3.12 and 3.13.
                try:
                    resolved_target = child.resolve(strict=True)
                except (OSError, RuntimeError):
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.SYMLINK_CYCLE,
                            id_key=id_key,
                        )
                    )
                    continue
                if not _is_under_root(resolved_target, root_path):
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.SYMLINK_ESCAPE,
                            id_key=id_key,
                        )
                    )
                    continue
                try:
                    target_rel_raw = resolved_target.relative_to(root_path).as_posix()
                except ValueError:
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.SYMLINK_ESCAPE,
                            id_key=id_key,
                        )
                    )
                    continue
                if target_rel_raw not in ("", "."):
                    try:
                        target_relative = normalize_relative_package_path(target_rel_raw)
                    except ValueError:
                        inventory.append(
                            _entry(
                                relative_package_path=relative,
                                disposition=AdmissionDisposition.QUARANTINED,
                                reason=AdmissionReason.SYMLINK_ESCAPE,
                                id_key=id_key,
                            )
                        )
                        continue
                    if _matches_exclusion(target_relative, exclusion_patterns):
                        target_identity = _inode_identity(resolved_target, follow_symlinks=False)
                        if target_identity is not None:
                            excluded_inodes.add(target_identity)
                        inventory.append(
                            _entry(
                                relative_package_path=relative,
                                disposition=AdmissionDisposition.EXCLUDED,
                                reason=AdmissionReason.EXPLICIT_EXCLUSION,
                                id_key=id_key,
                            )
                        )
                        continue
                # Never follow symlinks for admission: closes alias exclusion
                # bypass and TOCTOU races between resolve and read.
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=(
                            AdmissionReason.DIRECTORY_SYMLINK
                            if resolved_target.is_dir()
                            else AdmissionReason.FILE_SYMLINK
                        ),
                        id_key=id_key,
                    )
                )
                continue

            if child.is_dir():
                visit(child, depth + 1)
                continue

            if not child.is_file():
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.NOT_A_FILE,
                        id_key=id_key,
                    )
                )
                continue

            file_identity = _inode_identity(child, follow_symlinks=False)
            if file_identity is not None and file_identity in excluded_inodes:
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.EXCLUDED,
                        reason=AdmissionReason.EXPLICIT_EXCLUSION,
                        id_key=id_key,
                    )
                )
                continue

            if not suffix_is_allowed(relative, limits):
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.UNSUPPORTED_TYPE,
                        id_key=id_key,
                        media_type=media_type_for_relative_path(relative),
                    )
                )
                continue

            try:
                size = child.stat().st_size
            except OSError:
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.UNREADABLE,
                        id_key=id_key,
                    )
                )
                continue

            if size > limits.max_file_bytes:
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.OVERSIZED,
                        id_key=id_key,
                        media_type=media_type_for_relative_path(relative),
                        byte_size=size,
                    )
                )
                continue

            try:
                payload = child.read_bytes()
            except OSError:
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.UNREADABLE,
                        id_key=id_key,
                        media_type=media_type_for_relative_path(relative),
                        byte_size=size,
                    )
                )
                continue

            digest = sha256_digest(payload)
            media_type = media_type_for_relative_path(relative) or "application/octet-stream"
            entry = _entry(
                relative_package_path=relative,
                disposition=AdmissionDisposition.ADMITTED,
                reason=AdmissionReason.OK,
                id_key=id_key,
                media_type=media_type,
                byte_size=len(payload),
                digest=digest,
            )
            inventory.append(entry)
            admitted.append(
                AdmittedPayload(
                    opaque_id=entry.opaque_id,
                    relative_package_path=entry.relative_package_path,
                    media_type=media_type,
                    digest=digest,
                    payload=payload,
                )
            )

    visit(root_path, depth=0)
    inventory.sort(key=lambda item: item.relative_package_path)
    admitted.sort(key=lambda item: item.relative_package_path)
    return LocalFolderScanResult(inventory=tuple(inventory), admitted=tuple(admitted))
