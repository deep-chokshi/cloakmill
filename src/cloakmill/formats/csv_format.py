"""CSV structured-field extraction for admitted payloads."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import CoverageState, SurfaceKind
from cloakmill.domain.locators import FieldPathLocator
from cloakmill.formats.common import is_schema_safe_key, part_id_for
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
    if not header or any(name.strip() == "" for name in header) or len(set(header)) != len(header):
        # Duplicate header names make ("rows", i, name) paths ambiguous and can
        # leave an unpatched column's original value in the writer output.
        return CsvExtractResult(parts=(), parse_error="InvalidHeader")
    if any(not is_schema_safe_key(name) for name in header):
        # Header cells are never rewritten by F08 writers; person-keyed headers
        # would ship original identifiers while reporting PROCESSED coverage.
        return CsvExtractResult(parts=(), parse_error="UncoveredKeys")

    parts: list[Part] = []
    ordinal = 0
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
            parts.append(
                Part(
                    opaque_id=part_id_for(artifact_version_id, "csv", ordinal),
                    artifact_version_id=artifact_version_id,
                    surface_kind=SurfaceKind.STRUCTURED_FIELD,
                    original_locator=FieldPathLocator(path=path),
                    coverage_state=CoverageState.PROCESSED,
                    content_length=len(cell),
                )
            )
            ordinal += 1
    return CsvExtractResult(parts=tuple(parts))
