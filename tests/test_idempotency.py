"""A client that retries after a timeout must never move money twice."""


class TestIdempotency:
    def test_same_key_deposit_applied_once(self, w):
        acc = w.account()
        first = w.deposit(acc, "100.00", key="dep-1")
        retry = w.deposit(acc, "100.00", key="dep-1")
        assert first.status_code == retry.status_code == 201
        assert first.json() == retry.json()  # identical response replayed
        assert w.balance(acc) == "100.00"

    def test_same_key_transfer_applied_once(self, w):
        a, b = w.account("100.00"), w.account()
        r1 = w.transfer(a, b, "40.00", key="tx-1")
        r2 = w.transfer(a, b, "40.00", key="tx-1")
        assert r1.json()["transfer_ref"] == r2.json()["transfer_ref"]
        assert w.balance(a) == "60.00"
        assert w.balance(b) == "40.00"

    def test_same_key_withdraw_applied_once(self, w):
        acc = w.account("100.00")
        w.withdraw(acc, "30.00", key="wd-1")
        w.withdraw(acc, "30.00", key="wd-1")
        assert w.balance(acc) == "70.00"

    def test_same_key_different_amount_is_conflict(self, w):
        acc = w.account()
        w.deposit(acc, "10.00", key="k")
        r = w.deposit(acc, "99.00", key="k")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert w.balance(acc) == "10.00"

    def test_same_key_different_account_is_conflict(self, w):
        a, b = w.account(), w.account()
        w.deposit(a, "10.00", key="k")
        assert w.deposit(b, "10.00", key="k").status_code == 409
        assert w.balance(b) == "0.00"

    def test_different_keys_are_independent(self, w):
        acc = w.account()
        w.deposit(acc, "10.00", key="a")
        w.deposit(acc, "10.00", key="b")
        assert w.balance(acc) == "20.00"

    def test_requests_without_key_are_not_deduplicated(self, w):
        acc = w.account()
        w.deposit(acc, "10.00")
        w.deposit(acc, "10.00")
        assert w.balance(acc) == "20.00"

    def test_failed_request_is_not_cached(self, w):
        """A rejected withdrawal must be retryable with the same key once funds exist."""
        acc = w.account()
        assert w.withdraw(acc, "50.00", key="retry-me").status_code == 422
        w.deposit(acc, "100.00")
        assert w.withdraw(acc, "50.00", key="retry-me").status_code == 201
        assert w.balance(acc) == "50.00"
