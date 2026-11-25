"""Vendored helper (invented for the demo). Do not edit: rule 1 in CLAUDE.md."""

from decimal import ROUND_HALF_EVEN, Decimal


def to_cents(amount: str) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
