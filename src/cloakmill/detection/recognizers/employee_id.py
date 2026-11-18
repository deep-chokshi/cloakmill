"""Regex recognizer for synthetic employee identifiers (E-XXXXXX)."""

from __future__ import annotations

from collections.abc import Sequence

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.entity_types import EMPLOYEE_ID
from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.detection.recognizers._patterns import EMPLOYEE_ID_RE
from cloakmill.detection.recognizers._span import iter_regex_candidates
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind, SurfaceKind


class EmployeeIdRecognizer(RuleRecognizer):
    """Pattern match for CloakMill synthetic employee id format."""

    def __init__(self) -> None:
        self._capability = RecognizerCapability(
            recognizer_id="rule.employee_id",
            version="1.0.0",
            entity_types=frozenset({EMPLOYEE_ID}),
            score_kind=ScoreKind.PATTERN_MATCH,
            surfaces=frozenset({SurfaceKind.TEXT, SurfaceKind.STRUCTURED_FIELD}),
        )

    @property
    def capability(self) -> RecognizerCapability:
        return self._capability

    def recognize(
        self,
        part: Part,
        content: str,
        *,
        field_name: str | None = None,
    ) -> Sequence[CandidateObservation]:
        del part, field_name
        return tuple(
            iter_regex_candidates(
                pattern=EMPLOYEE_ID_RE,
                content=content,
                capability=self._capability,
                entity_type=EMPLOYEE_ID,
                score_value=0.95,
            )
        )
