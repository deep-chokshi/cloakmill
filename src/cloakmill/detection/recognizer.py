"""Rule recognizer interface for CloakMill-owned detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from cloakmill.detection.candidates import CandidateObservation
from cloakmill.domain.artifacts import Part
from cloakmill.domain.enums import ScoreKind, SurfaceKind


@dataclass(frozen=True, slots=True)
class RecognizerCapability:
    """Versioned capability descriptor registered in the recognizer catalog."""

    recognizer_id: str
    version: str
    entity_types: frozenset[str]
    score_kind: ScoreKind
    surfaces: frozenset[SurfaceKind]
    languages: frozenset[str] = frozenset({"*"})

    @property
    def recognizer_version(self) -> str:
        """Stable ``<id>/<version>`` tag persisted on observations."""
        return f"{self.recognizer_id}/{self.version}"


class RuleRecognizer(ABC):
    """Deterministic recognizer that emits exact evidence spans.

    Implementations must not invent replacement values, call hosted models, or
    import Presidio. LLM/NER adapters are out of scope for F05.
    """

    @property
    @abstractmethod
    def capability(self) -> RecognizerCapability:
        """Describe entity types, surfaces, and version for catalog scheduling."""

    @abstractmethod
    def recognize(
        self,
        part: Part,
        content: str,
        *,
        field_name: str | None = None,
    ) -> Sequence[CandidateObservation]:
        """Scan ``content`` for this part and return exact-span candidates.

        ``field_name`` is the leaf structured-field name when known (for schema
        hints). Locators must refer to the immutable content coordinate system.
        """

    def exception_review_required(self) -> bool:
        """True when the last ``recognize`` pass left unresolved sensitive material.

        Default is false. Checksum recognizers may set this when card-length
        digit runs remain uncovered after Luhn window search.
        """
        return False
