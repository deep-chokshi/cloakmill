"""Transactional reservation of unique synthetic attributes within a namespace."""

from __future__ import annotations

from dataclasses import dataclass, field

from cloakmill.identity.errors import AssignmentError
from cloakmill.identity.profiles import UNIQUE_ATTRS, SyntheticProfile


@dataclass(slots=True)
class _ReservationState:
    """Mutable reservation map for one namespace: (attr_kind, value) → entity_id."""

    owners: dict[tuple[str, str], str] = field(default_factory=dict)


class AttributeReservationRegistry:
    """In-memory uniqueness registry used during a single assignment pass.

    Reservations are namespace-scoped. Callers seed prior entity→profile bindings
    so incremental runs cannot collide with already-issued unique attributes.
    """

    def __init__(self) -> None:
        self._by_namespace: dict[str, _ReservationState] = {}

    def seed_entity_profile(
        self,
        *,
        namespace_id: str,
        entity_id: str,
        profile: SyntheticProfile,
    ) -> None:
        """Register prior unique attributes owned by ``entity_id``."""
        if profile.namespace_id != namespace_id:
            raise AssignmentError(
                f"profile {profile.opaque_id!r} namespace does not match {namespace_id!r}"
            )
        state = self._by_namespace.setdefault(namespace_id, _ReservationState())
        for attr_kind, value in profile.unique_attributes().items():
            key = (attr_kind, value)
            existing = state.owners.get(key)
            if existing is not None and existing != entity_id:
                raise AssignmentError(
                    f"conflicting prior reservation for {attr_kind}={value!r}: "
                    f"owned by {existing!r}, seeding {entity_id!r}"
                )
            state.owners[key] = entity_id

    def try_reserve_profile(
        self,
        *,
        namespace_id: str,
        entity_id: str,
        profile: SyntheticProfile,
    ) -> bool:
        """Attempt to reserve all unique attrs. Return False on collision."""
        state = self._by_namespace.setdefault(namespace_id, _ReservationState())
        pending: list[tuple[str, str]] = []
        for attr_kind, value in profile.unique_attributes().items():
            if attr_kind not in UNIQUE_ATTRS:
                raise AssignmentError(f"attribute {attr_kind!r} is not a unique attr")
            key = (attr_kind, value)
            owner = state.owners.get(key)
            if owner is not None and owner != entity_id:
                return False
            pending.append(key)
        for key in pending:
            state.owners[key] = entity_id
        return True
