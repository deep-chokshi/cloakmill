"""CloakMill-owned detection orchestration (no Presidio dependency)."""

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.catalog import RecognizerCatalog
from cloakmill.detection.engine import (
    DiscoveryEngine,
    DiscoveryResult,
    PartDiscoveryResult,
    PartInput,
    default_field_name,
)
from cloakmill.detection.entity_types import (
    ACCOUNT_ID,
    EMAIL_ADDRESS,
    EMPLOYEE_ID,
    KNOWN_RULE_ENTITY_TYPES,
    PAYMENT_CARD,
)
from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.detection.recognizers import build_default_catalog
from cloakmill.detection.validator import (
    ObservationConflict,
    ObservationValidator,
    RejectedCandidate,
    RejectionReason,
    ValidationResult,
)

__all__ = [
    "ACCOUNT_ID",
    "EMAIL_ADDRESS",
    "EMPLOYEE_ID",
    "KNOWN_RULE_ENTITY_TYPES",
    "PAYMENT_CARD",
    "CandidateObservation",
    "DiscoveryEngine",
    "DiscoveryResult",
    "ObservationConflict",
    "ObservationValidator",
    "PartDiscoveryResult",
    "PartInput",
    "RecognizerCapability",
    "RecognizerCatalog",
    "RejectedCandidate",
    "RejectionReason",
    "RuleRecognizer",
    "ValidationResult",
    "build_default_catalog",
    "default_field_name",
]
