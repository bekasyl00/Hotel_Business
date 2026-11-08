from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from psycopg.types.range import Range

from booking.errors import Problem
from booking.models import Audit, User
from booking.serializers import booking_data

from . import test_bank_payments as bank
from .models import OnsiteSettlement, RefundRequest
from .payment_services import apply_transaction
from .services import cancellation_preview
from .settlement import freeze_payment_terms, payment_terms


@override_settings(**bank.BANK)
class SettlementTests(TestCase):
    setUp = bank.BankTests.setUp
    create = bank.BankTests.create
    payment = bank.BankTests.payment

    def terms(self, base=280000, percent="10"):
        self.resort.commission_percent = Decimal(percent)
        self.resort.save(update_fields=["commission_percent"])
        terms = freeze_payment_terms(self.resort, base)
        self.booking.snapshot = {**self.booking.snapshot, "total": base, "paymentTerms": terms}
        self.booking.save(update_fields=["snapshot"])
        return terms

    def paid(self):
        self.terms()
        payment = self.payment()
        apply_transaction(payment.pk, bank.evidence(payment))
        self.booking.refresh_from_db()
        return payment

    def login(self, user):
        self.client.force_login(user)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def post(self, path, body):
        return self.client.post(path, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_fee_added_to_base_and_only_fee_collected_and_refunded(self):
        payment = self.paid()
        self.assertEqual(payment.amount, 28000)
        terms = booking_data(self.booking)["paymentTerms"]
        self.assertEqual(
            (terms["total"], terms["onlineAmount"], terms["onsiteAmount"]), (308000, 28000, 280000)
        )
        self.assertEqual(self.booking.status, "confirmed")
        preview = cancellation_preview(self.booking)
        self.assertEqual((preview["refundPercent"], preview["refundAmount"]), (100, 28000))
        self.resort.commission_percent = 20
        self.resort.save()
        self.assertEqual(payment_terms(self.booking), terms)

    def test_legacy_booking_collects_original_full_amount(self):
        payment = self.payment()
        self.assertEqual(payment.amount, 36000)
        self.assertEqual(payment_terms(self.booking)["onsiteAmount"], 0)

    def test_cancelled_refunded_voucher_remains_owned_history_not_valid_ticket(self):
        payment = self.paid()
        self.booking.status = "cancelled"
        self.booking.save(update_fields=["status"])
        RefundRequest.objects.create(
            payment=payment,
            amount=payment.amount,
            percent=100,
            policy={},
            actor_kind="guest",
            status="succeeded",
        )
        response = self.client.get(f"/api/bookings/{self.booking.pk}/voucher")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertEqual(response.json()["refundedAmount"], 28000)

    def test_rounding_and_unconfigured_commission(self):
        self.resort.commission_percent = Decimal("7.25")
        self.assertEqual(freeze_payment_terms(self.resort, 81000)["onlineAmount"], 5873)
        for rate in (None, Decimal(0)):
            self.resort.commission_percent = rate
            with self.assertRaises(Problem):
                freeze_payment_terms(self.resort, 10000)

    def test_owned_voucher_pdf_and_unpaid_or_foreign_denial(self):
        path = f"/api/bookings/{self.booking.pk}/voucher"
        self.assertEqual(self.client.get(path).status_code, 409)
        self.paid()
        data = self.client.get(path).json()
        self.assertEqual(data["onlinePaid"], 28000)
        self.assertEqual(data["paymentTerms"]["onsiteAmount"], 280000)
        response = self.client.get(path + "/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("no-store", response["Cache-Control"])
        self.client.logout()
        self.assertIn(self.client.get(path).status_code, (401, 404))
        other = User.objects.create_user(username="other-tenant", email="other@fictional.test")
        self.login(other)
        self.assertEqual(self.client.get(path).status_code, 403)

    def test_onsite_requires_scope_actual_stay_and_received_ack(self):
        self.paid()
        path = f"/api/bookings/{self.booking.pk}/onsite-payment"
        body = {"version": self.booking.version, "method": "cash", "received": True}
        self.assertEqual(self.post(path, body).status_code, 401)
        self.login(self.manager)
        self.assertEqual(self.post(path, body).status_code, 409)
        today = timezone.localdate()
        self.booking.stay = Range(today, today + timedelta(days=2), "[)")
        self.booking.save(update_fields=["stay"])
        self.assertEqual(self.post(path, {**body, "received": False}).status_code, 422)
        self.assertEqual(self.post(path, {**body, "amount": 1}).status_code, 422)
        self.assertEqual(self.client.post(path, body, format="json").status_code, 403)
        self.assertEqual(self.post(path, {**body, "version": 1}).status_code, 409)
        result = self.post(path, body)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["onsitePayment"]["status"], "recorded")
        self.assertEqual(result.json()["onsitePayment"]["amount"], 280000)
        self.assertEqual(self.post(path, body).status_code, 200)
        self.assertEqual(OnsiteSettlement.objects.count(), 1)
        self.assertEqual(Audit.objects.filter(action="onsite_payment_recorded").count(), 1)
        self.assertEqual(self.post(path, {**body, "method": "card"}).status_code, 409)
        accountant = User.objects.create_user(
            username="accountant", email="accountant@test.invalid", role="accountant"
        )
        self.login(accountant)
        self.assertEqual(self.post(path, body).status_code, 403)
        self.assertEqual(
            self.client.get(path.replace("onsite-payment", "voucher")).status_code, 200
        )

    @override_settings(PAYMENTS_INLINE_CHECKOUT=True)
    def test_inline_creation_uses_one_leased_job_and_refresh_is_read_only_lookup(self):
        with patch("commerce.payment_views.run_one") as run:
            response = self.create()
            self.assertEqual(response.status_code, 202)
            pk = response.json()["id"]
            run.assert_called_once_with(payment_id=pk, kinds=["create"])
            run.reset_mock()
            self.post(f"/api/payments/{pk}/refresh", {})
            run.assert_called_once_with(payment_id=pk, kinds=["verify", "refund_verify"])
