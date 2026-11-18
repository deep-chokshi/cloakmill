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
# Locator prefix for object-key surfaces so key text is detectable coverage.
KEY_SURFACE_PREFIX = "$key"


class DuplicateObjectKeyError(ValueError):
    """JSON object repeated a key; stdlib last-wins parse would hide earlier values.

    Mirrors F09 ``ValidationInputError(... DuplicateObjectKey)`` fail-closed policy.
    """


@dataclass(frozen=True, slots=True)
class JsonExtractResult(ExtractedParts):
    parse_error: str | None = None
    skipped_leaves: int = 0


def _object_pairs_no_duplicates(pairs: list[tuple[Any, Any]]) -> dict[Any, Any]:
    """Fail closed when a JSON object repeats a key (shadowed PII vector)."""
    seen: set[Any] = set()
    out: dict[Any, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateObjectKeyError("DuplicateObjectKey")
        seen.add(key)
        out[key] = value
    return out


def _loads_json_document(text: str) -> Any:
    """Parse JSON, rejecting duplicate object keys (no last-wins)."""
    return json.loads(text, object_pairs_hook=_object_pairs_no_duplicates)


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
    keys: list[tuple[tuple[str | int, ...], str]],
    skipped: list[int],
) -> None:
    """Walk JSON values, emitting stringable leaves and object keys; count drops."""
    text = _scalar_text(value) if not isinstance(value, dict | list) else None
    if text is not None:
        if path:
            out.append((path, text))
        elif text != "":
            out.append((("value",), text))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_values(item, (*path, index), out, keys, skipped)
        return
    if isinstance(value, dict):
        for key_index, key in enumerate(sorted(value, key=lambda item: str(item))):
            encoded = _encode_key(key)
            if encoded is None:
                skipped[0] += 1
                continue
            # Track key text as a surface so identifier-keyed objects are covered.
            keys.append(((KEY_SURFACE_PREFIX, *path, key_index), key))
            _walk_values(value[key], (*path, encoded), out, keys, skipped)
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
    """Parse a JSON document and emit parts for extractable leaf fields.

    Duplicate object keys fail closed (``DuplicateObjectKey``) so shadowed
    values cannot stay invisible while coverage reports PROCESSED.
    """
    try:
        text = payload.decode("utf-8")
        document = _loads_json_document(text)
    except DuplicateObjectKeyError:
        return JsonExtractResult(parts=(), parse_error="DuplicateObjectKey")
    except RecursionError:
        return JsonExtractResult(parts=(), parse_error="RecursionError")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return JsonExtractResult(parts=(), parse_error=type(exc).__name__)

    leaves: list[tuple[tuple[str | int, ...], str]] = []
    keys: list[tuple[tuple[str | int, ...], str]] = []
    skipped = [0]
    try:
        if isinstance(document, str):
            leaves.append((("value",), document))
        else:
            _walk_values(document, (), leaves, keys, skipped)
    except RecursionError:
        return JsonExtractResult(parts=(), parse_error="RecursionError")

    if skipped[0] > 0:
        return JsonExtractResult(
            parts=(),
            parse_error="SkippedLeaves",
            skipped_leaves=skipped[0],
        )

    # Key surfaces first so ordinals stay stable relative to leaf-only extracts.
    surfaces = [*keys, *leaves]
    parts = _parts_from_leaves(
        artifact_version_id=artifact_version_id,
        leaves=surfaces,
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
            document = _loads_json_document(line)
        except DuplicateObjectKeyError:
            return JsonExtractResult(parts=(), parse_error="DuplicateObjectKey")
        except RecursionError:
            return JsonExtractResult(parts=(), parse_error="RecursionError")
        except (json.JSONDecodeError, ValueError):
            return JsonExtractResult(parts=(), parse_error="JSONDecodeError")
        leaves: list[tuple[tuple[str | int, ...], str]] = []
        keys: list[tuple[tuple[str | int, ...], str]] = []
        skipped = [0]
        try:
            if isinstance(document, str):
                leaves.append(((line_no, "value"), document))
            else:
                _walk_values(document, (line_no,), leaves, keys, skipped)
        except RecursionError:
            return JsonExtractResult(parts=(), parse_error="RecursionError")
        total_skipped += skipped[0]
        if skipped[0] > 0:
            return JsonExtractResult(
                parts=(),
                parse_error="SkippedLeaves",
                skipped_leaves=total_skipped,
            )
        surfaces = [*keys, *leaves]
        batch = _parts_from_leaves(
            artifact_version_id=artifact_version_id,
            leaves=surfaces,
            index_offset=ordinal,
        )
        ordinal += len(batch)
        all_parts.extend(batch)
    return JsonExtractResult(parts=tuple(all_parts), skipped_leaves=0)
