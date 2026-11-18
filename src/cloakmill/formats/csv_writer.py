"""CSV writer that applies approved structured field patches only."""

from __future__ import annotations

import csv
import io

from cloakmill.domain.enums import PolicyAction
from cloakmill.domain.locators import FieldPathLocator
from cloakmill.domain.mapping import PatchPlanEntry
from cloakmill.formats.write_common import require_field_path, resolve_patch_text
from cloakmill.transforms.errors import WriterError
from cloakmill.transforms.replacements import ReplacementVault


def write_csv_document(
    *,
    original_payload: bytes,
    patches: tuple[PatchPlanEntry, ...],
    vault: ReplacementVault,
) -> bytes:
    """Parse UTF-8 CSV, apply cell patches at F04 ``("rows", i, col)`` paths, emit CSV."""
    try:
        text = original_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WriterError("CSV payload must be UTF-8") from exc

    reader = csv.reader(io.StringIO(text))
    try:
        rows = [list(row) for row in reader]
    except csv.Error as exc:
        raise WriterError("invalid CSV payload") from exc
    if not rows:
        if patches:
            raise WriterError("cannot apply patches to an empty CSV document")
        return b""

    header = rows[0]
    if not header or any(name.strip() == "" for name in header):
        raise WriterError("CSV header is invalid")

    body = [list(row) for row in rows[1:]]
    for entry in _ordered_field_patches(patches):
        locator = require_field_path(entry.locator)
        path = locator.path
        row_index, column = _parse_csv_path(path)
        if row_index < 0 or row_index >= len(body):
            raise WriterError(f"CSV patch row index {row_index} out of range")
        row = body[row_index]
        col_index = _column_index(header, column)
        replacement = resolve_patch_text(entry, vault)
        if replacement == "" and entry.action is not PolicyAction.REMOVE:
            raise WriterError("refusing empty replacement for CSV cell")
        while len(row) <= col_index:
            row.append("")
        row[col_index] = replacement

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in body:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _ordered_field_patches(patches: tuple[PatchPlanEntry, ...]) -> list[PatchPlanEntry]:
    ordered: list[PatchPlanEntry] = []
    for entry in patches:
        if entry.action is PolicyAction.EXCLUDE:
            raise WriterError("exclude patches cannot be applied by CSV writers")
        if not isinstance(entry.locator, FieldPathLocator):
            raise WriterError("CSV writers require field_path locators")
        ordered.append(entry)
    ordered.sort(key=lambda item: (tuple(item.locator.path), item.opaque_id))
    return ordered


def _parse_csv_path(path: tuple[str | int, ...]) -> tuple[int, str | int]:
    if len(path) != 3 or path[0] != "rows" or not isinstance(path[1], int):
        raise WriterError("CSV field path must be ('rows', row_index, column_name_or_index)")
    return path[1], path[2]


def _column_index(header: list[str], column: str | int) -> int:
    if isinstance(column, int):
        if column < 0:
            raise WriterError("CSV positional column index must be >= 0")
        return column
    try:
        return header.index(column)
    except ValueError as exc:
        raise WriterError(f"CSV header missing column {column!r}") from exc
