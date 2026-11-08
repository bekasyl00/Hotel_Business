from dataclasses import replace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .provider_config import XPaymentConfig
from .providers.base import ProviderError
from .providers.xpayment import XPaymentProvider
from .test_xpayment_provider import (
    ACCOUNT,
    INTENT,
    ORDER,
    PAYMENT,
    link_row,
    page,
    payment_row,
    refund_row,
)


class XPaymentV2Tests(SimpleTestCase):
    def setUp(self):
        self.config = XPaymentConfig(
            api_key="xapi_fixture_never_live",
            account_id=ACCOUNT,
            webhook_secret="test-only-" + "s" * 32,
            api_version="v2",
            device_name="MainCashier",
        )
        self.provider = XPaymentProvider(self.config)

    def test_v2_create_and_lookup_use_named_device(self):
        from types import SimpleNamespace

        with patch.object(
            self.provider,
            "_request",
            side_effect=[
                link_row(),
                payment_row(device_name="maincashier"),
            ],
        ) as request:
            checkout = self.provider.create_checkout(
                SimpleNamespace(invoice_id=ORDER, amount=12000, currency="KZT")
            )
        self.assertEqual(checkout.link_id, PAYMENT)
        self.assertEqual(
            request.call_args_list[0].args[1], "https://api.xpayment.kz/v2/payments/link"
        )
        self.assertEqual(request.call_args_list[0].kwargs["body"]["device_name"], "MainCashier")
        with patch.object(
            self.provider,
            "_request",
            side_effect=[
                page(payment_row(device_name="MainCashier")),
                payment_row(device_name="MainCashier"),
            ],
        ) as request:
            self.provider.lookup_payment(ORDER)
        self.assertIn("device_name=MainCashier", request.call_args_list[0].args[1])

    def test_v2_missing_or_other_cashier_is_rejected(self):
        for device in [None, "Another", "", 12]:
            with self.subTest(device=device), self.assertRaises(ProviderError):
                self.provider._payment(payment_row(device_name=device))

    def test_observed_live_alias_accepts_real_create_and_independent_lookup(self):
        from types import SimpleNamespace

        row = payment_row(device_name="MainCashier", environment="live")
        with patch.object(
            self.provider, "_request", side_effect=[link_row(environment="live"), row]
        ) as request:
            checkout = self.provider.create_checkout(
                SimpleNamespace(invoice_id=ORDER, amount=12000, currency="KZT")
            )
        self.assertEqual(checkout.link_id, PAYMENT)
        self.assertTrue(checkout.url.startswith("https://qr.kaspi.kz/"))
        self.assertEqual(request.call_args_list[1].args[0], "GET")
        row = {**row, "status": "COMPLETED"}
        with patch.object(self.provider, "_request", side_effect=[page(row), row]):
            fact = self.provider.lookup_payment(ORDER)
        self.assertEqual(fact.status, "CHARGE")
        self.assertEqual(fact.amount, 12000)
        self.assertEqual(self.config.environment, "production")

    def test_live_alias_refund_requires_independent_exact_amount_verification(self):
        from types import SimpleNamespace

        row = payment_row(
            device_name="MainCashier", environment="live", status="PARTIALLY_REFUNDED"
        )
        refunds = {"data": [refund_row(environment="live")], "total": 1}
        with patch.object(self.provider, "_request", side_effect=[page(row), row, refunds]):
            fact = self.provider.lookup_refund(
                SimpleNamespace(
                    invoice_id=ORDER, amount=12000, currency="KZT", invoice_link_id=PAYMENT
                ),
                SimpleNamespace(pk=INTENT, amount=8400),
            )
        self.assertEqual(fact.status, "REFUND")
        self.assertEqual(fact.refunded_amount, 8400)
        self.assertEqual(fact.amount, 3600)

    def test_response_environment_alias_is_strict_and_never_crosses_sandbox(self):
        from types import SimpleNamespace

        sandbox = XPaymentProvider(
            replace(
                self.config, environment="sandbox", device_name="test", api_key="xapi_test_fixture"
            )
        )
        for provider, rejected in [
            (self.provider, ["sandbox", "LIVE", "live ", "test", None, {}, []]),
            (sandbox, ["live", "production", "Sandbox", None, {}, []]),
        ]:
            valid_row = payment_row(
                device_name=provider.config.device_name, environment=provider.config.environment
            )
            charge = provider._payment(valid_row)
            for value in rejected:
                with self.subTest(environment=provider.config.environment, rejected=value):
                    with self.assertRaises(ProviderError):
                        provider._payment({**valid_row, "environment": value})
                    with (
                        patch.object(provider, "_request", return_value=link_row(environment=value)),
                        self.assertRaises(ProviderError),
                    ):
                        provider.create_checkout(
                            SimpleNamespace(invoice_id=ORDER, amount=12000, currency="KZT")
                        )
                    with self.assertRaises(ProviderError):
                        provider._refund(
                            refund_row(environment=value),
                            charge,
                            amount=8400,
                            reason="tynys-refund:" + INTENT,
                        )

    def test_observed_sandbox_qr_status_url_and_environment(self):
        from types import SimpleNamespace

        provider = XPaymentProvider(
            replace(
                self.config, environment="sandbox", device_name="test", api_key="xapi_test_fixture"
            )
        )
        url = "https://xpayment.kz/sandbox/qr/123456789"
        row = payment_row(device_name="test", environment="sandbox", status="QR_TOKEN_CREATED")
        link = link_row(environment="sandbox", status="QR_TOKEN_CREATED", qr_token=url)
        with patch.object(provider, "_request", side_effect=[link, row]):
            checkout = provider.create_checkout(
                SimpleNamespace(invoice_id=ORDER, amount=12000, currency="KZT")
            )
        self.assertEqual(checkout.url, url)
        self.assertEqual(checkout.status, "ACTIVE")
        for change in [
            {"environment": "production"},
            {"qr_token": "https://qr.kaspi.kz/123"},
            {"qr_token": url + "?redirect=evil"},
        ]:
            with (
                self.subTest(change=change),
                patch.object(provider, "_request", return_value={**link, **change}),
            ):
                with self.assertRaises(ProviderError):
                    provider.create_checkout(
                        SimpleNamespace(invoice_id=ORDER, amount=12000, currency="KZT")
                    )
        with self.assertRaises(ProviderError):
            self.provider._payment(row)
        with self.assertRaises(ProviderError):
            provider._payment({**row, "environment": "production"})

    def test_credentials_match_version_and_environment(self):
        for change in [
            {"api_key": "xdev_fixture"},
            {"api_key": "xapi_test_fixture"},
            {"api_version": "v3"},
            {"environment": "test"},
            {"environment": "live"},
            {"device_name": ""},
            {"device_name": "wrong/name"},
            {"device_name": "test"},
            {"environment": "sandbox"},
            {"environment": "sandbox", "api_key": "xapi_test_fixture"},
        ]:
            with self.subTest(change=change), self.assertRaises(ProviderError):
                XPaymentProvider(replace(self.config, **change))
        sandbox = replace(
            self.config, environment="sandbox", device_name="test", api_key="xapi_test_fixture"
        )
        XPaymentProvider(sandbox)
        self.assertNotEqual(sandbox.merchant_scope, self.config.merchant_scope)
        self.assertNotEqual(
            replace(self.config, device_name="Other").merchant_scope, self.config.merchant_scope
        )
        self.assertEqual(
            replace(self.config, device_name="maincashier").merchant_scope,
            self.config.merchant_scope,
        )
        self.assertNotIn(self.config.api_key, repr(self.config))

    def test_config_loader_has_no_sandbox_bypass_to_production(self):
        with (
            override_settings(
                XPAYMENT_API_VERSION="v2",
                XPAYMENT_ENV="production",
                XPAYMENT_DEVICE_NAME="MainCashier",
                XPAYMENT_API_KEY="xapi_test_fixture",
                XPAYMENT_ACCOUNT_ID=ACCOUNT,
                XPAYMENT_WEBHOOK_SECRET="s" * 32,
            ),
            self.assertRaises(ProviderError),
        ):
            XPaymentConfig.from_settings(require_gate=False)

    def test_sandbox_acceptance_never_opens_production(self):
        with (
            override_settings(
                XPAYMENT_ENABLED=True,
                XPAYMENT_SANDBOX_PROTOCOL_VERIFIED=True,
                XPAYMENT_PROTOCOL_VERIFIED=False,
                XPAYMENT_ENV="production",
                XPAYMENT_API_VERSION="v2",
                XPAYMENT_DEVICE_NAME="MainCashier",
                XPAYMENT_API_KEY="xapi_fixture_live",
                XPAYMENT_ACCOUNT_ID=ACCOUNT,
                XPAYMENT_WEBHOOK_SECRET="s" * 32,
            ),
            self.assertRaises(ProviderError) as error,
        ):
            XPaymentConfig.from_settings()
        self.assertEqual(error.exception.code, "xpayment_protocol_not_verified")

    def test_v2_transport_refuses_v1_and_other_hosts_before_transmitting_key(self):
        with patch.object(self.provider.opener, "open") as send:
            for url in ["https://api.xpayment.kz/v1/payments", "https://attacker.test/v2/payments"]:
                with self.assertRaises(ProviderError):
                    self.provider._request("GET", url)
            send.assert_not_called()

    def test_observed_refund_total_envelope_requires_complete_results(self):
        self.assertEqual(self.provider._one_page({"data": [], "total": 0}, allow_total=True), [])
        for row in [
            {"data": [], "total": 1},
            {"data": [], "total": False},
            {"data": [], "total": 0, "has_more": True},
            {"data": [], "total": 0, "next_cursor": "more"},
            {"data": []},
        ]:
            with self.subTest(row=row), self.assertRaises(ProviderError):
                self.provider._one_page(row, allow_total=True)
        with self.assertRaises(ProviderError):
            self.provider._one_page({"data": [], "total": 0})

    def test_refunded_payment_never_becomes_new_charge_or_duplicate_refund(self):
        from types import SimpleNamespace

        for status, amount in [("REFUNDED", 12000), ("PARTIALLY_REFUNDED", 8400)]:
            row = payment_row(device_name="MainCashier", status=status)
            refunds = {"data": [refund_row(amount=amount)], "total": 1}
            self.assertEqual(self.provider._payment(row).status, "REFUND")
            with patch.object(self.provider, "_request", side_effect=[row, refunds]) as request:
                self.provider.request_refund(PAYMENT, amount, INTENT)
                self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))
            with patch.object(self.provider, "_request", side_effect=[page(row), row, refunds]):
                fact = self.provider.lookup_refund(
                    SimpleNamespace(
                        invoice_id=ORDER, amount=12000, currency="KZT", invoice_link_id=PAYMENT
                    ),
                    SimpleNamespace(pk=INTENT, amount=amount),
                )
            self.assertEqual(fact.refunded_amount, amount)
            self.assertEqual(fact.original_amount, 12000)
            self.assertEqual(fact.amount, 12000 - amount)
            with patch.object(
                self.provider, "_request", side_effect=[row, {"data": [], "total": 0}]
            ) as request:
                with self.assertRaises(ProviderError):
                    self.provider.request_refund(PAYMENT, amount, INTENT)
                self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))
