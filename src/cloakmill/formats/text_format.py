"""Plain-text part extraction for admitted payloads."""

from __future__ import annotations

from dataclasses import dataclass

from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import CoverageState, SurfaceKind, TextOffsetUnit
from cloakmill.domain.locators import TextOffsetLocator
from cloakmill.formats.common import part_id_for


@dataclass(frozen=True, slots=True)
class ExtractedParts:
    parts: tuple[Part, ...]
    decode_errors: bool = False


def extract_text_parts(
    *,
    artifact_version_id: str,
    payload: bytes,
) -> ExtractedParts:
    """Decode UTF-8 text and emit one TEXT surface covering the full content."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("utf-8", errors="replace")
        decode_errors = True
    else:
        decode_errors = False

    content_length = len(text)
    part = Part(
        opaque_id=part_id_for(artifact_version_id, "text", 0),
        artifact_version_id=artifact_version_id,
        surface_kind=SurfaceKind.TEXT,
        original_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=content_length,
        ),
        coverage_state=CoverageState.PROCESSED,
        content_length=content_length,
    )
    return ExtractedParts(parts=(part,), decode_errors=decode_errors)
