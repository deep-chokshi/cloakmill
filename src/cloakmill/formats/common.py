"""Shared helpers for format extractors."""

from __future__ import annotations

import hashlib
import re

# F08 writers cannot rename object keys / CSV headers. Until connectors supply a
# schema, only this explicit allow-list is admitted so person-keyed documents
# (usernames, name slugs, IDs) fail closed instead of leaking PII.
_SCHEMA_KEY_SHAPE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED_SCHEMA_KEYS = frozenset(
    {
        # Structural / document shape
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
        "ticket",
        "tickets",
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
        "blob",
        "phone",
        "email",
        # Common schema field names used by synthetic fixtures / writers
        "owner_email",
        "owner_id",
        "watcher_id",
        "assignee_email",
        "employee_id",
        "account_id",
        "full_name",
        "given_name",
        "family_name",
        "display_name",
        "organization_name",
        "email_address",
    }
)


def part_id_for(artifact_version_id: str, kind: str, index: int) -> str:
    """Stable opaque part id derived from artifact id, kind, and ordinal."""
    material = f"{artifact_version_id}:{kind}:{index}".encode()
    digest = hashlib.sha256(material).hexdigest()[:20]
    return f"part-{digest}"


def is_schema_safe_key(key: str) -> bool:
    """Return True when ``key`` is an allow-listed schema identifier."""
    if not isinstance(key, str) or not key:
        return False
    if not _SCHEMA_KEY_SHAPE_RE.fullmatch(key):
        return False
    return key in _ALLOWED_SCHEMA_KEYS
