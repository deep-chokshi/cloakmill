"""Dispatch admitted payloads to JSON / CSV / text extractors."""

from __future__ import annotations

from dataclasses import dataclass

from cloakmill.domain.artifacts import Part
from cloakmill.formats.csv_format import extract_csv_parts
from cloakmill.formats.json_format import extract_json_parts, extract_jsonl_parts
from cloakmill.formats.text_format import extract_text_parts


@dataclass(frozen=True, slots=True)
class FormatExtractResult:
    parts: tuple[Part, ...]
    ok: bool
    error: str | None = None


def extract_parts_for_media_type(
    *,
    artifact_version_id: str,
    media_type: str,
    payload: bytes,
) -> FormatExtractResult:
    """Extract domain Parts for a declared media type."""
    if media_type == "application/json":
        result = extract_json_parts(
            artifact_version_id=artifact_version_id,
            payload=payload,
        )
        if result.parse_error:
            return FormatExtractResult(parts=(), ok=False, error=result.parse_error)
        return FormatExtractResult(parts=result.parts, ok=True)

    if media_type == "application/x-ndjson":
        result = extract_jsonl_parts(
            artifact_version_id=artifact_version_id,
            payload=payload,
        )
        if result.parse_error:
            return FormatExtractResult(parts=(), ok=False, error=result.parse_error)
        return FormatExtractResult(parts=result.parts, ok=True)

    if media_type == "text/csv":
        result = extract_csv_parts(
            artifact_version_id=artifact_version_id,
            payload=payload,
        )
        if result.parse_error:
            return FormatExtractResult(parts=(), ok=False, error=result.parse_error)
        return FormatExtractResult(parts=result.parts, ok=True)

    if media_type == "text/plain":
        result = extract_text_parts(
            artifact_version_id=artifact_version_id,
            payload=payload,
        )
        return FormatExtractResult(parts=result.parts, ok=True)

    return FormatExtractResult(parts=(), ok=False, error="unsupported_media_type")
