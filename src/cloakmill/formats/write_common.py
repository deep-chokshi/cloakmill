"""Shared helpers for structured writers that apply approved patches only."""

from __future__ import annotations

from cloakmill.domain.enums import PolicyAction
from cloakmill.domain.locators import FieldPathLocator, OriginalLocator, TextOffsetLocator
from cloakmill.domain.mapping import PatchPlanEntry
from cloakmill.formats.json_format import EMPTY_KEY_SEGMENT
from cloakmill.transforms.errors import WriterError
from cloakmill.transforms.replacements import ReplacementVault
from cloakmill.transforms.safety import assert_safe_replacement


def resolve_patch_text(entry: PatchPlanEntry, vault: ReplacementVault) -> str:
    """Resolve the textual substitution for one non-exclude patch entry."""
    if entry.action is PolicyAction.EXCLUDE:
        raise WriterError("exclude patches cannot be applied by content writers")
    if entry.action is PolicyAction.REMOVE:
        return ""
    if entry.replacement_ref is None:
        raise WriterError(f"patch {entry.opaque_id!r} is missing replacement_ref")
    value = vault.get(entry.replacement_ref)
    return assert_safe_replacement(value, field_name=entry.replacement_ref)


def apply_text_offset_patches(
    text: str,
    entries: list[tuple[TextOffsetLocator, str]],
) -> str:
    """Apply non-overlapping text substitutions from end to start."""
    ordered = sorted(entries, key=lambda item: (item[0].start, item[0].end), reverse=True)
    chars = list(text)
    length = len(chars)
    for locator, replacement in ordered:
        if locator.end > length:
            raise WriterError(f"text patch end {locator.end} exceeds content length {length}")
        if locator.start < 0 or locator.end < locator.start:
            raise WriterError("invalid text offset patch bounds")
        chars[locator.start : locator.end] = list(replacement)
    return "".join(chars)


def decode_field_key(segment: str) -> str:
    """Decode F04 empty-key sentinel back to a JSON object key."""
    if segment == EMPTY_KEY_SEGMENT:
        return ""
    return segment


def require_field_path(locator: OriginalLocator) -> FieldPathLocator:
    if not isinstance(locator, FieldPathLocator):
        raise WriterError(
            f"structured writer expected field_path locator, got {type(locator).__name__}"
        )
    return locator


def require_text_offset(locator: OriginalLocator) -> TextOffsetLocator:
    if not isinstance(locator, TextOffsetLocator):
        raise WriterError(f"text writer expected text_offset locator, got {type(locator).__name__}")
    return locator
