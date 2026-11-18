"""JSON serialization helpers for domain contracts."""

from __future__ import annotations

import json
from typing import Any, cast, overload

from cloakmill.domain.artifacts import ArtifactVersion, Part
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.locators import (
    FieldPathLocator,
    OriginalLocator,
    TextOffsetLocator,
    locator_from_dict,
)
from cloakmill.domain.mapping import (
    EntityGraphVersion,
    MappingAssignment,
    MappingSnapshot,
    NamespaceKeyRef,
    PatchPlanEntry,
)
from cloakmill.domain.observations import EvidenceRef, Observation

DomainRecord = (
    ArtifactVersion
    | Part
    | Observation
    | EvidenceRef
    | OriginalLocator
    | NamespaceKeyRef
    | EntityGraphVersion
    | MappingAssignment
    | MappingSnapshot
    | PatchPlanEntry
)
type DomainRecordT = (
    ArtifactVersion
    | Part
    | Observation
    | EvidenceRef
    | TextOffsetLocator
    | FieldPathLocator
    | NamespaceKeyRef
    | EntityGraphVersion
    | MappingAssignment
    | MappingSnapshot
    | PatchPlanEntry
)


def to_jsonable(record: DomainRecord) -> dict[str, Any]:
    """Convert a domain record into a JSON-ready mapping."""
    return record.to_dict()


@overload
def from_jsonable(data: dict[str, Any], record_type: type[ArtifactVersion]) -> ArtifactVersion: ...


@overload
def from_jsonable(data: dict[str, Any], record_type: type[Part]) -> Part: ...


@overload
def from_jsonable(data: dict[str, Any], record_type: type[Observation]) -> Observation: ...


@overload
def from_jsonable(data: dict[str, Any], record_type: type[EvidenceRef]) -> EvidenceRef: ...


@overload
def from_jsonable(
    data: dict[str, Any], record_type: type[TextOffsetLocator]
) -> TextOffsetLocator: ...


@overload
def from_jsonable(
    data: dict[str, Any], record_type: type[FieldPathLocator]
) -> FieldPathLocator: ...


@overload
def from_jsonable(data: dict[str, Any], record_type: type[NamespaceKeyRef]) -> NamespaceKeyRef: ...


@overload
def from_jsonable(
    data: dict[str, Any], record_type: type[EntityGraphVersion]
) -> EntityGraphVersion: ...


@overload
def from_jsonable(
    data: dict[str, Any], record_type: type[MappingAssignment]
) -> MappingAssignment: ...


@overload
def from_jsonable(data: dict[str, Any], record_type: type[MappingSnapshot]) -> MappingSnapshot: ...


@overload
def from_jsonable(data: dict[str, Any], record_type: type[PatchPlanEntry]) -> PatchPlanEntry: ...


def from_jsonable[T: DomainRecordT](data: dict[str, Any], record_type: type[T]) -> T:
    """Parse and validate a domain record from a JSON-ready mapping."""
    if not isinstance(data, dict):
        raise DomainValidationError("serialized domain record must be an object")
    if record_type is ArtifactVersion:
        return cast(T, ArtifactVersion.from_dict(data))
    if record_type is Part:
        return cast(T, Part.from_dict(data))
    if record_type is Observation:
        return cast(T, Observation.from_dict(data))
    if record_type is EvidenceRef:
        return cast(T, EvidenceRef.from_dict(data))
    if record_type is TextOffsetLocator:
        return cast(T, TextOffsetLocator.from_dict(data))
    if record_type is FieldPathLocator:
        return cast(T, FieldPathLocator.from_dict(data))
    if record_type is NamespaceKeyRef:
        return cast(T, NamespaceKeyRef.from_dict(data))
    if record_type is EntityGraphVersion:
        return cast(T, EntityGraphVersion.from_dict(data))
    if record_type is MappingAssignment:
        return cast(T, MappingAssignment.from_dict(data))
    if record_type is MappingSnapshot:
        return cast(T, MappingSnapshot.from_dict(data))
    if record_type is PatchPlanEntry:
        return cast(T, PatchPlanEntry.from_dict(data))
    raise DomainValidationError(f"unsupported domain record type: {record_type!r}")


def dumps(record: DomainRecord, *, indent: int | None = 2) -> str:
    """Serialize a domain record to a JSON string."""
    return json.dumps(to_jsonable(record), indent=indent, sort_keys=True)


def loads[T: DomainRecordT](payload: str, record_type: type[T]) -> T:
    """Deserialize and validate a domain record from a JSON string."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DomainValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DomainValidationError("serialized domain record must be a JSON object")
    return from_jsonable(data, record_type)


def loads_locator(payload: str) -> OriginalLocator:
    """Deserialize a tagged original locator from JSON."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DomainValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DomainValidationError("serialized locator must be a JSON object")
    return locator_from_dict(data)
