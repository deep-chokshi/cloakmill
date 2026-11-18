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

    Greedy digit runs can absorb a nearby short digit before the PAN
    (e.g. ``qty 1 4111...``) or trailing year/CVV digits that share space or
    hyphen separators. Candidates therefore start at every digit-run boundary,
    and when the maximal token fails Luhn, shorter 13-19 digit prefixes inside
    that token are tried so a valid card span is still emitted.
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
            if match is not None:
                span = _longest_luhn_prefix(content, match.start(), match.end())
                if span is not None:
                    yield span
        index += 1


def _longest_luhn_prefix(content: str, start: int, end: int) -> tuple[int, int] | None:
    """Return the longest Luhn-valid 13-19 digit prefix inside ``[start, end)``.

    The maximal ``_CARD_TOKEN_RE`` match may absorb trailing year or CVV digits
    that share space/hyphen separators. Walking digit-end offsets from longest
    to shortest recovers the exact PAN span when the full token fails Luhn.
    """
    digit_ends: list[int] = []
    index = start
    while index < end:
        char = content[index]
        if char.isdigit():
            digit_ends.append(index + 1)
            index += 1
            continue
        if char in " -" and index + 1 < end and content[index + 1].isdigit():
            index += 1
            continue
        break

    for count in range(min(len(digit_ends), 19), 12, -1):
        prefix_end = digit_ends[count - 1]
        if luhn_ok(digits_only(content[start:prefix_end])):
            return start, prefix_end
    return None
