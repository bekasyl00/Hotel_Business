import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import Audit, User

from .jobs import claim, create_bank_link, enqueue, finish
from .models import PaymentAttempt, PaymentEvent, PaymentJob, RefundRequest
from .payment_services import apply_transaction, checkout_matches
from .providers.base import Checkout, ProviderError, Transaction
from .providers.halyk_epay import HalykProvider, checkout_url
from .refund_services import process_refund
from .services import apply_cancellation, booking_payment_data, has_paid_booking
from .tests import fixture

BANK = dict(
    PAYMENT_PROVIDER="halyk_epay",
    HALYK_EPAY_ENV="sandbox",
    HALYK_EPAY_PROTOCOL_VERIFIED=True,
    HALYK_EPAY_CLIENT_ID="fixture",
    HALYK_EPAY_CLIENT_SECRET="fixture-only",
    HALYK_EPAY_SHOP_ID="shop",
    HALYK_EPAY_TERMINAL_ID="terminal",
    HALYK_EPAY_LOOKUP_GRANT="client_credentials",
    HALYK_EPAY_INVOICE_START=700000,
    HALYK_EPAY_INVOICE_END=700999,
    HALYK_EPAY_INVOICE_PREFIX="2611",
    PAYMENTS_PUBLIC_API_ORIGIN="https://api.example.test",
    PAYMENTS_PUBLIC_SITE_ORIGIN="https://site.example.test",
    PAYMENTS_PUBLIC_STAFF_ORIGIN="https://staff.example.test",
)


def evidence(payment, **changes):
    return replace(
        Transaction(
            transaction_id="transaction-1",
            invoice_id=payment.invoice_id,
            terminal_id=payment.terminal_id,
            account_id=payment.account_id,
            amount=Decimal(payment.amount),
            currency="KZT",
            status="CHARGE",
            occurred_at=timezone.now(),
        ),
        **changes,
    )


def checkout(payment):
    return Checkout(
        link_id="00000000-0000-4000-8000-000000000001",
        invoice_id=payment.invoice_id,
        shop_id=payment.shop_id,
        terminal_id=payment.terminal_id,
        account_id="",
        amount=Decimal(payment.amount),
        currency="KZT",
        status="ACTIVE",
        url="https://testepay.homebank.kz/api/redirect/invoice-link/00000000-0000-4000-8000-000000000001",
    )


@override_settings(**BANK)
class BankTests(TestCase):
    def setUp(self):
        self.resort, self.booking, self.manager = fixture()
        self.booking.status = "pending"
        self.booking.hold_expires_at = timezone.now() + timedelta(minutes=30)
        self.booking.save()
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        session = self.client.session
        session["guest_owner"] = self.booking.owner
        session.save()
        self.payload = {
            "bookingId": self.booking.pk,
            "requestKey": str(uuid.uuid4()),
            "locale": "ru",
        }

    def create(self, **extra):
        return self.client.post(
            "/api/payments/checkouts",
            {**self.payload, **extra},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )

    def payment(self):
        response = self.create()
        self.assertEqual(response.status_code, 202, response.content)
        return PaymentAttempt.objects.get(pk=response.json()["id"])

    def test_checkout_snapshot_idempotency_and_no_contacts_or_url_input(self):
        p = self.payment()
        self.assertEqual(p.amount, self.booking.snapshot["total"])
        self.assertEqual(self.create().json()["id"], p.pk)
        self.assertEqual(self.create(requestKey=str(uuid.uuid4())).json()["id"], p.pk)
        self.assertEqual(self.create(amount=1).status_code, 422)
        self.assertEqual(self.create(returnUrl="https://attacker.test").status_code, 422)
        self.assertEqual(self.create(invoicePhone="+77000000000").status_code, 422)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertEqual(PaymentJob.objects.filter(kind="create").count(), 1)

    def test_csrf_owner_and_invalid_bearer(self):
        self.assertEqual(
            self.client.post("/api/payments/checkouts", self.payload, format="json").status_code,
            403,
        )
        p = self.payment()
        stranger = APIClient()
        self.assertEqual(stranger.get(f"/api/payments/{p.pk}").status_code, 404)
        self.assertEqual(
            self.client.get(
                f"/api/payments/{p.pk}", HTTP_AUTHORIZATION="Bearer invalid"
            ).status_code,
            401,
        )
        self.assertEqual(self.client.get(f"/api/v1/payments/{p.pk}").status_code, 200)
        self.assertIn("no-store", self.client.get(f"/api/payments/{p.pk}")["Cache-Control"])

    def test_staff_cannot_pay_website_order_and_manager_scope(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/payments/staff/checkouts",
            self.payload,
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 403)
        self.booking.source = "staff"
        self.booking.save()
        response = self.client.post(
            "/api/payments/staff/checkouts",
            self.payload,
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 202)
        outsider = User.objects.create(username="outside", resort_id=None)
        self.client.force_authenticate(outsider)
        self.assertEqual(
            self.client.get("/api/payments/staff/" + response.json()["id"]).status_code, 403
        )

    def test_bank_charge_confirms_once_and_checkin_uses_common_payment(self):
        p = self.payment()
        before = self.booking.version
        apply_transaction(p.pk, evidence(p))
        apply_transaction(p.pk, evidence(p))
        self.booking.refresh_from_db()
        p.refresh_from_db()
        self.assertEqual(self.booking.status, "confirmed")
        self.assertEqual(self.booking.version, before + 1)
        self.assertEqual(PaymentEvent.objects.filter(applied=True).count(), 1)
        self.assertEqual(Audit.objects.filter(action="payment_confirmed").count(), 1)
        self.assertTrue(has_paid_booking(self.booking))
        self.assertEqual(booking_payment_data(self.booking)["provider"], "halyk_epay")
        apply_transaction(p.pk, evidence(p, status="REJECT"))
        p.refresh_from_db()
        self.assertEqual(p.status, "succeeded")

    def test_untrusted_callback_never_confirms_and_get_never_calls_bank(self):
        p = self.payment()
        with patch.object(HalykProvider, "lookup_payment") as bank:
            self.client.post(
                "/api/v1/payments/providers/halyk/callback",
                {"invoiceId": p.invoice_id, "status": "CHARGE", "amount": p.amount},
                format="json",
            )
            self.client.get(f"/api/payments/{p.pk}")
            bank.assert_not_called()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")
        self.assertEqual(PaymentJob.objects.filter(payment=p, kind="verify").count(), 1)
        self.assertEqual(
            self.client.post(
                "/api/payments/providers/halyk/callback", {"padding": "x" * 17000}, format="json"
            ).status_code,
            413,
        )

    def test_auth_refund_zero_verification_is_not_a_charge(self):
        p = self.payment()
        for status in ["AUTH", "NEW", "FINGERPRINT", "VERIFIED", "FAILED", "REFUND"]:
            apply_transaction(p.pk, evidence(p, status=status))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")
        self.assertFalse(PaymentEvent.objects.filter(applied=True).exists())

    def test_amount_identity_mismatch_extra_charge_and_expiry(self):
        p = self.payment()
        apply_transaction(p.pk, evidence(p, amount=Decimal("1")))
        p.refresh_from_db()
        self.assertEqual(p.reconciliation_reason, "bank_amount_mismatch")
        self.assertEqual(PaymentEvent.objects.count(), 1)
        self.assertFalse(PaymentEvent.objects.first().applied)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")
        apply_transaction(p.pk, evidence(p, transaction_id="charge-2", terminal_id="wrong"))
        p.refresh_from_db()
        self.assertEqual(p.reconciliation_reason, "bank_identity_mismatch")

    def test_late_charge_is_recorded_without_restoring_inventory(self):
        p = self.payment()
        self.booking.hold_expires_at = timezone.now() - timedelta(seconds=1)
        self.booking.save()
        apply_transaction(p.pk, evidence(p))
        self.booking.refresh_from_db()
        p.refresh_from_db()
        self.assertEqual(self.booking.status, "expired")
        self.assertEqual(p.reconciliation_reason, "late_charge")
        self.assertEqual(PaymentEvent.objects.count(), 1)
        self.assertFalse(PaymentEvent.objects.first().applied)
        self.assertTrue(PaymentJob.objects.filter(kind="deactivate").exists())

    def test_additional_charge_is_not_counted_twice(self):
        p = self.payment()
        apply_transaction(p.pk, evidence(p))
        apply_transaction(p.pk, evidence(p, transaction_id="charge-2"))
        p.refresh_from_db()
        self.assertEqual(p.reconciliation_reason, "additional_charge")
        self.assertEqual(PaymentEvent.objects.count(), 2)
        self.assertEqual(PaymentEvent.objects.filter(applied=True).count(), 1)

    def test_cancellation_and_refund_request_roll_back_together(self):
        p = self.payment()
        apply_transaction(p.pk, evidence(p))
        self.booking.refresh_from_db()
        with self.assertRaises(RuntimeError), transaction.atomic():
            apply_cancellation(self.booking, self.manager)
            raise RuntimeError("rollback")
        self.assertFalse(RefundRequest.objects.exists())
        preview = apply_cancellation(self.booking, self.manager)
        self.assertEqual(preview["refundStatus"], "queued")
        refund = RefundRequest.objects.get()
        self.assertEqual(refund.amount, p.amount)
        self.assertFalse(has_paid_booking(self.booking))
        with (
            patch.object(HalykProvider, "request_refund") as post,
            patch.object(HalykProvider, "lookup_payment") as lookup,
        ):
            from .payment_services import configuration

            provider = HalykProvider(configuration())
            process_refund(p, provider)
            lookup.return_value = None
            with self.assertRaises(ProviderError):
                process_refund(p, provider, verify=False)
            self.assertEqual(post.call_count, 1)
            lookup.return_value = evidence(
                p,
                status="REFUND",
                amount=Decimal(0),
                original_amount=Decimal(p.amount),
                refunded_amount=Decimal(p.amount),
            )
            process_refund(p, provider, verify=True)
        refund.refresh_from_db()
        self.assertEqual(refund.status, "succeeded")

    def test_simulator_cannot_bypass_bank_checkout(self):
        self.payment()
        response = self.client.post(
            "/api/payments/demo",
            {"bookingId": self.booking.pk, "requestId": str(uuid.uuid4()), "outcome": "success"},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 409)

    def test_recover_sms_error_without_duplicate_invoice(self):
        p = self.payment()
        from .payment_services import configuration

        provider = HalykProvider(configuration())
        with (
            patch.object(provider, "find_checkout", side_effect=[None, checkout(p)]),
            patch.object(
                provider,
                "create_checkout",
                side_effect=ProviderError("bank_http_error", ambiguous=True),
            ) as create,
        ):
            create_bank_link(p, provider)
            create.assert_called_once()
        p.refresh_from_db()
        self.assertEqual(p.status, "pending")
        self.assertTrue(p.checkout_url)
        self.assertTrue(checkout_matches(p, checkout(p)))

    def test_ambiguous_creation_is_never_reposted(self):
        p = self.payment()
        p.creation_started_at = timezone.now()
        p.save()
        from .payment_services import configuration

        provider = HalykProvider(configuration())
        with (
            patch.object(provider, "find_checkout", return_value=None),
            patch.object(provider, "create_checkout") as create,
        ):
            with self.assertRaises(ProviderError):
                create_bank_link(p, provider)
            create.assert_not_called()

    def test_lease_recovery_does_not_allow_stale_finisher(self):
        p = self.payment()
        old = claim()
        PaymentJob.objects.filter(pk=old.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        current = claim()
        self.assertNotEqual(old.lease_token, current.lease_token)
        finish(old)
        current.refresh_from_db()
        self.assertEqual(current.state, "running")
        finish(current)
        current.refresh_from_db()
        self.assertEqual(current.state, "done")
        enqueue(p, "create")
        self.assertEqual(PaymentJob.objects.count(), 1)

    def test_analytics_separates_bank_and_simulator(self):
        p = self.payment()
        apply_transaction(p.pk, evidence(p))
        self.client.force_authenticate(self.manager)
        report = self.client.get("/api/analytics?paymentMode=sandbox").json()
        self.assertEqual(report["totals"]["grossReceived"], p.amount)
        self.assertEqual(
            self.client.get("/api/analytics?paymentMode=demo").json()["totals"]["grossReceived"], 0
        )
        self.assertEqual(report["byRoom"][0]["grossReceived"], p.amount)

    def test_checkout_host_allowlist_and_production_gate(self):
        for url in [
            "http://testepay.homebank.kz/api/redirect/invoice-link/00000000-0000-4000-8000-000000000001",
            "https://attacker.test/",
            "https://testepay.homebank.kz@attacker.test/",
        ]:
            with self.assertRaises(ProviderError):
                checkout_url(url)
        with self.settings(HALYK_EPAY_ENV="production"):
            self.assertFalse(self.client.get("/api/payments/config").json()["available"])
            self.assertEqual(self.create().status_code, 503)

    def test_contract_and_recorded_provider_shapes(self):
        root = Path(__file__).resolve().parents[2] / "docs/contracts"
        contract = json.loads((root / "payments.openapi.yaml").read_text())
        response = self.create()
        schema = contract["components"]["schemas"]["Payment"]
        self.assertEqual(set(response.json()), set(schema["required"]))
        self.assertIn(response.json()["status"], schema["properties"]["status"]["enum"])
        from .payment_services import configuration

        provider = HalykProvider(configuration())
        fixtures = json.loads((root / "fixtures/halyk-sandbox.json").read_text())
        with (
            patch.object(provider, "_token", return_value="fixture-only"),
            patch.object(provider, "_request", return_value=fixtures["emptyLookup"]),
        ):
            self.assertIsNone(provider.find_checkout("700001"))
        active = provider._checkout(fixtures["activeLink"])
        self.assertEqual(active.account_id, "")
        self.assertEqual(active.status, "ACTIVE")
        with (
            patch.object(provider, "_token", return_value="fixture-only"),
            patch.object(provider, "_request", return_value=fixtures["rejected"]),
        ):
            rejected = provider.lookup_payment("700001")
            self.assertEqual(rejected.status, "REJECT")
            self.assertEqual(rejected.account_id, "fixture-account")

    def test_new_charge_cannot_clear_unresolved_financial_exception(self):
        p = self.payment()
        apply_transaction(p.pk, evidence(p, amount=Decimal(1)))
        apply_transaction(p.pk, evidence(p, transaction_id="second-charge"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")
        self.assertEqual(PaymentEvent.objects.count(), 2)
        self.assertFalse(PaymentEvent.objects.filter(applied=True).exists())

    @override_settings(PAYMENTS_SCHEDULER_SECRET="test-scheduler-" + "a" * 32)
    def test_scheduler_auth_and_closed_gate(self):
        with patch("commerce.scheduler.schedule_due") as schedule:
            self.assertEqual(self.client.post("/internal/payments/tick").status_code, 401)
            schedule.assert_not_called()
            with self.settings(HALYK_EPAY_PROTOCOL_VERIFIED=False):
                response = self.client.post(
                    "/internal/payments/tick",
                    HTTP_AUTHORIZATION="Bearer test-scheduler-" + "a" * 32,
                )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["bankEnabled"])
            schedule.assert_called_once()

    def test_partial_zero_and_minimum_refund(self):
        from .refund_services import queue_refund

        for amount, expected in [
            (25200, "queued"),
            (0, "succeeded"),
            (7, "reconciliation_required"),
        ]:
            with self.subTest(amount=amount), transaction.atomic():
                p = self.payment()
                result = queue_refund(
                    p,
                    {
                        "refundAmount": amount,
                        "refundPercent": 70 if amount else 0,
                        "actorKind": "guest",
                    },
                )
                self.assertEqual(result["refundStatus"], expected)
                self.assertEqual(PaymentJob.objects.filter(kind="refund").exists(), amount >= 10)
                transaction.set_rollback(True)


@override_settings(**BANK)
class BankConcurrencyTests(TransactionTestCase):
    def test_worker_network_runs_outside_database_transaction(self):
        from .jobs import run_one
        from .payment_services import configuration

        _, booking, _ = fixture()
        booking.status = "pending"
        booking.hold_expires_at = timezone.now() + timedelta(minutes=30)
        booking.save()
        p = PaymentAttempt.objects.create(
            booking=booking,
            request_key=uuid.uuid4(),
            fingerprint="f",
            actor_binding="a",
            merchant_scope="scope",
            invoice_id="700002",
            shop_id="shop",
            terminal_id="terminal",
            account_id="account",
            amount=36000,
            expires_at=booking.hold_expires_at,
        )
        provider = HalykProvider(configuration())

        def lookup(_):
            self.assertFalse(connections["default"].in_atomic_block)
            return checkout(p)

        enqueue(p, "create")
        with patch.object(provider, "find_checkout", side_effect=lookup):
            self.assertTrue(run_one(provider=provider))
        p.refresh_from_db()
        self.assertEqual(p.status, "pending")

    def test_two_workers_apply_one_charge(self):
        resort, booking, _ = fixture()
        booking.status = "pending"
        booking.hold_expires_at = timezone.now() + timedelta(minutes=30)
        booking.save()
        p = PaymentAttempt.objects.create(
            booking=booking,
            request_key=uuid.uuid4(),
            fingerprint="f",
            actor_binding="a",
            merchant_scope="scope",
            invoice_id="700001",
            shop_id="shop",
            terminal_id="terminal",
            account_id="account",
            amount=36000,
            expires_at=booking.hold_expires_at,
        )
        barrier = Barrier(2)

        def work():
            close_old_connections()
            try:
                barrier.wait()
                apply_transaction(p.pk, evidence(p))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: work(), range(2)))
        booking.refresh_from_db()
        self.assertEqual(booking.status, "confirmed")
        self.assertEqual(booking.version, 2)
        self.assertEqual(PaymentEvent.objects.count(), 1)
