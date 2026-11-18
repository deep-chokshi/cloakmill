"""Coverage ledger / report for offline ingest (release-facing serialization)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from cloakmill.connectors.admission import AdmissionDisposition, AdmissionReason
from cloakmill.connectors.inventory import InventoryEntry
from cloakmill.domain.enums import CoverageState


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    """Per-artifact coverage row without absolute filesystem paths or digests."""

    opaque_id: str
    relative_package_path: str
    coverage_state: CoverageState
    disposition: AdmissionDisposition
    reason: AdmissionReason
    media_type: str | None = None
    byte_size: int | None = None

    def to_dict(self, *, include_package_path: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "coverage_state": self.coverage_state.value,
            "disposition": self.disposition.value,
            "reason": self.reason.value,
        }
        if include_package_path:
            payload["relative_package_path"] = self.relative_package_path
        if self.media_type is not None:
            payload["media_type"] = self.media_type
        if self.byte_size is not None:
            payload["byte_size"] = self.byte_size
        return payload


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Aggregate coverage ledger suitable for operator / release-facing views."""

    schema_version: str
    access_scope: str
    totals: dict[str, int]
    entries: tuple[CoverageEntry, ...]

    def to_dict(self, *, include_package_path: bool = True) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "totals": dict(self.totals),
            "entries": [
                entry.to_dict(include_package_path=include_package_path) for entry in self.entries
            ],
        }


COVERAGE_REPORT_SCHEMA_VERSION = "cloakmill.coverage.v1"


def build_coverage_report(
    inventory: tuple[InventoryEntry, ...],
    *,
    access_scope: str,
) -> CoverageReport:
    entries = tuple(
        CoverageEntry(
            opaque_id=item.opaque_id,
            relative_package_path=item.relative_package_path,
            coverage_state=item.coverage_state,
            disposition=item.disposition,
            reason=item.reason,
            media_type=item.media_type,
            byte_size=item.byte_size,
        )
        for item in inventory
    )
    counter: Counter[str] = Counter(entry.coverage_state.value for entry in entries)
    totals = {
        CoverageState.PROCESSED.value: counter.get(CoverageState.PROCESSED.value, 0),
        CoverageState.UNAVAILABLE.value: counter.get(CoverageState.UNAVAILABLE.value, 0),
        CoverageState.FAILED.value: counter.get(CoverageState.FAILED.value, 0),
        CoverageState.EXCLUDED.value: counter.get(CoverageState.EXCLUDED.value, 0),
    }
    return CoverageReport(
        schema_version=COVERAGE_REPORT_SCHEMA_VERSION,
        access_scope=access_scope,
        totals=totals,
        entries=entries,
    )
