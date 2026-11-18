"""Schema and referential join integrity checks for candidate outputs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from cloakmill.formats import extract_parts_for_media_type
from cloakmill.validation.coverage import CandidateArtifact
from cloakmill.validation.findings import (
    CODE_STRUCTURE_JOIN_MISMATCH,
    CODE_STRUCTURE_REPARSE_FAILED,
    CODE_STRUCTURE_SCHEMA_MISMATCH,
    Finding,
    GateKind,
)
from cloakmill.validation.ids import finding_opaque_id, identifier_detail_ref, subject_ref_for
from cloakmill.validation.surfaces import field_paths_for_artifact, read_field_value


@dataclass(frozen=True, slots=True)
class SchemaExpectation:
    """Expected field paths for one structured candidate artifact."""

    artifact_version_id: str
    field_paths: frozenset[tuple[str | int, ...]]


@dataclass(frozen=True, slots=True)
class JoinExpectation:
    """Referential join that must hold across candidate artifacts."""

    opaque_id: str
    left_artifact_version_id: str
    left_path: tuple[str | int, ...]
    right_artifact_version_id: str
    right_path: tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class StructureContext:
    """Schema and join expectations for the structure gate."""

    schemas: tuple[SchemaExpectation, ...] = ()
    joins: tuple[JoinExpectation, ...] = ()


def check_structure(
    *,
    candidates: Iterable[CandidateArtifact],
    context: StructureContext,
) -> tuple[Finding, ...]:
    """Reparse candidates; verify schemas and joins independently of writers."""
    findings: list[Finding] = []
    by_id = {item.artifact_version_id: item for item in candidates}

    for artifact in by_id.values():
        if artifact.excluded:
            continue
        reparse = extract_parts_for_media_type(
            artifact_version_id=artifact.artifact_version_id,
            media_type=artifact.media_type,
            payload=artifact.payload,
        )
        if not reparse.ok:
            subject = subject_ref_for(artifact_version_id=artifact.artifact_version_id)
            findings.append(
                Finding(
                    opaque_id=finding_opaque_id(
                        gate=GateKind.STRUCTURE.value,
                        code=CODE_STRUCTURE_REPARSE_FAILED,
                        subject_ref=subject,
                    ),
                    gate=GateKind.STRUCTURE,
                    code=CODE_STRUCTURE_REPARSE_FAILED,
                    artifact_version_id=artifact.artifact_version_id,
                    detail_ref=identifier_detail_ref(
                        f"{artifact.artifact_version_id}:{reparse.error or 'reparse'}"
                    ),
                )
            )

    for schema in context.schemas:
        artifact = by_id.get(schema.artifact_version_id)
        if artifact is None or artifact.excluded:
            subject = subject_ref_for(artifact_version_id=schema.artifact_version_id)
            findings.append(
                Finding(
                    opaque_id=finding_opaque_id(
                        gate=GateKind.STRUCTURE.value,
                        code=CODE_STRUCTURE_SCHEMA_MISMATCH,
                        subject_ref=subject,
                    ),
                    gate=GateKind.STRUCTURE,
                    code=CODE_STRUCTURE_SCHEMA_MISMATCH,
                    artifact_version_id=schema.artifact_version_id,
                    detail_ref=identifier_detail_ref(f"missing:{schema.artifact_version_id}"),
                )
            )
            continue
        actual_paths = field_paths_for_artifact(artifact)
        if actual_paths != schema.field_paths:
            subject = subject_ref_for(artifact_version_id=schema.artifact_version_id)
            findings.append(
                Finding(
                    opaque_id=finding_opaque_id(
                        gate=GateKind.STRUCTURE.value,
                        code=CODE_STRUCTURE_SCHEMA_MISMATCH,
                        subject_ref=subject,
                    ),
                    gate=GateKind.STRUCTURE,
                    code=CODE_STRUCTURE_SCHEMA_MISMATCH,
                    artifact_version_id=schema.artifact_version_id,
                    detail_ref=identifier_detail_ref(f"schema:{schema.artifact_version_id}"),
                )
            )

    for join in context.joins:
        left = by_id.get(join.left_artifact_version_id)
        right = by_id.get(join.right_artifact_version_id)
        left_value = read_field_value(left, join.left_path) if left is not None else None
        right_value = read_field_value(right, join.right_path) if right is not None else None
        if left_value is None or right_value is None or left_value != right_value:
            subject = subject_ref_for(
                artifact_version_id=join.left_artifact_version_id,
                surface_key=join.opaque_id,
            )
            findings.append(
                Finding(
                    opaque_id=finding_opaque_id(
                        gate=GateKind.STRUCTURE.value,
                        code=CODE_STRUCTURE_JOIN_MISMATCH,
                        subject_ref=subject,
                    ),
                    gate=GateKind.STRUCTURE,
                    code=CODE_STRUCTURE_JOIN_MISMATCH,
                    artifact_version_id=join.left_artifact_version_id,
                    detail_ref=identifier_detail_ref(join.opaque_id),
                )
            )

    return tuple(findings)
