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
