"""Privacy, coverage, and structural release validation (independent of writers)."""

from cloakmill.validation.coverage import (
    CandidateArtifact,
    CoverageLedger,
    CoverageSurfaceRef,
    compare_coverage,
    observed_ledger_from_candidates,
)
from cloakmill.validation.errors import ValidationError, ValidationInputError
from cloakmill.validation.findings import (
    CODE_COVERAGE_EXCLUDED_LEAKED,
    CODE_COVERAGE_GAP,
    CODE_COVERAGE_STATE_MISMATCH,
    CODE_PRIVACY_CANARY_DETECTED,
    CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE,
    CODE_PRIVACY_UNEXPECTED_IDENTIFIER,
    CODE_STRUCTURE_JOIN_MISMATCH,
    CODE_STRUCTURE_REPARSE_FAILED,
    CODE_STRUCTURE_SCHEMA_MISMATCH,
    Finding,
    GateKind,
    GateResult,
    ValidationDecision,
    ValidationReport,
)
from cloakmill.validation.gates import (
    VALIDATOR_VERSION,
    ReleaseCandidate,
    assert_report_has_no_sensitive_leak,
    sensitive_values_for_leak_checks,
    validate_release_candidate,
)
from cloakmill.validation.privacy import (
    KnownSourceIdentifier,
    PrivacyContext,
    SeededCanary,
    check_privacy,
)
from cloakmill.validation.structure import (
    JoinExpectation,
    SchemaExpectation,
    StructureContext,
    check_structure,
)

__all__ = [
    "CODE_COVERAGE_EXCLUDED_LEAKED",
    "CODE_COVERAGE_GAP",
    "CODE_COVERAGE_STATE_MISMATCH",
    "CODE_PRIVACY_CANARY_DETECTED",
    "CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE",
    "CODE_PRIVACY_UNEXPECTED_IDENTIFIER",
    "CODE_STRUCTURE_JOIN_MISMATCH",
    "CODE_STRUCTURE_REPARSE_FAILED",
    "CODE_STRUCTURE_SCHEMA_MISMATCH",
    "VALIDATOR_VERSION",
    "CandidateArtifact",
    "CoverageLedger",
    "CoverageSurfaceRef",
    "Finding",
    "GateKind",
    "GateResult",
    "JoinExpectation",
    "KnownSourceIdentifier",
    "PrivacyContext",
    "ReleaseCandidate",
    "SchemaExpectation",
    "SeededCanary",
    "StructureContext",
    "ValidationDecision",
    "ValidationError",
    "ValidationInputError",
    "ValidationReport",
    "assert_report_has_no_sensitive_leak",
    "check_privacy",
    "check_structure",
    "compare_coverage",
    "observed_ledger_from_candidates",
    "sensitive_values_for_leak_checks",
    "validate_release_candidate",
]
