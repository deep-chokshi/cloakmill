"""JSON / JSONL writers that apply approved structured field patches only."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from cloakmill.domain.enums import PolicyAction
from cloakmill.domain.locators import FieldPathLocator
from cloakmill.domain.mapping import PatchPlanEntry
from cloakmill.formats.json_format import (
    ROOT_SEGMENT,
    decode_field_key,
    is_jsonl_root_scalar_path,
    is_root_scalar_path,
)
from cloakmill.formats.write_common import require_field_path, resolve_patch_text
from cloakmill.transforms.errors import WriterError
from cloakmill.transforms.replacements import ReplacementVault


def write_json_document(
    *,
    original_payload: bytes,
    patches: tuple[PatchPlanEntry, ...],
    vault: ReplacementVault,
) -> bytes:
    """Parse JSON, apply field-path patches, and emit UTF-8 JSON stably."""
    document = _load_json(original_payload)
    working: Any = deepcopy(document)
    for entry in _ordered_field_patches(patches):
        locator = require_field_path(entry.locator)
        replacement = resolve_patch_text(entry, vault)
        working = _apply_field_patch(
            working,
            locator.path,
            replacement,
            allow_empty=entry.action is PolicyAction.REMOVE,
        )
    return _dump_json(working)


def write_jsonl_document(
    *,
    original_payload: bytes,
    patches: tuple[PatchPlanEntry, ...],
    vault: ReplacementVault,
) -> bytes:
    """Parse JSON Lines, apply line-indexed field patches, emit UTF-8 JSONL."""
    try:
        text = original_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WriterError("JSONL payload must be UTF-8") from exc

    raw_lines = text.splitlines()
    documents: list[Any] = []
    line_indexes: list[int] = []
    for line_no, raw_line in enumerate(raw_lines):
        if raw_line.strip() == "":
            continue
        try:
            documents.append(json.loads(raw_line))
        except json.JSONDecodeError as exc:
            raise WriterError("invalid JSONL line") from exc
        line_indexes.append(line_no)

    index_to_slot = {line_no: slot for slot, line_no in enumerate(line_indexes)}
    working_docs = [deepcopy(doc) for doc in documents]

    for entry in _ordered_field_patches(patches):
        locator = require_field_path(entry.locator)
        path = locator.path
        if not path or not isinstance(path[0], int):
            raise WriterError("JSONL field patches must begin with a line index")
        line_no = path[0]
        try:
            slot = index_to_slot[line_no]
        except KeyError as exc:
            raise WriterError(f"JSONL patch references missing line {line_no}") from exc
        replacement = resolve_patch_text(entry, vault)
        if is_jsonl_root_scalar_path(path):
            if isinstance(working_docs[slot], dict | list):
                raise WriterError("JSONL root sentinel cannot replace a container document line")
            working_docs[slot] = replacement
            continue
        rest = path[1:]
        if not rest:
            raise WriterError("JSONL field patch path must include a field after line index")
        working_docs[slot] = _apply_field_patch(
            working_docs[slot],
            rest,
            replacement,
            allow_empty=entry.action is PolicyAction.REMOVE,
        )

    out_lines = [_dump_json_line(doc) for doc in working_docs]
    payload = "\n".join(out_lines)
    if payload:
        payload += "\n"
    return payload.encode("utf-8")


def _ordered_field_patches(patches: tuple[PatchPlanEntry, ...]) -> list[PatchPlanEntry]:
    ordered: list[PatchPlanEntry] = []
    for entry in patches:
        if entry.action is PolicyAction.EXCLUDE:
            raise WriterError("exclude patches cannot be applied by JSON writers")
        if not isinstance(entry.locator, FieldPathLocator):
            raise WriterError("JSON writers require field_path locators for structured leaves")
        ordered.append(entry)
    ordered.sort(key=lambda item: (tuple(item.locator.path), item.opaque_id))
    return ordered


def _apply_field_patch(
    document: Any,
    path: tuple[str | int, ...],
    value: str,
    *,
    allow_empty: bool,
) -> Any:
    if is_root_scalar_path(path):
        if isinstance(document, dict | list):
            raise WriterError("JSON root sentinel cannot patch a container document")
        if value == "" and not allow_empty:
            raise WriterError("refusing empty replacement for JSON string leaf")
        return value
    if not path:
        raise WriterError("field path must not be empty")
    if path[0] == ROOT_SEGMENT:
        raise WriterError("JSON root sentinel is only valid as a bare scalar path")
    _set_path_value(document, path, value, allow_empty=allow_empty)
    return document


def _load_json(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WriterError("JSON payload must be valid UTF-8 JSON") from exc


def _dump_json(document: Any) -> bytes:
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def _dump_json_line(document: Any) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def _set_path_value(
    document: Any,
    path: tuple[str | int, ...],
    value: str,
    *,
    allow_empty: bool,
) -> None:
    cursor: Any = document
    for segment in path[:-1]:
        cursor = _step(cursor, segment)
    last = path[-1]
    parent = cursor
    if value == "" and not allow_empty:
        raise WriterError("refusing empty replacement for JSON leaf")
    if isinstance(parent, dict):
        if not isinstance(last, str):
            raise WriterError("object path segment must be a string key")
        key = decode_field_key(last)
        if key not in parent:
            raise WriterError(f"missing JSON object key {key!r}")
        parent[key] = value
        return
    if isinstance(parent, list):
        if not isinstance(last, int):
            raise WriterError("array path segment must be an int index")
        if last < 0 or last >= len(parent):
            raise WriterError(f"JSON array index {last} out of range")
        parent[last] = value
        return
    raise WriterError("invalid JSON parent for field path write")


def _step(cursor: Any, segment: str | int) -> Any:
    if isinstance(cursor, dict):
        if not isinstance(segment, str):
            raise WriterError("object path segment must be a string key")
        key = decode_field_key(segment)
        try:
            return cursor[key]
        except KeyError as exc:
            raise WriterError(f"missing JSON object key {key!r}") from exc
    if isinstance(cursor, list):
        if not isinstance(segment, int):
            raise WriterError("array path segment must be an int index")
        try:
            return cursor[segment]
        except IndexError as exc:
            raise WriterError(f"JSON array index {segment} out of range") from exc
    raise WriterError("field path walked into a non-container JSON value")
