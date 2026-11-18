"""Unit tests for mention validation and accepted entity graph contracts."""

from __future__ import annotations

import json

import pytest

from cloakmill.domain import AnchorKind, DomainValidationError, EntityKind
from cloakmill.identity import (
    AcceptedEntity,
    AcceptedEntityGraph,
    DirectoryAnchor,
    MentionEvidence,
    PrivateAnchorIndex,
    StrongAnchor,
    accepted_entity_graphs_equal,
    normalize_anchor_value,
    opaque_anchor_ref,
    opaque_directory_entity_ref,
    validate_directory_anchor,
    validate_mention_evidence,
)

TEST_NAMESPACE_SECRET = b"cloakmill-test-ns-secret-01"
TEST_NAMESPACE_ID = "ns-demo"


def test_normalize_anchor_values() -> None:
    assert normalize_anchor_value(AnchorKind.EMAIL, " Maya@Acme.Example ") == "maya@acme.example"
    assert normalize_anchor_value(AnchorKind.EMPLOYEE_ID, "e-ab12cd") == "E-AB12CD"
    assert normalize_anchor_value(AnchorKind.ACCOUNT_ID, "ac-104") == "AC-104"
    assert normalize_anchor_value(AnchorKind.FIRST_NAME, "  Maya  ") == "maya"


def test_mention_and_directory_validation() -> None:
    mention = MentionEvidence(
        observation_id="obs-1",
        entity_type="email_address",
        normalized_value="maya@acme.example",
        part_id="part-1",
        artifact_version_id="art-1",
        first_name="Maya",
    )
    validate_mention_evidence(mention)
    assert mention.strong_anchor() == (AnchorKind.EMAIL, "maya@acme.example")

    shared = DirectoryAnchor(
        anchor_kind=AnchorKind.EMAIL,
        normalized_value="helpdesk@acme.example",
        entity_kind=EntityKind.ACCOUNT,
        entity_key="acct-helpdesk",
        is_shared=True,
        operator_person_keys=("person-maya", "person-jordan"),
    )
    validate_directory_anchor(shared)

    with pytest.raises(DomainValidationError):
        validate_directory_anchor(
            DirectoryAnchor(
                anchor_kind=AnchorKind.EMAIL,
                normalized_value="helpdesk@acme.example",
                entity_kind=EntityKind.PERSON,
                entity_key="bad",
                is_shared=True,
            )
        )

    with pytest.raises(DomainValidationError, match="duplicate operator_person_key") as exc_info:
        validate_directory_anchor(
            DirectoryAnchor(
                anchor_kind=AnchorKind.EMAIL,
                normalized_value="helpdesk@acme.example",
                entity_kind=EntityKind.ACCOUNT,
                entity_key="acct-helpdesk",
                is_shared=True,
                operator_person_keys=("person-maya", "person-maya"),
            )
        )
    assert "person-maya" not in str(exc_info.value)


def test_accepted_entity_graph_round_trip_uses_opaque_refs_only() -> None:
    opaque = opaque_anchor_ref(
        kind=AnchorKind.EMAIL,
        normalized_value="maya@acme.example",
        namespace_id=TEST_NAMESPACE_ID,
        namespace_secret=TEST_NAMESPACE_SECRET,
    )
    directory_ref = opaque_directory_entity_ref(
        entity_key="person-maya",
        namespace_id=TEST_NAMESPACE_ID,
        namespace_secret=TEST_NAMESPACE_SECRET,
    )
    entity = AcceptedEntity(
        opaque_id="ent-person-1",
        entity_kind=EntityKind.PERSON,
        observation_ids=("obs-a", "obs-b"),
        strong_anchors=(StrongAnchor(kind=AnchorKind.EMAIL, opaque_ref=opaque),),
        directory_entity_ref=directory_ref,
    )
    graph = AcceptedEntityGraph(
        opaque_id="graph-1",
        graph_version="1",
        namespace_id=TEST_NAMESPACE_ID,
        entities=(entity,),
    )
    payload = graph.to_dict()
    serialized = json.dumps(payload)
    assert "maya@acme.example" not in serialized
    assert "person-maya" not in serialized
    assert "directory_entity_key" not in serialized
    assert "normalized_value" not in serialized
    assert opaque in serialized
    assert directory_ref in serialized
    assert directory_ref.startswith("dref-")

    restored = AcceptedEntityGraph.from_dict(payload)
    assert accepted_entity_graphs_equal(graph, restored)
    assert restored.entity_ids == ("ent-person-1",)

    with pytest.raises(DomainValidationError, match="opaque_ref"):
        StrongAnchor.from_dict({"kind": "email", "normalized_value": "maya@acme.example"})

    with pytest.raises(DomainValidationError, match="directory_entity_ref"):
        AcceptedEntity.from_dict(
            {
                "opaque_id": "ent-legacy",
                "entity_kind": "person",
                "observation_ids": ["obs-a"],
                "strong_anchors": [],
                "directory_entity_key": "person-maya",
            }
        )

    with pytest.raises(DomainValidationError):
        AcceptedEntity.from_dict(
            {
                "opaque_id": "ent-dup",
                "entity_kind": "person",
                "observation_ids": ["obs-a", "obs-a"],
                "strong_anchors": [],
            }
        )


def test_private_anchor_index_repr_omits_cleartext() -> None:
    index = PrivateAnchorIndex(values={"aref-email-abc": "maya@acme.example"})
    rendered = repr(index)
    assert "maya@acme.example" not in rendered
    assert "entries=1" in rendered
    assert str(index) == rendered
    with pytest.raises(TypeError, match="cannot be pickled"):
        index.__reduce__()
