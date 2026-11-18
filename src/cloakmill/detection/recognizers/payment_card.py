"""Checksum recognizer for payment card numbers (Luhn)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.entity_types import PAYMENT_CARD
from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.detection.recognizers._patterns import PAYMENT_CARD_RE, digits_only, luhn_ok
from cloakmill.detection.recognizers._span import iter_regex_candidates
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind, SurfaceKind


class PaymentCardRecognizer(RuleRecognizer):
    """Emit payment_card only when digit runs pass the Luhn checksum."""

    def __init__(self) -> None:
        self._capability = RecognizerCapability(
            recognizer_id="rule.payment_card_luhn",
            version="1.0.0",
            entity_types=frozenset({PAYMENT_CARD}),
            score_kind=ScoreKind.CHECKSUM,
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

        def accept(match: re.Match[str]) -> bool:
            return luhn_ok(digits_only(match.group(0)))

        return tuple(
            iter_regex_candidates(
                pattern=PAYMENT_CARD_RE,
                content=content,
                capability=self._capability,
                entity_type=PAYMENT_CARD,
                score_value=0.99,
                score_kind=ScoreKind.CHECKSUM,
                accept=accept,
            )
        )
