"""Errors for deterministic patch planning and structured writers."""

from __future__ import annotations


class TransformError(ValueError):
    """Base error for transform planning and writing failures."""


class PatchConflictError(TransformError):
    """Raised when patch candidates overlap or disagree at the same locator."""


class UnsafeReplacementError(TransformError):
    """Raised when a replacement string fails injection-safety checks."""


class WriterError(TransformError):
    """Raised when a format writer cannot apply an approved patch plan."""
