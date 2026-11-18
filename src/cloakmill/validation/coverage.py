"""Coverage ledger comparison for release candidates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from cloakmill.domain.enums import CoverageState
from cloakmill.validation.findings import (
    CODE_COVERAGE_EXCLUDED_LEAKED,
    CODE_COVERAGE_GAP,
    CODE_COVERAGE_STATE_MISMATCH,
    Finding,
    GateKind,
)
from cloakmill.validation.ids import finding_opaque_id, identifier_detail_ref, subject_ref_for


@dataclass(frozen=True, slots=True)
class CoverageSurfaceRef:
    """One expected or observed surface in the coverage ledger."""

    opaque_id: str
    artifact_version_id: str
    surface_key: str
    state: CoverageState
    required: bool = True


@dataclass(frozen=True, slots=True)
class CoverageLedger:
    """Declared coverage for a release scope."""

    entries: tuple[CoverageSurfaceRef, ...]

    def by_opaque_id(self) -> dict[str, CoverageSurfaceRef]:
        return {entry.opaque_id: entry for entry in self.entries}


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    """One candidate output artifact presented to validation."""

    artifact_version_id: str
    media_type: str
    payload: bytes
    excluded: bool = False


def compare_coverage(
    *,
    expected: CoverageLedger,
    observed: CoverageLedger,
    candidate_artifacts: Iterable[CandidateArtifact] | None = None,
) -> tuple[Finding, ...]:
    """Compare expected vs observed coverage; emit opaque findings on gaps."""
    findings: list[Finding] = []
    observed_map = observed.by_opaque_id()
    candidates = {
        artifact.artifact_version_id: artifact for artifact in (candidate_artifacts or ())
    }

    for expected_entry in expected.entries:
        observed_entry = observed_map.get(expected_entry.opaque_id)
        subject = subject_ref_for(
            artifact_version_id=expected_entry.artifact_version_id,
            surface_key=expected_entry.surface_key,
        )

        if expected_entry.state is CoverageState.EXCLUDED:
            candidate = candidates.get(expected_entry.artifact_version_id)
            if candidate is not None and not candidate.excluded and candidate.payload:
                findings.append(
                    _finding(
                        code=CODE_COVERAGE_EXCLUDED_LEAKED,
                        subject=subject,
                        artifact_version_id=expected_entry.artifact_version_id,
                        detail_seed=expected_entry.opaque_id,
                    )
                )
            continue

        if not expected_entry.required:
            continue

        if observed_entry is None:
            findings.append(
                _finding(
                    code=CODE_COVERAGE_GAP,
                    subject=subject,
                    artifact_version_id=expected_entry.artifact_version_id,
                    detail_seed=expected_entry.opaque_id,
                )
            )
            continue

        if observed_entry.state is not expected_entry.state:
            findings.append(
                _finding(
                    code=CODE_COVERAGE_STATE_MISMATCH,
                    subject=subject,
                    artifact_version_id=expected_entry.artifact_version_id,
                    detail_seed=f"{expected_entry.opaque_id}:{observed_entry.state.value}",
                )
            )

    return tuple(findings)


def observed_ledger_from_candidates(
    *,
    expected: CoverageLedger,
    candidates: Iterable[CandidateArtifact],
) -> CoverageLedger:
    """Derive an observed ledger for expected surfaces from candidate presence."""
    by_artifact = {item.artifact_version_id: item for item in candidates}
    observed: list[CoverageSurfaceRef] = []
    for entry in expected.entries:
        candidate = by_artifact.get(entry.artifact_version_id)
        if entry.state is CoverageState.EXCLUDED:
            state = CoverageState.EXCLUDED
            if candidate is not None and not candidate.excluded and candidate.payload:
                # Presence of payload will be flagged by compare_coverage.
                state = CoverageState.PROCESSED
            observed.append(
                CoverageSurfaceRef(
                    opaque_id=entry.opaque_id,
                    artifact_version_id=entry.artifact_version_id,
                    surface_key=entry.surface_key,
                    state=state,
                    required=entry.required,
                )
            )
            continue

        if candidate is None:
            continue
        if candidate.excluded:
            state = CoverageState.EXCLUDED
        elif candidate.payload:
            state = CoverageState.PROCESSED
        else:
            state = CoverageState.FAILED
        observed.append(
            CoverageSurfaceRef(
                opaque_id=entry.opaque_id,
                artifact_version_id=entry.artifact_version_id,
                surface_key=entry.surface_key,
                state=state,
                required=entry.required,
            )
        )
    return CoverageLedger(entries=tuple(observed))


def _finding(
    *,
    code: str,
    subject: str,
    artifact_version_id: str,
    detail_seed: str,
) -> Finding:
    return Finding(
        opaque_id=finding_opaque_id(gate=GateKind.COVERAGE.value, code=code, subject_ref=subject),
        gate=GateKind.COVERAGE,
        code=code,
        artifact_version_id=artifact_version_id,
        detail_ref=identifier_detail_ref(detail_seed),
    )
