"""Immutable artifact version and extracted part contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cloakmill.domain.enums import CoverageState, SurfaceKind
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_non_empty_str, require_opaque_id
from cloakmill.domain.locators import (
    OriginalLocator,
    locator_from_dict,
    validate_locator,
)

_DIGEST_RE = re.compile(r"^(sha256|sha384|sha512):[0-9a-f]{32,128}$")


@dataclass(frozen=True, slots=True)
class NormalizationSpan:
    """Maps a normalized span back to immutable original coordinates."""

    normalized_start: int
    normalized_end: int
    original_start: int
    original_end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_start": self.normalized_start,
            "normalized_end": self.normalized_end,
            "original_start": self.original_start,
            "original_end": self.original_end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizationSpan:
        try:
            span = cls(
                normalized_start=data["normalized_start"],
                normalized_end=data["normalized_end"],
                original_start=data["original_start"],
                original_end=data["original_end"],
            )
        except (KeyError, TypeError) as exc:
            raise DomainValidationError(f"invalid normalization span: {exc}") from exc
        validate_normalization_span(span)
        return span


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    """Immutable versioned source artifact admitted into processing."""

    opaque_id: str
    source_version: str
    private_integrity_digest: str
    access_scope: str
    media_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "source_version": self.source_version,
            "private_integrity_digest": self.private_integrity_digest,
            "access_scope": self.access_scope,
        }
        if self.media_type is not None:
            payload["media_type"] = self.media_type
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactVersion:
        if not isinstance(data, dict):
            raise DomainValidationError("artifact version must be an object")
        artifact = cls(
            opaque_id=data.get("opaque_id", ""),
            source_version=data.get("source_version", ""),
            private_integrity_digest=data.get("private_integrity_digest", ""),
            access_scope=data.get("access_scope", ""),
            media_type=data.get("media_type"),
        )
        validate_artifact_version(artifact)
        return artifact


@dataclass(frozen=True, slots=True)
class Part:
    """Extracted readable surface tied to an immutable artifact version."""

    opaque_id: str
    artifact_version_id: str
    surface_kind: SurfaceKind
    original_locator: OriginalLocator
    coverage_state: CoverageState
    content_length: int | None = None
    normalization_map: tuple[NormalizationSpan, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "artifact_version_id": self.artifact_version_id,
            "surface_kind": self.surface_kind.value,
            "original_locator": self.original_locator.to_dict(),
            "coverage_state": self.coverage_state.value,
            "normalization_map": [span.to_dict() for span in self.normalization_map],
        }
        if self.content_length is not None:
            payload["content_length"] = self.content_length
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Part:
        if not isinstance(data, dict):
            raise DomainValidationError("part must be an object")
        try:
            surface_kind = SurfaceKind(data["surface_kind"])
            coverage_state = CoverageState(data["coverage_state"])
            locator = locator_from_dict(data["original_locator"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid part fields: {exc}") from exc

        raw_map = data.get("normalization_map", [])
        if not isinstance(raw_map, list):
            raise DomainValidationError("normalization_map must be a list")
        normalization_map = tuple(NormalizationSpan.from_dict(item) for item in raw_map)

        content_length = data.get("content_length")
        if content_length is not None and (
            isinstance(content_length, bool) or not isinstance(content_length, int)
        ):
            raise DomainValidationError("content_length must be an int when present")

        part = cls(
            opaque_id=data.get("opaque_id", ""),
            artifact_version_id=data.get("artifact_version_id", ""),
            surface_kind=surface_kind,
            original_locator=locator,
            coverage_state=coverage_state,
            content_length=content_length,
            normalization_map=normalization_map,
        )
        validate_part(part)
        return part


def validate_normalization_span(span: NormalizationSpan) -> None:
    for name, value in (
        ("normalized_start", span.normalized_start),
        ("normalized_end", span.normalized_end),
        ("original_start", span.original_start),
        ("original_end", span.original_end),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise DomainValidationError(f"{name} must be an int")
        if value < 0:
            raise DomainValidationError(f"{name} must be >= 0, got {value}")
    if span.normalized_end < span.normalized_start:
        raise DomainValidationError("normalized_end must be >= normalized_start")
    if span.original_end < span.original_start:
        raise DomainValidationError("original_end must be >= original_start")


def validate_artifact_version(artifact: ArtifactVersion) -> None:
    require_opaque_id(artifact.opaque_id, "opaque_id")
    require_non_empty_str(artifact.source_version, "source_version")
    require_non_empty_str(artifact.access_scope, "access_scope")
    digest = artifact.private_integrity_digest
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise DomainValidationError(
            "private_integrity_digest must look like '<alg>:<hex>' "
            f"(supported algs: sha256, sha384, sha512); got {digest!r}"
        )
    if artifact.media_type is not None:
        require_non_empty_str(artifact.media_type, "media_type")


def validate_part(part: Part) -> None:
    require_opaque_id(part.opaque_id, "opaque_id")
    require_opaque_id(part.artifact_version_id, "artifact_version_id")
    if not isinstance(part.surface_kind, SurfaceKind):
        raise DomainValidationError("surface_kind must be a SurfaceKind")
    if not isinstance(part.coverage_state, CoverageState):
        raise DomainValidationError("coverage_state must be a CoverageState")
    if part.content_length is not None:
        if isinstance(part.content_length, bool) or not isinstance(part.content_length, int):
            raise DomainValidationError("content_length must be an int when present")
        if part.content_length < 0:
            raise DomainValidationError("content_length must be >= 0")
    validate_locator(part.original_locator)
    for span in part.normalization_map:
        validate_normalization_span(span)
        if part.content_length is not None and span.original_end > part.content_length:
            raise DomainValidationError(
                "normalization map original_end exceeds part content_length"
            )
