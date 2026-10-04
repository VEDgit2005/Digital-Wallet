import pytest


class TestCreateAccount:
    def test_creates_account_with_zero_balance(self, client):
        r = client.post("/accounts", json={"owner_name": "Asha Rao", "email": "asha@example.com"})
        assert r.status_code == 201
        body = r.json()
        assert body["owner_name"] == "Asha Rao"
        assert body["email"] == "asha@example.com"
        assert float(body["balance"]) == 0
        assert body["is_active"] is True
        assert isinstance(body["id"], int)

    def test_duplicate_email_rejected(self, client):
        payload = {"owner_name": "A", "email": "dup@example.com"}
        assert client.post("/accounts", json=payload).status_code == 201
        r = client.post("/accounts", json=payload)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "DUPLICATE_EMAIL"

    def test_duplicate_email_is_case_insensitive(self, client):
        client.post("/accounts", json={"owner_name": "A", "email": "Case@Example.com"})
        r = client.post("/accounts", json={"owner_name": "B", "email": "case@example.com"})
        assert r.status_code == 409

    @pytest.mark.parametrize("email", ["not-an-email", "missing@", "@no-user.com", "", "a b@c.com"])
    def test_invalid_email_rejected(self, client, email):
        r = client.post("/accounts", json={"owner_name": "A", "email": email})
        assert r.status_code == 422

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name_rejected(self, client, name):
        r = client.post("/accounts", json={"owner_name": name, "email": "x@example.com"})
        assert r.status_code == 422

    def test_name_boundary_100_chars_ok_101_rejected(self, client):
        ok = client.post("/accounts", json={"owner_name": "a" * 100, "email": "a@example.com"})
        too_long = client.post("/accounts", json={"owner_name": "a" * 101, "email": "b@example.com"})
        assert ok.status_code == 201
        assert too_long.status_code == 422

    def test_missing_fields_rejected(self, client):
        assert client.post("/accounts", json={}).status_code == 422
        assert client.post("/accounts", json={"owner_name": "A"}).status_code == 422


class TestGetAccount:
    def test_returns_existing_account(self, client, w):
        acc_id = w.account()
        r = client.get(f"/accounts/{acc_id}")
        assert r.status_code == 200
        assert r.json()["id"] == acc_id

    def test_unknown_account_returns_404(self, client):
        r = client.get("/accounts/99999")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"

    def test_non_integer_id_returns_422(self, client):
        assert client.get("/accounts/abc").status_code == 422


class TestDeactivate:
    def test_deactivate_empty_account(self, client, w):
        acc = w.account()
        r = client.post(f"/accounts/{acc}/deactivate")
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_cannot_deactivate_with_balance(self, client, w):
        acc = w.account("10.00")
        r = client.post(f"/accounts/{acc}/deactivate")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "BALANCE_NOT_ZERO"
        assert client.get(f"/accounts/{acc}").json()["is_active"] is True

    def test_deactivate_unknown_account(self, client):
        assert client.post("/accounts/424242/deactivate").status_code == 404

    def test_deactivated_account_rejects_deposit_and_withdraw(self, client, w):
        acc = w.account()
        client.post(f"/accounts/{acc}/deactivate")
        for r in (w.deposit(acc, "5.00"), w.withdraw(acc, "1.00")):
            assert r.status_code == 409
            assert r.json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
