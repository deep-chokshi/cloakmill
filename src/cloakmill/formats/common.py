"""Shared helpers for format extractors."""

from __future__ import annotations

import hashlib
import re

# F08 writers cannot rename object keys / CSV headers. Only schema-shaped names
# are admitted so person-keyed documents fail closed instead of leaking PII.
_SCHEMA_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def part_id_for(artifact_version_id: str, kind: str, index: int) -> str:
    """Stable opaque part id derived from artifact id, kind, and ordinal."""
    material = f"{artifact_version_id}:{kind}:{index}".encode()
    digest = hashlib.sha256(material).hexdigest()[:20]
    return f"part-{digest}"


def is_schema_safe_key(key: str) -> bool:
    """Return True when ``key`` is a schema identifier (not person-keyed content)."""
    return isinstance(key, str) and bool(_SCHEMA_KEY_RE.fullmatch(key))
