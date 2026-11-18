"""Inventory records produced by local-folder admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloakmill.connectors.admission import AdmissionDisposition, AdmissionReason
from cloakmill.domain.enums import CoverageState


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    """One inventoried package path after admission.

    Uses a relative package locator only. Absolute filesystem paths must never
    be stored on this record or emitted by ``to_dict``.
    """

    opaque_id: str
    relative_package_path: str
    disposition: AdmissionDisposition
    reason: AdmissionReason
    coverage_state: CoverageState
    media_type: str | None = None
    byte_size: int | None = None
    private_integrity_digest: str | None = None

    def to_dict(self, *, include_private_digest: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "relative_package_path": self.relative_package_path,
            "disposition": self.disposition.value,
            "reason": self.reason.value,
            "coverage_state": self.coverage_state.value,
        }
        if self.media_type is not None:
            payload["media_type"] = self.media_type
        if self.byte_size is not None:
            payload["byte_size"] = self.byte_size
        if include_private_digest and self.private_integrity_digest is not None:
            payload["private_integrity_digest"] = self.private_integrity_digest
        return payload
