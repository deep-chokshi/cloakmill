"""Namespace-scoped synthetic profile assignment with collision reservation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cloakmill.domain.fields import require_non_empty_str, require_opaque_id
from cloakmill.domain.mapping import (
    EntityGraphVersion,
    MappingAssignment,
    MappingSnapshot,
    NamespaceKeyRef,
    validate_mapping_snapshot,
)
from cloakmill.identity.errors import AssignmentError, CollisionExhaustedError
from cloakmill.identity.graph import (
    AcceptedEntity,
    AcceptedEntityGraph,
    validate_accepted_entity_graph,
)
from cloakmill.identity.namespace import (
    NamespaceScope,
    require_matching_namespace,
    validate_namespace_scope,
)
from cloakmill.identity.profiles import (
    ASSIGNMENT_POLICY_VERSION,
    NamespaceKeyMaterial,
    SyntheticProfile,
    derive_profile_candidate,
    validate_synthetic_profile,
)
from cloakmill.identity.registry import AttributeReservationRegistry

DEFAULT_MAX_COLLISION_ATTEMPTS = 64


@dataclass(frozen=True, slots=True)
class MappingAssignmentDraft:
    """Mutable-construction result prior to freeze. Treat as read-only once returned."""

    namespace: NamespaceScope
    graph_version: EntityGraphVersion
    key_ref: NamespaceKeyRef
    policy_version: str
    snapshot_version: str
    assignments: tuple[MappingAssignment, ...]
    profiles: tuple[SyntheticProfile, ...]
    reused_entity_ids: tuple[str, ...]
    newly_assigned_entity_ids: tuple[str, ...]

    def profile_by_id(self) -> dict[str, SyntheticProfile]:
        return {profile.opaque_id: profile for profile in self.profiles}

    def profile_for_entity(self, entity_id: str) -> SyntheticProfile:
        by_entity = {item.entity_id: item.profile_id for item in self.assignments}
        try:
            profile_id = by_entity[entity_id]
        except KeyError as exc:
            raise AssignmentError(f"no assignment for entity {entity_id!r}") from exc
        return self.profile_by_id()[profile_id]


class NamespaceScopedProfileAssigner:
    """Assign coherent synthetic profiles under a customer/project/recipient namespace."""

    def __init__(self, *, max_collision_attempts: int = DEFAULT_MAX_COLLISION_ATTEMPTS) -> None:
        if max_collision_attempts < 1:
            raise AssignmentError("max_collision_attempts must be >= 1")
        self._max_collision_attempts = max_collision_attempts

    def assign(
        self,
        *,
        graph: AcceptedEntityGraph,
        namespace: NamespaceScope,
        key_material: NamespaceKeyMaterial,
        snapshot_version: str,
        policy_version: str = ASSIGNMENT_POLICY_VERSION,
        prior_assignments: tuple[MappingAssignment, ...] = (),
        prior_profiles: tuple[SyntheticProfile, ...] = (),
    ) -> MappingAssignmentDraft:
        """Assign profiles for all graph entities, reusing prior bindings when present."""
        validate_accepted_entity_graph(graph)
        validate_namespace_scope(namespace)
        require_non_empty_str(snapshot_version, "snapshot_version")
        require_non_empty_str(policy_version, "policy_version")
        require_matching_namespace(
            expected=namespace.namespace_id,
            actual=graph.namespace_id,
            field_name="graph.namespace_id",
        )
        require_matching_namespace(
            expected=namespace.namespace_id,
            actual=key_material.key_ref.namespace_id,
            field_name="key_ref.namespace_id",
        )

        prior_by_entity = _index_prior(
            namespace_id=namespace.namespace_id,
            prior_assignments=prior_assignments,
            prior_profiles=prior_profiles,
        )
        registry = AttributeReservationRegistry()
        for entity_id, profile in prior_by_entity.items():
            registry.seed_entity_profile(
                namespace_id=namespace.namespace_id,
                entity_id=entity_id,
                profile=profile,
            )

        # Stable reservation order: sorted entity opaque ids.
        entities = tuple(sorted(graph.entities, key=lambda item: item.opaque_id))
        assignments: list[MappingAssignment] = []
        profiles: list[SyntheticProfile] = []
        reused: list[str] = []
        newly: list[str] = []
        seen_profile_ids: set[str] = set()

        for entity in entities:
            prior_profile = prior_by_entity.get(entity.opaque_id)
            if prior_profile is not None:
                if prior_profile.entity_kind is not entity.entity_kind:
                    raise AssignmentError(
                        f"prior profile kind {prior_profile.entity_kind!r} does not match "
                        f"entity {entity.opaque_id!r} kind {entity.entity_kind!r}"
                    )
                profile = prior_profile
                reused.append(entity.opaque_id)
            else:
                profile = self._allocate_new_profile(
                    entity=entity,
                    namespace_id=namespace.namespace_id,
                    key_material=key_material,
                    policy_version=policy_version,
                    registry=registry,
                )
                newly.append(entity.opaque_id)

            if profile.opaque_id in seen_profile_ids:
                raise AssignmentError(f"duplicate profile_id in draft: {profile.opaque_id}")
            seen_profile_ids.add(profile.opaque_id)
            profiles.append(profile)
            assignments.append(
                MappingAssignment(entity_id=entity.opaque_id, profile_id=profile.opaque_id)
            )

        graph_version = EntityGraphVersion(
            opaque_id=_graph_version_id(graph),
            graph_version=graph.graph_version,
            namespace_id=namespace.namespace_id,
            entity_ids=tuple(entity.opaque_id for entity in entities),
        )
        return MappingAssignmentDraft(
            namespace=namespace,
            graph_version=graph_version,
            key_ref=key_material.key_ref,
            policy_version=policy_version,
            snapshot_version=snapshot_version,
            assignments=tuple(assignments),
            profiles=tuple(profiles),
            reused_entity_ids=tuple(reused),
            newly_assigned_entity_ids=tuple(newly),
        )

    def _allocate_new_profile(
        self,
        *,
        entity: AcceptedEntity,
        namespace_id: str,
        key_material: NamespaceKeyMaterial,
        policy_version: str,
        registry: AttributeReservationRegistry,
    ) -> SyntheticProfile:
        for attempt in range(self._max_collision_attempts):
            candidate = derive_profile_candidate(
                entity_id=entity.opaque_id,
                entity_kind=entity.entity_kind,
                namespace_id=namespace_id,
                key_material=key_material,
                policy_version=policy_version,
                attempt=attempt,
            )
            if registry.try_reserve_profile(
                namespace_id=namespace_id,
                entity_id=entity.opaque_id,
                profile=candidate,
            ):
                return candidate
        raise CollisionExhaustedError(
            f"could not reserve unique attributes for entity {entity.opaque_id!r} "
            f"after {self._max_collision_attempts} attempts"
        )


def build_mapping_snapshot(draft: MappingAssignmentDraft) -> MappingSnapshot:
    """Build a validated mapping snapshot from an assignment draft (not yet sealed)."""
    snapshot = MappingSnapshot(
        opaque_id=_snapshot_opaque_id(
            namespace_id=draft.namespace.namespace_id,
            snapshot_version=draft.snapshot_version,
            graph_version_id=draft.graph_version.opaque_id,
            assignments=draft.assignments,
        ),
        snapshot_version=draft.snapshot_version,
        namespace_id=draft.namespace.namespace_id,
        entity_graph_version_id=draft.graph_version.opaque_id,
        policy_version=draft.policy_version,
        namespace_key_ref=draft.key_ref,
        assignments=draft.assignments,
    )
    validate_mapping_snapshot(snapshot)
    return snapshot


def _index_prior(
    *,
    namespace_id: str,
    prior_assignments: tuple[MappingAssignment, ...],
    prior_profiles: tuple[SyntheticProfile, ...],
) -> dict[str, SyntheticProfile]:
    if len(prior_assignments) != len({item.entity_id for item in prior_assignments}):
        raise AssignmentError("prior_assignments contain duplicate entity_id values")
    profiles_by_id = {}
    for profile in prior_profiles:
        validate_synthetic_profile(profile)
        require_matching_namespace(
            expected=namespace_id,
            actual=profile.namespace_id,
            field_name="prior profile.namespace_id",
        )
        if profile.opaque_id in profiles_by_id:
            raise AssignmentError(f"duplicate prior profile_id: {profile.opaque_id}")
        profiles_by_id[profile.opaque_id] = profile

    indexed: dict[str, SyntheticProfile] = {}
    for assignment in prior_assignments:
        require_opaque_id(assignment.entity_id, "prior entity_id")
        require_opaque_id(assignment.profile_id, "prior profile_id")
        try:
            profile = profiles_by_id[assignment.profile_id]
        except KeyError as exc:
            raise AssignmentError(
                f"prior assignment references unknown profile_id {assignment.profile_id!r}"
            ) from exc
        indexed[assignment.entity_id] = profile
    return indexed


def _graph_version_id(graph: AcceptedEntityGraph) -> str:
    material = "\0".join((graph.namespace_id, graph.graph_version, *sorted(graph.entity_ids)))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"egv-{digest}"


def _snapshot_opaque_id(
    *,
    namespace_id: str,
    snapshot_version: str,
    graph_version_id: str,
    assignments: tuple[MappingAssignment, ...],
) -> str:
    material = "\0".join(
        (
            namespace_id,
            snapshot_version,
            graph_version_id,
            *(
                f"{item.entity_id}:{item.profile_id}"
                for item in sorted(assignments, key=lambda a: a.entity_id)
            ),
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"map-{digest}"
