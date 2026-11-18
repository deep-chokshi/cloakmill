"""Extract candidate text surfaces for independent validation scanning."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import CoverageState, SurfaceKind, TextOffsetUnit
from cloakmill.domain.locators import FieldPathLocator, TextOffsetLocator
from cloakmill.formats.common import part_id_for
from cloakmill.formats.json_format import (
    ROOT_SEGMENT,
    decode_field_key,
    encode_field_key,
)
from cloakmill.validation.coverage import CandidateArtifact
from cloakmill.validation.errors import ValidationInputError


@dataclass(frozen=True, slots=True)
class CandidateSurface:
    """One readable surface taken from a candidate artifact."""

    artifact_version_id: str
    media_type: str
    part: Part
    content: str
    field_name: str | None = None


def iter_candidate_surfaces(artifact: CandidateArtifact) -> tuple[CandidateSurface, ...]:
    """Yield structured/text surfaces from a candidate payload for scanning."""
    if artifact.excluded:
        return ()
    if artifact.media_type == "application/json":
        return tuple(_json_surfaces(artifact))
    if artifact.media_type == "application/x-ndjson":
        return tuple(_jsonl_surfaces(artifact))
    if artifact.media_type == "text/csv":
        return tuple(_csv_surfaces(artifact))
    if artifact.media_type == "text/plain":
        return tuple(_text_surfaces(artifact))
    raise ValidationInputError(f"unsupported candidate media type: {artifact.media_type!r}")


def read_field_value(
    artifact: CandidateArtifact,
    path: tuple[str | int, ...],
) -> str | None:
    """Return the stringable value at ``path``, or None when missing."""
    if artifact.excluded or not artifact.payload:
        return None
    if artifact.media_type == "application/json":
        try:
            document = json.loads(artifact.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return _scalar_at_path(document, path)
    if artifact.media_type == "application/x-ndjson":
        try:
            lines = [
                json.loads(raw)
                for raw in artifact.payload.decode("utf-8").splitlines()
                if raw.strip()
            ]
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not path:
            return None
        line_index = path[0]
        if not isinstance(line_index, int) or line_index < 0 or line_index >= len(lines):
            return None
        return _scalar_at_path(lines[line_index], path[1:])
    if artifact.media_type == "text/csv":
        return _csv_value_at_path(artifact.payload, path)
    if artifact.media_type == "text/plain":
        try:
            text = artifact.payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if path == ("body",) or path == ():
            return text
        return None
    return None


def field_paths_for_artifact(artifact: CandidateArtifact) -> frozenset[tuple[str | int, ...]]:
    """Return extractable field paths for schema comparison."""
    paths: set[tuple[str | int, ...]] = set()
    for surface in iter_candidate_surfaces(artifact):
        locator = surface.part.original_locator
        if isinstance(locator, FieldPathLocator):
            paths.add(locator.path)
    return frozenset(paths)


def slice_observation_text(content: str, start: int, end: int) -> str:
    """Slice Unicode codepoint offsets from content (private-boundary use only)."""
    return content[start:end]


def _json_surfaces(artifact: CandidateArtifact) -> Iterator[CandidateSurface]:
    try:
        document = json.loads(artifact.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationInputError(f"candidate JSON reparse failed: {type(exc).__name__}") from exc
    leaves: list[tuple[tuple[str | int, ...], str]] = []
    if isinstance(document, str):
        leaves.append(((ROOT_SEGMENT,), document))
    else:
        collision = _walk_json(document, (), leaves)
        if collision is not None:
            raise ValidationInputError(f"candidate JSON reparse failed: {collision}")
    for ordinal, (path, text) in enumerate(leaves):
        part = Part(
            opaque_id=part_id_for(artifact.artifact_version_id, "val-json", ordinal),
            artifact_version_id=artifact.artifact_version_id,
            surface_kind=SurfaceKind.STRUCTURED_FIELD,
            original_locator=FieldPathLocator(path=path),
            coverage_state=CoverageState.PROCESSED,
            content_length=len(text),
        )
        leaf = path[-1] if path else None
        yield CandidateSurface(
            artifact_version_id=artifact.artifact_version_id,
            media_type=artifact.media_type,
            part=part,
            content=text,
            field_name=leaf if isinstance(leaf, str) else None,
        )


def _jsonl_surfaces(artifact: CandidateArtifact) -> Iterator[CandidateSurface]:
    try:
        text = artifact.payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationInputError("candidate JSONL reparse failed: UnicodeDecodeError") from exc
    ordinal = 0
    for line_no, raw in enumerate(text.splitlines()):
        if raw.strip() == "":
            continue
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationInputError("candidate JSONL reparse failed: JSONDecodeError") from exc
        leaves: list[tuple[tuple[str | int, ...], str]] = []
        if isinstance(document, str):
            leaves.append(((line_no, ROOT_SEGMENT), document))
        else:
            collision = _walk_json(document, (line_no,), leaves)
            if collision is not None:
                raise ValidationInputError(f"candidate JSONL reparse failed: {collision}")
        for path, value in leaves:
            part = Part(
                opaque_id=part_id_for(artifact.artifact_version_id, "val-jsonl", ordinal),
                artifact_version_id=artifact.artifact_version_id,
                surface_kind=SurfaceKind.STRUCTURED_FIELD,
                original_locator=FieldPathLocator(path=path),
                coverage_state=CoverageState.PROCESSED,
                content_length=len(value),
            )
            leaf = path[-1] if path else None
            yield CandidateSurface(
                artifact_version_id=artifact.artifact_version_id,
                media_type=artifact.media_type,
                part=part,
                content=value,
                field_name=leaf if isinstance(leaf, str) else None,
            )
            ordinal += 1


def _csv_surfaces(artifact: CandidateArtifact) -> Iterator[CandidateSurface]:
    try:
        text = artifact.payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationInputError("candidate CSV reparse failed: UnicodeDecodeError") from exc
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise ValidationInputError("candidate CSV reparse failed: csv.Error") from exc
    if not rows:
        return
    header = rows[0]
    if not header or any(name.strip() == "" for name in header) or len(set(header)) != len(header):
        raise ValidationInputError("candidate CSV reparse failed: InvalidHeader")
    ordinal = 0
    for row_index, row in enumerate(rows[1:]):
        width = max(len(header), len(row))
        for col_index in range(width):
            if col_index >= len(row):
                continue
            cell = row[col_index]
            if col_index < len(header):
                path: tuple[str | int, ...] = ("rows", row_index, header[col_index])
                field_name: str | None = header[col_index]
            else:
                path = ("rows", row_index, col_index)
                field_name = None
            part = Part(
                opaque_id=part_id_for(artifact.artifact_version_id, "val-csv", ordinal),
                artifact_version_id=artifact.artifact_version_id,
                surface_kind=SurfaceKind.STRUCTURED_FIELD,
                original_locator=FieldPathLocator(path=path),
                coverage_state=CoverageState.PROCESSED,
                content_length=len(cell),
            )
            yield CandidateSurface(
                artifact_version_id=artifact.artifact_version_id,
                media_type=artifact.media_type,
                part=part,
                content=cell,
                field_name=field_name,
            )
            ordinal += 1


def _text_surfaces(artifact: CandidateArtifact) -> Iterator[CandidateSurface]:
    try:
        text = artifact.payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationInputError("candidate text reparse failed: UnicodeDecodeError") from exc
    part = Part(
        opaque_id=part_id_for(artifact.artifact_version_id, "val-text", 0),
        artifact_version_id=artifact.artifact_version_id,
        surface_kind=SurfaceKind.TEXT,
        original_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=len(text),
        ),
        coverage_state=CoverageState.PROCESSED,
        content_length=len(text),
    )
    yield CandidateSurface(
        artifact_version_id=artifact.artifact_version_id,
        media_type=artifact.media_type,
        part=part,
        content=text,
        field_name=None,
    )


def _walk_json(
    value: Any,
    path: tuple[str | int, ...],
    out: list[tuple[tuple[str | int, ...], str]],
) -> str | None:
    """Walk JSON values; return an error code on encoded-key collision."""
    text = _scalar_text(value) if not isinstance(value, dict | list) else None
    if text is not None:
        if path:
            out.append((path, text))
        elif text != "":
            out.append(((ROOT_SEGMENT,), text))
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            error = _walk_json(item, (*path, index), out)
            if error is not None:
                return error
        return None
    if isinstance(value, dict):
        seen_encoded: set[str] = set()
        for key in sorted(value, key=lambda item: str(item)):
            encoded = encode_field_key(key)
            if encoded is None:
                continue
            if encoded == ROOT_SEGMENT or encoded in seen_encoded:
                return "EncodedKeyCollision"
            seen_encoded.add(encoded)
            error = _walk_json(value[key], (*path, encoded), out)
            if error is not None:
                return error
        return None
    return None


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


def _scalar_at_path(document: Any, path: tuple[str | int, ...]) -> str | None:
    if path == (ROOT_SEGMENT,):
        return _scalar_text(document)
    current: Any = document
    for segment in path:
        if isinstance(segment, int):
            if not isinstance(current, list) or segment < 0 or segment >= len(current):
                return None
            current = current[segment]
            continue
        if not isinstance(segment, str):
            return None
        key = decode_field_key(segment)
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return _scalar_text(current)


def _csv_value_at_path(payload: bytes, path: tuple[str | int, ...]) -> str | None:
    if len(path) != 3 or path[0] != "rows" or not isinstance(path[1], int):
        return None
    try:
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        return None
    if not rows:
        return None
    header = rows[0]
    row_index = path[1]
    if row_index < 0 or row_index + 1 >= len(rows):
        return None
    row = rows[row_index + 1]
    col = path[2]
    if isinstance(col, str):
        try:
            col_index = header.index(col)
        except ValueError:
            return None
    elif isinstance(col, int):
        col_index = col
    else:
        return None
    if col_index < 0 or col_index >= len(row):
        return None
    return row[col_index]
