"""Fixed seeds, reserved domains, and corpus sizes for synthetic eval corpora."""

from __future__ import annotations

SCHEMA_VERSION = "provisional-f01-v1"
GENERATOR_VERSION = "synthetic-corpus-generator/1.0.0"
CORPUS_SERIES = "eval-v1"

# Fixed seed so 1k / 10k regenerations are bit-stable across machines.
MASTER_SEED = 20_251_118

SIZES: dict[str, int] = {
    "1k": 1_000,
    "10k": 10_000,
}

# RFC 2606 / reserved example domains only.
RESERVED_EMAIL_DOMAINS: tuple[str, ...] = (
    "acme.example",
    "birch.example",
    "contoso.example",
    "fabrikam.example",
    "northwind.example",
)

ORGANIZATION_NAMES: tuple[str, ...] = (
    "Acme Example Corp",
    "Birch Example Labs",
    "Contoso Example Systems",
    "Fabrikam Example Group",
    "Northwind Example Trading",
)

FIRST_NAMES: tuple[str, ...] = (
    "Alex",
    "Jordan",
    "Sam",
    "Taylor",
    "Casey",
    "Riley",
    "Morgan",
    "Quinn",
    "Avery",
    "Reese",
    "Jamie",
    "Cameron",
    "Drew",
    "Harper",
    "Logan",
    "Parker",
    "Skyler",
    "Rowan",
    "Elliot",
    "Finley",
)

LAST_NAMES: tuple[str, ...] = (
    "Nguyen",
    "Patel",
    "Garcia",
    "Okoro",
    "Andersen",
    "Silva",
    "Khan",
    "Berg",
    "Costa",
    "Nakamura",
    "Okafor",
    "Petrov",
    "Ibrahim",
    "Vargas",
    "Singh",
    "Nielsen",
    "Almeida",
    "Johansson",
    "Martinez",
    "Chen",
)

# Deliberately ambiguous shared first names used for abstention cases.
AMBIGUOUS_FIRST_NAMES: tuple[str, ...] = ("Alex", "Jordan", "Sam")
