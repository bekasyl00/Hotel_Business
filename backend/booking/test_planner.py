import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from .models import Audit, Booking, RoomPricePeriod
from .tests import fixture


class PlannerTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.start = timezone.localdate() + timedelta(days=5)
        self.payload = dict(
            roomId=self.room.pk,
            start=str(self.start),
            end=str(self.start + timedelta(days=3)),
            guests=2,
            guestLabel="Demo planner",
            requestId=str(uuid.uuid4()),
        )

    def post(self, path, data):
        return self.client.post(path, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    def create(self):
        result = self.post("/api/bookings", self.payload)
        self.assertEqual(result.status_code, 201, result.content)
        return Booking.objects.get(pk=result.json()["id"])

    def test_room_only_seasonal_price_payment_receipt_and_immutable_snapshot(self):
        RoomPricePeriod.objects.create(
            room=self.room,
            stay=Range(self.start, self.start + timedelta(days=1)),
            price=12345,
            label="Season",
        )
        b = self.create()
        self.assertIsNone(b.tariff_id)
        self.assertEqual(b.snapshot["total"], 12345 + self.room.price * 2)
        self.assertEqual(b.snapshot["pricingBasis"], "room")
        result = self.post(
            "/api/payments/demo/staff",
            dict(bookingId=b.pk, requestId=str(uuid.uuid4()), outcome="success"),
        )
        self.assertEqual(result.status_code, 200, result.content)
        b.refresh_from_db()
        self.assertEqual(b.status, "confirmed")
        receipt = b.demo_payments.get(outcome="success").receipt
        self.assertEqual(receipt["total"], b.snapshot["total"])
        self.room.price += 100
        self.room.save()
        b.refresh_from_db()
        self.assertEqual(b.snapshot["total"], 12345 + (self.room.price - 100) * 2)

    def test_guest_cannot_use_room_only_price(self):
        self.client.logout()
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.payload["guestPhone"] = "+70000000000"
        result = self.post("/api/my-bookings", self.payload)
        self.assertEqual(result.status_code, 422)
        self.assertEqual(Booking.objects.count(), 0)

    def test_notes_tenant_version_csrf_and_public_privacy(self):
        b = self.create()
        url = f"/api/v1/bookings/{b.pk}/notes"
        result = self.post(url, dict(version=1, staffNotes="Private operational note"))
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["staffNotes"], "Private operational note")
        self.assertEqual(self.post(url, dict(version=1, staffNotes="stale")).status_code, 409)
        self.assertEqual(
            self.client.post(url, dict(version=2, staffNotes="csrf"), format="json").status_code,
            403,
        )
        self.assertEqual(self.post(url, dict(version=2, staffNotes="x" * 2001)).status_code, 422)
        self.assertNotIn(
            "Private operational note", str(list(Audit.objects.values("before", "after")))
        )
        from .serializers import booking_data

        b.refresh_from_db()
        self.assertNotIn("staffNotes", booking_data(b))
        self.assertEqual(booking_data(b, staff=True)["staffNotes"], "Private operational note")
        self.manager.resort = None
        self.manager.save()
        self.assertEqual(self.post(url, dict(version=2, staffNotes="foreign")).status_code, 403)

    def test_notes_and_audit_roll_back_together(self):
        b = self.create()
        with patch("booking.services.log_change", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.post(f"/api/bookings/{b.pk}/notes", dict(version=1, staffNotes="rolled back"))
        b.refresh_from_db()
        self.assertEqual((b.version, b.staff_notes), (1, ""))
