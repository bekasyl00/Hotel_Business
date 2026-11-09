import csv
import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import User
from commerce.accounting.services import snapshot
from commerce.models import AccountingDocument, DemoPayment, OnsiteSettlement
from commerce.settlement import freeze_payment_terms
from commerce.test_accounting import COMPANY
from commerce.test_document_helpers import complete_roster, document_key
from commerce.tests import fixture


class AccountingFeeTests(TestCase):
    def setUp(self):
        document_key(self)
        self.resort, self.booking, self.manager = fixture()
        self.resort.commission_percent = Decimal("10")
        self.resort.save()
        self.booking.snapshot["paymentTerms"] = freeze_payment_terms(self.resort, 36000)
        self.booking.snapshot["commissionTerms"] = {"amount": 3600}
        self.booking.save()
        user = User.objects.create_user(
            username="accounting-fee@example.test",
            email="accounting-fee@example.test",
            name="Fictional accountant",
            role="accountant",
            password="Fictional-only-2026!",
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(user)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def report(self, mode="demo"):
        response = self.client.get("/api/accounting", {"paymentMode": mode})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def paid_fee(self):
        return DemoPayment.objects.create(
            booking=self.booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="paid",
            amount=3600,
        )

    def onsite(self):
        return OnsiteSettlement.objects.create(
            booking=self.booking, amount=36000, method="cash", recorded_by=self.manager
        )

    def write(self, path, data, method="post"):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_awaiting_payment_uses_online_fee_and_legacy_fallback(self):
        self.booking.status = "pending"
        self.booking.hold_expires_at = timezone.now() + timedelta(minutes=15)
        self.booking.save()
        self.assertEqual(self.report()["totals"]["awaitingPayment"], 3600)
        del self.booking.snapshot["paymentTerms"]
        self.booking.save()
        self.assertEqual(self.report()["totals"]["awaitingPayment"], 36000)

    def test_manual_onsite_records_never_inflate_platform_income_or_other_modes(self):
        self.paid_fee()
        totals = self.report()["totals"]
        self.assertEqual(totals["confirmedAmount"], 36000)
        self.assertEqual(totals["received"], 3600)
        self.assertEqual(totals["onsiteDue"], 36000)
        self.assertEqual(totals["onsiteRecorded"], 0)
        self.onsite()
        report = self.report()
        self.assertEqual(report["totals"]["received"], 3600)
        self.assertEqual(report["totals"]["net"], 3600)
        self.assertEqual(report["totals"]["onsiteDue"], 0)
        self.assertEqual(report["totals"]["onsiteRecorded"], 36000)
        self.assertEqual(report["finance"]["byResort"][0]["onsiteRecorded"], 36000)
        self.assertEqual(self.report("production")["totals"]["onsiteRecorded"], 0)

    def test_accommodation_document_separates_fee_payment_and_onsite_payment(self):
        payment = self.paid_fee()
        result = snapshot(self.booking, "TEST")
        self.assertEqual(result["amount"], 36000)
        self.assertEqual(result["customerTotal"], 39600)
        self.assertEqual(result["paidAmount"], 0)
        self.assertEqual(result["paymentEvidence"], "not_recorded")
        self.assertEqual(result["platformFeePaidAmount"], 3600)
        self.onsite()
        self.booking.refresh_from_db()
        result = snapshot(self.booking, "TEST")
        self.assertEqual(result["paidAmount"], 36000)
        self.assertEqual(result["paymentEvidence"], "staff_attestation")
        payment.refunded_amount = 2520
        payment.status = "partially_refunded"
        payment.save()
        result = snapshot(self.booking, "TEST")
        self.assertEqual(result["refundedAmount"], 0)
        self.assertEqual(result["platformFeeRefundedAmount"], 2520)

    def test_release_waits_for_onsite_attestation_and_keeps_released_copy_immutable(self):
        self.client.force_login(self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        complete_roster(self.booking, self.manager)
        self.paid_fee()
        self.booking.checked_in_at = timezone.now() - timedelta(days=1)
        self.booking.checked_out_at = timezone.now()
        self.booking.save()
        self.write("/api/accounting/company/" + self.resort.pk, COMPANY, "patch")
        created = self.write(
            "/api/accounting/documents", {"bookingId": self.booking.pk, "kind": "act"}
        )
        self.assertEqual(created.status_code, 201, created.content)
        doc = AccountingDocument.objects.get(pk=created.json()["id"])
        url = f"/api/accounting/documents/{doc.pk}/release"
        self.assertEqual(self.write(url, {"version": doc.version}).status_code, 409)
        self.onsite()
        released = self.write(url, {"version": doc.version})
        self.assertEqual(released.status_code, 200, released.content)
        doc.refresh_from_db()
        saved = dict(doc.snapshot)
        self.resort.commission_percent = 20
        self.resort.save()
        self.assertEqual(
            self.write(
                f"/api/accounting/documents/{doc.pk}/refresh", {"version": doc.version}
            ).status_code,
            409,
        )
        doc.refresh_from_db()
        self.assertEqual(doc.snapshot, saved)

    def test_accounting_export_labels_customer_fee_and_property_amounts_separately(self):
        self.paid_fee()
        self.onsite()
        response = self.client.get("/api/accounting/export?paymentMode=demo")
        self.assertEqual(response.status_code, 200)
        row = next(csv.DictReader(StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(row["Стоимость проживания KZT"], "36000")
        self.assertEqual(row["Полная стоимость KZT"], "39600")
        self.assertEqual(row["Онлайн-оплата по условиям KZT"], "3600")
        self.assertEqual(row["Отмечено сотрудником в санатории KZT"], "36000")
