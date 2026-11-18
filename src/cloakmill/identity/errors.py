"""Errors raised by profile assignment and mapping freeze."""

from __future__ import annotations

from cloakmill.domain.errors import DomainValidationError


class AssignmentError(DomainValidationError):
    """Raised when namespace-scoped profile assignment cannot complete safely."""


class FrozenMappingError(AssignmentError):
    """Raised when a caller attempts to mutate a frozen mapping snapshot."""


class CollisionExhaustedError(AssignmentError):
    """Raised when unique attribute reservation cannot find a free candidate."""
