"""Local-folder ingest orchestration: admit, extract, inventory, coverage."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cloakmill.connectors.admission import (
    AdmissionDisposition,
    AdmissionLimits,
    AdmissionReason,
)
from cloakmill.connectors.inventory import InventoryEntry
from cloakmill.connectors.local_folder import AdmittedPayload, scan_local_folder
from cloakmill.domain.artifacts import ArtifactVersion, Part
from cloakmill.domain.enums import CoverageState
from cloakmill.formats.extract import extract_parts_for_media_type
from cloakmill.pipeline.coverage import CoverageReport, build_coverage_report


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of a local-folder ingest.

    ``admitted_payloads`` is process-private and must not be serialized into
    release-facing structures. Use ``to_release_facing_dict`` for exports.
    """

    access_scope: str
    inventory: tuple[InventoryEntry, ...]
    coverage: CoverageReport
    artifacts: tuple[ArtifactVersion, ...]
    parts: tuple[Part, ...]
    admitted_payloads: tuple[AdmittedPayload, ...]

    def to_release_facing_dict(self) -> dict[str, Any]:
        """Serialize inventory summary + coverage without digests or payloads."""
        return {
            "access_scope": self.access_scope,
            "inventory": [entry.to_dict(include_private_digest=False) for entry in self.inventory],
            "coverage": self.coverage.to_dict(),
            "artifact_ids": [artifact.opaque_id for artifact in self.artifacts],
            "part_ids": [part.opaque_id for part in self.parts],
        }

    def release_facing_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_release_facing_dict(), indent=indent, sort_keys=True)


def _replace_inventory_entry(
    inventory: Sequence[InventoryEntry],
    opaque_id: str,
    *,
    disposition: AdmissionDisposition,
    reason: AdmissionReason,
    coverage_state: CoverageState,
) -> tuple[InventoryEntry, ...]:
    updated: list[InventoryEntry] = []
    for entry in inventory:
        if entry.opaque_id != opaque_id:
            updated.append(entry)
            continue
        updated.append(
            InventoryEntry(
                opaque_id=entry.opaque_id,
                relative_package_path=entry.relative_package_path,
                disposition=disposition,
                reason=reason,
                coverage_state=coverage_state,
                media_type=entry.media_type,
                byte_size=entry.byte_size,
                private_integrity_digest=entry.private_integrity_digest,
            )
        )
    return tuple(updated)


def ingest_local_folder(
    root: Path | str,
    *,
    access_scope: str = "project:local-ingest",
    limits: AdmissionLimits | None = None,
    exclusions: Iterable[str] = (),
) -> IngestResult:
    """Admit a selected local folder and extract JSON/CSV/text parts.

    Absolute filesystem paths remain process-local to the scan and never appear
    in ``IngestResult.to_release_facing_dict``.
    """
    limits = limits or AdmissionLimits()
    scan = scan_local_folder(
        root,
        limits=limits,
        exclusions=exclusions,
        access_scope=access_scope,
    )

    inventory = list(scan.inventory)
    artifacts: list[ArtifactVersion] = []
    parts: list[Part] = []
    kept_payloads: list[AdmittedPayload] = []

    for payload in scan.admitted:
        extract = extract_parts_for_media_type(
            artifact_version_id=payload.opaque_id,
            media_type=payload.media_type,
            payload=payload.payload,
        )
        if not extract.ok:
            inventory_tuple = _replace_inventory_entry(
                inventory,
                payload.opaque_id,
                disposition=AdmissionDisposition.QUARANTINED,
                reason=AdmissionReason.PARSE_FAILED,
                coverage_state=CoverageState.FAILED,
            )
            inventory = list(inventory_tuple)
            continue

        artifact = ArtifactVersion(
            opaque_id=payload.opaque_id,
            source_version=f"local:{payload.relative_package_path}",
            private_integrity_digest=payload.digest,
            access_scope=access_scope,
            media_type=payload.media_type,
        )
        artifacts.append(artifact)
        parts.extend(extract.parts)
        kept_payloads.append(payload)

    inventory_tuple = tuple(sorted(inventory, key=lambda item: item.relative_package_path))
    coverage = build_coverage_report(inventory_tuple, access_scope=access_scope)
    return IngestResult(
        access_scope=access_scope,
        inventory=inventory_tuple,
        coverage=coverage,
        artifacts=tuple(artifacts),
        parts=tuple(parts),
        admitted_payloads=tuple(kept_payloads),
    )
