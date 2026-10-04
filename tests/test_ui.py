def test_home_page_serves_the_web_ui(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Digital Wallet" in r.text


def test_list_accounts_empty(client):
    assert client.get("/accounts").json() == []


def test_list_accounts_returns_all_in_id_order_with_balances(client, w):
    a = w.account("10.00", name="First")
    b = w.account("0.00", name="Second")
    rows = client.get("/accounts").json()
    assert [r["id"] for r in rows] == [a, b]
    assert [r["balance"] for r in rows] == ["10.00", "0.00"]
