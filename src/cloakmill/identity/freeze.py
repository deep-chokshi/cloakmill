"""Freeze API for immutable mapping snapshots and private profile vaults."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from cloakmill.domain.mapping import (
    EntityGraphVersion,
    MappingAssignment,
    MappingSnapshot,
    mapping_snapshots_equal,
    validate_mapping_snapshot,
)
from cloakmill.identity.assignment import MappingAssignmentDraft, build_mapping_snapshot
from cloakmill.identity.errors import AssignmentError, FrozenMappingError
from cloakmill.identity.profiles import SyntheticProfile, validate_synthetic_profile


@dataclass(frozen=True, slots=True)
class FrozenMappingBundle:
    """Immutable sealed mapping snapshot plus private synthetic profile vault.

    Snapshot assignments are opaque entity→profile bindings only. Synthetic
    attribute values live in ``profiles`` and must not enter release exports.
    """

    snapshot: MappingSnapshot
    graph_version: EntityGraphVersion
    profiles: tuple[SyntheticProfile, ...]

    def __post_init__(self) -> None:
        validate_mapping_snapshot(self.snapshot)
        profile_ids = {profile.opaque_id for profile in self.profiles}
        if len(profile_ids) != len(self.profiles):
            raise AssignmentError("frozen bundle contains duplicate profile ids")
        assigned_profiles = {item.profile_id for item in self.snapshot.assignments}
        if assigned_profiles != profile_ids:
            raise AssignmentError("frozen bundle profiles must match snapshot assignments")
        for profile in self.profiles:
            validate_synthetic_profile(profile)
            if profile.namespace_id != self.snapshot.namespace_id:
                raise AssignmentError("profile namespace_id must match snapshot namespace_id")
        if self.graph_version.opaque_id != self.snapshot.entity_graph_version_id:
            raise AssignmentError("graph_version id must match snapshot entity_graph_version_id")
        if self.graph_version.namespace_id != self.snapshot.namespace_id:
            raise AssignmentError("graph_version namespace_id must match snapshot namespace_id")

    @property
    def assignments(self) -> tuple[MappingAssignment, ...]:
        return self.snapshot.assignments

    def profile_by_id(self) -> MappingProxyType[str, SyntheticProfile]:
        return MappingProxyType({profile.opaque_id: profile for profile in self.profiles})

    def profile_for_entity(self, entity_id: str) -> SyntheticProfile:
        for assignment in self.snapshot.assignments:
            if assignment.entity_id == entity_id:
                return self.profile_by_id()[assignment.profile_id]
        raise AssignmentError(f"no frozen assignment for entity {entity_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "graph_version": self.graph_version.to_dict(),
            "profiles": [profile.to_dict() for profile in self.profiles],
        }


def freeze_mapping(draft: MappingAssignmentDraft) -> FrozenMappingBundle:
    """Seal an assignment draft into an immutable frozen mapping bundle."""
    if not isinstance(draft, MappingAssignmentDraft):
        raise AssignmentError("freeze_mapping requires a MappingAssignmentDraft")
    snapshot = build_mapping_snapshot(draft)
    return FrozenMappingBundle(
        snapshot=snapshot,
        graph_version=draft.graph_version,
        profiles=draft.profiles,
    )


class FrozenMappingStore:
    """In-memory store that rejects conflicting writes to a frozen snapshot id."""

    def __init__(self) -> None:
        self._by_snapshot_id: dict[str, FrozenMappingBundle] = {}

    def put(self, bundle: FrozenMappingBundle) -> FrozenMappingBundle:
        """Persist a frozen bundle. Idempotent for equal content; rejects mutation."""
        if not isinstance(bundle, FrozenMappingBundle):
            raise FrozenMappingError("store only accepts FrozenMappingBundle")
        existing = self._by_snapshot_id.get(bundle.snapshot.opaque_id)
        if existing is not None:
            if not frozen_bundles_equal(existing, bundle):
                raise FrozenMappingError(
                    f"frozen snapshot {bundle.snapshot.opaque_id!r} is immutable"
                )
            return existing
        self._by_snapshot_id[bundle.snapshot.opaque_id] = bundle
        return bundle

    def get(self, snapshot_id: str) -> FrozenMappingBundle:
        try:
            return self._by_snapshot_id[snapshot_id]
        except KeyError as exc:
            raise AssignmentError(f"unknown frozen snapshot {snapshot_id!r}") from exc

    def __contains__(self, snapshot_id: str) -> bool:
        return snapshot_id in self._by_snapshot_id


def assert_frozen_immutable(bundle: FrozenMappingBundle) -> None:
    """Behavioral guard: frozen dataclasses and mapping proxies reject mutation."""
    if not isinstance(bundle, FrozenMappingBundle):
        raise FrozenMappingError("bundle must be a FrozenMappingBundle")
    try:
        bundle.profiles = ()  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise FrozenMappingError("FrozenMappingBundle accepted attribute mutation")

    try:
        bundle.snapshot.assignments = ()  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise FrozenMappingError("MappingSnapshot accepted attribute mutation")

    proxy = bundle.profile_by_id()
    if not isinstance(proxy, MappingProxyType):
        raise FrozenMappingError("profile_by_id must return a MappingProxyType")
    try:
        # Value must not depend on profiles[0] — empty graphs are valid.
        proxy["tamper"] = None  # type: ignore[index]
    except TypeError:
        return
    raise FrozenMappingError("profile map accepted mutation")


def frozen_bundles_equal(left: FrozenMappingBundle, right: FrozenMappingBundle) -> bool:
    """Structural equality for freeze/replay checks (profile order ignored)."""
    if not mapping_snapshots_equal(left.snapshot, right.snapshot):
        return False
    if left.graph_version != right.graph_version:
        return False
    left_profiles = {profile.opaque_id: profile.to_dict() for profile in left.profiles}
    right_profiles = {profile.opaque_id: profile.to_dict() for profile in right.profiles}
    return left_profiles == right_profiles
