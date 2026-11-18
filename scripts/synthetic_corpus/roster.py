"""Synthetic people, accounts, and ambiguity/ownership scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .constants import (
    AMBIGUOUS_FIRST_NAMES,
    FIRST_NAMES,
    LAST_NAMES,
    ORGANIZATION_NAMES,
    RESERVED_EMAIL_DOMAINS,
)


@dataclass(frozen=True, slots=True)
class Person:
    entity_id: str
    first_name: str
    last_name: str
    email: str
    employee_id: str
    organization: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Account:
    entity_id: str
    account_id: str
    display_name: str
    kind: str  # customer | shared_mailbox | service
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OwnershipPeriod:
    mailbox: str
    owner_entity_id: str
    valid_from: str
    valid_to: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Roster:
    people: tuple[Person, ...]
    accounts: tuple[Account, ...]
    ownership_periods: tuple[OwnershipPeriod, ...]
    shared_mailbox: str
    shared_mailbox_operator_ids: tuple[str, ...]


def _stable_hex(label: str, width: int = 8) -> str:
    return sha256(label.encode("utf-8")).hexdigest()[:width]


def build_roster(*, person_count: int, seed_label: str) -> Roster:
    """Build a deterministic roster sized for the target corpus.

    Includes repeated-mention people, shared-first-name ambiguity clusters,
    a shared mailbox with multiple operators, and an email ownership change.
    """
    if person_count < 24:
        msg = "person_count must be at least 24 to cover ambiguity scenarios"
        raise ValueError(msg)

    people: list[Person] = []
    for index in range(person_count):
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
        # Force ambiguous first-name clusters for the first few dozen people.
        if index < 12:
            first = AMBIGUOUS_FIRST_NAMES[index % len(AMBIGUOUS_FIRST_NAMES)]
            last = LAST_NAMES[index]
        domain = RESERVED_EMAIL_DOMAINS[index % len(RESERVED_EMAIL_DOMAINS)]
        local = f"{first.lower()}.{last.lower()}.{index:04d}"
        email = f"{local}@{domain}"
        org = ORGANIZATION_NAMES[index % len(ORGANIZATION_NAMES)]
        tags: list[str] = ["roster_member"]
        if first in AMBIGUOUS_FIRST_NAMES and index < 12:
            tags.append("shared_first_name")
        people.append(
            Person(
                entity_id=f"entity:person:{index:05d}",
                first_name=first,
                last_name=last,
                email=email,
                employee_id=f"E-{_stable_hex(f'{seed_label}:emp:{index}', 6).upper()}",
                organization=org,
                tags=tuple(tags),
            )
        )

    # Shared mailbox operators (first three ambiguous people).
    operators = tuple(p.entity_id for p in people[:3])
    shared_mailbox = f"support@{RESERVED_EMAIL_DOMAINS[0]}"

    accounts: list[Account] = []
    for index in range(max(8, person_count // 8)):
        owner = people[index % len(people)]
        accounts.append(
            Account(
                entity_id=f"entity:account:{index:05d}",
                account_id=f"AC-{1000 + index}",
                display_name=f"{owner.last_name} Account {index:04d}",
                kind="customer",
                tags=("customer_account",),
            )
        )
    accounts.append(
        Account(
            entity_id="entity:account:shared_support",
            account_id="MBX-SUPPORT",
            display_name="Support Shared Mailbox",
            kind="shared_mailbox",
            tags=("shared_mailbox", "do_not_merge_operators"),
        )
    )

    # Ownership change: a recycled mailbox moves from person 0 to person 10.
    recycled = f"ops.desk@{RESERVED_EMAIL_DOMAINS[1]}"
    ownership_periods = (
        OwnershipPeriod(
            mailbox=recycled,
            owner_entity_id=people[0].entity_id,
            valid_from="2021-01-01",
            valid_to="2023-06-30",
            tags=("ownership_change", "prior_owner"),
        ),
        OwnershipPeriod(
            mailbox=recycled,
            owner_entity_id=people[10].entity_id,
            valid_from="2023-07-01",
            valid_to=None,
            tags=("ownership_change", "current_owner"),
        ),
    )

    return Roster(
        people=tuple(people),
        accounts=tuple(accounts),
        ownership_periods=ownership_periods,
        shared_mailbox=shared_mailbox,
        shared_mailbox_operator_ids=operators,
    )
