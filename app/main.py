import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import errors, services
from .database import Base, engine, get_db
from .models import IdempotencyRecord
from .schemas import (AccountCreate, AccountOut, AmountIn, TransactionOut, TransferIn, TransferOut,
                      minor_to_decimal)

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Digital Wallet API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(errors.WalletError)
async def wallet_error_handler(_: Request, exc: errors.WalletError):
    return JSONResponse(status_code=exc.status_code,
                        content={"error": {"code": exc.code, "message": exc.message}})


def _account_out(a) -> AccountOut:
    return AccountOut(id=a.id, owner_name=a.owner_name, email=a.email,
                      balance=minor_to_decimal(a.balance_minor), is_active=a.is_active, created_at=a.created_at)


def _txn_out(t) -> TransactionOut:
    return TransactionOut(id=t.id, account_id=t.account_id, type=t.type,
                          amount=minor_to_decimal(t.amount_minor),
                          balance_after=minor_to_decimal(t.balance_after_minor),
                          counterparty_account_id=t.counterparty_account_id,
                          transfer_ref=t.transfer_ref, created_at=t.created_at)


def _json(body: str, status: int) -> Response:
    return Response(content=body, status_code=status, media_type="application/json")


def run_idempotent(db: Session, key: str | None, endpoint: str, payload: dict,
                   action: Callable[[], str], status: int) -> Response:
    """Run `action` (returns a JSON body) at most once per Idempotency-Key.
    Same key + same payload -> replay the stored response. Same key + different payload -> 409."""
    if not key:
        body = action()
        db.commit()
        return _json(body, status)

    req_hash = hashlib.sha256(json.dumps([endpoint, payload], sort_keys=True, default=str).encode()).hexdigest()

    def replay_or_conflict() -> Response | None:
        rec = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
        if rec is None:
            return None
        if rec.request_hash != req_hash:
            raise errors.IdempotencyConflict("Idempotency-Key was already used with a different request")
        return _json(rec.response_body, rec.status_code)

    if (replayed := replay_or_conflict()) is not None:
        return replayed
    body = action()
    db.add(IdempotencyRecord(key=key, endpoint=endpoint, request_hash=req_hash,
                             status_code=status, response_body=body))
    try:
        db.commit()  # money movement and the idempotency record commit together
    except IntegrityError:  # a concurrent request with the same key won the race
        db.rollback()
        replayed = replay_or_conflict()
        if replayed is not None:
            return replayed
        raise
    return _json(body, status)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    account = services.create_account(db, data)
    db.commit()
    return _account_out(account)


@app.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return [_account_out(a) for a in services.list_accounts(db)]


@app.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: int, db: Session = Depends(get_db)):
    return _account_out(services.get_account(db, account_id))


@app.post("/accounts/{account_id}/deactivate", response_model=AccountOut)
def deactivate_account(account_id: int, db: Session = Depends(get_db)):
    account = services.deactivate(db, account_id)
    db.commit()
    return _account_out(account)


@app.post("/accounts/{account_id}/deposit", response_model=TransactionOut, status_code=201)
def deposit(account_id: int, data: AmountIn, db: Session = Depends(get_db),
            idempotency_key: str | None = Header(default=None)):
    return run_idempotent(
        db, idempotency_key, "deposit", {"account_id": account_id, "amount": data.amount},
        lambda: _txn_out(services.deposit(db, account_id, data.amount)).model_dump_json(), 201)


@app.post("/accounts/{account_id}/withdraw", response_model=TransactionOut, status_code=201)
def withdraw(account_id: int, data: AmountIn, db: Session = Depends(get_db),
             idempotency_key: str | None = Header(default=None)):
    return run_idempotent(
        db, idempotency_key, "withdraw", {"account_id": account_id, "amount": data.amount},
        lambda: _txn_out(services.withdraw(db, account_id, data.amount)).model_dump_json(), 201)


@app.post("/transfers", response_model=TransferOut, status_code=201)
def transfer(data: TransferIn, db: Session = Depends(get_db),
             idempotency_key: str | None = Header(default=None)):
    return run_idempotent(
        db, idempotency_key, "transfer", data.model_dump(),
        lambda: TransferOut(**services.transfer(db, data.from_account_id, data.to_account_id,
                                                data.amount)).model_dump_json(), 201)


@app.get("/accounts/{account_id}/transactions", response_model=list[TransactionOut])
def transactions(account_id: int, type: str | None = Query(default=None, pattern="^(DEPOSIT|WITHDRAWAL|TRANSFER_OUT|TRANSFER_IN)$"),
                 limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
                 db: Session = Depends(get_db)):
    return [_txn_out(t) for t in services.list_transactions(db, account_id, type, limit, offset)]
