"""Provisional F01-aligned shapes for held-out eval expectations.

These mirror the planned domain contracts (artifact/version, part, locator,
observation, identity link) without importing or rewriting ``cloakmill.domain``.
When F01 lands, eval loaders can migrate onto the real types; fixture *files*
keep this schema_version until then.
"""

from __future__ import annotations

from typing import Any, Literal

SCHEMA_VERSION = "provisional-f01-v1"

EntityType = Literal[
    "person_name",
    "email_address",
    "employee_id",
    "account_id",
    "organization_name",
    "shared_mailbox",
]

LocatorKind = Literal["text_offset", "field_path"]
CoverageState = Literal["complete", "partial", "unavailable", "excluded"]
ExpectedDecision = Literal["accept", "abstain_review", "keep_separate"]
EntityKind = Literal["person", "account", "organization", "mailbox"]


def field_path_locator(field_path: str) -> dict[str, Any]:
    return {"kind": "field_path", "field_path": field_path}


def text_offset_locator(*, start: int, end: int, unit: str = "codepoint") -> dict[str, Any]:
    if start < 0 or end < start:
        msg = f"invalid text offset bounds: start={start} end={end}"
        raise ValueError(msg)
    return {"kind": "text_offset", "unit": unit, "start": start, "end": end}


def make_observation(
    *,
    observation_id: str,
    artifact_opaque_id: str,
    source_version: str,
    relative_path: str,
    part_id: str,
    surface_kind: str,
    coverage_state: CoverageState,
    entity_type: EntityType,
    evidence_locator: dict[str, Any],
    evidence_text: str,
    underlying_entity_ref: str,
    case_tags: tuple[str, ...] = (),
    recognizer_version: str,
) -> dict[str, Any]:
    """Build one held-out observation dict aligned with planned F01 fields."""
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_id": observation_id,
        "artifact": {
            "opaque_id": artifact_opaque_id,
            "source_version": source_version,
            "relative_path": relative_path,
        },
        "part": {
            "part_id": part_id,
            "surface_kind": surface_kind,
            "coverage_state": coverage_state,
        },
        "entity_type": entity_type,
        "evidence_locator": evidence_locator,
        "evidence_text": evidence_text,
        "score_kind": "seeded_ground_truth",
        "recognizer_version": recognizer_version,
        "underlying_entity_ref": underlying_entity_ref,
        "case_tags": list(case_tags),
    }


def make_identity_link(
    *,
    link_id: str,
    entity_id: str,
    entity_kind: EntityKind,
    observation_ids: list[str],
    expected_decision: ExpectedDecision,
    case_tags: tuple[str, ...] = (),
    ownership_period: dict[str, Any] | None = None,
    related_entity_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "link_id": link_id,
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "observation_ids": list(observation_ids),
        "expected_decision": expected_decision,
        "case_tags": list(case_tags),
        "related_entity_ids": list(related_entity_ids),
    }
    if ownership_period is not None:
        payload["ownership_period"] = ownership_period
    return payload


def validate_observation(obs: dict[str, Any]) -> None:
    required = (
        "schema_version",
        "observation_id",
        "artifact",
        "part",
        "entity_type",
        "evidence_locator",
        "evidence_text",
        "score_kind",
        "recognizer_version",
        "underlying_entity_ref",
    )
    for key in required:
        if key not in obs:
            msg = f"observation missing {key}"
            raise ValueError(msg)
    locator = obs["evidence_locator"]
    kind = locator.get("kind")
    if kind == "text_offset":
        start = locator["start"]
        end = locator["end"]
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
            msg = f"invalid text_offset locator: {locator}"
            raise ValueError(msg)
    elif kind == "field_path":
        if not locator.get("field_path"):
            msg = "field_path locator requires field_path"
            raise ValueError(msg)
    else:
        msg = f"unknown locator kind: {kind}"
        raise ValueError(msg)


def validate_identity_link(link: dict[str, Any]) -> None:
    required = (
        "schema_version",
        "link_id",
        "entity_id",
        "entity_kind",
        "observation_ids",
        "expected_decision",
    )
    for key in required:
        if key not in link:
            msg = f"identity link missing {key}"
            raise ValueError(msg)
    if not isinstance(link["observation_ids"], list):
        msg = "observation_ids must be a list"
        raise ValueError(msg)
