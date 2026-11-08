"""XPayment v1/v2 API. Signed notifications are never payment evidence.

Contracts: https://xpayment.kz/openapi/xpayment-api-v{1,2}.json
Sandbox credentials are isolated; link/refund POSTs are never blindly retried.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .base import Checkout, ProviderError, Transaction

API = "https://api.xpayment.kz/v1"
MAX_RESPONSE_BYTES = 1024 * 1024
PAYMENT_STATUSES = {
    "QR_TOKEN_CREATED": "ACTIVE",
    "PENDING": "ACTIVE",
    "PROCESSING": "ACTIVE",
    "COMPLETED": "CHARGE",
    "REFUNDED": "REFUND",
    "PARTIALLY_REFUNDED": "REFUND",
    "FAILED": "FAILED",
    "EXPIRED": "EXPIRED",
    "CANCELLED": "CANCELLED",
}
REFUND_STATUSES = {"PENDING", "PROCESSING", "COMPLETED", "FAILED"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def identifier(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError):
        raise ProviderError("bank_response_invalid") from None


def money(value):
    try:
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise ValueError
        amount = Decimal(value)
        if (
            not amount.is_finite()
            or amount <= 0
            or amount > 10**15
            or amount != amount.quantize(Decimal("0.01"))
        ):
            raise ValueError
        return amount
    except (ValueError, InvalidOperation):
        raise ProviderError("bank_response_invalid") from None


def aware_datetime(value):
    try:
        parsed = parse_datetime(value) if isinstance(value, str) else None
        if not isinstance(parsed, datetime) or timezone.is_naive(parsed):
            raise ValueError
        return parsed
    except (ValueError, TypeError, OverflowError):
        raise ProviderError("bank_response_invalid") from None


def checkout_url(value, *, environment="production"):
    pattern = (
        r"https://xpayment\.kz/sandbox/qr/[0-9]{1,200}"
        if environment == "sandbox"
        else r"https://qr\.kaspi\.kz/[0-9]{1,200}"
    )
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ProviderError("bank_checkout_url_invalid")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError


def _encode_body(body):
    # These requests are flat objects. Preserve decimal KZT without binary floats.
    return (
        "{"
        + ",".join(
            json.dumps(key)
            + ":"
            + (
                format(money(value), "f")
                if isinstance(value, Decimal)
                else json.dumps(value, allow_nan=False)
            )
            for key, value in body.items()
        )
        + "}"
    ).encode("utf-8")


class XPaymentProvider:
    def __init__(self, config):
        self.config = config
        identifier(config.account_id)
        config.validate_transport()
        self.api = config.api_url
        self.opener = urllib.request.build_opener(NoRedirect())

    def _request(self, method, url, *, body=None, mutation=False):
        if not url.startswith(self.api + "/"):
            raise ProviderError("bank_host_invalid")
        headers = {
            "Authorization": "Bearer " + self.config.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            request = urllib.request.Request(
                url,
                method=method,
                headers=headers,
                data=_encode_body(body) if body is not None else None,
            )
            with self.opener.open(request, timeout=10) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError
            parsed = (
                json.loads(
                    raw,
                    parse_float=Decimal,
                    parse_constant=_reject_constant,
                    object_pairs_hook=_unique_object,
                )
                if raw
                else {}
            )
            if not isinstance(parsed, dict):
                raise ValueError
            return parsed
        except urllib.error.HTTPError as exc:
            raise ProviderError(
                "bank_http_error",
                retryable=exc.code >= 500 or exc.code == 429,
                ambiguous=mutation,
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("bank_unavailable", retryable=True, ambiguous=mutation) from None
        except (ValueError, TypeError, RecursionError):
            raise ProviderError("bank_response_invalid", ambiguous=mutation) from None

    def _payment(self, row, *, order_id=None, payment_id=None, final_time=True):
        if not isinstance(row, dict):
            raise ProviderError("bank_response_invalid")
        try:
            actual_id = identifier(row["payment_id"])
            actual_order = identifier(row["merchant_order_id"])
            if (
                identifier(row["user_id"]) != self.config.account_id
                or row.get("environment", "production") != self.config.environment
                or (order_id is not None and actual_order != order_id)
                or (payment_id is not None and actual_id != payment_id)
                or row["currency"] != "KZT"
                or (
                    self.config.api_version == "v2"
                    and (
                        not isinstance(row.get("device_name"), str)
                        or row["device_name"].lower() != self.config.device_name.lower()
                    )
                )
            ):
                raise ProviderError("bank_payment_mismatch")
            status = PAYMENT_STATUSES[row["status"]]
            completed_at = (
                aware_datetime(row["completed_at"]) if status == "CHARGE" and final_time else None
            )
            return Transaction(
                transaction_id=actual_id,
                invoice_id=actual_order,
                terminal_id="",
                account_id="",
                amount=money(row["amount"]),
                currency="KZT",
                status=status,
                occurred_at=completed_at,
            )
        except (KeyError, TypeError):
            raise ProviderError("bank_response_invalid") from None

    def _get_payment(self, payment_id, *, order_id=None):
        payment_id = identifier(payment_id)
        return self._payment(
            self._request("GET", self.api + "/payments/" + payment_id),
            order_id=order_id,
            payment_id=payment_id,
        )

    def _one_page(self, response, *, allow_total=False):
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise ProviderError("bank_response_invalid")
        # The live per-payment refund endpoint returns {data, total}, although
        # its OpenAPI currently describes the paginated list envelope.
        complete_total = (
            allow_total
            and "has_more" not in response
            and type(response.get("total")) is int
            and response["total"] == len(response["data"])
        )
        if (response.get("has_more") is not False and not complete_total) or response.get(
            "next_cursor", ""
        ) != "":
            raise ProviderError("bank_invoice_collision")
        if len(response["data"]) > 1:
            raise ProviderError("bank_invoice_collision")
        return response["data"]

    def _find_payment(self, order_id):
        order_id = identifier(order_id)
        query = {"merchant_order_id": order_id}
        if self.config.api_version == "v2":
            query["device_name"] = self.config.device_name
        rows = self._one_page(
            self._request("GET", self.api + "/payments?" + urllib.parse.urlencode(query))
        )
        if not rows:
            return None
        listed = self._payment(rows[0], order_id=order_id, final_time=False)
        actual = self._get_payment(listed.transaction_id, order_id=order_id)
        if actual.amount != listed.amount:
            raise ProviderError("bank_payment_mismatch")
        return actual

    def _checkout(self, payment, *, url="", expires_at=None):
        return Checkout(
            link_id=payment.transaction_id,
            invoice_id=payment.invoice_id,
            shop_id="",
            terminal_id="",
            account_id="",
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            url=url,
            expires_at=expires_at,
        )

    def create_checkout(self, payment):
        order_id, amount = identifier(payment.invoice_id), money(payment.amount)
        if payment.currency != "KZT":
            raise ProviderError("bank_payment_mismatch")
        body = {"amount": amount, "merchant_order_id": order_id}
        if self.config.api_version == "v2":
            body["device_name"] = self.config.device_name
        row = self._request(
            "POST",
            self.api + "/payments/link",
            mutation=True,
            body=body,
        )
        try:
            if not isinstance(row, dict) or row.get("status") not in (
                "QrTokenCreated",
                "QR_TOKEN_CREATED",
            ):
                raise ProviderError("bank_response_invalid")
            payment_id = identifier(row["payment_id"])
            if row.get("environment", "production") != self.config.environment:
                raise ProviderError("bank_payment_mismatch")
            url = checkout_url(row["qr_token"], environment=self.config.environment)
            expiry = aware_datetime(row["expire_date"])
            actual = self._get_payment(payment_id, order_id=order_id)
            if actual.amount != amount:
                raise ProviderError("bank_payment_mismatch")
            return self._checkout(actual, url=url, expires_at=expiry)
        except (KeyError, TypeError):
            raise ProviderError("bank_response_invalid", ambiguous=True) from None
        except ProviderError as exc:
            # The link may already exist even if parsing or independent lookup failed.
            raise ProviderError(exc.code, retryable=exc.retryable, ambiguous=True) from None

    def find_checkout(self, invoice_id):
        payment = self._find_payment(invoice_id)
        # GET/list do not expose qr_token or expire_date. Never recreate an existing link.
        return self._checkout(payment) if payment else None

    def lookup_payment(self, invoice_id):
        return self._find_payment(invoice_id)

    def deactivate_checkout(self, link_id):
        payment_id = identifier(link_id)
        actual = self._get_payment(payment_id)
        if actual.status != "ACTIVE":
            return
        row = self._request(
            "POST",
            self.api + "/payments/" + payment_id + "/cancel",
            mutation=True,
            body={"reason": "Tynys booking hold expired"},
        )
        try:
            self._payment(row, order_id=actual.invoice_id, payment_id=payment_id)
        except ProviderError as exc:
            raise ProviderError(exc.code, retryable=exc.retryable, ambiguous=True) from None
        # A cancel response is not proof that a QR can no longer be paid. Jobs re-query.

    def _refund(self, row, charge, *, amount, reason):
        if not isinstance(row, dict):
            raise ProviderError("bank_response_invalid")
        try:
            identifier(row["refund_id"])
            if (
                identifier(row["user_id"]) != self.config.account_id
                or identifier(row["payment_id"]) != charge.transaction_id
                or row.get("environment", "production") != self.config.environment
                or row["reason"] != reason
                or money(row["amount"]) != amount
                or amount > charge.amount
            ):
                raise ProviderError("bank_refund_mismatch")
            if row["status"] not in REFUND_STATUSES:
                raise ProviderError("bank_response_invalid")
            completed_at = (
                aware_datetime(row["completed_at"]) if row["status"] == "COMPLETED" else None
            )
            return row["status"], completed_at
        except (KeyError, TypeError):
            raise ProviderError("bank_response_invalid") from None

    def _refunds(self, charge):
        return self._one_page(
            self._request("GET", self.api + "/payments/" + charge.transaction_id + "/refunds"),
            allow_total=True,
        )

    def request_refund(self, transaction_id, amount, external_id):
        amount = money(amount)
        reason = "tynys-refund:" + identifier(external_id)
        charge = self._get_payment(transaction_id)
        if charge.status not in ("CHARGE", "REFUND") or amount > charge.amount:
            raise ProviderError("bank_refund_mismatch")
        rows = self._refunds(charge)
        if rows:
            self._refund(rows[0], charge, amount=amount, reason=reason)
            return
        if charge.status != "CHARGE":
            raise ProviderError("bank_refund_mismatch")
        row = self._request(
            "POST",
            self.api + "/payments/" + charge.transaction_id + "/refund",
            mutation=True,
            body={"amount": amount, "reason": reason},
        )
        try:
            self._refund(row, charge, amount=amount, reason=reason)
        except ProviderError as exc:
            raise ProviderError(exc.code, retryable=exc.retryable, ambiguous=True) from None

    def lookup_refund(self, payment, refund):
        charge = self._find_payment(payment.invoice_id)
        if charge is None or charge.status not in ("CHARGE", "REFUND"):
            raise ProviderError("bank_refund_unverified", retryable=True)
        if (
            charge.amount != money(payment.amount)
            or charge.currency != payment.currency
            or (payment.invoice_link_id and charge.transaction_id != payment.invoice_link_id)
        ):
            raise ProviderError("bank_refund_mismatch")
        amount = money(refund.amount)
        reason = "tynys-refund:" + identifier(str(refund.pk))
        rows = self._refunds(charge)
        if not rows:
            return None
        status, completed_at = self._refund(rows[0], charge, amount=amount, reason=reason)
        if status == "FAILED":
            raise ProviderError("bank_refund_failed")
        if status != "COMPLETED":
            return None
        return Transaction(
            transaction_id=charge.transaction_id,
            invoice_id=charge.invoice_id,
            terminal_id="",
            account_id="",
            amount=charge.amount - amount,
            currency="KZT",
            status="REFUND",
            occurred_at=completed_at,
            original_amount=charge.amount,
            refunded_amount=amount,
        )
