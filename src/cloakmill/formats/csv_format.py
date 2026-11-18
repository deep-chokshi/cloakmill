"""CSV structured-field extraction for admitted payloads."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import CoverageState, SurfaceKind
from cloakmill.domain.locators import FieldPathLocator
from cloakmill.formats.common import part_id_for
from cloakmill.formats.text_format import ExtractedParts


@dataclass(frozen=True, slots=True)
class CsvExtractResult(ExtractedParts):
    parse_error: str | None = None


def extract_csv_parts(
    *,
    artifact_version_id: str,
    payload: bytes,
) -> CsvExtractResult:
    """Parse UTF-8 CSV with a header row and emit per-cell structured parts.

    The header row itself is emitted as Parts under ``("header", col_index)`` so a
    headerless export cannot silently drop its first record from coverage.
    Cells beyond the header width are emitted with a positional integer path
    segment so ragged rows cannot silently disappear from coverage.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return CsvExtractResult(parts=(), parse_error="UnicodeDecodeError")

    reader = csv.reader(io.StringIO(text))
    try:
        rows = list(reader)
    except csv.Error:
        return CsvExtractResult(parts=(), parse_error="csv.Error")

    if not rows:
        return CsvExtractResult(parts=())

    header = rows[0]
    if not header or any(name.strip() == "" for name in header):
        return CsvExtractResult(parts=(), parse_error="InvalidHeader")
    # Duplicate header names would collide FieldPathLocator paths (last-wins shadow).
    if len(set(header)) != len(header):
        return CsvExtractResult(parts=(), parse_error="DuplicateHeader")

    parts: list[Part] = []
    ordinal = 0
    seen_paths: set[tuple[str | int, ...]] = set()

    def _emit(path: tuple[str | int, ...], content_length: int) -> str | None:
        nonlocal ordinal
        if path in seen_paths:
            return "LocatorCollision"
        seen_paths.add(path)
        parts.append(
            Part(
                opaque_id=part_id_for(artifact_version_id, "csv", ordinal),
                artifact_version_id=artifact_version_id,
                surface_kind=SurfaceKind.STRUCTURED_FIELD,
                original_locator=FieldPathLocator(path=path),
                coverage_state=CoverageState.PROCESSED,
                content_length=content_length,
            )
        )
        ordinal += 1
        return None

    # Track header cells as surfaces so headerless first-row data is not dropped.
    for col_index, name in enumerate(header):
        error = _emit(("header", col_index), len(name))
        if error is not None:
            return CsvExtractResult(parts=(), parse_error=error)

    for row_index, row in enumerate(rows[1:]):
        width = max(len(header), len(row))
        for col_index in range(width):
            if col_index >= len(row):
                continue
            cell = row[col_index]
            if col_index < len(header):
                path: tuple[str | int, ...] = ("rows", row_index, header[col_index])
            else:
                path = ("rows", row_index, col_index)
            error = _emit(path, len(cell))
            if error is not None:
                return CsvExtractResult(parts=(), parse_error=error)
    return CsvExtractResult(parts=tuple(parts))
