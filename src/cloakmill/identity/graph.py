"""Versioned accepted entity graph and identity decision records.

These shapes are produced by strong-anchor resolution (F06). They intentionally
omit synthetic profile assignments and mapping key material (F07).

Serialized graph records carry opaque keyed refs only — never cleartext emails,
employee/account ids, or names.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cloakmill.domain.enums import AnchorKind, DecisionOutcome, EntityKind
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_non_empty_str, require_opaque_id


@dataclass(frozen=True, slots=True)
class StrongAnchor:
    """A strong identity anchor attached to an accepted entity.

    ``opaque_ref`` is a keyed digest (see ``opaque_anchor_ref``). Cleartext
    values never belong on this record or in ``to_dict()``.
    """

    kind: AnchorKind
    opaque_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "opaque_ref": self.opaque_ref}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrongAnchor:
        if not isinstance(data, dict):
            raise DomainValidationError("strong anchor must be an object")
        if "normalized_value" in data:
            raise DomainValidationError(
                "strong anchor must not carry cleartext normalized_value; use opaque_ref"
            )
        try:
            kind = AnchorKind(data["kind"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid strong anchor kind: {exc}") from exc
        anchor = cls(kind=kind, opaque_ref=data.get("opaque_ref", ""))
        validate_strong_anchor(anchor)
        return anchor


@dataclass(frozen=True, slots=True)
class AcceptedEntity:
    """One accepted entity in a versioned graph, distinct by kind."""

    opaque_id: str
    entity_kind: EntityKind
    observation_ids: tuple[str, ...]
    strong_anchors: tuple[StrongAnchor, ...] = ()
    directory_entity_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "entity_kind": self.entity_kind.value,
            "observation_ids": list(self.observation_ids),
            "strong_anchors": [anchor.to_dict() for anchor in self.strong_anchors],
        }
        if self.directory_entity_key is not None:
            payload["directory_entity_key"] = self.directory_entity_key
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptedEntity:
        if not isinstance(data, dict):
            raise DomainValidationError("accepted entity must be an object")
        try:
            entity_kind = EntityKind(data["entity_kind"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid accepted entity kind: {exc}") from exc
        raw_obs = data.get("observation_ids", [])
        raw_anchors = data.get("strong_anchors", [])
        if not isinstance(raw_obs, list):
            raise DomainValidationError("observation_ids must be a list")
        if not isinstance(raw_anchors, list):
            raise DomainValidationError("strong_anchors must be a list")
        entity = cls(
            opaque_id=data.get("opaque_id", ""),
            entity_kind=entity_kind,
            observation_ids=tuple(raw_obs),
            strong_anchors=tuple(StrongAnchor.from_dict(item) for item in raw_anchors),
            directory_entity_key=data.get("directory_entity_key"),
        )
        validate_accepted_entity(entity)
        return entity


@dataclass(frozen=True, slots=True)
class IdentityDecision:
    """Automatic or review-bound identity decision with rule provenance."""

    opaque_id: str
    outcome: DecisionOutcome
    rule_id: str
    rule_version: str
    observation_ids: tuple[str, ...]
    reason_code: str
    entity_id: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "outcome": self.outcome.value,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "observation_ids": list(self.observation_ids),
            "reason_code": self.reason_code,
            "evidence_refs": list(self.evidence_refs),
        }
        if self.entity_id is not None:
            payload["entity_id"] = self.entity_id
        return payload


@dataclass(frozen=True, slots=True)
class ExceptionGroup:
    """Grouped unresolved mentions for exception review (not per-mention approval).

    ``weak_signal_refs`` holds keyed opaque refs only — never cleartext names.
    """

    opaque_id: str
    reason_code: str
    observation_ids: tuple[str, ...]
    candidate_entity_ids: tuple[str, ...] = ()
    weak_signal_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_id": self.opaque_id,
            "reason_code": self.reason_code,
            "observation_ids": list(self.observation_ids),
            "candidate_entity_ids": list(self.candidate_entity_ids),
            "weak_signal_refs": list(self.weak_signal_refs),
        }


@dataclass(frozen=True, slots=True)
class ContradictionConstraint:
    """Preserved conflicting constraint that blocked an automatic merge."""

    opaque_id: str
    reason_code: str
    left_observation_ids: tuple[str, ...]
    right_observation_ids: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_id": self.opaque_id,
            "reason_code": self.reason_code,
            "left_observation_ids": list(self.left_observation_ids),
            "right_observation_ids": list(self.right_observation_ids),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AcceptedEntityGraph:
    """Versioned accepted entity graph pinned for later mapping freeze (F07)."""

    opaque_id: str
    graph_version: str
    namespace_id: str
    entities: tuple[AcceptedEntity, ...] = ()

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(entity.opaque_id for entity in self.entities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_id": self.opaque_id,
            "graph_version": self.graph_version,
            "namespace_id": self.namespace_id,
            "entities": [entity.to_dict() for entity in self.entities],
            "entity_ids": list(self.entity_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptedEntityGraph:
        if not isinstance(data, dict):
            raise DomainValidationError("accepted entity graph must be an object")
        raw_entities = data.get("entities", [])
        if not isinstance(raw_entities, list):
            raise DomainValidationError("entities must be a list")
        graph = cls(
            opaque_id=data.get("opaque_id", ""),
            graph_version=data.get("graph_version", ""),
            namespace_id=data.get("namespace_id", ""),
            entities=tuple(AcceptedEntity.from_dict(item) for item in raw_entities),
        )
        validate_accepted_entity_graph(graph)
        return graph


@dataclass(frozen=True, slots=True)
class PrivateAnchorIndex:
    """In-process cleartext lookup by opaque_ref.

    Private-boundary only: intentionally has no ``to_dict``. Never place this
    object in release manifests, logs, or UI DTOs.
    """

    values: Mapping[str, str]

    def get(self, opaque_ref: str) -> str | None:
        return self.values.get(opaque_ref)


def validate_strong_anchor(anchor: StrongAnchor) -> None:
    if not isinstance(anchor.kind, AnchorKind):
        raise DomainValidationError("strong anchor kind must be an AnchorKind")
    if anchor.kind not in {AnchorKind.EMAIL, AnchorKind.EMPLOYEE_ID, AnchorKind.ACCOUNT_ID}:
        raise DomainValidationError(f"strong anchor kind must be strong, got {anchor.kind!r}")
    require_opaque_id(anchor.opaque_ref, "opaque_ref")


def validate_accepted_entity(entity: AcceptedEntity) -> None:
    require_opaque_id(entity.opaque_id, "opaque_id")
    if not isinstance(entity.entity_kind, EntityKind):
        raise DomainValidationError("entity_kind must be an EntityKind")
    seen_obs: set[str] = set()
    for obs_id in entity.observation_ids:
        require_opaque_id(obs_id, "observation_ids[]")
        if obs_id in seen_obs:
            raise DomainValidationError(f"duplicate observation_id on entity: {obs_id}")
        seen_obs.add(obs_id)
    seen_anchors: set[tuple[str, str]] = set()
    for anchor in entity.strong_anchors:
        validate_strong_anchor(anchor)
        key = (anchor.kind.value, anchor.opaque_ref)
        if key in seen_anchors:
            raise DomainValidationError(
                f"duplicate strong anchor on entity for kind {anchor.kind.value}"
            )
        seen_anchors.add(key)
    if entity.directory_entity_key is not None:
        require_opaque_id(entity.directory_entity_key, "directory_entity_key")


def validate_accepted_entity_graph(graph: AcceptedEntityGraph) -> None:
    require_opaque_id(graph.opaque_id, "opaque_id")
    require_non_empty_str(graph.graph_version, "graph_version")
    require_opaque_id(graph.namespace_id, "namespace_id")
    seen: set[str] = set()
    for entity in graph.entities:
        validate_accepted_entity(entity)
        if entity.opaque_id in seen:
            raise DomainValidationError(f"duplicate entity_id in graph: {entity.opaque_id}")
        seen.add(entity.opaque_id)


def accepted_entity_graphs_equal(left: AcceptedEntityGraph, right: AcceptedEntityGraph) -> bool:
    """Structural equality for freeze/replay checks (ignores dict key order)."""
    return left.to_dict() == right.to_dict()
