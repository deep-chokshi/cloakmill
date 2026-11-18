"""Acceptance tests for F06 strong-anchor resolution against synthetic held-out links."""

from __future__ import annotations

import json
from math import inf
from pathlib import Path

from cloakmill.domain import AnchorKind, EntityKind
from cloakmill.identity import (
    AcceptedEntity,
    AcceptedEntityGraph,
    DirectoryAnchor,
    MentionEvidence,
    StrongAnchorIdentityResolver,
    score_wrong_merges,
)
from cloakmill.identity.metrics import build_resolution_metrics

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_resolution_cases.json"
TEST_NAMESPACE_SECRET = b"cloakmill-accept-ns-secret"


def _load_cases() -> list[dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["kind"] == "synthetic-identity-acceptance"
    return list(payload["cases"])


def _mention(raw: dict) -> MentionEvidence:
    return MentionEvidence(
        observation_id=raw["observation_id"],
        entity_type=raw["entity_type"],
        normalized_value=raw["normalized_value"],
        part_id=raw["part_id"],
        artifact_version_id=raw["artifact_version_id"],
        first_name=raw.get("first_name"),
        display_name=raw.get("display_name"),
    )


def _directory(raw: dict) -> DirectoryAnchor:
    return DirectoryAnchor(
        anchor_kind=AnchorKind(raw["anchor_kind"]),
        normalized_value=raw["normalized_value"],
        entity_kind=EntityKind(raw["entity_kind"]),
        entity_key=raw["entity_key"],
        is_shared=bool(raw.get("is_shared", False)),
        operator_person_keys=tuple(raw.get("operator_person_keys", [])),
    )


def test_synthetic_resolution_cases_report_zero_wrong_merges() -> None:
    resolver = StrongAnchorIdentityResolver()
    namespace_id = json.loads(FIXTURE.read_text(encoding="utf-8"))["namespace_id"]

    for case in _load_cases():
        mentions = tuple(_mention(item) for item in case["mentions"])
        directory = tuple(_directory(item) for item in case["directory"])
        expected_links = case["expected_links"]
        result = resolver.resolve(
            mentions,
            namespace_id=namespace_id,
            namespace_secret=TEST_NAMESPACE_SECRET,
            graph_version="accept-1",
            directory=directory,
            expected_links=expected_links,
        )
        expectations = case["assert"]
        assert len(result.graph.entities) == expectations["entity_count"], case["case_id"]
        assert result.metrics.wrong_merge_count == 0, (
            case["case_id"],
            result.metrics.to_dict(),
        )
        assert result.metrics.wrong_merge_rate is not None, case["case_id"]
        assert result.metrics.wrong_merge_rate <= expectations["max_wrong_merge_rate"], (
            case["case_id"],
            result.metrics.to_dict(),
        )
        assert result.requires_exception_review is expectations["require_review"], case["case_id"]

        serialized = json.dumps(result.graph.to_dict())
        for mention in mentions:
            assert mention.normalized_value not in serialized, case["case_id"]
        for group in result.exceptions:
            assert "first_name:" not in json.dumps(group.to_dict())

        if "exception_reason" in expectations:
            assert any(
                group.reason_code == expectations["exception_reason"] for group in result.exceptions
            ), case["case_id"]

        if "shared_account_obs" in expectations:
            shared_obs = expectations["shared_account_obs"]
            shared_entity = next(
                entity for entity in result.graph.entities if shared_obs in entity.observation_ids
            )
            assert shared_entity.entity_kind is EntityKind.ACCOUNT, case["case_id"]
            for entity in result.graph.entities:
                if entity.opaque_id == shared_entity.opaque_id:
                    continue
                assert shared_obs not in entity.observation_ids
                assert entity.entity_kind is EntityKind.PERSON


def test_score_wrong_merges_detects_forced_error_and_inf_rate() -> None:
    """Bad merge with zero expected accept pairs reports inf rate, not 0.0."""
    graph = AcceptedEntityGraph(
        opaque_id="graph-bad",
        graph_version="1",
        namespace_id="ns-demo",
        entities=(
            AcceptedEntity(
                opaque_id="ent-bad",
                entity_kind=EntityKind.PERSON,
                observation_ids=("obs_a", "obs_b"),
                strong_anchors=(),
            ),
        ),
    )
    expected = [
        {"expected_decision": "accept", "observation_ids": ["obs_a"]},
        {"expected_decision": "accept", "observation_ids": ["obs_b"]},
    ]
    wrong, expected_pairs = score_wrong_merges(graph, expected)
    assert wrong == 1
    assert expected_pairs == 0
    metrics = build_resolution_metrics(
        graph=graph,
        decisions=(),
        exceptions=(),
        total_mentions=2,
        expected_links=expected,
    )
    assert metrics.wrong_merge_count == 1
    assert metrics.wrong_merge_rate == inf


def test_correct_merge_not_penalized_by_shared_abstain_review_ids() -> None:
    """Accept pair A+A2 must not count wrong just because A also appears in abstain_review."""
    graph = AcceptedEntityGraph(
        opaque_id="graph-ok",
        graph_version="1",
        namespace_id="ns-demo",
        entities=(
            AcceptedEntity(
                opaque_id="ent-a",
                entity_kind=EntityKind.PERSON,
                observation_ids=("obs_a", "obs_a2"),
                strong_anchors=(),
            ),
            AcceptedEntity(
                opaque_id="ent-b",
                entity_kind=EntityKind.PERSON,
                observation_ids=("obs_b",),
                strong_anchors=(),
            ),
        ),
    )
    expected = [
        {
            "expected_decision": "accept",
            "observation_ids": ["obs_a", "obs_a2"],
        },
        {
            "expected_decision": "accept",
            "observation_ids": ["obs_b"],
        },
        {
            "expected_decision": "abstain_review",
            "observation_ids": ["obs_a", "obs_b"],
        },
    ]
    wrong, expected_pairs = score_wrong_merges(graph, expected)
    assert wrong == 0
    assert expected_pairs == 1
