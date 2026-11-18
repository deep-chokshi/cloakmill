"""Integration smoke: DiscoveryEngine on synthetic multi-part inputs."""

from __future__ import annotations

import json
from pathlib import Path

from cloakmill.detection import (
    DiscoveryEngine,
    PartInput,
    build_default_catalog,
    default_field_name,
)
from cloakmill.detection.entity_types import ACCOUNT_ID, EMAIL_ADDRESS, EMPLOYEE_ID, PAYMENT_CARD
from cloakmill.domain import (
    CoverageState,
    FieldPathLocator,
    Part,
    ScoreKind,
    SurfaceKind,
    TextOffsetLocator,
    TextOffsetUnit,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "synthetic"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _text_part(part_id: str, content: str) -> Part:
    return Part(
        opaque_id=part_id,
        artifact_version_id="art-smoke-001",
        surface_kind=SurfaceKind.TEXT,
        original_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=len(content),
        ),
        coverage_state=CoverageState.PROCESSED,
        content_length=len(content),
    )


def _field_part(part_id: str, path: tuple[str | int, ...], content: str) -> Part:
    return Part(
        opaque_id=part_id,
        artifact_version_id="art-smoke-001",
        surface_kind=SurfaceKind.STRUCTURED_FIELD,
        original_locator=FieldPathLocator(path=path),
        coverage_state=CoverageState.PROCESSED,
        content_length=len(content),
    )


def test_discovery_across_text_and_structured_fields() -> None:
    note = (
        "Follow up with Maya Shah <maya@acme.example> (E-2C702C) "
        "regarding account AC-104. Card on file: 4111 1111 1111 1111."
    )
    email_value = "maya@acme.example"
    employee_value = "E-2C702C"

    inputs = [
        PartInput(part=_text_part("part-note", note), content=note),
        PartInput(
            part=_field_part("part-email", ("contacts", 0, "email"), email_value),
            content=email_value,
            field_name="email",
        ),
        PartInput(
            part=_field_part("part-emp", ("contacts", 0, "employee_id"), employee_value),
            content=employee_value,
            field_name="employee_id",
        ),
    ]

    result = DiscoveryEngine(build_default_catalog()).discover(inputs)
    by_part = {part.part_id: part for part in result.parts}

    note_types = {o.entity_type for o in by_part["part-note"].observations}
    assert EMAIL_ADDRESS in note_types
    assert EMPLOYEE_ID in note_types
    assert ACCOUNT_ID in note_types
    assert PAYMENT_CARD in note_types

    email_obs = by_part["part-email"].observations
    assert any(
        o.entity_type == EMAIL_ADDRESS and o.score_kind is ScoreKind.SCHEMA for o in email_obs
    )

    emp_obs = by_part["part-emp"].observations
    assert any(o.entity_type == EMPLOYEE_ID and o.score_kind is ScoreKind.SCHEMA for o in emp_obs)

    # Exact spans on the free-text note.
    for observation in by_part["part-note"].observations:
        locator = observation.evidence_locator
        assert isinstance(locator, TextOffsetLocator)
        span = note[locator.start : locator.end]
        if observation.entity_type == EMAIL_ADDRESS:
            assert span == "maya@acme.example"
        elif observation.entity_type == EMPLOYEE_ID:
            assert span == "E-2C702C"
        elif observation.entity_type == ACCOUNT_ID:
            assert span == "AC-104"
        elif observation.entity_type == PAYMENT_CARD:
            assert span == "4111 1111 1111 1111"


def test_overlap_conflict_surfaces_in_engine_output() -> None:
    # Force two recognizer-like candidates by scanning text where email local-part
    # alone is not enough; instead embed a Luhn-valid digit run that also matches
    # a crafted overlapping account pattern is hard — use validator-level overlap
    # via a custom dual-hit content: employee id nested inside a longer token is
    # avoided by boundaries. Use adjacent payment+account is non-overlap.
    # Here we verify engine wires validator conflicts when a stub emits overlap.
    from cloakmill.detection.candidates import CandidateObservation
    from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
    from cloakmill.detection.validator import ObservationValidator, RejectionReason
    from cloakmill.domain.enums import ScoreKind

    class OverlapStub(RuleRecognizer):
        def __init__(self) -> None:
            self._capability = RecognizerCapability(
                recognizer_id="rule.overlap_stub",
                version="1.0.0",
                entity_types=frozenset({"email_address", "employee_id"}),
                score_kind=ScoreKind.PATTERN_MATCH,
                surfaces=frozenset({SurfaceKind.TEXT}),
            )

        @property
        def capability(self) -> RecognizerCapability:
            return self._capability

        def recognize(self, part: Part, content: str, *, field_name: str | None = None):
            del part, content, field_name
            version = self._capability.recognizer_version
            return (
                CandidateObservation(
                    entity_type="email_address",
                    evidence_locator=TextOffsetLocator(
                        unit=TextOffsetUnit.CODEPOINTS, start=0, end=8
                    ),
                    recognizer_id=self._capability.recognizer_id,
                    recognizer_version=version,
                    score_kind=ScoreKind.PATTERN_MATCH,
                    score_value=0.5,
                ),
                CandidateObservation(
                    entity_type="employee_id",
                    evidence_locator=TextOffsetLocator(
                        unit=TextOffsetUnit.CODEPOINTS, start=4, end=12
                    ),
                    recognizer_id=self._capability.recognizer_id,
                    recognizer_version=version,
                    score_kind=ScoreKind.PATTERN_MATCH,
                    score_value=0.5,
                ),
            )

    from cloakmill.detection.catalog import RecognizerCatalog

    text = "abcdefghijkl"
    part = _text_part("part-overlap", text)
    engine = DiscoveryEngine(
        RecognizerCatalog((OverlapStub(),)),
        validator=ObservationValidator(),
    )
    result = engine.discover([PartInput(part=part, content=text)])
    assert len(result.observations) == 1
    assert len(result.conflicts) == 1
    assert result.rejected[0].reason is RejectionReason.OVERLAP_CONFLICT


def test_optional_smoke_against_identity_preview_example() -> None:
    preview_path = EXAMPLES / "identity-preview.json"
    assert preview_path.is_file()
    payload = json.loads(preview_path.read_text(encoding="utf-8"))
    assert payload.get("kind") == "illustrative-product-example"

    source_email = payload["person"]["source"]["email"]
    account = payload["account"]["source"]
    chat = payload["surfaces"][1]["source"]

    inputs = [
        PartInput(
            part=_field_part("part-preview-email", ("person", "source", "email"), source_email),
            content=source_email,
            field_name=default_field_name(
                _field_part("part-preview-email", ("person", "source", "email"), source_email)
            ),
        ),
        PartInput(part=_text_part("part-preview-chat", chat), content=chat),
        PartInput(
            part=_field_part("part-preview-account", ("account", "source"), account),
            content=account,
            field_name="account_id",
        ),
    ]
    result = DiscoveryEngine(build_default_catalog()).discover(inputs)
    types = {o.entity_type for o in result.observations}
    assert EMAIL_ADDRESS in types
    assert ACCOUNT_ID in types
