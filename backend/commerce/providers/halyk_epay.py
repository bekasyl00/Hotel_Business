"""Halyk invoice-link sandbox. Network results are evidence, never browser assertions."""

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.utils.dateparse import parse_datetime

from .base import Checkout, ProviderError, Transaction

OAUTH = "https://test-epay-oauth.epayment.kz/oauth2/token"
API = "https://test-epay-api.epayment.kz"
SCOPE = "webapi usermanagement email_send verification statement statistics payment"
_TOKENS = {}
_LOCK = threading.Lock()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def decimal(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 10**15:
            raise ValueError
        return amount
    except (ValueError, InvalidOperation):
        raise ProviderError("bank_response_invalid") from None


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ProviderError("bank_response_invalid")
    return value


def checkout_url(value):
    if not isinstance(value, str):
        raise ProviderError("bank_response_invalid")
    value = value.strip()
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "testepay.homebank.kz"
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/api/redirect/invoice-link/[a-fA-F0-9-]{36}", parsed.path)
    ):
        raise ProviderError("bank_checkout_url_invalid")
    return value


class HalykProvider:
    def __init__(self, config):
        self.config = config
        self.opener = urllib.request.build_opener(NoRedirect())

    def _request(self, method, url, *, body=None, token=None, mutation=False):
        if not (url == OAUTH or url.startswith(API + "/")):
            raise ProviderError("bank_host_invalid")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode() if body is not None else None
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(body or {}).encode()
        try:
            with self.opener.open(
                urllib.request.Request(url, data=data, headers=headers, method=method), timeout=10
            ) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ProviderError("bank_response_invalid", ambiguous=mutation)
            return json.loads(raw, parse_float=Decimal) if raw else {}
        except urllib.error.HTTPError as exc:
            # Even HTTP 400 can mean an invoice was created: sandbox code 1079
            # reports SMS failure AFTER persisting the payable invoice.
            raise ProviderError(
                "bank_http_error", retryable=exc.code >= 500 or exc.code == 429, ambiguous=mutation
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("bank_unavailable", retryable=True, ambiguous=mutation) from None
        except (ValueError, TypeError):
            raise ProviderError("bank_response_invalid", ambiguous=mutation) from None

    def _token(self, *, lookup=False):
        c = self.config
        grant = c.lookup_grant if lookup else "client_credentials"
        key = hashlib.sha256(
            f"{c.client_id}:{c.client_secret}:{c.terminal_id}:{grant}".encode()
        ).hexdigest()
        with _LOCK:
            cached = _TOKENS.get(key)
            if cached and cached[1] > time.monotonic():
                return cached[0]
        body = {
            "grant_type": grant,
            "client_id": c.client_id,
            "client_secret": c.client_secret,
            "scope": "api" if grant == "password" else SCOPE,
            "terminal": c.terminal_id,
        }
        if grant == "password":
            body.update(username=c.username, password=c.password)
        response = self._request("POST", OAUTH, body=body)
        token = response.get("access_token") if isinstance(response, dict) else None
        if not isinstance(token, str) or not token or len(token) > 10000:
            raise ProviderError("bank_auth_failed")
        try:
            ttl = min(max(int(response.get("expires_in", 60)) - 30, 0), 600)
        except (ValueError, TypeError):
            raise ProviderError("bank_response_invalid") from None
        with _LOCK:
            _TOKENS[key] = (token, time.monotonic() + ttl)
        return token

    def _checkout(self, row):
        try:
            return Checkout(
                link_id=str(UUID(row["id"])),
                invoice_id=identifier(row["invoice_id"]),
                shop_id=identifier(row["shop_id"]),
                terminal_id=identifier(row["terminal_id"]),
                account_id=str(row.get("account_id", "")),
                amount=decimal(row["amount"]),
                currency=str(row["currency"]),
                url=checkout_url(row["invoice_url"]),
                status=identifier(row["status"]),
            )
        except (KeyError, TypeError, ValueError):
            raise ProviderError("bank_response_invalid") from None

    def create_checkout(self, payment):
        c = self.config
        site = c.staff_origin if payment.booking.source == "staff" else c.site_origin
        if not site:
            raise ProviderError("payment_configuration_missing")
        route = "/staff/bookings" if payment.booking.source == "staff" else "/bookings"
        back = site + route + "?paymentReturn=" + str(payment.pk)
        callback = c.api_origin + "/api/v1/payments/providers/halyk/callback"
        row = self._request(
            "POST",
            API + "/invoice",
            token=self._token(),
            mutation=True,
            body={
                "shop_id": payment.shop_id,
                "account_id": payment.account_id,
                "invoice_id": payment.invoice_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "language": {"ru": "rus", "kk": "kaz", "en": "eng"}[payment.locale],
                "description": "Tynys sandbox booking " + str(payment.booking_id),
                "expire_period": "1d",
                "recipient_contact": payment.recipient_email,
                "recipient_contact_sms": payment.recipient_phone,
                "notifier_contact": "",
                "notifier_contact_sms": "",
                "post_link": callback,
                "failure_post_link": callback,
                "back_link": back,
                "failure_back_link": back,
            },
        )
        return self._checkout(row)

    def find_checkout(self, invoice_id):
        row = self._request(
            "POST",
            API + "/invoice-links",
            token=self._token(lookup=True),
            body={
                "paging": {"skip": 0, "limit": 2},
                "searchParameters": [
                    {"name": "invoice_id", "method": "=", "searchParameter": [invoice_id]}
                ],
                "orderParameters": {"field": "id", "typeOrder": "DESC"},
            },
        )
        if not isinstance(row, dict) or not isinstance(row.get("TotalCount"), int):
            raise ProviderError("bank_response_invalid")
        records = row.get("Records") or []
        if row["TotalCount"] == 0 and not records:
            return None
        if row["TotalCount"] != 1 or not isinstance(records, list) or len(records) != 1:
            raise ProviderError("bank_invoice_collision")
        return self._checkout(records[0])

    def lookup_payment(self, invoice_id):
        row = self._request(
            "GET",
            API + "/check-status/payment/transaction/" + identifier(invoice_id),
            token=self._token(),
        )
        if not isinstance(row, dict):
            raise ProviderError("bank_response_invalid")
        code = str(row.get("resultCode"))
        if code == "102":
            return None
        if code not in ("100", "101", "107"):
            raise ProviderError("bank_verification_unavailable", retryable=code == "103")
        t = row.get("transaction")
        if not isinstance(t, dict):
            if code == "107":
                return None
            raise ProviderError("bank_response_invalid")
        try:
            return Transaction(
                transaction_id=identifier(t["id"]),
                invoice_id=identifier(t["invoiceID"]),
                terminal_id=identifier(t["terminalID"]),
                account_id=str(t.get("accountID", "")),
                amount=decimal(t["amount"]),
                currency=str(t["currency"]),
                status=identifier(t["statusName"]),
                occurred_at=parse_datetime(t.get("createdDate", "")),
                original_amount=decimal(t["orgAmount"]) if "orgAmount" in t else None,
                refunded_amount=decimal(t["payoutAmount"]) if "payoutAmount" in t else None,
            )
        except (KeyError, ValueError, TypeError):
            raise ProviderError("bank_response_invalid") from None

    def deactivate_checkout(self, link_id):
        self._request(
            "PUT",
            API + "/deactivate/invoice-links/" + str(UUID(link_id)),
            token=self._token(lookup=True),
            mutation=True,
        )

    def request_refund(self, transaction_id, amount, external_id):
        if amount < 10:
            raise ProviderError("bank_refund_below_minimum")
        query = urllib.parse.urlencode({"amount": amount, "externalID": identifier(external_id)})
        self._request(
            "POST",
            API + "/operation/" + identifier(transaction_id) + "/refund?" + query,
            token=self._token(),
            mutation=True,
        )
