"""Admission limits, dispositions, and integrity digests for offline ingest."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath


class AdmissionDisposition(StrEnum):
    """How an inventoried path was handled at the admission gate."""

    ADMITTED = "admitted"
    QUARANTINED = "quarantined"
    EXCLUDED = "excluded"


class AdmissionReason(StrEnum):
    """Machine-stable reason codes. Never embed absolute filesystem paths."""

    OK = "ok"
    EXPLICIT_EXCLUSION = "explicit_exclusion"
    SYMLINK_ESCAPE = "symlink_escape"
    SYMLINK_CYCLE = "symlink_cycle"
    DIRECTORY_SYMLINK = "directory_symlink"
    PATH_TRAVERSAL = "path_traversal"
    MAX_DEPTH_EXCEEDED = "max_depth_exceeded"
    OVERSIZED = "oversized"
    UNSUPPORTED_TYPE = "unsupported_type"
    UNREADABLE = "unreadable"
    NOT_A_FILE = "not_a_file"
    PARSE_FAILED = "parse_failed"


# Default allowlist for the first offline ingest path (JSON / CSV / text).
DEFAULT_ALLOWED_SUFFIXES: frozenset[str] = frozenset({".json", ".jsonl", ".csv", ".txt"})

_SUFFIX_MEDIA_TYPES: dict[str, str] = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


@dataclass(frozen=True, slots=True)
class AdmissionLimits:
    """Hard bounds for local-folder admission."""

    max_depth: int = 8
    max_file_bytes: int = 10 * 1024 * 1024
    allowed_suffixes: frozenset[str] = DEFAULT_ALLOWED_SUFFIXES

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if self.max_file_bytes < 0:
            raise ValueError("max_file_bytes must be >= 0")
        normalized = frozenset(
            suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}"
            for suffix in self.allowed_suffixes
        )
        object.__setattr__(self, "allowed_suffixes", normalized)


def encode_unsafe_relative_path(relative_path: str) -> str:
    """Encode backslashes so quarantine rows do not invent path separators."""
    return relative_path.replace("\\", "%5C")


def normalize_relative_package_path(relative_path: str) -> str:
    """Normalize to a posix relative package locator without drive or root.

    Backslashes are rejected rather than rewritten into separators, so a POSIX
    filename containing ``\\`` cannot spoof a multi-segment package path.
    """
    if "\\" in relative_path:
        raise ValueError("relative package path must not contain backslash characters")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or path.anchor:
        raise ValueError("relative package path must not be absolute")
    parts = [part for part in path.parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("relative package path must not contain '..'")
    if not parts:
        raise ValueError("relative package path must not be empty")
    return PurePosixPath(*parts).as_posix()


def media_type_for_relative_path(relative_path: str) -> str | None:
    """Return a declared media type for an allowed suffix, else None."""
    suffix = PurePosixPath(relative_path).suffix.lower()
    if suffix in _SUFFIX_MEDIA_TYPES:
        return _SUFFIX_MEDIA_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(relative_path)
    return guessed


def suffix_is_allowed(relative_path: str, limits: AdmissionLimits) -> bool:
    suffix = PurePosixPath(relative_path).suffix.lower()
    return suffix in limits.allowed_suffixes


def sha256_digest(payload: bytes) -> str:
    """Return a private integrity digest in the domain ``alg:hex`` form."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def opaque_id_for_relative_path(prefix: str, relative_path: str) -> str:
    """Deterministic opaque id from a relative package path (not absolute)."""
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"
