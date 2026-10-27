import importlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.apps import apps
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from commerce.models import DemoPayment

from .errors import Problem
from .models import Audit, Booking, GuestProfile, Resort, Room, Tariff
from .services import change_stay
from .tests import fixture


class ProfileTests(TestCase):
    def setUp(self):
        self.resort, self.room, self.tariff, self.manager, self.admin = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.today = timezone.localdate()
        clock = patch(
            "django.utils.timezone.now",
            return_value=datetime.combine(self.today, time(8), tzinfo=ZoneInfo("Asia/Almaty")),
        )
        clock.start()
        self.addCleanup(clock.stop)
        self.payload = {
            "roomId": self.room.id,
            "tariffId": self.tariff.id,
            "start": str(self.today),
            "end": str(self.today + timedelta(days=2)),
            "guests": 1,
            "guestLabel": "Гость один",
            "guestPhone": "+70000000000",
            "requestId": str(uuid.uuid4()),
        }

    def write(self, method, url, data):
        return getattr(self.client, method)(url, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    def create(self, **changes):
        response = self.write(
            "post", "/api/my-bookings", {**self.payload, "requestId": str(uuid.uuid4()), **changes}
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Booking.objects.get(pk=response.json()["id"])

    def staff(self, user=None):
        self.client.force_login(user or self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]

    def paid_confirmed(self, booking):
        booking.status = "confirmed"
        booking.save(update_fields=["status"])
        DemoPayment.objects.create(
            booking=booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="paid",
            amount=booking.snapshot["total"],
        )

    def test_first_profile_and_updates_are_session_owned_and_do_not_rewrite_booking(self):
        empty = self.client.get("/api/profile").json()
        self.assertEqual(empty["profile"]["name"], "")
        self.assertEqual(empty["bookings"], [])
        booking = self.create()
        response = self.client.get("/api/profile").json()
        profile = response["profile"]
        self.assertEqual(profile["id"], empty["profile"]["id"])
        self.assertEqual(profile["name"], "Гость один")
        self.assertEqual(booking.guest_profile_id, profile["id"])
        self.assertEqual(response["bookings"][0]["guestProfileId"], profile["id"])
        self.assertNotIn("owner", profile)
        for payload in [
            {"owner": "foreign", "name": "Другое имя", "phone": "+71111111111"},
            {"id": "foreign", "name": "Другое имя", "phone": "+71111111111"},
            {"name": "Без телефона"},
        ]:
            self.assertEqual(self.write("patch", "/api/profile", payload).status_code, 422)
        result = self.write("patch", "/api/profile", {"name": "Новое имя", "phone": "+71111111111"})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["profile"]["phone"], "+71111111111")
        booking.refresh_from_db()
        self.assertEqual(booking.guest_phone, "+70000000000")
        profile_audit = Audit.objects.filter(entity="guestProfiles").get()
        self.assertNotIn("phone", profile_audit.after)
        self.assertNotIn("name", profile_audit.after)
        foreign = APIClient()
        self.assertNotEqual(foreign.get("/api/profile").json()["profile"]["id"], profile["id"])
        self.assertEqual(foreign.get("/api/profile").json()["bookings"], [])
        self.assertEqual(foreign.get(f"/api/guests/{profile['id']}").status_code, 401)

    def test_website_profiles_do_not_merge_by_phone_and_manual_bookings_remain_unlinked(self):
        booking = self.create()
        foreign = APIClient()
        future = self.today + timedelta(days=5)
        response = foreign.post(
            "/api/my-bookings",
            {
                **self.payload,
                "start": str(future),
                "end": str(future + timedelta(days=2)),
                "requestId": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotEqual(response.json()["guestProfileId"], booking.guest_profile_id)
        self.assertEqual(GuestProfile.objects.filter(phone="+70000000000").count(), 2)
        self.staff()
        future += timedelta(days=4)
        response = self.write(
            "post",
            "/api/bookings",
            {
                **self.payload,
                "start": str(future),
                "end": str(future + timedelta(days=2)),
                "requestId": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.json()["guestProfileId"])

    def test_staff_profile_history_is_scoped_even_for_same_guest(self):
        own = self.create()
        other = Resort.objects.create(
            name="Другой", city="Тест", address="Тест", lat=1, lng=1, status="published"
        )
        room = Room.objects.create(
            resort=other,
            number="101",
            category="standard",
            title="Чужой номер",
            capacity=2,
            area=20,
            beds="1",
            price=10000,
        )
        tariff = Tariff.objects.create(resort=other, name="Чужой тариф")
        foreign = self.create(roomId=room.id, tariffId=tariff.id)
        self.assertEqual(own.guest_profile_id, foreign.guest_profile_id)
        self.staff()
        result = self.client.get(f"/api/guests/{own.guest_profile_id}")
        self.assertEqual(result.status_code, 200)
        self.assertEqual([b["id"] for b in result.json()["bookings"]], [own.id])
        self.assertNotIn("Чужой", result.content.decode())
        empty_resort = Resort.objects.create(
            name="Без броней", city="Тест", address="Тест", lat=1, lng=1
        )
        self.manager.resort = empty_resort
        self.manager.save()
        self.assertEqual(self.client.get(f"/api/guests/{own.guest_profile_id}").status_code, 404)
        self.staff(self.admin)
        self.assertEqual(
            len(self.client.get(f"/api/guests/{own.guest_profile_id}").json()["bookings"]), 2
        )

    def test_checkin_requires_paid_booking_dates_and_version(self):
        booking = self.create()
        url = f"/api/bookings/{booking.id}/check-in"
        self.assertEqual(self.write("post", url, {"version": 1}).status_code, 401)
        self.staff()
        self.assertEqual(self.client.post(url, {"version": 1}, format="json").status_code, 403)
        self.assertEqual(self.write("post", url, {"version": 1}).status_code, 409)
        booking.status = "confirmed"
        booking.save()
        self.assertEqual(self.write("post", url, {"version": 1}).status_code, 409)
        self.paid_confirmed(booking)
        booking.stay = Range(self.today + timedelta(days=1), self.today + timedelta(days=3))
        booking.save()
        self.assertEqual(self.write("post", url, {"version": 1}).status_code, 409)
        booking.stay = Range(self.today, self.today + timedelta(days=2))
        booking.save()
        self.assertEqual(self.write("post", url, {"version": 0}).status_code, 409)
        result = self.write("post", url, {"version": 1})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["stayStatus"], "in_house")
        self.assertIsNotNone(result.json()["checkedInAt"])
        self.assertEqual(self.write("post", url, {"version": 1}).status_code, 409)
        self.assertEqual(
            self.write(
                "patch", f"/api/bookings/{booking.id}", {"version": 2, "status": "cancelled"}
            ).status_code,
            409,
        )
        self.assertEqual(Audit.objects.filter(action="check-in").count(), 1)

    def test_checkout_requires_arrival_and_preserves_reservation_inventory_status(self):
        booking = self.create()
        self.paid_confirmed(booking)
        self.staff()
        check_out = f"/api/bookings/{booking.id}/check-out"
        self.assertEqual(self.write("post", check_out, {"version": 1}).status_code, 409)
        self.assertEqual(
            self.write("post", f"/api/bookings/{booking.id}/check-in", {"version": 1}).status_code,
            200,
        )
        result = self.write("post", check_out, {"version": 2})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["stayStatus"], "checked_out")
        self.assertEqual(result.json()["status"], "confirmed")
        self.assertIsNotNone(result.json()["checkedOutAt"])
        self.assertEqual(self.write("post", check_out, {"version": 3}).status_code, 409)
        self.assertEqual(
            self.write(
                "patch", f"/api/bookings/{booking.id}", {"version": 3, "status": "cancelled"}
            ).status_code,
            409,
        )
        self.assertEqual(Audit.objects.filter(action="check-out").count(), 1)

    def test_foreign_manager_cannot_register_arrival(self):
        booking = self.create()
        self.paid_confirmed(booking)
        other = Resort.objects.create(name="Чужой", city="Тест", address="Тест", lat=1, lng=1)
        self.manager.resort = other
        self.manager.save()
        self.staff()
        self.assertEqual(
            self.write("post", f"/api/bookings/{booking.id}/check-in", {"version": 1}).status_code,
            403,
        )
        booking.refresh_from_db()
        self.assertIsNone(booking.checked_in_at)

    def test_stay_actions_reject_other_http_methods_without_server_errors(self):
        booking = self.create()
        for action in ["check-in", "check-out"]:
            url = f"/api/bookings/{booking.id}/{action}"
            for method in ["get", "head"]:
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)
            for method in ["patch", "delete"]:
                self.assertEqual(self.write(method, url, {"version": 1}).status_code, 405)
        booking.refresh_from_db()
        self.assertIsNone(booking.checked_in_at)
        self.assertIsNone(booking.checked_out_at)

    def test_backfill_groups_only_website_owner_and_never_phone_or_manual_operator(self):
        booking = self.create()
        original_profile = booking.guest_profile_id
        second = self.create(
            start=str(self.today + timedelta(days=3)), end=str(self.today + timedelta(days=4))
        )
        Booking.objects.filter(pk__in=[booking.pk, second.pk]).update(guest_profile=None)
        manual = Booking.objects.create(
            resort=self.resort,
            room=self.room,
            tariff=self.tariff,
            stay=Range(self.today + timedelta(days=8), self.today + timedelta(days=9)),
            guests=1,
            guest_label="Manual guest",
            guest_phone=booking.guest_phone,
            owner=booking.owner,
            source="staff",
            status="cancelled",
            request_key=uuid.uuid4(),
            request_hash="test",
        )
        migration = importlib.import_module("booking.migrations.0003_guest_profiles_and_stays")
        migration.backfill_profiles(apps, SimpleNamespace(connection=connections["default"]))
        booking.refresh_from_db()
        second.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(booking.guest_profile_id, original_profile)
        self.assertEqual(second.guest_profile_id, original_profile)
        self.assertIsNone(manual.guest_profile_id)


class ConcurrentArrivalTests(TransactionTestCase):
    def test_two_arrival_requests_record_one_action(self):
        resort, room, tariff, manager, _ = fixture()
        today = timezone.localdate()
        booking = Booking.objects.create(
            resort=resort,
            room=room,
            tariff=tariff,
            stay=Range(today, today + timedelta(days=2)),
            guests=1,
            guest_label="Гость",
            owner="owner",
            source="website",
            status="confirmed",
            request_key=uuid.uuid4(),
            request_hash="test",
        )
        DemoPayment.objects.create(
            booking=booking,
            request_key=uuid.uuid4(),
            outcome="success",
            status="paid",
            amount=10000,
        )
        barrier = Barrier(2)

        def arrive():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    change_stay(
                        SimpleNamespace(user=manager, data={"version": 1}), booking.pk, "check-in"
                    )
                    return 200
                except Problem as exc:
                    return exc.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: arrive(), range(2)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(Audit.objects.filter(action="check-in").count(), 1)
