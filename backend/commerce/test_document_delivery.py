"""Document delivery requires settled, independently applied payment evidence."""

import uuid
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from booking.models import GuestAccount, GuestProfile
from commerce import test_bank_payments as bank_tests
from commerce.accounting.services import prepare_after_stay
from commerce.models import (
    AccountingCompany,
    AccountingDocument,
    DemoPayment,
    OnsiteSettlement,
    RefundRequest,
)
from commerce.payment_services import apply_transaction
from commerce.services import booking_payment_data
from commerce.settlement import freeze_payment_terms
from commerce.test_accounting import COMPANY
from commerce.test_bank_payments import BANK, evidence
from commerce.test_document_helpers import complete_roster, document_key
from commerce.tests import fixture


class OwnedDocumentDeliveryTests(TestCase):
    """Manager release is visible to the same authenticated owner on web and native."""

    def setUp(self):
        document_key(self)
        self.resort, self.booking, self.manager = fixture()
        self.profile = GuestProfile.objects.create(
            owner=self.booking.owner, name="Тестовый владелец", phone="+77010000051"
        )
        self.password = "fictional-document-password"
        self.account = GuestAccount.objects.create(
            profile=self.profile, phone=self.profile.phone, password=make_password(self.password)
        )
        self.booking.guest_profile = self.profile
        self.booking.checked_in_at = timezone.now() - timedelta(days=1)
        self.booking.checked_out_at = timezone.now()
        self.booking.save()
        complete_roster(self.booking, self.manager)
        DemoPayment.objects.create(
            booking=self.booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="paid",
            amount=36000,
        )
        AccountingCompany.objects.create(
            resort=self.resort, details={k: v for k, v in COMPANY.items() if k != "version"}
        )
        self.staff = APIClient(enforce_csrf_checks=True)
        self.staff.force_login(self.manager)
        self.csrf = self.staff.get("/api/auth/csrf").json()["token"]

    def write(self, path, body):
        return self.staff.post(path, body, format="json", HTTP_X_CSRFTOKEN=self.csrf)

    def login(self, *, native=False):
        client = APIClient(enforce_csrf_checks=True)
        body = {"phone": self.account.phone, "password": self.password}
        if native:
            body["deviceName"] = "Fictional document Android"
            response = client.post("/api/v1/mobile-auth/login", body, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            client.credentials(HTTP_AUTHORIZATION="Bearer " + response.json()["accessToken"])
        else:
            token = client.get("/api/auth/csrf").json()["token"]
            response = client.post(
                "/api/guest-auth/login", body, format="json", HTTP_X_CSRFTOKEN=token
            )
            self.assertEqual(response.status_code, 200, response.content)
        return client

    def prepare(self):
        response = self.write(
            "/api/accounting/documents", {"bookingId": self.booking.pk, "kind": "act"}
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def release(self, doc):
        result = self.write(
            f"/api/accounting/documents/{doc['id']}/release", {"version": doc["version"]}
        )
        self.assertEqual(result.status_code, 200, result.content)
        return result.json()

    def test_explicit_manager_release_appears_for_registered_browser_and_native_owner(self):
        web, native = self.login(), self.login(native=True)
        doc = self.prepare()
        for client in (web, native):
            self.assertEqual(client.get("/api/v1/my-documents").json(), [])
        self.release(doc)
        for prefix, client in (("/api", web), ("/api/v1", native)):
            response = client.get(f"{prefix}/my-documents", {"bookingId": self.booking.pk})
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual([d["id"] for d in response.json()], [doc["id"]])
            item = response.json()[0]
            self.assertEqual(
                (item["resortName"], item["start"], item["end"]),
                (
                    self.resort.name,
                    self.booking.stay.lower.isoformat(),
                    self.booking.stay.upper.isoformat(),
                ),
            )
            for kind, signature in (("pdf", b"%PDF"), ("xlsx", b"PK")):
                download = client.get(f"{prefix}/my-documents/{doc['id']}/{kind}/download")
                self.assertEqual(download.status_code, 200, download.content[:80])
                self.assertTrue(download.content.startswith(signature))

    def test_anonymous_legacy_owner_and_invalid_native_credentials_do_not_grant_document_access(
        self,
    ):
        doc = self.release(self.prepare())
        anonymous = APIClient()
        session = anonymous.session
        session["guest_owner"] = self.booking.owner
        session.save()
        for path in ("/api/my-documents", f"/api/my-documents/{doc['id']}/pdf/download"):
            self.assertEqual(anonymous.get(path).status_code, 401)
        web = self.login()
        web.credentials(HTTP_AUTHORIZATION="Bearer invalid-document-token")
        self.assertEqual(web.get("/api/my-documents").status_code, 401)
        self.assertEqual(APIClient().get("/api/my-documents").status_code, 401)

    def test_buyer_contact_does_not_change_owner_or_disclose_manual_staff_booking(self):
        doc = self.release(self.prepare())
        web = self.login()
        self.booking.owner = "unrelated-booking-owner"
        self.booking.guest_phone = self.account.phone
        self.booking.save(update_fields=["owner", "guest_phone"])
        self.assertEqual(web.get("/api/my-documents").json(), [])
        self.assertEqual(web.get(f"/api/my-documents/{doc['id']}/pdf/download").status_code, 404)
        self.booking.owner = self.profile.owner
        self.booking.source = "staff"
        self.booking.save(update_fields=["owner", "source"])
        self.assertEqual(web.get("/api/my-documents").json(), [])

    def test_disabled_owner_loses_browser_and_native_document_access(self):
        doc = self.release(self.prepare())
        clients = (self.login(), self.login(native=True))
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])
        for client in clients:
            self.assertEqual(client.get("/api/my-documents").status_code, 401)
            self.assertEqual(
                client.get(f"/api/my-documents/{doc['id']}/pdf/download").status_code, 401
            )


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
