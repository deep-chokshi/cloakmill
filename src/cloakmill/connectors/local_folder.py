"""Bounded local-folder acquisition and admission for offline ingest."""

from __future__ import annotations

import fnmatch
import os
import secrets
import stat as stat_module
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


@dataclass(frozen=True, slots=True)
class _ExcludedInodeScan:
    """Excluded inode set plus whether enumeration under exclusions was incomplete."""

    inodes: frozenset[tuple[int, int]]
    incomplete: bool


def normalize_exclusion_pattern(pattern: str) -> str:
    """Normalize an exclusion to a root-relative POSIX pattern.

    Grammar (after normalization):
    - ``name`` / ``path/seg`` — exact path or ancestor bare-name match
    - ``path/**`` — directory prefix match
    - ``*.ext`` / other fnmatch globs against the path and ancestors

    Leading ``./`` and ``/``, and a lone trailing ``/``, are stripped so common
    spellings such as ``./secrets/**``, ``/secrets/**``, and ``secrets/`` work.
    Backslashes are rejected (they are not path separators in this dialect).
    """
    text = pattern.strip()
    if not text:
        raise ValueError("exclusion pattern must be non-empty")
    if "\\" in text:
        raise ValueError(f"exclusion pattern must not contain backslashes: {pattern!r}")
    while text.startswith("./"):
        text = text[2:]
    text = text.lstrip("/")
    if text.endswith("/") and not text.endswith("**/"):
        text = text.rstrip("/")
    if not text or text in {".", ".."}:
        raise ValueError(f"exclusion pattern is empty after normalization: {pattern!r}")
    return text


def normalize_exclusion_patterns(patterns: Iterable[str]) -> tuple[str, ...]:
    """Normalize and de-duplicate exclusion patterns; fail closed on invalid input."""
    normalized: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        item = normalize_exclusion_pattern(pattern)
        if item not in seen:
            seen.add(item)
            normalized.append(item)
    return tuple(normalized)


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
        result = path.stat() if follow_symlinks else path.lstat()
    except OSError:
        return None
    return (result.st_dev, result.st_ino)


def _dir_identity(path: Path) -> tuple[int, int] | None:
    return _inode_identity(path, follow_symlinks=True)


def _collect_excluded_inodes(
    root_path: Path,
    exclusion_patterns: Sequence[str],
) -> _ExcludedInodeScan:
    """Walk the tree and record inodes for every excluded path and descendant.

    Hard links outside an exclusion prefix share ``(st_dev, st_ino)`` with the
    scoped-out file; collecting those identities closes the bypass.

    If any directory under an exclusion cannot be enumerated, ``incomplete`` is
    set so admission can fail closed for multiply-linked files.
    """
    if not exclusion_patterns:
        return _ExcludedInodeScan(inodes=frozenset(), incomplete=False)

    excluded: set[tuple[int, int]] = set()
    visited_dirs: set[tuple[int, int]] = set()
    incomplete = False

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
        nonlocal incomplete
        dir_id = _inode_identity(directory, follow_symlinks=False)
        if dir_id is None:
            if under_exclusion or exclusion_patterns:
                incomplete = True
            return
        if dir_id in visited_dirs:
            return
        visited_dirs.add(dir_id)

        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError:
            # Fail closed: missing excluded-tree inodes must not silently admit aliases.
            incomplete = True
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
    return _ExcludedInodeScan(inodes=frozenset(excluded), incomplete=incomplete)


def _open_regular_file_nofollow(
    path: Path,
) -> tuple[int, os.stat_result] | None:
    """Open ``path`` without following symlinks; return ``(fd, fstat)`` or ``None``."""
    flags = os.O_RDONLY | os.O_CLOEXEC
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
    except OSError:
        os.close(fd)
        return None
    if not stat_module.S_ISREG(info.st_mode):
        os.close(fd)
        return None
    return fd, info


def _read_fd(fd: int, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


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

    Exclusion patterns are normalized via :func:`normalize_exclusion_patterns`
    (root-relative POSIX; leading ``./``/``/`` and trailing ``/`` stripped).
    """
    del access_scope  # used by pipeline; kept here for a stable connector signature
    limits = limits or AdmissionLimits()
    exclusion_patterns = normalize_exclusion_patterns(exclusions)
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise NotADirectoryError(f"ingest root must be a directory: {root_path}")

    inventory: list[InventoryEntry] = []
    admitted: list[AdmittedPayload] = []
    visited_dirs: set[tuple[int, int]] = set()
    exclusion_scan = _collect_excluded_inodes(root_path, exclusion_patterns)
    excluded_inodes: set[tuple[int, int]] = set(exclusion_scan.inodes)
    exclusion_scan_incomplete = exclusion_scan.incomplete
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
                    file_id = _inode_identity(child, follow_symlinks=False)
                    if file_id is not None:
                        excluded_inodes.add(file_id)
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
                    file_id = _inode_identity(child, follow_symlinks=False)
                    if file_id is not None:
                        excluded_inodes.add(file_id)
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
                file_id = _inode_identity(child, follow_symlinks=False)
                if file_id is not None:
                    excluded_inodes.add(file_id)
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
                # Inventory symlinks as quarantined; never open/read via path
                # re-resolution (TOCTOU). File bytes are only admitted through
                # O_NOFOLLOW opens of non-symlink directory entries.
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

            # Pin the inode with O_NOFOLLOW so type/size/exclusion/read share one fd.
            opened = _open_regular_file_nofollow(child)
            if opened is None:
                # Symlink swap after listing, non-regular, or unreadable — fail closed.
                if child.is_symlink():
                    open_reason = AdmissionReason.FILE_SYMLINK
                elif child.exists() and not child.is_file():
                    open_reason = AdmissionReason.NOT_A_FILE
                else:
                    open_reason = AdmissionReason.UNREADABLE
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=open_reason,
                        id_key=id_key,
                        media_type=media_type_for_relative_path(relative),
                    )
                )
                continue

            fd, info = opened
            try:
                file_identity = (info.st_dev, info.st_ino)
                if file_identity in excluded_inodes:
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.EXCLUDED,
                            reason=AdmissionReason.EXPLICIT_EXCLUSION,
                            id_key=id_key,
                        )
                    )
                    continue
                # Incomplete exclusion enumeration: refuse multiply-linked files.
                if exclusion_scan_incomplete and info.st_nlink > 1:
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.EXCLUDED,
                            reason=AdmissionReason.EXPLICIT_EXCLUSION,
                            id_key=id_key,
                        )
                    )
                    continue

                size = info.st_size
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
                    payload = _read_fd(fd, size)
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
            finally:
                os.close(fd)

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
