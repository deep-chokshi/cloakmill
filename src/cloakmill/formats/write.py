"""Dispatch approved patch plans to JSON / CSV / text writers."""

from __future__ import annotations

from dataclasses import dataclass

from cloakmill.domain.mapping import PatchPlanEntry
from cloakmill.formats.csv_writer import write_csv_document
from cloakmill.formats.json_writer import write_json_document, write_jsonl_document
from cloakmill.formats.text_writer import write_text_document
from cloakmill.transforms.errors import WriterError
from cloakmill.transforms.planner import PatchPlan, patches_for_artifact
from cloakmill.transforms.replacements import ReplacementVault

SUPPORTED_WRITE_MEDIA_TYPES: frozenset[str] = frozenset(
    {
        "application/json",
        "application/x-ndjson",
        "text/csv",
        "text/plain",
    }
)


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Bytes produced by a structured writer for one artifact."""

    media_type: str
    payload: bytes
    excluded: bool = False


def write_artifact(
    *,
    media_type: str,
    original_payload: bytes,
    artifact_version_id: str,
    plan: PatchPlan,
) -> WriteResult:
    """Apply the patch plan for one artifact without mutating ``original_payload``.

    Originals are never written in place: callers receive a new ``bytes`` object.
    Excluded artifacts return ``excluded=True`` with empty payload and must not be
    copied into a sanitized release.
    """
    if media_type not in SUPPORTED_WRITE_MEDIA_TYPES:
        raise WriterError(f"unsupported write media type: {media_type!r}")
    if artifact_version_id in plan.excluded_artifact_ids:
        return WriteResult(media_type=media_type, payload=b"", excluded=True)

    patches = patches_for_artifact(plan, artifact_version_id)
    # Defensive copy so callers cannot observe mutation of the input buffer.
    source = bytes(original_payload)
    payload = apply_patches(
        media_type=media_type,
        original_payload=source,
        patches=patches,
        vault=plan.vault,
    )
    return WriteResult(media_type=media_type, payload=payload, excluded=False)


def apply_patches(
    *,
    media_type: str,
    original_payload: bytes,
    patches: tuple[PatchPlanEntry, ...],
    vault: ReplacementVault,
) -> bytes:
    """Low-level media-type dispatch used by ``write_artifact`` and tests."""
    if media_type == "application/json":
        return write_json_document(
            original_payload=original_payload,
            patches=patches,
            vault=vault,
        )
    if media_type == "application/x-ndjson":
        return write_jsonl_document(
            original_payload=original_payload,
            patches=patches,
            vault=vault,
        )
    if media_type == "text/csv":
        return write_csv_document(
            original_payload=original_payload,
            patches=patches,
            vault=vault,
        )
    if media_type == "text/plain":
        return write_text_document(
            original_payload=original_payload,
            patches=patches,
            vault=vault,
        )
    raise WriterError(f"unsupported write media type: {media_type!r}")
