"""Business logic. Every public function runs inside the caller's DB transaction;
the caller (see main.py) commits once, so a request either fully applies or not at all."""
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import errors
from .models import Account, Transaction
from .schemas import AccountCreate, minor_to_decimal


def to_minor(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


def create_account(db: Session, data: AccountCreate) -> Account:
    email = data.email.lower()
    if db.scalar(select(Account).where(Account.email == email)):
        raise errors.DuplicateEmail(f"An account with email {email} already exists")
    account = Account(owner_name=data.owner_name, email=email)
    db.add(account)
    try:
        db.flush()
    except IntegrityError:  # lost a race with a concurrent signup for the same email
        db.rollback()
        raise errors.DuplicateEmail(f"An account with email {email} already exists")
    return account


def get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise errors.AccountNotFound(f"Account {account_id} not found")
    return account


def _lock_accounts(db: Session, *ids: int) -> dict[int, Account]:
    """Lock rows in ascending id order (prevents deadlocks between opposite transfers).
    FOR UPDATE is a no-op on SQLite, which serialises writes on its own."""
    rows = db.scalars(
        select(Account).where(Account.id.in_(ids)).order_by(Account.id).with_for_update()
    ).all()
    found = {a.id: a for a in rows}
    for i in ids:
        if i not in found:
            raise errors.AccountNotFound(f"Account {i} not found")
    return found


def _require_active(account: Account) -> None:
    if not account.is_active:
        raise errors.AccountInactive(f"Account {account.id} is deactivated")


def deposit(db: Session, account_id: int, amount: Decimal) -> Transaction:
    account = _lock_accounts(db, account_id)[account_id]
    _require_active(account)
    minor = to_minor(amount)
    account.balance_minor += minor
    txn = Transaction(account_id=account.id, type="DEPOSIT", amount_minor=minor,
                      balance_after_minor=account.balance_minor)
    db.add(txn)
    db.flush()
    return txn


def withdraw(db: Session, account_id: int, amount: Decimal) -> Transaction:
    account = _lock_accounts(db, account_id)[account_id]
    _require_active(account)
    minor = to_minor(amount)
    if minor > account.balance_minor:
        raise errors.InsufficientFunds(
            f"Balance {minor_to_decimal(account.balance_minor)} is less than requested {amount}")
    account.balance_minor -= minor
    txn = Transaction(account_id=account.id, type="WITHDRAWAL", amount_minor=minor,
                      balance_after_minor=account.balance_minor)
    db.add(txn)
    db.flush()
    return txn


def transfer(db: Session, from_id: int, to_id: int, amount: Decimal) -> dict:
    if from_id == to_id:
        raise errors.InvalidTransfer("Cannot transfer to the same account")
    accounts = _lock_accounts(db, from_id, to_id)
    src, dst = accounts[from_id], accounts[to_id]
    _require_active(src)
    _require_active(dst)
    minor = to_minor(amount)
    if minor > src.balance_minor:
        raise errors.InsufficientFunds(
            f"Balance {minor_to_decimal(src.balance_minor)} is less than requested {amount}")
    src.balance_minor -= minor
    dst.balance_minor += minor
    ref = str(uuid.uuid4())
    db.add_all([
        Transaction(account_id=src.id, type="TRANSFER_OUT", amount_minor=minor,
                    balance_after_minor=src.balance_minor, counterparty_account_id=dst.id, transfer_ref=ref),
        Transaction(account_id=dst.id, type="TRANSFER_IN", amount_minor=minor,
                    balance_after_minor=dst.balance_minor, counterparty_account_id=src.id, transfer_ref=ref),
    ])
    db.flush()
    return {"transfer_ref": ref, "from_account_id": src.id, "to_account_id": dst.id,
            "amount": amount, "from_balance_after": minor_to_decimal(src.balance_minor),
            "to_balance_after": minor_to_decimal(dst.balance_minor)}


def deactivate(db: Session, account_id: int) -> Account:
    account = _lock_accounts(db, account_id)[account_id]
    if account.balance_minor != 0:
        raise errors.BalanceNotZero("Withdraw or transfer the remaining balance before deactivating")
    account.is_active = False
    return account


def list_transactions(db: Session, account_id: int, type_: str | None, limit: int, offset: int):
    get_account(db, account_id)
    q = select(Transaction).where(Transaction.account_id == account_id)
    if type_:
        q = q.where(Transaction.type == type_)
    return db.scalars(q.order_by(Transaction.id.desc()).limit(limit).offset(offset)).all()


def list_accounts(db: Session):
    return db.scalars(select(Account).order_by(Account.id)).all()
