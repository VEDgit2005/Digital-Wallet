"""Shared fixtures.

TEST_DATABASE_URL picks the backend:
  - unset            -> throwaway SQLite file (zero setup, fast)
  - postgresql://... -> real PostgreSQL (used in CI and docker compose)
Every test starts from empty tables.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db, make_engine
from app.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_wallet.db")
IS_POSTGRES = TEST_DATABASE_URL.startswith("postgresql")

test_engine = make_engine(TEST_DATABASE_URL)
TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


def pytest_collection_modifyitems(config, items):
    if not IS_POSTGRES:
        skip = pytest.mark.skip(reason="requires PostgreSQL (set TEST_DATABASE_URL)")
        for item in items:
            if "postgres_only" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = TestSession()
    yield session
    session.close()


class WalletHelper:
    """Small helper so tests read like scenarios instead of HTTP plumbing."""

    def __init__(self, client):
        self.c = client
        self._n = 0

    def account(self, balance="0.00", name="Test User"):
        self._n += 1
        r = self.c.post("/accounts", json={"owner_name": name, "email": f"user{self._n}@example.com"})
        assert r.status_code == 201, r.text
        acc = r.json()
        if float(balance) > 0:
            d = self.c.post(f"/accounts/{acc['id']}/deposit", json={"amount": balance})
            assert d.status_code == 201, d.text
        return acc["id"]

    def balance(self, account_id):
        r = self.c.get(f"/accounts/{account_id}")
        assert r.status_code == 200, r.text
        return r.json()["balance"]

    def deposit(self, account_id, amount, key=None):
        return self.c.post(f"/accounts/{account_id}/deposit", json={"amount": amount},
                           headers={"Idempotency-Key": key} if key else {})

    def withdraw(self, account_id, amount, key=None):
        return self.c.post(f"/accounts/{account_id}/withdraw", json={"amount": amount},
                           headers={"Idempotency-Key": key} if key else {})

    def transfer(self, src, dst, amount, key=None):
        return self.c.post("/transfers", json={"from_account_id": src, "to_account_id": dst, "amount": amount},
                           headers={"Idempotency-Key": key} if key else {})


@pytest.fixture
def w(client):
    return WalletHelper(client)
