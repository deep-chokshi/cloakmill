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

# FieldPathLocator rejects empty string segments; encode JSON "" keys explicitly.
EMPTY_KEY_SEGMENT = "$empty_key"


@dataclass(frozen=True, slots=True)
class JsonExtractResult(ExtractedParts):
    parse_error: str | None = None
    skipped_leaves: int = 0


def _encode_key(key: object) -> str | None:
    if not isinstance(key, str):
        return None
    if key == "":
        return EMPTY_KEY_SEGMENT
    return key


def _scalar_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if value is None:
        return "null"
    return None


def _walk_values(
    value: Any,
    path: tuple[str | int, ...],
    out: list[tuple[tuple[str | int, ...], str]],
    skipped: list[int],
) -> None:
    """Walk JSON values, emitting stringable leaves; count anything dropped."""
    text = _scalar_text(value) if not isinstance(value, dict | list) else None
    if text is not None:
        if path:
            out.append((path, text))
        elif text != "":
            out.append((("value",), text))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_values(item, (*path, index), out, skipped)
        return
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item)):
            encoded = _encode_key(key)
            if encoded is None:
                skipped[0] += 1
                continue
            _walk_values(value[key], (*path, encoded), out, skipped)
        return
    skipped[0] += 1


def _parts_from_leaves(
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
    """Parse a JSON document and emit parts for extractable leaf fields."""
    try:
        text = payload.decode("utf-8")
        document = json.loads(text)
    except RecursionError:
        return JsonExtractResult(parts=(), parse_error="RecursionError")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return JsonExtractResult(parts=(), parse_error=type(exc).__name__)

    leaves: list[tuple[tuple[str | int, ...], str]] = []
    skipped = [0]
    try:
        if isinstance(document, str):
            leaves.append((("value",), document))
        else:
            _walk_values(document, (), leaves, skipped)
    except RecursionError:
        return JsonExtractResult(parts=(), parse_error="RecursionError")

    if skipped[0] > 0:
        return JsonExtractResult(
            parts=(),
            parse_error="SkippedLeaves",
            skipped_leaves=skipped[0],
        )

    parts = _parts_from_leaves(
        artifact_version_id=artifact_version_id,
        leaves=leaves,
    )
    return JsonExtractResult(parts=tuple(parts), skipped_leaves=0)


def extract_jsonl_parts(
    *,
    artifact_version_id: str,
    payload: bytes,
) -> JsonExtractResult:
    """Parse JSON Lines and emit parts for leaves, keyed by line index."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return JsonExtractResult(parts=(), parse_error="UnicodeDecodeError")

    all_parts: list[Part] = []
    ordinal = 0
    total_skipped = 0
    for line_no, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if line == "":
            continue
        try:
            document = json.loads(line)
        except RecursionError:
            return JsonExtractResult(parts=(), parse_error="RecursionError")
        except json.JSONDecodeError:
            return JsonExtractResult(parts=(), parse_error="JSONDecodeError")
        leaves: list[tuple[tuple[str | int, ...], str]] = []
        skipped = [0]
        try:
            if isinstance(document, str):
                leaves.append(((line_no, "value"), document))
            else:
                _walk_values(document, (line_no,), leaves, skipped)
        except RecursionError:
            return JsonExtractResult(parts=(), parse_error="RecursionError")
        total_skipped += skipped[0]
        if skipped[0] > 0:
            return JsonExtractResult(
                parts=(),
                parse_error="SkippedLeaves",
                skipped_leaves=total_skipped,
            )
        batch = _parts_from_leaves(
            artifact_version_id=artifact_version_id,
            leaves=leaves,
            index_offset=ordinal,
        )
        ordinal += len(batch)
        all_parts.extend(batch)
    return JsonExtractResult(parts=tuple(all_parts), skipped_leaves=0)
