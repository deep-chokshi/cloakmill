"""Shared regex patterns and checksum helpers for rule recognizers."""

from __future__ import annotations

import re

# Practical email pattern; reserved .example domains in fixtures.
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9._%+-])"
)

# Synthetic employee ids: E- followed by 6 hex characters (see eval corpora).
EMPLOYEE_ID_RE = re.compile(r"(?<![A-Za-z0-9-])E-[0-9A-Fa-f]{6}(?![A-Za-z0-9-])")

# Synthetic account ids: AC- followed by digits (see identity-preview / corpora).
ACCOUNT_ID_RE = re.compile(r"(?<![A-Za-z0-9-])AC-\d{3,8}(?![A-Za-z0-9-])")

# Candidate payment-card digit runs (13-19 digits, optional separators).
PAYMENT_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

SCHEMA_FIELD_ALIASES: dict[str, str] = {
    "email": "email_address",
    "email_address": "email_address",
    "owner_email": "email_address",
    "employee_id": "employee_id",
    "emp_id": "employee_id",
    "account_id": "account_id",
    "account": "account_id",
    "payment_card": "payment_card",
    "card_number": "payment_card",
    "credit_card": "payment_card",
}


def luhn_ok(digits: str) -> bool:
    """Return True when ``digits`` (0-9 only) passes the Luhn checksum."""
    if len(digits) < 13 or len(digits) > 19 or not digits.isdigit():
        return False
    total = 0
    reverse = digits[::-1]
    for index, char in enumerate(reverse):
        value = ord(char) - 48
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())
