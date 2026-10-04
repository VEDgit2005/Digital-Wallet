# Digital Wallet API — with an automated test suite

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

A REST API for a digital wallet (accounts, deposits, withdrawals, peer-to-peer transfers) built with
**FastAPI + PostgreSQL**, plus a **pytest suite of 94 tests** that verifies business rules, input validation,
database integrity and race conditions, running automatically on every push via **GitHub Actions**.

The point of the project is not the wallet itself, it is showing how an application is **proven correct**:
test design, SQL-level data validation, concurrency testing, containerised environments and CI.

## Features
| Endpoint | Purpose |
|---|---|
| `POST /accounts` | Create an account (validates name and email, unique email) |
| `GET /accounts/{id}` | Account details and balance |
| `POST /accounts/{id}/deposit` | Add money |
| `POST /accounts/{id}/withdraw` | Remove money (never below zero) |
| `POST /transfers` | Atomic transfer between two accounts |
| `GET /accounts/{id}/transactions` | Ledger history with `type`, `limit`, `offset` filters |
| `POST /accounts/{id}/deactivate` | Close an account (only when balance is zero) |

Money-moving endpoints accept an optional `Idempotency-Key` header: retrying the same request never moves money twice.

**Business rules enforced:** amount > 0, max 2 decimal places, max 1,000,000.00 per transaction; no overdrafts;
no self-transfers; inactive accounts cannot transact; a transfer fully succeeds or fully fails.

## Web UI
After starting the app, open **http://localhost:8000** for a simple web page (create accounts, deposit, withdraw, transfer, view history). Swagger API docs stay at `/docs`.

## Run it
```bash
# API + PostgreSQL
docker compose up --build          # http://localhost:8000/docs  (interactive Swagger UI)

# Full test suite against PostgreSQL
docker compose run --rm tests

# Or locally with no Docker (SQLite, concurrency tests skipped)
pip install -r requirements-dev.txt
pytest
```
Run the full suite including concurrency tests against your own PostgreSQL:
```bash
TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/wallet_test pytest --cov=app
```

## How it is tested
| Test file | What it verifies |
|---|---|
| `test_accounts.py` | Creation, duplicate/case-insensitive email, invalid email, name length boundaries (100 vs 101), 404s, deactivation rules |
| `test_deposit_withdraw.py` | Balance maths, zero/negative/non-numeric/3-decimal amounts, max-amount boundary, exact-balance and 1-cent-over withdrawals, no float drift |
| `test_transfers.py` | Success path, money conservation, linked ledger entries, every rejection leaves **both** accounts unchanged |
| `test_transactions.py` | Ordering, running balance, filtering, pagination, invalid query params |
| `test_idempotency.py` | Retry replays the same response, payload mismatch → 409, failed requests are not cached |
| `test_db_integrity.py` | **SQL checks**: balance = sum of ledger, no negative balances, every transfer has one debit + one equal credit, DB constraints hold even if app logic is bypassed |
| `test_concurrency.py` | **PostgreSQL only**: parallel withdrawals cannot overdraw, no lost deposits, concurrent same-key requests apply once, opposite-direction transfers don't deadlock |

Result: **94 tests, 97% line coverage**. See [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) for the test strategy and the
fault-injection results (8 deliberately seeded bugs, all caught).

## Design decisions worth discussing
- **Integer minor units, not floats.** Balances are stored as integer paise/cents. `0.1 × 10 ≠ 1.0` in floating point; there is a test for it.
- **One DB transaction per request.** Balance changes, ledger rows and the idempotency record commit together or not at all.
- **Row locking in a fixed order.** `SELECT … FOR UPDATE` ordered by account id stops double-spend races and prevents deadlocks between A→B and B→A transfers.
- **Defence in depth.** `CHECK (balance_minor >= 0)` and `CHECK (amount_minor > 0)` in the database mean a bug in the app code still cannot corrupt data.
- **Consistent error contract.** Every business error returns `{"error": {"code": "...", "message": "..."}}` with an appropriate HTTP status.

## Project layout
```
app/        main.py (routes, idempotency) · services.py (business logic) · models.py · schemas.py · errors.py
tests/      7 test modules + conftest.py (fixtures, scenario helper)
docs/       TEST_PLAN.md
.github/    workflows/ci.yml  (SQLite run + PostgreSQL run with coverage gate ≥ 90%)
```
