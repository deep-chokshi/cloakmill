"""Behavioral tests for F03 mapping/policy snapshot contracts (synthetic only)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cloakmill.domain import (
    DomainValidationError,
    EntityGraphVersion,
    FieldPathLocator,
    MappingAssignment,
    MappingSnapshot,
    NamespaceKeyRef,
    PatchPlanEntry,
    PolicyAction,
    TextOffsetLocator,
    TextOffsetUnit,
    dumps,
    entity_graph_versions_equal,
    loads,
    mapping_snapshots_equal,
    to_jsonable,
    validate_entity_graph_version,
    validate_mapping_snapshot,
    validate_patch_plan_entry,
)
from cloakmill.identity import (
    MappingSnapshot as IdentityMappingSnapshot,
)
from cloakmill.identity import (
    PolicyAction as IdentityPolicyAction,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "synthetic_mapping_snapshot_bundle.json"


def _key_ref() -> NamespaceKeyRef:
    return NamespaceKeyRef(
        opaque_id="nkr-syn-demo-1",
        namespace_id="ns-syn-demo",
        key_version="nk.v1",
    )


def _graph() -> EntityGraphVersion:
    return EntityGraphVersion(
        opaque_id="egv-syn-demo-1",
        graph_version="graph.v3",
        namespace_id="ns-syn-demo",
        entity_ids=("ent-syn-maya", "ent-syn-shared-mailbox"),
    )


def _snapshot() -> MappingSnapshot:
    return MappingSnapshot(
        opaque_id="map-syn-demo-1",
        snapshot_version="map.v3",
        namespace_id="ns-syn-demo",
        entity_graph_version_id="egv-syn-demo-1",
        policy_version="policy.content.v2",
        namespace_key_ref=_key_ref(),
        assignments=(
            MappingAssignment(entity_id="ent-syn-maya", profile_id="prof-syn-a12"),
            MappingAssignment(entity_id="ent-syn-shared-mailbox", profile_id="prof-syn-b07"),
        ),
    )


def test_mapping_snapshot_and_graph_round_trip_json() -> None:
    graph = _graph()
    snapshot = _snapshot()
    assert loads(dumps(graph), EntityGraphVersion) == graph
    assert loads(dumps(snapshot), MappingSnapshot) == snapshot
    assert loads(dumps(_key_ref()), NamespaceKeyRef) == _key_ref()


def test_patch_plan_entries_round_trip_for_each_policy_action() -> None:
    entries = (
        PatchPlanEntry(
            opaque_id="patch-syn-email-1",
            mapping_snapshot_id="map-syn-demo-1",
            artifact_version_id="art-syn-crm-1",
            part_id="part-syn-row-0-owner",
            locator=FieldPathLocator(path=("rows", 0, "owner_email")),
            action=PolicyAction.REPLACE,
            entity_id="ent-syn-maya",
            replacement_ref="attr-syn-email-a12",
        ),
        PatchPlanEntry(
            opaque_id="patch-syn-token-1",
            mapping_snapshot_id="map-syn-demo-1",
            artifact_version_id="art-syn-crm-1",
            part_id="part-syn-row-0-token",
            locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=12, end=40),
            action=PolicyAction.INERT,
            replacement_ref="attr-syn-inert-cred-1",
        ),
        PatchPlanEntry(
            opaque_id="patch-syn-remove-1",
            mapping_snapshot_id="map-syn-demo-1",
            artifact_version_id="art-syn-note-1",
            part_id="part-syn-note-body",
            locator=TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=0, end=8),
            action=PolicyAction.REMOVE,
        ),
        PatchPlanEntry(
            opaque_id="patch-syn-exclude-1",
            mapping_snapshot_id="map-syn-demo-1",
            artifact_version_id="art-syn-bin-1",
            part_id="part-syn-unsupported",
            locator=FieldPathLocator(path=("blob",)),
            action=PolicyAction.EXCLUDE,
        ),
    )
    for entry in entries:
        validate_patch_plan_entry(entry)
        assert loads(dumps(entry), PatchPlanEntry) == entry


def test_snapshot_equality_ignores_assignment_and_entity_order() -> None:
    left_graph = _graph()
    right_graph = EntityGraphVersion(
        opaque_id=left_graph.opaque_id,
        graph_version=left_graph.graph_version,
        namespace_id=left_graph.namespace_id,
        entity_ids=tuple(reversed(left_graph.entity_ids)),
    )
    assert entity_graph_versions_equal(left_graph, right_graph)

    left = _snapshot()
    right = MappingSnapshot(
        opaque_id=left.opaque_id,
        snapshot_version=left.snapshot_version,
        namespace_id=left.namespace_id,
        entity_graph_version_id=left.entity_graph_version_id,
        policy_version=left.policy_version,
        namespace_key_ref=left.namespace_key_ref,
        assignments=tuple(reversed(left.assignments)),
    )
    assert mapping_snapshots_equal(left, right)

    different_policy = MappingSnapshot(
        opaque_id=left.opaque_id,
        snapshot_version=left.snapshot_version,
        namespace_id=left.namespace_id,
        entity_graph_version_id=left.entity_graph_version_id,
        policy_version="policy.content.v9",
        namespace_key_ref=left.namespace_key_ref,
        assignments=left.assignments,
    )
    assert not mapping_snapshots_equal(left, different_policy)


def test_version_fields_are_required() -> None:
    with pytest.raises(DomainValidationError, match="graph_version"):
        validate_entity_graph_version(
            EntityGraphVersion(
                opaque_id="egv-syn-bad",
                graph_version="   ",
                namespace_id="ns-syn-demo",
            )
        )
    with pytest.raises(DomainValidationError, match="key_version"):
        NamespaceKeyRef.from_dict(
            {"opaque_id": "nkr-syn-bad", "namespace_id": "ns-syn-demo", "key_version": ""}
        )
    with pytest.raises(DomainValidationError, match="snapshot_version"):
        validate_mapping_snapshot(
            MappingSnapshot(
                opaque_id="map-syn-bad",
                snapshot_version="",
                namespace_id="ns-syn-demo",
                entity_graph_version_id="egv-syn-demo-1",
                policy_version="policy.content.v2",
                namespace_key_ref=_key_ref(),
            )
        )
    with pytest.raises(DomainValidationError, match="policy_version"):
        MappingSnapshot.from_dict(
            {
                "opaque_id": "map-syn-bad-policy",
                "snapshot_version": "map.v1",
                "namespace_id": "ns-syn-demo",
                "entity_graph_version_id": "egv-syn-demo-1",
                "policy_version": "",
                "namespace_key_ref": _key_ref().to_dict(),
                "assignments": [],
            }
        )


@pytest.mark.parametrize("bad_id", [None, 12, True])
def test_from_dict_rejects_null_and_non_string_ids(bad_id: object) -> None:
    with pytest.raises(DomainValidationError):
        NamespaceKeyRef.from_dict(
            {"opaque_id": bad_id, "namespace_id": "ns-syn-demo", "key_version": "nk.v1"}
        )
    with pytest.raises(DomainValidationError):
        NamespaceKeyRef.from_dict(
            {"opaque_id": "nkr-syn-demo-1", "namespace_id": bad_id, "key_version": "nk.v1"}
        )
    with pytest.raises(DomainValidationError):
        EntityGraphVersion.from_dict(
            {
                "opaque_id": bad_id,
                "graph_version": "graph.v3",
                "namespace_id": "ns-syn-demo",
                "entity_ids": ["ent-syn-maya"],
            }
        )
    with pytest.raises(DomainValidationError):
        EntityGraphVersion.from_dict(
            {
                "opaque_id": "egv-syn-demo-1",
                "graph_version": "graph.v3",
                "namespace_id": bad_id,
                "entity_ids": ["ent-syn-maya"],
            }
        )
    with pytest.raises(DomainValidationError):
        EntityGraphVersion.from_dict(
            {
                "opaque_id": "egv-syn-demo-1",
                "graph_version": "graph.v3",
                "namespace_id": "ns-syn-demo",
                "entity_ids": [bad_id],
            }
        )
    with pytest.raises(DomainValidationError):
        MappingAssignment.from_dict({"entity_id": bad_id, "profile_id": "prof-syn-a12"})
    with pytest.raises(DomainValidationError):
        MappingAssignment.from_dict({"entity_id": "ent-syn-maya", "profile_id": bad_id})
    with pytest.raises(DomainValidationError):
        MappingSnapshot.from_dict(
            {
                "opaque_id": bad_id,
                "snapshot_version": "map.v3",
                "namespace_id": "ns-syn-demo",
                "entity_graph_version_id": "egv-syn-demo-1",
                "policy_version": "policy.content.v2",
                "namespace_key_ref": _key_ref().to_dict(),
                "assignments": [],
            }
        )
    with pytest.raises(DomainValidationError):
        MappingSnapshot.from_dict(
            {
                "opaque_id": "map-syn-demo-1",
                "snapshot_version": "map.v3",
                "namespace_id": bad_id,
                "entity_graph_version_id": "egv-syn-demo-1",
                "policy_version": "policy.content.v2",
                "namespace_key_ref": _key_ref().to_dict(),
                "assignments": [],
            }
        )
    with pytest.raises(DomainValidationError):
        MappingSnapshot.from_dict(
            {
                "opaque_id": "map-syn-demo-1",
                "snapshot_version": "map.v3",
                "namespace_id": "ns-syn-demo",
                "entity_graph_version_id": bad_id,
                "policy_version": "policy.content.v2",
                "namespace_key_ref": _key_ref().to_dict(),
                "assignments": [],
            }
        )
    with pytest.raises(DomainValidationError):
        # Both namespace fields null must not coerce-match as "None" == "None".
        MappingSnapshot.from_dict(
            {
                "opaque_id": None,
                "snapshot_version": "map.v1",
                "namespace_id": None,
                "entity_graph_version_id": None,
                "policy_version": "p.v1",
                "namespace_key_ref": {
                    "opaque_id": None,
                    "namespace_id": None,
                    "key_version": "nk.v1",
                },
                "assignments": [{"entity_id": None, "profile_id": None}],
            }
        )
    with pytest.raises(DomainValidationError):
        PatchPlanEntry.from_dict(
            {
                "opaque_id": bad_id,
                "mapping_snapshot_id": "map-syn-demo-1",
                "artifact_version_id": "art-syn-crm-1",
                "part_id": "part-syn-row-0-owner",
                "locator": {"kind": "field_path", "path": ["rows", 0, "owner_email"]},
                "action": "replace",
                "entity_id": "ent-syn-maya",
                "replacement_ref": "attr-syn-email-a12",
            }
        )
    with pytest.raises(DomainValidationError):
        PatchPlanEntry.from_dict(
            {
                "opaque_id": "patch-syn-email-1",
                "mapping_snapshot_id": bad_id,
                "artifact_version_id": "art-syn-crm-1",
                "part_id": "part-syn-row-0-owner",
                "locator": {"kind": "field_path", "path": ["rows", 0, "owner_email"]},
                "action": "replace",
                "entity_id": "ent-syn-maya",
                "replacement_ref": "attr-syn-email-a12",
            }
        )


def test_replace_and_inert_patch_constraints() -> None:
    base = {
        "opaque_id": "patch-syn-bad",
        "mapping_snapshot_id": "map-syn-demo-1",
        "artifact_version_id": "art-syn-crm-1",
        "part_id": "part-syn-row-0-owner",
        "locator": FieldPathLocator(path=("rows", 0, "owner_email")),
    }
    with pytest.raises(DomainValidationError, match="replace patches require entity_id"):
        validate_patch_plan_entry(
            PatchPlanEntry(
                **base,
                action=PolicyAction.REPLACE,
                replacement_ref="attr-syn-email-a12",
            )
        )
    with pytest.raises(DomainValidationError, match="inert patches require replacement_ref"):
        validate_patch_plan_entry(
            PatchPlanEntry(
                **base,
                action=PolicyAction.INERT,
            )
        )
    with pytest.raises(DomainValidationError, match="remove patches must not set replacement_ref"):
        validate_patch_plan_entry(
            PatchPlanEntry(
                **base,
                action=PolicyAction.REMOVE,
                replacement_ref="attr-syn-email-a12",
            )
        )


def test_duplicate_assignments_rejected() -> None:
    with pytest.raises(DomainValidationError, match="duplicate entity assignment"):
        validate_mapping_snapshot(
            MappingSnapshot(
                opaque_id="map-syn-dup",
                snapshot_version="map.v1",
                namespace_id="ns-syn-demo",
                entity_graph_version_id="egv-syn-demo-1",
                policy_version="policy.content.v2",
                namespace_key_ref=_key_ref(),
                assignments=(
                    MappingAssignment(entity_id="ent-syn-maya", profile_id="prof-syn-a12"),
                    MappingAssignment(entity_id="ent-syn-maya", profile_id="prof-syn-a99"),
                ),
            )
        )


def test_records_are_immutable() -> None:
    snapshot = _snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.snapshot_version = "mutated"  # type: ignore[misc]


def test_identity_package_reexports_mapping_types() -> None:
    assert IdentityPolicyAction is PolicyAction
    assert IdentityMappingSnapshot is MappingSnapshot


def test_round_trip_from_committed_synthetic_fixture() -> None:
    bundle = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8").lower()

    # Fixtures must not embed secrets or source-to-synthetic value maps.
    forbidden_tokens = (
        "secret",
        "private_key",
        "api_key",
        "password",
        "-----begin",
        "@acme.example",
        "maya@",
    )
    for token in forbidden_tokens:
        assert token not in fixture_text

    key_ref = NamespaceKeyRef.from_dict(bundle["namespace_key_ref"])
    graph = EntityGraphVersion.from_dict(bundle["entity_graph_version"])
    snapshot = MappingSnapshot.from_dict(bundle["mapping_snapshot"])
    entries = [PatchPlanEntry.from_dict(item) for item in bundle["patch_plan_entries"]]

    validate_entity_graph_version(graph)
    validate_mapping_snapshot(snapshot)
    for entry in entries:
        validate_patch_plan_entry(entry)

    assert to_jsonable(key_ref) == bundle["namespace_key_ref"]
    assert to_jsonable(graph) == bundle["entity_graph_version"]
    assert to_jsonable(snapshot) == bundle["mapping_snapshot"]
    assert [to_jsonable(entry) for entry in entries] == bundle["patch_plan_entries"]
    assert {entry.action for entry in entries} == set(PolicyAction)
