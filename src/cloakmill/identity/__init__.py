"""Canonical identities, temporal aliases, and versioned synthetic profiles.

F03 exposes type-only mapping and policy snapshot shapes here. Assignment
algorithms, persistence, and key management live in later features.
"""

from cloakmill.domain.enums import PolicyAction
from cloakmill.domain.mapping import (
    EntityGraphVersion,
    MappingAssignment,
    MappingSnapshot,
    NamespaceKeyRef,
    PatchPlanEntry,
    entity_graph_versions_equal,
    mapping_snapshots_equal,
    validate_entity_graph_version,
    validate_mapping_snapshot,
    validate_namespace_key_ref,
    validate_patch_plan_entry,
)

__all__ = [
    "EntityGraphVersion",
    "MappingAssignment",
    "MappingSnapshot",
    "NamespaceKeyRef",
    "PatchPlanEntry",
    "PolicyAction",
    "entity_graph_versions_equal",
    "mapping_snapshots_equal",
    "validate_entity_graph_version",
    "validate_mapping_snapshot",
    "validate_namespace_key_ref",
    "validate_patch_plan_entry",
]
