"""Integration: resolve → assign → freeze → incremental reuse / collision."""

from __future__ import annotations

import hashlib

from cloakmill.domain import EntityKind, NamespaceKeyRef
from cloakmill.domain.enums import AnchorKind
from cloakmill.identity import (
    DirectoryAnchor,
    FrozenMappingStore,
    MentionEvidence,
    NamespaceKeyMaterial,
    NamespaceScope,
    NamespaceScopedProfileAssigner,
    StrongAnchorIdentityResolver,
    entity_opaque_id,
    freeze_mapping,
    frozen_bundles_equal,
)

TEST_NAMESPACE_SECRET = b"integration-synthetic-key!!"


def _mention(
    obs_id: str,
    entity_type: str,
    value: str,
    *,
    part_id: str = "part-1",
) -> MentionEvidence:
    return MentionEvidence(
        observation_id=obs_id,
        entity_type=entity_type,
        normalized_value=value,
        part_id=part_id,
        artifact_version_id="art-int-1",
    )


def test_resolve_assign_freeze_incremental_and_collision() -> None:
    scope = NamespaceScope(
        customer_id="cust-int",
        project_id="proj-int",
        recipient_id="rcpt-int",
    )
    key = NamespaceKeyMaterial(
        key_ref=NamespaceKeyRef(
            opaque_id="nkr-int-1",
            namespace_id=scope.namespace_id,
            key_version="nk.v1",
        ),
        key_bytes=TEST_NAMESPACE_SECRET,
    )

    resolver = StrongAnchorIdentityResolver()
    first_resolution = resolver.resolve(
        [
            _mention("obs-maya-email", "email_address", "maya@acme.example"),
            _mention("obs-maya-emp", "employee_id", "E-AB12CD", part_id="part-1"),
            _mention("obs-help", "account_id", "AC-104", part_id="part-2"),
        ],
        namespace_id=scope.namespace_id,
        namespace_secret=TEST_NAMESPACE_SECRET,
        directory=[
            DirectoryAnchor(
                anchor_kind=AnchorKind.ACCOUNT_ID,
                normalized_value="AC-104",
                entity_kind=EntityKind.ACCOUNT,
                entity_key="acct-helpdesk",
                is_shared=True,
                operator_person_keys=("person-maya",),
            )
        ],
    )
    # Rewrite graph namespace to the scoped namespace id (resolver already uses it).
    graph_v1 = first_resolution.graph
    assert graph_v1.namespace_id == scope.namespace_id
    assert len(graph_v1.entities) >= 2

    assigner = NamespaceScopedProfileAssigner()
    draft_v1 = assigner.assign(
        graph=graph_v1,
        namespace=scope,
        key_material=key,
        snapshot_version="map.v1",
    )
    frozen_v1 = freeze_mapping(draft_v1)
    store = FrozenMappingStore()
    store.put(frozen_v1)

    # Replay with identical inputs yields an equal frozen bundle.
    replay = freeze_mapping(
        assigner.assign(
            graph=graph_v1,
            namespace=scope,
            key_material=key,
            snapshot_version="map.v1",
        )
    )
    assert frozen_bundles_equal(frozen_v1, replay)
    store.put(replay)  # idempotent

    # Unique attrs must not collide across entities in the namespace.
    unique_emails = {
        frozen_v1.profile_for_entity(entity.opaque_id).email
        for entity in graph_v1.entities
        if frozen_v1.profile_for_entity(entity.opaque_id).email is not None
    }
    assert len(unique_emails) == sum(
        1
        for entity in graph_v1.entities
        if frozen_v1.profile_for_entity(entity.opaque_id).email is not None
    )

    # Incremental import: reuse prior person/account, assign a new person.
    second_resolution = resolver.resolve(
        [
            _mention("obs-maya-email", "email_address", "maya@acme.example"),
            _mention("obs-maya-emp", "employee_id", "E-AB12CD", part_id="part-1"),
            _mention("obs-help", "account_id", "AC-104", part_id="part-2"),
            _mention("obs-jordan", "email_address", "jordan@acme.example", part_id="part-3"),
        ],
        namespace_id=scope.namespace_id,
        namespace_secret=TEST_NAMESPACE_SECRET,
        directory=[
            DirectoryAnchor(
                anchor_kind=AnchorKind.ACCOUNT_ID,
                normalized_value="AC-104",
                entity_kind=EntityKind.ACCOUNT,
                entity_key="acct-helpdesk",
                is_shared=True,
                operator_person_keys=("person-maya",),
            )
        ],
    )
    graph_v2 = second_resolution.graph
    prior_entity_ids = set(graph_v1.entity_ids)
    draft_v2 = assigner.assign(
        graph=graph_v2,
        namespace=scope,
        key_material=key,
        snapshot_version="map.v2",
        prior_assignments=frozen_v1.assignments,
        prior_profiles=frozen_v1.profiles,
    )
    frozen_v2 = freeze_mapping(draft_v2)

    for entity_id in prior_entity_ids & set(graph_v2.entity_ids):
        assert entity_id in draft_v2.reused_entity_ids
        assert frozen_v2.profile_for_entity(entity_id) == frozen_v1.profile_for_entity(entity_id)

    new_ids = set(graph_v2.entity_ids) - prior_entity_ids
    assert new_ids
    assert set(draft_v2.newly_assigned_entity_ids) == new_ids
    for entity_id in new_ids:
        new_profile = frozen_v2.profile_for_entity(entity_id)
        for prior in frozen_v1.profiles:
            for attr, value in new_profile.unique_attributes().items():
                assert prior.unique_attributes().get(attr) != value

    # Release export stays free of source cleartext and profile vault.
    export = frozen_v2.to_export_dict()
    assert "profiles" not in export
    assert "maya@acme.example" not in str(export)
    assert "jordan@acme.example" not in str(export)
    assert "E-AB12CD" not in str(export)
    assert export["snapshot"]["private_integrity_digest"].startswith("sha256:")
    # Entity ids are not recoverable via unkeyed digests of candidate anchors.
    for candidate in ("maya@acme.example", "jordan@acme.example", "E-AB12CD", "AC-104"):
        unkeyed = hashlib.sha256(
            "\0".join(
                (
                    scope.namespace_id,
                    EntityKind.PERSON.value,
                    "email",
                    candidate,
                )
            ).encode("utf-8")
        ).hexdigest()[:24]
        assert all(unkeyed not in entity_id for entity_id in graph_v2.entity_ids)
        wrong = entity_opaque_id(
            entity_kind=EntityKind.PERSON,
            seed_anchor_kind=AnchorKind.EMAIL,
            seed_value=candidate,
            namespace_id=scope.namespace_id,
            namespace_secret=b"different-secret-xx",
        )
        assert wrong not in graph_v2.entity_ids

    store.put(frozen_v2)
    assert store.get(frozen_v2.snapshot.opaque_id) == frozen_v2
