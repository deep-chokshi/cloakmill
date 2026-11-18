"""Typed observations and opaque evidence references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_non_empty_str, require_opaque_id
from cloakmill.domain.locators import (
    OriginalLocator,
    TextOffsetLocator,
    locator_from_dict,
    validate_locator,
)


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Opaque pointer to supporting evidence without embedding source snippets."""

    opaque_id: str
    part_id: str
    locator: OriginalLocator
    recognizer_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "part_id": self.part_id,
            "locator": self.locator.to_dict(),
        }
        if self.recognizer_version is not None:
            payload["recognizer_version"] = self.recognizer_version
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRef:
        if not isinstance(data, dict):
            raise DomainValidationError("evidence ref must be an object")
        try:
            locator = locator_from_dict(data["locator"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid evidence ref locator: {exc}") from exc
        ref = cls(
            opaque_id=str(data.get("opaque_id", "")),
            part_id=str(data.get("part_id", "")),
            locator=locator,
            recognizer_version=data.get("recognizer_version"),
        )
        validate_evidence_ref(ref)
        return ref


@dataclass(frozen=True, slots=True)
class Observation:
    """Detector proposal tied to exact evidence; not an accepted identity decision."""

    opaque_id: str
    part_id: str
    artifact_version_id: str
    entity_type: str
    evidence_locator: OriginalLocator
    recognizer_version: str
    score_kind: ScoreKind
    score_value: float | None = None
    proposal_snapshot_ref: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "part_id": self.part_id,
            "artifact_version_id": self.artifact_version_id,
            "entity_type": self.entity_type,
            "evidence_locator": self.evidence_locator.to_dict(),
            "recognizer_version": self.recognizer_version,
            "score_kind": self.score_kind.value,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
        }
        if self.score_value is not None:
            payload["score_value"] = self.score_value
        if self.proposal_snapshot_ref is not None:
            payload["proposal_snapshot_ref"] = self.proposal_snapshot_ref
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        if not isinstance(data, dict):
            raise DomainValidationError("observation must be an object")
        try:
            score_kind = ScoreKind(data["score_kind"])
            evidence_locator = locator_from_dict(data["evidence_locator"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid observation fields: {exc}") from exc

        raw_refs = data.get("evidence_refs", [])
        if not isinstance(raw_refs, list):
            raise DomainValidationError("evidence_refs must be a list")
        evidence_refs = tuple(EvidenceRef.from_dict(item) for item in raw_refs)

        score_value = data.get("score_value")
        if score_value is not None and (
            isinstance(score_value, bool) or not isinstance(score_value, int | float)
        ):
            raise DomainValidationError("score_value must be a number when present")

        observation = cls(
            opaque_id=str(data.get("opaque_id", "")),
            part_id=str(data.get("part_id", "")),
            artifact_version_id=str(data.get("artifact_version_id", "")),
            entity_type=str(data.get("entity_type", "")),
            evidence_locator=evidence_locator,
            recognizer_version=str(data.get("recognizer_version", "")),
            score_kind=score_kind,
            score_value=None if score_value is None else float(score_value),
            proposal_snapshot_ref=data.get("proposal_snapshot_ref"),
            evidence_refs=evidence_refs,
        )
        validate_observation(observation)
        return observation


def validate_evidence_ref(
    ref: EvidenceRef,
    *,
    part: Part | None = None,
) -> None:
    require_opaque_id(ref.opaque_id, "opaque_id")
    require_opaque_id(ref.part_id, "part_id")
    if ref.recognizer_version is not None:
        require_non_empty_str(ref.recognizer_version, "recognizer_version")
    content_length = None
    if part is not None:
        if ref.part_id != part.opaque_id:
            raise DomainValidationError(
                f"evidence ref part_id {ref.part_id!r} does not match part {part.opaque_id!r}"
            )
        if isinstance(ref.locator, TextOffsetLocator):
            content_length = part.content_length
    validate_locator(ref.locator, content_length=content_length)


def validate_observation(
    observation: Observation,
    *,
    part: Part | None = None,
) -> None:
    require_opaque_id(observation.opaque_id, "opaque_id")
    require_opaque_id(observation.part_id, "part_id")
    require_opaque_id(observation.artifact_version_id, "artifact_version_id")
    require_non_empty_str(observation.entity_type, "entity_type")
    require_non_empty_str(observation.recognizer_version, "recognizer_version")
    if not isinstance(observation.score_kind, ScoreKind):
        raise DomainValidationError("score_kind must be a ScoreKind")
    if observation.score_value is not None:
        if isinstance(observation.score_value, bool) or not isinstance(
            observation.score_value, int | float
        ):
            raise DomainValidationError("score_value must be a number when present")
        if not (0.0 <= float(observation.score_value) <= 1.0):
            raise DomainValidationError("score_value must be within [0.0, 1.0] when present")
    if observation.proposal_snapshot_ref is not None:
        require_opaque_id(observation.proposal_snapshot_ref, "proposal_snapshot_ref")

    content_length = None
    if part is not None:
        if observation.part_id != part.opaque_id:
            raise DomainValidationError(
                f"observation part_id {observation.part_id!r} "
                f"does not match part {part.opaque_id!r}"
            )
        if observation.artifact_version_id != part.artifact_version_id:
            raise DomainValidationError(
                "observation artifact_version_id does not match part.artifact_version_id"
            )
        if isinstance(observation.evidence_locator, TextOffsetLocator):
            content_length = part.content_length

    validate_locator(observation.evidence_locator, content_length=content_length)
    for ref in observation.evidence_refs:
        validate_evidence_ref(ref, part=part if ref.part_id == observation.part_id else None)
