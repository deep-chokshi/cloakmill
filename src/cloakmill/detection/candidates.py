"""Candidate observations produced by recognizers before validation."""

from __future__ import annotations

from dataclasses import dataclass

from cloakmill.domain.enums import ScoreKind
from cloakmill.domain.locators import OriginalLocator


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    """Recognizer proposal with exact evidence; not yet an accepted Observation."""

    entity_type: str
    evidence_locator: OriginalLocator
    recognizer_id: str
    recognizer_version: str
    score_kind: ScoreKind
    score_value: float | None = None
