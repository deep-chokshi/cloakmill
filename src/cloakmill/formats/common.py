"""Shared helpers for format extractors."""

from __future__ import annotations

import hashlib


def part_id_for(artifact_version_id: str, kind: str, index: int) -> str:
    """Stable opaque part id derived from artifact id, kind, and ordinal."""
    material = f"{artifact_version_id}:{kind}:{index}".encode()
    digest = hashlib.sha256(material).hexdigest()[:20]
    return f"part-{digest}"
