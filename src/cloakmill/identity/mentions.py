"""Mention evidence and directory anchors supplied to identity resolution.

Observations from detection do not embed matched text. Callers attach the
normalized span value (and optional weak context) here. Identity resolution
never invents replacement profiles.
"""

from __future__ import annotations

from dataclasses import dataclass

from cloakmill.domain.enums import AnchorKind, EntityKind
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_non_empty_str, require_opaque_id

# Detection entity types that act as strong identity anchors.
STRONG_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "email_address",
        "employee_id",
        "account_id",
    }
)

_ENTITY_TYPE_TO_ANCHOR: dict[str, AnchorKind] = {
    "email_address": AnchorKind.EMAIL,
    "employee_id": AnchorKind.EMPLOYEE_ID,
    "account_id": AnchorKind.ACCOUNT_ID,
}

_DEFAULT_KIND_FOR_ANCHOR: dict[AnchorKind, EntityKind] = {
    AnchorKind.EMAIL: EntityKind.PERSON,
    AnchorKind.EMPLOYEE_ID: EntityKind.PERSON,
    AnchorKind.ACCOUNT_ID: EntityKind.ACCOUNT,
}


def anchor_kind_for_entity_type(entity_type: str) -> AnchorKind | None:
    """Return the strong AnchorKind for a detection entity type, if any."""
    return _ENTITY_TYPE_TO_ANCHOR.get(entity_type)


def default_entity_kind_for_anchor(anchor_kind: AnchorKind) -> EntityKind:
    """Default entity kind when no directory override applies."""
    try:
        return _DEFAULT_KIND_FOR_ANCHOR[anchor_kind]
    except KeyError as exc:
        raise DomainValidationError(
            f"anchor kind {anchor_kind!r} is not a strong identity anchor"
        ) from exc


def normalize_anchor_value(anchor_kind: AnchorKind, value: str) -> str:
    """Normalize strong-anchor values for deterministic indexing."""
    require_non_empty_str(value, "normalized_value")
    stripped = value.strip()
    if anchor_kind is AnchorKind.EMAIL:
        return stripped.casefold()
    if anchor_kind in {AnchorKind.EMPLOYEE_ID, AnchorKind.ACCOUNT_ID}:
        return stripped.upper()
    if anchor_kind in {AnchorKind.DISPLAY_NAME, AnchorKind.FIRST_NAME}:
        return " ".join(stripped.casefold().split())
    raise DomainValidationError(f"unsupported anchor kind for normalization: {anchor_kind!r}")


# Anchor kinds whose values are source-local (must be scoped by authority_id).
LOCAL_ANCHOR_KINDS: frozenset[AnchorKind] = frozenset(
    {AnchorKind.EMPLOYEE_ID, AnchorKind.ACCOUNT_ID}
)


@dataclass(frozen=True, slots=True)
class MentionEvidence:
    """One detected mention plus the normalized value used for retrieval.

    ``authority_id`` scopes source-local anchors (employee_id / account_id).
    Emails are treated as globally unique and ignore authority for retrieval.
    """

    observation_id: str
    entity_type: str
    normalized_value: str
    part_id: str
    artifact_version_id: str
    first_name: str | None = None
    display_name: str | None = None
    authority_id: str = "default"

    def strong_anchor(self) -> tuple[AnchorKind, str] | None:
        kind = anchor_kind_for_entity_type(self.entity_type)
        if kind is None:
            return None
        return kind, normalize_anchor_value(kind, self.normalized_value)


def retrieval_key(
    kind: AnchorKind,
    normalized_value: str,
    *,
    authority_id: str,
) -> tuple[str, str, str]:
    """Stable retrieval key for candidate indexing.

    Emails are global (authority ignored). Employee/account ids are scoped to
    ``authority_id`` so dense local identifiers cannot cross-link sources.
    """
    require_non_empty_str(authority_id, "authority_id")
    if kind is AnchorKind.EMAIL:
        return ("*", kind.value, normalized_value)
    if kind in LOCAL_ANCHOR_KINDS:
        return (authority_id, kind.value, normalized_value)
    raise DomainValidationError(f"unsupported retrieval kind: {kind!r}")


@dataclass(frozen=True, slots=True)
class DirectoryAnchor:
    """Authoritative directory entry scoped to a source authority.

    Shared mailboxes and service accounts are ``EntityKind.ACCOUNT`` with
    ``is_shared=True``. Operator person keys are related ownership hints; they
    must never be treated as aliases of the shared account.
    """

    anchor_kind: AnchorKind
    normalized_value: str
    entity_kind: EntityKind
    entity_key: str
    is_shared: bool = False
    operator_person_keys: tuple[str, ...] = ()
    authority_id: str = "default"

    def indexed_value(self) -> str:
        return normalize_anchor_value(self.anchor_kind, self.normalized_value)


def validate_mention_evidence(mention: MentionEvidence) -> None:
    require_opaque_id(mention.observation_id, "observation_id")
    require_non_empty_str(mention.entity_type, "entity_type")
    require_non_empty_str(mention.normalized_value, "normalized_value")
    require_opaque_id(mention.part_id, "part_id")
    require_opaque_id(mention.artifact_version_id, "artifact_version_id")
    require_non_empty_str(mention.authority_id, "authority_id")
    if mention.first_name is not None:
        require_non_empty_str(mention.first_name, "first_name")
    if mention.display_name is not None:
        require_non_empty_str(mention.display_name, "display_name")


def validate_directory_anchor(anchor: DirectoryAnchor) -> None:
    if not isinstance(anchor.anchor_kind, AnchorKind):
        raise DomainValidationError("anchor_kind must be an AnchorKind")
    if anchor.anchor_kind not in {
        AnchorKind.EMAIL,
        AnchorKind.EMPLOYEE_ID,
        AnchorKind.ACCOUNT_ID,
    }:
        raise DomainValidationError(
            f"directory anchors must use a strong kind, got {anchor.anchor_kind!r}"
        )
    if not isinstance(anchor.entity_kind, EntityKind):
        raise DomainValidationError("entity_kind must be an EntityKind")
    require_non_empty_str(anchor.normalized_value, "normalized_value")
    require_opaque_id(anchor.entity_key, "entity_key")
    require_non_empty_str(anchor.authority_id, "authority_id")
    if anchor.is_shared and anchor.entity_kind is not EntityKind.ACCOUNT:
        raise DomainValidationError("shared directory anchors must use EntityKind.ACCOUNT")
    seen: set[str] = set()
    for key in anchor.operator_person_keys:
        require_opaque_id(key, "operator_person_keys[]")
        if key in seen:
            # Do not embed cleartext directory keys in exception text.
            raise DomainValidationError("duplicate operator_person_key in directory anchor")
        seen.add(key)
        if key == anchor.entity_key:
            raise DomainValidationError(
                "operator_person_keys must not include the shared account entity_key"
            )
