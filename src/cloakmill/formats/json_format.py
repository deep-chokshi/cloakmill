"""JSON / JSONL structured-field extraction for admitted payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import CoverageState, SurfaceKind
from cloakmill.domain.locators import FieldPathLocator
from cloakmill.formats.common import is_schema_safe_key, part_id_for
from cloakmill.formats.text_format import ExtractedParts

# FieldPathLocator rejects empty string segments; encode JSON "" keys explicitly.
EMPTY_KEY_SEGMENT = "$empty_key"
# Bare JSON/JSONL scalar documents use this reserved root sentinel (not a real key).
ROOT_SEGMENT = "$root"
# Literal object keys that start with "$" (including sentinel names) are escaped.
LITERAL_KEY_PREFIX = "$lit:"


@dataclass(frozen=True, slots=True)
class JsonExtractResult(ExtractedParts):
    parse_error: str | None = None
    skipped_leaves: int = 0


def encode_field_key(key: object) -> str | None:
    """Encode a JSON object key into a FieldPathLocator segment.

    Empty keys become ``EMPTY_KEY_SEGMENT``. Any key that starts with ``$`` is
    prefixed with ``LITERAL_KEY_PREFIX`` so reserved sentinels never collide with
    real property names. Callers must reject non-schema keys before encoding.
    """
    if not isinstance(key, str):
        return None
    if key == "":
        return EMPTY_KEY_SEGMENT
    if key.startswith("$"):
        return f"{LITERAL_KEY_PREFIX}{key}"
    return key


def decode_field_key(segment: str) -> str:
    """Decode a FieldPathLocator segment back to a JSON object key."""
    if segment == EMPTY_KEY_SEGMENT:
        return ""
    if segment.startswith(LITERAL_KEY_PREFIX):
        return segment[len(LITERAL_KEY_PREFIX) :]
    return segment


def is_root_scalar_path(path: tuple[str | int, ...]) -> bool:
    """Return True when ``path`` addresses a bare JSON scalar document."""
    return path == (ROOT_SEGMENT,)


def is_jsonl_root_scalar_path(path: tuple[str | int, ...]) -> bool:
    """Return True when ``path`` addresses a bare JSONL scalar line."""
    return len(path) == 2 and isinstance(path[0], int) and path[1] == ROOT_SEGMENT


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
) -> str | None:
    """Walk JSON values, emitting stringable leaves; count anything dropped.

    Returns an error code when encoded object-key segments collide within one
    object (fail closed). Otherwise returns None.
    """
    text = _scalar_text(value) if not isinstance(value, dict | list) else None
    if text is not None:
        if path:
            out.append((path, text))
        elif text != "":
            out.append(((ROOT_SEGMENT,), text))
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            error = _walk_values(item, (*path, index), out, skipped)
            if error is not None:
                return error
        return None
    if isinstance(value, dict):
        seen_encoded: set[str] = set()
        for key in sorted(value, key=lambda item: str(item)):
            if not isinstance(key, str) or not is_schema_safe_key(key):
                # Writers cannot rename keys; person-keyed / non-schema keys fail closed.
                return "UncoveredKeys"
            encoded = encode_field_key(key)
            if encoded is None:
                skipped[0] += 1
                continue
            if encoded == ROOT_SEGMENT or encoded in seen_encoded:
                return "EncodedKeyCollision"
            seen_encoded.add(encoded)
            error = _walk_values(value[key], (*path, encoded), out, skipped)
            if error is not None:
                return error
        return None
    skipped[0] += 1
    return None


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
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return JsonExtractResult(parts=(), parse_error=type(exc).__name__)

    leaves: list[tuple[tuple[str | int, ...], str]] = []
    skipped = [0]
    try:
        if isinstance(document, str):
            leaves.append(((ROOT_SEGMENT,), document))
        else:
            collision = _walk_values(document, (), leaves, skipped)
            if collision is not None:
                return JsonExtractResult(parts=(), parse_error=collision)
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
        except (json.JSONDecodeError, ValueError):
            return JsonExtractResult(parts=(), parse_error="JSONDecodeError")
        leaves: list[tuple[tuple[str | int, ...], str]] = []
        skipped = [0]
        try:
            # Every bare scalar line (string/number/bool/null) uses the root
            # sentinel so writers accept the path; containers walk under line_no.
            if not isinstance(document, dict | list):
                text = _scalar_text(document)
                if text is None:
                    return JsonExtractResult(
                        parts=(),
                        parse_error="SkippedLeaves",
                        skipped_leaves=1,
                    )
                leaves.append(((line_no, ROOT_SEGMENT), text))
            else:
                collision = _walk_values(document, (line_no,), leaves, skipped)
                if collision is not None:
                    return JsonExtractResult(parts=(), parse_error=collision)
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
