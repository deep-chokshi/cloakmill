"""Checksum recognizer for payment card numbers (Luhn)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.entity_types import PAYMENT_CARD
from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.detection.recognizers._patterns import luhn_ok
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind, SurfaceKind, TextOffsetUnit
from cloakmill.domain.locators import TextOffsetLocator

# Maximal run of digits joined by optional single space/hyphen separators.
_DIGIT_REGION_RE = re.compile(r"\d(?:[ -]?\d)*")


class PaymentCardRecognizer(RuleRecognizer):
    """Emit payment_card only when digit windows pass the Luhn checksum.

    Scans every separator-joined digit region and Luhn-checks all interior
    13-19 digit windows (not only prefixes of digit-run boundaries). Selection
    maximizes covered digits among non-overlapping Luhn windows so concatenated
    PANs are preferred over a longer straddling false window. When a card-length
    stretch of digits remains uncovered after selection,
    ``exception_review_required`` is set so free-text misses cannot fail open.
    """

    def __init__(self) -> None:
        self._capability = RecognizerCapability(
            recognizer_id="rule.payment_card_luhn",
            version="1.0.0",
            entity_types=frozenset({PAYMENT_CARD}),
            score_kind=ScoreKind.CHECKSUM,
            surfaces=frozenset({SurfaceKind.TEXT, SurfaceKind.STRUCTURED_FIELD}),
        )
        self._exception_review_required = False

    @property
    def capability(self) -> RecognizerCapability:
        return self._capability

    def exception_review_required(self) -> bool:
        return self._exception_review_required

    def recognize(
        self,
        part: Part,
        content: str,
        *,
        field_name: str | None = None,
    ) -> Sequence[CandidateObservation]:
        del part, field_name
        spans, needs_review = _scan_luhn_spans(content)
        self._exception_review_required = needs_review
        hits: list[CandidateObservation] = []
        seen: set[tuple[int, int]] = set()
        for start, end in spans:
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


def _scan_luhn_spans(content: str) -> tuple[list[tuple[int, int]], bool]:
    """Return coverage-maximizing Luhn spans and residual-review flag."""
    selected: list[tuple[int, int]] = []
    needs_review = False
    for match in _DIGIT_REGION_RE.finditer(content):
        region_spans, region_needs_review = _cover_digit_region(content, match.start(), match.end())
        selected.extend(region_spans)
        needs_review = needs_review or region_needs_review
    return selected, needs_review


def _cover_digit_region(
    content: str, region_start: int, region_end: int
) -> tuple[list[tuple[int, int]], bool]:
    """Select Luhn windows inside one separator-joined digit region."""
    digit_offsets: list[int] = [
        index for index in range(region_start, region_end) if content[index].isdigit()
    ]
    digit_count = len(digit_offsets)
    if digit_count < 13:
        return [], False

    windows: list[tuple[int, int, int, int]] = []
    for start_di in range(digit_count):
        for length in range(min(19, digit_count - start_di), 12, -1):
            end_di = start_di + length
            digits = "".join(content[digit_offsets[i]] for i in range(start_di, end_di))
            # Major-network IIN lead digits avoid Luhn-valid junk interiors (e.g. runs of 1).
            if digits[0] not in "3456" or not luhn_ok(digits):
                continue
            content_start = digit_offsets[start_di]
            content_end = digit_offsets[end_di - 1] + 1
            windows.append((start_di, end_di, content_start, content_end))

    taken = _max_digit_coverage(windows)
    covered: set[int] = set()
    for start_di, end_di, _content_start, _content_end in taken:
        covered.update(range(start_di, end_di))

    uncovered_run = 0
    needs_review = False
    for index in range(digit_count):
        if index in covered:
            uncovered_run = 0
            continue
        uncovered_run += 1
        if uncovered_run >= 13:
            needs_review = True
            break

    spans = [(content_start, content_end) for _s, _e, content_start, content_end in taken]
    spans.sort(key=lambda item: item[0])
    return spans, needs_review


def _max_digit_coverage(
    windows: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Weighted interval scheduling: maximize digits covered without overlap.

    Each window is ``(start_di, end_di, content_start, content_end)``. Longer
    straddling false positives lose to multiple shorter genuine PANs.
    """
    if not windows:
        return []

    ordered = sorted(windows, key=lambda item: (item[1], item[0], -(item[1] - item[0])))
    count = len(ordered)
    # latest compatible predecessor: end_di <= start_di
    predecessors = [-1] * count
    for index in range(count):
        start_di = ordered[index][0]
        lo, hi = 0, index - 1
        best = -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if ordered[mid][1] <= start_di:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        predecessors[index] = best

    # dp_value[i] = best coverage using ordered[0..i]
    dp_value = [0] * count
    # dp_take[i] = True when ordered[i] is in the optimal set for prefix i
    dp_take = [False] * count
    for index in range(count):
        weight = ordered[index][1] - ordered[index][0]
        with_prev = weight
        prev = predecessors[index]
        if prev >= 0:
            with_prev += dp_value[prev]
        without = dp_value[index - 1] if index > 0 else 0
        if with_prev > without:
            dp_value[index] = with_prev
            dp_take[index] = True
        else:
            dp_value[index] = without
            dp_take[index] = False

    selected: list[tuple[int, int, int, int]] = []
    index = count - 1
    while index >= 0:
        if dp_take[index]:
            selected.append(ordered[index])
            index = predecessors[index]
        else:
            index -= 1
    selected.reverse()
    return selected
