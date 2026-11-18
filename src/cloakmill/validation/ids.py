"""Opaque finding identifiers (metadata only; never hash source PII unkeyed)."""

from __future__ import annotations

import hashlib


def finding_opaque_id(*, gate: str, code: str, subject_ref: str) -> str:
    """Deterministic opaque finding id from non-sensitive gate metadata."""
    digest = _meta_digest(gate, code, subject_ref)
    return f"finding-{digest}"


def subject_ref_for(*, artifact_version_id: str, surface_key: str = "") -> str:
    """Build a subject ref from opaque artifact ids and non-sensitive keys."""
    if surface_key:
        return f"{artifact_version_id}:{surface_key}"
    return artifact_version_id


def identifier_detail_ref(opaque_identifier_id: str) -> str:
    """Opaque detail pointer for a known-source or canary identity."""
    digest = _meta_digest("id-ref", opaque_identifier_id)
    return f"detail-{digest}"


def _meta_digest(*parts: str) -> str:
    material = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]
