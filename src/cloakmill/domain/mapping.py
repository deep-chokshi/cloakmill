"""Frozen entity-graph, mapping-snapshot, and patch-plan contract shapes.

These records pin replay inputs for assignment and writers. They never embed
namespace key material, source-to-synthetic value maps, or original PII.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from cloakmill.domain.artifacts import validate_private_integrity_digest
from cloakmill.domain.enums import PolicyAction
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import (
    length_prefixed_utf8,
    require_opaque_id,
    require_version_token,
)
from cloakmill.domain.locators import (
    OriginalLocator,
    locator_from_dict,
    validate_locator,
)

# Minimum secret length for mapping-snapshot HMAC (private boundary only).
_MIN_MAPPING_SECRET_LENGTH = 16


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
    private_integrity_digest: str
    assignments: tuple[MappingAssignment, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_id": self.opaque_id,
            "snapshot_version": self.snapshot_version,
            "namespace_id": self.namespace_id,
            "entity_graph_version_id": self.entity_graph_version_id,
            "policy_version": self.policy_version,
            "namespace_key_ref": self.namespace_key_ref.to_dict(),
            "private_integrity_digest": self.private_integrity_digest,
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
            private_integrity_digest=data.get("private_integrity_digest", ""),
            assignments=assignments,
        )
        # Structure + content-addressed opaque_id only. HMAC authentication
        # requires ``validate_mapping_snapshot(..., namespace_secret=...)``.
        validate_mapping_snapshot_structure(snapshot)
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


def _require_mapping_secret(secret: object) -> bytes:
    if not isinstance(secret, bytes | bytearray):
        raise DomainValidationError("namespace_secret must be bytes")
    material = bytes(secret)
    if len(material) < _MIN_MAPPING_SECRET_LENGTH:
        raise DomainValidationError(
            f"namespace_secret must be at least {_MIN_MAPPING_SECRET_LENGTH} bytes"
        )
    return material


def mapping_snapshot_commitment_material(
    *,
    snapshot_version: str,
    namespace_id: str,
    entity_graph_version_id: str,
    policy_version: str,
    namespace_key_ref: NamespaceKeyRef,
    assignments: tuple[MappingAssignment, ...],
) -> bytes:
    """Canonical injective bytes covered by opaque_id and HMAC digest.

    Fields are length-prefixed (not NUL-joined) so embedded separators cannot
    collide distinct snapshots onto one commitment. Assignments are two separate
    fields each (entity_id, profile_id), never a colon-joined pair.
    """
    require_version_token(snapshot_version, "snapshot_version")
    require_version_token(policy_version, "policy_version")
    require_version_token(namespace_key_ref.key_version, "key_version")
    ordered = tuple(sorted(assignments, key=lambda item: item.entity_id))
    parts: list[str] = [
        "mapping-snapshot-v2",
        snapshot_version,
        namespace_id,
        entity_graph_version_id,
        policy_version,
        namespace_key_ref.opaque_id,
        namespace_key_ref.namespace_id,
        namespace_key_ref.key_version,
        str(len(ordered)),
    ]
    for item in ordered:
        parts.append(item.entity_id)
        parts.append(item.profile_id)
    return length_prefixed_utf8(*parts)


def compute_mapping_snapshot_opaque_id(
    *,
    snapshot_version: str,
    namespace_id: str,
    entity_graph_version_id: str,
    policy_version: str,
    namespace_key_ref: NamespaceKeyRef,
    assignments: tuple[MappingAssignment, ...] = (),
) -> str:
    """Content-addressed opaque id (unkeyed). Not an authenticity guarantee."""
    material = mapping_snapshot_commitment_material(
        snapshot_version=snapshot_version,
        namespace_id=namespace_id,
        entity_graph_version_id=entity_graph_version_id,
        policy_version=policy_version,
        namespace_key_ref=namespace_key_ref,
        assignments=assignments,
    )
    return f"map-{hashlib.sha256(material).hexdigest()[:24]}"


def compute_mapping_snapshot_commitment(
    *,
    snapshot_version: str,
    namespace_id: str,
    entity_graph_version_id: str,
    policy_version: str,
    namespace_key_ref: NamespaceKeyRef,
    assignments: tuple[MappingAssignment, ...] = (),
    namespace_secret: bytes,
) -> tuple[str, str]:
    """Return ``(opaque_id, private_integrity_digest)`` under namespace HMAC."""
    secret = _require_mapping_secret(namespace_secret)
    material = mapping_snapshot_commitment_material(
        snapshot_version=snapshot_version,
        namespace_id=namespace_id,
        entity_graph_version_id=entity_graph_version_id,
        policy_version=policy_version,
        namespace_key_ref=namespace_key_ref,
        assignments=assignments,
    )
    opaque_id = f"map-{hashlib.sha256(material).hexdigest()[:24]}"
    mac_hex = hmac.new(secret, material, hashlib.sha256).hexdigest()
    return opaque_id, f"hmac-sha256:{mac_hex}"


def make_mapping_snapshot(
    *,
    snapshot_version: str,
    namespace_id: str,
    entity_graph_version_id: str,
    policy_version: str,
    namespace_key_ref: NamespaceKeyRef,
    assignments: tuple[MappingAssignment, ...] = (),
    namespace_secret: bytes,
) -> MappingSnapshot:
    """Build a validated snapshot with HMAC integrity under ``namespace_secret``."""
    opaque_id, digest = compute_mapping_snapshot_commitment(
        snapshot_version=snapshot_version,
        namespace_id=namespace_id,
        entity_graph_version_id=entity_graph_version_id,
        policy_version=policy_version,
        namespace_key_ref=namespace_key_ref,
        assignments=assignments,
        namespace_secret=namespace_secret,
    )
    snapshot = MappingSnapshot(
        opaque_id=opaque_id,
        snapshot_version=snapshot_version,
        namespace_id=namespace_id,
        entity_graph_version_id=entity_graph_version_id,
        policy_version=policy_version,
        namespace_key_ref=namespace_key_ref,
        private_integrity_digest=digest,
        assignments=assignments,
    )
    validate_mapping_snapshot(snapshot, namespace_secret=namespace_secret)
    return snapshot


def validate_namespace_key_ref(ref: NamespaceKeyRef) -> None:
    require_opaque_id(ref.opaque_id, "opaque_id")
    require_opaque_id(ref.namespace_id, "namespace_id")
    require_version_token(ref.key_version, "key_version")


def validate_entity_graph_version(graph: EntityGraphVersion) -> None:
    require_opaque_id(graph.opaque_id, "opaque_id")
    require_version_token(graph.graph_version, "graph_version")
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


def validate_mapping_snapshot_structure(snapshot: MappingSnapshot) -> None:
    """Validate fields, duplicates, digest shape, and content-addressed opaque_id.

    Does not authenticate ``private_integrity_digest``; call
    ``validate_mapping_snapshot`` with ``namespace_secret`` for HMAC verification.
    """
    require_opaque_id(snapshot.opaque_id, "opaque_id")
    require_version_token(snapshot.snapshot_version, "snapshot_version")
    require_opaque_id(snapshot.namespace_id, "namespace_id")
    require_opaque_id(snapshot.entity_graph_version_id, "entity_graph_version_id")
    require_version_token(snapshot.policy_version, "policy_version")
    if not isinstance(snapshot.namespace_key_ref, NamespaceKeyRef):
        raise DomainValidationError("namespace_key_ref must be a NamespaceKeyRef")
    validate_namespace_key_ref(snapshot.namespace_key_ref)
    if snapshot.namespace_key_ref.namespace_id != snapshot.namespace_id:
        raise DomainValidationError(
            "namespace_key_ref.namespace_id must match mapping snapshot namespace_id"
        )
    validate_private_integrity_digest(snapshot.private_integrity_digest)
    if not snapshot.private_integrity_digest.startswith("hmac-sha256:"):
        raise DomainValidationError(
            "mapping snapshot private_integrity_digest must use hmac-sha256"
        )
    seen_entities: set[str] = set()
    for assignment in snapshot.assignments:
        validate_mapping_assignment(assignment)
        if assignment.entity_id in seen_entities:
            raise DomainValidationError(
                f"duplicate entity assignment in snapshot: {assignment.entity_id}"
            )
        seen_entities.add(assignment.entity_id)

    expected_id = compute_mapping_snapshot_opaque_id(
        snapshot_version=snapshot.snapshot_version,
        namespace_id=snapshot.namespace_id,
        entity_graph_version_id=snapshot.entity_graph_version_id,
        policy_version=snapshot.policy_version,
        namespace_key_ref=snapshot.namespace_key_ref,
        assignments=snapshot.assignments,
    )
    if snapshot.opaque_id != expected_id:
        raise DomainValidationError("mapping snapshot opaque_id does not match committed content")


def validate_mapping_snapshot(snapshot: MappingSnapshot, *, namespace_secret: bytes) -> None:
    """Authenticate snapshot content under the namespace HMAC secret."""
    validate_mapping_snapshot_structure(snapshot)
    _expected_id, expected_digest = compute_mapping_snapshot_commitment(
        snapshot_version=snapshot.snapshot_version,
        namespace_id=snapshot.namespace_id,
        entity_graph_version_id=snapshot.entity_graph_version_id,
        policy_version=snapshot.policy_version,
        namespace_key_ref=snapshot.namespace_key_ref,
        assignments=snapshot.assignments,
        namespace_secret=namespace_secret,
    )
    if snapshot.private_integrity_digest != expected_digest:
        raise DomainValidationError(
            "mapping snapshot private_integrity_digest does not match committed content"
        )


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
    validate_mapping_snapshot_structure(left)
    validate_mapping_snapshot_structure(right)
    left_assignments = frozenset((item.entity_id, item.profile_id) for item in left.assignments)
    right_assignments = frozenset((item.entity_id, item.profile_id) for item in right.assignments)
    return (
        left.opaque_id == right.opaque_id
        and left.snapshot_version == right.snapshot_version
        and left.namespace_id == right.namespace_id
        and left.entity_graph_version_id == right.entity_graph_version_id
        and left.policy_version == right.policy_version
        and left.namespace_key_ref == right.namespace_key_ref
        and left.private_integrity_digest == right.private_integrity_digest
        and left_assignments == right_assignments
    )
