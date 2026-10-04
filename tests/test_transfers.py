import pytest


class TestTransferSuccess:
    def test_moves_money_between_accounts(self, w):
        a, b = w.account("100.00"), w.account("20.00")
        r = w.transfer(a, b, "35.50")
        assert r.status_code == 201
        body = r.json()
        assert body["from_balance_after"] == "64.50"
        assert body["to_balance_after"] == "55.50"
        assert w.balance(a) == "64.50"
        assert w.balance(b) == "55.50"

    def test_total_money_is_conserved(self, w):
        a, b, c = w.account("100.00"), w.account("50.00"), w.account("0.00")
        w.transfer(a, b, "10.10")
        w.transfer(b, c, "30.30")
        w.transfer(c, a, "5.05")
        total = sum(float(w.balance(x)) for x in (a, b, c))
        assert round(total, 2) == 150.00

    def test_transfer_entire_balance(self, w):
        a, b = w.account("42.00"), w.account()
        assert w.transfer(a, b, "42.00").status_code == 201
        assert w.balance(a) == "0.00"
        assert w.balance(b) == "42.00"

    def test_transfer_records_two_linked_ledger_entries(self, client, w):
        a, b = w.account("100.00"), w.account()
        ref = w.transfer(a, b, "25.00").json()["transfer_ref"]
        out = client.get(f"/accounts/{a}/transactions", params={"type": "TRANSFER_OUT"}).json()
        inn = client.get(f"/accounts/{b}/transactions", params={"type": "TRANSFER_IN"}).json()
        assert len(out) == 1 and len(inn) == 1
        assert out[0]["transfer_ref"] == inn[0]["transfer_ref"] == ref
        assert out[0]["counterparty_account_id"] == b
        assert inn[0]["counterparty_account_id"] == a

    def test_opposite_direction_transfers(self, w):
        a, b = w.account("100.00"), w.account("100.00")
        w.transfer(a, b, "30.00")
        w.transfer(b, a, "10.00")
        assert w.balance(a) == "80.00"
        assert w.balance(b) == "120.00"


class TestTransferRejections:
    def test_insufficient_funds_changes_nothing(self, w):
        a, b = w.account("10.00"), w.account("5.00")
        r = w.transfer(a, b, "10.01")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
        assert w.balance(a) == "10.00"
        assert w.balance(b) == "5.00"

    def test_same_account_rejected(self, w):
        a = w.account("100.00")
        r = w.transfer(a, a, "10.00")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_TRANSFER"
        assert w.balance(a) == "100.00"

    def test_unknown_destination_does_not_debit_source(self, w):
        a = w.account("100.00")
        r = w.transfer(a, 99999, "10.00")
        assert r.status_code == 404
        assert w.balance(a) == "100.00"

    def test_unknown_source_rejected(self, w):
        b = w.account("100.00")
        assert w.transfer(99999, b, "10.00").status_code == 404
        assert w.balance(b) == "100.00"

    def test_inactive_destination_rejected_and_source_unchanged(self, client, w):
        a, b = w.account("100.00"), w.account()
        client.post(f"/accounts/{b}/deactivate")
        r = w.transfer(a, b, "10.00")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "ACCOUNT_INACTIVE"
        assert w.balance(a) == "100.00"

    def test_inactive_source_rejected(self, client, w):
        a, b = w.account(), w.account("50.00")
        client.post(f"/accounts/{a}/deactivate")
        assert w.transfer(a, b, "1.00").status_code == 409

    @pytest.mark.parametrize("amount", ["0", "-10", "abc", "1.001", "1000000.01"])
    def test_invalid_amount_rejected(self, w, amount):
        a, b = w.account("100.00"), w.account()
        assert w.transfer(a, b, amount).status_code == 422
        assert w.balance(a) == "100.00"

    def test_missing_fields_rejected(self, client):
        assert client.post("/transfers", json={"amount": "5.00"}).status_code == 422
        assert client.post("/transfers", json={"from_account_id": 1, "to_account_id": 2}).status_code == 422
