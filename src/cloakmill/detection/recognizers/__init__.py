"""Built-in CloakMill-owned rule recognizers (no Presidio)."""

from __future__ import annotations

from cloakmill.detection.catalog import RecognizerCatalog
from cloakmill.detection.recognizers.account_id import AccountIdRecognizer
from cloakmill.detection.recognizers.email import EmailRecognizer
from cloakmill.detection.recognizers.employee_id import EmployeeIdRecognizer
from cloakmill.detection.recognizers.payment_card import PaymentCardRecognizer
from cloakmill.detection.recognizers.schema import SchemaFieldRecognizer


def build_default_catalog() -> RecognizerCatalog:
    """Catalog of schema/regex/checksum recognizers for known identifier types."""
    return RecognizerCatalog(
        (
            SchemaFieldRecognizer(),
            EmailRecognizer(),
            EmployeeIdRecognizer(),
            AccountIdRecognizer(),
            PaymentCardRecognizer(),
        )
    )


__all__ = [
    "AccountIdRecognizer",
    "EmailRecognizer",
    "EmployeeIdRecognizer",
    "PaymentCardRecognizer",
    "SchemaFieldRecognizer",
    "build_default_catalog",
]
