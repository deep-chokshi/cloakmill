"""Immutable original locator kinds for source content."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloakmill.domain.enums import LocatorKind, TextOffsetUnit
from cloakmill.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class TextOffsetLocator:
    """Half-open ``[start, end)`` span in an immutable text surface."""

    unit: TextOffsetUnit
    start: int
    end: int
    kind: LocatorKind = LocatorKind.TEXT_OFFSET

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "unit": self.unit.value,
            "start": self.start,
            "end": self.end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TextOffsetLocator:
        if data.get("kind") != LocatorKind.TEXT_OFFSET.value:
            raise DomainValidationError(
                f"expected locator kind {LocatorKind.TEXT_OFFSET.value!r}, got {data.get('kind')!r}"
            )
        try:
            unit = TextOffsetUnit(data["unit"])
            start = data["start"]
            end = data["end"]
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid text offset locator: {exc}") from exc
        if not isinstance(start, int) or isinstance(start, bool):
            raise DomainValidationError("text offset start must be an int")
        if not isinstance(end, int) or isinstance(end, bool):
            raise DomainValidationError("text offset end must be an int")
        locator = cls(unit=unit, start=start, end=end)
        validate_text_offset_locator(locator)
        return locator


@dataclass(frozen=True, slots=True)
class FieldPathLocator:
    """Path into a structured record (object keys and non-negative array indexes)."""

    path: tuple[str | int, ...]
    kind: LocatorKind = LocatorKind.FIELD_PATH

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "path": list(self.path),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldPathLocator:
        if data.get("kind") != LocatorKind.FIELD_PATH.value:
            raise DomainValidationError(
                f"expected locator kind {LocatorKind.FIELD_PATH.value!r}, got {data.get('kind')!r}"
            )
        raw_path = data.get("path")
        if not isinstance(raw_path, list):
            raise DomainValidationError("field path must be a list")
        path: list[str | int] = []
        for segment in raw_path:
            if isinstance(segment, bool) or not isinstance(segment, str | int):
                raise DomainValidationError(
                    f"field path segments must be str or int, got {type(segment).__name__}"
                )
            path.append(segment)
        locator = cls(path=tuple(path))
        validate_field_path_locator(locator)
        return locator


OriginalLocator = TextOffsetLocator | FieldPathLocator


def validate_text_offset_locator(
    locator: TextOffsetLocator,
    *,
    content_length: int | None = None,
) -> None:
    """Reject negative, inverted, or out-of-bounds text offsets."""
    if locator.kind is not LocatorKind.TEXT_OFFSET:
        raise DomainValidationError("text offset locator has incorrect kind tag")
    if locator.start < 0:
        raise DomainValidationError(f"text offset start must be >= 0, got {locator.start}")
    if locator.end < locator.start:
        raise DomainValidationError(
            f"text offset end ({locator.end}) must be >= start ({locator.start})"
        )
    if content_length is not None:
        if content_length < 0:
            raise DomainValidationError(f"content_length must be >= 0, got {content_length}")
        if locator.end > content_length:
            raise DomainValidationError(
                f"text offset end ({locator.end}) exceeds content_length ({content_length})"
            )


def validate_field_path_locator(locator: FieldPathLocator) -> None:
    """Reject empty paths and invalid segment values."""
    if locator.kind is not LocatorKind.FIELD_PATH:
        raise DomainValidationError("field path locator has incorrect kind tag")
    if not locator.path:
        raise DomainValidationError("field path must contain at least one segment")
    for index, segment in enumerate(locator.path):
        if isinstance(segment, bool) or not isinstance(segment, str | int):
            raise DomainValidationError(
                f"field path segment {index} must be str or int, got {type(segment).__name__}"
            )
        if isinstance(segment, str) and segment == "":
            raise DomainValidationError(f"field path segment {index} must be a non-empty string")
        if isinstance(segment, int) and segment < 0:
            raise DomainValidationError(
                f"field path segment {index} index must be >= 0, got {segment}"
            )


def validate_locator(
    locator: OriginalLocator,
    *,
    content_length: int | None = None,
) -> None:
    """Validate locator shape and optional text bounds."""
    if isinstance(locator, TextOffsetLocator):
        validate_text_offset_locator(locator, content_length=content_length)
        return
    if isinstance(locator, FieldPathLocator):
        if content_length is not None:
            raise DomainValidationError("content_length applies only to text offset locators")
        validate_field_path_locator(locator)
        return
    raise DomainValidationError(f"unsupported locator type: {type(locator).__name__}")


def locator_from_dict(data: dict[str, Any]) -> OriginalLocator:
    """Deserialize a tagged locator object."""
    if not isinstance(data, dict):
        raise DomainValidationError("locator must be an object")
    kind = data.get("kind")
    if kind == LocatorKind.TEXT_OFFSET.value:
        return TextOffsetLocator.from_dict(data)
    if kind == LocatorKind.FIELD_PATH.value:
        return FieldPathLocator.from_dict(data)
    raise DomainValidationError(f"unknown locator kind: {kind!r}")
