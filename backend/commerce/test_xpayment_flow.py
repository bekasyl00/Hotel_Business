import hashlib
import hmac
import json
import uuid
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from . import test_bank_payments as bank_tests
from .jobs import create_bank_link, enqueue, run_one, verify_bank_payment
from .models import PaymentAttempt, PaymentEvent, RefundRequest, WebhookDelivery
from .payment_services import apply_transaction
from .provider_config import XPaymentConfig
from .provider_registry import provider_for
from .providers.base import ProviderError
from .providers.halyk_epay import HalykProvider
from .providers.xpayment import XPaymentProvider
from .refund_services import process_refund
from .services import apply_cancellation, booking_payment_data
from .test_bank_payments import BANK, checkout, evidence

XPAYMENT = {
    **BANK,
    "PAYMENT_PROVIDER": "xpayment",
    "XPAYMENT_ENABLED": True,
    "XPAYMENT_PROTOCOL_VERIFIED": True,
    "XPAYMENT_API_KEY": "xdev_fixture_only",
    "XPAYMENT_API_VERSION": "v1",
    "XPAYMENT_ENV": "production",
    "XPAYMENT_DEVICE_NAME": "",
    "XPAYMENT_ACCOUNT_ID": "00000000-0000-4000-8000-000000000001",
    "XPAYMENT_WEBHOOK_SECRET": "fictional-webhook-secret-" + "a" * 32,
}


@override_settings(**XPAYMENT)
class XPaymentFlowTests(TestCase):
    create = bank_tests.BankTests.create
    payment = bank_tests.BankTests.payment

    def setUp(self):
        bank_tests.BankTests.setUp(self)
        scope = self.settings(XPAYMENT_PRODUCTION_RESORT_IDS=[str(self.resort.pk)])
        scope.enable()
        self.addCleanup(scope.disable)

    def linked(self):
        p = self.payment()
        p.invoice_link_id = str(uuid.uuid4())
        p.status = "pending"
        p.save()
        return p

    def fact(self, payment, **changes):
        return evidence(payment, transaction_id=payment.invoice_link_id, **changes)

    def test_explicit_gates_no_fallback_no_network(self):
        for key in ("XPAYMENT_ENABLED", "XPAYMENT_PROTOCOL_VERIFIED"):
            with (
                self.subTest(key=key),
                self.settings(**{key: False}),
                patch.object(XPaymentProvider, "_request") as remote,
            ):
                config = self.client.get("/api/payments/config").json()
                self.assertEqual(config["provider"], "xpayment")
                self.assertEqual(config["environment"], "production")
                self.assertFalse(config["available"])
                self.assertEqual(self.create().status_code, 503)
                remote.assert_not_called()
        self.assertFalse(PaymentAttempt.objects.exists())

    def test_production_scope_advertises_and_allows_only_named_resort(self):
        config = self.client.get("/api/payments/config").json()
        self.assertTrue(config["available"])
        self.assertEqual(config["productionResortIds"], [str(self.resort.pk)])
        with patch.object(XPaymentProvider, "_request") as remote:
            p = self.payment()
            self.assertEqual(p.booking.resort_id, self.resort.pk)
            self.assertEqual(p.environment, "production")
            self.assertEqual(p.jobs.filter(kind="create").count(), 1)
            remote.assert_not_called()

    def test_unlisted_or_empty_production_scope_creates_no_attempt_or_job(self):
        from .models import PaymentJob

        for allowed in ([], [str(uuid.uuid4())]):
            with (
                self.subTest(allowed=allowed),
                self.settings(XPAYMENT_PRODUCTION_RESORT_IDS=allowed),
                patch.object(XPaymentProvider, "_request") as remote,
            ):
                config = self.client.get("/api/payments/config").json()
                self.assertEqual(config["productionResortIds"], allowed)
                self.assertEqual(config["available"], bool(allowed))
                if not allowed:
                    self.assertEqual(config["reason"], "xpayment_production_resorts_missing")
                response = self.create()
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "payment_resort_not_enabled")
                remote.assert_not_called()
                self.assertFalse(PaymentAttempt.objects.exists())
                self.assertFalse(PaymentJob.objects.exists())

    def test_scope_removal_preserves_existing_attempt_and_settlement(self):
        p = self.linked()
        with self.settings(XPAYMENT_PRODUCTION_RESORT_IDS=[]):
            self.assertFalse(self.client.get("/api/payments/config").json()["available"])
            self.assertEqual(self.create().json()["id"], p.pk)
            self.assertIsInstance(provider_for(p), XPaymentProvider)
            apply_transaction(p.pk, self.fact(p))
            p.booking.refresh_from_db()
            self.assertEqual(p.booking.status, "confirmed")
            self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_scope_removal_skips_unstarted_create_but_preserves_started_recovery(self):
        p = self.payment()
        with (
            self.settings(XPAYMENT_PRODUCTION_RESORT_IDS=[]),
            patch.object(XPaymentProvider, "_request") as remote,
        ):
            self.assertFalse(run_one(payment_id=p.pk))
            remote.assert_not_called()
            self.assertEqual(p.jobs.get(kind="create").attempts, 0)
            p.creation_started_at = timezone.now()
            p.save(update_fields=["creation_started_at"])
            link = replace(checkout(p), url="https://qr.kaspi.kz/123456789")
            with (
                patch.object(XPaymentProvider, "find_checkout", return_value=link),
                patch.object(XPaymentProvider, "create_checkout") as create,
            ):
                self.assertTrue(run_one(payment_id=p.pk))
                create.assert_not_called()
            p.refresh_from_db()
            self.assertEqual(p.invoice_link_id, link.link_id)
            self.assertEqual(p.jobs.get(kind="create").state, "done")

    def test_scope_removal_keeps_verify_jobs_for_existing_provider_links(self):
        p = self.linked()
        p.jobs.filter(kind="create").update(state="done")
        enqueue(p, "verify")
        link = replace(checkout(p), link_id=p.invoice_link_id)
        with (
            self.settings(XPAYMENT_PRODUCTION_RESORT_IDS=[]),
            patch.object(XPaymentProvider, "find_checkout", return_value=link),
            patch.object(XPaymentProvider, "lookup_payment", return_value=self.fact(p)),
            patch.object(XPaymentProvider, "_request") as remote,
        ):
            self.assertTrue(run_one(payment_id=p.pk))
            remote.assert_not_called()
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "confirmed")

    @override_settings(
        XPAYMENT_ENV="sandbox",
        XPAYMENT_API_KEY="xdev_test_fixture_only",
        XPAYMENT_SANDBOX_PROTOCOL_VERIFIED=True,
    )
    def test_empty_production_scope_does_not_restrict_sandbox(self):
        with self.settings(XPAYMENT_PRODUCTION_RESORT_IDS=[]):
            config = self.client.get("/api/payments/config").json()
            self.assertTrue(config["available"])
            self.assertNotIn("productionResortIds", config)
            self.assertEqual(self.payment().environment, "sandbox")

    def test_freezes_provider_and_preserves_existing_payment_after_switch(self):
        p = self.payment()
        self.assertEqual(p.provider, "xpayment")
        self.assertEqual(p.environment, "production")
        self.assertEqual(str(uuid.UUID(p.invoice_id)), p.invoice_id)
        self.assertEqual(
            p.shop_id + p.terminal_id + p.account_id + p.recipient_phone + p.recipient_email, ""
        )
        with self.settings(PAYMENT_PROVIDER="halyk_epay", HALYK_EPAY_PROTOCOL_VERIFIED=False):
            self.assertEqual(self.create().json()["id"], p.pk)
            self.assertIsInstance(provider_for(p), XPaymentProvider)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertEqual(booking_payment_data(p.booking)["paymentMode"], "production")

    def test_database_rejects_unknown_payment_environment(self):
        p = self.payment()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAttempt.objects.filter(pk=p.pk).update(environment="fictional")

    @override_settings(
        XPAYMENT_API_VERSION="v2",
        XPAYMENT_ENV="sandbox",
        XPAYMENT_DEVICE_NAME="test",
        XPAYMENT_API_KEY="xapi_test_fixture_only",
        XPAYMENT_SANDBOX_PROTOCOL_VERIFIED=True,
    )
    def test_sandbox_is_frozen_and_never_counted_as_real_money(self):
        self.assertEqual(
            self.client.get("/api/payments/config").json(),
            {
                "provider": "xpayment",
                "environment": "sandbox",
                "available": True,
            },
        )
        p = self.linked()
        self.assertEqual(p.environment, "sandbox")
        self.assertIsInstance(provider_for(p), XPaymentProvider)
        self.assertEqual(self.webhook(p).status_code, 422)
        self.assertEqual(self.webhook(p, environment="production").status_code, 422)
        self.assertEqual(self.webhook(p, environment="live").status_code, 422)
        self.assertEqual(self.webhook(p, environment="sandbox").status_code, 200)
        apply_transaction(p.pk, self.fact(p))
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "confirmed")
        self.client.force_authenticate(self.manager)
        for mode, expected in [("sandbox", p.amount), ("production", 0)]:
            self.assertEqual(
                self.client.get("/api/analytics?paymentMode=" + mode).json()["totals"][
                    "grossReceived"
                ],
                expected,
            )
        with self.settings(
            XPAYMENT_ENV="production",
            XPAYMENT_DEVICE_NAME="Main",
            XPAYMENT_API_KEY="xapi_fixture_live",
        ):
            with self.assertRaises(ProviderError):
                provider_for(p)
            self.assertFalse(run_one(payment_id=p.pk))

    def test_production_rejects_sandbox_callback(self):
        self.assertEqual(self.webhook(self.linked(), environment="sandbox").status_code, 422)
        self.assertFalse(WebhookDelivery.objects.exists())

    def test_merchant_rotation_does_not_redirect_old_jobs(self):
        p = self.linked()
        with self.settings(XPAYMENT_ACCOUNT_ID=str(uuid.uuid4())):
            with self.assertRaises(ProviderError):
                provider_for(p)
            self.assertFalse(run_one(payment_id=p.pk))
        self.assertEqual(p.jobs.get(kind="create").attempts, 0)

    def test_old_halyk_jobs_survive_new_default_and_closed_new_payment_gate(self):
        with self.settings(PAYMENT_PROVIDER="halyk_epay"):
            p = self.payment()
        p.invoice_link_id = checkout(p).link_id
        p.save()
        p.jobs.filter(kind="create").update(state="done")
        enqueue(p, "verify")
        with (
            self.settings(HALYK_EPAY_PROTOCOL_VERIFIED=False),
            patch.object(HalykProvider, "find_checkout", return_value=checkout(p)),
            patch.object(HalykProvider, "lookup_payment", return_value=evidence(p)),
            patch.object(XPaymentProvider, "_request") as wrong,
        ):
            self.assertTrue(run_one(payment_id=p.pk))
            wrong.assert_not_called()
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "confirmed")

    def test_creation_gate_preserves_unstarted_jobs_while_verify_can_run(self):
        p = self.payment()
        with (
            self.settings(XPAYMENT_ENABLED=False),
            patch.object(XPaymentProvider, "_request") as remote,
        ):
            self.assertFalse(run_one(payment_id=p.pk))
            remote.assert_not_called()
        self.assertEqual(p.jobs.get(kind="create").attempts, 0)

    def test_link_deadline_shortens_hold_and_recovery_preserves_url(self):
        p = self.payment()
        link = replace(
            checkout(p),
            url="https://qr.kaspi.kz/123456789",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        provider = Mock()
        provider.find_checkout.return_value = None
        provider.create_checkout.return_value = link
        create_bank_link(p, provider)
        p.refresh_from_db()
        p.booking.refresh_from_db()
        self.assertEqual(p.expires_at, link.expires_at)
        self.assertEqual(p.booking.hold_expires_at, link.expires_at)
        provider.find_checkout.return_value = replace(link, url="", expires_at=None)
        create_bank_link(p, provider)
        self.assertEqual(provider.create_checkout.call_count, 1)
        p.refresh_from_db()
        self.assertEqual(p.checkout_url, link.url)

    def test_recovery_without_link_does_not_create_duplicate_and_can_verify(self):
        p = self.payment()
        link = replace(checkout(p), url="")
        provider = Mock()
        provider.find_checkout.return_value = link
        provider.lookup_payment.return_value = evidence(p, transaction_id=link.link_id)
        verify_bank_payment(p, provider)
        p.refresh_from_db()
        self.assertEqual(p.status, "succeeded")
        self.assertEqual(p.invoice_link_id, link.link_id)
        self.assertEqual(p.checkout_url, "")
        provider.create_checkout.assert_not_called()

    def webhook(self, p, *, delivery=None, signature=True, raw=None, **changes):
        data = {
            "event": "payment.completed",
            "event_version": "1",
            "source": "xpayment",
            "delivery_id": delivery or str(uuid.uuid4()),
            "attempt_number": 1,
            "payment_id": p.invoice_link_id,
            "merchant_order_id": p.invoice_id,
            "created_at": timezone.now().isoformat(),
            **changes,
        }
        body = raw or json.dumps(data).encode()
        sig = (
            hmac.new(XPAYMENT["XPAYMENT_WEBHOOK_SECRET"].encode(), body, hashlib.sha256).hexdigest()
            if signature
            else "0" * 64
        )
        return self.client.post(
            "/api/v1/payments/providers/xpayment/callback",
            body,
            content_type="application/json",
            HTTP_X_XPAYMENT_SIGNATURE=sig,
        )

    def test_authenticated_simulated_and_replayed_webhook_is_only_a_signal(self):
        p = self.linked()
        delivery = str(uuid.uuid4())
        with patch.object(XPaymentProvider, "_request") as remote:
            self.assertEqual(self.webhook(p, delivery=delivery, amount=p.amount).status_code, 200)
            self.assertEqual(self.webhook(p, delivery=delivery, attempt_number=2).status_code, 200)
            remote.assert_not_called()
        self.assertEqual(WebhookDelivery.objects.count(), 1)
        self.assertEqual(p.jobs.filter(kind="verify").count(), 1)
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "pending")
        self.assertFalse(PaymentEvent.objects.exists())

    def test_signed_live_webhook_only_queues_independent_production_reconciliation(self):
        p = self.linked()
        p.jobs.filter(kind="create").update(state="done")
        delivery = str(uuid.uuid4())
        with patch.object(XPaymentProvider, "_request") as remote:
            self.assertEqual(self.webhook(p, environment="live", delivery=delivery).status_code, 200)
            self.assertEqual(self.webhook(p, environment="live", delivery=delivery).status_code, 200)
            remote.assert_not_called()
        self.assertEqual(WebhookDelivery.objects.count(), 1)
        self.assertFalse(PaymentEvent.objects.exists())
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "pending")
        link = replace(checkout(p), link_id=p.invoice_link_id)
        with (
            patch.object(XPaymentProvider, "find_checkout", return_value=link),
            patch.object(XPaymentProvider, "lookup_payment", return_value=self.fact(p)) as lookup,
        ):
            self.assertTrue(run_one(payment_id=p.pk))
            lookup.assert_called_once_with(p.invoice_id)
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "confirmed")
        self.assertEqual(PaymentEvent.objects.get(applied=True).environment, "production")

    def test_bad_signature_or_reference_never_enqueues(self):
        p = self.linked()
        self.assertEqual(self.webhook(p, signature=False).status_code, 401)
        self.assertEqual(self.webhook(p, payment_id=str(uuid.uuid4())).status_code, 422)
        self.assertEqual(self.webhook(p, source="test").status_code, 422)
        self.assertEqual(self.webhook(p, event=[]).status_code, 422)
        self.assertEqual(self.webhook(p, raw=b"x" * 17000).status_code, 413)
        self.assertFalse(WebhookDelivery.objects.exists())
        self.assertFalse(p.jobs.filter(kind="verify").exists())

    def test_charge_matches_bound_provider_id_and_confirms_once(self):
        p = self.linked()
        apply_transaction(p.pk, self.fact(p))
        apply_transaction(p.pk, self.fact(p))
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "confirmed")
        self.assertEqual(PaymentEvent.objects.filter(applied=True).count(), 1)
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get("/api/analytics?paymentMode=production").json()["totals"][
                "grossReceived"
            ],
            p.amount,
        )
        self.assertEqual(
            self.client.get("/api/analytics?paymentMode=sandbox").json()["totals"]["grossReceived"],
            0,
        )

    def test_wrong_provider_payment_id_cannot_confirm(self):
        p = self.linked()
        apply_transaction(p.pk, evidence(p, transaction_id=str(uuid.uuid4())))
        p.booking.refresh_from_db()
        self.assertEqual(p.booking.status, "pending")
        self.assertFalse(PaymentEvent.objects.exists())

    def test_refund_ack_does_not_finalize_and_analytics_isolates_environment(self):
        p = self.linked()
        apply_transaction(p.pk, self.fact(p))
        p.refresh_from_db()
        p.booking.refresh_from_db()
        apply_cancellation(p.booking, self.manager)
        refund = RefundRequest.objects.get(payment=p)
        provider = Mock()
        provider.lookup_payment.return_value = self.fact(p)
        process_refund(p, provider)
        refund.refresh_from_db()
        self.assertEqual(refund.status, "submitted")
        provider.lookup_refund.return_value = self.fact(
            p, status="REFUND", amount=0, original_amount=p.amount, refunded_amount=refund.amount
        )
        process_refund(p, provider, verify=True)
        refund.refresh_from_db()
        self.assertEqual(refund.status, "succeeded")
        self.assertEqual(provider.request_refund.call_count, 1)
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get("/api/analytics?paymentMode=production").json()["totals"]["refunds"],
            refund.amount,
        )
        self.assertEqual(
            self.client.get("/api/analytics?paymentMode=sandbox").json()["totals"]["refunds"], 0
        )

    def test_hard_provider_error_dead_letters_without_repeated_network(self):
        p = self.payment()
        provider = Mock()
        provider.find_checkout.side_effect = ProviderError("bank_invoice_collision")
        self.assertTrue(run_one(payment_id=p.pk, provider=provider))
        self.assertFalse(run_one(payment_id=p.pk, provider=provider))
        self.assertEqual(p.jobs.get(kind="create").state, "dead")
        self.assertEqual(provider.find_checkout.call_count, 1)

    def test_started_create_recovers_after_gate_closed_without_post(self):
        p = self.payment()
        p.creation_started_at = timezone.now()
        p.save()
        with (
            self.settings(XPAYMENT_ENABLED=False),
            patch.object(
                XPaymentProvider, "find_checkout", return_value=replace(checkout(p), url="")
            ),
            patch.object(XPaymentProvider, "create_checkout") as post,
        ):
            self.assertTrue(run_one(payment_id=p.pk))
            post.assert_not_called()
        p.refresh_from_db()
        self.assertEqual(p.invoice_link_id, checkout(p).link_id)
        self.assertEqual(p.jobs.get(kind="create").state, "done")

    def test_configuration_does_not_expose_secrets(self):
        config = XPaymentConfig.from_settings()
        self.assertNotIn(config.api_key, repr(config))
        self.assertNotIn(config.webhook_secret, repr(config))
