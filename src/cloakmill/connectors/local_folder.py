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

_DIR_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
_FILE_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC
if hasattr(os, "O_NOFOLLOW"):
    _DIR_OPEN_FLAGS |= os.O_NOFOLLOW
    _FILE_OPEN_FLAGS |= os.O_NOFOLLOW


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
    - ``**/name`` — name at any depth, including the package root
    - ``*.ext`` / other fnmatch globs against the path and ancestors

    Leading ``./`` and ``/``, and any trailing ``/``, are stripped so spellings
    such as ``./secrets/**``, ``/secrets/**``, ``secrets/``, and ``secrets/**/``
    all work. Backslashes are rejected.
    """
    text = pattern.strip()
    if not text:
        raise ValueError("exclusion pattern must be non-empty")
    if "\\" in text:
        raise ValueError(f"exclusion pattern must not contain backslashes: {pattern!r}")
    while text.startswith("./"):
        text = text[2:]
    # Keep a leading **/ (any-depth) but strip a lone absolute slash.
    if text.startswith("**/"):
        rest = text[3:].lstrip("/")
        text = f"**/{rest}" if rest else "**"
    else:
        text = text.lstrip("/")
    # Always strip trailing slashes so secrets/**/ → secrets/**
    text = text.rstrip("/")
    if not text or text in {".", "..", "**"}:
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


def _pattern_match_forms(pattern: str) -> tuple[str, ...]:
    """Return pattern forms to evaluate (expand leading ``**/`` to also match at root)."""
    if pattern.startswith("**/"):
        rest = pattern[3:]
        return (pattern, rest) if rest else (pattern,)
    return (pattern,)


def _matches_one_pattern(candidate: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(candidate, pattern):
        return True
    # Directory-prefix style exclusions such as "secrets/**".
    if pattern.endswith("/**") and (
        candidate == pattern[:-3] or candidate.startswith(pattern[:-2])
    ):
        return True
    # Bare directory/file name excludes that path and everything beneath it.
    if candidate == pattern or candidate.startswith(f"{pattern}/"):
        return True
    # Any-depth suffix: candidate ends with /pattern (for **/name expanded form).
    return candidate.endswith(f"/{pattern}")


def _matches_exclusion(relative_path: str, patterns: Sequence[str]) -> bool:
    """Match exclusions against the path and every ancestor (resolved or lexical)."""
    candidates = _path_and_ancestors(relative_path)
    for pattern in patterns:
        for form in _pattern_match_forms(pattern):
            for candidate in candidates:
                if _matches_one_pattern(candidate, form):
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


def _join_relative(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def _fstat_identity(fd: int) -> tuple[int, int] | None:
    try:
        info = os.fstat(fd)
    except OSError:
        return None
    return (info.st_dev, info.st_ino)


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


def _collect_excluded_inodes(
    root_fd: int,
    exclusion_patterns: Sequence[str],
) -> _ExcludedInodeScan:
    """Walk via dirfds and record inodes for every excluded path and descendant."""
    if not exclusion_patterns:
        return _ExcludedInodeScan(inodes=frozenset(), incomplete=False)

    excluded: set[tuple[int, int]] = set()
    visited_dirs: set[tuple[int, int]] = set()
    incomplete = False

    def record_fd(fd: int) -> None:
        identity = _fstat_identity(fd)
        if identity is not None:
            excluded.add(identity)

    def record_name(dir_fd: int, name: str) -> None:
        try:
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError:
            nonlocal incomplete
            incomplete = True
            return
        excluded.add((info.st_dev, info.st_ino))
        if stat_module.S_ISLNK(info.st_mode):
            try:
                followed = os.stat(name, dir_fd=dir_fd, follow_symlinks=True)
            except OSError:
                return
            excluded.add((followed.st_dev, followed.st_ino))

    def walk(dir_fd: int, *, relative_prefix: str, under_exclusion: bool) -> None:
        nonlocal incomplete
        dir_id = _fstat_identity(dir_fd)
        if dir_id is None:
            incomplete = True
            return
        if dir_id in visited_dirs:
            return
        visited_dirs.add(dir_id)

        try:
            names = sorted(os.listdir(dir_fd))
        except OSError:
            incomplete = True
            return

        for name in names:
            raw_relative = _join_relative(relative_prefix, name)
            has_backslash = "\\" in name or "\\" in raw_relative

            matched = under_exclusion
            if not matched:
                if has_backslash:
                    matched = _matches_exclusion(raw_relative, exclusion_patterns)
                else:
                    try:
                        relative = normalize_relative_package_path(raw_relative)
                    except ValueError:
                        continue
                    matched = _matches_exclusion(relative, exclusion_patterns)

            try:
                info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError:
                if matched or under_exclusion:
                    incomplete = True
                continue

            is_link = stat_module.S_ISLNK(info.st_mode)
            is_dir = stat_module.S_ISDIR(info.st_mode)

            if matched:
                record_name(dir_fd, name)
                if is_link:
                    continue
                if is_dir:
                    try:
                        child_fd = os.open(name, _DIR_OPEN_FLAGS, dir_fd=dir_fd)
                    except OSError:
                        incomplete = True
                        continue
                    try:
                        walk(
                            child_fd,
                            relative_prefix=raw_relative,
                            under_exclusion=True,
                        )
                    finally:
                        os.close(child_fd)
                continue

            if is_dir and not is_link:
                try:
                    child_fd = os.open(name, _DIR_OPEN_FLAGS, dir_fd=dir_fd)
                except OSError:
                    incomplete = True
                    continue
                try:
                    walk(
                        child_fd,
                        relative_prefix=raw_relative,
                        under_exclusion=False,
                    )
                finally:
                    os.close(child_fd)

    walk(root_fd, relative_prefix="", under_exclusion=False)
    return _ExcludedInodeScan(inodes=frozenset(excluded), incomplete=incomplete)


def scan_local_folder(
    root: Path | str,
    *,
    limits: AdmissionLimits | None = None,
    exclusions: Iterable[str] = (),
    access_scope: str = "project:local-ingest",
) -> LocalFolderScanResult:
    """Scan ``root`` with bounded recursion and admission gates.

    Directory descent and file reads use ``O_NOFOLLOW`` (and ``O_DIRECTORY`` for
    dirs) so symlink swaps cannot escape the ingest root between check and use.

    Exclusion patterns are normalized via :func:`normalize_exclusion_patterns`.
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
    id_key = secrets.token_bytes(32)

    try:
        root_fd = os.open(root_path, _DIR_OPEN_FLAGS)
    except OSError as exc:
        raise NotADirectoryError(f"ingest root must be a directory: {root_path}") from exc

    try:
        exclusion_scan = _collect_excluded_inodes(root_fd, exclusion_patterns)
        excluded_inodes: set[tuple[int, int]] = set(exclusion_scan.inodes)
        exclusion_scan_incomplete = exclusion_scan.incomplete

        def visit(dir_fd: int, *, relative_prefix: str, depth: int) -> None:
            identity = _fstat_identity(dir_fd)
            if identity is None:
                if relative_prefix:
                    inventory.append(
                        _entry(
                            relative_package_path=relative_prefix,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.UNREADABLE,
                            id_key=id_key,
                        )
                    )
                return
            if identity in visited_dirs:
                if relative_prefix:
                    inventory.append(
                        _entry(
                            relative_package_path=relative_prefix,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.SYMLINK_CYCLE,
                            id_key=id_key,
                        )
                    )
                return
            visited_dirs.add(identity)

            try:
                names = sorted(os.listdir(dir_fd))
            except OSError:
                if relative_prefix:
                    inventory.append(
                        _entry(
                            relative_package_path=relative_prefix,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.UNREADABLE,
                            id_key=id_key,
                        )
                    )
                return

            for name in names:
                raw_relative = _join_relative(relative_prefix, name)

                if "\\" in name or "\\" in raw_relative:
                    if _matches_exclusion(raw_relative, exclusion_patterns):
                        try:
                            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                            excluded_inodes.add((info.st_dev, info.st_ino))
                        except OSError:
                            pass
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
                        try:
                            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                            excluded_inodes.add((info.st_dev, info.st_ino))
                        except OSError:
                            pass
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
                    info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
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

                is_link = stat_module.S_ISLNK(info.st_mode)
                is_dir = stat_module.S_ISDIR(info.st_mode)
                is_reg = stat_module.S_ISREG(info.st_mode)

                if _matches_exclusion(relative, exclusion_patterns):
                    excluded_inodes.add((info.st_dev, info.st_ino))
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

                if is_link:
                    # Resolve for classification only; never descend or read through it.
                    link_path = root_path.joinpath(*PurePosixPath(relative).parts)
                    try:
                        resolved_target = link_path.resolve(strict=True)
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
                    try:
                        resolved_target.relative_to(root_path)
                        under_root = True
                    except ValueError:
                        under_root = False
                    if not under_root:
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
                            try:
                                target_stat = resolved_target.stat()
                                excluded_inodes.add((target_stat.st_dev, target_stat.st_ino))
                            except OSError:
                                pass
                            inventory.append(
                                _entry(
                                    relative_package_path=relative,
                                    disposition=AdmissionDisposition.EXCLUDED,
                                    reason=AdmissionReason.EXPLICIT_EXCLUSION,
                                    id_key=id_key,
                                )
                            )
                            continue
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

                if is_dir:
                    try:
                        child_fd = os.open(name, _DIR_OPEN_FLAGS, dir_fd=dir_fd)
                    except OSError:
                        # Became a symlink or vanished between lstat and open.
                        inventory.append(
                            _entry(
                                relative_package_path=relative,
                                disposition=AdmissionDisposition.QUARANTINED,
                                reason=AdmissionReason.DIRECTORY_SYMLINK,
                                id_key=id_key,
                            )
                        )
                        continue
                    try:
                        visit(child_fd, relative_prefix=relative, depth=depth + 1)
                    finally:
                        os.close(child_fd)
                    continue

                if not is_reg:
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.NOT_A_FILE,
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
                    fd = os.open(name, _FILE_OPEN_FLAGS, dir_fd=dir_fd)
                except OSError:
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.UNREADABLE,
                            id_key=id_key,
                            media_type=media_type_for_relative_path(relative),
                        )
                    )
                    continue

                try:
                    opened = os.fstat(fd)
                    if not stat_module.S_ISREG(opened.st_mode):
                        inventory.append(
                            _entry(
                                relative_package_path=relative,
                                disposition=AdmissionDisposition.QUARANTINED,
                                reason=AdmissionReason.NOT_A_FILE,
                                id_key=id_key,
                                media_type=media_type_for_relative_path(relative),
                            )
                        )
                        continue

                    file_identity = (opened.st_dev, opened.st_ino)
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
                    if exclusion_scan_incomplete and opened.st_nlink > 1:
                        inventory.append(
                            _entry(
                                relative_package_path=relative,
                                disposition=AdmissionDisposition.EXCLUDED,
                                reason=AdmissionReason.EXPLICIT_EXCLUSION,
                                id_key=id_key,
                            )
                        )
                        continue

                    size = opened.st_size
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

        visit(root_fd, relative_prefix="", depth=0)
    finally:
        os.close(root_fd)

    inventory.sort(key=lambda item: item.relative_package_path)
    admitted.sort(key=lambda item: item.relative_package_path)
    return LocalFolderScanResult(inventory=tuple(inventory), admitted=tuple(admitted))
