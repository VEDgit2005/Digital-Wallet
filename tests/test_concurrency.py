"""Race-condition tests. These only prove something on a real database with row locking,
so they run against PostgreSQL (CI and docker compose) and are skipped on SQLite."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.postgres_only


def _parallel(fn, jobs, workers=10):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, jobs))


def _call(method, url, **kw):
    # One client per thread. Not used as a context manager, so the app's startup hook
    # (which targets the default DATABASE_URL) is skipped and the test DB override is used.
    return TestClient(app).request(method, url, **kw)


def test_concurrent_withdrawals_cannot_overdraw(w):
    acc = w.account("500.00")
    results = _parallel(lambda _: _call("POST", f"/accounts/{acc}/withdraw", json={"amount": "100.00"}),
                        range(10))
    codes = sorted(r.status_code for r in results)
    assert codes == [201] * 5 + [422] * 5, codes   # exactly five fit in the balance
    assert w.balance(acc) == "0.00"


def test_concurrent_deposits_none_lost(w):
    acc = w.account()
    results = _parallel(lambda _: _call("POST", f"/accounts/{acc}/deposit", json={"amount": "10.00"}), range(20))
    assert all(r.status_code == 201 for r in results)
    assert w.balance(acc) == "200.00"  # no lost updates


def test_concurrent_requests_with_same_idempotency_key_apply_once(w):
    acc = w.account()

    def go(_):
        return _call("POST", f"/accounts/{acc}/deposit", json={"amount": "50.00"},
                     headers={"Idempotency-Key": "race-key"})

    results = _parallel(go, range(8))
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    assert w.balance(acc) == "50.00"
    assert len({r.json()["id"] for r in results}) == 1  # all got the same transaction back


def test_opposite_transfers_do_not_deadlock_and_conserve_money(w):
    a, b = w.account("1000.00"), w.account("1000.00")

    def go(i):
        src, dst = (a, b) if i % 2 == 0 else (b, a)
        return _call("POST", "/transfers", json={"from_account_id": src, "to_account_id": dst, "amount": "10.00"})

    results = _parallel(go, range(20))
    assert all(r.status_code == 201 for r in results), [r.text for r in results if r.status_code != 201]
    assert float(w.balance(a)) + float(w.balance(b)) == 2000.00
    assert w.balance(a) == "1000.00"  # 10 transfers each way cancel out
