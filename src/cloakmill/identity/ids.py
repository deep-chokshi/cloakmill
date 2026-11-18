"""Deterministic opaque ids for identity graph records and decisions.

Entity and anchor identifiers that incorporate source values MUST use a keyed
HMAC under a per-namespace secret held inside the private boundary. Unkeyed
digests of emails / employee ids / account ids are invertible and forbidden.
"""

from __future__ import annotations

import hashlib
import hmac

from cloakmill.domain.enums import AnchorKind, EntityKind
from cloakmill.domain.errors import DomainValidationError

# Minimum secret length for namespace-scoped HMAC material (private boundary only).
MIN_NAMESPACE_SECRET_LENGTH = 16


def require_namespace_secret(secret: object) -> bytes:
    """Validate private-boundary HMAC key material (never log or serialize)."""
    if not isinstance(secret, bytes | bytearray):
        raise DomainValidationError("namespace_secret must be bytes")
    material = bytes(secret)
    if len(material) < MIN_NAMESPACE_SECRET_LENGTH:
        raise DomainValidationError(
            f"namespace_secret must be at least {MIN_NAMESPACE_SECRET_LENGTH} bytes"
        )
    return material


def keyed_digest(namespace_secret: bytes, *parts: str) -> str:
    """HMAC-SHA256 hex digest (32 chars) over NUL-joined parts."""
    secret = require_namespace_secret(namespace_secret)
    mac = hmac.new(secret, "\0".join(parts).encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()[:32]


def opaque_anchor_ref(
    *,
    kind: AnchorKind,
    normalized_value: str,
    namespace_secret: bytes,
) -> str:
    """Opaque keyed reference for a strong or weak anchor value."""
    digest = keyed_digest(
        namespace_secret,
        "anchor",
        kind.value,
        normalized_value,
    )
    return f"aref-{kind.value}-{digest}"


def opaque_weak_signal_ref(
    *,
    kind: AnchorKind,
    normalized_value: str,
    namespace_secret: bytes,
) -> str:
    """Opaque keyed reference for a weak signal (first/display name)."""
    digest = keyed_digest(
        namespace_secret,
        "weak",
        kind.value,
        normalized_value,
    )
    return f"wref-{kind.value}-{digest}"


def entity_opaque_id(
    *,
    entity_kind: EntityKind,
    seed_anchor_kind: AnchorKind,
    seed_value: str,
    namespace_id: str,
    namespace_secret: bytes,
) -> str:
    """Opaque entity id via keyed HMAC over the seed anchor (not unkeyed SHA-256)."""
    digest = keyed_digest(
        namespace_secret,
        "entity",
        namespace_id,
        entity_kind.value,
        seed_anchor_kind.value,
        seed_value,
    )
    return f"ent-{entity_kind.value}-{digest}"


def decision_opaque_id(
    *,
    outcome: str,
    rule_id: str,
    observation_ids: tuple[str, ...],
) -> str:
    material = ",".join(sorted(observation_ids))
    digest = _unkeyed_meta_digest(outcome, rule_id, material)
    return f"dec-{digest}"


def exception_opaque_id(*, reason_code: str, observation_ids: tuple[str, ...]) -> str:
    material = ",".join(sorted(observation_ids))
    digest = _unkeyed_meta_digest(reason_code, material)
    return f"exc-{digest}"


def contradiction_opaque_id(*, left_key: str, right_key: str, reason_code: str) -> str:
    ordered = tuple(sorted((left_key, right_key)))
    digest = _unkeyed_meta_digest(reason_code, ordered[0], ordered[1])
    return f"ctr-{digest}"


def graph_opaque_id(*, namespace_id: str, graph_version: str, entity_ids: tuple[str, ...]) -> str:
    material = ",".join(entity_ids)
    digest = _unkeyed_meta_digest(namespace_id, graph_version, material)
    return f"graph-{digest}"


def _unkeyed_meta_digest(*parts: str) -> str:
    """Unkeyed digest over non-sensitive metadata only (opaque ids, rule names)."""
    material = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]
