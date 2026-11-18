"""Independent privacy gate: rule scan, known-source checks, seeded canaries."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from cloakmill.detection.engine import DiscoveryEngine, PartInput
from cloakmill.detection.recognizers import build_default_catalog
from cloakmill.domain.locators import TextOffsetLocator
from cloakmill.validation.coverage import CandidateArtifact
from cloakmill.validation.findings import (
    CODE_PRIVACY_CANARY_DETECTED,
    CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE,
    CODE_PRIVACY_UNEXPECTED_IDENTIFIER,
    Finding,
    GateKind,
)
from cloakmill.validation.ids import finding_opaque_id, identifier_detail_ref, subject_ref_for
from cloakmill.validation.surfaces import (
    CandidateSurface,
    iter_candidate_surfaces,
    slice_observation_text,
)


@dataclass(frozen=True, slots=True)
class KnownSourceIdentifier:
    """Private-boundary known source identifier used only for residual checks.

    Never log or serialize ``normalized_value``. Findings reference ``opaque_id``.
    """

    opaque_id: str
    normalized_value: str
    kind: str

    def __repr__(self) -> str:
        return f"KnownSourceIdentifier(opaque_id={self.opaque_id!r}, kind={self.kind!r})"


@dataclass(frozen=True, slots=True)
class SeededCanary:
    """Seeded canary token that must not appear in candidate outputs."""

    opaque_id: str
    token: str

    def __repr__(self) -> str:
        return f"SeededCanary(opaque_id={self.opaque_id!r})"


@dataclass(frozen=True, slots=True)
class PrivacyContext:
    """Private-boundary inputs for the privacy gate."""

    known_sources: tuple[KnownSourceIdentifier, ...]
    canaries: tuple[SeededCanary, ...] = ()
    allowed_synthetics: frozenset[str] = frozenset()

    def __repr__(self) -> str:
        return (
            "PrivacyContext("
            f"known_source_ids={tuple(item.opaque_id for item in self.known_sources)!r}, "
            f"canary_ids={tuple(item.opaque_id for item in self.canaries)!r}, "
            f"allowed_synthetic_count={len(self.allowed_synthetics)})"
        )


def check_privacy(
    *,
    candidates: Iterable[CandidateArtifact],
    context: PrivacyContext,
    engine: DiscoveryEngine | None = None,
) -> tuple[Finding, ...]:
    """Run independent residual, canary, and unexpected-identifier checks."""
    findings: list[Finding] = []
    discovery = engine if engine is not None else DiscoveryEngine(build_default_catalog())
    known_by_value = {item.normalized_value: item for item in context.known_sources}
    canary_by_token = {item.token: item for item in context.canaries}
    allowed = context.allowed_synthetics

    for artifact in candidates:
        if artifact.excluded:
            continue
        payload_text = _decode_payload(artifact.payload)

        # Direct known-source and canary scans over the full payload.
        findings.extend(
            _scan_literals(
                artifact_version_id=artifact.artifact_version_id,
                haystack=payload_text,
                known_by_value=known_by_value,
                canary_by_token=canary_by_token,
            )
        )

        surfaces = iter_candidate_surfaces(artifact)
        findings.extend(
            _independent_rule_scan(
                surfaces=surfaces,
                discovery=discovery,
                known_by_value=known_by_value,
                canary_by_token=canary_by_token,
                allowed=allowed,
            )
        )

    return _dedupe_findings(findings)


def _independent_rule_scan(
    *,
    surfaces: tuple[CandidateSurface, ...],
    discovery: DiscoveryEngine,
    known_by_value: dict[str, KnownSourceIdentifier],
    canary_by_token: dict[str, SeededCanary],
    allowed: frozenset[str],
) -> list[Finding]:
    """Scan with a separate DiscoveryEngine instance (not the writer path)."""
    findings: list[Finding] = []
    part_inputs = [
        PartInput(part=surface.part, content=surface.content, field_name=surface.field_name)
        for surface in surfaces
    ]
    if not part_inputs:
        return findings

    content_by_part = {surface.part.opaque_id: surface.content for surface in surfaces}
    result = discovery.discover(part_inputs)
    for observation in result.observations:
        content = content_by_part.get(observation.part_id, "")
        locator = observation.evidence_locator
        if isinstance(locator, TextOffsetLocator):
            matched = slice_observation_text(content, locator.start, locator.end)
        else:
            matched = content
        if not matched:
            continue
        if matched in known_by_value:
            source = known_by_value[matched]
            findings.append(
                _privacy_finding(
                    code=CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE,
                    artifact_version_id=observation.artifact_version_id,
                    detail_seed=source.opaque_id,
                    subject_extra=source.opaque_id,
                )
            )
            continue
        if matched in canary_by_token:
            canary = canary_by_token[matched]
            findings.append(
                _privacy_finding(
                    code=CODE_PRIVACY_CANARY_DETECTED,
                    artifact_version_id=observation.artifact_version_id,
                    detail_seed=canary.opaque_id,
                    subject_extra=canary.opaque_id,
                )
            )
            continue
        if matched not in allowed:
            findings.append(
                _privacy_finding(
                    code=CODE_PRIVACY_UNEXPECTED_IDENTIFIER,
                    artifact_version_id=observation.artifact_version_id,
                    detail_seed=f"{observation.entity_type}:{observation.opaque_id}",
                    subject_extra=observation.opaque_id,
                )
            )
    return findings


def _scan_literals(
    *,
    artifact_version_id: str,
    haystack: str,
    known_by_value: dict[str, KnownSourceIdentifier],
    canary_by_token: dict[str, SeededCanary],
) -> list[Finding]:
    findings: list[Finding] = []
    for value, source in known_by_value.items():
        if value and value in haystack:
            findings.append(
                _privacy_finding(
                    code=CODE_PRIVACY_RESIDUAL_KNOWN_SOURCE,
                    artifact_version_id=artifact_version_id,
                    detail_seed=source.opaque_id,
                    subject_extra=source.opaque_id,
                )
            )
    for token, canary in canary_by_token.items():
        if token and token in haystack:
            findings.append(
                _privacy_finding(
                    code=CODE_PRIVACY_CANARY_DETECTED,
                    artifact_version_id=artifact_version_id,
                    detail_seed=canary.opaque_id,
                    subject_extra=canary.opaque_id,
                )
            )
    return findings


def _privacy_finding(
    *,
    code: str,
    artifact_version_id: str,
    detail_seed: str,
    subject_extra: str,
) -> Finding:
    subject = subject_ref_for(
        artifact_version_id=artifact_version_id,
        surface_key=subject_extra,
    )
    return Finding(
        opaque_id=finding_opaque_id(gate=GateKind.PRIVACY.value, code=code, subject_ref=subject),
        gate=GateKind.PRIVACY,
        code=code,
        artifact_version_id=artifact_version_id,
        detail_ref=identifier_detail_ref(detail_seed),
    )


def _decode_payload(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        # Binary-safe fallback: search latin-1 round-trip without raising.
        return payload.decode("latin-1")


def _dedupe_findings(findings: list[Finding]) -> tuple[Finding, ...]:
    seen: set[str] = set()
    ordered: list[Finding] = []
    for finding in findings:
        if finding.opaque_id in seen:
            continue
        seen.add(finding.opaque_id)
        ordered.append(finding)
    return tuple(ordered)
