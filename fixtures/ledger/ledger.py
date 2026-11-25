"""A tiny invented ledger: accounts hold integer cents; transfers move money between them."""

from vendor.money import to_cents


def transfer(balances: dict[str, int], source: str, target: str, amount: str) -> dict[str, int]:
    """Return new balances after moving `amount` (a decimal string) from source to target."""
    cents = to_cents(amount)
    if cents <= 0:
        raise ValueError("amount must be positive")
    if balances.get(source, 0) < cents:
        raise ValueError(f"insufficient funds in {source}")
    updated = dict(balances)
    updated[source] -= cents
    updated[target] = updated.get(target, 0) + cents
    return updated
