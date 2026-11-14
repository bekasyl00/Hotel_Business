"""Fictional end-to-end document lifecycle through authenticated API handlers."""

import os
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from booking.models import Booking, GuestAccount, GuestProfile
from booking.tests import fixture
from commerce.models import AccountingDocument, OnsiteSettlement
from commerce.test_accounting import COMPANY
from commerce.test_document_helpers import document_key, fictional_guests


class DocumentLifecycleTests(TestCase):
    def setUp(self):
        document_key(self)
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.profile = GuestProfile.objects.create(
            owner="fictional-lifecycle-owner", name="Вымышленный Владелец", phone="+77010000081"
        )
        self.password = "fictional-lifecycle-password"
        self.account = GuestAccount.objects.create(
            profile=self.profile, phone=self.profile.phone, password=make_password(self.password)
        )
        self.guest = APIClient(enforce_csrf_checks=True)
        self.write(
            self.guest, "/api/guest-auth/login",
            {"phone": self.account.phone, "password": self.password},
        )
        self.staff = APIClient(enforce_csrf_checks=True)
        self.staff.force_login(self.manager)

    def write(self, client, path, data, *, method="post", expected=200):
        token = client.get("/api/auth/csrf").json()["token"]
        response = getattr(client, method)(path, data, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, expected, response.content)
        return response.json()

    def test_booking_to_released_owner_files_preserves_selected_buyer(self):
        start = timezone.localdate() + timedelta(days=5)
        created = self.write(
            self.guest, "/api/my-bookings",
            {
                "roomId": self.room.pk, "tariffId": self.tariff.pk,
                "start": str(start), "end": str(start + timedelta(days=2)),
                "guests": 2, "requestId": str(uuid.uuid4()),
            }, expected=201,
        )
        booking = Booking.objects.get(pk=created["id"])
        self.assertEqual(booking.guest_profile_id, self.profile.pk)
        self.assertEqual(booking.owner, self.profile.owner)
        self.assertIsNone(booking.checked_in_at)
        self.write(
            self.guest, "/api/payments/demo",
            {"bookingId": booking.pk, "outcome": "success", "requestId": str(uuid.uuid4())},
        )
        booking.refresh_from_db()
        self.assertEqual(booking.status, "confirmed")
        self.write(
            self.staff, f"/api/accounting/company/{self.resort.pk}",
            {**COMPANY, "supplier": "Вымышленная организация ДЕМО", "documentDelivery": "manual"},
            method="patch",
        )
        roster = {"version": 0, **fictional_guests(booking)}
        roster["buyerIndex"] = 1
        buyer = roster["guests"][1]
        buyer.update(fullName="Вымышленный Плательщик", address="Вымышленный адрес ДЕМО")
        saved = self.write(
            self.staff, f"/api/bookings/{booking.pk}/document-guests", roster, method="put"
        )
        self.assertTrue(saved["complete"])
        self.assertEqual(saved["guests"][0]["fullName"], self.profile.name)
        admission_at = datetime.fromisoformat(booking.snapshot["cancellationPolicy"]["checkinAt"])
        with patch("django.utils.timezone.now", return_value=admission_at + timedelta(hours=1)):
            self.write(
                self.staff, f"/api/bookings/{booking.pk}/accept-arrival",
                {"version": booking.version, "method": "cash", "received": True},
            )
        booking.refresh_from_db()
        self.assertIsNotNone(booking.checked_in_at)
        self.assertIsNone(booking.checked_out_at)
        self.assertEqual(OnsiteSettlement.objects.get(booking=booking).amount, booking.snapshot["total"])
        with patch("django.utils.timezone.now", return_value=admission_at + timedelta(days=2)):
            self.write(
                self.staff, f"/api/bookings/{booking.pk}/check-out", {"version": booking.version}
            )
        booking.refresh_from_db()
        self.assertIsNotNone(booking.checked_out_at)
        docs = list(AccountingDocument.objects.filter(booking=booking).order_by("kind"))
        self.assertEqual([doc.kind for doc in docs], ["act", "invoice"])
        self.assertTrue(all(doc.state == "draft" for doc in docs))
        self.assertEqual(self.guest.get("/api/my-documents").json(), [])
        for doc in docs:
            self.assertEqual(
                self.guest.get(f"/api/my-documents/{doc.pk}/pdf/download").status_code, 404
            )
            self.write(
                self.staff, f"/api/accounting/documents/{doc.pk}/release", {"version": doc.version}
            )
        listed = self.guest.get("/api/my-documents").json()
        self.assertEqual({doc["id"] for doc in listed}, {doc.pk for doc in docs})
        stranger = APIClient(enforce_csrf_checks=True)
        other = GuestProfile.objects.create(
            owner="fictional-unrelated-owner", name="Вымышленный Посторонний", phone="+77010000082"
        )
        GuestAccount.objects.create(
            profile=other, phone=other.phone, password=make_password(self.password)
        )
        self.write(
            stranger, "/api/guest-auth/login", {"phone": other.phone, "password": self.password}
        )
        self.assertEqual(stranger.get("/api/my-documents").json(), [])
        export_dir = os.environ.get("DOCUMENT_LIFECYCLE_OUTPUT")
        for doc in docs:
            doc.refresh_from_db()
            self.assertEqual(doc.state, "released")
            self.assertEqual(doc.snapshot["amount"], int(booking.snapshot["total"]))
            self.assertEqual(doc.snapshot["paidAmount"], int(booking.snapshot["total"]))
            for kind in ("pdf", "xlsx"):
                path = f"/api/my-documents/{doc.pk}/{kind}/download"
                response = self.guest.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(stranger.get(path).status_code, 404)
                self.assertEqual(APIClient().get(path).status_code, 401)
                self.assertIn("no-store", response["Cache-Control"])
                if kind == "pdf":
                    self.assertTrue(response.content.startswith(b"%PDF"))
                else:
                    sheet = load_workbook(BytesIO(response.content)).active
                    values = " ".join(str(cell.value or "") for row in sheet for cell in row)
                    self.assertIn(buyer["fullName"], values)
                    self.assertIn(buyer["iin"], values)
                    self.assertIn(buyer["address"], values)
                    self.assertIn("ДЕМО", values)
                if export_dir:
                    destination = Path(export_dir)
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / f"fictional-{doc.kind}.{kind}").write_bytes(response.content)
