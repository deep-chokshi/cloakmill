"""Bounded local-folder acquisition and admission for offline ingest."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

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


def _matches_exclusion(relative_path: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatchcase(relative_path, pattern):
            return True
        # Also allow directory-prefix style exclusions such as "secrets/**".
        if pattern.endswith("/**") and (
            relative_path == pattern[:-3] or relative_path.startswith(pattern[:-2])
        ):
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
    media_type: str | None = None,
    byte_size: int | None = None,
    digest: str | None = None,
) -> InventoryEntry:
    return InventoryEntry(
        opaque_id=opaque_id_for_relative_path("art", relative_package_path),
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


def _dir_identity(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


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
                    )
                )
                continue

            # Quarantine backslash filenames before any rewrite/normalization.
            if "\\" in raw_relative or any(
                "\\" in part for part in child.relative_to(root_path).parts
            ):
                inventory.append(
                    _entry(
                        relative_package_path=encode_unsafe_relative_path(raw_relative),
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.PATH_TRAVERSAL,
                    )
                )
                continue

            try:
                relative = normalize_relative_package_path(raw_relative)
            except ValueError:
                inventory.append(
                    _entry(
                        relative_package_path=encode_unsafe_relative_path(raw_relative),
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.PATH_TRAVERSAL,
                    )
                )
                continue

            if _matches_exclusion(relative, exclusion_patterns):
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.EXCLUDED,
                        reason=AdmissionReason.EXPLICIT_EXCLUSION,
                    )
                )
                continue

            if depth > limits.max_depth:
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.MAX_DEPTH_EXCEEDED,
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
                        )
                    )
                    continue
                if not _is_under_root(resolved_target, root_path):
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.SYMLINK_ESCAPE,
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
                            )
                        )
                        continue
                    if _matches_exclusion(target_relative, exclusion_patterns):
                        inventory.append(
                            _entry(
                                relative_package_path=relative,
                                disposition=AdmissionDisposition.EXCLUDED,
                                reason=AdmissionReason.EXPLICIT_EXCLUSION,
                            )
                        )
                        continue
                # Never descend through directory symlinks: alias paths would bypass
                # exclusions written against the real package path.
                if resolved_target.is_dir():
                    inventory.append(
                        _entry(
                            relative_package_path=relative,
                            disposition=AdmissionDisposition.QUARANTINED,
                            reason=AdmissionReason.DIRECTORY_SYMLINK,
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
                    )
                )
                continue

            if not suffix_is_allowed(relative, limits):
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.UNSUPPORTED_TYPE,
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
                    )
                )
                continue

            if size > limits.max_file_bytes:
                inventory.append(
                    _entry(
                        relative_package_path=relative,
                        disposition=AdmissionDisposition.QUARANTINED,
                        reason=AdmissionReason.OVERSIZED,
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
