"""Shared records, source locators, evidence, and transformation contracts."""

from cloakmill.domain.artifacts import (
    ArtifactVersion,
    NormalizationSpan,
    Part,
    validate_artifact_version,
    validate_part,
)
from cloakmill.domain.enums import (
    CoverageState,
    LocatorKind,
    ScoreKind,
    SurfaceKind,
    TextOffsetUnit,
)
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.locators import (
    FieldPathLocator,
    OriginalLocator,
    TextOffsetLocator,
    locator_from_dict,
    validate_field_path_locator,
    validate_locator,
    validate_text_offset_locator,
)
from cloakmill.domain.observations import (
    EvidenceRef,
    Observation,
    validate_evidence_ref,
    validate_observation,
)
from cloakmill.domain.serialize import dumps, from_jsonable, loads, loads_locator, to_jsonable

__all__ = [
    "ArtifactVersion",
    "CoverageState",
    "DomainValidationError",
    "EvidenceRef",
    "FieldPathLocator",
    "LocatorKind",
    "NormalizationSpan",
    "Observation",
    "OriginalLocator",
    "Part",
    "ScoreKind",
    "SurfaceKind",
    "TextOffsetLocator",
    "TextOffsetUnit",
    "dumps",
    "from_jsonable",
    "loads",
    "loads_locator",
    "locator_from_dict",
    "to_jsonable",
    "validate_artifact_version",
    "validate_evidence_ref",
    "validate_field_path_locator",
    "validate_locator",
    "validate_observation",
    "validate_part",
    "validate_text_offset_locator",
]
