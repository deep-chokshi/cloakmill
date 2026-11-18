"""Versioned registry of CloakMill-owned recognizers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from cloakmill.detection.recognizer import RecognizerCapability, RuleRecognizer
from cloakmill.domain.enums import SurfaceKind
from cloakmill.domain.errors import DomainValidationError


class RecognizerCatalog:
    """Validated, ordered catalog of rule recognizers.

    Rule packs are explicit registrations. Arbitrary plugin loading is out of
    scope; callers construct recognizers in code and register them here.
    """

    def __init__(self, recognizers: Sequence[RuleRecognizer] = ()) -> None:
        self._by_id: dict[str, RuleRecognizer] = {}
        self._order: list[str] = []
        for recognizer in recognizers:
            self.register(recognizer)

    def register(self, recognizer: RuleRecognizer) -> None:
        capability = recognizer.capability
        _validate_capability(capability)
        if capability.recognizer_id in self._by_id:
            raise DomainValidationError(
                f"duplicate recognizer_id {capability.recognizer_id!r} in catalog"
            )
        self._by_id[capability.recognizer_id] = recognizer
        self._order.append(capability.recognizer_id)

    def get(self, recognizer_id: str) -> RuleRecognizer:
        try:
            return self._by_id[recognizer_id]
        except KeyError as exc:
            raise DomainValidationError(f"unknown recognizer_id {recognizer_id!r}") from exc

    def capabilities(self) -> tuple[RecognizerCapability, ...]:
        return tuple(self._by_id[rid].capability for rid in self._order)

    def select(
        self,
        *,
        surface: SurfaceKind | None = None,
        entity_types: frozenset[str] | None = None,
        languages: frozenset[str] | None = None,
    ) -> tuple[RuleRecognizer, ...]:
        """Return enabled recognizers in registration order for the given filters."""
        selected: list[RuleRecognizer] = []
        for recognizer_id in self._order:
            recognizer = self._by_id[recognizer_id]
            capability = recognizer.capability
            if surface is not None and surface not in capability.surfaces:
                continue
            if entity_types is not None and capability.entity_types.isdisjoint(entity_types):
                continue
            if languages is not None and not _language_match(capability.languages, languages):
                continue
            selected.append(recognizer)
        return tuple(selected)

    def __iter__(self) -> Iterable[RuleRecognizer]:
        return (self._by_id[rid] for rid in self._order)

    def __len__(self) -> int:
        return len(self._order)


def _validate_capability(capability: RecognizerCapability) -> None:
    if not capability.recognizer_id.strip():
        raise DomainValidationError("recognizer_id must be a non-empty string")
    if not capability.version.strip():
        raise DomainValidationError("recognizer version must be a non-empty string")
    if not capability.entity_types:
        raise DomainValidationError("recognizer must declare at least one entity_type")
    if not capability.surfaces:
        raise DomainValidationError("recognizer must declare at least one surface")
    if not capability.languages:
        raise DomainValidationError("recognizer must declare at least one language tag")


def _language_match(supported: frozenset[str], requested: frozenset[str]) -> bool:
    if "*" in supported or "*" in requested:
        return True
    return not supported.isdisjoint(requested)
