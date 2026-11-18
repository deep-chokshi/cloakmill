"""Precision-oriented unit tests for CloakMill-owned rule recognizers."""

from __future__ import annotations

from cloakmill.detection.entity_types import (
    ACCOUNT_ID,
    EMAIL_ADDRESS,
    EMPLOYEE_ID,
    PAYMENT_CARD,
)
from cloakmill.detection.recognizers import (
    AccountIdRecognizer,
    EmailRecognizer,
    EmployeeIdRecognizer,
    PaymentCardRecognizer,
    SchemaFieldRecognizer,
)
from cloakmill.detection.recognizers._patterns import luhn_ok
from cloakmill.domain import (
    CoverageState,
    FieldPathLocator,
    Part,
    ScoreKind,
    SurfaceKind,
    TextOffsetLocator,
    TextOffsetUnit,
)


def _text_part(content: str) -> Part:
    return Part(
        opaque_id="part-text-001",
        artifact_version_id="art-001",
        surface_kind=SurfaceKind.TEXT,
        original_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=len(content),
        ),
        coverage_state=CoverageState.PROCESSED,
        content_length=len(content),
    )


def _field_part(path: tuple[str | int, ...], content: str) -> Part:
    return Part(
        opaque_id="part-field-001",
        artifact_version_id="art-001",
        surface_kind=SurfaceKind.STRUCTURED_FIELD,
        original_locator=FieldPathLocator(path=path),
        coverage_state=CoverageState.PROCESSED,
        content_length=len(content),
    )


def test_email_recognizer_exact_span_on_synthetic_text() -> None:
    text = "Ask Maya Shah <maya@acme.example> about account AC-104."
    start = text.index("maya@acme.example")
    end = start + len("maya@acme.example")
    part = _text_part(text)

    hits = EmailRecognizer().recognize(part, text)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.entity_type == EMAIL_ADDRESS
    assert hit.score_kind is ScoreKind.PATTERN_MATCH
    assert isinstance(hit.evidence_locator, TextOffsetLocator)
    assert hit.evidence_locator.start == start
    assert hit.evidence_locator.end == end
    assert text[start:end] == "maya@acme.example"


def test_email_recognizer_rejects_near_miss_local_parts() -> None:
    text = "not-an-email@ and user@localhost are incomplete"
    hits = EmailRecognizer().recognize(_text_part(text), text)
    assert hits == ()


def test_email_recognizer_allows_trailing_sentence_period() -> None:
    text = "Write alice@example.com. Then follow up."
    hits = EmailRecognizer().recognize(_text_part(text), text)
    assert len(hits) == 1
    locator = hits[0].evidence_locator
    assert isinstance(locator, TextOffsetLocator)
    assert text[locator.start : locator.end] == "alice@example.com"


def test_email_recognizer_still_extends_through_domain_dot_labels() -> None:
    text = "Contact maya@acme.example today"
    hits = EmailRecognizer().recognize(_text_part(text), text)
    assert len(hits) == 1
    locator = hits[0].evidence_locator
    assert isinstance(locator, TextOffsetLocator)
    assert text[locator.start : locator.end] == "maya@acme.example"


def test_employee_and_account_id_recognizers_are_precise() -> None:
    text = "Owner E-2C702C on AC-104; ignore EX-2C702C and ACCT-104."
    part = _text_part(text)

    employee_hits = EmployeeIdRecognizer().recognize(part, text)
    assert len(employee_hits) == 1
    emp = employee_hits[0].evidence_locator
    assert isinstance(emp, TextOffsetLocator)
    assert text[emp.start : emp.end] == "E-2C702C"

    account_hits = AccountIdRecognizer().recognize(part, text)
    assert len(account_hits) == 1
    acct = account_hits[0].evidence_locator
    assert isinstance(acct, TextOffsetLocator)
    assert text[acct.start : acct.end] == "AC-104"


def test_payment_card_requires_luhn_checksum() -> None:
    # 4111111111111111 is a well-known Luhn-valid test PAN (synthetic only).
    valid = "card 4111-1111-1111-1111 on file"
    invalid = "card 4111-1111-1111-1112 on file"
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")

    recognizer = PaymentCardRecognizer()
    valid_hits = recognizer.recognize(_text_part(valid), valid)
    assert len(valid_hits) == 1
    assert valid_hits[0].entity_type == PAYMENT_CARD
    assert valid_hits[0].score_kind is ScoreKind.CHECKSUM
    locator = valid_hits[0].evidence_locator
    assert isinstance(locator, TextOffsetLocator)
    assert valid[locator.start : locator.end] == "4111-1111-1111-1111"

    invalid_hits = recognizer.recognize(_text_part(invalid), invalid)
    assert invalid_hits == ()


def test_payment_card_recovers_from_greedy_nearby_digit_merge() -> None:
    # Greedy ``(?:\d[ -]?){12,18}\d`` can absorb the leading ``1`` from ``qty 1``.
    text = "qty 1 4111111111111111 purchased"
    hits = PaymentCardRecognizer().recognize(_text_part(text), text)
    assert len(hits) == 1
    locator = hits[0].evidence_locator
    assert isinstance(locator, TextOffsetLocator)
    assert text[locator.start : locator.end] == "4111111111111111"


def test_schema_field_recognizer_uses_field_path_evidence() -> None:
    value = "alex.nguyen.0000@acme.example"
    part = _field_part(("records", 0, "email"), value)
    hits = SchemaFieldRecognizer().recognize(part, value, field_name="email")
    assert len(hits) == 1
    assert hits[0].entity_type == EMAIL_ADDRESS
    assert hits[0].score_kind is ScoreKind.SCHEMA
    assert hits[0].evidence_locator == part.original_locator


def test_schema_field_recognizer_rejects_mismatched_value() -> None:
    value = "not-an-email"
    part = _field_part(("email",), value)
    hits = SchemaFieldRecognizer().recognize(part, value, field_name="email")
    assert hits == ()


def test_schema_field_ignores_unknown_field_names() -> None:
    value = "maya@acme.example"
    part = _field_part(("notes",), value)
    hits = SchemaFieldRecognizer().recognize(part, value, field_name="notes")
    assert hits == ()


def test_schema_employee_and_account_aliases() -> None:
    emp_value = "E-2C702C"
    emp_part = _field_part(("employee_id",), emp_value)
    emp_hits = SchemaFieldRecognizer().recognize(emp_part, emp_value, field_name="employee_id")
    assert len(emp_hits) == 1
    assert emp_hits[0].entity_type == EMPLOYEE_ID

    acct_value = "AC-1000"
    acct_part = _field_part(("account_id",), acct_value)
    acct_hits = SchemaFieldRecognizer().recognize(acct_part, acct_value, field_name="account_id")
    assert len(acct_hits) == 1
    assert acct_hits[0].entity_type == ACCOUNT_ID
