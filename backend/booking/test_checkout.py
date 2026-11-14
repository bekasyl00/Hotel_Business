import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from commerce.models import DemoPayment

from .models import Audit, Booking
from .tests import authenticate_guest, fixture


class CheckoutTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        authenticate_guest(self.client)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        start = timezone.localdate() + timedelta(days=5)
        self.payload = {
            "roomId": self.room.pk,
            "tariffId": self.tariff.pk,
            "start": str(start),
            "end": str(start + timedelta(days=3)),
            "guests": 2,
            "guestLabel": "Демо",
            "guestPhone": "+70000000000",
            "requestId": str(uuid.uuid4()),
        }

    def write(self, method, url, payload):
        return getattr(self.client, method)(
            url, payload, format="json", HTTP_X_CSRFTOKEN=self.token
        )

    def create(self, staff=False):
        result = self.write("post", "/api/bookings" if staff else "/api/my-bookings", self.payload)
        self.assertEqual(result.status_code, 201, result.content)
        return Booking.objects.get(pk=result.json()["id"])

    def login(self, user):
        self.client.force_login(user)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def payment(self, booking, outcome="success", request_id=None, staff=False):
        return self.write(
            "post",
            "/api/payments/demo/staff" if staff else "/api/payments/demo",
            {
                "bookingId": booking.pk,
                "outcome": outcome,
                "requestId": request_id or str(uuid.uuid4()),
            },
        )

    def due_stay(self, *, admitted=True, paid=True):
        booking = self.create()
        if paid:
            self.assertEqual(self.payment(booking).status_code, 200)
            booking.refresh_from_db()
        booking.status = "confirmed"
        booking.stay = Range(
            timezone.localdate() - timedelta(days=2), timezone.localdate() - timedelta(days=1), "[)"
        )
        booking.checked_in_at = timezone.now() - timedelta(days=2) if admitted else None
        booking.save(update_fields=["status", "stay", "checked_in_at"])
        return booking

    def test_scheduler_completes_due_paid_admitted_stay_idempotently(self):
        from .departures import complete_due_departures

        booking = self.due_stay()
        arrival, version = booking.checked_in_at, booking.version
        now = timezone.now()
        with patch("commerce.accounting.services.prepare_after_stay") as prepare:
            self.assertEqual(complete_due_departures(now), 1)
            self.assertEqual(complete_due_departures(now), 0)
        booking.refresh_from_db()
        self.assertEqual(booking.checked_out_at, now)
        self.assertEqual(booking.checked_in_at, arrival)
        self.assertEqual(booking.version, version + 1)
        self.assertEqual(Audit.objects.filter(entity_id=booking.pk, action="check-out").count(), 1)
        prepare.assert_called_once()

    def test_scheduler_never_infers_admission_for_paid_booking(self):
        from .departures import complete_due_departures

        booking = self.due_stay(admitted=False)
        version = booking.version
        with patch("commerce.accounting.services.prepare_after_stay") as prepare:
            self.assertEqual(complete_due_departures(), 0)
        booking.refresh_from_db()
        self.assertIsNone(booking.checked_in_at)
        self.assertIsNone(booking.checked_out_at)
        self.assertEqual(booking.version, version)
        prepare.assert_not_called()
        self.assertFalse(Audit.objects.filter(entity_id=booking.pk, action="check-out").exists())

    def test_scheduler_requires_verified_payment(self):
        from .departures import complete_due_departures

        booking = self.due_stay(paid=False)
        with patch("commerce.accounting.services.prepare_after_stay") as prepare:
            self.assertEqual(complete_due_departures(), 0)
        booking.refresh_from_db()
        self.assertIsNone(booking.checked_out_at)
        prepare.assert_not_called()

    def test_scheduler_filters_future_departures_before_batch_limit(self):
        from .departures import complete_due_departures

        future = self.due_stay()
        future.stay = Range(
            timezone.localdate() - timedelta(days=10), timezone.localdate() + timedelta(days=10), "[)"
        )
        future.save(update_fields=["stay"])
        self.room.pk = str(uuid.uuid4())
        self.room.number = "202"
        self.room.save(force_insert=True)
        self.payload.update(roomId=self.room.pk, requestId=str(uuid.uuid4()))
        due = self.due_stay()
        with patch("commerce.accounting.services.prepare_after_stay"):
            self.assertEqual(complete_due_departures(limit=1), 1)
        future.refresh_from_db()
        due.refresh_from_db()
        self.assertIsNone(future.checked_out_at)
        self.assertIsNotNone(due.checked_out_at)

    def test_scheduler_audit_failure_rolls_back_checkout(self):
        from .departures import complete_due_departures

        booking = self.due_stay()
        version = booking.version
        with patch("booking.stays.log_change", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                complete_due_departures()
        booking.refresh_from_db()
        self.assertIsNone(booking.checked_out_at)
        self.assertEqual(booking.version, version)

    def test_failed_then_success_payment_confirms_once_without_manager(self):
        booking = self.create()
        self.assertIsNotNone(booking.hold_expires_at)
        self.assertEqual(self.payment(booking, "failed").status_code, 200)
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.version), ("pending", 1))
        key = str(uuid.uuid4())
        paid = self.payment(booking, request_id=key)
        self.assertEqual(paid.status_code, 200, paid.content)
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.version), ("confirmed", 2))
        self.assertEqual(self.payment(booking, request_id=key).json()["id"], paid.json()["id"])
        self.assertEqual(self.payment(booking).status_code, 409)
        self.assertEqual(Audit.objects.filter(action="payment_confirmed").count(), 1)

    def test_expired_payment_refused_and_inventory_can_be_reused(self):
        booking = self.create()
        booking.hold_expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=["hold_expires_at"])
        available = self.client.get("/api/availability", self.payload).json()["roomIds"]
        self.assertIn(self.room.pk, available)
        self.assertEqual(self.payment(booking).status_code, 409)
        booking.refresh_from_db()
        self.assertEqual(booking.status, "expired")
        self.assertEqual(DemoPayment.objects.count(), 0)
        self.payload["requestId"] = str(uuid.uuid4())
        replacement = self.create()
        self.assertEqual(replacement.status, "pending")
        self.assertNotEqual(replacement.pk, booking.pk)

    def test_expiry_command_is_idempotent_and_keeps_paid_bookings(self):
        booking = self.create()
        booking.hold_expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=["hold_expires_at"])
        call_command("expire_payment_holds", verbosity=0)
        call_command("expire_payment_holds", verbosity=0)
        self.assertEqual(Audit.objects.filter(action="payment_expired").count(), 1)
        self.payload["requestId"] = str(uuid.uuid4())
        paid = self.create()
        self.payment(paid)
        Booking.objects.filter(pk=paid.pk).update(
            hold_expires_at=timezone.now() - timedelta(days=1)
        )
        call_command("expire_payment_holds", verbosity=0)
        paid.refresh_from_db()
        self.assertEqual(paid.status, "confirmed")

    def test_payment_and_confirmation_rollback_together_on_audit_failure(self):
        booking = self.create()
        with patch("booking.audit.log_change", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.payment(booking)
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.version), ("pending", 1))
        self.assertEqual(DemoPayment.objects.count(), 0)

    def test_admin_commission_is_private_frozen_and_manager_cannot_change_it(self):
        self.login(self.admin)
        url = f"/api/resorts/{self.resort.pk}"
        result = self.write("patch", url, {"version": 1, "commissionPercent": "7.25"})
        self.assertEqual(result.status_code, 200, result.content)
        booking = self.create()
        self.assertEqual(booking.snapshot["commissionTerms"]["amount"], 9788)
        self.assertEqual(booking.snapshot["commissionTerms"]["resortAmount"], 135000)
        self.assertEqual(booking.snapshot["paymentTerms"]["total"], 144788)
        self.assertNotIn("commissionTerms", self.client.get("/api/my-bookings").json()[0])
        self.assertNotIn("commissionPercent", self.client.get("/api/catalog").json()["resorts"][0])
        self.assertEqual(
            self.write("patch", url, {"version": 2, "commissionPercent": "10"}).status_code, 200
        )
        booking.refresh_from_db()
        self.assertEqual(booking.snapshot["commissionTerms"]["percent"], "7.25")
        self.login(self.manager)
        self.assertEqual(
            self.write("patch", url, {"version": 3, "commissionPercent": "0"}).status_code, 403
        )
        self.assertEqual(
            self.client.get("/api/workspace").json()["bookings"][0]["commissionTerms"]["amount"],
            9788,
        )

    def test_commission_blank_is_distinct_from_zero_and_invalid_values_are_rejected(self):
        self.login(self.admin)
        url = f"/api/resorts/{self.resort.pk}"
        for value in ["-1", "100.01", "0.001"]:
            self.assertEqual(
                self.write("patch", url, {"version": 1, "commissionPercent": value}).status_code,
                422,
            )
        for version, value in [(1, None), (2, 0)]:
            response = self.write("patch", url, {"version": version, "commissionPercent": value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["commissionPercent"], None if value is None else "0.00"
            )
            response = self.write(
                "post", "/api/bookings", {**self.payload, "requestId": str(uuid.uuid4())}
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["code"], "booking_fee_not_configured")

    def test_staff_demo_payment_requires_staff_source_and_scope(self):
        guest = self.create()
        self.assertEqual(self.payment(guest, staff=True).status_code, 401)
        self.login(self.manager)
        self.assertEqual(self.payment(guest, staff=True).status_code, 403)
        self.assertEqual(
            self.write(
                "patch", f"/api/bookings/{guest.pk}", {"version": 1, "status": "confirmed"}
            ).status_code,
            409,
        )
        self.write("patch", f"/api/bookings/{guest.pk}", {"version": 1, "status": "cancelled"})
        self.payload["requestId"] = str(uuid.uuid4())
        manual = self.create(staff=True)
        self.assertEqual(self.payment(manual, staff=True).status_code, 200)
        manual.refresh_from_db()
        self.assertEqual(manual.status, "confirmed")
