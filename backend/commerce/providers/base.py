from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


class ProviderError(Exception):
    """Only a fixed safe code crosses the transport boundary, never bank payloads."""

    def __init__(self, code, *, retryable=False, ambiguous=False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.ambiguous = ambiguous


@dataclass(frozen=True)
class Checkout:
    link_id: str
    invoice_id: str
    shop_id: str
    terminal_id: str
    account_id: str
    amount: Decimal
    currency: str
    url: str
    status: str


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    invoice_id: str
    terminal_id: str
    account_id: str
    amount: Decimal
    currency: str
    status: str
    occurred_at: datetime | None = None
    original_amount: Decimal | None = None
    refunded_amount: Decimal | None = None


class PaymentProvider(Protocol):
    def create_checkout(self, payment) -> Checkout: ...
    def find_checkout(self, invoice_id: str) -> Checkout | None: ...
    def lookup_payment(self, invoice_id: str) -> Transaction | None: ...
    def deactivate_checkout(self, link_id: str) -> None: ...
    def request_refund(self, transaction_id: str, amount: int, external_id: str) -> None: ...
