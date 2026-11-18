"""Validate candidate observations: bounds, evidence integrity, overlap policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.ids import evidence_opaque_id, observation_opaque_id
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.locators import FieldPathLocator, OriginalLocator, TextOffsetLocator
from cloakmill.domain.observations import EvidenceRef, Observation, validate_observation


class RejectionReason(StrEnum):
    """Why a candidate was rejected before acceptance."""

    INVALID_ENTITY_TYPE = "invalid_entity_type"
    INVALID_LOCATOR = "invalid_locator"
    EMPTY_SPAN = "empty_span"
    OUT_OF_BOUNDS = "out_of_bounds"
    PART_MISMATCH = "part_mismatch"
    DUPLICATE = "duplicate"
    OVERLAP_CONFLICT = "overlap_conflict"
    DOMAIN_INVALID = "domain_invalid"


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    candidate: CandidateObservation
    reason: RejectionReason
    detail: str


@dataclass(frozen=True, slots=True)
class ObservationConflict:
    """Explicit overlap/conflict between two candidates (no silent drop)."""

    left: CandidateObservation
    right: CandidateObservation
    reason: str
    leaves_uncovered_evidence: bool = False


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: tuple[Observation, ...]
    rejected: tuple[RejectedCandidate, ...]
    conflicts: tuple[ObservationConflict, ...]
    requires_exception_review: bool = False


class ObservationValidator:
    """Promote candidates to Observations or reject/conflict them explicitly.

    Overlapping text offsets on the same part are never silently discarded.
    Coverage-preserving policy: consider longer spans (then higher scores)
    first so a nested shorter match cannot preempt a containing sensitive
    span. Contained overlaps are rejected with ``OVERLAP_CONFLICT``. Partial
    overlaps that would leave residual uncovered evidence bytes set
    ``requires_exception_review`` so downstream release cannot treat the
    part as fully covered.
    """

    def validate(
        self,
        part: Part,
        candidates: tuple[CandidateObservation, ...] | list[CandidateObservation],
    ) -> ValidationResult:
        accepted: list[Observation] = []
        rejected: list[RejectedCandidate] = []
        conflicts: list[ObservationConflict] = []
        accepted_keys: set[tuple[str, str]] = set()
        accepted_spans: list[tuple[TextOffsetLocator, CandidateObservation]] = []
        requires_exception_review = False

        ordered = sorted(candidates, key=_candidate_sort_key)
        for candidate in ordered:
            outcome = self._validate_one(
                part,
                candidate,
                accepted_keys=accepted_keys,
                accepted_spans=accepted_spans,
            )
            if isinstance(outcome, Observation):
                accepted.append(outcome)
                accepted_keys.add(_dedupe_key(candidate))
                if isinstance(candidate.evidence_locator, TextOffsetLocator):
                    accepted_spans.append((candidate.evidence_locator, candidate))
                continue
            if isinstance(outcome, tuple):
                rejection, conflict = outcome
                rejected.append(rejection)
                if conflict is not None:
                    conflicts.append(conflict)
                    if conflict.leaves_uncovered_evidence:
                        requires_exception_review = True
                continue
            rejected.append(outcome)

        return ValidationResult(
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            conflicts=tuple(conflicts),
            requires_exception_review=requires_exception_review,
        )

    def _validate_one(
        self,
        part: Part,
        candidate: CandidateObservation,
        *,
        accepted_keys: set[tuple[str, str]],
        accepted_spans: list[tuple[TextOffsetLocator, CandidateObservation]],
    ) -> Observation | RejectedCandidate | tuple[RejectedCandidate, ObservationConflict | None]:
        if not isinstance(candidate.entity_type, str) or candidate.entity_type.strip() == "":
            return RejectedCandidate(
                candidate=candidate,
                reason=RejectionReason.INVALID_ENTITY_TYPE,
                detail="entity_type must be a non-empty string",
            )

        locator = candidate.evidence_locator
        empty = _empty_span(locator)
        if empty is not None:
            return RejectedCandidate(
                candidate=candidate,
                reason=RejectionReason.EMPTY_SPAN,
                detail=empty,
            )

        try:
            _check_locator_against_part(part, locator)
        except DomainValidationError as exc:
            reason = (
                RejectionReason.OUT_OF_BOUNDS
                if "exceeds content_length" in str(exc)
                else RejectionReason.INVALID_LOCATOR
            )
            return RejectedCandidate(candidate=candidate, reason=reason, detail=str(exc))

        key = _dedupe_key(candidate)
        if key in accepted_keys:
            return RejectedCandidate(
                candidate=candidate,
                reason=RejectionReason.DUPLICATE,
                detail="identical entity_type and evidence locator already accepted",
            )

        if isinstance(locator, TextOffsetLocator):
            for prior_locator, prior_candidate in accepted_spans:
                if not _text_offsets_overlap(prior_locator, locator):
                    continue
                uncovered = not _span_fully_covered(locator, accepted_spans)
                conflict = ObservationConflict(
                    left=prior_candidate,
                    right=candidate,
                    reason=(
                        "overlapping text evidence on the same part; "
                        "later (narrower/lower-precedence) candidate rejected explicitly"
                        + (
                            "; residual uncovered evidence requires exception review"
                            if uncovered
                            else ""
                        )
                    ),
                    leaves_uncovered_evidence=uncovered,
                )
                rejection = RejectedCandidate(
                    candidate=candidate,
                    reason=RejectionReason.OVERLAP_CONFLICT,
                    detail=conflict.reason,
                )
                return rejection, conflict

        observation = _to_observation(part, candidate)
        try:
            validate_observation(observation, part=part)
        except DomainValidationError as exc:
            return RejectedCandidate(
                candidate=candidate,
                reason=RejectionReason.DOMAIN_INVALID,
                detail=str(exc),
            )
        return observation


def _to_observation(part: Part, candidate: CandidateObservation) -> Observation:
    recognizer_version = candidate.recognizer_version
    opaque_id = observation_opaque_id(
        part_id=part.opaque_id,
        entity_type=candidate.entity_type,
        recognizer_version=recognizer_version,
        locator=candidate.evidence_locator,
    )
    evidence = EvidenceRef(
        opaque_id=evidence_opaque_id(
            part_id=part.opaque_id,
            recognizer_version=recognizer_version,
            locator=candidate.evidence_locator,
        ),
        part_id=part.opaque_id,
        locator=candidate.evidence_locator,
        recognizer_version=recognizer_version,
    )
    score_kind = candidate.score_kind
    if not isinstance(score_kind, ScoreKind):
        raise DomainValidationError("score_kind must be a ScoreKind")
    return Observation(
        opaque_id=opaque_id,
        part_id=part.opaque_id,
        artifact_version_id=part.artifact_version_id,
        entity_type=candidate.entity_type,
        evidence_locator=candidate.evidence_locator,
        recognizer_version=recognizer_version,
        score_kind=score_kind,
        score_value=candidate.score_value,
        evidence_refs=(evidence,),
    )


def _check_locator_against_part(part: Part, locator: OriginalLocator) -> None:
    from cloakmill.domain.locators import validate_locator

    if isinstance(locator, TextOffsetLocator):
        validate_locator(locator, content_length=part.content_length)
        return
    if isinstance(locator, FieldPathLocator):
        validate_locator(locator)
        if (
            isinstance(part.original_locator, FieldPathLocator)
            and locator.path != part.original_locator.path
        ):
            raise DomainValidationError(
                "field-path evidence must match the structured part original_locator"
            )
        return
    raise DomainValidationError(f"unsupported locator type: {type(locator).__name__}")


def _empty_span(locator: OriginalLocator) -> str | None:
    if isinstance(locator, TextOffsetLocator) and locator.start == locator.end:
        return "text offset span must be non-empty"
    return None


def _text_offsets_overlap(left: TextOffsetLocator, right: TextOffsetLocator) -> bool:
    if left.unit != right.unit:
        return False
    return left.start < right.end and right.start < left.end


def _span_fully_covered(
    locator: TextOffsetLocator,
    accepted_spans: list[tuple[TextOffsetLocator, CandidateObservation]],
) -> bool:
    """Return True when every offset in ``locator`` is inside some accepted span."""
    for offset in range(locator.start, locator.end):
        covered = False
        for accepted, _candidate in accepted_spans:
            if accepted.unit != locator.unit:
                continue
            if accepted.start <= offset < accepted.end:
                covered = True
                break
        if not covered:
            return False
    return True


def _dedupe_key(candidate: CandidateObservation) -> tuple[str, str]:
    return candidate.entity_type, _locator_fingerprint(candidate.evidence_locator)


def _locator_fingerprint(locator: OriginalLocator) -> str:
    if isinstance(locator, TextOffsetLocator):
        return f"to:{locator.unit.value}:{locator.start}:{locator.end}"
    if isinstance(locator, FieldPathLocator):
        return "fp:" + "/".join(str(s) for s in locator.path)
    return f"unknown:{type(locator).__name__}"


def _candidate_sort_key(
    candidate: CandidateObservation,
) -> tuple[int, float, int, str, str, str]:
    """Coverage-preserving order: longest span, then highest score, then start."""
    locator = candidate.evidence_locator
    if isinstance(locator, TextOffsetLocator):
        start = locator.start
        length = locator.end - locator.start
    else:
        # Field-path whole-field evidence sorts before text spans of equal score.
        start = -1
        length = 10**9
    score = candidate.score_value if candidate.score_value is not None else -1.0
    return (
        -length,
        -score,
        start,
        candidate.entity_type,
        candidate.recognizer_id,
        candidate.recognizer_version,
    )
