"""Behavioral tests for F01 domain contracts (synthetic fixtures only)."""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cloakmill.domain import (
    ArtifactVersion,
    CoverageState,
    DomainValidationError,
    EvidenceRef,
    FieldPathLocator,
    Observation,
    Part,
    ScoreKind,
    SurfaceKind,
    TextOffsetLocator,
    TextOffsetUnit,
    dumps,
    loads,
    to_jsonable,
    validate_locator,
    validate_observation,
    validate_part,
)

DOMAIN_ROOT = Path(__file__).resolve().parents[3] / "src" / "cloakmill" / "domain"
FORBIDDEN_IMPORT_PREFIXES = (
    "cloakmill.connectors",
    "cloakmill.formats",
    "cloakmill.detection",
    "cloakmill.identity",
    "cloakmill.transforms",
    "cloakmill.validation",
    "cloakmill.pipeline",
)

# Synthetic chat body using reserved example domains only.
SYNTHETIC_TEXT = "Ask Maya Shah <maya@acme.example> about account AC-104."
EMAIL_START = SYNTHETIC_TEXT.index("maya@acme.example")
EMAIL_END = EMAIL_START + len("maya@acme.example")


def _artifact() -> ArtifactVersion:
    return ArtifactVersion(
        opaque_id="art-syn-001",
        source_version="export-2026-03-01T12:00:00Z",
        private_integrity_digest="sha256:" + ("ab" * 32),
        access_scope="project:syn-demo",
        media_type="text/plain",
    )


def _text_part(artifact: ArtifactVersion) -> Part:
    return Part(
        opaque_id="part-syn-body",
        artifact_version_id=artifact.opaque_id,
        surface_kind=SurfaceKind.TEXT,
        original_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=len(SYNTHETIC_TEXT),
        ),
        coverage_state=CoverageState.PROCESSED,
        content_length=len(SYNTHETIC_TEXT),
    )


def _field_part(artifact: ArtifactVersion) -> Part:
    return Part(
        opaque_id="part-syn-email",
        artifact_version_id=artifact.opaque_id,
        surface_kind=SurfaceKind.STRUCTURED_FIELD,
        original_locator=FieldPathLocator(path=("records", 0, "owner", "email")),
        coverage_state=CoverageState.PROCESSED,
        content_length=len("maya@acme.example"),
    )


def _email_observation(part: Part) -> Observation:
    return Observation(
        opaque_id="obs-syn-email-1",
        part_id=part.opaque_id,
        artifact_version_id=part.artifact_version_id,
        entity_type="EMAIL_ADDRESS",
        evidence_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=EMAIL_START,
            end=EMAIL_END,
        ),
        recognizer_version="rule.email.v1",
        score_kind=ScoreKind.PATTERN_MATCH,
        score_value=1.0,
        evidence_refs=(
            EvidenceRef(
                opaque_id="ev-syn-email-1",
                part_id=part.opaque_id,
                locator=TextOffsetLocator(
                    unit=TextOffsetUnit.CODEPOINTS,
                    start=EMAIL_START,
                    end=EMAIL_END,
                ),
                recognizer_version="rule.email.v1",
            ),
        ),
    )


def test_artifact_part_observation_round_trip_json() -> None:
    artifact = _artifact()
    part = _text_part(artifact)
    observation = _email_observation(part)

    assert loads(dumps(artifact), ArtifactVersion) == artifact
    assert loads(dumps(part), Part) == part
    assert loads(dumps(observation), Observation) == observation

    # Tagged locator payloads remain stable under plain json.dumps of to_jsonable.
    locator_payload = to_jsonable(observation.evidence_locator)
    assert json.loads(json.dumps(locator_payload)) == locator_payload


def test_field_path_locator_round_trip_and_part_validation() -> None:
    artifact = _artifact()
    part = _field_part(artifact)
    validate_part(part)
    restored = loads(dumps(part), Part)
    assert restored.original_locator == FieldPathLocator(path=("records", 0, "owner", "email"))
    assert restored.coverage_state is CoverageState.PROCESSED


def test_observation_validated_against_part_bounds() -> None:
    artifact = _artifact()
    part = _text_part(artifact)
    observation = _email_observation(part)
    validate_observation(observation, part=part)

    too_long = Observation(
        opaque_id="obs-syn-bad-bounds",
        part_id=part.opaque_id,
        artifact_version_id=part.artifact_version_id,
        entity_type="EMAIL_ADDRESS",
        evidence_locator=TextOffsetLocator(
            unit=TextOffsetUnit.CODEPOINTS,
            start=0,
            end=len(SYNTHETIC_TEXT) + 1,
        ),
        recognizer_version="rule.email.v1",
        score_kind=ScoreKind.PATTERN_MATCH,
    )
    with pytest.raises(DomainValidationError, match="exceeds content_length"):
        validate_observation(too_long, part=part)


@pytest.mark.parametrize(
    "locator",
    [
        TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=-1, end=2),
        TextOffsetLocator(unit=TextOffsetUnit.CODEPOINTS, start=5, end=4),
        TextOffsetLocator(unit=TextOffsetUnit.UTF8_BYTES, start=0, end=99),
        FieldPathLocator(path=()),
        FieldPathLocator(path=("owner", "")),
        FieldPathLocator(path=("items", -1)),
    ],
)
def test_invalid_locators_are_rejected(locator: object) -> None:
    content_length = 10 if isinstance(locator, TextOffsetLocator) else None
    with pytest.raises(DomainValidationError):
        if isinstance(locator, TextOffsetLocator | FieldPathLocator):
            validate_locator(locator, content_length=content_length)
        else:  # pragma: no cover - parametrization only uses locator types
            raise AssertionError("unexpected locator fixture")


def test_from_dict_rejects_invalid_serialized_locators() -> None:
    with pytest.raises(DomainValidationError):
        TextOffsetLocator.from_dict(
            {"kind": "text_offset", "unit": "codepoints", "start": 3, "end": 1}
        )
    with pytest.raises(DomainValidationError):
        FieldPathLocator.from_dict({"kind": "field_path", "path": []})
    with pytest.raises(DomainValidationError):
        ArtifactVersion.from_dict(
            {
                "opaque_id": "art-syn-002",
                "source_version": "v1",
                "private_integrity_digest": "md5:deadbeef",
                "access_scope": "project:syn-demo",
            }
        )


@pytest.mark.parametrize("bad_id", [None, 123, True])
def test_from_dict_rejects_null_and_non_string_ids(bad_id: object) -> None:
    """JSON null/non-strings must not coerce into accepted opaque ids like \"None\"."""
    digest = "sha256:" + ("ab" * 32)
    with pytest.raises(DomainValidationError):
        ArtifactVersion.from_dict(
            {
                "opaque_id": bad_id,
                "source_version": "v1",
                "private_integrity_digest": digest,
                "access_scope": "project:syn-demo",
            }
        )
    with pytest.raises(DomainValidationError):
        Part.from_dict(
            {
                "opaque_id": bad_id,
                "artifact_version_id": "art-syn-001",
                "surface_kind": "text",
                "original_locator": {
                    "kind": "text_offset",
                    "unit": "codepoints",
                    "start": 0,
                    "end": 1,
                },
                "coverage_state": "processed",
            }
        )
    with pytest.raises(DomainValidationError):
        Observation.from_dict(
            {
                "opaque_id": bad_id,
                "part_id": "part-syn-body",
                "artifact_version_id": "art-syn-001",
                "entity_type": "EMAIL_ADDRESS",
                "evidence_locator": {
                    "kind": "text_offset",
                    "unit": "codepoints",
                    "start": 0,
                    "end": 1,
                },
                "recognizer_version": "rule.email.v1",
                "score_kind": "pattern_match",
            }
        )
    with pytest.raises(DomainValidationError):
        EvidenceRef.from_dict(
            {
                "opaque_id": "ev-syn-1",
                "part_id": bad_id,
                "locator": {
                    "kind": "text_offset",
                    "unit": "codepoints",
                    "start": 0,
                    "end": 1,
                },
            }
        )
    with pytest.raises(DomainValidationError):
        Observation.from_dict(
            {
                "opaque_id": "obs-syn-1",
                "part_id": "part-syn-body",
                "artifact_version_id": "art-syn-001",
                "entity_type": "EMAIL_ADDRESS",
                "evidence_locator": {
                    "kind": "text_offset",
                    "unit": "codepoints",
                    "start": 0,
                    "end": 1,
                },
                "recognizer_version": bad_id,
                "score_kind": "pattern_match",
            }
        )


def test_domain_modules_do_not_import_adapters_or_pipeline() -> None:
    offenders: list[str] = []
    for path in sorted(DOMAIN_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                names = [node.module]
            else:
                continue
            for name in names:
                if any(
                    name == prefix or name.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ):
                    offenders.append(f"{path.name}: {name}")
    assert offenders == []


def test_records_are_immutable() -> None:
    artifact = _artifact()
    with pytest.raises(FrozenInstanceError):
        artifact.opaque_id = "mutated"  # type: ignore[misc]

    part = _text_part(artifact)
    with pytest.raises(FrozenInstanceError):
        part.coverage_state = CoverageState.FAILED  # type: ignore[misc]


def test_round_trip_from_committed_synthetic_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "synthetic_observation_bundle.json"
    bundle = json.loads(fixture_path.read_text(encoding="utf-8"))

    artifact = ArtifactVersion.from_dict(bundle["artifact_version"])
    part = Part.from_dict(bundle["part"])
    observation = Observation.from_dict(bundle["observation"])

    validate_part(part)
    validate_observation(observation, part=part)

    assert to_jsonable(artifact) == bundle["artifact_version"]
    assert to_jsonable(part) == bundle["part"]
    assert to_jsonable(observation) == bundle["observation"]
    assert "maya@" not in fixture_path.read_text(encoding="utf-8")
