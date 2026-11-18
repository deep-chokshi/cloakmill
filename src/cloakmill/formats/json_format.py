"""JSON / JSONL structured-field extraction for admitted payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import CoverageState, SurfaceKind
from cloakmill.domain.locators import FieldPathLocator
from cloakmill.formats.common import part_id_for
from cloakmill.formats.text_format import ExtractedParts


@dataclass(frozen=True, slots=True)
class JsonExtractResult(ExtractedParts):
    parse_error: str | None = None


def _walk_strings(
    value: Any,
    path: tuple[str | int, ...],
    out: list[tuple[tuple[str | int, ...], str]],
) -> None:
    if isinstance(value, str):
        if path:
            out.append((path, value))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_strings(item, (*path, index), out)
        return
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item)):
            if not isinstance(key, str) or key == "":
                continue
            _walk_strings(value[key], (*path, key), out)


def _parts_from_string_leaves(
    *,
    artifact_version_id: str,
    leaves: list[tuple[tuple[str | int, ...], str]],
    index_offset: int = 0,
) -> list[Part]:
    parts: list[Part] = []
    for ordinal, (path, text) in enumerate(leaves):
        parts.append(
            Part(
                opaque_id=part_id_for(artifact_version_id, "json", index_offset + ordinal),
                artifact_version_id=artifact_version_id,
                surface_kind=SurfaceKind.STRUCTURED_FIELD,
                original_locator=FieldPathLocator(path=path),
                coverage_state=CoverageState.PROCESSED,
                content_length=len(text),
            )
        )
    return parts


def extract_json_parts(
    *,
    artifact_version_id: str,
    payload: bytes,
) -> JsonExtractResult:
    """Parse a JSON document and emit parts for string leaf fields."""
    try:
        text = payload.decode("utf-8")
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return JsonExtractResult(parts=(), parse_error=type(exc).__name__)

    leaves: list[tuple[tuple[str | int, ...], str]] = []
    if isinstance(document, str):
        # Root string: use a synthetic single-segment path.
        leaves.append((("value",), document))
    else:
        _walk_strings(document, (), leaves)

    parts = _parts_from_string_leaves(
        artifact_version_id=artifact_version_id,
        leaves=leaves,
    )
    return JsonExtractResult(parts=tuple(parts))


def extract_jsonl_parts(
    *,
    artifact_version_id: str,
    payload: bytes,
) -> JsonExtractResult:
    """Parse JSON Lines and emit parts for string leaves, keyed by line index."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return JsonExtractResult(parts=(), parse_error="UnicodeDecodeError")

    all_parts: list[Part] = []
    ordinal = 0
    for line_no, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if line == "":
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            return JsonExtractResult(parts=(), parse_error="JSONDecodeError")
        leaves: list[tuple[tuple[str | int, ...], str]] = []
        if isinstance(document, str):
            leaves.append(((line_no, "value"), document))
        else:
            _walk_strings(document, (line_no,), leaves)
        batch = _parts_from_string_leaves(
            artifact_version_id=artifact_version_id,
            leaves=leaves,
            index_offset=ordinal,
        )
        ordinal += len(batch)
        all_parts.extend(batch)
    return JsonExtractResult(parts=tuple(all_parts))
