"""Deterministic opaque ids for identity graph records and decisions."""

from __future__ import annotations

import hashlib

from cloakmill.domain.enums import AnchorKind, EntityKind


def entity_opaque_id(
    *,
    entity_kind: EntityKind,
    seed_anchor_kind: AnchorKind,
    seed_value: str,
    namespace_id: str,
) -> str:
    digest = _digest(namespace_id, entity_kind.value, seed_anchor_kind.value, seed_value)
    return f"ent-{entity_kind.value}-{digest}"


def decision_opaque_id(
    *,
    outcome: str,
    rule_id: str,
    observation_ids: tuple[str, ...],
) -> str:
    material = ",".join(sorted(observation_ids))
    digest = _digest(outcome, rule_id, material)
    return f"dec-{digest}"


def exception_opaque_id(*, reason_code: str, observation_ids: tuple[str, ...]) -> str:
    material = ",".join(sorted(observation_ids))
    digest = _digest(reason_code, material)
    return f"exc-{digest}"


def contradiction_opaque_id(*, left_key: str, right_key: str, reason_code: str) -> str:
    ordered = tuple(sorted((left_key, right_key)))
    digest = _digest(reason_code, ordered[0], ordered[1])
    return f"ctr-{digest}"


def graph_opaque_id(*, namespace_id: str, graph_version: str, entity_ids: tuple[str, ...]) -> str:
    material = ",".join(entity_ids)
    digest = _digest(namespace_id, graph_version, material)
    return f"graph-{digest}"


def _digest(*parts: str) -> str:
    material = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]
