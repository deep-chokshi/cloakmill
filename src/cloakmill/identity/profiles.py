"""Coherent synthetic profiles derived under a namespace key.

Profiles hold synthetic attribute values only. They never embed source PII or
source-to-synthetic maps. Mapping snapshots reference profiles by opaque id.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from cloakmill.domain.enums import EntityKind
from cloakmill.domain.errors import DomainValidationError
from cloakmill.domain.fields import require_non_empty_str, require_opaque_id
from cloakmill.domain.mapping import NamespaceKeyRef
from cloakmill.identity.errors import AssignmentError

ASSIGNMENT_POLICY_VERSION = "profile-assign-v1"

# Approved synthetic catalogs (reserved example domains only).
GIVEN_NAMES: tuple[str, ...] = (
    "Avery",
    "Blake",
    "Casey",
    "Drew",
    "Ellis",
    "Finley",
    "Harper",
    "Jordan",
    "Kai",
    "Logan",
    "Morgan",
    "Noah",
    "Parker",
    "Quinn",
    "Riley",
    "Sage",
)
FAMILY_NAMES: tuple[str, ...] = (
    "Alden",
    "Brooks",
    "Carter",
    "Dalton",
    "Ellis",
    "Foster",
    "Griffin",
    "Hayes",
    "Ingram",
    "Jordan",
    "Keller",
    "Larsen",
    "Monroe",
    "Nolan",
    "Owens",
    "Porter",
)
ORG_NAMES: tuple[str, ...] = (
    "Northwind Labs",
    "Cedar River Systems",
    "Blue Harbor Group",
    "Maple Ridge Works",
    "Silver Pine Co",
    "Summit Field Services",
    "Copper Line Analytics",
    "Harbor Light Media",
)
ACCOUNT_LABELS: tuple[str, ...] = (
    "Shared Inbox",
    "Support Desk",
    "Ops Relay",
    "Billing Queue",
    "Facilities Desk",
    "Security Relay",
    "Payroll Desk",
    "Travel Desk",
)

EMAIL_DOMAIN = "profiles.example"
UNIQUE_ATTRS: frozenset[str] = frozenset(
    {"email", "employee_id", "account_id", "organization_name"}
)


@dataclass(frozen=True, slots=True)
class NamespaceKeyMaterial:
    """In-memory namespace key bytes. Never serialized into mapping snapshots."""

    key_ref: NamespaceKeyRef
    key_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.key_ref, NamespaceKeyRef):
            raise AssignmentError("key_ref must be a NamespaceKeyRef")
        if not isinstance(self.key_bytes, (bytes, bytearray)) or len(self.key_bytes) < 16:
            raise AssignmentError("key_bytes must be at least 16 bytes")


@dataclass(frozen=True, slots=True)
class SyntheticProfile:
    """Coherent synthetic replacement profile for one accepted entity."""

    opaque_id: str
    entity_kind: EntityKind
    namespace_id: str
    given_name: str | None = None
    family_name: str | None = None
    full_name: str | None = None
    email: str | None = None
    employee_id: str | None = None
    account_id: str | None = None
    display_name: str | None = None
    organization_name: str | None = None

    def unique_attributes(self) -> dict[str, str]:
        """Return attributes that must be unique within a namespace."""
        attrs: dict[str, str] = {}
        if self.email is not None:
            attrs["email"] = self.email
        if self.employee_id is not None:
            attrs["employee_id"] = self.employee_id
        if self.account_id is not None:
            attrs["account_id"] = self.account_id
        if self.organization_name is not None:
            attrs["organization_name"] = self.organization_name
        return attrs

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opaque_id": self.opaque_id,
            "entity_kind": self.entity_kind.value,
            "namespace_id": self.namespace_id,
        }
        for field_name in (
            "given_name",
            "family_name",
            "full_name",
            "email",
            "employee_id",
            "account_id",
            "display_name",
            "organization_name",
        ):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyntheticProfile:
        if not isinstance(data, dict):
            raise DomainValidationError("synthetic profile must be an object")
        try:
            entity_kind = EntityKind(data["entity_kind"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid synthetic profile kind: {exc}") from exc
        profile = cls(
            opaque_id=data.get("opaque_id", ""),
            entity_kind=entity_kind,
            namespace_id=data.get("namespace_id", ""),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
            full_name=data.get("full_name"),
            email=data.get("email"),
            employee_id=data.get("employee_id"),
            account_id=data.get("account_id"),
            display_name=data.get("display_name"),
            organization_name=data.get("organization_name"),
        )
        validate_synthetic_profile(profile)
        return profile


def validate_synthetic_profile(profile: SyntheticProfile) -> None:
    require_opaque_id(profile.opaque_id, "opaque_id")
    require_opaque_id(profile.namespace_id, "namespace_id")
    if not isinstance(profile.entity_kind, EntityKind):
        raise DomainValidationError("entity_kind must be an EntityKind")

    if profile.entity_kind is EntityKind.PERSON:
        require_non_empty_str(profile.given_name, "given_name")
        require_non_empty_str(profile.family_name, "family_name")
        require_non_empty_str(profile.full_name, "full_name")
        require_non_empty_str(profile.email, "email")
        require_non_empty_str(profile.employee_id, "employee_id")
        expected_full = f"{profile.given_name} {profile.family_name}"
        if profile.full_name != expected_full:
            raise DomainValidationError("full_name must equal given_name + family_name")
        if profile.account_id is not None or profile.organization_name is not None:
            raise DomainValidationError("person profiles must not set account/org fields")
    elif profile.entity_kind is EntityKind.ACCOUNT:
        require_non_empty_str(profile.account_id, "account_id")
        require_non_empty_str(profile.display_name, "display_name")
        require_non_empty_str(profile.email, "email")
        if profile.given_name is not None or profile.family_name is not None:
            raise DomainValidationError("account profiles must not set person name parts")
        if profile.organization_name is not None or profile.employee_id is not None:
            raise DomainValidationError("account profiles must not set org/employee fields")
    elif profile.entity_kind is EntityKind.ORGANIZATION:
        require_non_empty_str(profile.organization_name, "organization_name")
        if any(
            getattr(profile, name) is not None
            for name in (
                "given_name",
                "family_name",
                "full_name",
                "email",
                "employee_id",
                "account_id",
                "display_name",
            )
        ):
            raise DomainValidationError("organization profiles must only set organization_name")
    else:
        raise DomainValidationError(f"unsupported entity_kind: {profile.entity_kind!r}")


def profile_opaque_id(
    *,
    namespace_id: str,
    entity_id: str,
    key_version: str,
    policy_version: str,
) -> str:
    digest = _digest_hex(namespace_id, entity_id, key_version, policy_version)
    return f"prof-{digest}"


def derive_profile_candidate(
    *,
    entity_id: str,
    entity_kind: EntityKind,
    namespace_id: str,
    key_material: NamespaceKeyMaterial,
    policy_version: str,
    attempt: int,
) -> SyntheticProfile:
    """Derive one coherent profile candidate for reservation."""
    if attempt < 0:
        raise AssignmentError("attempt must be non-negative")
    if key_material.key_ref.namespace_id != namespace_id:
        raise AssignmentError("key_material namespace_id does not match assignment namespace")

    opaque_id = profile_opaque_id(
        namespace_id=namespace_id,
        entity_id=entity_id,
        key_version=key_material.key_ref.key_version,
        policy_version=policy_version,
    )
    # Keep profile id stable across collision retries; only attribute values bump.
    seed = _hmac_digest(
        key_material.key_bytes,
        namespace_id,
        entity_id,
        entity_kind.value,
        policy_version,
        str(attempt),
    )

    if entity_kind is EntityKind.PERSON:
        given = _pick(GIVEN_NAMES, seed, salt="given")
        family = _pick(FAMILY_NAMES, seed, salt="family")
        suffix = _hex_suffix(seed, salt="email", length=4)
        email = f"{given.lower()}.{family.lower()}.{suffix}@{EMAIL_DOMAIN}"
        employee_id = f"E-{_hex_suffix(seed, salt='employee', length=6).upper()}"
        profile = SyntheticProfile(
            opaque_id=opaque_id,
            entity_kind=entity_kind,
            namespace_id=namespace_id,
            given_name=given,
            family_name=family,
            full_name=f"{given} {family}",
            email=email,
            employee_id=employee_id,
        )
    elif entity_kind is EntityKind.ACCOUNT:
        label = _pick(ACCOUNT_LABELS, seed, salt="account-label")
        suffix = _hex_suffix(seed, salt="account-email", length=4)
        account_id = f"AC-{_hex_suffix(seed, salt='account-id', length=6).upper()}"
        email = f"{label.lower().replace(' ', '.')}.{suffix}@{EMAIL_DOMAIN}"
        profile = SyntheticProfile(
            opaque_id=opaque_id,
            entity_kind=entity_kind,
            namespace_id=namespace_id,
            account_id=account_id,
            display_name=label,
            email=email,
        )
    elif entity_kind is EntityKind.ORGANIZATION:
        org_name = _pick(ORG_NAMES, seed, salt="org")
        # Collision retries append a stable synthetic discriminator.
        if attempt:
            org_name = f"{org_name} {_hex_suffix(seed, salt='org-bump', length=3).upper()}"
        profile = SyntheticProfile(
            opaque_id=opaque_id,
            entity_kind=entity_kind,
            namespace_id=namespace_id,
            organization_name=org_name,
        )
    else:
        raise AssignmentError(f"unsupported entity_kind for assignment: {entity_kind!r}")

    validate_synthetic_profile(profile)
    return profile


def _pick(catalog: tuple[str, ...], seed: bytes, *, salt: str) -> str:
    index = int.from_bytes(_hmac_digest(seed, salt)[:8], "big") % len(catalog)
    return catalog[index]


def _hex_suffix(seed: bytes, *, salt: str, length: int) -> str:
    return _hmac_digest(seed, salt).hex()[:length]


def _hmac_digest(key: bytes, *parts: str) -> bytes:
    material = "\0".join(parts).encode("utf-8")
    return hmac.new(key, material, hashlib.sha256).digest()


def _digest_hex(*parts: str) -> str:
    material = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]
