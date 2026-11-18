"""Canonical entity type strings for CloakMill-owned rule recognizers."""

from __future__ import annotations

# Align string values with synthetic eval corpora / identity resolution.
EMAIL_ADDRESS = "email_address"
EMPLOYEE_ID = "employee_id"
ACCOUNT_ID = "account_id"
PAYMENT_CARD = "payment_card"

KNOWN_RULE_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        EMAIL_ADDRESS,
        EMPLOYEE_ID,
        ACCOUNT_ID,
        PAYMENT_CARD,
    }
)
