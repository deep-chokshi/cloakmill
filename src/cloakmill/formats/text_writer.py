"""Plain-text writer that applies approved text-offset patches only."""

from __future__ import annotations

from cloakmill.domain.enums import PolicyAction, TextOffsetUnit
from cloakmill.domain.locators import TextOffsetLocator
from cloakmill.domain.mapping import PatchPlanEntry
from cloakmill.formats.write_common import apply_text_offset_patches, resolve_patch_text
from cloakmill.transforms.errors import WriterError
from cloakmill.transforms.replacements import ReplacementVault


def write_text_document(
    *,
    original_payload: bytes,
    patches: tuple[PatchPlanEntry, ...],
    vault: ReplacementVault,
) -> bytes:
    """Decode UTF-8 text, apply non-overlapping codepoint patches, emit UTF-8."""
    try:
        text = original_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WriterError("text payload must be UTF-8") from exc

    spans: list[tuple[TextOffsetLocator, str]] = []
    for entry in patches:
        if entry.action is PolicyAction.EXCLUDE:
            raise WriterError("exclude patches cannot be applied by text writers")
        if not isinstance(entry.locator, TextOffsetLocator):
            raise WriterError("text writers require text_offset locators")
        if entry.locator.unit is not TextOffsetUnit.CODEPOINTS:
            raise WriterError("text writer only supports codepoint offsets")
        replacement = resolve_patch_text(entry, vault)
        spans.append((entry.locator, replacement))

    # Overlap checking is the planner's job; writers still refuse overlaps defensively.
    ordered = sorted(spans, key=lambda item: (item[0].start, item[0].end))
    last_end = 0
    for locator, _ in ordered:
        if locator.start < last_end:
            raise WriterError("overlapping text patches are not writable")
        last_end = locator.end

    updated = apply_text_offset_patches(text, spans)
    return updated.encode("utf-8")
