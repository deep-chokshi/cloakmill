"""Customer / project / recipient namespace scoping for profile assignment."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cloakmill.domain.fields import require_opaque_id
from cloakmill.identity.errors import AssignmentError


@dataclass(frozen=True, slots=True)
class NamespaceScope:
    """Assignment scope: customer, project, and intended recipient.

    Distinct scopes produce distinct ``namespace_id`` values so synthetic
    profiles do not unintentionally link across recipients or projects.
    """

    customer_id: str
    project_id: str
    recipient_id: str

    @property
    def namespace_id(self) -> str:
        material = "\0".join((self.customer_id, self.project_id, self.recipient_id))
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        return f"ns-{digest}"

    def to_dict(self) -> dict[str, str]:
        return {
            "customer_id": self.customer_id,
            "project_id": self.project_id,
            "recipient_id": self.recipient_id,
            "namespace_id": self.namespace_id,
        }


def validate_namespace_scope(scope: NamespaceScope) -> None:
    require_opaque_id(scope.customer_id, "customer_id")
    require_opaque_id(scope.project_id, "project_id")
    require_opaque_id(scope.recipient_id, "recipient_id")
    require_opaque_id(scope.namespace_id, "namespace_id")


def require_matching_namespace(*, expected: str, actual: str, field_name: str) -> None:
    require_opaque_id(expected, "expected namespace_id")
    require_opaque_id(actual, field_name)
    if actual != expected:
        raise AssignmentError(f"{field_name} {actual!r} does not match namespace {expected!r}")
