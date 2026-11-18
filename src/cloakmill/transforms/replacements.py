"""Private replacement vault: opaque refs resolve to injection-safe strings.

``PatchPlanEntry.replacement_ref`` never embeds the synthetic value. Writers
look up approved values here. The vault must not enter training-data exports.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from cloakmill.domain.fields import require_opaque_id
from cloakmill.identity.profiles import SyntheticProfile
from cloakmill.transforms.errors import TransformError, UnsafeReplacementError
from cloakmill.transforms.safety import assert_safe_replacement

# Entity-type / attribute keys used by the planner when selecting profile fields.
ATTRIBUTE_EMAIL = "email"
ATTRIBUTE_EMPLOYEE_ID = "employee_id"
ATTRIBUTE_ACCOUNT_ID = "account_id"
ATTRIBUTE_FULL_NAME = "full_name"
ATTRIBUTE_GIVEN_NAME = "given_name"
ATTRIBUTE_FAMILY_NAME = "family_name"
ATTRIBUTE_DISPLAY_NAME = "display_name"
ATTRIBUTE_ORGANIZATION_NAME = "organization_name"

ENTITY_TYPE_TO_ATTRIBUTE: dict[str, str] = {
    "email_address": ATTRIBUTE_EMAIL,
    "EMAIL_ADDRESS": ATTRIBUTE_EMAIL,
    "employee_id": ATTRIBUTE_EMPLOYEE_ID,
    "EMPLOYEE_ID": ATTRIBUTE_EMPLOYEE_ID,
    "account_id": ATTRIBUTE_ACCOUNT_ID,
    "ACCOUNT_ID": ATTRIBUTE_ACCOUNT_ID,
}

_PROFILE_ATTR_GETTERS: dict[str, str] = {
    ATTRIBUTE_EMAIL: "email",
    ATTRIBUTE_EMPLOYEE_ID: "employee_id",
    ATTRIBUTE_ACCOUNT_ID: "account_id",
    ATTRIBUTE_FULL_NAME: "full_name",
    ATTRIBUTE_GIVEN_NAME: "given_name",
    ATTRIBUTE_FAMILY_NAME: "family_name",
    ATTRIBUTE_DISPLAY_NAME: "display_name",
    ATTRIBUTE_ORGANIZATION_NAME: "organization_name",
}


@dataclass(frozen=True, slots=True)
class ReplacementVault:
    """Private opaque_ref → safe replacement string mapping for writers."""

    values: MappingProxyType[str, str]

    def get(self, replacement_ref: str) -> str:
        require_opaque_id(replacement_ref, "replacement_ref")
        try:
            return self.values[replacement_ref]
        except KeyError as exc:
            raise TransformError(f"unknown replacement_ref {replacement_ref!r}") from exc

    def __contains__(self, replacement_ref: object) -> bool:
        return isinstance(replacement_ref, str) and replacement_ref in self.values


def attribute_key_for_entity_type(entity_type: str) -> str:
    """Map a detection entity type to a synthetic profile attribute key."""
    try:
        return ENTITY_TYPE_TO_ATTRIBUTE[entity_type]
    except KeyError as exc:
        raise TransformError(
            f"no profile attribute mapping for entity type {entity_type!r}"
        ) from exc


def profile_attribute_value(profile: SyntheticProfile, attribute_key: str) -> str:
    """Resolve one coherent profile attribute and enforce injection safety."""
    field_name = _PROFILE_ATTR_GETTERS.get(attribute_key)
    if field_name is None:
        raise TransformError(f"unsupported attribute_key {attribute_key!r}")
    value = getattr(profile, field_name)
    if value is None:
        raise TransformError(
            f"profile {profile.opaque_id!r} has no value for attribute {attribute_key!r}"
        )
    return assert_safe_replacement(value, field_name=attribute_key)


def mint_replacement_ref(
    *,
    mapping_snapshot_id: str,
    entity_id: str | None,
    attribute_key: str | None,
    action: str,
    inert_token: str | None = None,
) -> str:
    """Deterministically mint an opaque replacement_ref for a vault entry."""
    material = "\0".join(
        [
            mapping_snapshot_id,
            action,
            entity_id or "",
            attribute_key or "",
            inert_token or "",
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
    return f"attr-{digest}"


def build_replacement_vault(entries: Mapping[str, str]) -> ReplacementVault:
    """Validate and freeze a private replacement table."""
    validated: dict[str, str] = {}
    for ref, value in entries.items():
        require_opaque_id(ref, "replacement_ref")
        try:
            validated[ref] = assert_safe_replacement(value, field_name=ref)
        except UnsafeReplacementError:
            raise
    return ReplacementVault(values=MappingProxyType(validated))
