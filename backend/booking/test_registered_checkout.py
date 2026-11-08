import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Booking
from .tests import authenticate_guest, fixture


@override_settings(BOOKING_HOLD_MINUTES=15)
class RegisteredCheckoutTests(TestCase):
    def setUp(self):
        _, self.room, self.tariff, self.manager, _ = fixture()
        self.api = APIClient(enforce_csrf_checks=True)
        start = timezone.localdate() + timedelta(days=5)
        self.payload = dict(
            roomId=self.room.pk,
            tariffId=self.tariff.pk,
            start=str(start),
            end=str(start + timedelta(days=2)),
            guests=1,
            requestId=str(uuid.uuid4()),
        )

    def post(self, **changes):
        csrf = self.api.get("/api/auth/csrf").json()["token"]
        return self.api.post(
            "/api/my-bookings", {**self.payload, **changes}, format="json", HTTP_X_CSRFTOKEN=csrf
        )

    def test_guest_account_required_even_with_staff_session_or_contact_fields(self):
        for staff in (False, True):
            if staff:
                self.api.force_login(self.manager)
            r = self.post(guestLabel="Forged name", guestPhone="+77010000001")
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.json()["code"], "guest_login_required")
        self.assertEqual(Booking.objects.count(), 0)

    def test_profile_contacts_override_payload_and_retry_does_not_extend_deadline(self):
        account = authenticate_guest(self.api, name="Profile name", phone="+77010000001")
        before = timezone.now()
        r = self.post(guestLabel="Forged name", guestPhone="+77010000002")
        self.assertEqual(r.status_code, 201, r.content)
        b = Booking.objects.get(pk=r.json()["id"])
        self.assertEqual((b.guest_label, b.guest_phone), ("Profile name", account.phone))
        self.assertGreaterEqual(b.hold_expires_at, before + timedelta(minutes=15))
        self.assertLessEqual(b.hold_expires_at, timezone.now() + timedelta(minutes=15))
        account.profile.name = "Updated profile"
        account.profile.save()
        retry = self.post()
        self.assertEqual(retry.status_code, 201, retry.content)
        self.assertEqual(retry.json()["id"], b.pk)
        b.refresh_from_db()
        self.assertEqual(b.guest_label, "Profile name")
        self.assertEqual(retry.json()["holdExpiresAt"], r.json()["holdExpiresAt"])
        self.assertEqual(Booking.objects.count(), 1)

    def test_revoked_account_cannot_create_or_reserve_inventory(self):
        account = authenticate_guest(self.api)
        account.auth_version += 1
        account.save()
        self.assertEqual(self.post().status_code, 401)
        self.assertEqual(Booking.objects.count(), 0)

    def test_full_iin_is_rejected_by_api(self):
        authenticate_guest(self.api)
        self.assertEqual(self.post(iin="241109000000").status_code, 422)
        self.assertEqual(Booking.objects.count(), 0)
