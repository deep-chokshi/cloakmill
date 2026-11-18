"""Frozen entity-graph, mapping-snapshot, and patch-plan contract shapes.

These records pin replay inputs for assignment and writers. They never embed
namespace key material, source-to-synthetic value maps, or original PII.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloakmill.domain.enums import PolicyAction
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_non_empty_str, require_opaque_id
from cloakmill.domain.locators import (
    OriginalLocator,
    locator_from_dict,
    validate_locator,
)


@dataclass(frozen=True, slots=True)
class NamespaceKeyRef:
    """Opaque reference to private namespace key material (never the key bytes)."""

    opaque_id: str
    namespace_id: str
    key_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_id": self.opaque_id,
            "namespace_id": self.namespace_id,
            "key_version": self.key_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NamespaceKeyRef:
        if not isinstance(data, dict):
            raise DomainValidationError("namespace key ref must be an object")
        ref = cls(
            opaque_id=data.get("opaque_id", ""),
            namespace_id=data.get("namespace_id", ""),
            key_version=data.get("key_version", ""),
        )
        validate_namespace_key_ref(ref)
        return ref


@dataclass(frozen=True, slots=True)
class EntityGraphVersion:
    """Versioned accepted entity graph pinned for mapping and release replay."""

    opaque_id: str
    graph_version: str
    namespace_id: str
    entity_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_id": self.opaque_id,
            "graph_version": self.graph_version,
            "namespace_id": self.namespace_id,
            "entity_ids": list(self.entity_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityGraphVersion:
        if not isinstance(data, dict):
            raise DomainValidationError("entity graph version must be an object")
        raw_ids = data.get("entity_ids", [])
        if not isinstance(raw_ids, list):
            raise DomainValidationError("entity_ids must be a list")
        graph = cls(
            opaque_id=data.get("opaque_id", ""),
            graph_version=data.get("graph_version", ""),
            namespace_id=data.get("namespace_id", ""),
            entity_ids=tuple(raw_ids),
        )
        validate_entity_graph_version(graph)
        return graph


@dataclass(frozen=True, slots=True)
class MappingAssignment:
    """Opaque entity-to-profile binding inside a frozen mapping snapshot."""

    entity_id: str
    profile_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "profile_id": self.profile_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MappingAssignment:
        if not isinstance(data, dict):
            raise DomainValidationError("mapping assignment must be an object")
        assignment = cls(
            entity_id=data.get("entity_id", ""),
            profile_id=data.get("profile_id", ""),
        )
        validate_mapping_assignment(assignment)
        return assignment


@dataclass(frozen=True, slots=True)
class MappingSnapshot:
    """Frozen, versioned mapping snapshot for deterministic transform replay."""

    opaque_id: str
    snapshot_version: str
    namespace_id: str
    entity_graph_version_id: str
    policy_version: str
    namespace_key_ref: NamespaceKeyRef
    assignments: tuple[MappingAssignment, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_id": self.opaque_id,
            "snapshot_version": self.snapshot_version,
            "namespace_id": self.namespace_id,
            "entity_graph_version_id": self.entity_graph_version_id,
            "policy_version": self.policy_version,
            "namespace_key_ref": self.namespace_key_ref.to_dict(),
            "assignments": [item.to_dict() for item in self.assignments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MappingSnapshot:
        if not isinstance(data, dict):
            raise DomainValidationError("mapping snapshot must be an object")
        try:
            key_ref = NamespaceKeyRef.from_dict(data["namespace_key_ref"])
        except (KeyError, TypeError, DomainValidationError) as exc:
            raise DomainValidationError(f"invalid mapping snapshot key ref: {exc}") from exc

        raw_assignments = data.get("assignments", [])
        if not isinstance(raw_assignments, list):
            raise DomainValidationError("assignments must be a list")
        assignments = tuple(MappingAssignment.from_dict(item) for item in raw_assignments)

        snapshot = cls(
            opaque_id=data.get("opaque_id", ""),
            snapshot_version=data.get("snapshot_version", ""),
            namespace_id=data.get("namespace_id", ""),
            entity_graph_version_id=data.get("entity_graph_version_id", ""),
            policy_version=data.get("policy_version", ""),
            namespace_key_ref=key_ref,
            assignments=assignments,
        )
        validate_mapping_snapshot(snapshot)
        return snapshot


@dataclass(frozen=True, slots=True)
class PatchPlanEntry:
    """One conflict-checked patch at an original locator under a frozen snapshot."""

    opaque_id: str
    mapping_snapshot_id: str
    artifact_version_id: str
    part_id: str
    locator: OriginalLocator
    action: PolicyAction
    entity_id: str | None = None
    replacement_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "mapping_snapshot_id": self.mapping_snapshot_id,
            "artifact_version_id": self.artifact_version_id,
            "part_id": self.part_id,
            "locator": self.locator.to_dict(),
            "action": self.action.value,
        }
        if self.entity_id is not None:
            payload["entity_id"] = self.entity_id
        if self.replacement_ref is not None:
            payload["replacement_ref"] = self.replacement_ref
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchPlanEntry:
        if not isinstance(data, dict):
            raise DomainValidationError("patch plan entry must be an object")
        try:
            action = PolicyAction(data["action"])
            locator = locator_from_dict(data["locator"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid patch plan entry fields: {exc}") from exc

        entry = cls(
            opaque_id=data.get("opaque_id", ""),
            mapping_snapshot_id=data.get("mapping_snapshot_id", ""),
            artifact_version_id=data.get("artifact_version_id", ""),
            part_id=data.get("part_id", ""),
            locator=locator,
            action=action,
            entity_id=data.get("entity_id"),
            replacement_ref=data.get("replacement_ref"),
        )
        validate_patch_plan_entry(entry)
        return entry


def validate_namespace_key_ref(ref: NamespaceKeyRef) -> None:
    require_opaque_id(ref.opaque_id, "opaque_id")
    require_opaque_id(ref.namespace_id, "namespace_id")
    require_non_empty_str(ref.key_version, "key_version")


def validate_entity_graph_version(graph: EntityGraphVersion) -> None:
    require_opaque_id(graph.opaque_id, "opaque_id")
    require_non_empty_str(graph.graph_version, "graph_version")
    require_opaque_id(graph.namespace_id, "namespace_id")
    seen: set[str] = set()
    for entity_id in graph.entity_ids:
        require_opaque_id(entity_id, "entity_ids[]")
        if entity_id in seen:
            raise DomainValidationError(f"duplicate entity_id in graph: {entity_id}")
        seen.add(entity_id)


def validate_mapping_assignment(assignment: MappingAssignment) -> None:
    require_opaque_id(assignment.entity_id, "entity_id")
    require_opaque_id(assignment.profile_id, "profile_id")


def validate_mapping_snapshot(snapshot: MappingSnapshot) -> None:
    require_opaque_id(snapshot.opaque_id, "opaque_id")
    require_non_empty_str(snapshot.snapshot_version, "snapshot_version")
    require_opaque_id(snapshot.namespace_id, "namespace_id")
    require_opaque_id(snapshot.entity_graph_version_id, "entity_graph_version_id")
    require_non_empty_str(snapshot.policy_version, "policy_version")
    if not isinstance(snapshot.namespace_key_ref, NamespaceKeyRef):
        raise DomainValidationError("namespace_key_ref must be a NamespaceKeyRef")
    validate_namespace_key_ref(snapshot.namespace_key_ref)
    if snapshot.namespace_key_ref.namespace_id != snapshot.namespace_id:
        raise DomainValidationError(
            "namespace_key_ref.namespace_id must match mapping snapshot namespace_id"
        )
    seen_entities: set[str] = set()
    for assignment in snapshot.assignments:
        validate_mapping_assignment(assignment)
        if assignment.entity_id in seen_entities:
            raise DomainValidationError(
                f"duplicate entity assignment in snapshot: {assignment.entity_id}"
            )
        seen_entities.add(assignment.entity_id)


def validate_patch_plan_entry(entry: PatchPlanEntry) -> None:
    require_opaque_id(entry.opaque_id, "opaque_id")
    require_opaque_id(entry.mapping_snapshot_id, "mapping_snapshot_id")
    require_opaque_id(entry.artifact_version_id, "artifact_version_id")
    require_opaque_id(entry.part_id, "part_id")
    if not isinstance(entry.action, PolicyAction):
        raise DomainValidationError("action must be a PolicyAction")
    validate_locator(entry.locator)

    if entry.entity_id is not None:
        require_opaque_id(entry.entity_id, "entity_id")
    if entry.replacement_ref is not None:
        require_opaque_id(entry.replacement_ref, "replacement_ref")

    if entry.action is PolicyAction.REPLACE:
        if entry.entity_id is None:
            raise DomainValidationError("replace patches require entity_id")
        if entry.replacement_ref is None:
            raise DomainValidationError("replace patches require replacement_ref")
    elif entry.action is PolicyAction.INERT:
        if entry.replacement_ref is None:
            raise DomainValidationError("inert patches require replacement_ref")
        if entry.entity_id is not None:
            raise DomainValidationError("inert patches must not set entity_id")
    elif entry.action is PolicyAction.REMOVE:
        if entry.replacement_ref is not None:
            raise DomainValidationError("remove patches must not set replacement_ref")
    elif entry.action is PolicyAction.EXCLUDE:
        if entry.replacement_ref is not None:
            raise DomainValidationError("exclude patches must not set replacement_ref")


def entity_graph_versions_equal(left: EntityGraphVersion, right: EntityGraphVersion) -> bool:
    """Return True when graph versions match structurally (entity order ignored)."""
    validate_entity_graph_version(left)
    validate_entity_graph_version(right)
    return (
        left.opaque_id == right.opaque_id
        and left.graph_version == right.graph_version
        and left.namespace_id == right.namespace_id
        and frozenset(left.entity_ids) == frozenset(right.entity_ids)
    )


def mapping_snapshots_equal(left: MappingSnapshot, right: MappingSnapshot) -> bool:
    """Return True when snapshots match for replay (assignment order ignored)."""
    validate_mapping_snapshot(left)
    validate_mapping_snapshot(right)
    left_assignments = frozenset((item.entity_id, item.profile_id) for item in left.assignments)
    right_assignments = frozenset((item.entity_id, item.profile_id) for item in right.assignments)
    return (
        left.opaque_id == right.opaque_id
        and left.snapshot_version == right.snapshot_version
        and left.namespace_id == right.namespace_id
        and left.entity_graph_version_id == right.entity_graph_version_id
        and left.policy_version == right.policy_version
        and left.namespace_key_ref == right.namespace_key_ref
        and left_assignments == right_assignments
    )
