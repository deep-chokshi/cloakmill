"""Shared helpers for format extractors."""

from __future__ import annotations

import hashlib
import re

# F08 writers cannot rename object keys / CSV headers. Only schema-shaped names
# are admitted so person-keyed documents fail closed instead of leaking PII.
#
# Shape rules (no connector schema yet):
# - lowercase snake_case with at least one underscore, or
# - a short token from the structural allow-list below.
# Uppercase, camelCase, bare usernames, and separator-free IDs are rejected.
_SCHEMA_SNAKE_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
_ALLOWED_SHORT_SCHEMA_KEYS = frozenset(
    {
        "id",
        "ok",
        "key",
        "rows",
        "items",
        "data",
        "meta",
        "type",
        "name",
        "text",
        "body",
        "role",
        "org",
        "user",
        "email",
        "phone",
        "ticket",
        "value",
        "status",
        "count",
        "total",
        "index",
        "label",
        "title",
        "person",
        "source",
        "records",
        "contacts",
        "owner",
        "payload",
        "content",
        "message",
        "account",
        "username",
    }
)


def part_id_for(artifact_version_id: str, kind: str, index: int) -> str:
    """Stable opaque part id derived from artifact id, kind, and ordinal."""
    material = f"{artifact_version_id}:{kind}:{index}".encode()
    digest = hashlib.sha256(material).hexdigest()[:20]
    return f"part-{digest}"


def is_schema_safe_key(key: str) -> bool:
    """Return True when ``key`` is a schema identifier (not person-keyed content)."""
    if not isinstance(key, str) or not key:
        return False
    if "_" in key:
        return bool(_SCHEMA_SNAKE_KEY_RE.fullmatch(key))
    return key in _ALLOWED_SHORT_SCHEMA_KEYS
