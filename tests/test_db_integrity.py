"""Checks the database itself with SQL, independent of what the API reports."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Account, Transaction


def scenario(w):
    """A mixed workload used by several integrity checks."""
    a, b, c = w.account("500.00"), w.account("200.00"), w.account()
    w.deposit(a, "25.25")
    w.withdraw(b, "60.10")
    w.transfer(a, c, "100.00")
    w.transfer(b, a, "40.40")
    w.transfer(c, b, "15.15")
    w.withdraw(a, "9999.00")  # rejected: must leave no trace
    w.transfer(a, a, "1.00")  # rejected
    return a, b, c


def test_balance_equals_sum_of_ledger(db, w):
    scenario(w)
    rows = db.execute(text("""
        SELECT a.id, a.balance_minor,
               COALESCE(SUM(CASE WHEN t.type IN ('DEPOSIT','TRANSFER_IN') THEN t.amount_minor
                                 ELSE -t.amount_minor END), 0) AS ledger_balance
        FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id
        GROUP BY a.id, a.balance_minor""")).all()
    assert rows
    for acc_id, balance, ledger in rows:
        assert balance == ledger, f"account {acc_id}: stored {balance} != ledger {ledger}"


def test_no_negative_balances(db, w):
    scenario(w)
    assert db.execute(text("SELECT COUNT(*) FROM accounts WHERE balance_minor < 0")).scalar() == 0


def test_every_transfer_has_exactly_one_debit_and_one_credit_of_equal_amount(db, w):
    scenario(w)
    rows = db.execute(text("""
        SELECT transfer_ref,
               SUM(CASE WHEN type='TRANSFER_OUT' THEN 1 ELSE 0 END) AS outs,
               SUM(CASE WHEN type='TRANSFER_IN'  THEN 1 ELSE 0 END) AS ins,
               SUM(CASE WHEN type='TRANSFER_OUT' THEN amount_minor ELSE 0 END) AS out_amt,
               SUM(CASE WHEN type='TRANSFER_IN'  THEN amount_minor ELSE 0 END) AS in_amt
        FROM transactions WHERE transfer_ref IS NOT NULL GROUP BY transfer_ref""")).all()
    assert len(rows) == 3  # only the three successful transfers
    for ref, outs, ins, out_amt, in_amt in rows:
        assert (outs, ins) == (1, 1)
        assert out_amt == in_amt


def test_rejected_requests_leave_no_ledger_rows(db, w):
    scenario(w)
    # 3 opening deposits (a, b; c has none) -> 2, plus 1 deposit, 1 withdrawal, 3 transfers x 2 rows
    assert db.execute(text("SELECT COUNT(*) FROM transactions")).scalar() == 2 + 1 + 1 + 6


def test_total_money_in_system_matches_deposits_minus_withdrawals(db, w):
    scenario(w)
    total = db.execute(text("SELECT SUM(balance_minor) FROM accounts")).scalar()
    deposits = db.execute(text("SELECT SUM(amount_minor) FROM transactions WHERE type='DEPOSIT'")).scalar()
    withdrawals = db.execute(text("SELECT SUM(amount_minor) FROM transactions WHERE type='WITHDRAWAL'")).scalar()
    assert total == deposits - withdrawals


def test_api_response_matches_database_row(db, w):
    acc = w.account("123.45")
    row = db.get(Account, acc)
    assert row.balance_minor == 12345
    assert w.balance(acc) == "123.45"


def test_ledger_balance_after_matches_final_balance(db, w):
    acc = w.account()
    for amt in ("10.00", "20.00", "30.00"):
        w.deposit(acc, amt)
    w.withdraw(acc, "15.00")
    last = db.query(Transaction).filter_by(account_id=acc).order_by(Transaction.id.desc()).first()
    assert last.balance_after_minor == db.get(Account, acc).balance_minor == 4500


def test_database_rejects_negative_balance_even_if_app_logic_is_bypassed(db, w):
    acc = w.account("10.00")
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE accounts SET balance_minor = -1 WHERE id = :i"), {"i": acc})
        db.commit()
    db.rollback()


def test_database_rejects_non_positive_transaction_amount(db, w):
    acc = w.account()
    with pytest.raises(IntegrityError):
        db.add(Transaction(account_id=acc, type="DEPOSIT", amount_minor=0, balance_after_minor=0))
        db.commit()
    db.rollback()


def test_database_enforces_unique_email(db, w):
    w.account()
    with pytest.raises(IntegrityError):
        db.add_all([Account(owner_name="x", email="same@example.com"),
                    Account(owner_name="y", email="same@example.com")])
        db.commit()
    db.rollback()
