"""Document delivery requires settled, independently applied payment evidence."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from commerce import test_bank_payments as bank_tests
from commerce.accounting.services import prepare_after_stay
from commerce.models import AccountingCompany, AccountingDocument, OnsiteSettlement, RefundRequest
from commerce.payment_services import apply_transaction
from commerce.services import booking_payment_data
from commerce.settlement import freeze_payment_terms
from commerce.test_accounting import COMPANY
from commerce.test_bank_payments import BANK, evidence
from commerce.test_document_helpers import complete_roster, document_key


@override_settings(**BANK)
class BankDocumentDeliveryTests(TestCase):
    create = bank_tests.BankTests.create
    payment = bank_tests.BankTests.payment

    def setUp(self):
        bank_tests.BankTests.setUp(self)
        document_key(self)
        self.booking.snapshot["paymentTerms"] = freeze_payment_terms(self.resort, 36000)
        self.booking.save()
        complete_roster(self.booking, self.manager)
        AccountingCompany.objects.create(
            resort=self.resort,
            details={
                **{key: value for key, value in COMPANY.items() if key != "version"},
                "documentDelivery": "automatic",
            },
        )
        self.staff = APIClient(enforce_csrf_checks=True)
        self.staff.force_login(self.manager)
        self.csrf = self.staff.get("/api/auth/csrf").json()["token"]

    def write(self, path, body):
        return self.staff.post(path, body, format="json", HTTP_X_CSRFTOKEN=self.csrf)

    def verified_stay(self, *, onsite=True):
        payment = self.payment()
        self.assertEqual(payment.amount, 3600)
        apply_transaction(payment.pk, evidence(payment))
        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "confirmed")
        self.booking.checked_in_at = timezone.now() - timedelta(days=1)
        self.booking.save(update_fields=["checked_in_at"])
        if onsite:
            OnsiteSettlement.objects.create(
                booking=self.booking, amount=36000, method="cash", recorded_by=self.manager
            )
        return payment

    def checkout(self):
        result = self.write(
            f"/api/bookings/{self.booking.pk}/check-out", {"version": self.booking.version}
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.booking.checked_out_at)

    def assert_drafts(self):
        self.assertEqual(AccountingDocument.objects.filter(state="draft").count(), 2)
        self.assertFalse(AccountingDocument.objects.exclude(state="draft").exists())

    def test_verified_bank_fee_and_onsite_attestation_release_separate_amounts_and_modes(self):
        self.verified_stay()
        self.checkout()
        for doc in AccountingDocument.objects.all():
            self.assertEqual(doc.state, "released")
            self.assertEqual(doc.snapshot["amount"], 36000)
            self.assertEqual(doc.snapshot["paidAmount"], 36000)
            self.assertEqual(doc.snapshot["platformFeePaidAmount"], 3600)
            self.assertEqual(doc.snapshot["customerTotal"], 39600)
            self.assertEqual(doc.snapshot["paymentEvidence"], "staff_attestation")
            self.assertEqual(doc.snapshot["paymentMode"], "sandbox")
        for mode, expected in (("sandbox", 2), ("production", 0), ("demo", 0)):
            response = self.staff.get("/api/accounting/documents", {"paymentMode": mode})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["documents"]), expected)

    def test_applied_charge_under_reconciliation_cannot_release_documents(self):
        payment = self.verified_stay()
        apply_transaction(payment.pk, evidence(payment, transaction_id="additional-charge"))
        self.booking.refresh_from_db()
        data = booking_payment_data(self.booking)
        self.assertEqual(data["status"], "paid")
        self.assertEqual(data["checkoutStatus"], "reconciliation_required")
        self.checkout()
        self.assert_drafts()
        doc = AccountingDocument.objects.get(kind="act")
        self.assertEqual(
            self.write(
                f"/api/accounting/documents/{doc.pk}/release", {"version": doc.version}
            ).status_code,
            409,
        )

    def test_every_refund_stage_blocks_manual_and_automatic_delivery(self):
        payment = self.verified_stay()
        self.booking.checked_out_at = timezone.now()
        self.booking.save(update_fields=["checked_out_at"])
        refund = RefundRequest.objects.create(
            payment=payment, amount=payment.amount, percent=100, actor_kind="guest"
        )
        for state in ("queued", "submitted", "reconciliation_required", "succeeded"):
            with self.subTest(state=state):
                refund.status = state
                refund.save(update_fields=["status"])
                self.booking.refresh_from_db()
                prepare_after_stay(self.booking, self.manager)
                self.assert_drafts()
                doc = AccountingDocument.objects.get(kind="act")
                self.assertEqual(
                    self.write(
                        f"/api/accounting/documents/{doc.pk}/release", {"version": doc.version}
                    ).status_code,
                    409,
                )

    def test_automatic_delivery_waits_for_onsite_amount_without_undoing_checkout(self):
        self.verified_stay(onsite=False)
        self.checkout()
        self.assert_drafts()
        onsite = OnsiteSettlement.objects.create(
            booking=self.booking, amount=35999, method="cash", recorded_by=self.manager
        )
        prepare_after_stay(self.booking, self.manager)
        self.assert_drafts()
        onsite.amount = 36000
        onsite.save(update_fields=["amount"])
        doc = AccountingDocument.objects.get(kind="act")
        result = self.write(f"/api/accounting/documents/{doc.pk}/release", {"version": doc.version})
        self.assertEqual(result.status_code, 200, result.content)
        doc.refresh_from_db()
        self.assertEqual(doc.snapshot["paidAmount"], 36000)
