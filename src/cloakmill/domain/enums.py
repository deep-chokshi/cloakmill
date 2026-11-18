"""Shared enumerations for domain contracts."""

from __future__ import annotations

from enum import StrEnum


class CoverageState(StrEnum):
    """Coverage ledger state for an expected artifact surface or part."""

    PROCESSED = "processed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    EXCLUDED = "excluded"


class SurfaceKind(StrEnum):
    """Extracted part surface kinds supported by early offline ingest."""

    TEXT = "text"
    STRUCTURED_FIELD = "structured_field"


class TextOffsetUnit(StrEnum):
    """Unit system for text offset locators. Normalized text never replaces these."""

    CODEPOINTS = "codepoints"
    UTF8_BYTES = "utf8_bytes"
    UTF16_CODE_UNITS = "utf16_code_units"


class ScoreKind(StrEnum):
    """Provenance kind for an observation score. Do not average unlike kinds."""

    PATTERN_MATCH = "pattern_match"
    CHECKSUM = "checksum"
    SCHEMA = "schema"
    DIRECTORY = "directory"
    MODEL = "model"
    MANUAL = "manual"


class LocatorKind(StrEnum):
    """Original locator kinds in scope for F01 domain contracts."""

    TEXT_OFFSET = "text_offset"
    FIELD_PATH = "field_path"


class EntityKind(StrEnum):
    """Canonical entity kinds kept distinct during identity resolution."""

    PERSON = "person"
    ACCOUNT = "account"
    ORGANIZATION = "organization"


class DecisionOutcome(StrEnum):
    """Identity decision outcomes: accept, keep separate, or send to review."""

    ACCEPT = "accept"
    SEPARATE = "separate"
    REVIEW = "review"


class AnchorKind(StrEnum):
    """Anchor kinds used for candidate retrieval and merge policy."""

    EMAIL = "email"
    EMPLOYEE_ID = "employee_id"
    ACCOUNT_ID = "account_id"
    DISPLAY_NAME = "display_name"
    FIRST_NAME = "first_name"
