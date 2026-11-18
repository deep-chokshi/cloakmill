"""Behavioral unit tests for strong-anchor identity resolution."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from cloakmill.domain import AnchorKind, DecisionOutcome, DomainValidationError, EntityKind
from cloakmill.identity import (
    DirectoryAnchor,
    MentionEvidence,
    StrongAnchorIdentityResolver,
    entity_opaque_id,
    require_namespace_secret,
)

TEST_NAMESPACE_SECRET = b"cloakmill-test-ns-secret-01"

IDENTITY_ROOT = Path(__file__).resolve().parents[3] / "src" / "cloakmill" / "identity"
FORBIDDEN_EVAL_PATH_FRAGMENTS = ("tests/fixtures/eval", "fixtures/eval")


def _mention(
    obs_id: str,
    entity_type: str,
    value: str,
    *,
    part_id: str = "part-1",
    first_name: str | None = None,
) -> MentionEvidence:
    return MentionEvidence(
        observation_id=obs_id,
        entity_type=entity_type,
        normalized_value=value,
        part_id=part_id,
        artifact_version_id="art-1",
        first_name=first_name,
    )


def _resolve(mentions, *, directory=(), expected_links=None, namespace_id="ns-demo"):
    return StrongAnchorIdentityResolver().resolve(
        mentions,
        namespace_id=namespace_id,
        namespace_secret=TEST_NAMESPACE_SECRET,
        directory=directory,
        expected_links=expected_links,
    )


def test_same_email_merges_into_one_person() -> None:
    result = _resolve(
        [
            _mention("obs-1", "email_address", "maya@acme.example", first_name="Maya"),
            _mention(
                "obs-2",
                "email_address",
                "Maya@Acme.Example",
                part_id="part-2",
                first_name="Maya",
            ),
        ]
    )
    assert len(result.graph.entities) == 1
    entity = result.graph.entities[0]
    assert entity.entity_kind is EntityKind.PERSON
    assert set(entity.observation_ids) == {"obs-1", "obs-2"}
    assert any(d.outcome is DecisionOutcome.ACCEPT for d in result.decisions)
    assert result.metrics.wrong_merge_rate is None
    serialized = json.dumps(result.graph.to_dict())
    assert "maya@acme.example" not in serialized
    assert result.private_anchor_index.get(entity.strong_anchors[0].opaque_ref) == (
        "maya@acme.example"
    )


def test_same_employee_id_merges() -> None:
    result = _resolve(
        [
            _mention("obs-a", "employee_id", "E-AB12CD"),
            _mention("obs-b", "employee_id", "e-ab12cd", part_id="part-2"),
        ]
    )
    assert len(result.graph.entities) == 1
    assert set(result.graph.entities[0].observation_ids) == {"obs-a", "obs-b"}


def test_colocated_email_and_employee_id_bind() -> None:
    result = _resolve(
        [
            _mention("obs-email", "email_address", "maya@acme.example", part_id="row-1"),
            _mention("obs-emp", "employee_id", "E-AB12CD", part_id="row-1"),
        ]
    )
    assert len(result.graph.entities) == 1
    assert set(result.graph.entities[0].observation_ids) == {"obs-email", "obs-emp"}


def test_ambiguous_first_name_does_not_merge_distinct_emails() -> None:
    result = _resolve(
        [
            _mention("obs-1", "email_address", "maya.shah@acme.example", first_name="Maya"),
            _mention(
                "obs-2",
                "email_address",
                "maya.chen@acme.example",
                part_id="part-2",
                first_name="Maya",
            ),
        ]
    )
    assert len(result.graph.entities) == 2
    assert not any(
        set(entity.observation_ids) == {"obs-1", "obs-2"} for entity in result.graph.entities
    )
    assert any(group.reason_code == "ambiguous_first_name_only" for group in result.exceptions)
    assert result.requires_exception_review
    for group in result.exceptions:
        blob = json.dumps(group.to_dict())
        assert "first_name:maya" not in blob
        assert all(ref.startswith("wref-") for ref in group.weak_signal_refs)


def test_shared_mailbox_not_merged_into_operators() -> None:
    directory = (
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMAIL,
            normalized_value="helpdesk@acme.example",
            entity_kind=EntityKind.ACCOUNT,
            entity_key="acct-helpdesk",
            is_shared=True,
            operator_person_keys=("person-maya", "person-jordan"),
        ),
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMAIL,
            normalized_value="maya@acme.example",
            entity_kind=EntityKind.PERSON,
            entity_key="person-maya",
        ),
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMAIL,
            normalized_value="jordan@acme.example",
            entity_kind=EntityKind.PERSON,
            entity_key="person-jordan",
        ),
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMPLOYEE_ID,
            normalized_value="E-AB12CD",
            entity_kind=EntityKind.PERSON,
            entity_key="person-maya",
        ),
    )
    result = _resolve(
        [
            _mention("obs-shared", "email_address", "helpdesk@acme.example"),
            _mention("obs-maya", "email_address", "maya@acme.example", part_id="part-2"),
            _mention("obs-jordan", "email_address", "jordan@acme.example", part_id="part-3"),
            _mention("obs-emp", "employee_id", "E-AB12CD", part_id="part-2"),
        ],
        directory=directory,
    )
    by_obs = {
        obs_id: entity for entity in result.graph.entities for obs_id in entity.observation_ids
    }
    assert by_obs["obs-shared"].entity_kind is EntityKind.ACCOUNT
    assert by_obs["obs-maya"].entity_kind is EntityKind.PERSON
    assert by_obs["obs-jordan"].entity_kind is EntityKind.PERSON
    assert by_obs["obs-shared"].opaque_id != by_obs["obs-maya"].opaque_id
    assert by_obs["obs-maya"].opaque_id != by_obs["obs-jordan"].opaque_id
    assert by_obs["obs-maya"].opaque_id == by_obs["obs-emp"].opaque_id
    assert any(d.reason_code == "shared_mailbox_not_person_alias" for d in result.decisions)


def test_person_and_account_remain_distinct() -> None:
    result = _resolve(
        [
            _mention("obs-person", "email_address", "maya@acme.example"),
            _mention("obs-account", "account_id", "AC-104", part_id="part-2"),
        ]
    )
    kinds = {entity.entity_kind for entity in result.graph.entities}
    assert kinds == {EntityKind.PERSON, EntityKind.ACCOUNT}
    assert any(d.reason_code == "entity_kind_mismatch" for d in result.decisions)


def test_conflicting_employee_ids_preserve_contradiction() -> None:
    directory = (
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMAIL,
            normalized_value="shared.alias@acme.example",
            entity_kind=EntityKind.PERSON,
            entity_key="person-bad-merge",
        ),
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMPLOYEE_ID,
            normalized_value="E-111111",
            entity_kind=EntityKind.PERSON,
            entity_key="person-bad-merge",
        ),
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMPLOYEE_ID,
            normalized_value="E-222222",
            entity_kind=EntityKind.PERSON,
            entity_key="person-bad-merge",
        ),
    )
    result = _resolve(
        [
            _mention("obs-email", "email_address", "shared.alias@acme.example"),
            _mention("obs-e1", "employee_id", "E-111111", part_id="part-2"),
            _mention("obs-e2", "employee_id", "E-222222", part_id="part-3"),
        ],
        directory=directory,
    )
    assert result.contradictions
    assert any(c.reason_code == "conflicting_employee_id" for c in result.contradictions)
    for entity in result.graph.entities:
        assert not {"obs-e1", "obs-e2"} <= set(entity.observation_ids)


def test_payment_card_without_strong_identity_goes_to_review() -> None:
    result = _resolve([_mention("obs-card", "payment_card", "4111111111111111")])
    assert result.graph.entities == ()
    assert len(result.exceptions) == 1
    assert result.exceptions[0].reason_code == "no_strong_anchor"


def test_weak_only_does_not_leak_into_accepted_graph_with_email_merges() -> None:
    """Regression: payment_card must not become a PERSON singleton via UnionFind find()."""
    result = _resolve(
        [
            _mention("obs-1", "email_address", "maya@acme.example"),
            _mention("obs-2", "email_address", "Maya@Acme.Example", part_id="part-2"),
            _mention("obs-card", "payment_card", "4111111111111111", part_id="part-3"),
        ]
    )
    assert len(result.graph.entities) == 1
    entity = result.graph.entities[0]
    assert set(entity.observation_ids) == {"obs-1", "obs-2"}
    assert "obs-card" not in entity.observation_ids
    card_decisions = [d for d in result.decisions if "obs-card" in d.observation_ids]
    assert card_decisions
    assert all(d.outcome is DecisionOutcome.REVIEW for d in card_decisions)
    assert not any(
        d.outcome is DecisionOutcome.ACCEPT and "obs-card" in d.observation_ids
        for d in result.decisions
    )


def test_entity_opaque_id_is_keyed_hmac_not_unkeyed_sha256() -> None:
    email = "maya@acme.example"
    keyed = entity_opaque_id(
        entity_kind=EntityKind.PERSON,
        seed_anchor_kind=AnchorKind.EMAIL,
        seed_value=email,
        namespace_id="ns-demo",
        namespace_secret=TEST_NAMESPACE_SECRET,
    )
    unkeyed = hashlib.sha256(
        "\0".join(["ns-demo", "person", "email", email]).encode("utf-8")
    ).hexdigest()[:24]
    assert unkeyed not in keyed
    other = entity_opaque_id(
        entity_kind=EntityKind.PERSON,
        seed_anchor_kind=AnchorKind.EMAIL,
        seed_value=email,
        namespace_id="ns-demo",
        namespace_secret=b"different-secret-xx",
    )
    assert keyed != other
    with pytest.raises(DomainValidationError):
        require_namespace_secret(b"short")


def test_directory_conflict_message_omits_cleartext_value() -> None:
    directory = (
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMAIL,
            normalized_value="maya@acme.example",
            entity_kind=EntityKind.PERSON,
            entity_key="person-a",
        ),
        DirectoryAnchor(
            anchor_kind=AnchorKind.EMAIL,
            normalized_value="maya@acme.example",
            entity_kind=EntityKind.PERSON,
            entity_key="person-b",
        ),
    )
    with pytest.raises(DomainValidationError) as exc_info:
        _resolve(
            [_mention("obs-1", "email_address", "maya@acme.example")],
            directory=directory,
        )
    message = str(exc_info.value)
    assert "maya@acme.example" not in message
    assert "email" in message
    assert "person-a" in message and "person-b" in message


def test_identity_package_does_not_load_held_out_eval_fixtures() -> None:
    for path in IDENTITY_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for fragment in FORBIDDEN_EVAL_PATH_FRAGMENTS:
                    assert fragment not in node.value.replace("\\", "/")
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "fixtures.eval" not in node.module
