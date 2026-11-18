"""Unit tests for ObservationValidator overlap and bounds policy."""

from __future__ import annotations

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.validator import ObservationValidator, RejectionReason
from cloakmill.domain import (
    CoverageState,
    Part,
    ScoreKind,
    SurfaceKind,
    TextOffsetLocator,
    TextOffsetUnit,
)


def _part(length: int) -> Part:
    return Part(
        opaque_id="part-body",
        artifact_version_id="art-syn",
        surface_kind=SurfaceKind.TEXT,
        original_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=length,
        ),
        coverage_state=CoverageState.PROCESSED,
        content_length=length,
    )


def _candidate(
    *,
    start: int,
    end: int,
    entity_type: str = "email_address",
    recognizer_id: str = "rule.email",
    version: str = "rule.email/1.0.0",
    score: float = 0.9,
) -> CandidateObservation:
    return CandidateObservation(
        entity_type=entity_type,
        evidence_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=start,
            end=end,
        ),
        recognizer_id=recognizer_id,
        recognizer_version=version,
        score_kind=ScoreKind.PATTERN_MATCH,
        score_value=score,
    )


def test_validator_accepts_exact_in_bounds_span() -> None:
    text = "maya@acme.example"
    part = _part(len(text))
    result = ObservationValidator().validate(part, (_candidate(start=0, end=len(text)),))
    assert len(result.accepted) == 1
    assert result.rejected == ()
    assert result.conflicts == ()
    obs = result.accepted[0]
    assert obs.part_id == part.opaque_id
    assert obs.artifact_version_id == part.artifact_version_id
    assert obs.evidence_refs[0].locator == obs.evidence_locator


def test_validator_rejects_out_of_bounds_and_empty_spans() -> None:
    part = _part(10)
    validator = ObservationValidator()

    oob = validator.validate(part, (_candidate(start=0, end=11),))
    assert oob.accepted == ()
    assert len(oob.rejected) == 1
    assert oob.rejected[0].reason is RejectionReason.OUT_OF_BOUNDS

    empty = validator.validate(part, (_candidate(start=3, end=3),))
    assert empty.accepted == ()
    assert empty.rejected[0].reason is RejectionReason.EMPTY_SPAN


def test_validator_conflicts_overlapping_evidence_explicitly() -> None:
    part = _part(20)
    first = _candidate(start=0, end=10, entity_type="email_address", score=0.9)
    second = _candidate(
        start=5,
        end=15,
        entity_type="employee_id",
        recognizer_id="rule.employee_id",
        version="rule.employee_id/1.0.0",
        score=0.95,
    )
    result = ObservationValidator().validate(part, (first, second))

    assert len(result.accepted) == 1
    assert result.accepted[0].entity_type == "email_address"
    assert len(result.rejected) == 1
    assert result.rejected[0].reason is RejectionReason.OVERLAP_CONFLICT
    assert len(result.conflicts) == 1
    assert result.conflicts[0].left == first
    assert result.conflicts[0].right == second


def test_validator_dedupes_identical_candidates() -> None:
    part = _part(20)
    one = _candidate(start=2, end=8)
    two = _candidate(start=2, end=8)
    result = ObservationValidator().validate(part, (one, two))
    assert len(result.accepted) == 1
    assert len(result.rejected) == 1
    assert result.rejected[0].reason is RejectionReason.DUPLICATE
    assert result.conflicts == ()


def test_validator_accepts_adjacent_non_overlapping_spans() -> None:
    part = _part(20)
    left = _candidate(start=0, end=5, entity_type="email_address")
    right = _candidate(
        start=5,
        end=10,
        entity_type="account_id",
        recognizer_id="rule.account_id",
        version="rule.account_id/1.0.0",
    )
    result = ObservationValidator().validate(part, (left, right))
    assert len(result.accepted) == 2
    assert result.conflicts == ()
    assert result.rejected == ()


def test_validator_ids_are_deterministic() -> None:
    part = _part(16)
    candidate = _candidate(start=1, end=8)
    first = ObservationValidator().validate(part, (candidate,)).accepted[0]
    second = ObservationValidator().validate(part, (candidate,)).accepted[0]
    assert first.opaque_id == second.opaque_id
    assert first.evidence_refs[0].opaque_id == second.evidence_refs[0].opaque_id
