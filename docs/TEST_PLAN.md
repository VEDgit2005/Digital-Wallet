# Test Plan — Digital Wallet API

## 1. Scope
In scope: all HTTP endpoints, business rules, input validation, data integrity in PostgreSQL, idempotency, concurrent access.
Out of scope: authentication, rate limiting, multi-currency, performance/load testing.

## 2. Approach
| Level | Technique | Examples |
|---|---|---|
| Functional | Happy path per endpoint | deposit increases balance; transfer moves money |
| Negative | Invalid input and state | zero/negative/non-numeric amounts, unknown accounts, inactive accounts, overdraft |
| Boundary value | Edges of every limit | 0.00 / 0.01; 1,000,000.00 / 1,000,000.01; name 100 / 101 chars; balance exact / 1 cent over; `limit` 1 / 100 / 0 / 101 |
| Atomicity | Failed operation changes nothing | rejected transfer leaves both balances and the ledger untouched |
| Data integrity (SQL) | Independent queries against the DB | stored balance = sum of ledger; each transfer has one debit and one credit of equal amount; total money = deposits − withdrawals |
| Constraint | Bypass the app, hit the DB directly | negative balance and zero-amount inserts are rejected by CHECK constraints |
| Idempotency | Retry semantics | same key replays response; different payload → 409; failures not cached |
| Concurrency | Parallel requests on PostgreSQL | 10 parallel withdrawals of 100 on a 500 balance → exactly 5 succeed |

## 3. Environments
- **SQLite** (default, zero setup): fast feedback, 90 tests.
- **PostgreSQL 16** (docker compose and CI): full 94 tests including concurrency and row-locking behaviour.

## 4. Entry / exit criteria
- Exit: all tests pass on both databases; line coverage ≥ 90% (enforced in CI; currently 97%).

## 5. Fault-injection (mutation) check
To confirm the suite can actually detect defects, 8 bugs were injected into the application one at a time and
the suite run against PostgreSQL. Every one was caught.

| # | Injected fault | Caught by |
|---|---|---|
| 1 | Withdrawal allows 1 cent more than the balance (off-by-one) | `test_one_cent_over_balance_rejected_and_balance_unchanged` |
| 2 | Transfer skips the destination-active check | `test_inactive_destination_rejected_and_source_unchanged` |
| 3 | Transfer skips the source balance check | `test_insufficient_funds_changes_nothing` |
| 4 | Row locking (`FOR UPDATE`) removed | `test_concurrent_withdrawals_cannot_overdraw` |
| 5 | Idempotency ignores a changed payload | `test_same_key_different_amount_is_conflict` |
| 6 | Deposit does not write a ledger row | `test_cannot_deactivate_with_balance` (first failure; SQL integrity tests also fail) |
| 7 | Self-transfer allowed | ledger integrity test (and `test_same_account_rejected`) |
| 8 | Email uniqueness made case-sensitive | `test_duplicate_email_is_case_insensitive` |

## 6. Issues found while building the test setup
- SQLAlchemy 2.1 changed the default PostgreSQL driver for `postgresql://` URLs → connection URLs now name the driver explicitly (`postgresql+psycopg2://`).
- Using `TestClient` as a context manager runs the app's startup hook against the default database, not the test database, which broke the threaded concurrency tests → clients are created without the context manager in those tests.
