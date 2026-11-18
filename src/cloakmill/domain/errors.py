"""Domain contract validation errors."""

from __future__ import annotations


class DomainValidationError(ValueError):
    """Raised when a domain record or locator fails contract validation."""
