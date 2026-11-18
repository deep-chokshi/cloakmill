"""DiscoveryEngine: schedule catalog recognizers and validate observations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.detection.catalog import RecognizerCatalog
from cloakmill.detection.validator import (
    ObservationConflict,
    ObservationValidator,
    RejectedCandidate,
    ValidationResult,
)
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import CoverageState, SurfaceKind
from cloakmill.domain.observations import Observation


@dataclass(frozen=True, slots=True)
class PartInput:
    """In-memory extracted part plus immutable content for rule scanning."""

    part: Part
    content: str
    field_name: str | None = None

    def __post_init__(self) -> None:
        if self.part.content_length is not None and self.part.content_length != len(self.content):
            msg = (
                f"part.content_length ({self.part.content_length}) does not match "
                f"content length ({len(self.content)})"
            )
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PartDiscoveryResult:
    part_id: str
    observations: tuple[Observation, ...]
    rejected: tuple[RejectedCandidate, ...]
    conflicts: tuple[ObservationConflict, ...]
    skipped: bool
    skip_reason: str | None = None
    requires_exception_review: bool = False


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Aggregated discovery output for a batch of parts."""

    parts: tuple[PartDiscoveryResult, ...]

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(obs for part in self.parts for obs in part.observations)

    @property
    def rejected(self) -> tuple[RejectedCandidate, ...]:
        return tuple(item for part in self.parts for item in part.rejected)

    @property
    def conflicts(self) -> tuple[ObservationConflict, ...]:
        return tuple(item for part in self.parts for item in part.conflicts)

    @property
    def requires_exception_review(self) -> bool:
        return any(part.requires_exception_review for part in self.parts)


class DiscoveryEngine:
    """Schedule enabled rule recognizers; never invent replacement values."""

    def __init__(
        self,
        catalog: RecognizerCatalog,
        validator: ObservationValidator | None = None,
    ) -> None:
        self._catalog = catalog
        self._validator = validator if validator is not None else ObservationValidator()

    @property
    def catalog(self) -> RecognizerCatalog:
        return self._catalog

    def discover(
        self,
        parts: Sequence[PartInput],
        *,
        entity_types: frozenset[str] | None = None,
        languages: frozenset[str] | None = None,
    ) -> DiscoveryResult:
        results: list[PartDiscoveryResult] = []
        for part_input in parts:
            results.append(
                self._discover_part(
                    part_input,
                    entity_types=entity_types,
                    languages=languages,
                )
            )
        return DiscoveryResult(parts=tuple(results))

    def _discover_part(
        self,
        part_input: PartInput,
        *,
        entity_types: frozenset[str] | None,
        languages: frozenset[str] | None,
    ) -> PartDiscoveryResult:
        part = part_input.part
        if part.coverage_state is not CoverageState.PROCESSED:
            return PartDiscoveryResult(
                part_id=part.opaque_id,
                observations=(),
                rejected=(),
                conflicts=(),
                skipped=True,
                skip_reason=f"coverage_state={part.coverage_state.value}",
                requires_exception_review=False,
            )

        recognizers = self._catalog.select(
            surface=part.surface_kind,
            entity_types=entity_types,
            languages=languages,
        )
        candidates: list[CandidateObservation] = []
        recognizer_exception_review = False
        for recognizer in recognizers:
            produced = recognizer.recognize(
                part,
                part_input.content,
                field_name=part_input.field_name,
            )
            recognizer_exception_review = (
                recognizer_exception_review or recognizer.exception_review_required()
            )
            for candidate in produced:
                if entity_types is not None and candidate.entity_type not in entity_types:
                    continue
                candidates.append(candidate)

        validation: ValidationResult = self._validator.validate(part, candidates)
        weak_schema = any(
            observation.recognizer_version.startswith("rule.schema_field/")
            and observation.score_value is not None
            and observation.score_value < 1.0
            for observation in validation.accepted
        )
        return PartDiscoveryResult(
            part_id=part.opaque_id,
            observations=validation.accepted,
            rejected=validation.rejected,
            conflicts=validation.conflicts,
            skipped=False,
            requires_exception_review=(
                validation.requires_exception_review or weak_schema or recognizer_exception_review
            ),
        )


def default_field_name(part: Part) -> str | None:
    """Derive a leaf field name from a structured part locator when present."""
    from cloakmill.domain.locators import FieldPathLocator

    if part.surface_kind is not SurfaceKind.STRUCTURED_FIELD:
        return None
    locator = part.original_locator
    if not isinstance(locator, FieldPathLocator) or not locator.path:
        return None
    leaf = locator.path[-1]
    return leaf if isinstance(leaf, str) else None
