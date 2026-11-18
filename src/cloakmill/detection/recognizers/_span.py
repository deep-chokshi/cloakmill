"""Helpers to emit exact text-offset candidates from regex matches."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.recognizer import RecognizerCapability
from cloakmill.domain.enums import ScoreKind, TextOffsetUnit
from cloakmill.domain.locators import TextOffsetLocator


def iter_regex_candidates(
    *,
    pattern: re.Pattern[str],
    content: str,
    capability: RecognizerCapability,
    entity_type: str,
    score_value: float,
    score_kind: ScoreKind | None = None,
    accept: Callable[[re.Match[str]], bool] | None = None,
) -> Iterator[CandidateObservation]:
    """Yield candidates for each match; spans use Unicode codepoint offsets."""
    kind = score_kind if score_kind is not None else capability.score_kind
    for match in pattern.finditer(content):
        if accept is not None and not accept(match):
            continue
        start, end = match.span()
        if start == end:
            continue
        yield CandidateObservation(
            entity_type=entity_type,
            evidence_locator=TextOffsetLocator(
                unit=TextOffsetUnit.CODEPOINTS,
                start=start,
                end=end,
            ),
            recognizer_id=capability.recognizer_id,
            recognizer_version=capability.recognizer_version,
            score_kind=kind,
            score_value=score_value,
        )
