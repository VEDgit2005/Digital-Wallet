import pytest


class TestDeposit:
    def test_deposit_increases_balance(self, w):
        acc = w.account()
        r = w.deposit(acc, "250.50")
        assert r.status_code == 201
        body = r.json()
        assert body["type"] == "DEPOSIT"
        assert float(body["amount"]) == 250.50
        assert float(body["balance_after"]) == 250.50
        assert float(w.balance(acc)) == 250.50

    def test_multiple_deposits_accumulate(self, w):
        acc = w.account()
        for amt in ("10.00", "20.00", "0.01"):
            w.deposit(acc, amt)
        assert float(w.balance(acc)) == 30.01

    def test_no_floating_point_drift(self, w):
        """Ten deposits of 0.10 must equal exactly 1.00 (0.1 * 10 != 1.0 in float arithmetic)."""
        acc = w.account()
        for _ in range(10):
            w.deposit(acc, "0.10")
        assert w.balance(acc) == "1.00"

    @pytest.mark.parametrize("amount", ["0", "0.00", "-1", "-0.01"])
    def test_zero_and_negative_rejected(self, w, amount):
        acc = w.account()
        assert w.deposit(acc, amount).status_code == 422
        assert float(w.balance(acc)) == 0

    @pytest.mark.parametrize("amount", ["abc", "", None, "1,000", "1e2e3"])
    def test_non_numeric_rejected(self, w, amount):
        acc = w.account()
        assert w.deposit(acc, amount).status_code == 422

    def test_more_than_two_decimals_rejected(self, w):
        acc = w.account()
        assert w.deposit(acc, "10.001").status_code == 422
        assert float(w.balance(acc)) == 0

    def test_smallest_amount_accepted(self, w):
        acc = w.account()
        assert w.deposit(acc, "0.01").status_code == 201

    def test_max_amount_boundary(self, w):
        acc = w.account()
        assert w.deposit(acc, "1000000.00").status_code == 201
        assert w.deposit(acc, "1000000.01").status_code == 422
        assert w.balance(acc) == "1000000.00"

    def test_missing_amount_field_rejected(self, client, w):
        acc = w.account()
        assert client.post(f"/accounts/{acc}/deposit", json={}).status_code == 422

    def test_unknown_account(self, w):
        assert w.deposit(99999, "5.00").status_code == 404


class TestWithdraw:
    def test_withdraw_reduces_balance(self, w):
        acc = w.account("100.00")
        r = w.withdraw(acc, "40.25")
        assert r.status_code == 201
        assert r.json()["type"] == "WITHDRAWAL"
        assert w.balance(acc) == "59.75"

    def test_withdraw_entire_balance_leaves_zero(self, w):
        acc = w.account("100.00")
        assert w.withdraw(acc, "100.00").status_code == 201
        assert w.balance(acc) == "0.00"

    def test_one_cent_over_balance_rejected_and_balance_unchanged(self, w):
        acc = w.account("100.00")
        r = w.withdraw(acc, "100.01")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
        assert w.balance(acc) == "100.00"

    def test_withdraw_from_empty_account_rejected(self, w):
        acc = w.account()
        assert w.withdraw(acc, "0.01").status_code == 422

    @pytest.mark.parametrize("amount", ["0", "-5.00", "abc", "1.234"])
    def test_invalid_amounts_rejected(self, w, amount):
        acc = w.account("100.00")
        assert w.withdraw(acc, amount).status_code == 422
        assert w.balance(acc) == "100.00"

    def test_unknown_account(self, w):
        assert w.withdraw(99999, "5.00").status_code == 404

    def test_repeated_withdrawals_cannot_overdraw(self, w):
        acc = w.account("100.00")
        results = [w.withdraw(acc, "30.00").status_code for _ in range(5)]
        assert results == [201, 201, 201, 422, 422]
        assert w.balance(acc) == "10.00"
