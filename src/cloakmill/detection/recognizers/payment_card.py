"""Checksum recognizer for payment card numbers (Luhn)."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.entity_types import PAYMENT_CARD
from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.detection.recognizers._patterns import digits_only, luhn_ok
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind, SurfaceKind, TextOffsetUnit
from cloakmill.domain.locators import TextOffsetLocator

# 13-19 digits with optional single space/hyphen separators between digits.
_CARD_TOKEN_RE = re.compile(r"\d(?:[ -]?\d){12,18}")


class PaymentCardRecognizer(RuleRecognizer):
    """Emit payment_card only when digit runs pass the Luhn checksum.

    Greedy digit runs can absorb a nearby short digit (e.g. ``qty 1 4111...``).
    Candidates are therefore started at every digit-run boundary and accepted
    only when the exact span passes Luhn, so a valid card is not skipped after
    a failed merged match.
    """

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
        seen: set[tuple[int, int]] = set()
        hits: list[CandidateObservation] = []
        for start, end in _iter_luhn_spans(content):
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                CandidateObservation(
                    entity_type=PAYMENT_CARD,
                    evidence_locator=TextOffsetLocator(
                        unit=TextOffsetUnit.CODEPOINTS,
                        start=start,
                        end=end,
                    ),
                    recognizer_id=self._capability.recognizer_id,
                    recognizer_version=self._capability.recognizer_version,
                    score_kind=ScoreKind.CHECKSUM,
                    score_value=0.99,
                )
            )
        return tuple(hits)


def _iter_luhn_spans(content: str) -> Iterator[tuple[int, int]]:
    """Yield ``[start, end)`` spans for Luhn-valid card token starts."""
    index = 0
    length = len(content)
    while index < length:
        char = content[index]
        if char.isdigit() and (index == 0 or not content[index - 1].isdigit()):
            match = _CARD_TOKEN_RE.match(content, index)
            if match is not None and luhn_ok(digits_only(match.group(0))):
                yield match.start(), match.end()
        index += 1
