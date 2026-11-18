"""Schema-hint recognizer for known structured field names."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.entity_types import (
    ACCOUNT_ID,
    EMAIL_ADDRESS,
    EMPLOYEE_ID,
    PAYMENT_CARD,
)
from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.detection.recognizers._patterns import (
    ACCOUNT_ID_RE,
    EMAIL_RE,
    EMPLOYEE_ID_RE,
    SCHEMA_FIELD_ALIASES,
    digits_only,
    luhn_ok,
)
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind, SurfaceKind, TextOffsetUnit
from cloakmill.domain.locators import FieldPathLocator, TextOffsetLocator

_VALUE_VALIDATORS: dict[str, Callable[[str], bool]] = {
    EMAIL_ADDRESS: lambda value: EMAIL_RE.fullmatch(value.strip()) is not None,
    EMPLOYEE_ID: lambda value: EMPLOYEE_ID_RE.fullmatch(value.strip()) is not None,
    ACCOUNT_ID: lambda value: ACCOUNT_ID_RE.fullmatch(value.strip()) is not None,
    PAYMENT_CARD: lambda value: luhn_ok(digits_only(value)),
}

# Score used when the field name is a known sensitive alias but the value fails
# format/checksum validation. Still emit so the field is not treated as clean.
_UNVALIDATED_SCHEMA_SCORE = 0.4


class SchemaFieldRecognizer(RuleRecognizer):
    """When a structured field name is a known identifier, emit field evidence.

    Emits a whole-field ``FieldPathLocator`` observation with ``ScoreKind.SCHEMA``
    when the leaf field name maps to a known entity type. Values that pass
    format/checksum checks score ``1.0``. Non-empty values that fail validation
    still emit at a reduced score so sensitive-named fields never fail open.
    """

    def __init__(self) -> None:
        self._capability = RecognizerCapability(
            recognizer_id="rule.schema_field",
            version="1.0.0",
            entity_types=frozenset({EMAIL_ADDRESS, EMPLOYEE_ID, ACCOUNT_ID, PAYMENT_CARD}),
            score_kind=ScoreKind.SCHEMA,
            surfaces=frozenset({SurfaceKind.STRUCTURED_FIELD}),
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
        if part.surface_kind is not SurfaceKind.STRUCTURED_FIELD:
            return ()
        leaf = field_name
        if leaf is None and isinstance(part.original_locator, FieldPathLocator):
            last = part.original_locator.path[-1]
            leaf = last if isinstance(last, str) else None
        if leaf is None:
            return ()

        entity_type = SCHEMA_FIELD_ALIASES.get(leaf.lower())
        if entity_type is None:
            return ()

        # Empty fields stay empty; nothing to cover.
        if content.strip() == "":
            return ()

        validator = _VALUE_VALIDATORS.get(entity_type)
        value_ok = validator is not None and validator(content)
        score = 1.0 if value_ok else _UNVALIDATED_SCHEMA_SCORE

        if isinstance(part.original_locator, FieldPathLocator):
            locator: FieldPathLocator | TextOffsetLocator = part.original_locator
        else:
            locator = TextOffsetLocator(
                unit=TextOffsetUnit.CODEPOINTS,
                start=0,
                end=len(content),
            )

        return (
            CandidateObservation(
                entity_type=entity_type,
                evidence_locator=locator,
                recognizer_id=self._capability.recognizer_id,
                recognizer_version=self._capability.recognizer_version,
                score_kind=ScoreKind.SCHEMA,
                score_value=score,
            ),
        )
