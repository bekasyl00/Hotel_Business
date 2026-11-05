import io
import json
import urllib.error
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .providers.base import ProviderError
from .providers.xpayment import API, MAX_RESPONSE_BYTES, XPaymentProvider, checkout_url

ACCOUNT = "00000000-0000-4000-8000-000000000001"
ORDER = "00000000-0000-4000-8000-000000000002"
PAYMENT = "00000000-0000-4000-8000-000000000003"
REFUND = "00000000-0000-4000-8000-000000000004"
INTENT = "00000000-0000-4000-8000-000000000005"
OTHER = "00000000-0000-4000-8000-000000000006"
NOW = "2026-11-06T14:00:00+05:00"
QR = "https://qr.kaspi.kz/55308082630746899169618031642188672381021"


def payment_row(**changes):
    return {
        "payment_id": PAYMENT,
        "merchant_order_id": ORDER,
        "user_id": ACCOUNT,
        "amount": 12000,
        "currency": "KZT",
        "status": "PENDING",
        "completed_at": NOW,
        **changes,
    }


def refund_row(**changes):
    return {
        "refund_id": REFUND,
        "payment_id": PAYMENT,
        "user_id": ACCOUNT,
        "amount": 8400,
        "reason": "tynys-refund:" + INTENT,
        "status": "COMPLETED",
        "completed_at": NOW,
        **changes,
    }


def page(*rows, **changes):
    return {"data": list(rows), "has_more": False, "next_cursor": "", **changes}


def link_row(**changes):
    return {
        "payment_id": PAYMENT,
        "qr_token": QR,
        "expire_date": NOW,
        "status": "QrTokenCreated",
        "ext_tran_id": "QR14893934009",
        "qr_operation_id": 14893934009,
        **changes,
    }


class XPaymentProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = XPaymentProvider(
            SimpleNamespace(
                api_key="xdev_fixture_never_live",
                account_id=ACCOUNT,
                webhook_secret="fixture-never-live",
            )
        )
        self.payment = SimpleNamespace(
            invoice_id=ORDER,
            amount=12000,
            currency="KZT",
            invoice_link_id=PAYMENT,
        )
        self.refund = SimpleNamespace(amount=8400, pk=INTENT)

    def replies(self, *values):
        return patch.object(self.provider, "_request", side_effect=list(values))

    def test_link_requires_independent_identity_and_amount_check(self):
        with self.replies(link_row(), payment_row()) as request:
            checkout = self.provider.create_checkout(self.payment)
        self.assertEqual(checkout.link_id, PAYMENT)
        self.assertEqual(checkout.invoice_id, ORDER)
        self.assertEqual(checkout.amount, Decimal("12000"))
        self.assertEqual(checkout.url, QR)
        self.assertEqual(checkout.status, "ACTIVE")
        self.assertEqual(checkout.expires_at.isoformat(), NOW)
        self.assertEqual(
            (checkout.shop_id, checkout.terminal_id, checkout.account_id), ("", "", "")
        )
        self.assertEqual(request.call_args_list[0].args, ("POST", API + "/payments/link"))
        self.assertEqual(
            request.call_args_list[0].kwargs,
            {
                "body": {"amount": Decimal("12000"), "merchant_order_id": ORDER},
                "mutation": True,
            },
        )
        self.assertEqual(request.call_args_list[1].args, ("GET", API + "/payments/" + PAYMENT))

    def test_create_mismatches_are_ambiguous_never_success(self):
        invalid = [
            {"amount": 11999},
            {"currency": "USD"},
            {"user_id": OTHER},
            {"merchant_order_id": OTHER},
            {"payment_id": OTHER},
            {"status": "paid"},
            {"status": "QrTokenCreated"},
        ]
        for change in invalid:
            with self.subTest(change=change), self.replies(link_row(), payment_row(**change)):
                with self.assertRaises(ProviderError) as error:
                    self.provider.create_checkout(self.payment)
                self.assertTrue(error.exception.ambiguous)

    def test_create_rejects_untrusted_urls_naive_expiry_and_unknown_link_state(self):
        for change in [
            {"qr_token": "https://attacker.test/42"},
            {"expire_date": "2026-11-06T14:00:00"},
            {"status": "COMPLETED"},
            {"payment_id": "not-a-uuid"},
            {"qr_token": None},
            {"expire_date": "never"},
        ]:
            with self.subTest(change=change), self.replies(link_row(**change)) as request:
                with self.assertRaises(ProviderError) as error:
                    self.provider.create_checkout(self.payment)
                self.assertTrue(error.exception.ambiguous)
                self.assertEqual(request.call_count, 1)

    def test_qr_allowlist_rejects_credentials_ports_subdomains_queries_and_whitespace(self):
        self.assertEqual(checkout_url(QR), QR)
        for value in [
            "http://qr.kaspi.kz/12",
            "https://qr.kaspi.kz:443/12",
            "https://qr.kaspi.kz.attacker.test/12",
            "https://user@qr.kaspi.kz/12",
            "https://qr.kaspi.kz/12?url=evil",
            "https://qr.kaspi.kz/12#part",
            "https://qr.kaspi.kz/../12",
            QR + "\n",
            " " + QR,
        ]:
            with self.subTest(value=value), self.assertRaises(ProviderError):
                checkout_url(value)

    def test_recovery_is_read_only_and_does_not_invent_a_qr_url_or_expiry(self):
        with self.replies(page(payment_row()), payment_row()) as request:
            checkout = self.provider.find_checkout(ORDER)
        self.assertEqual(checkout.url, "")
        self.assertIsNone(checkout.expires_at)
        self.assertEqual(checkout.link_id, PAYMENT)
        self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))
        self.assertEqual(
            request.call_args_list[0].args[1], API + "/payments?merchant_order_id=" + ORDER
        )

    def test_empty_recovery_is_none_but_pagination_duplicates_or_malformed_lists_fail(self):
        with self.replies(page()):
            self.assertIsNone(self.provider.find_checkout(ORDER))
        for response in [
            page(payment_row(), payment_row()),
            page(has_more=True),
            page(payment_row(), next_cursor="more"),
            {"data": []},
            page(data=None),
            page(data={}),
            [],
        ]:
            with self.subTest(response=response), self.replies(response) as request:
                with self.assertRaises(ProviderError):
                    self.provider.find_checkout(ORDER)
                self.assertEqual(request.call_count, 1)

    def test_lookup_checks_list_and_detail_ownership_order_and_money(self):
        for changes in [
            {"user_id": OTHER},
            {"merchant_order_id": OTHER},
            {"payment_id": OTHER},
            {"amount": 14000},
            {"currency": "USD"},
        ]:
            with (
                self.subTest(changes=changes),
                self.replies(page(payment_row()), payment_row(**changes)),
            ):
                with self.assertRaises(ProviderError):
                    self.provider.lookup_payment(ORDER)
        with self.replies(page(payment_row(user_id=OTHER))) as request:
            with self.assertRaises(ProviderError):
                self.provider.lookup_payment(ORDER)
            self.assertEqual(request.call_count, 1)

    def test_only_completed_becomes_charge_and_requires_aware_completion_time(self):
        statuses = {
            "PENDING": "ACTIVE",
            "PROCESSING": "ACTIVE",
            "COMPLETED": "CHARGE",
            "CANCELLED": "CANCELLED",
            "FAILED": "FAILED",
            "EXPIRED": "EXPIRED",
        }
        for status, expected in statuses.items():
            with (
                self.subTest(status=status),
                self.replies(page(payment_row()), payment_row(status=status)),
            ):
                evidence = self.provider.lookup_payment(ORDER)
                self.assertEqual(evidence.status, expected)
                self.assertEqual(evidence.transaction_id, PAYMENT)
                self.assertEqual((evidence.terminal_id, evidence.account_id), ("", ""))
        for status, date in [
            ("PAID", NOW),
            ("COMPLETED", None),
            ("COMPLETED", "2026-11-06T14:00:00"),
        ]:
            with (
                self.subTest(status=status, date=date),
                self.replies(
                    page(payment_row()),
                    payment_row(status=status, completed_at=date),
                ),
            ):
                with self.assertRaises(ProviderError):
                    self.provider.lookup_payment(ORDER)

    def test_money_and_identifiers_are_not_coerced_or_rounded(self):
        for amount in [
            True,
            "12000",
            0,
            -1,
            Decimal("NaN"),
            Decimal("Infinity"),
            Decimal("1.001"),
            10**16,
        ]:
            with self.subTest(amount=amount), self.replies(page(payment_row(amount=amount))):
                with self.assertRaises(ProviderError):
                    self.provider.lookup_payment(ORDER)
        for identifier in [
            ORDER.upper().replace("00000000", "ABCDEFAB", 1),
            "{" + ORDER + "}",
            ORDER.replace("-", ""),
            "../",
        ]:
            with (
                self.subTest(identifier=identifier),
                patch.object(self.provider, "_request") as request,
            ):
                with self.assertRaises(ProviderError):
                    self.provider.lookup_payment(identifier)
                request.assert_not_called()

    def test_cancel_is_scoped_to_verified_payment_and_never_uses_arbitrary_url(self):
        with self.replies(payment_row(), payment_row(status="CANCELLED")) as request:
            self.assertIsNone(self.provider.deactivate_checkout(PAYMENT))
        self.assertEqual(
            request.call_args_list[1].args, ("POST", API + "/payments/" + PAYMENT + "/cancel")
        )
        self.assertTrue(request.call_args_list[1].kwargs["mutation"])
        with self.replies(payment_row(status="COMPLETED")) as request:
            self.provider.deactivate_checkout(PAYMENT)
            self.assertEqual(request.call_count, 1)
        with self.replies(payment_row(user_id=OTHER)) as request:
            with self.assertRaises(ProviderError):
                self.provider.deactivate_checkout(PAYMENT)
            self.assertEqual(request.call_count, 1)

    def test_refund_request_uses_exact_local_reason_not_unsupported_idempotency(self):
        with self.replies(
            payment_row(status="COMPLETED"), page(), refund_row(status="PENDING")
        ) as request:
            self.assertIsNone(self.provider.request_refund(PAYMENT, 8400, INTENT))
        self.assertEqual(
            request.call_args_list[-1].args, ("POST", API + "/payments/" + PAYMENT + "/refund")
        )
        self.assertEqual(
            request.call_args_list[-1].kwargs,
            {
                "mutation": True,
                "body": {"amount": Decimal(8400), "reason": "tynys-refund:" + INTENT},
            },
        )

    def test_matching_existing_refund_is_not_submitted_twice(self):
        for status in ["PENDING", "PROCESSING", "COMPLETED", "FAILED"]:
            with (
                self.subTest(status=status),
                self.replies(
                    payment_row(status="COMPLETED"),
                    page(refund_row(status=status)),
                ) as request,
            ):
                self.provider.request_refund(PAYMENT, 8400, INTENT)
                self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))

    def test_unexpected_refund_or_over_refund_prevents_new_post(self):
        for rows in [
            page(refund_row(reason="manual")),
            page(refund_row(), refund_row()),
            page(has_more=True),
        ]:
            with (
                self.subTest(rows=rows),
                self.replies(payment_row(status="COMPLETED"), rows) as request,
            ):
                with self.assertRaises(ProviderError):
                    self.provider.request_refund(PAYMENT, 8400, INTENT)
                self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))
        with self.replies(payment_row(status="COMPLETED")) as request:
            with self.assertRaises(ProviderError):
                self.provider.request_refund(PAYMENT, 12001, INTENT)
            self.assertEqual(request.call_count, 1)

    def test_refund_post_mismatch_is_ambiguous(self):
        with self.replies(payment_row(status="COMPLETED"), page(), refund_row(user_id=OTHER)):
            with self.assertRaises(ProviderError) as error:
                self.provider.request_refund(PAYMENT, 8400, INTENT)
            self.assertTrue(error.exception.ambiguous)

    def test_partial_and_full_refunds_are_independently_reconciled(self):
        for amount, remaining in [(8400, 3600), (12000, 0)]:
            self.refund.amount = amount
            with (
                self.subTest(amount=amount),
                self.replies(
                    page(payment_row()),
                    payment_row(status="COMPLETED"),
                    page(refund_row(amount=amount)),
                ) as request,
            ):
                evidence = self.provider.lookup_refund(self.payment, self.refund)
                self.assertEqual(evidence.status, "REFUND")
                self.assertEqual(evidence.amount, Decimal(remaining))
                self.assertEqual(evidence.original_amount, Decimal(12000))
                self.assertEqual(evidence.refunded_amount, Decimal(amount))
                self.assertEqual(evidence.transaction_id, PAYMENT)
                self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))

    def test_refund_requires_exact_independent_payment_and_refund_identity(self):
        for change in [
            {"user_id": OTHER},
            {"payment_id": OTHER},
            {"reason": "manual"},
            {"amount": 1},
            {"refund_id": "bad"},
            {"status": "SUCCESS"},
            {"completed_at": "2026-11-06T14:00:00"},
        ]:
            with (
                self.subTest(change=change),
                self.replies(
                    page(payment_row()),
                    payment_row(status="COMPLETED"),
                    page(refund_row(**change)),
                ),
            ):
                with self.assertRaises(ProviderError):
                    self.provider.lookup_refund(self.payment, self.refund)
        self.payment.invoice_link_id = OTHER
        with self.replies(page(payment_row()), payment_row(status="COMPLETED")):
            with self.assertRaises(ProviderError):
                self.provider.lookup_refund(self.payment, self.refund)

    def test_pending_missing_failed_and_duplicated_refunds_do_not_complete(self):
        for rows in [
            page(),
            page(refund_row(status="PENDING")),
            page(refund_row(status="PROCESSING")),
        ]:
            with (
                self.subTest(rows=rows),
                self.replies(page(payment_row()), payment_row(status="COMPLETED"), rows),
            ):
                self.assertIsNone(self.provider.lookup_refund(self.payment, self.refund))
        for rows in [
            page(refund_row(status="FAILED")),
            page(refund_row(), refund_row()),
            page(has_more=True),
        ]:
            with (
                self.subTest(rows=rows),
                self.replies(page(payment_row()), payment_row(status="COMPLETED"), rows),
            ):
                with self.assertRaises(ProviderError):
                    self.provider.lookup_refund(self.payment, self.refund)

    def test_transport_preserves_decimal_amounts_and_has_a_bounded_timeout(self):
        self.provider.opener.open = Mock(return_value=io.BytesIO(b'{"amount":12000.70}'))
        result = self.provider._request(
            "POST",
            API + "/payments/link",
            body={"amount": Decimal("12000.70")},
            mutation=True,
        )
        self.assertEqual(result["amount"], Decimal("12000.70"))
        request = self.provider.opener.open.call_args.args[0]
        self.assertEqual(
            json.loads(request.data, parse_float=Decimal)["amount"], Decimal("12000.70")
        )
        self.assertEqual(self.provider.opener.open.call_args.kwargs, {"timeout": 10})
        self.assertEqual(request.get_header("Authorization"), "Bearer xdev_fixture_never_live")

    def test_transport_rejects_bad_or_large_json_and_duplicate_keys(self):
        for body in [
            b"[]",
            b'{"amount":NaN}',
            b'{"status":"PENDING","status":"COMPLETED"}',
            b"bad",
            b"x" * (MAX_RESPONSE_BYTES + 1),
        ]:
            with self.subTest(body=body[:80]):
                self.provider.opener.open = Mock(return_value=io.BytesIO(body))
                with self.assertRaises(ProviderError) as error:
                    self.provider._request("POST", API + "/payments/link", body={}, mutation=True)
                self.assertEqual(error.exception.code, "bank_response_invalid")
                self.assertTrue(error.exception.ambiguous)

    def test_transport_does_not_retry_or_disclose_payload_on_http_timeout_and_redirect(self):
        for error in [
            urllib.error.HTTPError(API, 302, "secret", {}, io.BytesIO(b"secret")),
            urllib.error.HTTPError(API, 500, "secret", {}, io.BytesIO(b"secret")),
            urllib.error.URLError("secret"),
            TimeoutError("secret"),
        ]:
            with self.subTest(error=type(error).__name__):
                self.provider.opener.open = Mock(side_effect=error)
                with self.assertRaises(ProviderError) as result:
                    self.provider._request("POST", API + "/payments/link", body={}, mutation=True)
                self.assertTrue(result.exception.ambiguous)
                self.assertNotIn("secret", str(result.exception))
                self.assertEqual(self.provider.opener.open.call_count, 1)
        self.assertTrue(
            any(type(handler).__name__ == "NoRedirect" for handler in self.provider.opener.handlers)
        )

    def test_transport_does_not_send_credentials_to_another_origin(self):
        self.provider.opener.open = Mock()
        for url in [
            "https://attacker.test/v1/payments",
            "http://api.xpayment.kz/v1/payments",
            "https://api.xpayment.kz.attacker.test/v1/payments",
        ]:
            with self.subTest(url=url), self.assertRaises(ProviderError):
                self.provider._request("GET", url)
        self.provider.opener.open.assert_not_called()
