"""Unit tests for RecognizerCatalog scheduling and DiscoveryEngine."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cloakmill.detection import (
    DiscoveryEngine,
    PartInput,
    RecognizerCatalog,
    build_default_catalog,
    default_field_name,
)
from cloakmill.detection.entity_types import EMAIL_ADDRESS, EMPLOYEE_ID, PAYMENT_CARD
from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.detection.recognizers.email import EmailRecognizer
from cloakmill.detection.recognizers.payment_card import PaymentCardRecognizer
from cloakmill.domain import (
    CoverageState,
    DomainValidationError,
    FieldPathLocator,
    Part,
    SurfaceKind,
    TextOffsetLocator,
    TextOffsetUnit,
)

DETECTION_ROOT = Path(__file__).resolve().parents[3] / "src" / "cloakmill" / "detection"
FORBIDDEN_IMPORT_NAMES = ("presidio", "presidio_analyzer", "presidio_anonymizer")


class _StubRecognizer(RuleRecognizer):
    def __init__(self, recognizer_id: str, surfaces: frozenset[SurfaceKind]) -> None:
        from cloakmill.domain.enums import ScoreKind

        self._capability = RecognizerCapability(
            recognizer_id=recognizer_id,
            version="0.0.1",
            entity_types=frozenset({"email_address"}),
            score_kind=ScoreKind.PATTERN_MATCH,
            surfaces=surfaces,
        )

    @property
    def capability(self) -> RecognizerCapability:
        return self._capability

    def recognize(self, part: Part, content: str, *, field_name: str | None = None):
        del part, content, field_name
        return ()


def _text_part(content: str, *, coverage: CoverageState = CoverageState.PROCESSED) -> Part:
    return Part(
        opaque_id="part-text",
        artifact_version_id="art-1",
        surface_kind=SurfaceKind.TEXT,
        original_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=len(content),
        ),
        coverage_state=coverage,
        content_length=len(content),
    )


def test_catalog_rejects_duplicate_ids_and_selects_by_surface() -> None:
    catalog = RecognizerCatalog(
        (
            _StubRecognizer("a", frozenset({SurfaceKind.TEXT})),
            _StubRecognizer("b", frozenset({SurfaceKind.STRUCTURED_FIELD})),
        )
    )
    assert len(catalog) == 2
    assert [r.capability.recognizer_id for r in catalog.select(surface=SurfaceKind.TEXT)] == ["a"]

    with pytest.raises(DomainValidationError, match="duplicate recognizer_id"):
        catalog.register(_StubRecognizer("a", frozenset({SurfaceKind.TEXT})))


def test_catalog_filters_by_entity_type() -> None:
    catalog = build_default_catalog()
    selected = catalog.select(entity_types=frozenset({EMAIL_ADDRESS}))
    ids = {r.capability.recognizer_id for r in selected}
    assert "rule.email" in ids
    assert "rule.schema_field" in ids
    assert "rule.employee_id" not in ids


def test_discovery_engine_is_deterministic_on_synthetic_text() -> None:
    text = "Contact maya@acme.example (E-2C702C) about AC-104."
    part = _text_part(text)
    engine = DiscoveryEngine(build_default_catalog())

    first = engine.discover([PartInput(part=part, content=text)])
    second = engine.discover([PartInput(part=part, content=text)])

    assert [o.to_dict() for o in first.observations] == [o.to_dict() for o in second.observations]
    types = {o.entity_type for o in first.observations}
    assert EMAIL_ADDRESS in types
    assert EMPLOYEE_ID in types
    assert "account_id" in types

    for observation in first.observations:
        locator = observation.evidence_locator
        assert isinstance(locator, TextOffsetLocator)
        span = text[locator.start : locator.end]
        if observation.entity_type == EMAIL_ADDRESS:
            assert span == "maya@acme.example"
        elif observation.entity_type == EMPLOYEE_ID:
            assert span == "E-2C702C"
        elif observation.entity_type == "account_id":
            assert span == "AC-104"


def test_discovery_skips_non_processed_coverage() -> None:
    text = "maya@acme.example"
    part = _text_part(text, coverage=CoverageState.EXCLUDED)
    result = DiscoveryEngine(build_default_catalog()).discover([PartInput(part=part, content=text)])
    assert result.parts[0].skipped is True
    assert result.observations == ()


def test_discovery_entity_type_filter() -> None:
    text = "maya@acme.example and E-2C702C"
    part = _text_part(text)
    result = DiscoveryEngine(build_default_catalog()).discover(
        [PartInput(part=part, content=text)],
        entity_types=frozenset({EMAIL_ADDRESS}),
    )
    assert {o.entity_type for o in result.observations} == {EMAIL_ADDRESS}


def test_default_field_name_from_locator() -> None:
    part = Part(
        opaque_id="part-email",
        artifact_version_id="art-1",
        surface_kind=SurfaceKind.STRUCTURED_FIELD,
        original_locator=FieldPathLocator(path=("rows", 0, "email")),
        coverage_state=CoverageState.PROCESSED,
        content_length=5,
    )
    assert default_field_name(part) == "email"


def test_part_input_rejects_content_length_mismatch() -> None:
    part = _text_part("abcd")
    with pytest.raises(ValueError, match="content_length"):
        PartInput(part=part, content="abc")


def test_detection_package_does_not_import_presidio() -> None:
    for path in DETECTION_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    assert root not in FORBIDDEN_IMPORT_NAMES, path
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                assert root not in FORBIDDEN_IMPORT_NAMES, path


def test_detection_does_not_import_eval_fixtures() -> None:
    forbidden = "tests.fixtures.eval"
    for path in DETECTION_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert forbidden not in source
        assert "ENGINE_INACCESSIBLE" not in source


def test_default_catalog_registers_email_recognizer() -> None:
    catalog = RecognizerCatalog((EmailRecognizer(),))
    assert catalog.get("rule.email").capability.version == "1.0.0"


def test_engine_flags_exception_review_for_uncovered_card_length_run() -> None:
    text = "card 4111111111111112 rejected"
    part = _text_part(text)
    engine = DiscoveryEngine(RecognizerCatalog((PaymentCardRecognizer(),)))
    result = engine.discover([PartInput(part=part, content=text)])
    assert result.observations == ()
    assert result.requires_exception_review is True


def test_engine_accepts_interior_payment_card_without_exception() -> None:
    text = "ref 994111111111111111 paid"
    part = _text_part(text)
    engine = DiscoveryEngine(RecognizerCatalog((PaymentCardRecognizer(),)))
    result = engine.discover([PartInput(part=part, content=text)])
    assert len(result.observations) == 1
    assert result.observations[0].entity_type == PAYMENT_CARD
    assert result.requires_exception_review is False
