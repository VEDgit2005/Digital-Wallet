class WalletError(Exception):
    status_code = 400
    code = "WALLET_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AccountNotFound(WalletError):
    status_code = 404
    code = "ACCOUNT_NOT_FOUND"


class DuplicateEmail(WalletError):
    status_code = 409
    code = "DUPLICATE_EMAIL"


class AccountInactive(WalletError):
    status_code = 409
    code = "ACCOUNT_INACTIVE"


class InsufficientFunds(WalletError):
    status_code = 422
    code = "INSUFFICIENT_FUNDS"


class InvalidTransfer(WalletError):
    status_code = 422
    code = "INVALID_TRANSFER"


class IdempotencyConflict(WalletError):
    status_code = 409
    code = "IDEMPOTENCY_KEY_REUSED"


class BalanceNotZero(WalletError):
    status_code = 409
    code = "BALANCE_NOT_ZERO"
