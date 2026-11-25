import pytest
from ledger import transfer


def test_transfer_moves_cents():
    assert transfer({"a": 5000, "b": 0}, "a", "b", "12.34") == {"a": 3766, "b": 1234}


def test_transfer_does_not_mutate_input():
    balances = {"a": 100}
    transfer(balances, "a", "b", "1")
    assert balances == {"a": 100}


@pytest.mark.parametrize("amount", ["0", "-1"])
def test_non_positive_amount_is_rejected(amount):
    with pytest.raises(ValueError, match="positive"):
        transfer({"a": 100}, "a", "b", amount)


def test_insufficient_funds_is_rejected():
    with pytest.raises(ValueError, match="insufficient"):
        transfer({"a": 100}, "a", "b", "2")
