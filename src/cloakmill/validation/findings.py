"""Pass/block findings with opaque refs — never embed raw PII snippets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class GateKind(StrEnum):
    """Independent release gate categories."""

    COVERAGE = "coverage"
    PRIVACY = "privacy"
    STRUCTURE = "structure"


class ValidationDecision(StrEnum):
    """Aggregate gate or release decision."""

    PASS = "pass"
    BLOCK = "block"


# Stable finding codes used in reports and tests.
CODE_COVERAGE_GAP = "coverage.gap"
CODE_COVERAGE_STATE_MISMATCH = "coverage.state_mismatch"
CODE_COVERAGE_EXCLUDED_LEAKED = "coverage.excluded_leaked"
CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE = "privacy.residual_known_source"
CODE_PRIVACY_CANARY_DETECTED = "privacy.canary_detected"
CODE_PRIVACY_UNEXPECTED_IDENTIFIER = "privacy.unexpected_identifier"
CODE_STRUCTURE_REPARSE_FAILED = "structure.reparse_failed"
CODE_STRUCTURE_SCHEMA_MISMATCH = "structure.schema_mismatch"
CODE_STRUCTURE_JOIN_MISMATCH = "structure.join_mismatch"


@dataclass(frozen=True, slots=True)
class Finding:
    """One validation finding. Logs and manifests may only use opaque fields."""

    opaque_id: str
    gate: GateKind
    code: str
    artifact_version_id: str | None
    detail_ref: str

    def to_log_record(self) -> dict[str, Any]:
        """Serialize for logs/manifests: opaque ids and codes only."""
        return {
            "opaque_id": self.opaque_id,
            "gate": self.gate.value,
            "code": self.code,
            "artifact_version_id": self.artifact_version_id,
            "detail_ref": self.detail_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.to_log_record()


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of a single gate."""

    gate: GateKind
    decision: ValidationDecision
    findings: tuple[Finding, ...]

    def to_log_record(self) -> dict[str, Any]:
        return {
            "gate": self.gate.value,
            "decision": self.decision.value,
            "finding_count": len(self.findings),
            "finding_ids": [finding.opaque_id for finding in self.findings],
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Independent validation report for a release candidate."""

    decision: ValidationDecision
    validator_version: str
    gates: tuple[GateResult, ...]
    findings: tuple[Finding, ...]

    def to_log_record(self) -> dict[str, Any]:
        """Aggregate, payload-free log record suitable for operational logs."""
        return {
            "decision": self.decision.value,
            "validator_version": self.validator_version,
            "finding_count": len(self.findings),
            "finding_ids": [finding.opaque_id for finding in self.findings],
            "gates": [gate.to_log_record() for gate in self.gates],
        }

    def contains_substring(self, value: str) -> bool:
        """Return True if ``value`` appears anywhere in log-safe serialization."""
        if not value:
            return False
        blob = repr(self.to_log_record())
        for finding in self.findings:
            blob += repr(finding.to_log_record())
        return value in blob
