class TestTransactionHistory:
    def test_history_is_newest_first_with_running_balance(self, client, w):
        acc = w.account()
        w.deposit(acc, "100.00")
        w.withdraw(acc, "30.00")
        w.deposit(acc, "5.00")
        rows = client.get(f"/accounts/{acc}/transactions").json()
        assert [r["type"] for r in rows] == ["DEPOSIT", "WITHDRAWAL", "DEPOSIT"]
        assert [r["balance_after"] for r in rows] == ["75.00", "70.00", "100.00"]

    def test_filter_by_type(self, client, w):
        acc = w.account()
        w.deposit(acc, "50.00")
        w.deposit(acc, "50.00")
        w.withdraw(acc, "10.00")
        rows = client.get(f"/accounts/{acc}/transactions", params={"type": "WITHDRAWAL"}).json()
        assert len(rows) == 1 and rows[0]["type"] == "WITHDRAWAL"

    def test_pagination(self, client, w):
        acc = w.account()
        for i in range(1, 8):
            w.deposit(acc, f"{i}.00")
        page1 = client.get(f"/accounts/{acc}/transactions", params={"limit": 3, "offset": 0}).json()
        page2 = client.get(f"/accounts/{acc}/transactions", params={"limit": 3, "offset": 3}).json()
        page3 = client.get(f"/accounts/{acc}/transactions", params={"limit": 3, "offset": 6}).json()
        assert [len(p) for p in (page1, page2, page3)] == [3, 3, 1]
        ids = [t["id"] for t in page1 + page2 + page3]
        assert len(set(ids)) == 7  # no overlaps between pages

    def test_empty_history(self, client, w):
        assert client.get(f"/accounts/{w.account()}/transactions").json() == []

    def test_failed_operations_leave_no_ledger_entry(self, client, w):
        acc = w.account("10.00")
        w.withdraw(acc, "999.00")
        rows = client.get(f"/accounts/{acc}/transactions").json()
        assert len(rows) == 1  # only the setup deposit

    def test_invalid_query_params_rejected(self, client, w):
        acc = w.account()
        url = f"/accounts/{acc}/transactions"
        assert client.get(url, params={"limit": 0}).status_code == 422
        assert client.get(url, params={"limit": 101}).status_code == 422
        assert client.get(url, params={"offset": -1}).status_code == 422
        assert client.get(url, params={"type": "REFUND"}).status_code == 422

    def test_limit_boundaries_accepted(self, client, w):
        acc = w.account()
        url = f"/accounts/{acc}/transactions"
        assert client.get(url, params={"limit": 1}).status_code == 200
        assert client.get(url, params={"limit": 100}).status_code == 200

    def test_unknown_account(self, client):
        assert client.get("/accounts/99999/transactions").status_code == 404
