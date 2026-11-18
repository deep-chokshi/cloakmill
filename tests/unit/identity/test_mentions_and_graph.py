"""Unit tests for mention validation and accepted entity graph contracts."""

from __future__ import annotations

import pytest

from cloakmill.domain import AnchorKind, DomainValidationError, EntityKind
from cloakmill.identity import (
    AcceptedEntity,
    AcceptedEntityGraph,
    DirectoryAnchor,
    MentionEvidence,
    StrongAnchor,
    accepted_entity_graphs_equal,
    normalize_anchor_value,
    validate_directory_anchor,
    validate_mention_evidence,
)


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


def test_accepted_entity_graph_round_trip_and_equality() -> None:
    entity = AcceptedEntity(
        opaque_id="ent-person-1",
        entity_kind=EntityKind.PERSON,
        observation_ids=("obs-a", "obs-b"),
        strong_anchors=(StrongAnchor(kind=AnchorKind.EMAIL, normalized_value="maya@acme.example"),),
        directory_entity_key="person-maya",
    )
    graph = AcceptedEntityGraph(
        opaque_id="graph-1",
        graph_version="1",
        namespace_id="ns-demo",
        entities=(entity,),
    )
    restored = AcceptedEntityGraph.from_dict(graph.to_dict())
    assert accepted_entity_graphs_equal(graph, restored)
    assert restored.entity_ids == ("ent-person-1",)

    with pytest.raises(DomainValidationError):
        AcceptedEntity.from_dict(
            {
                "opaque_id": "ent-dup",
                "entity_kind": "person",
                "observation_ids": ["obs-a", "obs-a"],
                "strong_anchors": [],
            }
        )
