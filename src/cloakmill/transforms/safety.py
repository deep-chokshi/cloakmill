"""Injection-safety checks for synthetic and inert replacement strings.

Writers must never emit executable code, SQL, spreadsheet formulas, or template
instructions as replacements. Profiles from approved catalogs are already safe;
this module rejects adversarial inert tokens and any vault values that violate
the contract before patches are applied.
"""

from __future__ import annotations

import re

from cloakmill.transforms.errors import UnsafeReplacementError

# Spreadsheet / CSV formula markers (including tab/CR prefixes used by some tools).
_FORMULA_PREFIX_RE = re.compile(r"^[\t\r\n ]*[=+\-@]")

# Executable / template / SQL-shaped payloads that must never appear as replacements.
_UNSAFE_SUBSTRING_RE = re.compile(
    r"(?is)"
    r"(?:<script\b|javascript:|data:text/html|"
    r"\{\{|\}\}|\$\{|<%|%>|"
    r"\b(?:drop|delete|insert|update|alter|exec|execute|union)\b\s+"
    r"(?:table|from|into|set|database|schema|sleep)\b|"
    r";\s*(?:drop|delete|insert|update|alter|exec)\b|"
    r"--\s|/\*|\*/)"
)

_NULL_BYTE = "\x00"

# Conservative max length for a single replacement leaf/span.
_MAX_REPLACEMENT_CHARS = 512


def assert_safe_replacement(value: str, *, field_name: str = "replacement") -> str:
    """Return ``value`` when safe; raise ``UnsafeReplacementError`` otherwise."""
    if not isinstance(value, str):
        raise UnsafeReplacementError(f"{field_name} must be a string")
    if value == "":
        # Empty string is allowed only for REMOVE actions, not REPLACE/INERT vaults.
        raise UnsafeReplacementError(f"{field_name} must be non-empty")
    if _NULL_BYTE in value:
        raise UnsafeReplacementError(f"{field_name} must not contain NUL bytes")
    if len(value) > _MAX_REPLACEMENT_CHARS:
        raise UnsafeReplacementError(
            f"{field_name} exceeds maximum length of {_MAX_REPLACEMENT_CHARS}"
        )
    if _FORMULA_PREFIX_RE.search(value):
        raise UnsafeReplacementError(
            f"{field_name} must not start with a spreadsheet formula marker"
        )
    if _UNSAFE_SUBSTRING_RE.search(value):
        raise UnsafeReplacementError(
            f"{field_name} contains forbidden executable/SQL/template content"
        )
    return value
