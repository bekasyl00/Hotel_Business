import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings

from .providers.base import ProviderError


def origin(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ProviderError("payment_origin_invalid") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or port
    ):
        raise ProviderError("payment_origin_invalid")
    return value.rstrip("/")


@dataclass(frozen=True)
class HalykConfig:
    client_id: str
    client_secret: str = field(repr=False)
    shop_id: str
    terminal_id: str
    api_origin: str
    site_origin: str
    staff_origin: str
    invoice_prefix: str
    invoice_start: int
    invoice_end: int
    lookup_grant: str
    username: str = field(repr=False)
    password: str = field(repr=False)

    @property
    def merchant_scope(self):
        return hashlib.sha256(("halyk:sandbox:" + self.shop_id).encode()).hexdigest()

    @classmethod
    def from_settings(cls, *, require_gate=True):
        if settings.HALYK_EPAY_ENV != "sandbox":
            raise ProviderError("production_payments_disabled")
        if require_gate and not settings.HALYK_EPAY_PROTOCOL_VERIFIED:
            raise ProviderError("sandbox_protocol_not_verified")
        if not all(
            [
                settings.HALYK_EPAY_CLIENT_ID,
                settings.HALYK_EPAY_CLIENT_SECRET,
                settings.HALYK_EPAY_SHOP_ID,
                settings.HALYK_EPAY_TERMINAL_ID,
            ]
        ):
            raise ProviderError("payment_configuration_missing")
        prefix = settings.HALYK_EPAY_INVOICE_PREFIX
        if not re.fullmatch(r"[0-9]{0,9}", prefix):
            raise ProviderError("invoice_pool_invalid")
        start, end = settings.HALYK_EPAY_INVOICE_START, settings.HALYK_EPAY_INVOICE_END
        if not 100000 <= start <= end <= 999999:
            raise ProviderError("invoice_pool_invalid")
        grant = settings.HALYK_EPAY_LOOKUP_GRANT
        if grant not in ("password", "client_credentials"):
            raise ProviderError("payment_configuration_invalid")
        if grant == "password" and not (
            settings.HALYK_EPAY_INVOICE_USERNAME and settings.HALYK_EPAY_INVOICE_PASSWORD
        ):
            raise ProviderError("payment_configuration_missing")
        return cls(
            client_id=settings.HALYK_EPAY_CLIENT_ID,
            client_secret=settings.HALYK_EPAY_CLIENT_SECRET,
            shop_id=settings.HALYK_EPAY_SHOP_ID,
            terminal_id=settings.HALYK_EPAY_TERMINAL_ID,
            api_origin=origin(settings.PAYMENTS_PUBLIC_API_ORIGIN),
            site_origin=origin(settings.PAYMENTS_PUBLIC_SITE_ORIGIN),
            staff_origin=origin(settings.PAYMENTS_PUBLIC_STAFF_ORIGIN)
            if settings.PAYMENTS_PUBLIC_STAFF_ORIGIN
            else "",
            invoice_prefix=prefix,
            invoice_start=start,
            invoice_end=end,
            lookup_grant=grant,
            username=settings.HALYK_EPAY_INVOICE_USERNAME,
            password=settings.HALYK_EPAY_INVOICE_PASSWORD,
        )


@dataclass(frozen=True)
class XPaymentConfig:
    api_key: str = field(repr=False)
    account_id: str
    webhook_secret: str = field(repr=False)

    @property
    def merchant_scope(self):
        return hashlib.sha256(("xpayment:production:" + self.account_id).encode()).hexdigest()

    @classmethod
    def from_settings(cls, *, require_gate=True):
        if require_gate and not settings.XPAYMENT_ENABLED:
            raise ProviderError("xpayment_disabled")
        if require_gate and not settings.XPAYMENT_PROTOCOL_VERIFIED:
            raise ProviderError("xpayment_protocol_not_verified")
        key = settings.XPAYMENT_API_KEY
        account = settings.XPAYMENT_ACCOUNT_ID
        secret = settings.XPAYMENT_WEBHOOK_SECRET
        if not key or not account or not secret:
            raise ProviderError("payment_configuration_missing")
        try:
            valid_account = str(UUID(account)) == account
        except (ValueError, TypeError, AttributeError):
            valid_account = False
        if not re.fullmatch(r"xdev_[A-Za-z0-9_-]+", key) or not valid_account or len(secret) < 32:
            raise ProviderError("payment_configuration_invalid")
        return cls(api_key=key, account_id=account, webhook_secret=secret)
