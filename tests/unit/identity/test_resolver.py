"""Behavioral unit tests for strong-anchor identity resolution."""

from __future__ import annotations

import ast
from pathlib import Path

from cloakmill.domain import AnchorKind, DecisionOutcome, EntityKind
from cloakmill.identity import (
    DirectoryAnchor,
    MentionEvidence,
    StrongAnchorIdentityResolver,
)

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


def test_same_email_merges_into_one_person() -> None:
    resolver = StrongAnchorIdentityResolver()
    result = resolver.resolve(
        [
            _mention("obs-1", "email_address", "maya@acme.example", first_name="Maya"),
            _mention(
                "obs-2",
                "email_address",
                "Maya@Acme.Example",
                part_id="part-2",
                first_name="Maya",
            ),
        ],
        namespace_id="ns-demo",
    )
    assert len(result.graph.entities) == 1
    entity = result.graph.entities[0]
    assert entity.entity_kind is EntityKind.PERSON
    assert set(entity.observation_ids) == {"obs-1", "obs-2"}
    assert any(d.outcome is DecisionOutcome.ACCEPT for d in result.decisions)
    assert result.metrics.wrong_merge_rate is None


def test_same_employee_id_merges() -> None:
    resolver = StrongAnchorIdentityResolver()
    result = resolver.resolve(
        [
            _mention("obs-a", "employee_id", "E-AB12CD"),
            _mention("obs-b", "employee_id", "e-ab12cd", part_id="part-2"),
        ],
        namespace_id="ns-demo",
    )
    assert len(result.graph.entities) == 1
    assert set(result.graph.entities[0].observation_ids) == {"obs-a", "obs-b"}


def test_colocated_email_and_employee_id_bind() -> None:
    resolver = StrongAnchorIdentityResolver()
    result = resolver.resolve(
        [
            _mention("obs-email", "email_address", "maya@acme.example", part_id="row-1"),
            _mention("obs-emp", "employee_id", "E-AB12CD", part_id="row-1"),
        ],
        namespace_id="ns-demo",
    )
    assert len(result.graph.entities) == 1
    assert set(result.graph.entities[0].observation_ids) == {"obs-email", "obs-emp"}


def test_ambiguous_first_name_does_not_merge_distinct_emails() -> None:
    resolver = StrongAnchorIdentityResolver()
    result = resolver.resolve(
        [
            _mention("obs-1", "email_address", "maya.shah@acme.example", first_name="Maya"),
            _mention(
                "obs-2",
                "email_address",
                "maya.chen@acme.example",
                part_id="part-2",
                first_name="Maya",
            ),
        ],
        namespace_id="ns-demo",
    )
    assert len(result.graph.entities) == 2
    assert not any(
        set(entity.observation_ids) == {"obs-1", "obs-2"} for entity in result.graph.entities
    )
    assert any(group.reason_code == "ambiguous_first_name_only" for group in result.exceptions)
    assert result.requires_exception_review


def test_shared_mailbox_not_merged_into_operators() -> None:
    resolver = StrongAnchorIdentityResolver()
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
    result = resolver.resolve(
        [
            _mention("obs-shared", "email_address", "helpdesk@acme.example"),
            _mention("obs-maya", "email_address", "maya@acme.example", part_id="part-2"),
            _mention("obs-jordan", "email_address", "jordan@acme.example", part_id="part-3"),
            _mention("obs-emp", "employee_id", "E-AB12CD", part_id="part-2"),
        ],
        namespace_id="ns-demo",
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
    resolver = StrongAnchorIdentityResolver()
    result = resolver.resolve(
        [
            _mention("obs-person", "email_address", "maya@acme.example"),
            _mention("obs-account", "account_id", "AC-104", part_id="part-2"),
        ],
        namespace_id="ns-demo",
    )
    kinds = {entity.entity_kind for entity in result.graph.entities}
    assert kinds == {EntityKind.PERSON, EntityKind.ACCOUNT}
    assert any(d.reason_code == "entity_kind_mismatch" for d in result.decisions)


def test_conflicting_employee_ids_preserve_contradiction() -> None:
    resolver = StrongAnchorIdentityResolver()
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
    result = resolver.resolve(
        [
            _mention("obs-email", "email_address", "shared.alias@acme.example"),
            _mention("obs-e1", "employee_id", "E-111111", part_id="part-2"),
            _mention("obs-e2", "employee_id", "E-222222", part_id="part-3"),
        ],
        namespace_id="ns-demo",
        directory=directory,
    )
    assert result.contradictions
    assert any(c.reason_code == "conflicting_employee_id" for c in result.contradictions)
    # Must not place both employee ids on one accepted entity.
    for entity in result.graph.entities:
        assert not {"obs-e1", "obs-e2"} <= set(entity.observation_ids)


def test_payment_card_without_strong_identity_goes_to_review() -> None:
    resolver = StrongAnchorIdentityResolver()
    result = resolver.resolve(
        [_mention("obs-card", "payment_card", "4111111111111111")],
        namespace_id="ns-demo",
    )
    assert result.graph.entities == ()
    assert len(result.exceptions) == 1
    assert result.exceptions[0].reason_code == "no_strong_anchor"


def test_identity_package_does_not_load_held_out_eval_fixtures() -> None:
    for path in IDENTITY_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for fragment in FORBIDDEN_EVAL_PATH_FRAGMENTS:
                    assert fragment not in node.value.replace("\\", "/")
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "fixtures.eval" not in node.module
