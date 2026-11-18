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


class SchemaFieldRecognizer(RuleRecognizer):
    """When a structured field name is a known identifier, validate the value.

    Emits a whole-field ``FieldPathLocator`` observation with ``ScoreKind.SCHEMA``
    when the leaf field name maps to a known entity type and the value matches.
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

        validator = _VALUE_VALIDATORS.get(entity_type)
        if validator is None or not validator(content):
            return ()

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
                score_value=1.0,
            ),
        )
