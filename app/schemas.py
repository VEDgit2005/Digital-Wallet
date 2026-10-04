from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

MAX_AMOUNT = Decimal("1000000.00")  # per-transaction limit


def minor_to_decimal(minor: int) -> Decimal:
    return (Decimal(minor) / 100).quantize(Decimal("0.01"))


class AccountCreate(BaseModel):
    owner_name: str = Field(min_length=1, max_length=100)
    email: EmailStr

    @field_validator("owner_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("owner_name must not be blank")
        return v.strip()


class AccountOut(BaseModel):
    id: int
    owner_name: str
    email: str
    balance: Decimal
    is_active: bool
    created_at: datetime


class AmountIn(BaseModel):
    amount: Decimal = Field(gt=0)

    @field_validator("amount")
    @classmethod
    def valid_money(cls, v: Decimal) -> Decimal:
        if v != v.quantize(Decimal("0.01")):
            raise ValueError("amount must have at most 2 decimal places")
        if v > MAX_AMOUNT:
            raise ValueError(f"amount must not exceed {MAX_AMOUNT}")
        return v


class TransferIn(AmountIn):
    from_account_id: int
    to_account_id: int


class TransactionOut(BaseModel):
    id: int
    account_id: int
    type: str
    amount: Decimal
    balance_after: Decimal
    counterparty_account_id: int | None
    transfer_ref: str | None
    created_at: datetime


class TransferOut(BaseModel):
    transfer_ref: str
    from_account_id: int
    to_account_id: int
    amount: Decimal
    from_balance_after: Decimal
    to_balance_after: Decimal
