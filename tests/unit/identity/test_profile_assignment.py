"""Unit tests for namespace-scoped profile assignment and freeze."""

from __future__ import annotations

import pytest

from cloakmill.domain import EntityKind, NamespaceKeyRef
from cloakmill.domain.enums import AnchorKind
from cloakmill.domain.mapping import MappingAssignment
from cloakmill.identity import (
    AcceptedEntity,
    AcceptedEntityGraph,
    AssignmentError,
    FrozenMappingError,
    FrozenMappingStore,
    NamespaceKeyMaterial,
    NamespaceScope,
    NamespaceScopedProfileAssigner,
    StrongAnchor,
    SyntheticProfile,
    assert_frozen_immutable,
    freeze_mapping,
    frozen_bundles_equal,
    opaque_anchor_ref,
)


def _scope() -> NamespaceScope:
    return NamespaceScope(
        customer_id="cust-demo",
        project_id="proj-alpha",
        recipient_id="rcpt-train",
    )


def _key(scope: NamespaceScope) -> NamespaceKeyMaterial:
    return NamespaceKeyMaterial(
        key_ref=NamespaceKeyRef(
            opaque_id="nkr-demo-1",
            namespace_id=scope.namespace_id,
            key_version="nk.v1",
        ),
        key_bytes=b"synthetic-test-key-material",
    )


def _person(entity_id: str) -> AcceptedEntity:
    # Assignment consumes opaque entity ids only — no cleartext anchors required.
    return AcceptedEntity(
        opaque_id=entity_id,
        entity_kind=EntityKind.PERSON,
        observation_ids=(f"obs-{entity_id}",),
    )


def _graph(
    *entities: AcceptedEntity,
    scope: NamespaceScope,
    version: str = "graph.v1",
) -> AcceptedEntityGraph:
    return AcceptedEntityGraph(
        opaque_id="graph-demo-1",
        graph_version=version,
        namespace_id=scope.namespace_id,
        entities=entities,
    )


def test_same_entity_gets_same_profile_within_namespace() -> None:
    scope = _scope()
    key = _key(scope)
    graph = _graph(_person("ent-maya"), scope=scope)
    assigner = NamespaceScopedProfileAssigner()

    first = freeze_mapping(
        assigner.assign(graph=graph, namespace=scope, key_material=key, snapshot_version="map.v1")
    )
    second = freeze_mapping(
        assigner.assign(graph=graph, namespace=scope, key_material=key, snapshot_version="map.v1")
    )

    assert frozen_bundles_equal(first, second)
    profile = first.profile_for_entity("ent-maya")
    assert profile.entity_kind is EntityKind.PERSON
    assert profile.full_name == f"{profile.given_name} {profile.family_name}"
    assert profile.email is not None and profile.email.endswith("@profiles.example")
    assert profile.employee_id is not None and profile.employee_id.startswith("E-")
    # Frozen mapping artifacts must not embed strong-anchor cleartext.
    assert "strong_anchors" not in first.snapshot.to_dict()
    assert "normalized_value" not in first.to_dict()


def test_distinct_entities_do_not_collide_on_unique_attrs() -> None:
    scope = _scope()
    key = _key(scope)
    graph = _graph(_person("ent-a"), _person("ent-b"), _person("ent-c"), scope=scope)
    bundle = freeze_mapping(
        NamespaceScopedProfileAssigner().assign(
            graph=graph,
            namespace=scope,
            key_material=key,
            snapshot_version="map.v1",
        )
    )
    emails = [bundle.profile_for_entity(eid).email for eid in ("ent-a", "ent-b", "ent-c")]
    employee_ids = [
        bundle.profile_for_entity(eid).employee_id for eid in ("ent-a", "ent-b", "ent-c")
    ]
    assert len(set(emails)) == 3
    assert len(set(employee_ids)) == 3


def test_namespaces_isolate_assignments() -> None:
    scope_a = NamespaceScope("cust-1", "proj-1", "rcpt-a")
    scope_b = NamespaceScope("cust-1", "proj-1", "rcpt-b")
    assert scope_a.namespace_id != scope_b.namespace_id

    entity = _person("ent-shared-id")
    assigner = NamespaceScopedProfileAssigner()
    bundle_a = freeze_mapping(
        assigner.assign(
            graph=_graph(entity, scope=scope_a),
            namespace=scope_a,
            key_material=_key(scope_a),
            snapshot_version="map.v1",
        )
    )
    # Same opaque entity id string under a different namespace scope.
    bundle_b = freeze_mapping(
        assigner.assign(
            graph=_graph(entity, scope=scope_b),
            namespace=scope_b,
            key_material=_key(scope_b),
            snapshot_version="map.v1",
        )
    )
    assert (
        bundle_a.profile_for_entity("ent-shared-id").email
        != bundle_b.profile_for_entity("ent-shared-id").email
    )


def test_freeze_is_immutable() -> None:
    scope = _scope()
    key = _key(scope)
    draft = NamespaceScopedProfileAssigner().assign(
        graph=_graph(_person("ent-maya"), scope=scope),
        namespace=scope,
        key_material=key,
        snapshot_version="map.v1",
    )
    bundle = freeze_mapping(draft)
    assert_frozen_immutable(bundle)

    store = FrozenMappingStore()
    store.put(bundle)
    # Equal re-put is idempotent.
    assert store.put(bundle) is bundle

    tampered = SyntheticProfile(
        opaque_id=bundle.profiles[0].opaque_id,
        entity_kind=EntityKind.PERSON,
        namespace_id=scope.namespace_id,
        given_name="Tampered",
        family_name="Name",
        full_name="Tampered Name",
        email="tampered.name.0001@profiles.example",
        employee_id="E-TAMPER1",
    )
    from cloakmill.identity.freeze import FrozenMappingBundle

    mutated = FrozenMappingBundle(
        snapshot=bundle.snapshot,
        graph_version=bundle.graph_version,
        profiles=(tampered,),
    )
    with pytest.raises(FrozenMappingError):
        store.put(mutated)


def test_incremental_run_preserves_prior_assignments() -> None:
    scope = _scope()
    key = _key(scope)
    assigner = NamespaceScopedProfileAssigner()

    first_graph = _graph(_person("ent-maya"), scope=scope, version="graph.v1")
    first = freeze_mapping(
        assigner.assign(
            graph=first_graph,
            namespace=scope,
            key_material=key,
            snapshot_version="map.v1",
        )
    )
    maya_profile = first.profile_for_entity("ent-maya")

    second_graph = _graph(
        _person("ent-maya"),
        _person("ent-jordan"),
        scope=scope,
        version="graph.v2",
    )
    draft = assigner.assign(
        graph=second_graph,
        namespace=scope,
        key_material=key,
        snapshot_version="map.v2",
        prior_assignments=first.assignments,
        prior_profiles=first.profiles,
    )
    second = freeze_mapping(draft)

    assert "ent-maya" in draft.reused_entity_ids
    assert "ent-jordan" in draft.newly_assigned_entity_ids
    assert second.profile_for_entity("ent-maya") == maya_profile
    assert second.profile_for_entity("ent-jordan").opaque_id != maya_profile.opaque_id
    assert second.profile_for_entity("ent-jordan").email != maya_profile.email
    assert second.snapshot.snapshot_version == "map.v2"
    assert second.snapshot.opaque_id != first.snapshot.opaque_id


def test_account_and_org_profiles_are_coherent() -> None:
    scope = _scope()
    key = _key(scope)
    graph = AcceptedEntityGraph(
        opaque_id="graph-mixed",
        graph_version="graph.v1",
        namespace_id=scope.namespace_id,
        entities=(
            AcceptedEntity(
                opaque_id="ent-helpdesk",
                entity_kind=EntityKind.ACCOUNT,
                observation_ids=("obs-help",),
            ),
            AcceptedEntity(
                opaque_id="ent-acme",
                entity_kind=EntityKind.ORGANIZATION,
                observation_ids=("obs-org",),
            ),
        ),
    )
    bundle = freeze_mapping(
        NamespaceScopedProfileAssigner().assign(
            graph=graph,
            namespace=scope,
            key_material=key,
            snapshot_version="map.v1",
        )
    )
    account = bundle.profile_for_entity("ent-helpdesk")
    org = bundle.profile_for_entity("ent-acme")
    assert account.account_id and account.display_name and account.email
    assert org.organization_name
    assert account.email != org.organization_name


def test_mismatched_namespace_rejected() -> None:
    scope = _scope()
    other = NamespaceScope("cust-x", "proj-x", "rcpt-x")
    with pytest.raises(AssignmentError):
        NamespaceScopedProfileAssigner().assign(
            graph=_graph(_person("ent-maya"), scope=other),
            namespace=scope,
            key_material=_key(scope),
            snapshot_version="map.v1",
        )


def test_prior_assignment_without_profile_rejected() -> None:
    scope = _scope()
    with pytest.raises(AssignmentError):
        NamespaceScopedProfileAssigner().assign(
            graph=_graph(_person("ent-maya"), scope=scope),
            namespace=scope,
            key_material=_key(scope),
            snapshot_version="map.v1",
            prior_assignments=(MappingAssignment(entity_id="ent-maya", profile_id="prof-missing"),),
            prior_profiles=(),
        )


def test_optional_anchors_are_ignored_by_assignment() -> None:
    """Even if a graph still carries opaque anchors, freeze artifacts stay cleartext-free."""
    scope = _scope()
    secret = b"synthetic-test-key-material"
    opaque = opaque_anchor_ref(
        kind=AnchorKind.EMAIL,
        normalized_value="maya@acme.example",
        namespace_secret=secret,
    )
    entity = AcceptedEntity(
        opaque_id="ent-maya",
        entity_kind=EntityKind.PERSON,
        observation_ids=("obs-ent-maya",),
        strong_anchors=(StrongAnchor(kind=AnchorKind.EMAIL, opaque_ref=opaque),),
    )
    bundle = freeze_mapping(
        NamespaceScopedProfileAssigner().assign(
            graph=_graph(entity, scope=scope),
            namespace=scope,
            key_material=_key(scope),
            snapshot_version="map.v1",
        )
    )
    dumped = bundle.to_dict()
    assert "maya@acme.example" not in str(dumped)
    assert "normalized_value" not in str(dumped)
    # Assignment freeze vault does not embed graph strong_anchors.
    assert "strong_anchors" not in dumped["snapshot"]
    assert "opaque_ref" not in str(dumped)


def test_empty_graph_freeze_assert_immutable_returns_cleanly() -> None:
    """Bugbot regression: empty profiles must not IndexError in assert_frozen_immutable."""
    scope = _scope()
    empty = AcceptedEntityGraph(
        opaque_id="graph-empty",
        graph_version="graph.v0",
        namespace_id=scope.namespace_id,
        entities=(),
    )
    bundle = freeze_mapping(
        NamespaceScopedProfileAssigner().assign(
            graph=empty,
            namespace=scope,
            key_material=_key(scope),
            snapshot_version="map.v0",
        )
    )
    assert bundle.profiles == ()
    assert bundle.assignments == ()
    assert_frozen_immutable(bundle)
