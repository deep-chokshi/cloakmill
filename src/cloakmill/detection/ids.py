"""Deterministic opaque ids for validated observations and evidence refs."""

from __future__ import annotations

import hashlib

from cloakmill.domain.locators import FieldPathLocator, OriginalLocator, TextOffsetLocator


def observation_opaque_id(
    *,
    part_id: str,
    entity_type: str,
    recognizer_version: str,
    locator: OriginalLocator,
) -> str:
    digest = _digest(part_id, entity_type, recognizer_version, _locator_key(locator))
    return f"obs-{digest}"


def evidence_opaque_id(
    *,
    part_id: str,
    recognizer_version: str,
    locator: OriginalLocator,
) -> str:
    digest = _digest(part_id, recognizer_version, _locator_key(locator))
    return f"ev-{digest}"


def _locator_key(locator: OriginalLocator) -> str:
    if isinstance(locator, TextOffsetLocator):
        return f"text_offset:{locator.unit.value}:{locator.start}:{locator.end}"
    if isinstance(locator, FieldPathLocator):
        path = "/".join(str(segment) for segment in locator.path)
        return f"field_path:{path}"
    raise TypeError(f"unsupported locator type: {type(locator).__name__}")


def _digest(*parts: str) -> str:
    material = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]
