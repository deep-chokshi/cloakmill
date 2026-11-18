"""Canonical identities, temporal aliases, and versioned synthetic profiles.

F06 implements strong-anchor identity resolution and grouped exceptions.
Profile assignment and frozen mapping snapshots belong to later features.
"""

from cloakmill.domain.enums import AnchorKind, DecisionOutcome, EntityKind
from cloakmill.identity.graph import (
    AcceptedEntity,
    AcceptedEntityGraph,
    ContradictionConstraint,
    ExceptionGroup,
    IdentityDecision,
    PrivateAnchorIndex,
    StrongAnchor,
    accepted_entity_graphs_equal,
    validate_accepted_entity,
    validate_accepted_entity_graph,
)
from cloakmill.identity.ids import (
    MIN_NAMESPACE_SECRET_LENGTH,
    entity_opaque_id,
    opaque_anchor_ref,
    opaque_directory_entity_ref,
    opaque_weak_signal_ref,
    require_namespace_secret,
)
from cloakmill.identity.mentions import (
    STRONG_ENTITY_TYPES,
    DirectoryAnchor,
    MentionEvidence,
    anchor_kind_for_entity_type,
    normalize_anchor_value,
    validate_directory_anchor,
    validate_mention_evidence,
)
from cloakmill.identity.metrics import ResolutionMetrics, score_wrong_merges
from cloakmill.identity.policy import POLICY_VERSION
from cloakmill.identity.resolver import ResolutionResult, StrongAnchorIdentityResolver

__all__ = [
    "MIN_NAMESPACE_SECRET_LENGTH",
    "POLICY_VERSION",
    "STRONG_ENTITY_TYPES",
    "AcceptedEntity",
    "AcceptedEntityGraph",
    "AnchorKind",
    "ContradictionConstraint",
    "DecisionOutcome",
    "DirectoryAnchor",
    "EntityKind",
    "ExceptionGroup",
    "IdentityDecision",
    "MentionEvidence",
    "PrivateAnchorIndex",
    "ResolutionMetrics",
    "ResolutionResult",
    "StrongAnchor",
    "StrongAnchorIdentityResolver",
    "accepted_entity_graphs_equal",
    "anchor_kind_for_entity_type",
    "entity_opaque_id",
    "normalize_anchor_value",
    "opaque_anchor_ref",
    "opaque_directory_entity_ref",
    "opaque_weak_signal_ref",
    "require_namespace_secret",
    "score_wrong_merges",
    "validate_accepted_entity",
    "validate_accepted_entity_graph",
    "validate_directory_anchor",
    "validate_mention_evidence",
]
