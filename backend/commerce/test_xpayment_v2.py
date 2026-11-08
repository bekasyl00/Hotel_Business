from dataclasses import replace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .provider_config import XPaymentConfig
from .providers.base import ProviderError
from .providers.xpayment import XPaymentProvider
from .test_xpayment_provider import ACCOUNT, ORDER, PAYMENT, link_row, page, payment_row


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
