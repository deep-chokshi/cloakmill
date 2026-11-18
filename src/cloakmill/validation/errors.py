"""Errors raised by independent release validation."""

from __future__ import annotations


class ValidationError(ValueError):
    """Invalid validation inputs or unsupported candidate surfaces."""


class ValidationInputError(ValidationError):
    """Caller supplied an incomplete or contradictory validation request."""
