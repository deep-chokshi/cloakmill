"""Shared field validators for opaque ids and non-empty strings."""

from __future__ import annotations

import re

from cloakmill.domain.errors import DomainValidationError

_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def require_opaque_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID_RE.fullmatch(value):
        raise DomainValidationError(
            f"{field_name} must be a non-empty opaque id matching {_OPAQUE_ID_RE.pattern}"
        )
    return value


def require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise DomainValidationError(f"{field_name} must be a non-empty string")
    return value


def require_version_token(value: object, field_name: str) -> str:
    """Non-empty version string with no ASCII control characters (incl. NUL)."""
    require_non_empty_str(value, field_name)
    assert isinstance(value, str)
    if any(ord(ch) < 32 for ch in value):
        raise DomainValidationError(f"{field_name} must not contain control characters")
    return value


def length_prefixed_utf8(*parts: str) -> bytes:
    """Injective length-prefixed UTF-8 encoding of string parts."""
    out = bytearray()
    for part in parts:
        if not isinstance(part, str):
            raise DomainValidationError("commitment parts must be strings")
        encoded = part.encode("utf-8")
        out.extend(len(encoded).to_bytes(4, "big"))
        out.extend(encoded)
    return bytes(out)
