"""Orchestrate independent coverage, privacy, and structure release gates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from cloakmill.detection.engine import DiscoveryEngine
from cloakmill.validation.coverage import (
    CandidateArtifact,
    CoverageLedger,
    compare_coverage,
    observed_ledger_from_candidates,
    require_unique_artifact_ids,
    verify_observed_ledger,
)
from cloakmill.validation.findings import (
    Finding,
    GateKind,
    GateResult,
    ValidationDecision,
    ValidationReport,
)
from cloakmill.validation.privacy import PrivacyContext, check_privacy
from cloakmill.validation.structure import StructureContext, check_structure

VALIDATOR_VERSION = "validation-gates-v1"


@dataclass(frozen=True, slots=True)
class ReleaseCandidate:
    """Candidate dataset presented to independent validation.

    ``observed_coverage``, when provided, is verified against a ledger derived
    from candidate artifacts. Divergent caller-supplied ledgers cannot vacate
    coverage gates.
    """

    artifacts: tuple[CandidateArtifact, ...]
    expected_coverage: CoverageLedger
    observed_coverage: CoverageLedger | None = None


def validate_release_candidate(
    *,
    candidate: ReleaseCandidate,
    privacy: PrivacyContext,
    structure: StructureContext | None = None,
    engine: DiscoveryEngine | None = None,
) -> ValidationReport:
    """Run coverage, privacy, and structure gates; return pass/block report.

    Validation rejects writer output independently: privacy uses a separate
    discovery engine instance, structure reparses bytes, and coverage is always
    derived from candidate artifacts (caller-supplied ledgers are verified).
    """
    structure_ctx = structure if structure is not None else StructureContext()
    # Reject duplicate artifact ids before any gate can collapse them away.
    artifacts = require_unique_artifact_ids(candidate.artifacts)
    derived = observed_ledger_from_candidates(
        expected=candidate.expected_coverage,
        candidates=artifacts,
    )
    tamper_findings: tuple[Finding, ...] = ()
    if candidate.observed_coverage is not None:
        tamper_findings = verify_observed_ledger(
            claimed=candidate.observed_coverage,
            derived=derived,
        )
    # Always compare against the derived ledger, never a writer-supplied one alone.
    coverage_findings = compare_coverage(
        expected=candidate.expected_coverage,
        observed=derived,
        candidate_artifacts=artifacts,
    )
    coverage_findings = (*tamper_findings, *coverage_findings)

    privacy_findings = check_privacy(
        candidates=artifacts,
        context=privacy,
        engine=engine,
    )
    structure_findings = check_structure(
        candidates=artifacts,
        context=structure_ctx,
    )

    gates = (
        _gate_result(GateKind.COVERAGE, coverage_findings),
        _gate_result(GateKind.PRIVACY, privacy_findings),
        _gate_result(GateKind.STRUCTURE, structure_findings),
    )
    findings = tuple(finding for gate in gates for finding in gate.findings)
    decision = (
        ValidationDecision.PASS
        if all(gate.decision is ValidationDecision.PASS for gate in gates)
        else ValidationDecision.BLOCK
    )
    return ValidationReport(
        decision=decision,
        validator_version=VALIDATOR_VERSION,
        gates=gates,
        findings=findings,
    )


def sensitive_values_for_leak_checks(
    *,
    privacy: PrivacyContext,
    extra: Iterable[str] = (),
) -> frozenset[str]:
    """Collect private-boundary strings that must never appear in log records."""
    values = {item.normalized_value for item in privacy.known_sources if item.normalized_value}
    values.update(item.token for item in privacy.canaries if item.token)
    values.update(value for value in extra if value)
    return frozenset(values)


def assert_report_has_no_sensitive_leak(
    report: ValidationReport,
    sensitive_values: Iterable[str],
) -> None:
    """Raise AssertionError if any sensitive value appears in log-safe output."""
    for value in sensitive_values:
        if value and report.contains_substring(value):
            raise AssertionError("validation report log record leaked a sensitive value")


def _gate_result(gate: GateKind, findings: tuple[Finding, ...]) -> GateResult:
    decision = ValidationDecision.BLOCK if findings else ValidationDecision.PASS
    return GateResult(gate=gate, decision=decision, findings=findings)
