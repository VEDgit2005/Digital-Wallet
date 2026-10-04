from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"
    # Money is stored as integer minor units (paise/cents) to avoid float rounding errors.
    __table_args__ = (CheckConstraint("balance_minor >= 0", name="ck_balance_non_negative"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("amount_minor > 0", name="ck_amount_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # DEPOSIT, WITHDRAWAL, TRANSFER_OUT, TRANSFER_IN
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    balance_after_minor: Mapped[int] = mapped_column(BigInteger)
    counterparty_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    transfer_ref: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyRecord(Base):
    """Remembers the result of a request so a retry with the same key is not applied twice."""
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[str] = mapped_column(Text)
